"""Tests hors échantillon des « boosts » sur les prédictions jugées (archives ia-archives + juges.json).

Rien ici ne touche au direct. Règles anti-triche :
- une prédiction faite à t0 n'utilise que des résultats connus à t0 (échéance <= t0) ;
- walk-forward par blocs d'une heure : on entraîne sur tout ce qui est connu avant le bloc, on teste sur le bloc ;
- contrôle « prix mélangés » : on mélange les résultats entre prédictions et on refait tout ; il faut retomber vers 50 %.

Usage : python -m ia.boost.tester tous.json [sortie.md]
"""
import json
import math
import random
import sys
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np

P8 = ["GOLD", "SILVER", "OIL_CRUDE", "US100", "US500", "DE40", "EURUSD", "GBPUSD"]
PARIS = ZoneInfo("Europe/Paris")
HS = [5, 15, 30, 60]


def ts(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()


def preparer(items):
    X = [dict(x) for x in items if x.get("p") and x["h"] in HS]
    for x in X:
        x["t0"] = ts(x["t"])
        x["p"] = {m: v for m, v in x["p"].items()}
        x["vote"] = float(np.mean(list(x["p"].values())))
        x["hp"] = datetime.fromtimestamp(x["t0"], PARIS).hour + datetime.fromtimestamp(x["t0"], PARIS).minute / 60
    X.sort(key=lambda x: x["t0"])
    return X


def contexte(X):
    """Indicateurs connus à t0 : derniers résultats du marché et réussite récente du vote (échéance <= t0)."""
    par_ech = sorted(X, key=lambda x: x["ech"])
    k = 0
    der_marche = defaultdict(lambda: deque(maxlen=6))   # derniers (up, mv/sqrt(h)) par marché
    acc_vote = defaultdict(lambda: deque(maxlen=30))    # réussite du vote par horizon (8 marchés)
    acc_mod = defaultdict(lambda: deque(maxlen=200))     # réussite de chaque IA par horizon (tous marchés)
    for x in X:
        while k < len(par_ech) and par_ech[k]["ech"] <= x["t0"]:
            y = par_ech[k]; k += 1
            der_marche[y["e"]].append((y["up"], y["mv"] / math.sqrt(y["h"])))
            if y["e"] in P8:
                acc_vote[y["h"]].append(int((y["vote"] > 0.5) == bool(y["up"])))
            for m, p in y["p"].items():
                acc_mod[(y["h"], m)].append(int((p > 0.5) == bool(y["up"])))
        d = der_marche[x["e"]]
        x["c_up"] = np.mean([u for u, _ in d]) if d else 0.5
        x["c_mv"] = float(np.mean([v for _, v in d])) if d else 0.0
        a = acc_vote[x["h"]]
        x["c_accv"] = np.mean(a) if len(a) >= 5 else 0.5
        x["c_acc"] = {m: (np.mean(acc_mod[(x["h"], m)]) if len(acc_mod[(x["h"], m)]) >= 30 else None) for m in x["p"]}


MODELES = None


def vecteur(x):
    return [x["p"].get(m, 0.5) for m in MODELES] + [x["vote"], x["hp"], x["h"], x["c_up"], x["c_mv"], x["c_accv"], x["sp"],
                                                     x["vote"] - 0.5 if x["c_accv"] >= 0.5 else 0.5 - x["vote"]]


def evaluer(X, h, graine=0):
    """Walk-forward par heure. Renvoie {stratégie: liste de (prédit hausse ?, x)} sur les 8 marchés, horizon h."""
    import lightgbm as lgb
    res = defaultdict(list)
    t_debut = X[0]["t0"] + 3 * 3600  # 3 h d'apprentissage avant le premier test
    blocs = np.arange(t_debut, X[-1]["t0"] + 1, 3600)
    for b in blocs:
        test = [x for x in X if b <= x["t0"] < b + 3600 and x["h"] == h and x["e"] in P8]
        if not test:
            continue
        train = [x for x in X if x["ech"] <= b]  # purge : résultat connu avant le bloc
        if len(train) < 300:
            continue
        # A. vote, B. Moirai seule
        for x in test:
            res["Vote de toutes les IA"].append((x["vote"] > 0.5, x))
            if "moirai2" in x["p"]:
                res["Moirai 2 seule"].append((x["p"]["moirai2"] > 0.5, x))
        # C. champion dynamique : la meilleure IA connue avant t0 (même horizon)
        for x in test:
            acc = {m: a for m, a in x["c_acc"].items() if a is not None}
            if acc:
                m = max(acc, key=acc.get)
                res["Champion du moment"].append((x["p"][m] > 0.5, x))
        # D. anti-retournement simple : si le vote se trompe souvent depuis peu, on prend le sens inverse
        for x in test:
            sens = x["vote"] > 0.5
            res["Anti-retournement (règle)"].append((sens if x["c_accv"] >= 0.45 else not sens, x))
        # E. correcteur LightGBM (toutes les données connues, tous marchés) + F. avec droit de ne pas parier
        Xtr = np.array([vecteur(x) for x in train]); ytr = np.array([x["up"] for x in train])
        mod = lgb.LGBMClassifier(n_estimators=120, learning_rate=0.05, num_leaves=8, min_child_samples=40,
                                 subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=graine)
        mod.fit(Xtr, ytr)
        pt = mod.predict_proba(np.array([vecteur(x) for x in test]))[:, 1]
        # seuil de confiance choisi sur le passé (8 marchés, même horizon) pour maximiser le gain après frais
        passe = [x for x in train if x["h"] == h and x["e"] in P8]
        seuil = 0.0
        if len(passe) >= 50:
            pp = mod.predict_proba(np.array([vecteur(x) for x in passe]))[:, 1]
            meilleur = -1e9
            for s in (0.0, 0.03, 0.06, 0.1, 0.15):
                g = [((x["mv"] if q > 0.5 else -x["mv"]) - x["sp"]) for x, q in zip(passe, pp) if abs(q - 0.5) >= s]
                if len(g) >= 20 and np.mean(g) > meilleur:
                    meilleur, seuil = np.mean(g), s
        for x, q in zip(test, pt):
            res["Correcteur LightGBM"].append((q > 0.5, x))
            if abs(q - 0.5) >= seuil:
                res["Correcteur + ne parie que si sûr"].append((q > 0.5, x))
    return res


def resume(lst):
    if not lst:
        return None
    n = len(lst); j = sum(s == bool(x["up"]) for s, x in lst)
    g = [((x["mv"] if s else -x["mv"]) - x["sp"]) for s, x in lst]
    return {"n": n, "acc": j / n, "gain": float(np.mean(g)), "inst": len({x["t"] for _, x in lst}),
            "maj": max(sum(x["up"] for _, x in lst), n - sum(x["up"] for _, x in lst)) / n}


def melanger(X, graine):
    """Prix mélangés : on redistribue au hasard les résultats (sens + mouvement) entre les prédictions."""
    r = random.Random(graine)
    res = [(x["up"], x["mv"]) for x in X]
    r.shuffle(res)
    Y = [dict(x) for x in X]
    for y, (u, mv) in zip(Y, res):
        y["up"], y["mv"] = u, mv
    return Y


def principal():
    global MODELES
    items = json.load(open(sys.argv[1]))
    X = preparer(items)
    MODELES = sorted({m for x in X for m in x["p"]})
    contexte(X)
    L = ["| Horizon | Stratégie | Prédictions (instants) | Réussite | Gain moyen après frais | Prix mélangés : réussite |", "|---|---|---|---|---|---|"]
    for h in (15, 5, 60):
        reel = evaluer(X, h)
        Y = preparer([{k: v for k, v in x.items() if k not in ("t0", "vote", "hp")} for x in melanger(X, 7)])
        contexte(Y)
        faux = evaluer(Y, h)
        for s, lst in reel.items():
            r, f = resume(lst), resume(faux.get(s, []))
            L.append(f"| {h} min | {s} | {r['n']} ({r['inst']}) | {100 * r['acc']:.1f} % | {r['gain']:+.4f} % | {100 * f['acc']:.1f} % |" if f else
                     f"| {h} min | {s} | {r['n']} ({r['inst']}) | {100 * r['acc']:.1f} % | {r['gain']:+.4f} % | — |")
    txt = "\n".join(L)
    print(txt)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(txt)


if __name__ == "__main__":
    principal()

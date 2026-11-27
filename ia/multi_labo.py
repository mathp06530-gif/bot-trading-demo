"""LABO de l'IA unique « multi-cerveaux » sur des ANNÉES de bougies (le direct n'a qu'un jour de données).

But : savoir, sur des centaines de changements de régime (tendance -> retournement), si un méta-cerveau qui
choisit QUI écouter fait mieux que le vote simple et que la meilleure IA seule, APRÈS le vrai spread.

Étapes (tout en walk-forward, rien du futur) :
 1. CERVEAUX (14) : 3 IA apprises (logistique, LightGBM, forêt) réentraînées chaque mois sur le passé seulement
    + 11 cerveaux de règles (élan 1/4/16/64 bougies, retour à la moyenne, RSI contrarien, cassure du range,
    croisement de moyennes, MACD, tendance « propre » (efficiency ratio), heure de la journée apprise sur le passé).
    Chaque cerveau a aussi son MIROIR (le sens inverse) : 28 avis.
 2. MÉTA-CERVEAUX (ils ne mélangent pas les avis à l'aveugle, ils choisissent qui écouter) :
    - vote simple (référence) ; champion du mois (meilleur cerveau sur le passé) ;
    - Fixed Share global (suit le meilleur cerveau du moment, se rattrape vite après un retournement) ;
    - Fixed Share PAR RÉGIME (tendance / retournement / neutre x calme / agité) ;
    - « aiguilleur » LightGBM (mixture of experts) : apprend, sur le passé, quel cerveau croire selon le régime
      (efficiency ratio, volatilité relative, heure, réussite récente de chaque cerveau) ;
    - CHEF : Fixed Share au-dessus des méta-cerveaux ;
    - ÉLÈVE (distillation) : un seul petit LightGBM sur les indicateurs bruts, entraîné à imiter l'aiguilleur.
 3. ABSTENTION (méta-labeling) : chaque méta-cerveau a une version « seulement si sûr » : seuil de confiance
    choisi sur le passé pour le meilleur gain après spread ; s'il n'y a aucun seuil gagnant, il ne parie pas.
 4. CONTRÔLE ANTI-TRICHE : on refait EXACTEMENT tout sur des prix mélangés (rendements des bougies permutés,
    spreads gardés) ; tout ce qui y dépasse ~53 % est jeté.

Usage : python ia/multi_labo.py tester <dossier_prix> <EPIC> <UNITE> <sortie.json>
        python ia/multi_labo.py bilan <dossier_resultats> <sortie.md> <sortie.json>
        python ia/multi_labo.py synthetique <sortie.json>   (vérification du moteur sur des prix inventés)
"""
import json
import math
import os
import sys
from collections import defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

MOIS_TEST = int(os.getenv("LABO_MOIS_TEST", "12"))      # mois jugés (les plus récents)
MOIS_CHAUFFE = int(os.getenv("LABO_MOIS_CHAUFFE", "4"))  # mois où les cerveaux prédisent déjà mais où les méta-cerveaux apprennent seulement
TRAIN_MAX = int(os.getenv("LABO_TRAIN_MAX", "40000"))
ETA = float(os.getenv("LABO_ETA", "3"))
ALPHA = float(os.getenv("LABO_ALPHA", "0.01"))
MIN_REGIME = 300
SEUILS = (0.0, 0.01, 0.02, 0.03, 0.05, 0.08)
FEN_SEUIL, MIN_SEUIL = 3000, 200
UNITE_MIN = {"MINUTE_5": 5, "MINUTE_15": 15, "HOUR": 60}
APPRIS = ["logistique", "lightgbm", "foret"]
COLS = None


# --------------------------------------------------------------------------- données
def preparer(d: pd.DataFrame, minutes: int, melange_graine=None):
    """Indicateurs connus à la clôture t, cible = sens de la bougie suivante, mouvement % et spread %."""
    from ia.predire import indicateurs
    d = d.copy()
    mid = (d.close_bid + d.close_ask) / 2
    sp = ((d.close_ask - d.close_bid) / mid * 100).clip(lower=0)
    if melange_graine is not None:  # prix mélangés : on permute les rendements, on reconstruit un chemin
        r = np.log(mid).diff().fillna(0).to_numpy()
        rng = np.random.default_rng(melange_graine)
        r = rng.permutation(r)
        nm = mid.iloc[0] * np.exp(np.cumsum(r))
        k = nm / mid.to_numpy()
        for c in [c for c in d.columns if c != "volume"]:
            d[c] = d[c] * k
        mid = pd.Series(nm, index=d.index)
    f = indicateurs(d)
    lc = np.log(mid)
    r1 = lc.diff()
    f["er16"] = (lc - lc.shift(16)).abs() / r1.abs().rolling(16).sum()
    f["vrel"] = r1.abs().rolling(16).mean() / r1.abs().rolling(400, min_periods=100).mean()
    suiv = mid.shift(-1)
    ecart = pd.Series(d.index, index=d.index).diff().shift(-1).dt.total_seconds() / 60
    f["mv"] = (suiv / mid - 1) * 100
    f["sp"] = sp
    f["y"] = (f["mv"] > 0).astype(float)
    ok = (ecart <= 2 * minutes) & (f["mv"] != 0) & f["mv"].notna()
    f = f[ok].replace([np.inf, -np.inf], np.nan).dropna()
    return f


# --------------------------------------------------------------------------- cerveaux
def regles(f: pd.DataFrame) -> dict:
    s = lambda x: 0.5 + 0.05 * np.sign(x)  # noqa: E731
    return {
        "elan1": s(f.r1), "elan4": s(f.r5), "elan16": s(f.r20), "elan64": s(f.r50),
        "retour_moyenne": s(-f.ema20), "rsi_contrarien": s(50 - f.rsi), "cassure_range": s(f.pos20 - 0.5),
        "croisement_moyennes": s(f.ema20 - f.ema50), "macd": s(f.macd),
        "tendance_propre": 0.5 + 0.05 * np.sign(f.r20) * (f.er16 > 0.35),
    }


def cerveaux(f: pd.DataFrame, blocs):
    """Probabilités de chaque cerveau pour chaque bougie des blocs (walk-forward, mois par mois)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import ExtraTreesClassifier
    import lightgbm as lgb
    cols = [c for c in f.columns if c not in ("mv", "sp", "y", "er16", "vrel")]
    P = pd.DataFrame(index=f.index)
    for nom, v in regles(f).items():
        P[nom] = v
    for nom in APPRIS + ["heure"]:
        P[nom] = np.nan
    X, y = f[cols].to_numpy(), f.y.to_numpy()
    heure = f.index.hour
    for debut, fin in blocs:
        tr = np.where(f.index < debut - pd.Timedelta(hours=2))[0][-TRAIN_MAX:]  # 2 h de trou (purge)
        te = np.where((f.index >= debut) & (f.index < fin))[0]
        if len(tr) < 2000 or not len(te):
            continue
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        m = LogisticRegression(C=0.1, max_iter=300).fit((X[tr] - mu) / sd, y[tr])
        P.iloc[te, P.columns.get_loc("logistique")] = m.predict_proba((X[te] - mu) / sd)[:, 1]
        m = lgb.LGBMClassifier(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=200, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.7, reg_lambda=5, verbose=-1, random_state=0).fit(X[tr], y[tr])
        P.iloc[te, P.columns.get_loc("lightgbm")] = m.predict_proba(X[te])[:, 1]
        m = ExtraTreesClassifier(n_estimators=80, min_samples_leaf=300, max_features=0.5, n_jobs=-1, random_state=0).fit(X[tr], y[tr])
        P.iloc[te, P.columns.get_loc("foret")] = m.predict_proba(X[te])[:, 1]
        taux = pd.Series(y[tr]).groupby(heure[tr]).agg(["mean", "count"])
        hz = taux["mean"].where(taux["count"] >= 100, 0.5).clip(0.45, 0.55)
        P.iloc[te, P.columns.get_loc("heure")] = pd.Series(heure[te]).map(hz).fillna(0.5).to_numpy()
    return P


# --------------------------------------------------------------------------- méta-cerveaux en ligne
class FS:
    def __init__(self, k):
        self.lw = np.zeros(k)
        self.n = 0

    def q(self, a):
        w = np.exp(self.lw - self.lw.max())
        return float(w @ a / w.sum())

    def maj(self, a, y):
        a = np.clip(a, 1e-3, 1 - 1e-3)
        self.lw += ETA * np.log(a if y else 1 - a)
        w = np.exp(self.lw - self.lw.max())
        w = (1 - ALPHA) * w / w.sum() + ALPHA / len(w)
        self.lw = np.log(w)
        self.n += 1


def en_ligne(f: pd.DataFrame, P: pd.DataFrame, t_meta):
    """Fixed Share global et par régime, bougie par bougie : la prédiction à t utilise les résultats <= t-1."""
    noms = list(P.columns)
    A = P.to_numpy()
    A = np.concatenate([A, 1 - A], axis=1)  # cerveaux + miroirs
    k = A.shape[1]
    y = f.y.to_numpy()
    er, vrel = f.er16.to_numpy(), f.vrel.to_numpy()
    glob, reg = FS(k), defaultdict(lambda: FS(k))
    suiv = deque(maxlen=50)
    sig1 = np.sign(f.r1.to_numpy())
    qg, qr, regs = np.full(len(f), np.nan), np.full(len(f), np.nan), [""] * len(f)
    racc = np.full((len(f), len(noms)), 0.5)    # réussite récente de chaque cerveau (pour l'aiguilleur)
    acc = deque(maxlen=200)
    for i in range(len(f)):
        if np.isnan(A[i]).any():
            continue
        if acc:
            racc[i] = np.mean(acc, axis=0)
        a_s = np.mean(suiv) if len(suiv) >= 20 else 0.5
        tend = "tendance" if a_s >= 0.54 or er[i] > 0.5 else "retournement" if a_s <= 0.46 else "neutre"
        r = f"{tend}|{'agite' if vrel[i] > 1.3 else 'calme'}"
        regs[i] = r
        qg[i] = glob.q(A[i])
        fr = reg[r]
        qr[i] = fr.q(A[i]) if fr.n >= MIN_REGIME else qg[i]
        # le résultat de la bougie i n'est connu qu'à la clôture de la suivante : on apprend APRÈS avoir prédit i
        glob.maj(A[i], y[i])
        fr.maj(A[i], y[i])
        acc.append((A[i, :len(noms)] > 0.5) == y[i])
        if i + 1 < len(f):
            suiv.append(int(np.sign(sig1[i + 1]) == np.sign(sig1[i])) if sig1[i] else 0)
    return qg, qr, regs, racc


def aiguilleur(f, P, racc, blocs):
    """Mixture of experts apprise : LightGBM sur (avis des cerveaux, réussite récente, régime), réentraîné chaque mois."""
    import lightgbm as lgb
    signe = (P.to_numpy() - 0.5) * (2 * racc - 1)  # avis de chaque cerveau x son avance récente (qui croire en ce moment)
    X = np.column_stack([P.to_numpy(), racc, signe, signe.sum(1), f[["er16", "vrel", "vol10", "vol50", "h_sin", "h_cos", "rsi", "r1", "r5"]].to_numpy()])
    y = f.y.to_numpy()
    q = np.full(len(f), np.nan)
    ok = ~np.isnan(X).any(1)
    for debut, fin in blocs:
        tr = np.where(ok & (f.index < debut - pd.Timedelta(hours=2)))[0][-TRAIN_MAX:]
        te = np.where(ok & (f.index >= debut) & (f.index < fin))[0]
        if len(tr) < 3000 or not len(te):
            continue
        m = lgb.LGBMClassifier(n_estimators=150, learning_rate=0.03, num_leaves=7, min_child_samples=300, subsample=0.8,
                               subsample_freq=1, colsample_bytree=0.6, reg_lambda=10, verbose=-1, random_state=1).fit(X[tr], y[tr])
        q[te] = m.predict_proba(X[te])[:, 1]
    return q


def eleve(f, cible, blocs):
    """Distillation : un seul LightGBM sur les indicateurs bruts, entraîné à imiter la probabilité de l'aiguilleur."""
    import lightgbm as lgb
    cols = [c for c in f.columns if c not in ("mv", "sp", "y")]
    X = f[cols].to_numpy()
    q = np.full(len(f), np.nan)
    for debut, fin in blocs:
        tr = np.where(~np.isnan(cible) & (f.index < debut - pd.Timedelta(hours=2)))[0][-TRAIN_MAX:]
        te = np.where((f.index >= debut) & (f.index < fin))[0]
        if len(tr) < 3000 or not len(te):
            continue
        m = lgb.LGBMRegressor(n_estimators=200, learning_rate=0.03, num_leaves=15, min_child_samples=200, verbose=-1,
                              random_state=2).fit(X[tr], cible[tr])
        q[te] = m.predict(X[te])
    return q


def chef(f, Q: dict):
    noms = list(Q)
    A = np.column_stack([Q[n] for n in noms])
    y = f.y.to_numpy()
    fs = FS(len(noms))
    q = np.full(len(f), np.nan)
    for i in range(len(f)):
        if np.isnan(A[i]).any():
            continue
        q[i] = fs.q(A[i])
        fs.maj(A[i], y[i])
    return q


def abstention(f, q, sur_test):
    """Seuil choisi sur les FEN_SEUIL dernières prédictions déjà jugées (gain moyen après spread), rien du futur."""
    mv, sp = f.mv.to_numpy(), f.sp.to_numpy()
    garde = np.zeros(len(f), bool)
    hist_c, hist_g = deque(maxlen=FEN_SEUIL), deque(maxlen=FEN_SEUIL)
    seuil, maj = None, 0
    for i in range(len(f)):
        if np.isnan(q[i]):
            continue
        c = abs(q[i] - 0.5)
        if maj % 200 == 0 and len(hist_c) >= MIN_SEUIL:
            hc, hg = np.array(hist_c), np.array(hist_g)
            best, seuil = 0.0, None
            for s in SEUILS:
                m = hc >= s
                if m.sum() >= MIN_SEUIL and hg[m].mean() > best:
                    best, seuil = hg[m].mean(), s
        maj += 1
        garde[i] = seuil is not None and c >= seuil
        hist_c.append(c)
        hist_g.append((mv[i] if q[i] > 0.5 else -mv[i]) - sp[i])
    return garde


# --------------------------------------------------------------------------- évaluation
def mesurer(f, q, garde=None, masque=None):
    m = ~np.isnan(q)
    if masque is not None:
        m &= masque
    if garde is not None:
        m &= garde
    if m.sum() == 0:
        return None
    hausse = q[m] > 0.5
    y, mv, sp = f.y.to_numpy()[m], f.mv.to_numpy()[m], f.sp.to_numpy()[m]
    g = np.where(hausse, mv, -mv) - sp
    mois = f.index[m].to_period("M")
    gm = pd.Series(g).groupby(np.asarray(mois)).mean()
    return {"n": int(m.sum()), "reussite": round(float((hausse == (y > 0.5)).mean()), 4), "gain": round(float(g.mean()), 5),
            "gain_brut": round(float(np.where(hausse, mv, -mv).mean()), 5),
            "t": round(float(g.mean() / (g.std() + 1e-12) * math.sqrt(len(g))), 2),
            "mois_positifs": int((gm > 0).sum()), "mois": int(len(gm))}


def tout(f: pd.DataFrame):
    fin = f.index.max()
    debut_test = fin - pd.DateOffset(months=MOIS_TEST)
    debut_c = debut_test - pd.DateOffset(months=MOIS_CHAUFFE)
    bornes = pd.date_range(debut_c, fin + pd.Timedelta(days=31), freq="MS")
    bornes = [debut_c] + [b for b in bornes if b > debut_c]
    blocs = list(zip(bornes[:-1], bornes[1:]))
    P = cerveaux(f, blocs)
    racc_cols = list(P.columns)
    qg, qr, regs, racc = en_ligne(f, P, debut_c)
    blocs_meta = [b for b in blocs if b[0] >= debut_c + pd.DateOffset(months=2)]
    qa = aiguilleur(f, P, racc, blocs_meta)
    qe = eleve(f, qa, [b for b in blocs if b[0] >= debut_test])
    vote = P.mean(axis=1).to_numpy()
    # champion du mois : le cerveau (ou son miroir) le plus juste sur tout le passé jugé
    Ab = P.to_numpy()
    yv = f.y.to_numpy()
    qc = np.full(len(f), np.nan)
    for debut, fin_b in blocs:
        if debut < debut_c + pd.DateOffset(months=1):
            continue
        p_ = np.where((f.index >= debut_c) & (f.index < debut))[0]
        te = np.where((f.index >= debut) & (f.index < fin_b))[0]
        ok = ~np.isnan(Ab[p_]).any(1)
        if ok.sum() < 500:
            continue
        acc = ((Ab[p_][ok] > 0.5) == (yv[p_][ok, None] > 0.5)).mean(0)
        j = int(np.argmax(np.abs(acc - 0.5)))
        qc[te] = Ab[te, j] if acc[j] >= 0.5 else 1 - Ab[te, j]
    Q = {"Vote simple": vote, "Champion du mois": qc, "Fixed Share global": qg, "Fixed Share par régime": qr,
         "Aiguilleur (mixture of experts)": qa}
    Q["CHEF (IA unique)"] = chef(f, {k: np.where(np.isnan(v), 0.5, v) for k, v in Q.items()})
    Q["Élève (distillation)"] = qe
    test = np.asarray(f.index >= debut_test)
    moitie = f.index[test].min() + (f.index.max() - f.index[test].min()) / 2
    res = {}
    regs_a = np.array(regs)
    for nom, q in Q.items():
        garde = abstention(f, q, test)
        res[nom] = {"toujours": mesurer(f, q, masque=test), "si_sur": mesurer(f, q, garde, test),
                    "moitie1": mesurer(f, q, masque=test & np.asarray(f.index < moitie)),
                    "moitie2": mesurer(f, q, masque=test & np.asarray(f.index >= moitie)),
                    "regimes": {r: mesurer(f, q, masque=test & (regs_a == r)) for r in sorted(set(regs_a[test])) if r}}
    for c in racc_cols:
        res.setdefault("_cerveaux", {})[c] = mesurer(f, P[c].to_numpy(), masque=test)
    res["_periode"] = [str(debut_test), str(f.index.max())]
    res["_sens_majoritaire"] = round(float(max(yv[test].mean(), 1 - yv[test].mean())), 4)
    return res


def tester(dossier, epic, unite, sortie):
    from ia.predire import lire
    d = lire(Path(dossier), epic, unite)
    if d is None or len(d) < 20000:
        print(epic, unite, ": pas assez de données")
        return
    minutes = UNITE_MIN[unite]
    out = {"epic": epic, "unite": unite}
    out["reel"] = tout(preparer(d, minutes))
    out["melange"] = tout(preparer(d, minutes, melange_graine=7))
    Path(sortie).write_text(json.dumps(out, ensure_ascii=False))
    for k in ("reel", "melange"):
        for nom, r in out[k].items():
            if not nom.startswith("_") and r["toujours"]:
                t, s = r["toujours"], r["si_sur"] or {}
                print(f"{k:7s} {epic} {unite} {nom:32s} {100 * t['reussite']:.2f} % gain {t['gain']:+.4f} | sûr {100 * s.get('reussite', 0):.2f} % "
                      f"n={s.get('n', 0)} gain {s.get('gain', 0):+.4f}")


def synthetique(sortie):
    """Prix inventés à régimes : tendance (élan marche) puis retournement (contrarien marche), par blocs de 1-3 jours."""
    rng = np.random.default_rng(3)
    n = 2 * 365 * 96
    idx = pd.date_range("2024-11-01", periods=n, freq="15min")
    r = np.zeros(n)
    rho, i = 0.15, 0
    while i < n:
        L = rng.integers(96, 288)
        rho = -rho if rng.random() < 0.7 else rho
        for j in range(i, min(n, i + L)):
            r[j] = rho * r[j - 1] + rng.normal(0, 1e-3) if j else rng.normal(0, 1e-3)
        i += L
    mid = 2000 * np.exp(np.cumsum(r))
    d = pd.DataFrame(index=idx)
    for c in ("open", "high", "low", "close"):
        d[f"{c}_bid"] = mid * (1 - 5e-5)
        d[f"{c}_ask"] = mid * (1 + 5e-5)
    d["high_bid"] *= 1 + 3e-4
    d["high_ask"] *= 1 + 3e-4
    d["low_bid"] *= 1 - 3e-4
    d["low_ask"] *= 1 - 3e-4
    d["volume"] = 1.0
    out = {"epic": "SYNTH", "unite": "MINUTE_15", "reel": tout(preparer(d, 15)), "melange": tout(preparer(d, 15, 7))}
    Path(sortie).write_text(json.dumps(out, ensure_ascii=False))
    for k in ("reel", "melange"):
        for nom, x in out[k].items():
            if not nom.startswith("_") and x["toujours"]:
                print(k, nom, x["toujours"]["reussite"], x["toujours"]["gain"])


def bilan(dossier, sortie_md, sortie_json):
    R = [json.loads(p.read_text()) for p in sorted(Path(dossier).glob("*.json"))]
    tab = defaultdict(lambda: defaultdict(list))
    for r in R:
        for k in ("reel", "melange"):
            for nom, x in r.get(k, {}).items():
                if not nom.startswith("_"):
                    tab[(r["unite"], nom)][k].append((r["epic"], x))
    L = ["# IA unique multi-cerveaux : labo sur l'historique (12 derniers mois jamais vus)", "",
         "Chaque ligne : moyenne sur les marchés. Gain = gain moyen par prédiction APRÈS le vrai spread (en % du prix).",
         "« Prix mélangés » = la même chaîne complète refaite sur des prix sans aucune structure (doit donner ~50 %).", ""]
    nb_essais = 0
    resume_l = []
    for unite in sorted({u for u, _ in tab}):
        L += [f"## {unite}", "", "| Méta-cerveau | Réussite | Gain après spread | Si sûr : réussite / couverture / gain | Marchés gagnants (si sûr) | Mois positifs (si sûr) | Prix mélangés (réussite, si sûr) |", "|---|---|---|---|---|---|---|"]
        for (u, nom), d in tab.items():
            if u != unite:
                continue
            nb_essais += 2 * len(d["reel"])
            t = [x["toujours"] for _, x in d["reel"] if x["toujours"]]
            s = [x["si_sur"] for _, x in d["reel"] if x["si_sur"]]
            fm = [x["si_sur"] or x["toujours"] for _, x in d["melange"] if x["toujours"]]
            if not t:
                continue
            ntot = sum(x["n"] for x in t)
            resume_l.append({"unite": unite, "nom": nom, "reussite": round(float(np.mean([x["reussite"] for x in t])), 4),
                             "gain": round(float(np.mean([x["gain"] for x in t])), 5), "n": ntot,
                             "sur_reussite": round(float(np.mean([x["reussite"] for x in s])), 4) if s else None,
                             "sur_gain": round(float(np.mean([x["gain"] for x in s])), 5) if s else None,
                             "sur_couverture": round(sum(x["n"] for x in s) / ntot, 3) if s else 0,
                             "sur_marches_gagnants": f"{sum(x['gain'] > 0 for x in s)}/{len(s)}" if s else "0/0",
                             "melange": round(float(np.mean([x["reussite"] for x in fm])), 4) if fm else None,
                             "marches": len(t)})
            L.append(f"| {nom} | {100 * np.mean([x['reussite'] for x in t]):.2f} % | {np.mean([x['gain'] for x in t]):+.4f} % | "
                     + (f"{100 * np.mean([x['reussite'] for x in s]):.2f} % / {100 * sum(x['n'] for x in s) / ntot:.0f} % / {np.mean([x['gain'] for x in s]):+.4f} % | "
                        f"{sum(x['gain'] > 0 for x in s)}/{len(s)} | {sum(x['mois_positifs'] for x in s)}/{sum(x['mois'] for x in s)} | " if s else "ne parie jamais | — | — | ")
                     + (f"{100 * np.mean([x['reussite'] for x in fm]):.2f} % |" if fm else "— |"))
        L.append("")
    L += [f"Essais comptés (méta-cerveau x marché x version) : {nb_essais}.", ""]
    Path(sortie_md).write_text("\n".join(L))
    from datetime import datetime, timezone
    Path(sortie_json).write_text(json.dumps({"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                             "essais": nb_essais, "lignes": resume_l,
                                             "marches": sorted({r["epic"] for r in R})}, ensure_ascii=False))
    print("\n".join(L))


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "tester":
        tester(*sys.argv[2:6])
    elif c == "bilan":
        bilan(*sys.argv[2:5])
    elif c == "synthetique":
        synthetique(sys.argv[2])

"""LABO n°5 « gros gains » (27/11/2026, demande de Mathis : +0,023 %/trade et ~50 trades/mois, c'est trop peu).

Base : le signal CONFIRMÉ « vote simple des 14 cerveaux, bougies 4 h, seulement ses plus sûres » (ia/multi_labo.py,
réglages inchangés). On cherche à augmenter le GAIN PAR SIGNAL et le NOMBRE de signaux :
  1. sorties : tenir 1 / 2 / 3 / 6 bougies 4 h ; objectif + stop en ATR (sortie au premier touché, stop d'abord si
     les deux dans la même bougie) ; stop suiveur en ATR ;
  2. seuil de confiance : 5 / 10 / 20 % plus sûres (seuil pris sur le passé) ;
  3. taille selon la confiance (1x à 3x) ;
  4. PLUS DE MARCHÉS : ~20 marchés Capital.com en plus, jamais regardés avec ce signal (vrai test hors échantillon).
Tout est simulé bougie par bougie au VRAI prix (achat au prix acheteur, vente au prix vendeur), une position à la fois
par marché, AVEC LES FRAIS DE NUIT Capital.com (à chaque 22 h UTC passée, week-end compris).

Anti-triche : réglages CHOISIS sur 2021-11 -> 2024-11 (8 marchés d'origine), JUGÉS sur 2024-11 -> maintenant et sur
les marchés nouveaux ; tout refait sur prix mélangés (2 graines) ; jeté si la réussite y dépasse ~53 %.

Usage : python ia/labo_gains.py telecharger <dossier> <EPIC...>
        python ia/labo_gains.py tester <dossier> <EPIC> <sortie.json>
        python ia/labo_gains.py bilan <dossier_resultats> <sortie.md> <sortie.json>
"""
import json
import os
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

os.environ["LABO_H"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ia.multi_labo as L  # noqa: E402

DEBUT = pd.Timestamp(os.getenv("LABO5_DEBUT", "2021-05-27"))       # début des cerveaux (6 mois de chauffe pour les seuils)
CHOIX = (pd.Timestamp("2021-11-27"), pd.Timestamp("2024-11-27"))  # période où l'on CHOISIT les réglages
ORIGINE = L.MARCHES
NOUVEAUX = ["US30", "UK100", "FR40", "EU50", "J225", "HK50", "AU200", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
            "EURJPY", "EURGBP", "NATURALGAS", "COPPER", "PLATINUM", "OIL_BRENT", "BTCUSD", "ETHUSD"]
GRAINES = (7, 11)
COUV = (0.05, 0.1, 0.2)


def sorties():
    s = [("tenir", n, None, None) for n in (1, 2, 3, 6)]
    s += [("atr", n, st, ob) for n, st, ob in product((3, 6), (1.0, 1.5, 2.0), (1.0, 2.0, 3.0))]
    s += [("suiveur", n, k, None) for n, k in product((6, 12), (1.0, 1.5, 2.0))]
    return s


SORTIES = sorties()


def nom_sortie(s):
    g, n, a, b = s
    if g == "tenir":
        return f"tenir {n} x 4 h"
    if g == "atr":
        return f"stop {a} ATR / objectif {b} ATR / max {n} x 4 h"
    return f"stop suiveur {a} ATR / max {n} x 4 h"


def nuits(t0, t1):
    """Nombre de 22 h UTC passés entre l'entrée et la sortie (frais de nuit Capital.com, week-end compris)."""
    a = (t0 - pd.Timedelta(hours=22)).normalize()
    b = (t1 - pd.Timedelta(hours=22)).normalize()
    return max(0, int((b - a).days))


def simuler(d, sig, s, nuit_achat, nuit_vente):
    """sig : DataFrame (index = bougie t, colonnes sens ±1, poids). Entrée à la clôture de t. Une position à la fois."""
    g, n, a, b = s
    idx = d.index
    pos_de = {t: i for i, t in enumerate(idx)}
    ob_, oa_ = d.open_bid.to_numpy(), d.open_ask.to_numpy()
    hb, ha, lb, la = d.high_bid.to_numpy(), d.high_ask.to_numpy(), d.low_bid.to_numpy(), d.low_ask.to_numpy()
    cb, ca = d.close_bid.to_numpy(), d.close_ask.to_numpy()
    mid = (cb + ca) / 2
    hm, lm = (hb + ha) / 2, (lb + la) / 2
    tr = np.maximum(hm[1:] - lm[1:], np.maximum(np.abs(hm[1:] - mid[:-1]), np.abs(lm[1:] - mid[:-1])))
    atr = pd.Series(np.r_[np.nan, tr]).rolling(14).mean().to_numpy()
    trades, libre = [], -1
    for t, r in sig.iterrows():
        i = pos_de.get(t)
        if i is None or i <= libre or i + 1 >= len(idx) or not atr[i] == atr[i]:
            continue
        sens, A = int(r.sens), atr[i]
        ent = ca[i] if sens > 0 else cb[i]
        stop = ent - sens * a * A if g in ("atr", "suiveur") else None
        obj = ent + sens * b * A if g == "atr" else None
        meilleur = ent
        sortie, j = None, i
        for j in range(i + 1, min(i + n, len(idx) - 1) + 1):
            if (idx[j] - idx[j - 1]) > pd.Timedelta(days=4):  # trou de données : on sort à l'ouverture
                sortie = ob_[j] if sens > 0 else oa_[j]
                break
            o_, h_, l_ = (ob_[j], hb[j], lb[j]) if sens > 0 else (oa_[j], ha[j], la[j])
            if stop is not None:
                if (sens > 0 and o_ <= stop) or (sens < 0 and o_ >= stop):
                    sortie = o_
                    break
                if (sens > 0 and l_ <= stop) or (sens < 0 and h_ >= stop):
                    sortie = stop
                    break
            if obj is not None:
                if (sens > 0 and o_ >= obj) or (sens < 0 and o_ <= obj):
                    sortie = o_
                    break
                if (sens > 0 and h_ >= obj) or (sens < 0 and l_ <= obj):
                    sortie = obj
                    break
            if g == "suiveur":  # le stop suit le meilleur prix de CLÔTURE (pas de regard dans la bougie)
                c_ = cb[j] if sens > 0 else ca[j]
                meilleur = max(meilleur, c_) if sens > 0 else min(meilleur, c_)
                stop = meilleur - sens * a * A if sens > 0 else meilleur + a * A
        if sortie is None:
            sortie = cb[j] if sens > 0 else ca[j]
        t_sortie = idx[j] + pd.Timedelta(minutes=240)
        brut = sens * (sortie - ent) / mid[i] * 100
        frais_n = nuits(idx[i] + pd.Timedelta(minutes=240), t_sortie) * (nuit_achat if sens > 0 else nuit_vente)
        trades.append((t, brut - frais_n, float(r.poids), sens * (sortie - ent) > 0, j - i))
        libre = j
    return trades


def resumer(trades, periode=None):
    if periode is not None:
        trades = [x for x in trades if periode[0] <= x[0] < periode[1]]
    if not trades:
        return None
    g = np.array([x[1] for x in trades])
    w = np.array([x[2] for x in trades])
    mois = pd.Series(g, index=pd.DatetimeIndex([x[0] for x in trades])).groupby(lambda t: (t.year, t.month)).sum()
    cum = np.cumsum(g)
    nmois = max(1.0, (trades[-1][0] - trades[0][0]).days / 30.44) if len(trades) > 1 else 1.0
    return {"n": len(g), "reussite": round(float(np.mean([x[3] for x in trades])), 4), "gain": round(float(g.mean()), 5),
            "gain_pondere": round(float((g * w).sum() / w.sum()), 5), "par_mois_pct": round(float(g.sum() / nmois), 4),
            "par_mois_pondere_pct": round(float((g * w).sum() / nmois), 4),
            "pire_baisse_pct": round(float((np.maximum.accumulate(np.r_[0, cum]) - np.r_[0, cum]).max()), 3),
            "mois_positifs": int((mois > 0).sum()), "mois": int(len(mois)), "tenue_moy": round(float(np.mean([x[4] for x in trades])), 2)}


def melanger(d, graine):
    mid = (d.close_bid + d.close_ask) / 2
    r = np.random.default_rng(graine).permutation(np.log(mid).diff().fillna(0).to_numpy())
    k = mid.iloc[0] * np.exp(np.cumsum(r)) / mid.to_numpy()
    d = d.copy()
    for c in [c for c in d.columns if c != "volume"]:
        d[c] = d[c] * k
    return d


def signaux(dossier, epic, d):
    L.PURGE = pd.Timedelta(hours=10)
    f = L.preparer(d, 240, croix=L.croises(dossier, epic, "HOUR_4", d.index), epic=epic)
    bornes = [DEBUT] + [b for b in pd.date_range(DEBUT, f.index.max() + pd.Timedelta(days=31), freq="MS") if b > DEBUT]
    P = L.cerveaux(f, list(zip(bornes[:-1], bornes[1:])))
    v = P.mean(axis=1)
    v = v[(v.index >= DEBUT) & P[L.APPRIS].notna().all(axis=1)]
    q = v.to_numpy()
    out = {}
    for c in COUV:
        garde = L.couverture(q, c)
        conf = np.abs(q - 0.5)
        s = pd.DataFrame({"sens": np.where(q > 0.5, 1, -1), "conf": conf}, index=v.index)[garde]
        # taille selon la confiance : 1x au seuil, jusqu'à 3x (connu au moment de la décision)
        seuil_ref = s.conf.rolling(200, min_periods=20).median().shift(1).bfill()
        s["poids"] = (s.conf / seuil_ref).clip(1, 3).fillna(1)
        out[c] = s
    return out


def tester(dossier, epic, sortie):
    from ia.predire import lire, frais_nuit
    d = lire(Path(dossier), epic, "HOUR_4")
    if d is None or len(d) < 6000 or d.index.min() > DEBUT - pd.DateOffset(months=18):
        print(epic, ": pas assez d'historique 4 h")
        return
    na, nv = frais_nuit(Path(dossier), epic)
    na, nv = na * 100, nv * 100  # en % par nuit
    fin = d.index.max() + pd.Timedelta(days=1)
    per = {"choix": CHOIX, "juge": (CHOIX[1], fin), "tout": (CHOIX[0], fin)}
    out = {"epic": epic, "nuit_pct": [round(na, 4), round(nv, 4)], "origine": epic in ORIGINE,
           "spread_moy_pct": round(float(((d.close_ask - d.close_bid) / ((d.close_ask + d.close_bid) / 2) * 100).tail(3000).mean()), 4),
           "reel": {}, "melange": {}}
    for cle, dd in [("reel", d)] + [(f"m{g}", melanger(d, g)) for g in GRAINES]:
        sig = signaux(dossier, epic, dd)
        res = {}
        for c, s in sig.items():
            for so in SORTIES:
                tr = simuler(dd, s, so, na, nv)
                res[f"{c}|{nom_sortie(so)}"] = {k: resumer(tr, p) for k, p in per.items()}
        if cle == "reel":
            out["reel"] = res
        else:
            out["melange"][cle] = res
        print(epic, cle, "fait")
    Path(sortie).write_text(json.dumps(out, ensure_ascii=False))


# --------------------------------------------------------------------------- bilan
def euros(a, capital, levier):
    """Capital x levier PARTAGÉ entre les marchés (mise par marché = capital x levier / nombre de marchés)."""
    return a["par_mois_pct"] / a["marches"] / 100 * capital * levier


def bilan(dossier, md, sortie_json):
    R = [json.loads(p.read_text()) for p in sorted(Path(dossier).glob("*.json"))]
    R = [r for r in R if r.get("reel")]
    cles = sorted(set(k for r in R for k in r["reel"]))

    def agg(groupe, cle, per, src="reel"):
        xs = []
        for r in groupe:
            blocs = [r[src].get(cle)] if src == "reel" else [m.get(cle) for m in r["melange"].values()]
            for b in blocs:
                if b and b.get(per):
                    xs.append(b[per])
        if not xs:
            return None
        n = sum(x["n"] for x in xs)
        return {"n": n, "marches": len(xs), "reussite": sum(x["reussite"] * x["n"] for x in xs) / n,
                "gain": sum(x["gain"] * x["n"] for x in xs) / n, "par_mois_pct": sum(x["par_mois_pct"] for x in xs),
                "par_mois_pondere_pct": sum(x["par_mois_pondere_pct"] for x in xs),
                "gagnants": sum(x["gain"] > 0 for x in xs), "pire_baisse_pct": max(x["pire_baisse_pct"] for x in xs),
                "mois_positifs": sum(x["mois_positifs"] for x in xs), "mois": sum(x["mois"] for x in xs)}

    orig = [r for r in R if r["origine"]]
    neuf = [r for r in R if not r["origine"]]
    lignes = []
    for k in cles:
        ch = agg(orig, k, "choix")
        if not ch:
            continue
        lignes.append({"cle": k, "choix": ch, "juge": agg(orig, k, "juge"), "nouveaux": agg(neuf, k, "tout"),
                       "melange": agg(orig + neuf, k, "tout", "melange")})
    # réglage CHOISI : meilleur gain cumulé par mois (fréquence x gain par trade) sur la période de choix
    # (8 marchés d'origine), >= 300 trades, gain par trade > 0, et prix mélangés <= 53 %
    # NB : avec un objectif plus proche que le stop, la réussite monte même au hasard (ex. stop 2 / objectif 1 ATR
    # ~ 67 %) : la règle anti-triche porte donc ici sur le GAIN des prix mélangés (il doit rester <= 0) et on montre
    # l'écart de réussite réel - mélangé.
    ok = [x for x in lignes if x["choix"]["n"] >= 300 and x["choix"]["gain"] > 0 and x["melange"] and x["melange"]["gain"] <= 0]
    ok.sort(key=lambda x: -x["choix"]["par_mois_pct"])
    choisi = ok[0] if ok else None
    base = next((x for x in lignes if x["cle"] == "0.05|tenir 1 x 4 h"), None)
    f = lambda a: "—" if not a else f"{100 * a['reussite']:.1f} % · {a['gain']:+.3f} % · {a['n']} trades · {a['gagnants']}/{a['marches']} marchés · {a['par_mois_pct']:+.2f} %/mois"  # noqa: E731
    L_ = ["# Labo n°5 « gros gains » : sorties, seuils, taille, plus de marchés (vote 4 h confirmé)", "",
          f"{len(orig)} marchés d'origine, {len(neuf)} marchés nouveaux. Frais de nuit Capital.com COMPTÉS. "
          f"Réglage choisi sur {CHOIX[0].date()} -> {CHOIX[1].date()} (8 marchés d'origine), puis jugé ailleurs.",
          f"Essais comptés : {len(lignes)} réglages x {len(R)} marchés x (réel + {len(GRAINES)} mélangés).", "",
          "Lecture : réussite · gain moyen par trade après spread et frais de nuit · trades · marchés gagnants · "
          "gain cumulé par mois en % d'UNE mise (somme des marchés, une position à la fois par marché).", "",
          "| Réglage | Choix 2021-2024 (8 marchés) | Jugé 2024-2026 (8 marchés) | Marchés NOUVEAUX 2021-2026 | Prix mélangés (réussite · gain) |",
          "|---|---|---|---|---|"]
    top = ok[:15]
    if base and base not in top:
        top = [base] + top
    for x in top:
        m = x["melange"]
        L_.append(f"| {x['cle']}{' (CHOISI)' if x is choisi else ''}{' (base actuelle)' if x is base else ''} | {f(x['choix'])} | {f(x['juge'])} | "
                  f"{f(x['nouveaux'])} | {100 * m['reussite']:.1f} % · {m['gain']:+.3f} % |")
    rejet = [x for x in lignes if x["melange"] and x["melange"]["gain"] > 0]
    L_ += ["", f"Réglages jetés (gagnants aussi sur prix mélangés) : {len(rejet)}. Réglages sans gain sur la période de choix : "
           f"{sum(1 for x in lignes if x['choix']['gain'] <= 0)} sur {len(lignes)}."]
    if choisi:
        L_ += ["", "## En euros (réglage choisi, jugé hors période de choix)", "",
               "Capital x levier partagé entre les marchés (ex. 100 € x 5 = 500 € répartis sur les marchés), une position "
               "à la fois par marché. Capital.com : jusqu'à 20x sur indices et or, 30x sur devises. Gain ET pire baisse "
               "sont multipliés par le levier.", "",
               "| Où | Levier | 100 € : par mois | 1 000 € : par mois | Pire baisse (en % de la mise, par marché) |", "|---|---|---|---|---|"]
        for nom, a in (("8 marchés, 2024-2026", choisi["juge"]), ("marchés nouveaux, 2021-2026", choisi["nouveaux"])):
            if not a:
                continue
            for lev in (1, 5, 10):
                L_.append(f"| {nom} | {lev}x | {euros(a, 100, lev):+.2f} € | {euros(a, 1000, lev):+.2f} € | "
                          f"{a['pire_baisse_pct'] * lev:.1f} % |")
    Path(md).write_text("\n".join(L_) + "\n")
    Path(sortie_json).write_text(json.dumps({"lignes": lignes, "choisi": choisi and choisi["cle"],
                                             "marches": [r["epic"] for r in R]}, ensure_ascii=False))
    print("\n".join(L_))


def telecharger(dossier, epics):
    from backtest import telecharger as t
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    t.DOSSIER = Path(dossier)
    Path(dossier).mkdir(parents=True, exist_ok=True)
    for e in epics:
        if (Path(dossier) / f"{e}_HOUR_4.csv").exists():
            print(e, "déjà là")
            continue
        try:
            (Path(dossier) / f"{e}_marche.json").write_text(json.dumps(api.marche(e), ensure_ascii=False))
            t.telecharger(api, e, "HOUR_4", 240, 3650)
        except Exception as x:
            print(e, "échec", str(x)[:200])
        api.deconnexion()
        time.sleep(1)
        api.connexion()
    api.deconnexion()


if __name__ == "__main__":
    a = sys.argv
    if a[1] == "telecharger":
        telecharger(a[2], a[3:])
    elif a[1] == "tester":
        tester(a[2], a[3], a[4])
    else:
        bilan(a[2], a[3], a[4])

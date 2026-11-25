"""Backtest des SORTIES de la Rapide 5 min sur l'or (25/11/2026).

Entrées : exactement celles du bot (EMA 9/50 dans le sens des tendances 1 h et 4 h, Bollinger qui
s'élargissent, ADX 5 min > 20), comme bot/amelioration.py (PR 31).
On compare plusieurs façons de SORTIR, toutes nettes de frais (spread bid/ask, prime du stop garanti,
frais de nuit) :
  - base     : sortie actuelle (croisement inverse / désaccord de tendance, stop garanti 1 %, suiveur 2 %)
  - be X     : dès que le gain a atteint X R, on sort si une bougie 5 min CLÔTURE au prix d'entrée
  - suiv G/T : dès que le gain a atteint G R, on sort si une bougie CLÔTURE à plus de T R du meilleur prix
  - tp X     : la moitié de la position est fermée à +X R (l'autre suit la sortie de base)
(1 R = la distance du stop = 1 % du prix.) Ces sorties « par clôture » sont gérées par le bot à chaque tour
(toutes les 5 min) : il ferme au prix du marché à l'ouverture de la bougie suivante, comme ici.

Usage : python backtest/sortie_rapide.py [dossier des données]  (GOLD_MINUTE_5.csv(.gz), GOLD_HOUR..., GOLD_HOUR_4...)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.strategie import adx, ema, milieu  # noqa: E402

DOSSIER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "donnees"


def lire(unite):
    for nom in (f"GOLD_{unite}.csv", f"GOLD_{unite}.csv.gz"):
        if (DOSSIER / nom).exists():
            df = pd.read_csv(DOSSIER / nom, parse_dates=["date"]).set_index("date").sort_index()
            df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
            return df[~df.index.duplicated()]
    raise FileNotFoundError(unite)


def alignee(df_sup, r, l, duree, quand):
    m = milieu(df_sup)
    a, b = ema(m.close, r), ema(m.close, l)
    s = pd.Series(np.where(a > b, 1, np.where(a < b, -1, 0)), index=m.index + duree)
    s[b.isna().values] = 0
    return s.reindex(quand, method="ffill").fillna(0).astype(int).values


def cibles(df5, df1h, df4h, adx_min=20.0):
    m = milieu(df5)
    fin = df5.index + pd.Timedelta(minutes=5)
    s5 = np.sign((ema(m.close, 9) - ema(m.close, 50)).fillna(0).values).astype(int)
    t1 = alignee(df1h, 50, 200, pd.Timedelta(hours=1), fin)
    t4 = alignee(df4h, 20, 200, pd.Timedelta(hours=4), fin)
    voulu = np.where((s5 == t1) & (s5 == t4), s5, 0)
    larg = 4 * m.close.rolling(20).std() / m.close.rolling(20).mean()
    bb = (larg / larg.rolling(100).median()).values
    force = adx(m).values
    ok_entree = (bb > 1) & (force > adx_min)
    return voulu, ok_entree


def simuler(df, voulu, ok_entree, cond, be=None, suiv=None, tp=None, verrou=None, suivi_pct=2.0, stop_pct=1.0):
    """Une position à la fois, en R (1 R = distance du stop). Renvoie la liste des trades (date, R net)."""
    ob, oa, hb, ha, lb, la, cb, ca = (df[c].values for c in
                                      ("open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask", "close_bid", "close_ask"))
    dates = df.index
    trades = []
    pos = 0
    for i in range(1, len(df)):
        # 1) ouverture de la bougie : sortie sur signal / sortie protégée décidée à la clôture précédente
        if pos:
            if voulu[i - 1] != pos or sortir:
                px = ob[i] if pos > 0 else oa[i]
                pnl += (px - entree) * pos * reste
                trades.append((d_entree, pnl / risque - frais / risque, "signal" if not sortir else sortir))
                pos = 0
        if not pos and voulu[i - 1] and ok_entree[i - 1]:
            pos = int(voulu[i - 1])
            entree = oa[i] if pos > 0 else ob[i]
            dist = entree * stop_pct / 100
            risque = dist  # par unité de taille
            stop = entree - dist * pos
            meilleur = entree
            reste, pnl, frais = 1.0, 0.0, 0.0
            tp_fait = False
            sortir = None
            d_entree = dates[i]
        if not pos:
            continue
        # 2) pendant la bougie : stop garanti, puis objectif partiel
        touche = (lb[i] <= stop) if pos > 0 else (ha[i] >= stop)
        if touche:
            pnl += (stop - entree) * pos * reste
            frais += stop * cond["prime_pct"] / 100 * reste
            trades.append((d_entree, pnl / risque - frais / risque, "stop"))
            pos = 0
            continue
        if tp and not tp_fait:
            niveau = entree + tp * dist * pos
            if (hb[i] >= niveau) if pos > 0 else (la[i] <= niveau):
                pnl += (niveau - entree) * pos * 0.5
                reste, tp_fait = 0.5, True
        # 3) clôture : frais de nuit, meilleur prix, suiveur garanti (2 %), sorties protégées
        mid = (cb[i] + ca[i]) / 2
        if dates[i].hour == 22 and dates[i].minute == 0:
            frais += mid * (cond["nuit_achat"] if pos > 0 else cond["nuit_vente"]) / 100 * reste
        haut = (hb[i] + ha[i]) / 2 if pos > 0 else (lb[i] + la[i]) / 2
        meilleur = max(meilleur, haut) if pos > 0 else min(meilleur, haut)
        if suivi_pct > 0:
            e = mid * max(suivi_pct, stop_pct) / 100
            stop = max(stop, mid - e) if pos > 0 else min(stop, mid + e)
        gain_max = (meilleur - entree) * pos / dist
        if verrou is not None:
            # stop GARANTI déplacé (touché pendant la bougie) : à `niveau` R dès que le gain a atteint `seuil` R,
            # seulement s'il reste au moins 0,25 % du prix (minimum Capital.com pour l'or)
            for seuil, niveau in verrou:
                if gain_max >= seuil:
                    cible = entree + niveau * dist * pos
                    if abs(mid - cible) >= mid * 0.0025 and (cible - mid) * pos < 0:
                        stop = max(stop, cible) if pos > 0 else min(stop, cible)
        sortie_px = cb[i] if pos > 0 else ca[i]
        gain_now = (sortie_px - entree) * pos / dist
        if be is not None and gain_max >= be and gain_now <= 0:
            sortir = "point d'entrée"
        if suiv is not None:
            g, t = suiv
            if gain_max >= g and (meilleur - mid) * pos / dist >= t:
                sortir = "suiveur serré"
    return pd.DataFrame(trades, columns=["date", "R", "raison"])


def resumer(t, milieu_):
    r = t.R.values
    c = np.concatenate([[0], np.cumsum(r)])
    g, p = r[r > 0].sum(), -r[r <= 0].sum()
    return {"R": round(r.sum(), 2), "R_1": round(t.R[t.date < milieu_].sum(), 2), "R_2": round(t.R[t.date >= milieu_].sum(), 2),
            "trades": len(r), "reussite": round((r > 0).mean() * 100, 1) if len(r) else 0,
            "pf": round(g / p, 2) if p else None, "pire_baisse_R": round((c - np.maximum.accumulate(c)).min(), 2)}


def principal():
    df5, df1h, df4h = lire("MINUTE_5"), lire("HOUR"), lire("HOUR_4")
    marche = json.loads((DOSSIER / "GOLD_marche.json").read_text()) if (DOSSIER / "GOLD_marche.json").exists() else {}
    inst = marche.get("instrument", {})
    regles = marche.get("dealingRules", {})
    # Frais de nuit Capital.com : overnightFee.longRate / shortRate en % par jour (signe négatif = coût)
    nuit = inst.get("overnightFee", {})
    # (prime du stop garanti : 0, comme bot/amelioration.py ; elle ne changerait que les rares sorties au stop)
    cond = {"nuit_achat": -float(nuit.get("longRate", -0.02)), "nuit_vente": -float(nuit.get("shortRate", -0.02)),
            "prime_pct": 0.0}
    print("Règles :", json.dumps(regles.get("minGuaranteedStopDistance", {})), "nuit :", nuit)
    print(f"Données 5 min : {df5.index[0]} -> {df5.index[-1]} ({len(df5)} bougies)")
    voulu, ok = cibles(df5, df1h, df4h)
    debut = df5.index[0] + pd.Timedelta(days=3)  # laisse les moyennes se former
    milieu_ = debut + (df5.index[-1] - debut) / 2
    variantes = {"base (actuelle)": {}}
    for x in (0.5, 1.0, 1.5):
        variantes[f"point d'entrée après +{x:g} R"] = {"be": x}
    for g in (1.0, 1.5, 2.0):
        for tt in (0.5, 0.75, 1.0):
            variantes[f"suiveur {tt:g} R après +{g:g} R"] = {"suiv": (g, tt)}
    for x in (1.0, 1.5, 2.0, 3.0):
        variantes[f"moitié à +{x:g} R"] = {"tp": x}
    for x in (1.5, 2.0):
        variantes[f"moitié à +{x:g} R + point d'entrée après +1 R"] = {"tp": x, "be": 1.0}
        variantes[f"moitié à +{x:g} R + suiveur 1 R après +1,5 R"] = {"tp": x, "suiv": (1.5, 1.0)}
    for x in (0.5, 0.75, 1.0, 1.5):
        variantes[f"stop garanti au point d'entrée après +{x:g} R"] = {"verrou": [(x, 0.0)]}
    for g, n in ((1.5, 0.5), (2.0, 1.0), (3.0, 2.0)):
        variantes[f"stop garanti à +{n:g} R après +{g:g} R"] = {"verrou": [(g, n)]}
    variantes["paliers : 0 R après +1 R, +1 R après +2 R, +2 R après +3 R"] = {"verrou": [(1, 0), (2, 1), (3, 2)]}
    variantes["point d'entrée +1 R + suiveur 1 R après +2 R"] = {"be": 1.0, "suiv": (2.0, 1.0)}
    variantes["point d'entrée +1 R + suiveur 0,75 R après +1,5 R"] = {"be": 1.0, "suiv": (1.5, 0.75)}
    res = {}
    for nom, kw in variantes.items():
        t = simuler(df5, voulu, ok, cond, **kw)
        t = t[t.date >= debut]
        res[nom] = resumer(t, milieu_)
        res[nom]["raisons"] = t.raison.value_counts().to_dict()
    base = res["base (actuelle)"]
    print(f"Période : {debut:%d/%m/%Y} -> {df5.index[-1]:%d/%m/%Y}, moitié au {milieu_:%d/%m/%Y}")
    print(f"{'variante':52s} {'R':>7s} {'R_1':>7s} {'R_2':>7s} {'trades':>6s} {'réuss.':>6s} {'PF':>5s} {'baisse':>7s}")
    for nom, s in res.items():
        mieux = "  <- mieux sur les 2 moitiés" if nom != "base (actuelle)" and s["R_1"] > base["R_1"] and s["R_2"] > base["R_2"] else ""
        print(f"{nom:52s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['reussite']:6.1f} "
              f"{s['pf'] or 0:5.2f} {s['pire_baisse_R']:7.2f}{mieux}")
    (Path(__file__).resolve().parent / "resultats_sortie_rapide.json").write_text(
        json.dumps({"periode": [str(debut), str(df5.index[-1])], "resultats": res}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    principal()

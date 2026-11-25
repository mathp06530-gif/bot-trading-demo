"""Rapide 5 min (or) : test des 3 défauts vus en démo le 25/11/2026 (demande de Mathis).

  1. suiveur trop loin : stop suiveur à 2 / 1,5 / 1,25 / 1 % du prix (le stop de départ reste 1 %) ;
  2. empilement en fin de mouvement : 1, 2 ou 3 positions par marché (une de plus quand le prix a avancé de 1 R) ;
  3. petites pertes quand la tendance hésite : ADX minimum 25 ou 30 (au lieu de 20), ou signal confirmé
     sur 2-3 bougies 5 min avant d'entrer, ou croisement inverse confirmé sur 2-3 bougies avant de sortir.
Toutes les versions gardent les sorties actuelles : prix d'entrée après +0,5 R, garde 60 % du gain après +1,5 R.
Net de spread et de frais de nuit. Résultats en R (1 R = 1 % du capital = ~1 € sur 100 €), chaque position compte 1 R.

Usage : python backtest/rapide_defauts.py [dossier]  (GOLD_MINUTE_5.csv, GOLD_HOUR.csv, GOLD_HOUR_4.csv, GOLD_marche.json)
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.serrage import conditions, lire  # noqa: E402
from bot.strategie import adx, ema, milieu  # noqa: E402
from backtest.sortie_rapide import alignee  # noqa: E402


def preparer(df5, df1h, df4h):
    m = milieu(df5)
    fin = df5.index + pd.Timedelta(minutes=5)
    s5 = np.sign((ema(m.close, 9) - ema(m.close, 50)).fillna(0).values).astype(int)
    t1 = alignee(df1h, 50, 200, pd.Timedelta(hours=1), fin)
    t4 = alignee(df4h, 20, 200, pd.Timedelta(hours=4), fin)
    voulu = np.where((s5 == t1) & (s5 == t4), s5, 0)
    larg = 4 * m.close.rolling(20).std() / m.close.rolling(20).mean()
    bb = (larg / larg.rolling(100).median()).values
    return voulu, bb, adx(m).values


def stable(voulu, k):
    """voulu[i] seulement s'il est le même sur les k dernières bougies, sinon 0."""
    if k <= 1:
        return voulu
    out = voulu.copy()
    for j in range(1, k):
        dec = np.r_[np.zeros(j, dtype=int), voulu[:-j]]
        out = np.where(dec == voulu, out, 0)
    return out


def simuler(df, voulu, ok, cond, suivi_pct=2.0, empiler=3, sortie_k=1, be=0.5, garde=(1.5, 0.6), stop_pct=1.0):
    ob, oa, hb, ha, lb, la, cb, ca = (df[c].values for c in
                                      ("open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask", "close_bid", "close_ask"))
    dates = df.index
    heures, minutes = dates.hour.values, dates.minute.values
    trades, pos, sens, contre = [], [], 0, 0
    for i in range(1, len(df)):
        # croisement inverse (confirmé sur sortie_k bougies) : tout fermer à l'ouverture
        if pos:
            contre = contre + 1 if voulu[i - 1] != sens else 0
            px = ob[i] if sens > 0 else oa[i]
            garder = []
            for p in pos:
                if contre >= sortie_k or p["sortir"]:
                    trades.append((p["d"], ((px - p["e"]) * sens - p["f"]) / p["dist"], "point d'entrée" if p["sortir"] else "signal"))
                else:
                    garder.append(p)
            pos = garder
            if not pos:
                sens, contre = 0, 0
        v = voulu[i - 1]
        if v and ok[i - 1] and (not pos or (v == sens and len(pos) < empiler)):
            prix = oa[i] if v > 0 else ob[i]
            dist = prix * stop_pct / 100
            dernier = max(p["e"] for p in pos) if pos and v > 0 else (min(p["e"] for p in pos) if pos else None)
            if dernier is None or (prix - dernier) * v >= dist:
                sens = v
                pos.append({"e": prix, "dist": dist, "stop": prix - dist * v, "m": prix, "f": 0.0, "d": dates[i], "sortir": False})
        if not pos:
            continue
        mid = (cb[i] + ca[i]) / 2
        haut = (hb[i] + ha[i]) / 2 if sens > 0 else (lb[i] + la[i]) / 2
        garder = []
        for p in pos:
            if (lb[i] <= p["stop"]) if sens > 0 else (ha[i] >= p["stop"]):
                trades.append((p["d"], ((p["stop"] - p["e"]) * sens - p["f"]) / p["dist"], "stop"))
                continue
            if heures[i] == 22 and minutes[i] == 0:
                p["f"] += mid * (cond["nuit_achat"] if sens > 0 else cond["nuit_vente"]) / 100
            e = mid * max(suivi_pct, stop_pct) / 100
            p["stop"] = max(p["stop"], mid - e) if sens > 0 else min(p["stop"], mid + e)
            p["m"] = max(p["m"], haut) if sens > 0 else min(p["m"], haut)
            gain = (p["m"] - p["e"]) * sens / p["dist"]
            if garde and gain >= garde[0]:
                c = p["e"] + garde[1] * (p["m"] - p["e"])
                lim = mid - mid * cond["min_pct"] / 100 * sens
                c = min(c, lim) if sens > 0 else max(c, lim)
                p["stop"] = max(p["stop"], c) if sens > 0 else min(p["stop"], c)
            if be and gain >= be and ((cb[i] if sens > 0 else ca[i]) - p["e"]) * sens <= 0:
                p["sortir"] = True
            garder.append(p)
        pos = garder
        if not pos:
            sens, contre = 0, 0
    return pd.DataFrame(trades, columns=["date", "R", "raison"])


def resumer(t, debut, milieu_):
    t = t[t.date >= debut].sort_values("date")
    r = t.R.values
    c = np.concatenate([[0], np.cumsum(r)])
    return {"R": round(float(r.sum()), 2), "R_1": round(float(t.R[t.date < milieu_].sum()), 2),
            "R_2": round(float(t.R[t.date >= milieu_].sum()), 2), "trades": int(len(r)),
            "reussite": round(float((r > 0).mean() * 100), 1) if len(r) else 0.0,
            "pire_baisse_R": round(float((c - np.maximum.accumulate(c)).min()), 2),
            "pertes_signal": int(((t.raison == "signal") & (t.R < 0)).sum())}


def principal():
    df5 = lire("GOLD", "MINUTE_5")
    voulu, bb, force = preparer(df5, lire("GOLD", "HOUR"), lire("GOLD", "HOUR_4"))
    cond = conditions("GOLD", float(df5.close_bid.iloc[-1]))
    cond["min_pct"] = min(cond["min_pct"], 1.0)
    debut = df5.index[0] + pd.Timedelta(days=3)
    milieu_ = debut + (df5.index[-1] - debut) / 2
    filtres = {"actuel (ADX 20)": dict(adx=20, k=1, sk=1), "ADX 25": dict(adx=25, k=1, sk=1),
               "ADX 30": dict(adx=30, k=1, sk=1), "entrée confirmée 2 bougies": dict(adx=20, k=2, sk=1),
               "entrée confirmée 3 bougies": dict(adx=20, k=3, sk=1), "sortie confirmée 2 bougies": dict(adx=20, k=1, sk=2),
               "sortie confirmée 3 bougies": dict(adx=20, k=1, sk=3)}
    res = {}
    for (nf, f), suivi, emp in itertools.product(filtres.items(), (2.0, 1.5, 1.25, 1.0), (3, 2, 1)):
        v_entree = stable(voulu, f["k"])
        ok = (bb > 1) & (force > f["adx"]) & (v_entree != 0)
        t = simuler(df5, voulu, ok, cond, suivi_pct=suivi, empiler=emp, sortie_k=f["sk"])
        res[f"{nf} | suiveur {suivi:g} % | {emp} pos."] = resumer(t, debut, milieu_)
    base = res["actuel (ADX 20) | suiveur 2 % | 3 pos."]
    print(f"Or 5 min : {debut:%d/%m/%Y} -> {df5.index[-1]:%d/%m/%Y} (moitié au {milieu_:%d/%m/%Y})")
    print(f"{'version':58s} {'R':>7s} {'R_1':>7s} {'R_2':>7s} {'trades':>6s} {'réuss.':>6s} {'baisse':>7s} {'p.sig':>5s}")
    for nom, s in sorted(res.items(), key=lambda kv: -kv[1]["R"]):
        mieux = s["R_1"] > base["R_1"] and s["R_2"] > base["R_2"]
        print(f"{nom:58s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['reussite']:6.1f} "
              f"{s['pire_baisse_R']:7.2f} {s['pertes_signal']:5d}{'  <- 2 moitiés' if mieux and nom != 'actuel (ADX 20) | suiveur 2 % | 3 pos.' else ''}")
    (Path(__file__).resolve().parent / "resultats_rapide_defauts.json").write_text(
        json.dumps({"periode": [str(debut), str(df5.index[-1])], "resultats": res}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    principal()

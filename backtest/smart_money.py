"""Backtest des idées « SMART MONEY » (gros acteurs), demande de Mathis du 25/11/2026 :
« il doit forcément y avoir un moyen, même peu sûr, qu'on peut tester ».

Idées testées (rien du futur : chaque décision n'utilise que des bougies terminées), nettes de frais
(spread bid/ask, frais de nuit, prime du stop garanti), sur 2 ans, or, argent et Bitcoin, en 1 h et en 4 h :

  1. CHASSE AUX STOPS (« liquidity sweep ») : la bougie dépasse le plus haut des N dernières bougies (là où
     dorment les stops des vendeurs) mais se referme EN DESSOUS : les gros acteurs ont pris la liquidité
     puis vendu -> VENTE. L'inverse sous le plus bas -> ACHAT. Stop au-delà de la mèche (+0,1 ATR),
     objectif K R, sortie forcée après H bougies.
  2. FAIR VALUE GAP (« trou » laissé par un gros ordre) : 3 bougies où le bas de la 3e est au-dessus du haut
     de la 1re (achat agressif). Si le prix revient dans le trou dans les 10 bougies -> ACHAT (vente pour
     l'inverse). Stop sous le bas du trou (+0,1 ATR), objectif K R, sortie après H bougies.
  3. ÉCART D'OUVERTURE DU LUNDI (or, argent) : si le marché rouvre à plus de 0,3 % de la clôture du vendredi,
     on parie que l'écart se referme. Stop = 1 écart, objectif = clôture du vendredi.
  Avec ou sans filtre EMA 200 (seulement dans le sens de la tendance de fond).

Une idée est « prometteuse » si elle gagne sur les DEUX moitiés des 2 ans, avec au moins 30 trades.

Usage : python backtest/smart_money.py [dossier]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402

if len(sys.argv) > 1:
    serrage.DOSSIER = Path(sys.argv[1])


def base(df):
    h = ((df.high_bid + df.high_ask) / 2).values
    l = ((df.low_bid + df.low_ask) / 2).values
    c = ((df.close_bid + df.close_ask) / 2).values
    o = ((df.open_bid + df.open_ask) / 2).values
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    ema200 = pd.Series(c).ewm(span=200, adjust=False).mean().values
    return o, h, l, c, atr, ema200


def tenir(sig, dist, n, duree):
    """Transforme des signaux ponctuels en (voulu, ok, dstop) : on garde la direction pendant `duree` bougies."""
    voulu = np.zeros(n, dtype=int)
    ok = np.zeros(n, dtype=bool)
    dstop = np.full(n, np.nan)
    i = 0
    while i < n:
        if sig[i]:
            fin = min(n, i + duree)
            voulu[i:fin] = sig[i]
            ok[i] = True
            dstop[i:fin] = dist[i]
            i = fin
        else:
            i += 1
    return voulu, ok, dstop


def chasse(df, n_haut, tendance):
    o, h, l, c, atr, e = base(df)
    hh = pd.Series(h).shift(1).rolling(n_haut).max().values
    ll = pd.Series(l).shift(1).rolling(n_haut).min().values
    vente = (h > hh) & (c < hh)
    achat = (l < ll) & (c > ll)
    if tendance:
        vente &= c < e
        achat &= c > e
    sig = np.where(vente, -1, np.where(achat, 1, 0))
    dist = np.where(sig == -1, h - c, c - l) + 0.1 * atr
    return sig, dist


def fvg(df, tendance):
    o, h, l, c, atr, e = base(df)
    n = len(df)
    sig = np.zeros(n, dtype=int)
    dist = np.full(n, np.nan)
    trous = []  # (sens, haut, bas, expire)
    for i in range(2, n):
        if l[i] > h[i - 2]:
            trous.append((1, l[i], h[i - 2], i + 10))
        if h[i] < l[i - 2]:
            trous.append((-1, l[i - 2], h[i], i + 10))
        trous = [t for t in trous if t[3] > i]
        for t in list(trous):
            s, haut, bas, _ = t
            if (s == 1 and l[i] <= haut and c[i] > bas) or (s == -1 and h[i] >= bas and c[i] < haut):
                if tendance and ((s == 1 and c[i] < e[i]) or (s == -1 and c[i] > e[i])):
                    trous.remove(t)
                    continue
                sig[i] = s
                dist[i] = (c[i] - bas if s == 1 else haut - c[i]) + 0.1 * atr[i]
                trous.remove(t)
                break
    return sig, dist


def ecart_lundi(df, seuil=0.3):
    o, h, l, c, atr, e = base(df)
    n = len(df)
    sig = np.zeros(n, dtype=int)
    dist = np.full(n, np.nan)
    obj = np.full(n, np.nan)
    trou = np.r_[False, (df.index[1:] - df.index[:-1]) > pd.Timedelta(hours=24)]
    for i in range(1, n):
        if trou[i]:
            ecart = (o[i] - c[i - 1]) / c[i - 1] * 100
            if abs(ecart) >= seuil:
                # décision prise à l'OUVERTURE de la bougie i (le prix est connu) : on la place sur i-1
                sig[i - 1] = -1 if ecart > 0 else 1
                dist[i - 1] = abs(o[i] - c[i - 1])
                obj[i - 1] = abs(o[i] - c[i - 1])
    return sig, dist, obj


def evaluer(jeux, ans=2.0):
    fin = max(j[1].index[-1] for j in jeux)
    debut = max(fin - pd.Timedelta(days=365 * ans), max(j[1].index[0] for j in jeux) + pd.Timedelta(days=30))
    milieu_ = debut + (fin - debut) / 2
    tous = []
    for (e, df, voulu, ok, dstop, dobj, cond) in jeux:
        tous.append(serrage.simuler(df, voulu, ok, dstop, None, cond, dobj=dobj))
    return serrage.resumer(pd.concat(tous, ignore_index=True), debut, milieu_)


def principal():
    marches = ("GOLD", "SILVER", "BTCUSD")
    donnees = {(e, u): serrage.lire(e, u) for e in marches for u in ("HOUR", "HOUR_4")}
    cond = {e: serrage.conditions(e, float(donnees[(e, "HOUR")].close_bid.iloc[-1])) for e in marches}
    res = {}
    for u in ("HOUR", "HOUR_4"):
        for e_set, titre_m in ((("GOLD", "SILVER"), "or+argent"), (("BTCUSD",), "BTC")):
            for tendance in (False, True):
                t = " + EMA 200" if tendance else ""
                for n_haut in (10, 20, 50):
                    for k in (1.5, 2.0, 3.0):
                        for duree in (10, 30):
                            jeux = []
                            for e in e_set:
                                df = donnees[(e, u)]
                                sig, dist = chasse(df, n_haut, tendance)
                                v, ok, ds = tenir(sig, dist, len(df), duree)
                                jeux.append((e, df, v, ok, ds, ds * k, cond[e]))
                            res[f"chasse {n_haut} {u} {titre_m}{t}, obj {k:g} R, max {duree}"] = evaluer(jeux)
                for k in (1.5, 2.0, 3.0):
                    jeux = []
                    for e in e_set:
                        df = donnees[(e, u)]
                        sig, dist = fvg(df, tendance)
                        v, ok, ds = tenir(sig, dist, len(df), 20)
                        jeux.append((e, df, v, ok, ds, ds * k, cond[e]))
                    res[f"FVG {u} {titre_m}{t}, obj {k:g} R"] = evaluer(jeux)
    for seuil in (0.2, 0.3, 0.5):
        jeux = []
        for e in ("GOLD", "SILVER"):
            df = donnees[(e, "HOUR")]
            sig, dist, obj = ecart_lundi(df, seuil)
            v, ok, ds = tenir(sig, dist, len(df), 24)
            ob = pd.Series(np.where(sig != 0, obj, np.nan)).ffill().values
            jeux.append((e, df, v, ok, ds, ob, cond[e]))
        res[f"écart du lundi > {seuil:g} % or+argent"] = evaluer(jeux)

    print(f"{'idée':58s} {'R':>7s} {'an 1':>7s} {'an 2':>7s} {'trades':>6s} {'réuss.':>6s} {'baisse':>7s}")
    prometteuses = []
    for nom, s in sorted(res.items(), key=lambda kv: -kv[1]["R"]):
        ok = s["R_1"] > 0 and s["R_2"] > 0 and s["trades"] >= 30
        if ok:
            prometteuses.append(nom)
        print(f"{nom:58s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['reussite']:6.1f} "
              f"{s['pire_baisse_R']:7.2f}{'  <- 2 moitiés +' if ok else ''}")
    print(f"\n{len(prometteuses)} idées gagnantes sur les 2 moitiés, sur {len(res)} testées.")
    (Path(__file__).resolve().parent / "resultats_smart_money.json").write_text(
        json.dumps({"prometteuses": prometteuses, "resultats": res}, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

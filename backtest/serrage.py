"""Backtest du STOP QUI SE RESSERRE APRÈS UN GAIN (demande de Mathis, 25/11/2026).

Idée : garder un stop large au début (le prix fait des allers-retours), puis, une fois que le gain a
atteint un SEUIL (en R, 1 R = distance du stop de départ), suivre le prix de beaucoup plus près pour
encaisser davantage en fin de mouvement. Le stop GARANTI est déplacé (touché pendant la bougie).

Deux façons de « suivre de près » :
  - suiveur T R après +G R : le stop est mis à T R derrière le meilleur prix atteint ;
  - garder K % après +G R  : le stop est mis pour garder K % du meilleur gain atteint.
Le stop ne recule jamais et respecte la distance minimale du stop garanti de Capital.com.

Testé sur les 3 stratégies actives, avec leurs entrées et sorties actuelles, nettes de frais
(spread bid/ask, frais de nuit, prime du stop garanti 0,1 %) :
  - Cassure 4 h or + argent (2 ans), Tendance 4 h BTC (2 ans, deux moitiés dont une avec TP 1 ATR),
  - Rapide 5 min or (~6 mois, avec la sortie au prix d'entrée après +0,5 R déjà en place).
Une variante n'est « meilleure » que si elle fait plus de R sur les DEUX moitiés de la période et que
la pire baisse ne s'aggrave pas de plus de 1 R (mêmes règles que l'auto-amélioration du dimanche).

Usage : python backtest/serrage.py [dossier]  (CSV de backtest/telecharger.py : <EPIC>_<UNITE>.csv + <EPIC>_marche.json)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.cassure import signaux_cassure  # noqa: E402
from bot.strategie import signaux_tendance  # noqa: E402

DOSSIER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "donnees"
PRIME_PCT = 0.1


def lire(epic, unite):
    df = pd.read_csv(DOSSIER / f"{epic}_{unite}.csv", parse_dates=["date"]).set_index("date").sort_index()
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    return df[~df.index.duplicated()]


def conditions(epic, prix):
    p = DOSSIER / f"{epic}_marche.json"
    m = json.loads(p.read_text()) if p.exists() else {}
    inst, regles = m.get("instrument", {}), m.get("dealingRules", {})
    nuit = inst.get("overnightFee", {})
    g = regles.get("minGuaranteedStopDistance", {})
    if g.get("unit") == "PERCENTAGE":
        mini = float(g["value"])
    elif g.get("value"):
        mini = float(g["value"]) / prix * 100
    else:
        mini = 0.25
    return {"nuit_achat": -float(nuit.get("longRate", -0.02)), "nuit_vente": -float(nuit.get("shortRate", -0.02)),
            "min_pct": mini}


def simuler(df, voulu, ok, dstop, dsuivi, cond, regle=None, be=None, dobj=None):
    """Une position à la fois. voulu : sens à garder (1/-1/0) ; ok : entrée permise ; dstop/dsuivi/dobj :
    distances (prix) du stop de départ, du suiveur de base et de l'objectif. regle :
    ("suiveur", G, T) ou ("garde", G, K). Renvoie les trades (date, R net, raison)."""
    ob, oa, hb, ha, lb, la, cb, ca = (df[c].values for c in
                                      ("open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask", "close_bid", "close_ask"))
    dates = df.index
    heures, minutes = dates.hour.values, dates.minute.values
    trades, pos, sortir = [], 0, None
    for i in range(1, len(df)):
        if pos and (voulu[i - 1] != pos or sortir):
            px = ob[i] if pos > 0 else oa[i]
            trades.append((d_entree, ((px - entree) * pos - frais) / dist, sortir or "signal"))
            pos, sortir = 0, None
        if not pos and voulu[i - 1] and ok[i - 1] and dstop[i - 1] == dstop[i - 1]:
            pos = int(voulu[i - 1])
            entree = oa[i] if pos > 0 else ob[i]
            dist = max(dstop[i - 1], entree * cond["min_pct"] / 100)
            stop = entree - dist * pos
            obj = entree + dobj[i - 1] * pos if dobj is not None and dobj[i - 1] == dobj[i - 1] else None
            meilleur, frais, d_entree = entree, 0.0, dates[i]
        if not pos:
            continue
        if (lb[i] <= stop) if pos > 0 else (ha[i] >= stop):
            frais += abs(stop) * PRIME_PCT / 100
            trades.append((d_entree, ((stop - entree) * pos - frais) / dist, "stop"))
            pos = 0
            continue
        if obj is not None and ((hb[i] >= obj) if pos > 0 else (la[i] <= obj)):
            px = max(obj, ob[i]) if pos > 0 else min(obj, oa[i])
            trades.append((d_entree, ((px - entree) * pos - frais) / dist, "objectif"))
            pos = 0
            continue
        mid = (cb[i] + ca[i]) / 2
        if heures[i] == 22 and minutes[i] == 0:
            frais += mid * (cond["nuit_achat"] if pos > 0 else cond["nuit_vente"]) / 100
        if dsuivi is not None and dsuivi[i] == dsuivi[i]:
            stop = max(stop, mid - dsuivi[i]) if pos > 0 else min(stop, mid + dsuivi[i])
        haut = (hb[i] + ha[i]) / 2 if pos > 0 else (lb[i] + la[i]) / 2
        meilleur = max(meilleur, haut) if pos > 0 else min(meilleur, haut)
        gain_max = (meilleur - entree) * pos / dist
        if regle is not None and gain_max >= regle[1]:
            if regle[0] == "suiveur":
                cible = meilleur - regle[2] * dist * pos
            else:
                cible = entree + regle[2] * (meilleur - entree)
            limite = mid - mid * cond["min_pct"] / 100 * pos  # Capital.com : distance minimale du stop garanti
            cible = min(cible, limite) if pos > 0 else max(cible, limite)
            stop = max(stop, cible) if pos > 0 else min(stop, cible)
        if be is not None and gain_max >= be and ((cb[i] if pos > 0 else ca[i]) - entree) * pos <= 0:
            sortir = "point d'entrée"
    return pd.DataFrame(trades, columns=["date", "R", "raison"])


def resumer(t, debut, milieu_):
    t = t[t.date >= debut].sort_values("date")
    r = t.R.values
    c = np.concatenate([[0], np.cumsum(r)])
    return {"R": round(float(r.sum()), 2), "R_1": round(float(t.R[t.date < milieu_].sum()), 2),
            "R_2": round(float(t.R[t.date >= milieu_].sum()), 2), "trades": int(len(r)),
            "reussite": round(float((r > 0).mean() * 100), 1) if len(r) else 0.0,
            "pire_baisse_R": round(float((c - np.maximum.accumulate(c)).min()), 2),
            "raisons": t.raison.value_counts().to_dict()}


VARIANTES = {"actuelle": None}
for g in (1.0, 1.5, 2.0, 3.0):
    for t in (0.5, 0.75, 1.0, 1.5):
        VARIANTES[f"suiveur {t:g} R après +{g:g} R"] = ("suiveur", g, t)
    for k in (0.5, 0.6, 0.7, 0.8):
        VARIANTES[f"garder {int(k * 100)} % après +{g:g} R"] = ("garde", g, k)


def strat_cassure(epics):
    """Cassure 20/20 bougies 4 h, stop garanti 2 ATR, pas de suiveur (sortie sur le canal)."""
    jeux = []
    for e in epics:
        df = lire(e, "HOUR_4")
        sig = signaux_cassure(df, entree=20, sortie=20)
        c = sig.cible.values
        neuf = np.r_[True, c[1:] != c[:-1]]
        jeux.append((e, df, c, neuf, sig.stop.values, None, None, conditions(e, float(df.close_bid.iloc[-1]))))
    return jeux


def strat_cassure_5min(epics):
    """Vérification : mêmes signaux 4 h, mais stop suivi toutes les 5 min (comme le bot, qui tourne toutes les 5 min)."""
    jeux = []
    for e in epics:
        df4, df5 = lire(e, "HOUR_4"), lire(e, "MINUTE_5")
        sig = signaux_cassure(df4, entree=20, sortie=20)
        c = sig.cible.values
        neuf = np.r_[True, c[1:] != c[:-1]]
        fin4 = df4.index + pd.Timedelta(hours=4)  # le signal est connu à la fin de la bougie 4 h
        fin5 = df5.index + pd.Timedelta(minutes=5)
        pos = np.searchsorted(fin4.values, fin5.values, side="right") - 1  # dernière bougie 4 h terminée
        valide = pos >= 0
        p = np.where(valide, pos, 0)
        c5 = np.where(valide, c[p], 0)
        premier = np.r_[True, p[1:] != p[:-1]]  # 1re bougie 5 min après la clôture 4 h
        ok5 = valide & neuf[p] & premier
        st5 = np.where(valide, sig.stop.values[p], np.nan)
        jeux.append((e, df5, c5, ok5, st5, None, None, conditions(e, float(df5.close_bid.iloc[-1]))))
    return jeux


def strat_tendance(epics):
    """Tendance 4 h : deux moitiés (une avec TP 1 ATR), stop 2 ATR, suiveur 5 ATR, ADX > 20."""
    jeux = []
    for e in epics:
        df = lire(e, "HOUR_4")
        sig = signaux_tendance(df, adx_min=20, suivi_atr=5)
        c = sig.cible.values
        neuf = np.r_[True, c[1:] != c[:-1]]
        cond = conditions(e, float(df.close_bid.iloc[-1]))
        jeux.append((e + " (moitié TP 1 ATR)", df, c, neuf, sig.stop.values, sig.suivi.values, sig.atr.values * 1.0, cond))
        jeux.append((e + " (moitié sans TP)", df, c, neuf, sig.stop.values, sig.suivi.values, None, cond))
    return jeux


def strat_rapide():
    from backtest.sortie_rapide import cibles
    df5 = lire("GOLD", "MINUTE_5")
    voulu, ok = cibles(df5, lire("GOLD", "HOUR"), lire("GOLD", "HOUR_4"))
    m = (df5.close_bid + df5.close_ask).values / 2
    cond = conditions("GOLD", float(m[-1]))
    cond["min_pct"] = min(cond["min_pct"], 1.0)
    return [("GOLD 5 min", df5, voulu, ok, m * 0.01, m * 0.02, None, cond)]


def evaluer(jeux, poids, be=None, ans=2.0):
    fin = max(j[1].index[-1] for j in jeux)
    debut = fin - pd.Timedelta(days=365 * ans)
    debut = max(debut, max(j[1].index[0] for j in jeux) + pd.Timedelta(days=60 if ans > 1 else 3 if ans == 1 else 1))
    milieu_ = debut + (fin - debut) / 2
    res = {}
    for nom, regle in VARIANTES.items():
        tous = []
        for (e, df, c, ok, dstop, dsuivi, dobj, cond), w in zip(jeux, poids):
            t = simuler(df, c, ok, dstop, dsuivi, cond, regle=regle, be=be, dobj=dobj)
            t["R"] *= w
            tous.append(t)
        res[nom] = resumer(pd.concat(tous, ignore_index=True), debut, milieu_)
    return res, (debut, milieu_, fin)


def afficher(titre, res, periode):
    base = res["actuelle"]
    print(f"\n=== {titre} : {periode[0]:%d/%m/%Y} -> {periode[2]:%d/%m/%Y} (moitié au {periode[1]:%d/%m/%Y})")
    print(f"{'variante':32s} {'R':>7s} {'R_1':>7s} {'R_2':>7s} {'trades':>6s} {'réuss.':>6s} {'baisse':>7s}")
    gagnantes = []
    for nom, s in sorted(res.items(), key=lambda kv: -kv[1]["R"]):
        mieux = nom != "actuelle" and s["R_1"] > base["R_1"] and s["R_2"] > base["R_2"] \
            and s["pire_baisse_R"] >= base["pire_baisse_R"] - 1
        if mieux:
            gagnantes.append(nom)
        print(f"{nom:32s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['reussite']:6.1f} "
              f"{s['pire_baisse_R']:7.2f}{'  <- MIEUX (2 moitiés)' if mieux else ''}")
    return gagnantes


def principal():
    sortie = {}
    for titre, jeux, poids, be, ans in (
            ("Cassure 4 h or + argent", strat_cassure(["GOLD", "SILVER"]), [1, 1], None, 2.0),
            ("Tendance 4 h BTC", strat_tendance(["BTCUSD"]), [0.5, 0.5], None, 2.0),
            ("Rapide 5 min or", strat_rapide(), [1], 0.5, 1.0),
            ("Cassure 4 h or + argent, mêmes 6 mois (stop suivi toutes les 4 h)", strat_cassure(["GOLD", "SILVER"]), [1, 1], None, 0.5),
            ("Cassure or + argent, stop suivi toutes les 5 min (vérif. 6 mois)", strat_cassure_5min(["GOLD", "SILVER"]), [1, 1], None, 0.5)):
        res, periode = evaluer(jeux, poids, be=be, ans=ans)
        gagnantes = afficher(titre, res, periode)
        sortie[titre] = {"periode": [str(p) for p in periode], "meilleures": gagnantes, "resultats": res}
    (Path(__file__).resolve().parent / "resultats_serrage.json").write_text(
        json.dumps(sortie, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

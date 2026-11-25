"""Backtest des stratégies trouvées sur les RÉSEAUX (Reddit, X, YouTube, TikTok…), demande de Mathis du 25/11/2026.

Chaque idée est codée avec les réglages PUBLIÉS par sa source (pas d'optimisation), puis rejouée sur 2 ans de
bougies Capital.com démo (bid/ask), nette de frais (spread, frais de nuit, prime du stop garanti), avec le même
moteur que les autres backtests (backtest/serrage.py : une position à la fois par marché, résultats en R).

Idées testées :
  1. SUPERTREND 10 / 3 en 4 h (vidéos YouTube/TikTok, test hackernoon 2026 sur l'or : PF 1,97 hors swap).
     Toujours en position, on se retourne quand la ligne est franchie ; stop garanti sur la ligne.
  2. BITCOIN LA NUIT « MAX(10) » (Quantpedia 2024, relayé sur X) : à la clôture de New York (16 h, heure de NY),
     si le BTC est au plus haut de 10 jours, achat jusqu'à 10 h le lendemain (nuits ven->lun, lun->mar, mar->mer).
  3. BITCOIN RSI(5) > 70 en jour (r/algotrading, « best backtested bitcoin strategy ») : achat tant que RSI(5) > 70.
  4. TTM SQUEEZE 4 h (indicateur LazyBear, très partagé sur YouTube) : les bandes de Bollinger sortent du canal
     de Keltner après au moins 6 bougies serrées -> on suit le sens de l'élan ; stop 2 ATR, sortie quand l'élan
     change de signe ou après 20 bougies.
  5. OR, ACHAT PENDANT LA SÉANCE ASIATIQUE (blog MQL5 « 190 tests sur 10 ans ») : achat à 0 h UTC, vente à 7 h UTC.
  6. OR, TOURNANT DU MOIS (même blog) : achat à la clôture de l'avant-dernier jour ouvré, vente après le 3e jour.
  7. NR7 en 4 h (Toby Crabel, très partagé) : la bougie la plus étroite des 7 dernières ; si une clôture sort de
     son haut/bas dans les 6 bougies suivantes -> on suit ; stop de l'autre côté, objectif 2 R, 20 bougies max.
  9. OR LA NUIT (blog MQL5, « seule règle horaire qui survit à 49 000 variantes ») : achat à 18 h heure de NY,
     vente à 3 h NY, du lundi au jeudi soir.
  8. MACD + EMA 200 (vidéo virale « 86 % de réussite ») en 4 h, pour vérifier : croisement MACD sous/au-dessus de
     0 dans le sens de l'EMA 200, stop 1,5 ATR, objectif 1,5 R.

Comparaison avec les stratégies actuelles sur la même période (Cassure or/argent avec garde 50 % après 1,5 R,
Tendance BTC, Élan du bot), puis effet sur le PORTEFEUILLE (risques réels : Cassure 3 %, Tendance 3 %, Élan 1 %,
nouvelle stratégie 1 %). Une idée est « à garder » si elle gagne sur les DEUX moitiés avec au moins 30 trades et
si elle améliore le portefeuille sur les deux moitiés sans aggraver sa pire baisse de plus de 2 %.

Usage : python backtest/reseaux.py [dossier]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from backtest.smart_money import base, tenir  # noqa: E402

if len(sys.argv) > 1:
    serrage.DOSSIER = Path(sys.argv[1])

ANS = 2.0


# --------------------------------------------------------------------------- indicateurs
def rsi(c, n):
    d = np.diff(c, prepend=c[0])
    g = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    p = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + g / p.replace(0, np.nan))).fillna(50).values


def atr_jour(df):
    """ATR(14) des bougies JOUR (construites à partir des bougies horaires), connue seulement le lendemain."""
    m = pd.DataFrame({k: (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2 for k in ("open", "high", "low", "close")})
    j = m.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    pc = j.close.shift()
    tr = pd.concat([j.high - j.low, (j.high - pc).abs(), (j.low - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)  # pas de futur
    return a.reindex(df.index.floor("1D")).values


# --------------------------------------------------------------------------- idées
def supertrend(df, n=10, mult=3.0, filtre=False):
    o, h, l, c, atr, e = base(df)
    a = pd.Series(np.maximum(h - l, np.maximum(abs(h - np.r_[c[0], c[:-1]]), abs(l - np.r_[c[0], c[:-1]])))) \
        .rolling(n).mean().bfill().values  # ATR simple, comme TradingView (« changeATR » = vrai)
    hl2 = (h + l) / 2
    up, dn = hl2 - mult * a, hl2 + mult * a
    d = np.ones(len(c), dtype=int)
    for i in range(1, len(c)):
        if c[i - 1] > up[i - 1]:
            up[i] = max(up[i], up[i - 1])
        if c[i - 1] < dn[i - 1]:
            dn[i] = min(dn[i], dn[i - 1])
        d[i] = 1 if (d[i - 1] == -1 and c[i] > dn[i - 1]) else -1 if (d[i - 1] == 1 and c[i] < up[i - 1]) else d[i - 1]
    ligne = np.where(d == 1, up, dn)
    voulu = d.copy()
    if filtre:
        voulu = np.where((d == 1) & (c > e) | (d == -1) & (c < e), d, 0)
    ok = np.r_[True, voulu[1:] != voulu[:-1]]
    dstop = np.abs(c - ligne) + 0.1 * atr
    return voulu, ok, dstop, None


def btc_nuit(df, n_jours=10, toutes_nuits=False):
    """Clôture de NY = bougie horaire qui commence à 15 h heure de NY ; sortie à l'ouverture de la bougie de 10 h."""
    o, h, l, c, atr, e = base(df)
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    heure, jour = ny.hour.values, ny.dayofweek.values
    fin_seance = (heure == 15) & (jour <= 4)
    clotures = pd.Series(c[fin_seance], index=np.where(fin_seance)[0])
    plus_haut = clotures >= clotures.rolling(n_jours).max()
    aj = atr_jour(df)
    voulu = np.zeros(len(c), dtype=int)
    ok = np.zeros(len(c), dtype=bool)
    dstop = np.full(len(c), np.nan)
    nuits_ok = (4, 0, 1)  # vendredi, lundi, mardi soir
    for i, haut in plus_haut.items():
        if not haut or (not toutes_nuits and jour[i] not in nuits_ok):
            continue
        j = i + 1
        while j < len(c) and not (heure[j] == 10 and jour[j] <= 4):
            j += 1
        voulu[i:j] = 1  # la position est ouverte à la bougie i+1 (16 h) et fermée à l'ouverture de la bougie de 10 h
        ok[i] = True
        dstop[i:j] = 2 * aj[i] if aj[i] == aj[i] else np.nan
    return voulu, ok, dstop, None


def btc_rsi5(df):
    """Bougies JOUR (00 h UTC) : achat tant que RSI(5) > 70. Stop garanti 2 ATR jour."""
    m = pd.DataFrame({k: (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2 for k in ("high", "low", "close")})
    j = m.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    r = pd.Series(rsi(j.close.values, 5), index=j.index)
    # Valeur connue à la fin du jour -> appliquée à partir de la 1re bougie horaire du jour suivant
    cible = (r > 70).astype(int).shift(1).reindex(df.index.floor("1D")).fillna(0).astype(int).values
    # Décision prise à la fin de la dernière bougie horaire du jour : on la place sur cette bougie (simuler lit i-1)
    voulu = np.r_[cible[1:], cible[-1]]
    ok = np.ones(len(voulu), dtype=bool)
    aj = atr_jour(df)
    dstop = 2 * np.r_[aj[1:], aj[-1]]
    return voulu, ok, dstop, None


def squeeze(df, serre_min=6, duree=20):
    o, h, l, c, atr, e = base(df)
    s = pd.Series(c)
    moy, et = s.rolling(20).mean(), s.rolling(20).std()
    a20 = pd.Series(atr)  # ATR 14 (Wilder), proche du « range » de LazyBear
    serre = ((moy + 2 * et) < (moy + 1.5 * a20)) & ((moy - 2 * et) > (moy - 1.5 * a20))
    hh, ll = pd.Series(h).rolling(20).max(), pd.Series(l).rolling(20).min()
    x = s - ((hh + ll) / 2 + moy) / 2
    elan = x.rolling(20).apply(lambda v: np.polyfit(np.arange(20), v, 1)[1] + np.polyfit(np.arange(20), v, 1)[0] * 19,
                               raw=True).values
    nb_serre = serre.astype(int).groupby((~serre).cumsum()).cumsum().shift(1).fillna(0).values
    sortie = (~serre.values) & (nb_serre >= serre_min)
    sig = np.where(sortie & (elan > 0), 1, np.where(sortie & (elan < 0), -1, 0))
    v, ok, ds = tenir(sig, 2 * atr, len(c), duree)
    # sortie quand l'élan change de signe
    for i in range(1, len(v)):
        if v[i] and not ok[i] and np.sign(elan[i]) != v[i]:
            k = i
            while k < len(v) and v[k] == v[i] and not ok[k]:
                v[k] = 0
                k += 1
    return v, ok, ds, None


def or_asie(df, filtre=False):
    """Achat à l'ouverture de la bougie de 0 h UTC, vente à l'ouverture de celle de 7 h UTC (jours de semaine)."""
    o, h, l, c, atr, e = base(df)
    heure, jour = df.index.hour.values, df.index.dayofweek.values
    voulu = ((heure >= 23) | (heure < 6)).astype(int)  # décision lue sur la bougie précédente (simuler)
    voulu = np.where((heure == 23) & (jour == 4), 0, voulu)  # pas le week-end
    voulu = np.where((heure < 6) & (jour >= 5), 0, voulu)
    if filtre:
        f = pd.Series(np.where(heure == 23, c > e, np.nan)).ffill().fillna(0).astype(bool).values
        voulu = np.where(f, voulu, 0)
    ok = np.r_[True, voulu[1:] != voulu[:-1]]
    aj = atr_jour(df)
    return voulu, ok, 1.0 * aj, None


def or_nuit_ny(df):
    """Blog MQL5 (6/11/2026, « la seule règle horaire qui survit » sur 49 000 variantes) : achat de l'or à 18 h heure
    de New York, vente 9 h plus tard (3 h NY), du lundi soir au jeudi soir. Stop garanti 1 ATR jour."""
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    heure, jour = ny.hour.values, ny.dayofweek.values
    n = len(df)
    voulu = np.zeros(n, dtype=int)
    ok = np.zeros(n, dtype=bool)
    for i in range(n - 1):
        if heure[i + 1] == 18 and jour[i + 1] <= 3:  # décision sur la bougie de 17 h, entrée à l'ouverture de 18 h
            ok[i] = True
            j = i
            while j < n - 1 and (j == i or heure[j + 1] != 3):
                voulu[j] = 1
                j += 1
    return voulu, ok, atr_jour(df), None


def or_tournant_mois(df):
    """Achat à la clôture de l'avant-dernier jour ouvré du mois, vente à la clôture du 3e jour ouvré du mois suivant."""
    jours = pd.Series(df.index.floor("1D").unique())
    jours = jours[jours.dt.dayofweek < 5]
    mois = jours.dt.to_period("M")
    rang_fin = jours.groupby(mois).rank(ascending=False).values
    rang_deb = jours.groupby(mois).rank().values
    entrees = set(jours[rang_fin == 2])
    sorties = set(jours[rang_deb == 3])
    j_idx = df.index.floor("1D")
    voulu = np.zeros(len(df), dtype=int)
    ok = np.zeros(len(df), dtype=bool)
    aj = atr_jour(df)
    dstop = 2 * aj
    dedans = False
    jour_prec = None
    for i in range(len(df) - 1):
        nouveau_jour = j_idx[i + 1] != j_idx[i]
        if nouveau_jour and j_idx[i] in entrees:
            dedans, ok[i] = True, True
        elif nouveau_jour and j_idx[i] in sorties:
            dedans = False
        voulu[i] = int(dedans)
    return voulu, ok, dstop, None


def nr7(df):
    o, h, l, c, atr, e = base(df)
    r = h - l
    est_nr7 = r <= pd.Series(r).rolling(7).min().values
    sig = np.zeros(len(c), dtype=int)
    dist = np.full(len(c), np.nan)
    actif = None  # (haut, bas, expire)
    for i in range(len(c)):
        if actif and i <= actif[2]:
            if c[i] > actif[0]:
                sig[i], dist[i], actif = 1, c[i] - actif[1], None
            elif c[i] < actif[1]:
                sig[i], dist[i], actif = -1, actif[0] - c[i], None
        elif actif:
            actif = None
        if est_nr7[i]:
            actif = (h[i], l[i], i + 6)
    dist = dist + 0.1 * atr
    v, ok, ds = tenir(sig, dist, len(c), 20)
    return v, ok, ds, ds * 2


def macd_ema(df):
    o, h, l, c, atr, e = base(df)
    s = pd.Series(c)
    m = (s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean()).values
    sg = pd.Series(m).ewm(span=9, adjust=False).mean().values
    hausse = (m > sg) & (np.r_[m[0], m[:-1]] <= np.r_[sg[0], sg[:-1]]) & (m < 0) & (c > e)
    baisse = (m < sg) & (np.r_[m[0], m[:-1]] >= np.r_[sg[0], sg[:-1]]) & (m > 0) & (c < e)
    sig = np.where(hausse, 1, np.where(baisse, -1, 0))
    v, ok, ds = tenir(sig, 1.5 * atr, len(c), 30)
    return v, ok, ds, ds * 1.5


# --------------------------------------------------------------------------- évaluation
def periode(dfs):
    fin = max(d.index[-1] for d in dfs)
    debut = max(fin - pd.Timedelta(days=365 * ANS), max(d.index[0] for d in dfs) + pd.Timedelta(days=60))
    return debut, debut + (fin - debut) / 2, fin


def jouer(jeux, regle=None):
    """jeux : (epic, df, voulu, ok, dstop, dsuivi, dobj, poids). Renvoie tous les trades (date, R, raison, epic)."""
    tous = []
    for j in jeux:
        e, df, v, ok, ds, dsu, dob, w = j if len(j) == 8 else (*j[:5], None, j[5], j[6])
        cond = serrage.conditions(e, float(df.close_bid.iloc[-1]))
        t = serrage.simuler(df, v, ok, ds, dsu, cond, regle=regle, dobj=dob)
        t["R"] *= w
        t["epic"] = e
        tous.append(t)
    return pd.concat(tous, ignore_index=True)


def actuelles(d):
    from bot.cassure import signaux_cassure
    from bot.elan import signaux_elan
    from bot.strategie import signaux_tendance
    res = {}
    jeux = []
    for e in ("GOLD", "SILVER"):
        df = d[(e, "HOUR_4")]
        sig = signaux_cassure(df, entree=20, sortie=20)
        c = sig.cible.values
        jeux.append((e, df, c, np.r_[True, c[1:] != c[:-1]], sig.stop.values, None, None, 1.0))
    res["Cassure 4 h or+argent (actuelle)"] = jouer(jeux, regle=("garde", 1.5, 0.5))
    df = d[("BTCUSD", "HOUR_4")]
    sig = signaux_tendance(df, adx_min=20, suivi_atr=5)
    c = sig.cible.values
    neuf = np.r_[True, c[1:] != c[:-1]]
    res["Tendance 4 h BTC (actuelle, sans 2e cerveau)"] = jouer([
        ("BTCUSD", df, c, neuf, sig.stop.values, sig.suivi.values, sig.atr.values, 0.5),
        ("BTCUSD", df, c, neuf, sig.stop.values, sig.suivi.values, None, 0.5)])
    jeux = []
    for e in ("GOLD", "SILVER"):
        df = d[(e, "HOUR_4")]
        se = signaux_elan(df)
        cc = signaux_cassure(df, entree=20, sortie=20).cible.values
        s = np.where(cc == -se.sig.values, 0, se.sig.values)
        v, ok, ds = tenir(s, se.dist.values, len(df), 20)
        v = np.where(cc == -v, 0, v)
        jeux.append((e, df, v, ok, ds, None, ds * 2.0, 1.0))
    res["Élan 4 h or+argent (actuelle, expérimentale)"] = jouer(jeux)
    return res


def nouvelles(d):
    res = {}
    for marches, nom in ((("GOLD", "SILVER"), "or+argent"), (("BTCUSD",), "BTC")):
        for filtre in (False, True):
            jeux = [(e, d[(e, "HOUR_4")], *supertrend(d[(e, "HOUR_4")], filtre=filtre), 1.0) for e in marches]
            res[f"Supertrend 10/3 4 h {nom}{' + EMA 200' if filtre else ''}"] = jouer(jeux)
        jeux = [(e, d[(e, "HOUR_4")], *squeeze(d[(e, "HOUR_4")]), 1.0) for e in marches]
        res[f"TTM Squeeze 4 h {nom}"] = jouer(jeux)
        jeux = [(e, d[(e, "HOUR_4")], *nr7(d[(e, "HOUR_4")]), 1.0) for e in marches]
        res[f"NR7 4 h {nom}"] = jouer(jeux)
        jeux = [(e, d[(e, "HOUR_4")], *macd_ema(d[(e, "HOUR_4")]), 1.0) for e in marches]
        res[f"MACD + EMA 200 4 h {nom}"] = jouer(jeux)
    df = d[("BTCUSD", "HOUR")]
    res["BTC nuit MAX(10) (3 nuits)"] = jouer([("BTCUSD", df, *btc_nuit(df), 1.0)])
    res["BTC nuit MAX(10) (toutes les nuits)"] = jouer([("BTCUSD", df, *btc_nuit(df, toutes_nuits=True), 1.0)])
    res["BTC RSI(5) > 70 jour"] = jouer([("BTCUSD", df, *btc_rsi5(df), 1.0)])
    for e in ("GOLD", "SILVER"):
        dfe = d[(e, "HOUR")]
        res[f"{e} achat séance Asie"] = jouer([(e, dfe, *or_asie(dfe), 1.0)])
        res[f"{e} achat séance Asie + EMA 200"] = jouer([(e, dfe, *or_asie(dfe, True), 1.0)])
        res[f"{e} nuit New York 18 h -> 3 h"] = jouer([(e, dfe, *or_nuit_ny(dfe), 1.0)])
        res[f"{e} tournant du mois"] = jouer([(e, dfe, *or_tournant_mois(dfe), 1.0)])
    return res


def resume(t, p):
    s = serrage.resumer(t, p[0], p[1])
    s["mois"] = round(s["trades"] / (ANS * 12), 1)
    return s


def portefeuille(trades, poids, p):
    """Courbe en % du capital (risque fixe, sans capitalisation) : somme des R × risque % par jour."""
    morceaux = []
    for nom, t in trades.items():
        t = t[t.date >= p[0]]
        morceaux.append(pd.Series(t.R.values * poids[nom], index=t.date))
    s = pd.concat(morceaux).sort_index()
    c = s.cumsum()
    baisse = float((c - np.maximum.accumulate(np.r_[0, c.values])[1:]).min()) if len(c) else 0.0
    return {"pct": round(float(s.sum()), 1), "pct_1": round(float(s[s.index < p[1]].sum()), 1),
            "pct_2": round(float(s[s.index >= p[1]].sum()), 1), "pire_baisse_pct": round(baisse, 1)}


def principal():
    d = {(e, u): serrage.lire(e, u) for e in ("GOLD", "SILVER", "BTCUSD") for u in ("HOUR", "HOUR_4")}
    p = periode([d[k] for k in d])
    print(f"Période : {p[0]:%d/%m/%Y} -> {p[2]:%d/%m/%Y} (moitié au {p[1]:%d/%m/%Y})\n")
    act = actuelles(d)
    neuves = nouvelles(d)
    tete = f"{'stratégie':48s} {'R':>7s} {'an 1':>7s} {'an 2':>7s} {'trades':>6s} {'/mois':>5s} {'réuss.':>6s} {'baisse':>7s}"
    print("=== Stratégies ACTUELLES (même moteur, même période)")
    print(tete)
    sortie = {"periode": [str(x) for x in p], "actuelles": {}, "nouvelles": {}, "portefeuille": {}}
    for nom, t in act.items():
        s = resume(t, p)
        sortie["actuelles"][nom] = s
        print(f"{nom:48s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['mois']:5.1f} "
              f"{s['reussite']:6.1f} {s['pire_baisse_R']:7.2f}")
    print("\n=== Stratégies des RÉSEAUX (réglages publiés, sans optimisation)")
    print(tete)
    for nom, t in sorted(neuves.items(), key=lambda kv: -resume(kv[1], p)["R"]):
        s = resume(t, p)
        s["deux_moities"] = bool(s["R_1"] > 0 and s["R_2"] > 0 and s["trades"] >= 30)
        sortie["nouvelles"][nom] = s
        print(f"{nom:48s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['mois']:5.1f} "
              f"{s['reussite']:6.1f} {s['pire_baisse_R']:7.2f}{'  <- 2 moitiés +' if s['deux_moities'] else ''}")

    poids = {"Cassure 4 h or+argent (actuelle)": 3.0, "Tendance 4 h BTC (actuelle, sans 2e cerveau)": 3.0,
             "Élan 4 h or+argent (actuelle, expérimentale)": 1.0}
    base_pf = portefeuille(act, poids, p)
    sortie["portefeuille"]["actuel"] = base_pf
    print(f"\n=== Portefeuille (en % du capital, risque fixe) : actuel = {base_pf}")
    a_garder = []
    for nom, t in neuves.items():
        if not sortie["nouvelles"][nom]["deux_moities"]:
            continue
        pf = portefeuille({**act, nom: t}, {**poids, nom: 1.0}, p)
        mieux = pf["pct_1"] > base_pf["pct_1"] and pf["pct_2"] > base_pf["pct_2"] \
            and pf["pire_baisse_pct"] >= base_pf["pire_baisse_pct"] - 2
        sortie["portefeuille"][nom] = {**pf, "a_garder": mieux}
        print(f"  + {nom:46s} {pf}{'  <- À GARDER' if mieux else ''}")
        if mieux:
            a_garder.append(nom)
    for nom in a_garder:
        t = neuves[nom]
        t = t[t.date >= p[0]]
        m_new = t.groupby(t.date.dt.to_period("M")).R.sum()
        m_act = pd.concat([x[x.date >= p[0]].assign(R=x.R * poids[n]) for n, x in act.items()])
        m_act = m_act.groupby(m_act.date.dt.to_period("M")).R.sum()
        j = pd.concat([m_new, m_act], axis=1).fillna(0)
        corr = float(j.corr().iloc[0, 1])
        sortie["portefeuille"][nom]["correlation_mensuelle"] = round(corr, 2)
        print(f"  corrélation mensuelle avec l'actuel ({nom}) : {corr:.2f} ; par trimestre (R) : "
              + ", ".join(f"{x:.1f}" for x in t.groupby(t.date.dt.to_period('Q')).R.sum().values))
    sortie["a_garder"] = a_garder
    print(f"\nÀ garder : {a_garder or 'aucune'}")
    (Path(__file__).resolve().parent / "resultats_reseaux.json").write_text(
        json.dumps(sortie, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

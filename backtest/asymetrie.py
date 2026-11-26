"""Recherche « gagner beaucoup en peu de temps » (26/11/2026, demande de Mathis). Ne passe AUCUN ordre.

Trois familles de pistes pas encore testées dans le dépôt :
  A. Trades d'événement / de calendrier (bougies 1 h Capital.com démo) :
       - « dérive avant la Fed » (Lucca & Moench 2015) : acheter l'indice la veille d'une annonce FOMC, revendre
         juste avant l'annonce ;
       - « dérive de nuit » (Lou, Polk & Skouras 2019) : acheter l'indice à la clôture, revendre à l'ouverture.
  B. Cassure de volatilité de Larry Williams (bougies jour) : achat si le prix dépasse l'ouverture + k × l'amplitude
     de la veille (méthode qui l'a fait gagner le championnat 1987), sortie à la clôture du jour.
  C. Taille des positions : critère de Kelly, croissance composée, risque de ruine et chances de réussir un
     challenge de prop firm, à partir des VRAIS trades backtestés des stratégies actives (Cassure or/argent,
     Supertrend ETH).
Méthode (comme l'usine) : réglages choisis sur 2017-2021, jugés sur 01/2022-06/2024 (validation) et
07/2024-aujourd'hui (test), frais réels (spread bid/ask, frais de nuit, prime du stop garanti), et même
procédure sur des prix tirés au hasard (contrôle).

Usage : python backtest/asymetrie.py telecharger <dossier>  puis  python backtest/asymetrie.py <dossier>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from backtest.audit_chiffres import cassure, cond_de, connecter, st_eth  # noqa: E402
from backtest.usine import lire  # noqa: E402

COUPES = (pd.Timestamp("2022-01-01"), pd.Timestamp("2024-07-01"))
INDICES = ("US500", "US100", "US30", "RTY", "DE40")
HORAIRES = INDICES + ("GOLD", "EURUSD")
JOUR = ("GOLD", "SILVER", "OIL_CRUDE", "NATURALGAS", "COPPER", "US500", "US100", "DE40", "J225",
        "EURUSD", "GBPUSD", "USDJPY", "BTCUSD", "ETHUSD")
# Annonces FOMC programmées (jour de la décision, 14 h heure de New York). Sans les réunions d'urgence de mars 2020.
FOMC = """2017-02-01 2017-03-15 2017-05-03 2017-06-14 2017-07-26 2017-09-20 2017-11-01 2017-12-13
2018-01-31 2018-03-21 2018-05-02 2018-06-13 2018-08-01 2018-09-26 2018-11-08 2018-12-19
2019-01-30 2019-03-20 2019-05-01 2019-06-19 2019-07-31 2019-09-18 2019-10-30 2019-12-11
2020-01-29 2020-04-29 2020-06-10 2020-07-29 2020-09-16 2020-11-05 2020-12-16
2021-01-27 2021-03-17 2021-04-28 2021-06-16 2021-07-28 2021-09-22 2021-11-03 2021-12-15
2022-01-26 2022-03-16 2022-05-04 2022-06-15 2022-07-27 2022-09-21 2022-11-02 2022-12-14
2023-02-01 2023-03-22 2023-05-03 2023-06-14 2023-07-26 2023-09-20 2023-11-01 2023-12-13
2024-01-31 2024-03-20 2024-05-01 2024-06-12 2024-07-31 2024-09-18 2024-11-07 2024-12-18
2025-01-29 2025-03-19 2025-05-07 2025-06-18 2025-07-30 2025-09-17 2025-10-29 2025-12-10
2026-01-28 2026-03-18 2026-04-29 2026-06-17 2026-07-29 2026-09-16 2026-10-28""".split()


# Copiés de backtest/audit_hasard.py (qui lit sys.argv dès l'import)
def marche_aleatoire(graine, jours, pas_min=5, sous_pas=5, vol_jour=0.012, spread_pct=0.012, debut="2017-01-02"):
    """Bougies de `pas_min` minutes (bid/ask) d'une marche aléatoire géométrique SANS dérive.
    Chaque bougie est faite de `sous_pas` petits pas (vrais plus haut / plus bas). Bourse ouverte 24 h/24."""
    rng = np.random.default_rng(graine)
    n = int(jours * 1440 / pas_min)
    sig = vol_jour / np.sqrt(1440 / pas_min * sous_pas)
    pas = rng.standard_normal((n, sous_pas)) * sig - sig ** 2 / 2  # martingale exacte sur le prix
    chemin = 2000 * np.exp(np.cumsum(pas.ravel())).reshape(n, sous_pas)
    ouv = np.r_[2000, chemin[:-1, -1]]
    haut = np.maximum(chemin.max(axis=1), ouv)
    bas = np.minimum(chemin.min(axis=1), ouv)
    clo = chemin[:, -1]
    idx = pd.date_range(debut, periods=n, freq=f"{pas_min}min")
    demi = spread_pct / 200
    d = {}
    for nom, x in (("open", ouv), ("high", haut), ("low", bas), ("close", clo)):
        d[f"{nom}_bid"], d[f"{nom}_ask"] = x * (1 - demi), x * (1 + demi)
    d["volume"] = 1.0
    return pd.DataFrame(d, index=idx)


def regrouper(df, regle):
    agg = {}
    for c in df.columns:
        agg[c] = "first" if c.startswith("open") else "max" if c.startswith("high") else "min" if c.startswith("low") \
            else "last" if c.startswith("close") else "sum"
    return df.resample(regle).agg(agg).dropna()



# =========================================================================== données
def telecharger(dossier: Path):
    from backtest import telecharger as t
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    a_faire = [(e, "HOUR", 60) for e in HORAIRES] + [(e, "DAY", 1440) for e in JOUR] + \
        [(e, "HOUR_4", 240) for e in ("GOLD", "SILVER", "ETHUSD")]
    api, deja = connecter(), set()
    for n, (epic, unite, minutes) in enumerate(a_faire):
        if n and n % 4 == 0:  # la session Capital.com expire : on la renouvelle souvent
            api.deconnexion()
            api = connecter()
        try:
            if epic not in deja:
                (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
                deja.add(epic)
            t.telecharger(api, epic, unite, minutes, 3650)
        except Exception as e:
            print(f"{epic} {unite} : échec ({str(e)[:120]})")
    api.deconnexion()


def periodes(t: pd.DataFrame) -> dict:
    t = t.sort_values("date")
    p = [t[t.date < COUPES[0]], t[(t.date >= COUPES[0]) & (t.date < COUPES[1])], t[t.date >= COUPES[1]]]
    c = np.r_[0, np.cumsum(t.R.values)]
    return {"entrainement": round(float(p[0].R.sum()), 1), "validation": round(float(p[1].R.sum()), 1),
            "test": round(float(p[2].R.sum()), 1), "trades": [len(x) for x in p],
            "R_par_trade": round(float(t.R.mean()), 3) if len(t) else 0.0,
            "pire_baisse": round(float((c - np.maximum.accumulate(c)).min()), 1)}


def atr_jour(df: pd.DataFrame, n=14) -> np.ndarray:
    """ATR 14 jours (prix milieu), ramené sur chaque bougie, connu à l'avance (jour précédent)."""
    m = pd.DataFrame({x: (df[f"{x}_bid"] + df[f"{x}_ask"]) / 2 for x in ("high", "low", "close")})
    j = m.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    tr = np.maximum(j.high - j.low, np.maximum(abs(j.high - j.close.shift()), abs(j.low - j.close.shift())))
    a = tr.ewm(alpha=1 / n, adjust=False).mean().shift(1)
    return a.reindex(df.index.floor("1D")).values


# =========================================================================== A. événements
def fenetre_fomc(idx: pd.DatetimeIndex, debut: str) -> np.ndarray:
    """Vrai pour les bougies 1 h qui commencent dans la fenêtre avant l'annonce (heure de New York)."""
    ny = idx.tz_localize("UTC").tz_convert("America/New_York")
    jour = ny.normalize().tz_localize(None)
    h = ny.hour.values
    dates = pd.to_datetime(FOMC)
    veille = dates - pd.tseries.offsets.BDay(1)
    le_jour = np.isin(jour, dates) & (h < 14)
    if debut == "veille_14h":
        return le_jour | (np.isin(jour, veille) & (h >= 14))
    return le_jour & (h >= int(debut.split("_")[1][:-1]))  # "jour_9h" : le matin même seulement


def fenetre_nuit(idx: pd.DatetimeIndex, epic: str, week_end: bool) -> np.ndarray:
    """Vrai entre la clôture de la bourse (16 h New York / 17 h 30 Francfort) et son ouverture le lendemain."""
    tz, fin, ouv = ("Europe/Berlin", 17, 9) if epic == "DE40" else ("America/New_York", 16, 9)
    loc = idx.tz_localize("UTC").tz_convert(tz)
    h, jsem = loc.hour.values, loc.dayofweek.values
    nuit = (h >= fin) | (h < ouv)
    if not week_end:  # pas de nuit du vendredi au lundi (3 nuits de frais)
        nuit &= ~((jsem == 4) & (h >= fin)) & ~(jsem >= 5) & ~((jsem == 0) & (h < ouv))
    return nuit


def jouer_fenetre(df, masque, cond, k_stop, sens=1):
    voulu = np.r_[masque[1:], False].astype(int) * sens  # bougie i-1 décide de l'entrée à l'ouverture de i
    dstop = atr_jour(df) * k_stop
    return serrage.simuler(df, voulu, voulu != 0, dstop, None, cond)


def evenements(donnees: dict, conds: dict) -> list:
    out = []
    for epic, df in donnees.items():
        for debut in ("veille_14h", "jour_9h"):
            for k in (1.0, 2.0):
                t = jouer_fenetre(df, fenetre_fomc(df.index, debut), conds[epic], k)
                out.append({"piste": "Avant la Fed", "marche": epic, "reglage": f"{debut}, stop {k:g} ATR", **periodes(t)})
        if epic in INDICES:
            for we in (False, True):
                for k in (1.0, 2.0):
                    t = jouer_fenetre(df, fenetre_nuit(df.index, epic, we), conds[epic], k)
                    out.append({"piste": "Achat de nuit", "marche": epic,
                                "reglage": f"{'avec' if we else 'sans'} week-end, stop {k:g} ATR", **periodes(t)})
    return out


# =========================================================================== B. cassure de volatilité (Williams)
def williams(df: pd.DataFrame, cond: dict, k: float, sens: str) -> pd.DataFrame:
    """Bougies jour. Ordre stop d'achat à ouverture + k × amplitude d'hier (et de vente symétrique si sens=les2).
    Stop garanti à l'ouverture (distance k × amplitude, au moins le minimum Capital.com), sortie à la clôture du jour.
    Si le stop et l'entrée sont touchés le même jour on compte la perte (on ne connaît pas l'ordre des prix),
    si les deux sens se déclenchent le même jour on compte une perte aussi (prudent)."""
    o, ha, hb, la, lb = (df[c].values for c in ("open_ask", "high_ask", "high_bid", "low_ask", "low_bid"))
    ob, cb, ca = df.open_bid.values, df.close_bid.values, df.close_ask.values
    om = (o + ob) / 2
    amp = ((df.high_bid + df.high_ask) / 2 - (df.low_bid + df.low_ask) / 2).shift(1).values
    trades = []
    for i in range(1, len(df)):
        if not amp[i] == amp[i] or amp[i] <= 0:
            continue
        d = max(k * amp[i], om[i] * cond["min_pct"] / 100)
        achat = om[i] + k * amp[i]
        vente = om[i] - k * amp[i]
        t_achat = ha[i] >= achat
        t_vente = sens == "les2" and lb[i] <= vente
        if t_achat and t_vente:
            trades.append((df.index[i], -1 - om[i] * 0.001 / d, "les deux"))
            continue
        if t_achat:
            e = max(achat, o[i])
            stop = e - d
            r = -1 - stop * 0.001 / d if lb[i] <= stop else (cb[i] - e) / d
            trades.append((df.index[i], r, "achat"))
        elif t_vente:
            e = min(vente, ob[i])
            stop = e + d
            r = -1 - stop * 0.001 / d if ha[i] >= stop else (e - ca[i]) / d
            trades.append((df.index[i], r, "vente"))
    return pd.DataFrame(trades, columns=["date", "R", "raison"])


def fouille_williams(donnees: dict, conds: dict) -> dict:
    """Choix sur 2017-2021 seulement : par marché, le meilleur réglage ; on garde les marchés gagnants à l'entraînement."""
    lignes, choisis = [], []
    for epic, df in donnees.items():
        best = None
        for k in (0.3, 0.5, 0.7, 1.0):
            for sens in ("les2", "achat"):
                p = periodes(williams(df, conds[epic], k, sens))
                lignes.append({"marche": epic, "reglage": f"k={k:g}, {sens}", **p})
                if best is None or p["entrainement"] > best["entrainement"]:
                    best = lignes[-1]
        if best["entrainement"] > 0:
            choisis.append(best)
    tot = {x: round(sum(c[x] for c in choisis), 1) for x in ("entrainement", "validation", "test")}
    return {"essais": len(lignes), "choisis_sur_2017_2021": choisis, "total_des_choisis": tot,
            "gagnants_validation_et_test": [c["marche"] for c in choisis if c["validation"] > 0 and c["test"] > 0]}


# =========================================================================== contrôle : prix au hasard
def hasard(graines=4) -> dict:
    """Même procédure sur des marches aléatoires (sans aucun avantage possible) : doit perdre ses frais."""
    res = {"avant_la_fed": [], "achat_de_nuit": [], "williams_total_des_choisis": []}
    cond = {"nuit_achat": 0.02, "nuit_vente": 0.02, "min_pct": 0.25}
    for g in range(graines):
        h = regrouper(marche_aleatoire(g, 3500, pas_min=15, sous_pas=4, vol_jour=0.011, spread_pct=0.01), "1h")
        h = h[h.index.dayofweek < 5]
        t = jouer_fenetre(h, fenetre_fomc(h.index, "veille_14h"), cond, 1.0)
        res["avant_la_fed"].append(periodes(t))
        t = jouer_fenetre(h, fenetre_nuit(h.index, "US500", False), cond, 1.0)
        res["achat_de_nuit"].append(periodes(t))
        j = regrouper(h, "1D")
        res["williams_total_des_choisis"].append(fouille_williams({f"H{g}": j}, {f"H{g}": cond})["total_des_choisis"])
    return res


# =========================================================================== C. taille, Kelly, ruine, challenge
def croissance(R: np.ndarray, par_an: int, risques=(0.5, 1, 2, 3, 5, 8, 12, 20, 30), n=20000, graine=1) -> list:
    """Tirage au hasard de 1 an de trades (avec remise) parmi les vrais trades : capital × (1 + risque × R)."""
    rng = np.random.default_rng(graine)
    tirs = R[rng.integers(0, len(R), (n, par_an))]
    out = []
    for f in risques:
        x = np.maximum(1 + f / 100 * tirs, 1e-9)
        cap = np.cumprod(x, axis=1)
        pire = (cap / np.maximum.accumulate(np.c_[np.ones(n), cap], axis=1)[:, 1:]).min(axis=1)
        fin = cap[:, -1]
        out.append({"risque_pct": f, "capital_median_x": round(float(np.median(fin)), 2),
                    "chance_perte_pct": round(float((fin < 1).mean() * 100), 1),
                    "chance_x2_pct": round(float((fin >= 2).mean() * 100), 1),
                    "chance_x10_pct": round(float((fin >= 10).mean() * 100), 1),
                    "chance_baisse_50_pct": round(float((pire <= 0.5).mean() * 100), 1),
                    "chance_ruine_90_pct": round(float((cap.min(axis=1) <= 0.1).mean() * 100), 1)})
    return out


def kelly(R: np.ndarray) -> float:
    fs = np.linspace(0.001, 0.6, 600)
    g = [np.mean(np.log(np.maximum(1 + f * R, 1e-12))) for f in fs]
    return round(float(fs[int(np.argmax(g))] * 100), 1)


def challenge(R: np.ndarray, risque: float, objectif=10, perte_max=10, n=20000, max_trades=400, graine=2) -> dict:
    """Challenge type FTMO : +10 % avant -10 % (le -5 %/jour est presque jamais touché avec 1 trade à la fois)."""
    rng = np.random.default_rng(graine)
    tirs = R[rng.integers(0, len(R), (n, max_trades))]
    cap = np.cumsum(risque * tirs, axis=1)  # en % du capital de départ (règles des prop firms : pas composé)
    gagne = np.where((cap >= objectif).any(axis=1), (cap >= objectif).argmax(axis=1), max_trades + 1)
    perdu = np.where((cap <= -perte_max).any(axis=1), (cap <= -perte_max).argmax(axis=1), max_trades + 1)
    ok = gagne < perdu
    return {"risque_pct": risque, "chance_reussite_pct": round(float(ok.mean() * 100), 1),
            "trades_medians_si_reussi": int(np.median(gagne[ok])) if ok.any() else None}


def tailles(dossier: Path) -> dict:
    serrage.NUITS_EXACTES = True
    tous = pd.concat([cassure(dossier, False).assign(strat="Cassure or+argent"),
                      st_eth(dossier).assign(strat="Supertrend ETH")]).sort_values("date")
    res = {}
    for nom, t in (("Cassure or+argent", tous[tous.strat == "Cassure or+argent"]), ("Cassure + Supertrend", tous)):
        ent, jv = t[t.date < COUPES[0]], t[t.date >= COUPES[0]]
        ans = (t.date.max() - t.date.min()).days / 365.25
        par_an = int(round(len(t) / ans))
        # année réelle par année réelle, à 3 % de risque (ordre réel des trades)
        reel = {}
        for f in (1, 3, 5, 10):
            reel[f"{f}%"] = {str(a): round(float(np.prod(1 + f / 100 * g.R.values)), 2) for a, g in t.groupby(t.date.dt.year)}
        res[nom] = {"trades_par_an": par_an, "R_par_trade_entrainement": round(float(ent.R.mean()), 3),
                    "R_par_trade_2022_auj": round(float(jv.R.mean()), 3),
                    "kelly_pct_entrainement": kelly(ent.R.values), "kelly_pct_2022_auj": kelly(jv.R.values),
                    "un_an_au_hasard_sur_2022_auj": croissance(jv.R.values, par_an),
                    "un_an_au_hasard_sur_2017_2021": croissance(ent.R.values, par_an),
                    "capital_x_par_annee_reelle": reel,
                    "challenge_prop_firm": [challenge(jv.R.values, f) for f in (0.5, 1, 2, 3)]}
    return res


# =========================================================================== bilan
def principal(dossier: Path):
    res = {}
    h = {e: lire(dossier, e, "HOUR") for e in HORAIRES}
    h = {e: d for e, d in h.items() if d is not None and len(d) > 5000}
    conds = {e: cond_de(dossier, e, d) for e, d in h.items()}
    res["donnees_1h"] = {e: f"{d.index[0]:%m/%Y} -> {d.index[-1]:%m/%Y}" for e, d in h.items()}
    res["A_evenements"] = evenements(h, conds)
    j = {e: lire(dossier, e, "DAY") for e in JOUR}
    j = {e: d for e, d in j.items() if d is not None and len(d) > 500}
    res["B_williams"] = fouille_williams(j, {e: cond_de(dossier, e, d) for e, d in j.items()})
    res["controle_prix_au_hasard"] = hasard()
    res["C_tailles"] = tailles(dossier)
    for x in res["A_evenements"]:
        print(f"{x['piste']:14s} {x['marche']:7s} {x['reglage']:34s} {x['entrainement']:7.1f} {x['validation']:7.1f} "
              f"{x['test']:7.1f}  {x['trades']}")
    print(json.dumps({k: v for k, v in res.items() if k != "A_evenements"}, ensure_ascii=False, indent=1)[:20000])
    Path(__file__).resolve().parent.joinpath("resultats_asymetrie.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    if sys.argv[1] == "telecharger":
        telecharger(Path(sys.argv[2]))
    else:
        principal(Path(sys.argv[1]))

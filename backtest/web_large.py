"""Grande fouille du web (26/11/2026, demande de Mathis : « retourne tout le web »). Ne passe AUCUN ordre.

Idées trouvées par 5 recherches (calendrier et événements, catalogues académiques, forums en plusieurs langues,
GitHub/Kaggle, carry et spreads), codées ici en familles de règles simples sur les prix Capital.com démo.

Méthode (comme l'usine et la recherche « gains rapides ») :
  1. réglages choisis sur 2017-2021 seulement (par famille et par marché, le meilleur réglage) ;
  2. jugés sur 01/2022-06/2024 (validation) et 07/2024-aujourd'hui (test), jamais vus ;
  3. frais réels : spread bid/ask, frais de nuit, prime du stop garanti ; puis frais x 1,5 (stress) ;
  4. voisins : les autres réglages du même marché doivent aussi gagner sur les années jamais vues ;
  5. prix au hasard : même procédure sur des prix mélangés (bougies permutées, plus aucun effet de calendrier) ;
  6. correction pour le nombre d'essais (Bonferroni sur tous les couples famille x marché retenus).
« Solide » = tout passe, y compris Bonferroni. « Prometteur » = tout sauf Bonferroni (p < 0,05 seul).

Usage : python backtest/web_large.py telecharger <dossier>  puis  python backtest/web_large.py <dossier>
"""
import json
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from backtest.asymetrie import FOMC  # noqa: E402
from backtest.audit_chiffres import cond_de, connecter  # noqa: E402
from backtest.usine import MARCHES, lire  # noqa: E402

serrage.NUITS_EXACTES = True
COUPES = (pd.Timestamp("2022-01-01"), pd.Timestamp("2024-07-01"))
JOUR = [m.strip() for m in MARCHES.split(",")]
# 26/11 (demande de Mathis) : CHAQUE idée testée sur TOUS les marchés (jour et 1 h)
HORAIRE = ("US500", "US100", "US30", "RTY", "DE40", "EU50", "FR40", "UK100", "J225", "AU200",
           "GOLD", "SILVER", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "ETHUSD") + tuple(
    m.strip() for m in MARCHES.split(",") if m.strip() not in ("US500", "US100", "US30", "RTY", "DE40", "EU50", "FR40",
                                                                 "UK100", "J225", "AU200", "GOLD", "SILVER", "EURUSD",
                                                                 "GBPUSD", "USDJPY", "AUDUSD", "BTCUSD", "ETHUSD"))
TOUS_LES_MARCHES = True
INDICES = ("US500", "US100", "US30", "RTY", "DE40", "UK100", "FR40", "EU50", "J225", "HK50", "AU200")
US = ("US500", "US100", "US30", "RTY")
NORM = NormalDist()
DATES = {}  # listes de dates d'annonces (dates.json à côté de ce fichier), lues dans principal()


# =========================================================================== données
def telecharger(dossier: Path):
    from backtest import telecharger as t
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    api, deja = connecter(), set()
    petits = list(trouver_petits(api, dossier))
    a_faire = [(e, "DAY", 1440) for e in JOUR + petits] + [(e, "HOUR", 60) for e in HORAIRE]
    for n, (epic, unite, minutes) in enumerate(a_faire):
        if (dossier / f"{epic}_{unite}.csv").exists():  # déjà dans le cache GitHub
            continue
        if n and n % 4 == 0:  # la session Capital.com expire : on la renouvelle souvent
            try:
                api.deconnexion()
            except Exception:
                pass
            api = connecter()
        try:
            if epic not in deja and not (dossier / f"{epic}_marche.json").exists():
                (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
            deja.add(epic)
            t.telecharger(api, epic, unite, minutes, 3650)
        except Exception as e:
            print(f"{epic} {unite} : échec ({str(e)[:120]})")
    api.deconnexion()


# 26/11 (demande de Mathis) : les « petits marchés » délaissés par les gros fonds. Epics essayés tels quels, puis
# recherchés par nom dans la liste des marchés Capital.com si l'epic n'existe pas. Spreads réels (bid/ask) utilisés.
PETITS = {
    "matières premières secondaires": ["COCOA", "COFFEEARABICA", "SUGAR", "COTTON", "OATS", "WHEAT", "CORN", "SOYBEAN",
                                       "ORANGEJUICE", "LUMBER", "LIVECATTLE", "LEANHOGS", "RICE", "HEATINGOIL", "GASOLINE"],
    "devises exotiques": ["USDTRY", "USDZAR", "USDMXN", "USDPLN", "USDHUF", "USDSEK", "USDNOK", "USDSGD", "USDCNH",
                          "EURTRY", "USDTHB", "USDCZK"],
    "petites cryptos": ["ADAUSD", "DOTUSD", "LINKUSD", "AVAXUSD", "ATOMUSD", "BCHUSD", "XLMUSD", "UNIUSD", "TRXUSD",
                        "ALGOUSD", "EOSUSD", "ETCUSD"],
    "petits indices": ["NL25", "ES35", "IT40", "CH20", "CN50", "SG25", "IN50", "SE30", "PL20", "SA40", "MX35", "NO25"],
    "petites actions": ["PLUG", "RIOT", "MARA", "SOFI", "GME", "AMC", "LCID", "RIVN", "NIO", "SNAP", "PLTR", "COIN"],
}
RECHERCHE = {"COCOA": "Cocoa", "COFFEEARABICA": "Coffee", "SUGAR": "Sugar", "COTTON": "Cotton", "OATS": "Oats",
             "WHEAT": "Wheat", "CORN": "Corn", "SOYBEAN": "Soybean", "ORANGEJUICE": "Orange Juice", "LUMBER": "Lumber",
             "LIVECATTLE": "Live Cattle", "LEANHOGS": "Lean Hogs", "RICE": "Rice", "HEATINGOIL": "Heating Oil",
             "GASOLINE": "Gasoline", "NL25": "Netherlands 25", "ES35": "Spain 35", "IT40": "Italy 40",
             "CH20": "Switzerland 20", "CN50": "China A50", "SG25": "Singapore", "IN50": "India 50", "SE30": "Sweden 30",
             "PL20": "Poland 20", "SA40": "South Africa 40", "MX35": "Mexico", "NO25": "Norway 25"}


def trouver_petits(api, dossier: Path) -> dict:
    """{epic: catégorie} des petits marchés qui existent vraiment chez Capital.com (écrit dans petits_marches.json)."""
    f = dossier / "petits_marches.json"
    if f.exists():
        return json.loads(f.read_text())
    trouves = {}
    for cat, liste in PETITS.items():
        for epic in liste:
            vrai = None
            try:
                api.marche(epic)
                vrai = epic
            except Exception:
                if epic in RECHERCHE:
                    try:
                        r = api._requete("GET", "/markets", params={"searchTerm": RECHERCHE[epic]}).get("markets", [])
                        r = [m for m in r if m.get("instrumentType") in ("COMMODITIES", "INDICES")]
                        vrai = r[0]["epic"] if r else None
                    except Exception:
                        vrai = None
            if vrai and vrai not in trouves:
                trouves[vrai] = cat
            print(f"petit marché {epic} -> {vrai}", flush=True)
    f.write_text(json.dumps(trouves, ensure_ascii=False))
    return trouves


def petits_connus(dossier: Path) -> dict:
    f = dossier / "petits_marches.json"
    return json.loads(f.read_text()) if f.exists() else {}


# =========================================================================== outils
def jour_de_bourse(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Date de séance d'une bougie jour (Capital.com fait parfois commencer la bougie la veille à 21-23 h UTC)."""
    return (idx + pd.Timedelta(hours=6)).floor("D")


def atr(df: pd.DataFrame, n=14) -> np.ndarray:
    """ATR 14 jours (prix milieu) connu à l'avance : sur bougies jour = ATR des jours terminés ; sur 1 h = idem
    ramené sur chaque heure."""
    m = pd.DataFrame({x: (df[f"{x}_bid"] + df[f"{x}_ask"]) / 2 for x in ("high", "low", "close")})
    j = m.groupby(jour_de_bourse(m.index)).agg({"high": "max", "low": "min", "close": "last"})
    tr = np.maximum(j.high - j.low, np.maximum(abs(j.high - j.close.shift()), abs(j.low - j.close.shift())))
    a = tr.ewm(alpha=1 / n, adjust=False).mean().shift(1)
    return a.reindex(jour_de_bourse(df.index)).values


def mid(df, x="close"):
    return ((df[f"{x}_bid"] + df[f"{x}_ask"]) / 2).values


def jouer(df, cond, tenir, sens, k_stop, dstop=None):
    """tenir[i] : on veut être en position PENDANT la bougie i (calendrier connu à l'avance) ; sens : +1/-1
    (scalaire ou tableau, connu à la fin de la bougie i-1). Entrée à l'ouverture de la 1re bougie, sortie à
    l'ouverture de la bougie qui suit la fenêtre. Stop garanti à k_stop x ATR jour."""
    tenir = np.asarray(tenir, dtype=bool)
    s = np.broadcast_to(np.asarray(sens, dtype=float), tenir.shape)
    s = np.nan_to_num(s)
    voulu = np.r_[tenir[1:] * np.sign(s[1:]), 0].astype(int)  # décidé à la bougie i-1 pour la bougie i
    d = atr(df) * k_stop if dstop is None else dstop
    return serrage.simuler(df, voulu, voulu != 0, d, None, cond)


def stresser(df: pd.DataFrame, cond: dict, f=1.5):
    """Spread et frais de nuit x f."""
    d = df.copy()
    for x in ("open", "high", "low", "close"):
        m, e = (d[f"{x}_bid"] + d[f"{x}_ask"]) / 2, (d[f"{x}_ask"] - d[f"{x}_bid"]) / 2 * f
        d[f"{x}_bid"], d[f"{x}_ask"] = m - e, m + e
    c = dict(cond, nuit_achat=cond["nuit_achat"] * f, nuit_vente=cond["nuit_vente"] * f)
    return d, c


def melanger(df: pd.DataFrame, graine: int) -> pd.DataFrame:
    """Prix au hasard : on permute les bougies (rendement, forme, spread) en gardant les dates. Plus aucun effet de
    calendrier ni de lien entre marchés, mais la même volatilité et les mêmes frais."""
    rng = np.random.default_rng(graine)
    c = mid(df)
    r = np.r_[0, np.diff(np.log(c))]
    rel = {x: np.log(mid(df, x) / c) for x in ("open", "high", "low")}
    sp = {x: (df[f"{x}_ask"] - df[f"{x}_bid"]).values / mid(df, x) for x in ("open", "high", "low", "close")}
    p = rng.permutation(len(df))
    c2 = c[0] * np.exp(np.cumsum(r[p]))
    out = {}
    for x in ("open", "high", "low", "close"):
        m = c2 * np.exp(rel[x][p]) if x != "close" else c2
        out[f"{x}_bid"], out[f"{x}_ask"] = m * (1 - sp[x][p] / 2), m * (1 + sp[x][p] / 2)
    out["volume"] = 1.0
    return pd.DataFrame(out, index=df.index)


def resume(t: pd.DataFrame) -> dict:
    if t is None or not len(t):
        return {"entrainement": 0.0, "validation": 0.0, "test": 0.0, "trades": [0, 0, 0], "R_trade": 0.0, "t_jv": 0.0,
                "pire_baisse": 0.0}
    t = t.sort_values("date")
    p = [t[t.date < COUPES[0]], t[(t.date >= COUPES[0]) & (t.date < COUPES[1])], t[t.date >= COUPES[1]]]
    jv = t[t.date >= COUPES[0]].R.values
    tj = float(jv.mean() / jv.std(ddof=1) * np.sqrt(len(jv))) if len(jv) > 2 and jv.std() > 0 else 0.0
    c = np.r_[0, np.cumsum(t.R.values)]
    return {"entrainement": round(float(p[0].R.sum()), 1), "validation": round(float(p[1].R.sum()), 1),
            "test": round(float(p[2].R.sum()), 1), "trades": [len(x) for x in p],
            "R_trade": round(float(t.R.mean()), 3), "t_jv": round(tj, 2),
            "pire_baisse": round(float((c - np.maximum.accumulate(c)).min()), 1)}


# =========================================================================== calendrier
def feries_nyse(a0=2016, a1=2027) -> pd.DatetimeIndex:
    from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay,
                                        USMartinLutherKingJr, USMemorialDay, USPresidentsDay, USThanksgivingDay,
                                        nearest_workday)

    class NYSE(AbstractHolidayCalendar):
        rules = [Holiday("an", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr, USPresidentsDay,
                 GoodFriday, USMemorialDay,
                 Holiday("juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
                 Holiday("4juillet", month=7, day=4, observance=nearest_workday), USLaborDay, USThanksgivingDay,
                 Holiday("noel", month=12, day=25, observance=nearest_workday)]
    return NYSE().holidays(f"{a0}-01-01", f"{a1}-12-31")


def rang_dans_mois(jours: pd.DatetimeIndex):
    """Pour des jours de séance triés : rang depuis le début du mois (1, 2, ...) et depuis la fin (-1 = dernier)."""
    s = pd.Series(1, index=jours)
    g = s.groupby([jours.year, jours.month])
    return g.cumsum().values, (g.cumsum() - g.transform("sum") - 1).values


def troisieme_vendredi(jours: pd.DatetimeIndex) -> np.ndarray:
    return ((jours.dayofweek == 4) & (jours.day >= 15) & (jours.day <= 21))


# =========================================================================== familles : bougies jour
def fam_debut_mois(df, cond, k):
    """Turn-of-the-month (Ariel 1987, Lakonishok-Smidt 1988, McConnell-Xu 2008) : tenir des derniers N jours du mois
    aux M premiers jours du mois suivant."""
    j = jour_de_bourse(df.index)
    debut, fin = rang_dans_mois(j)
    out = {}
    for n in (1, 2, 3):
        for m in (2, 3, 4):
            tenir = (fin >= -n) | (debut <= m)
            out[f"{n} derniers + {m} premiers jours"] = jouer(df, cond, tenir, 1, k)
    return out


def fam_veille_ferie(df, cond, k):
    """Pre-holiday effect (Ariel 1990, Kim-Park 1994) : les indices montent la veille des jours fériés (NYSE)."""
    j = jour_de_bourse(df.index)
    fer = feries_nyse()
    veille = np.isin(j + pd.offsets.BDay(1), fer) | np.isin(j + pd.offsets.BDay(1) + pd.offsets.BDay(0), fer)
    apres = np.isin(j - pd.offsets.BDay(1), fer)
    v2 = np.isin(j + pd.offsets.BDay(2), fer) & ~veille
    return {"veille": jouer(df, cond, veille, 1, k),
            "veille + lendemain": jouer(df, cond, veille | apres, 1, k),
            "2 veilles": jouer(df, cond, veille | v2, 1, k)}


def fam_opex(df, cond, k):
    """Semaine d'expiration des options (3e vendredi) haussière, semaine suivante baissière (Stivers-Sun 2013)."""
    j = jour_de_bourse(df.index)
    v = troisieme_vendredi(j)
    sem = pd.Series(j.to_period("W-FRI"), index=df.index)
    sem_opex = set(sem[v].values)
    dans = sem.isin(sem_opex).values
    suivante = sem.apply(lambda p: (p - 1) in sem_opex).values
    return {"achat semaine OPEX": jouer(df, cond, dans, 1, k),
            "vente semaine après OPEX": jouer(df, cond, suivante, -1, k),
            "achat OPEX + vente après": jouer(df, cond, dans | suivante, np.where(dans, 1, -1), k)}


def fam_jour_semaine(df, cond, k, crypto=False):
    """Effet jour de la semaine (lundi, vendredi...) ; cryptos : week-end."""
    j = jour_de_bourse(df.index)
    out = {}
    noms = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
    for d in range(7 if crypto else 5):
        for s in (1, -1):
            out[f"{'achat' if s > 0 else 'vente'} le {noms[d]}"] = jouer(df, cond, j.dayofweek == d, s, k)
    if crypto:
        for s in (1, -1):
            out[f"{'achat' if s > 0 else 'vente'} le week-end"] = jouer(df, cond, j.dayofweek >= 5, s, k)
    return out


def fam_saison_mois(df, cond, k):
    """Saisonnalité de retour (Heston-Sadka 2008, Keloharju-Linnainmaa-Nyberg 2016) : ce mois-ci, même sens que la
    moyenne du même mois les années passées (au moins 3 ans connus)."""
    j = jour_de_bourse(df.index)
    c = pd.Series(mid(df), index=j)
    mens = c.groupby([j.year, j.month]).last()
    r = np.log(mens).diff()
    out = {}
    for ans in (3, 5, 99):
        s = {}
        for (a, m), _ in r.items():
            passe = [r.get((a - x, m)) for x in range(1, ans + 1)]
            passe = [x for x in passe if x is not None and x == x]
            s[(a, m)] = np.sign(np.mean(passe)) if len(passe) >= 3 else 0
        sens = np.array([s.get((d.year, d.month), 0) for d in j])
        out[f"même mois, {ans if ans < 99 else 'toutes les'} années passées"] = jouer(df, cond, sens != 0, sens, k)
    return out


def fam_halloween(df, cond, k):
    """« Sell in May » (Bouman-Jacobsen 2002) : acheté de novembre à avril seulement."""
    j = jour_de_bourse(df.index)
    out = {}
    for deb in (10, 11):
        for fin in (4, 5):
            tenir = (j.month >= deb) | (j.month <= fin)
            out[f"achat de {deb} à {fin}"] = jouer(df, cond, tenir, 1, k)
    return out


def fam_ibs(df, cond, k):
    """Internal Bar Strength (Pagonidis 2013, réplications Quantpedia/QuantifiedStrategies) : acheter à la clôture d'un
    jour qui finit près de son plus bas, revendre le lendemain."""
    h, l, c = mid(df, "high"), mid(df, "low"), mid(df)
    ibs = (c - l) / np.where(h > l, h - l, np.nan)
    out = {}
    for x in (0.1, 0.2, 0.3):
        for jours in (1, 3):
            sig = ibs < x
            tenir = np.zeros(len(df), bool)
            for d in range(1, jours + 1):
                tenir |= np.r_[np.zeros(d, bool), sig[:-d]]
            out[f"IBS < {x}, {jours} j"] = jouer(df, cond, tenir, 1, k)
            out[f"IBS > {1 - x:.1f}, vente {jours} j"] = jouer(
                df, cond, np.r_[np.zeros(1, bool), (ibs > 1 - x)[:-1]] if jours == 1 else
                np.convolve((ibs > 1 - x).astype(float), np.ones(jours))[:len(df)].astype(bool) & np.r_[False, np.ones(len(df) - 1, bool)], -1, k)
    return out


def fam_baisses_affilee(df, cond, k):
    """Retour à la moyenne court terme (Lo-MacKinlay 1990, Connors) : après N clôtures en baisse, acheter M jours."""
    c = mid(df)
    bas = np.r_[False, c[1:] < c[:-1]]
    out = {}
    for n in (2, 3, 4):
        suite = pd.Series(bas).rolling(n).sum().values == n
        for m in (1, 3, 5):
            tenir = np.zeros(len(df), bool)
            for d in range(1, m + 1):
                tenir |= np.r_[np.zeros(d, bool), suite[:-d]]
            out[f"{n} baisses -> achat {m} j"] = jouer(df, cond, tenir, 1, k)
    return out


def fam_fin_mois_reequilibrage(df, cond, k):
    """Rééquilibrage des fonds de pension en fin de mois (Harvey, Mazzoleni, Melone 2025) : si l'indice a beaucoup
    monté depuis le début du mois, il baisse les derniers jours (et l'inverse)."""
    j = jour_de_bourse(df.index)
    debut, fin = rang_dans_mois(j)
    c = pd.Series(mid(df), index=df.index)
    premier = c.groupby([j.year, j.month]).transform("first").shift(0)
    mtd = (c / pd.Series(np.r_[np.nan, c.values[:-1]], index=c.index).groupby([j.year, j.month]).transform("first")) - 1
    out = {}
    for n in (2, 3, 5):
        for trim in (False, True):
            tenir = (fin >= -n) & ((j.month % 3 == 0) if trim else True)
            # sens figé à la clôture qui précède la fenêtre
            sens = pd.Series(np.where(fin == -n, -np.sign(mtd.shift(1).values), np.nan), index=c.index).ffill().values
            out[f"{n} derniers jours{' (trimestre)' if trim else ''}"] = jouer(df, cond, tenir, sens, k)
    del premier
    return out


def fam_retour_semaine(df, cond, k):
    """Retournement hebdomadaire des indices (Baltussen, van Bekkum, Da, JFE 2019) : chaque vendredi, position contraire
    au rendement des 5 derniers jours, tenue une semaine."""
    j = jour_de_bourse(df.index)
    c = pd.Series(mid(df), index=df.index)
    out = {}
    ven = (j.dayofweek == 4)
    for L in (5, 10):
        r = (c / c.shift(L) - 1).where(ven).ffill().shift(1).values  # connu à la clôture du vendredi
        for sens, nom in ((-1, "contre"), (1, "avec")):
            out[f"{nom} les {L} derniers jours, tenu 1 semaine"] = jouer(df, cond, ~np.isnan(r), sens * np.sign(r), k)
    return out


def fam_crypto_semaine(df, cond, k):
    """Momentum hebdomadaire des cryptos (Liu-Tsyvinski, RFS 2021) : achat le lundi pour 7 jours si la semaine passée
    a monté."""
    j = jour_de_bourse(df.index)
    c = pd.Series(mid(df), index=df.index)
    lun = j.dayofweek == 0
    out = {}
    for L in (7, 14, 28):
        r = (c / c.shift(L) - 1).where(lun).ffill().shift(1).values
        out[f"achat si hausse sur {L} j"] = jouer(df, cond, r > 0, 1, k)
        out[f"achat/vente selon {L} j"] = jouer(df, cond, ~np.isnan(r), np.sign(r), k)
    return out


def fam_composite(df, cond, k):
    """Calendrier composite de Quantpedia (2019) : fin de mois + semaine avant l'OPEX + 15 du mois, seulement au-dessus
    de la moyenne 200 jours."""
    j = jour_de_bourse(df.index)
    debut, fin = rang_dans_mois(j)
    c = pd.Series(mid(df), index=df.index)
    haut = (c > c.rolling(200).mean()).shift(1).fillna(False).values
    v = troisieme_vendredi(j)
    sem_v = pd.Series(j.to_period("W-FRI"), index=df.index)
    s_opex = set(sem_v[v].values)
    avant_opex = sem_v.isin(s_opex).values & (j.dayofweek <= 3)
    paie = j.day.isin([16, 17]) & (pd.Series(j.day, index=df.index).shift(1).isin([13, 14, 15]).values)
    fdm = (fin == -1) | (debut == 1)
    out = {}
    for nom, t in (("fin de mois", np.r_[fdm[1:], False] | fdm), ("avant OPEX", avant_opex), ("lendemain du 15", paie),
                   ("les trois", fdm | avant_opex | paie)):
        out[f"{nom}, filtre 200 j"] = jouer(df, cond, t & haut, 1, k)
        out[f"{nom}, sans filtre"] = jouer(df, cond, t, 1, k)
    return out


def fam_crypto_fin_mois(df, cond, k):
    """BTC/ETH achetés du 25 au 3 du mois suivant (idée de forum, preuve faible)."""
    j = jour_de_bourse(df.index)
    return {"du 25 au 3": jouer(df, cond, (j.day >= 25) | (j.day <= 3), 1, k),
            "du 28 au 5": jouer(df, cond, (j.day >= 28) | (j.day <= 5), 1, k)}


def fam_veille_banque(cle):
    """Dérive avant les banques centrales hors Fed (Quantpedia 2025) : l'indice local monte de la clôture de J-2 à la
    clôture de J-1 (BoE, BoJ, BCE) ; baisse avant la RBA."""
    def f(df, cond, k):
        dates = DATES.get(cle, [])
        if not dates:
            return {}
        j = jour_de_bourse(df.index)
        d = pd.to_datetime(dates)
        veille = np.isin(j, d - pd.offsets.BDay(1))
        v2 = np.isin(j, d - pd.offsets.BDay(2))
        return {"achat la veille": jouer(df, cond, veille, 1, k), "vente la veille": jouer(df, cond, veille, -1, k),
                "achat J-2 et J-1": jouer(df, cond, veille | v2, 1, k)}
    return f


def fam_inversion_fin_mois(df, cond, k):
    """Inversion de fin de mois (Graziani 2024, « Dash for Cash » Etula et al. 2020) : si l'indice a baissé du 4e
    vendredi à la fin du mois, acheté le mois suivant (ou ses 5 premiers jours)."""
    j = jour_de_bourse(df.index)
    debut, fin = rang_dans_mois(j)
    c = pd.Series(mid(df), index=df.index)
    v4 = (j.dayofweek == 4) & (j.day >= 22) & (j.day <= 28)
    ref = c.where(v4).groupby([j.year, j.month]).transform("last")
    fin_m = c.where(fin == -1)
    r = (fin_m / ref - 1).ffill().shift(1).values  # connu à la clôture du dernier jour
    out = {}
    for nj in (5, 10, 31):
        tenir = (debut <= nj) & (r < 0)
        out[f"achat {nj if nj < 31 else 'tout le'} {'premiers jours' if nj < 31 else 'mois'} après une fin de mois en baisse"] = jouer(df, cond, tenir, 1, k)
    return out


def fam_automne_or(df, cond, k):
    """Effet d'automne de l'or (Baur 2013) : acheté en septembre et novembre."""
    j = jour_de_bourse(df.index)
    return {"septembre + novembre": jouer(df, cond, j.month.isin([9, 11]), 1, k),
            "août à novembre": jouer(df, cond, j.month.isin([8, 9, 10, 11]), 1, k)}


FAMILLES_JOUR = {
    "Veille BoE (indice anglais)": (fam_veille_banque("BOE"), ("UK100",)),
    "Veille BoJ (Nikkei)": (fam_veille_banque("BOJ"), ("J225",)),
    "Veille BCE (indices zone euro)": (fam_veille_banque("ECB"), ("DE40", "EU50", "FR40")),
    "Veille RBA (indice australien)": (fam_veille_banque("RBA"), ("AU200",)),
    "Inversion de fin de mois": (fam_inversion_fin_mois, US + ("DE40", "J225")),
    "Automne de l'or": (fam_automne_or, ("GOLD",)),
    "Retournement hebdo des indices": (fam_retour_semaine, INDICES),
    "Momentum hebdo crypto": (fam_crypto_semaine, ("BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD")),
    "Calendrier composite (Quantpedia)": (fam_composite, US),
    "Crypto du 25 au 3": (fam_crypto_fin_mois, ("BTCUSD", "ETHUSD")),
    "Début/fin de mois": (fam_debut_mois, INDICES + ("GOLD", "BTCUSD")),
    "Veille de jour férié": (fam_veille_ferie, INDICES),
    "Expiration des options": (fam_opex, US + ("DE40",)),
    "Jour de la semaine": (fam_jour_semaine, None),  # tous les marchés
    "Saisonnalité même mois": (fam_saison_mois, None),
    "Sell in May (Halloween)": (fam_halloween, INDICES),
    "IBS (clôture près du bas)": (fam_ibs, INDICES + ("GOLD", "BTCUSD", "ETHUSD")),
    "Baisses d'affilée": (fam_baisses_affilee, INDICES + ("GOLD", "SILVER", "BTCUSD", "ETHUSD")),
    "Rééquilibrage fin de mois": (fam_fin_mois_reequilibrage, US + ("DE40", "UK100", "EU50")),
}


# =========================================================================== familles : bougies 1 h
def heure_locale(idx, tz):
    loc = idx.tz_localize("UTC").tz_convert(tz)
    return loc, loc.normalize().tz_localize(None), loc.hour.values


def fenetre_evenement(idx, dates, tz, h_avant, h_annonce, apres=None):
    """Avant : de la veille (jour ouvré) h_avant au jour J h_annonce - 1 h (on sort avant l'annonce).
    Après (apres=(h1, h2)) : le jour J de h1 à h2."""
    loc, jour, h = heure_locale(idx, tz)
    d = pd.to_datetime(sorted(dates))
    veille = d - pd.offsets.BDay(1)
    if apres:
        return np.isin(jour, d) & (h >= apres[0]) & (h < apres[1])
    return (np.isin(jour, d) & (h < h_annonce)) | (np.isin(jour, veille) & (h >= h_avant))


EVENEMENTS = {  # nom : (clé des dates, fuseau, heure veille, heure de l'annonce (heure locale), après (h1, h2), marchés)
    "Avant/après l'emploi US (NFP)": ("NFP", "America/New_York", 14, 8, (9, 16), ("US500", "US100", "GOLD", "EURUSD", "USDJPY")),
    "Avant/après l'inflation US (CPI)": ("CPI_US", "America/New_York", 14, 8, (9, 16), ("US500", "US100", "GOLD", "EURUSD", "USDJPY")),
    "Avant/après la BCE": ("ECB", "Europe/Berlin", 14, 14, (15, 18), ("DE40", "EU50", "FR40", "EURUSD")),
    "Avant/après la Banque d'Angleterre": ("BOE", "Europe/London", 12, 12, (13, 17), ("UK100", "GBPUSD")),
    "Avant/après la Banque du Japon": ("BOJ", "Asia/Tokyo", 9, 12, (13, 15), ("J225", "USDJPY")),
    "Avant/après la banque d'Australie": ("RBA", "Australia/Sydney", 14, 14, (15, 16), ("AU200", "AUDUSD")),
    "Après la Fed (FOMC)": ("FOMC", "America/New_York", 14, 14, (15, 16), ("US500", "US100", "GOLD", "EURUSD")),
}


def fam_evenement(nom):
    cle, tz, hv, ha, apres, _ = EVENEMENTS[nom]

    def f(df, cond, k):
        dates = DATES.get(cle, [])
        if not dates:
            return {}
        out = {}
        av = fenetre_evenement(df.index, dates, tz, hv, ha)
        ap = fenetre_evenement(df.index, dates, tz, hv, ha, apres)
        for s in (1, -1):
            sn = "achat" if s > 0 else "vente"
            if cle != "FOMC":
                out[f"{sn} avant"] = jouer(df, cond, av, s, k)
            out[f"{sn} après"] = jouer(df, cond, ap, s, k)
        return out
    return f


def fam_momentum_intraday(df, cond, k):
    """Gao, Han, Li, Zhou (2018) : le rendement de la nuit + 1re demi-heure prédit la dernière demi-heure.
    En 1 h : rendement de la veille 16 h au jour 10 h (New York) -> même sens de 15 h à 16 h (ou 14 h-16 h)."""
    loc, jour, h = heure_locale(df.index, "America/New_York")
    c = pd.Series(mid(df, "open"), index=df.index)  # ouverture de la bougie = prix à l'heure pile
    o16 = c.where(h == 16).ffill().shift(1)
    o10 = c.where(h == 10)
    r = (o10 / o16 - 1).groupby(jour).transform("max").values
    o15 = c.where(h == 15)
    r15 = (o15 / o16 - 1).groupby(jour).transform("max").values  # connu à 15 h pile (Baltussen et al. 2021)
    gros = np.abs(r15) > pd.Series(np.abs(r15)).rolling(1500, min_periods=200).median().shift(24).values
    out = {}
    ouvre = loc.dayofweek.values < 5
    for h1 in (14, 15):
        tenir = (h >= h1) & (h < 16) & ouvre
        out[f"{h1} h-16 h dans le sens du matin"] = jouer(df, cond, tenir, np.sign(r), k)
        out[f"{h1} h-16 h contre le matin"] = jouer(df, cond, tenir, -np.sign(r), k)
    t15 = (h == 15) & ouvre
    out["15 h-16 h dans le sens de la journée"] = jouer(df, cond, t15, np.sign(r15), k)
    out["15 h-16 h sens de la journée, gros jours seulement"] = jouer(df, cond, t15 & gros, np.sign(r15), k)
    return out


def fam_v_dollar(df, cond, k):
    """« V » du dollar autour des fixings (Krohn, Mueller, Whelan 2022) : le dollar monte avant le fixing de Tokyo
    (9 h 55) et de Londres (16 h), baisse après. Heures de New York."""
    loc, jour, h = heure_locale(df.index, "America/New_York")
    u = 1 if cond.get("epic", "").startswith("USD") else -1  # sens « dollar acheté »
    ouvre = loc.dayofweek.values < 5
    tokyo_av = (h >= 17) & (h < 20) & ouvre & ~((loc.dayofweek.values == 4) & (h >= 17))
    tokyo_ap = (h >= 21) & (h < 24) | (h < 2)
    out = {"dollar acheté 17 h-20 h (avant Tokyo)": jouer(df, cond, tokyo_av, u, k),
           "dollar vendu 21 h-2 h (après Tokyo)": jouer(df, cond, tokyo_ap & ouvre, -u, k),
           "dollar acheté 2 h-8 h (Europe)": jouer(df, cond, (h >= 2) & (h < 8) & ouvre, u, k),
           "dollar vendu 11 h-17 h (après Londres)": jouer(df, cond, (h >= 11) & (h < 17) & ouvre, -u, k)}
    return out


def fam_us_vers_asie(df, cond, k, us500=None):
    """Lien fin de séance US -> ouverture asiatique (COTSM, Griffith) : rendement US500 15 h-16 h (New York), même sens
    sur l'indice asiatique à l'ouverture de sa bourse, sortie 1 ou 2 h après."""
    if us500 is None:
        return {}
    loc, jour, h = heure_locale(us500.index, "America/New_York")
    o = pd.Series(mid(us500, "open"), index=us500.index)
    r = (o.where(h == 16) / o.shift(1).where(h == 16) - 1).dropna()  # bougie 15 h-16 h finie à 16 h
    sig = r.reindex(df.index, method="ffill", tolerance=pd.Timedelta(hours=12)).values
    hu = df.index.hour.values
    ouv = {"J225": 0, "HK50": 1, "AU200": 23}.get(cond.get("epic"), 0)
    out = {}
    for duree in (1, 2):
        tenir = np.isin(hu, [(ouv + x) % 24 for x in range(duree)]) & (df.index.dayofweek.values < 5)
        out[f"sens US, {duree} h après l'ouverture"] = jouer(df, cond, tenir, np.sign(sig), k)
        out[f"contre US, {duree} h après l'ouverture"] = jouer(df, cond, tenir, -np.sign(sig), k)
    return out


def fam_heures_btc(df, cond, k):
    """Saisonnalité horaire du Bitcoin (Quantpedia 2023) : achat 21 h-23 h UTC ; variantes."""
    h = df.index.hour.values
    out = {}
    for a, b in ((21, 23), (20, 23), (22, 0)):
        tenir = (h >= a) & (h < b) if b > a else (h >= a)
        out[f"achat {a} h-{b} h UTC"] = jouer(df, cond, tenir, 1, k)
    return out


def fam_btc_meneur(df, cond, k, btc=None):
    """Prévisibilité croisée des cryptos : rendement 1 h du BTC -> même sens sur l'ETH l'heure suivante."""
    if btc is None:
        return {}
    r = pd.Series(mid(btc), index=btc.index).pct_change().reindex(df.index).values
    out = {}
    for seuil in (0.0, 0.005, 0.01):
        s = np.where(np.abs(r) > seuil, np.sign(r), 0)
        tenir = np.r_[False, s[:-1] != 0]
        out[f"sens du BTC si |r| > {seuil:.1%}"] = jouer(df, cond, tenir, np.r_[0, s[:-1]], k)
    return out


def fam_gotobi(df, cond, k):
    """Gotobi (Ito-Yamada 2017, Bessho 2023) : les entreprises japonaises achètent des dollars les jours 5, 10, 15,
    20, 25 et fin de mois avant le fixing de 9 h 55 (Tokyo) : USD/JPY monte avant, baisse après."""
    loc, jour, h = heure_locale(df.index, "Asia/Tokyo")
    jours = pd.bdate_range("2016-01-01", "2027-12-31")
    cible = []
    for a in range(2016, 2028):
        for m in range(1, 13):
            fin_m = pd.Timestamp(a, m, 1) + pd.offsets.MonthEnd(0)
            for d in (5, 10, 15, 20, 25, fin_m.day):
                x = pd.Timestamp(a, m, min(d, fin_m.day))
                while x.dayofweek >= 5:
                    x -= pd.Timedelta(days=1)
                cible.append(x)
    g = np.isin(jour, pd.DatetimeIndex(cible))
    del jours
    out = {}
    for h0 in (3, 5, 7, 8):
        out[f"achat de {h0} h à 10 h (Tokyo)"] = jouer(df, cond, g & (h >= h0) & (h < 10), 1, k)
    out["vente de 10 h à 15 h (Tokyo)"] = jouer(df, cond, g & (h >= 10) & (h < 15), -1, k)
    out["achat 7-10 h puis vente 10-15 h"] = jouer(df, cond, g & (h >= 7) & (h < 15), np.where(h < 10, 1, -1), k)
    return out


def fam_sessions_or(df, cond, k):
    """Or : hausse pendant la séance asiatique, baisse pendant Londres/New York (« gold overnight » ; fixing de
    l'après-midi à Londres, Caminschi-Heaney 2014)."""
    h = df.index.hour.values
    jsem = df.index.dayofweek.values
    ouvre = jsem < 5
    out = {}
    for (a, b), s in (((23, 7), 1), ((0, 6), 1), ((21, 7), 1), ((13, 20), -1), ((14, 16), -1), ((7, 13), -1), ((13, 18), -1)):
        tenir = ((h >= a) | (h < b)) if a > b else ((h >= a) & (h < b))
        out[f"{'achat' if s > 0 else 'vente'} {a} h-{b} h UTC"] = jouer(df, cond, tenir & ouvre, s, k)
    return out


def fam_fixing_fin_mois_usd(df, cond, k, us500=None):
    """Fixing WM/Reuters de fin de mois (Melvin-Prins 2015) : si les actions US ont monté dans le mois, les gérants
    étrangers revendent des dollars pour se couvrir -> dollar plus faible le dernier jour, 8 h-16 h Londres."""
    loc, jour, h = heure_locale(df.index, "Europe/London")
    jours = pd.DatetimeIndex(sorted(set(jour)))
    _, fin = rang_dans_mois(jours)
    dernier = set(jours[fin == -1])
    est = np.isin(jour, list(dernier))
    out = {}
    if us500 is None:
        return out
    c = pd.Series(mid(us500), index=us500.index)
    debut_mois = c.groupby([c.index.year, c.index.month]).transform("first")
    mtd = (c / debut_mois - 1).reindex(df.index, method="ffill").values
    usd_base = 1 if cond.get("epic", "").startswith("USD") else -1  # USDJPY : dollar en premier
    for h0 in (8, 12):
        tenir = est & (h >= h0) & (h < 16)
        out[f"dollar contre les actions US, {h0} h-16 h"] = jouer(df, cond, tenir, -usd_base * np.sign(mtd) * -1, k)
        out[f"dollar avec les actions US, {h0} h-16 h"] = jouer(df, cond, tenir, usd_base * np.sign(mtd), k)
    return out


FAMILLES_HEURE = {nom: (fam_evenement(nom), v[5]) for nom, v in EVENEMENTS.items()}
FAMILLES_HEURE.update({
    "Momentum intraday US": (fam_momentum_intraday, US),
    "Gotobi (USD/JPY)": (fam_gotobi, ("USDJPY",)),
    "Séances de l'or": (fam_sessions_or, ("GOLD", "SILVER")),
    "Fixing de fin de mois (dollar)": (fam_fixing_fin_mois_usd, ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD")),
    "Fin de séance US -> ouverture Asie": (fam_us_vers_asie, ("J225", "AU200")),
    "Heures du Bitcoin": (fam_heures_btc, ("BTCUSD",)),
    "V du dollar autour des fixings": (fam_v_dollar, ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD")),
    "BTC meneur de l'ETH": (fam_btc_meneur, ("ETHUSD",)),
})


# =========================================================================== portefeuilles (plusieurs marchés)
def portefeuille_momentum(jour: dict, conds: dict, k=3.0, melange=None):
    """Momentum entre marchés (Asness-Moskowitz-Pedersen 2013) et tendance par marché (Moskowitz-Ooi-Pedersen 2012),
    en portefeuille de tous les marchés : chaque fin de mois, classement par rendement passé."""
    prix = pd.DataFrame({e: pd.Series(mid(d), index=jour_de_bourse(d.index)).groupby(level=0).last()
                         for e, d in jour.items()}).sort_index()
    prix = prix[prix.index.dayofweek < 5].ffill(limit=5)
    fins = prix.groupby([prix.index.year, prix.index.month]).tail(1).index
    out = {}
    for L in (21, 63, 126, 252):
        r = prix.loc[fins].pct_change(fill_method=None) if L == 21 else (prix / prix.shift(L) - 1).loc[fins]
        for mode, K in (("classement", 3), ("classement", 5), ("tendance", 0)):
            nom = f"{'meilleurs/pires ' + str(K) if mode == 'classement' else 'signe du rendement'} sur {L} j"
            pos = pd.DataFrame(0.0, index=r.index, columns=r.columns)
            for t, ligne in r.iterrows():
                v = ligne.dropna()
                if len(v) < 10:
                    continue
                if mode == "classement":
                    s = v.sort_values()
                    pos.loc[t, s.index[-K:]] = 1
                    pos.loc[t, s.index[:K]] = -1
                else:
                    pos.loc[t, v.index] = np.sign(v.values)
            trades = []
            for e, d in jour.items():
                j = jour_de_bourse(d.index)
                p = pos[e].reindex(j, method="ffill").shift(1).fillna(0).values  # connu à la fin du mois
                t_e = jouer(d, conds[e], p != 0, p, k)
                if len(t_e):
                    trades.append(t_e.assign(marche=e))
            out[nom] = pd.concat(trades, ignore_index=True) if trades else None
    return out


PAIRES = (("GOLD", "SILVER"), ("GOLD", "PLATINUM"), ("OIL_BRENT", "OIL_CRUDE"), ("US500", "US100"),
          ("US500", "RTY"), ("US30", "US500"), ("DE40", "EU50"), ("FR40", "EU50"), ("AUDUSD", "NZDUSD"),
          ("EURUSD", "GBPUSD"), ("EURJPY", "USDJPY"), ("BTCUSD", "ETHUSD"), ("US100", "NVDA"), ("MSFT", "AAPL"))


def paire(a: pd.DataFrame, b: pd.DataFrame, ca: dict, cb: dict, fen: int, seuil: float, dossier_stop=1.5):
    """Écart log(A) - beta log(B) (beta glissant 120 j, connu la veille). Entrée si z > seuil : vente A / achat B (et
    l'inverse) à l'ouverture suivante ; sortie quand z repasse 0, après 20 jours, ou stop si |z| > seuil + 1,5.
    1 R = perte au stop prévue (écart-type x 1,5). Frais : spread des deux jambes à l'entrée et à la sortie, frais de
    nuit des deux jambes chaque nuit."""
    ja, jb = jour_de_bourse(a.index), jour_de_bourse(b.index)
    A = pd.DataFrame({"m": mid(a), "o": mid(a, "open"), "sp": (a.close_ask - a.close_bid).values}, index=ja).groupby(level=0).last()
    B = pd.DataFrame({"m": mid(b), "o": mid(b, "open"), "sp": (b.close_ask - b.close_bid).values}, index=jb).groupby(level=0).last()
    x = A.join(B, lsuffix="a", rsuffix="b", how="inner")
    x = x[x.index.dayofweek < 5]
    la, lb = np.log(x.ma), np.log(x.mb)
    ra, rb = la.diff(), lb.diff()
    beta = (ra.rolling(120).cov(rb) / rb.rolling(120).var()).clip(0.2, 5)
    ec = la - beta * lb
    z = ((ec - ec.rolling(fen).mean()) / ec.rolling(fen).std())
    sd = ec.diff().rolling(fen).std() * np.sqrt(5)
    zv, bv, sdv = z.values, beta.values, sd.values
    oa, ob, spa, spb = x.oa.values, x.ob.values, x.spa.values, x.spb.values
    ma, mb = x.ma.values, x.mb.values
    trades, pos, i0 = [], 0, 0
    for i in range(1, len(x)):
        if pos:
            ecart_i = (np.log(oa[i]) - be * np.log(ob[i]))
            gain = (ecart_i - e0) * -pos  # pos = +1 : écart vendu (on parie qu'il baisse)
            jours = i - i0
            zz = zv[i - 1]
            fin = (pos > 0 and zz <= 0) or (pos < 0 and zz >= 0) or jours >= 20 or abs(zz) > seuil + 1.5
            if fin:
                frais = (spa[i] / ma[i] + be * spb[i] / mb[i]) / 2 * 2 + nuit_par_j * jours
                trades.append((d0, (gain - frais) / risque))
                pos = 0
        if not pos and zv[i - 1] == zv[i - 1] and abs(zv[i - 1]) > seuil and sdv[i - 1] == sdv[i - 1]:
            pos = 1 if zv[i - 1] > 0 else -1
            be = bv[i - 1]
            e0 = np.log(oa[i]) - be * np.log(ob[i])
            risque = 1.5 * sdv[i - 1]
            # pos +1 : vente A, achat B ; frais de nuit en % par jour (taux annuel/365 déjà en %/jour chez Capital.com)
            nuit_par_j = ((ca["nuit_vente"] if pos > 0 else ca["nuit_achat"]) + be * (cb["nuit_achat"] if pos > 0 else cb["nuit_vente"])) / 100 * 7 / 5
            d0, i0 = x.index[i], i
    return pd.DataFrame(trades, columns=["date", "R"])


def fam_paires(jour, conds, stress=False):
    out = {}
    for a, b in PAIRES:
        if a not in jour or b not in jour:
            continue
        da, db, ca, cb = jour[a], jour[b], conds[a], conds[b]
        if stress:
            da, ca = stresser(da, ca)
            db, cb = stresser(db, cb)
        res = {}
        for fen in (20, 60):
            for seuil in (1.5, 2.0, 2.5):
                res[f"z {fen} j, entrée {seuil:g}"] = paire(da, db, ca, cb, fen, seuil)
        out[f"{a}/{b}"] = res
    return out


# =========================================================================== sélection et verdict
def choisir(resultats: dict, mini=15) -> tuple:
    """Meilleur réglage sur 2017-2021 seulement (assez de trades), et voisins = les autres réglages."""
    ok = {r: resume(t) for r, t in resultats.items()}
    cand = [r for r, s in ok.items() if s["trades"][0] >= mini]
    if not cand:
        return None, ok
    best = max(cand, key=lambda r: ok[r]["entrainement"])
    return best, ok


def verdict(s: dict, voisins: list, stress: dict | None) -> str:
    jv = s["validation"] + s["test"]
    if s["entrainement"] <= 0:
        return "perd à l'entraînement"
    if sum(s["trades"][1:]) < 30:
        return "trop peu de trades"
    if s["validation"] <= 0 or s["test"] <= 0:
        return "échoue sur les années jamais vues"
    if voisins and np.mean([v["validation"] + v["test"] > 0 for v in voisins]) < 0.6:
        return "réglage isolé (voisins perdants)"
    if stress is not None and stress["validation"] + stress["test"] <= 0:
        return "ne tient pas avec frais x 1,5"
    return "passe" if jv > 0 else "échoue"


def evaluer_famille(nom, f, donnees, conds, marches, k_stops, extra=None):
    """Pour chaque marché : tous les réglages x stops, choix sur 2017-2021, verdict."""
    lignes = []
    for e in marches or donnees.keys():
        if e not in donnees:
            continue
        df, c = donnees[e], dict(conds[e], epic=e)
        res = {}
        for k in k_stops:
            try:
                r = f(df, c, k, **(extra or {})) if extra else f(df, c, k)
            except TypeError:
                r = f(df, c, k)
            res.update({f"{x}, stop {k:g} ATR": t for x, t in r.items()})
        if not res:
            continue
        best, ok = choisir(res)
        if best is None:
            lignes.append({"famille": nom, "marche": e, "reglage": None, "verdict": "trop peu de trades", "essais": len(res)})
            continue
        s = ok[best]
        voisins = [v for r, v in ok.items() if r != best]
        stress = None
        if s["entrainement"] > 0 and s["validation"] > 0 and s["test"] > 0:
            ds, cs = stresser(df, c)
            base, k = best.rsplit(", stop ", 1)
            k = float(k.split()[0])
            try:
                r2 = f(ds, cs, k, **(extra or {})) if extra else f(ds, cs, k)
            except TypeError:
                r2 = f(ds, cs, k)
            stress = resume(r2.get(base))
        v = verdict(s, voisins, stress)
        lignes.append({"famille": nom, "marche": e, "reglage": best, "verdict": v, "essais": len(res), **s,
                       "stress_jamais_vu": None if stress is None else round(stress["validation"] + stress["test"], 1)})
    return lignes


TACHES = []


def _tache(i):
    try:
        return evaluer_famille(*TACHES[i])
    except Exception as e:  # une idée qui plante sur un marché ne bloque pas les autres
        print(f"{TACHES[i][0]} {TACHES[i][4]} : erreur {str(e)[:100]}", flush=True)
        return []


def p_value(t: float) -> float:
    return 1 - NORM.cdf(t)


def principal(dossier: Path, hasard_graines=2):
    global DATES
    f_dates = Path(__file__).resolve().parent / "dates_annonces.json"
    DATES = json.loads(f_dates.read_text()) if f_dates.exists() else {}
    DATES["FOMC"] = FOMC
    petits = petits_connus(dossier)
    jour = {e: lire(dossier, e, "DAY") for e in JOUR + [p for p in petits if p not in JOUR]}
    jour = {e: d for e, d in jour.items() if d is not None and len(d) > 500}
    heure = {e: lire(dossier, e, "HOUR") for e in HORAIRE}
    heure = {e: d for e, d in heure.items() if d is not None and len(d) > 5000}
    cj = {e: cond_de(dossier, e, d) for e, d in jour.items()}
    ch = {e: cond_de(dossier, e, d) for e, d in heure.items()}
    res = {"donnees": {"jour": {e: f"{d.index[0]:%m/%Y}-{d.index[-1]:%m/%Y}" for e, d in jour.items()},
                       "heure": {e: f"{d.index[0]:%m/%Y}-{d.index[-1]:%m/%Y}" for e, d in heure.items()},
                       "dates_annonces": {k: len(v) for k, v in DATES.items()},
                       "exemple_heure_bougie_jour": {e: str(d.index[-1]) for e, d in list(jour.items())[:5]}}}

    def tout(jour, heure, cj, ch):
        global TACHES
        TACHES = []
        for nom, (f, m) in FAMILLES_JOUR.items():
            for e in (jour.keys() if TOUS_LES_MARCHES or not m else m):
                if e not in jour:
                    continue
                if f is fam_jour_semaine:
                    g = (lambda df, c, k, cr=e in ("BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "LTCUSD"): fam_jour_semaine(df, c, k, cr))
                else:
                    g = f
                TACHES.append((nom, g, jour, cj, [e], (1.5, 3.0)))
        for nom, (f, m) in FAMILLES_HEURE.items():
            if f in (fam_fixing_fin_mois_usd, fam_us_vers_asie):
                us = heure.get("US500")
                g = (lambda df, c, k, us=us, f=f: f(df, c, k, us))
            elif f is fam_btc_meneur:
                g = (lambda df, c, k, b=heure.get("BTCUSD"): fam_btc_meneur(df, c, k, b))
            else:
                g = f
            for e in (heure.keys() if TOUS_LES_MARCHES or not m else m):
                if e in heure and not (f is fam_btc_meneur and e == "BTCUSD") and not (f is fam_us_vers_asie and e == "US500"):
                    TACHES.append((nom, g, heure, ch, [e], (1.0, 2.0)))
        import multiprocessing as mp
        with mp.get_context("fork").Pool() as pool:
            morceaux = pool.map(_tache, range(len(TACHES)), chunksize=4)
        lignes = [x for m in morceaux for x in m]
        print(f"{len(TACHES)} couples idée x marché : fait", flush=True)
        # portefeuilles momentum : un seul « marché » (le portefeuille)
        pm = portefeuille_momentum(jour, cj)
        best, ok = choisir(pm, mini=30)
        if best:
            st = {k: v for k, v in pm.items()}
            jd = {e: stresser(d, cj[e]) for e, d in jour.items()}
            pms = portefeuille_momentum({e: x[0] for e, x in jd.items()}, {e: x[1] for e, x in jd.items()}) \
                if ok[best]["validation"] > 0 and ok[best]["test"] > 0 else None
            stress = resume(pms[best]) if pms else None
            lignes.append({"famille": "Momentum entre marchés (portefeuille 41 marchés)", "marche": "portefeuille",
                           "reglage": best, "verdict": verdict(ok[best], [v for r, v in ok.items() if r != best], stress),
                           "essais": len(pm), **ok[best],
                           "stress_jamais_vu": None if stress is None else round(stress["validation"] + stress["test"], 1),
                           "tous_reglages": ok})
            del st
        print("momentum : fait", flush=True)
        pa, pas_ = fam_paires(jour, cj), None
        for nom_p, r in pa.items():
            best, ok = choisir(r)
            if not best:
                lignes.append({"famille": "Paires (retour à la moyenne de l'écart)", "marche": nom_p, "reglage": None,
                               "verdict": "trop peu de trades", "essais": len(r)})
                continue
            s = ok[best]
            stress = None
            if s["entrainement"] > 0 and s["validation"] > 0 and s["test"] > 0:
                pas_ = pas_ or fam_paires(jour, cj, stress=True)
                stress = resume(pas_[nom_p][best])
            lignes.append({"famille": "Paires (retour à la moyenne de l'écart)", "marche": nom_p, "reglage": best,
                           "verdict": verdict(s, [v for k, v in ok.items() if k != best], stress), "essais": len(r), **s,
                           "stress_jamais_vu": None if stress is None else round(stress["validation"] + stress["test"], 1)})
        print("paires : fait", flush=True)
        return lignes

    lignes = tout(jour, heure, cj, ch)
    n_choix = sum(1 for x in lignes if x.get("reglage"))
    n_essais = sum(x.get("essais", 0) for x in lignes)
    t_bonf = NORM.inv_cdf(1 - 0.05 / max(n_choix, 1))
    for x in lignes:
        if x["verdict"] == "passe":
            x["p_jamais_vu"] = round(p_value(x["t_jv"]), 4)
            x["verdict"] = "SOLIDE" if x["t_jv"] >= t_bonf else ("prometteur" if x["t_jv"] >= 1.645 else "passe, mais pourrait être le hasard")
    res["essais"] = {"reglages_testes": n_essais, "couples_famille_marche": n_choix,
                     "t_minimum_bonferroni": round(t_bonf, 2)}
    res["resultats"] = lignes
    res["bilan"] = {v: sum(1 for x in lignes if x["verdict"] == v) for v in sorted({x["verdict"] for x in lignes})}
    for x in lignes:
        x["categorie"] = petits.get(x["marche"], "grands marchés")
    res["petits_marches"] = {
        cat: {"marches_trouves": [e for e, c in petits.items() if c == cat and e in jour],
              "spread_median_pct": {e: round(float(((jour[e].close_ask - jour[e].close_bid) / jour[e].close_bid).median() * 100), 3)
                                    for e, c in petits.items() if c == cat and e in jour},
              "verdicts": {v: sum(1 for x in lignes if x["categorie"] == cat and x["verdict"] == v)
                           for v in {x["verdict"] for x in lignes if x["categorie"] == cat}},
              "meilleurs": sorted([(x["famille"], x["marche"], x["reglage"], x["validation"], x["test"], x["t_jv"], x["verdict"])
                                   for x in lignes if x["categorie"] == cat and x.get("reglage")], key=lambda y: -y[5])[:8]}
        for cat in PETITS}
    # tableau demandé par Mathis : idée x meilleur marché (choisi sur 2017-2021) x résultat jamais vu
    tab = {}
    for x in lignes:
        if not x.get("reglage") or x["entrainement"] <= 0:
            continue
        b = tab.get(x["famille"])
        if b is None or x["entrainement"] > b["entrainement"]:
            tab[x["famille"]] = x
    res["tableau_idee_meilleur_marche"] = [
        {"idee": k, "meilleur_marche_2017_2021": v["marche"], "reglage": v["reglage"], "R_2017_21": v["entrainement"],
         "R_2022_mi24": v["validation"], "R_mi24_26": v["test"], "t": v["t_jv"], "verdict": v["verdict"],
         "marches_testes": sum(1 for y in lignes if y["famille"] == k)} for k, v in tab.items()]

    # contrôle : prix mélangés (aucun effet possible) -> combien « passent » par hasard ?
    hz = []
    for g in range(hasard_graines):
        jm = {e: melanger(d, 100 * g + i) for i, (e, d) in enumerate(jour.items())}
        hm = {e: melanger(d, 100 * g + 50 + i) for i, (e, d) in enumerate(heure.items())}
        lh = tout(jm, hm, cj, ch)
        passe = [x for x in lh if x["verdict"] == "passe"]
        hz.append({"graine": g, "couples": sum(1 for x in lh if x.get("reglage")), "passent_tout_sauf_bonferroni": len(passe),
                   "dont_t_sup_1_645": sum(1 for x in passe if x["t_jv"] >= 1.645),
                   "dont_bonferroni": sum(1 for x in passe if x["t_jv"] >= t_bonf),
                   "exemples": [(x["famille"], x["marche"], x["reglage"], x["t_jv"]) for x in passe][:8]})
        print(f"hasard {g} : {hz[-1]['passent_tout_sauf_bonferroni']} passent", flush=True)
    res["controle_prix_melanges"] = hz
    Path(__file__).resolve().parent.joinpath("resultats_web_large.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False, default=str))
    print(json.dumps({k: res[k] for k in ("donnees", "essais", "bilan", "controle_prix_melanges")}, ensure_ascii=False, indent=1))
    for x in sorted(lignes, key=lambda x: -x.get("t_jv", -9)):
        if x.get("reglage"):
            print(f"{x['verdict'][:22]:22s} {x['famille'][:34]:34s} {x['marche']:12s} {str(x['reglage'])[:44]:44s} "
                  f"{x['entrainement']:7.1f} {x['validation']:7.1f} {x['test']:7.1f} t={x['t_jv']:5.2f} {x['trades']}")


if __name__ == "__main__":
    if sys.argv[1] == "telecharger":
        telecharger(Path(sys.argv[2]))
    else:
        principal(Path(sys.argv[1]))

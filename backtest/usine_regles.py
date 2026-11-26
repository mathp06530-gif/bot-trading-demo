"""Règles de l'USINE À STRATÉGIES (26/11/2026) : les briques que l'usine (backtest/usine.py) assemble.
Si une stratégie de l'usine passe un jour en démo, son module dans bot/ doit réutiliser CES fonctions. Une stratégie = une combinaison :

  déclencheur (famille + réglages) × filtre × sens × stop (en ATR) × objectif (en R) × suiveur × durée max.

Tout est calculé sur des bougies TERMINÉES, en prix milieu ((bid + ask) / 2). Le signal de la bougie i est joué à
l'ouverture de la bougie i + 1. On n'entre que sur un signal NOUVEAU (changement d'état), jamais deux fois le même.
"""
import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- grilles de réglages
# famille -> (type, liste des réglages, forme de la grille pour les « voisins »)
FAMILLES = {
    "don": ("tendance", [(n,) for n in (10, 20, 40, 55, 100)], (5,)),                       # cassure de canal (Donchian)
    "ema": ("tendance", [(5, 20), (10, 30), (20, 50), (20, 100), (50, 200)], (5,)),          # croisement de moyennes
    "st": ("tendance", [(n, m) for n in (7, 10, 14) for m in (2.0, 3.0, 4.0)], (3, 3)),      # Supertrend
    "roc": ("tendance", [(n,) for n in (20, 50, 100, 200)], (4,)),                           # élan (variation sur N)
    "bb": ("tendance", [(n, k) for n in (20, 50) for k in (1.5, 2.0, 2.5)], (2, 3)),         # sortie des bandes de Bollinger
    "macd": ("tendance", [(12, 26, 9), (24, 52, 18)], (2,)),                                 # MACD
    "rsi": ("retour", [(n, lo) for n in (2, 3, 5, 14) for lo in (10, 20, 30)], (4, 3)),      # RSI extrême -> retour à 50
    "bbr": ("retour", [(n, k) for n in (20, 50) for k in (2.0, 2.5)], (2, 2)),               # hors des bandes -> retour au milieu
    "ibs": ("retour", [(x,) for x in (0.1, 0.2, 0.3)], (3,)),                                # clôture tout en bas de la bougie
    "bas": ("retour", [(n,) for n in (5, 10, 20)], (3,)),                                    # plus bas de N bougies -> rebond
}
FILTRES = ["aucun", "t200", "adx25", "adx20m", "volh", "volb"]
SENS = ["les2", "achat", "vente"]
STOPS = [1.5, 2.5, 4.0]          # stop garanti à k × ATR 14
OBJECTIFS = [0, 1.0, 2.0, 3.0]   # objectif à x R (0 = aucun)
SUIVEURS = [0, 3.0]              # stop suiveur à k × ATR derrière le meilleur prix (0 = aucun)
DUREES = [0, 20]                 # sortie forcée après N bougies (0 = aucune)
UNITES = ["HOUR_4", "DAY"]

NOMS_FAMILLES = {"don": "Cassure du canal", "ema": "Croisement de moyennes", "st": "Supertrend", "roc": "Élan",
                 "bb": "Sortie des bandes de Bollinger", "macd": "MACD", "rsi": "RSI extrême", "bbr": "Retour dans les bandes",
                 "ibs": "Clôture en bas de bougie", "bas": "Rebond sur plus bas"}
NOMS_FILTRES = {"aucun": "", "t200": "dans le sens de la moyenne 200", "adx25": "seulement si tendance forte (ADX > 25)",
                "adx20m": "seulement si marché calme (ADX < 20)", "volh": "seulement si la volatilité monte",
                "volb": "seulement si la volatilité baisse"}


# --------------------------------------------------------------------------- indicateurs
def milieu(df: pd.DataFrame) -> pd.DataFrame:
    if "close_bid" not in df:
        return df[["open", "high", "low", "close"]].astype(float)
    return pd.DataFrame({k: (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2 for k in ("open", "high", "low", "close")}, index=df.index)


def _tr(m):
    pc = m.close.shift()
    return pd.concat([m.high - m.low, (m.high - pc).abs(), (m.low - pc).abs()], axis=1).max(axis=1)


def _wilder(x, n):
    return x.ewm(alpha=1 / n, adjust=False).mean()


def _rsi(c, n):
    d = c.diff().fillna(0.0)
    g, p = _wilder(d.clip(lower=0), n), _wilder((-d).clip(lower=0), n)
    return (100 - 100 / (1 + g / p.replace(0, np.nan))).fillna(50)


def _adx(m, n=14):
    up, down = m.high.diff(), -m.low.diff()
    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=m.index)
    ndm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=m.index)
    a = _wilder(_tr(m), n)
    pdi, ndi = 100 * _wilder(pdm, n) / a, 100 * _wilder(ndm, n) / a
    return _wilder(100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan), n).fillna(0)


def _supertrend(m, n, mult):
    h, l, c = m.high.values, m.low.values, m.close.values
    a = _tr(m).rolling(n).mean().bfill().values
    hl2 = (h + l) / 2
    up, dn = hl2 - mult * a, hl2 + mult * a
    d = np.ones(len(c), dtype=int)
    for i in range(1, len(c)):
        if c[i - 1] > up[i - 1]:
            up[i] = max(up[i], up[i - 1])
        if c[i - 1] < dn[i - 1]:
            dn[i] = min(dn[i], dn[i - 1])
        d[i] = 1 if (d[i - 1] == -1 and c[i] > dn[i - 1]) else -1 if (d[i - 1] == 1 and c[i] < up[i - 1]) else d[i - 1]
    return d


def _par_evenements(entre_achat, sort_achat, entre_vente, sort_vente):
    """État +1 / -1 / 0 tenu entre un événement d'entrée et l'événement de sortie correspondant."""
    ea, sa, ev, sv = (np.asarray(x, dtype=bool) for x in (entre_achat, sort_achat, entre_vente, sort_vente))
    etat = np.zeros(len(ea), dtype=np.int8)
    e = 0
    for i in range(len(ea)):
        if e == 1 and sa[i]:
            e = 0
        elif e == -1 and sv[i]:
            e = 0
        if ea[i] and not ev[i]:
            e = 1
        elif ev[i] and not ea[i]:
            e = -1
        etat[i] = e
    return etat


class Indicateurs:
    """Cache des indicateurs d'une série de bougies (une seule fois par marché et unité de temps)."""

    def __init__(self, df: pd.DataFrame):
        self.m = m = milieu(df)
        self.c = m.close
        self.atr = _wilder(_tr(m), 14)
        self.atr100 = _wilder(_tr(m), 100)
        self.sma200 = m.close.rolling(200).mean()
        self.adx = _adx(m)
        self._etats = {}

    def etat(self, famille: str, p: tuple) -> np.ndarray:
        cle = (famille, p)
        if cle not in self._etats:
            self._etats[cle] = self._calculer(famille, p)
        return self._etats[cle]

    def _calculer(self, f, p):
        m, c = self.m, self.c
        if f == "don":
            n = p[0]
            haut, bas = m.high.rolling(n).max().shift(), m.low.rolling(n).min().shift()
            h2, b2 = m.high.rolling(max(2, n // 2)).max().shift(), m.low.rolling(max(2, n // 2)).min().shift()
            return _par_evenements(c > haut, c < b2, c < bas, c > h2)
        if f == "ema":
            a, b = (c.ewm(span=x, adjust=False).mean() for x in p)
            return np.sign(a - b).fillna(0).astype(np.int8).values
        if f == "st":
            return _supertrend(m, p[0], p[1]).astype(np.int8)
        if f == "roc":
            return np.sign(c / c.shift(p[0]) - 1).fillna(0).astype(np.int8).values
        if f in ("bb", "bbr"):
            n, k = p
            mil, et = c.rolling(n).mean(), c.rolling(n).std()
            haut, bas = mil + k * et, mil - k * et
            if f == "bb":
                return _par_evenements(c > haut, c < mil, c < bas, c > mil)
            return _par_evenements(c < bas, c > mil, c > haut, c < mil)
        if f == "macd":
            a, b, s = p
            ligne = c.ewm(span=a, adjust=False).mean() - c.ewm(span=b, adjust=False).mean()
            return np.sign(ligne - ligne.ewm(span=s, adjust=False).mean()).fillna(0).astype(np.int8).values
        if f == "rsi":
            n, lo = p
            r = _rsi(c, n)
            return _par_evenements(r < lo, r > 50, r > 100 - lo, r < 50)
        if f == "ibs":
            x = p[0]
            ibs = ((c - m.low) / (m.high - m.low).replace(0, np.nan)).fillna(0.5)
            return _par_evenements(ibs < x, ibs > 1 - x, ibs > 1 - x, ibs < x)
        if f == "bas":
            n = p[0]
            return _par_evenements(c <= c.rolling(n).min(), c > m.high.shift(), c >= c.rolling(n).max(), c < m.low.shift())
        raise ValueError(f)

    def filtre(self, nom: str, etat: np.ndarray) -> np.ndarray:
        """Entrée permise ? (tableau de booléens, même longueur)."""
        if nom == "aucun":
            return np.ones(len(etat), dtype=bool)
        if nom == "t200":
            s = self.sma200.values
            c = self.c.values
            return ((etat > 0) & (c > s)) | ((etat < 0) & (c < s))
        if nom == "adx25":
            return self.adx.values > 25
        if nom == "adx20m":
            return self.adx.values < 20
        r = (self.atr / self.atr100).values
        return r > 1 if nom == "volh" else r < 1


def preparer(ind: Indicateurs, spec: dict):
    """Pour une stratégie : voulu (sens à tenir), ok (entrée permise sur cette bougie), dstop, dobj (prix ou NaN).
    Une entrée n'est permise que sur une bougie où l'état vient de changer (signal nouveau)."""
    etat = ind.etat(spec["famille"], tuple(spec["p"])).copy()
    if spec["sens"] == "achat":
        etat[etat < 0] = 0
    elif spec["sens"] == "vente":
        etat[etat > 0] = 0
    nouveau = np.r_[etat[0] != 0, etat[1:] != etat[:-1]] & (etat != 0)
    ok = nouveau & ind.filtre(spec["filtre"], etat)
    ok[:200] = False  # temps de chauffe des indicateurs (moyenne 200)
    a = ind.atr.values
    dstop = spec["stop"] * a
    dobj = spec["objectif"] * dstop if spec["objectif"] else np.full(len(a), np.nan)
    return etat, ok, dstop, dobj


def decrire(spec: dict) -> str:
    """Phrase lisible pour l'appli et le Journal."""
    nom = NOMS_FAMILLES[spec["famille"]] + " " + "/".join(f"{x:g}" for x in spec["p"])
    sens = {"les2": "achat et vente", "achat": "achat seulement", "vente": "vente seulement"}[spec["sens"]]
    bouts = [nom, sens]
    if NOMS_FILTRES[spec["filtre"]]:
        bouts.append(NOMS_FILTRES[spec["filtre"]])
    bouts.append(f"stop garanti {spec['stop']:g} ATR")
    if spec["objectif"]:
        bouts.append(f"objectif {spec['objectif']:g} R")
    if spec["suiveur"]:
        bouts.append(f"suiveur {spec['suiveur']:g} ATR")
    if spec["duree"]:
        bouts.append(f"{spec['duree']} bougies max")
    return ", ".join(bouts)

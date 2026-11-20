"""STRATÉGIE « IA 4 h » (apprentissage automatique), or + argent. EXPÉRIENCE demandée par Mathis.

Un modèle simple (régression logistique) apprend, sur les ~800 dernières bougies de 4 h terminées,
si la bougie suivante a plus de chances de monter ou de descendre, à partir de 17 indices
(variations passées, volatilité, RSI, ADX, écart aux moyennes EMA 20/50/200, heure, jour, spread).
Il est réentraîné à chaque tour, uniquement sur le passé.

Test honnête du 20/11/2026 (2 ans, réentraînement mensuel, spread compris) : 51 à 52,5 % de bonnes
prédictions, à peine mieux qu'une pièce. Sur 16 essais (BTC, or, argent, Nasdaq, 1 h / 4 h), 14 perdent.
Seuls l'or (+525 €) et l'argent (+1 923 €) en 4 h gagnent, probablement par chance.
À considérer comme un test, PAS comme une stratégie fiable.

Règles : modèle > 50 % hausse = ACHAT, sinon VENTE ; on se retourne quand la prévision change.
Stop GARANTI à 2 × ATR. Taille : RISQUE_IA_PCT (0,25 %) du capital perdu au maximum si le stop est touché.
Les ordres passent par bot/cassure.py:tour_cassure (mêmes vérifications et garde-fous).
"""
import os

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from bot.strategie import atr, ema, milieu

LISTE = [m.strip() for m in os.getenv("IA_MARCHES", "GOLD,SILVER").split(",") if m.strip()]
RISQUE_IA_PCT = float(os.getenv("RISQUE_IA_PCT", "0.25"))
ACTIVE_PAR_DEFAUT = os.getenv("IA_4H", "non").strip().lower() in ("oui", "1", "true", "on")
STOP_ATR = 2.0
NOM = f"IA (régression logistique) sur bougies 4 h, réentraînée à chaque tour, stop garanti {STOP_ATR:g} ATR"


def _rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    p = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + g / p)


def _adx(m, n=14):
    up, down = m.high.diff(), -m.low.diff()
    pdm = np.where((up > down) & (up > 0), up, 0.0)
    ndm = np.where((down > up) & (down > 0), down, 0.0)
    a = atr(m, n)
    pdi = 100 * pd.Series(pdm, index=m.index).ewm(alpha=1 / n, adjust=False).mean() / a
    ndi = 100 * pd.Series(ndm, index=m.index).ewm(alpha=1 / n, adjust=False).mean() / a
    return (100 * (pdi - ndi).abs() / (pdi + ndi)).ewm(alpha=1 / n, adjust=False).mean()


def indices(df: pd.DataFrame):
    """Les 17 indices donnés au modèle + la réponse attendue (1 = la bougie suivante monte)."""
    m = milieu(df)
    c, a = m.close, atr(m)
    r = np.log(c).diff()
    X = pd.DataFrame(index=df.index)
    for k in (1, 2, 4, 8, 24, 72):
        X[f"r{k}"] = np.log(c / c.shift(k))
    X["vol24"] = r.rolling(24).std()
    X["vol_ratio"] = r.rolling(6).std() / X.vol24
    X["rsi"] = _rsi(c)
    X["adx"] = _adx(m)
    for n in (20, 50, 200):
        X[f"d_ema{n}"] = (c - ema(c, n)) / a
    X["range"] = (m.high - m.low) / a
    X["pos_range"] = (c - m.low) / (m.high - m.low + 1e-12)
    X["heure"] = df.index.hour
    X["jour"] = df.index.dayofweek
    X["spread"] = (df.close_ask - df.close_bid) / a
    y = (c.shift(-1) > c).astype(int)
    return X, y, m, a


def probabilite_hausse(df: pd.DataFrame, mini=500) -> float | None:
    """Entraîne sur toutes les bougies terminées dont on connaît la suite, prédit la dernière."""
    X, y, _, _ = indices(df)
    ok = X.notna().all(axis=1)
    entr = ok & (np.arange(len(X)) < len(X) - 1)
    if entr.sum() < mini or not ok.iloc[-1]:
        return None
    mdl = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500))
    mdl.fit(X[entr].values, y[entr].values)
    return float(mdl.predict_proba(X.iloc[[-1]].values)[0, 1])


def signaux_ia(df: pd.DataFrame) -> pd.DataFrame:
    """Même format que bot/cassure.py:signaux_cassure. Seule la DERNIÈRE bougie porte la prévision :
    une nouvelle prévision à chaque bougie, donc on peut ré-entrer après un stop (comme dans le test)."""
    _, _, m, a = indices(df)
    p = probabilite_hausse(df)
    cible = np.zeros(len(df), dtype=int)
    if p is not None:
        cible[-1] = 1 if p > 0.5 else -1
    out = pd.DataFrame({"cible": cible, "stop": a * STOP_ATR, "atr": a,
                        "haut": m.high.rolling(20).max().shift(), "bas": m.low.rolling(20).min().shift(),
                        "ema": ema(m.close, 200), "cloture": m.close}, index=df.index)
    out.attrs["proba"] = p
    return out

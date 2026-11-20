"""STRATÉGIE « TENDANCE 1 MOIS, 12 MARCHÉS » (momentum), un sous-bot par marché, décision une fois par jour.

Testée le 20/11/2026 sur 2 ans de prix Capital.com (bougies jour), avec le spread et les frais de nuit.
Réglage choisi sur la 1re année (30 jours = le meilleur), vérifié sur la 2e, sur les 11 marchés
(sans le BTC, déjà tradé par les stratégies 4 h et rapide : le compte refuse deux sens opposés) :
+2 403 € puis +1 054 € sur 21 000 € à 0,4 % de risque par marché, pire baisse -7 %, ~20 trades/mois.
Les réglages voisins (21 à 42 jours) gagnent aussi les deux années ; 10 jours et 3-12 mois perdent l'année 2.
C'est une EXPÉRIENCE en démo sur 2 ans de données seulement, pas une promesse.

Règles, sur les bougies JOUR terminées (prix milieu) :
  ACHAT  si le prix de clôture est plus haut qu'il y a LOOKBACK (30) bougies, VENTE s'il est plus bas.
  On se retourne quand le sens change. Après un stop, on reprend la position le lendemain.
  STOP   : stop GARANTI à 3 × ATR 20 jours (≈ taille selon la volatilité : même risque sur chaque marché).
  TAILLE : RISQUE_TENDANCE_MOIS_PCT (0,4 %) du capital perdu au maximum si le stop est touché.
  REFUS  : mêmes vérifications que la cassure (bot/cassure.py), dont : pas d'ordre opposé à la
           position d'une autre stratégie sur le même marché (compte sans couverture).
"""
import os

import numpy as np
import pandas as pd

from bot.strategie import atr, milieu

LISTE = [m.strip() for m in os.getenv(
    "TENDANCE_MOIS_MARCHES",
    "GOLD,SILVER,ETHUSD,US100,US500,DE40,OIL_CRUDE,EURUSD,GBPUSD,AUDUSD,USDJPY").split(",") if m.strip()]
RISQUE_TENDANCE_MOIS_PCT = float(os.getenv("RISQUE_TENDANCE_MOIS_PCT", "0.4"))
ACTIVE_PAR_DEFAUT = os.getenv("TENDANCE_MOIS", "non").strip().lower() in ("oui", "1", "true", "on")
LOOKBACK, STOP_ATR, N_ATR = 30, 3.0, 20
UNITE = "DAY"
NOM = f"Tendance {LOOKBACK} jours sur {len(LISTE)} marchés, décision chaque jour, stop garanti {STOP_ATR:g} ATR"


def signaux_tendance(df: pd.DataFrame, lookback: int = LOOKBACK) -> pd.DataFrame:
    """Même format que bot/cassure.py:signaux_cassure. Seule la DERNIÈRE bougie porte la décision du jour
    (comme le backtest : toujours en position, reprise le lendemain d'un stop)."""
    m = milieu(df)
    c, a = m.close, atr(m, N_ATR)
    mom = c / c.shift(lookback) - 1
    cible = np.zeros(len(df), dtype=int)
    if len(df) > lookback and mom.iloc[-1] == mom.iloc[-1] and a.iloc[-1] == a.iloc[-1]:
        cible[-1] = 1 if mom.iloc[-1] > 0 else -1
    out = pd.DataFrame({"cible": cible, "stop": a * STOP_ATR, "atr": a,
                        "haut": m.high.rolling(20).max().shift(), "bas": m.low.rolling(20).min().shift(),
                        "ema": c.rolling(lookback).mean(), "cloture": c}, index=df.index)
    pct = None if mom.iloc[-1] != mom.iloc[-1] else round(float(mom.iloc[-1]) * 100, 2)
    sens = "plus haut" if (pct or 0) > 0 else "plus bas"
    out.attrs.update({"nom": "Tendance 1 mois", "momentum_pct": pct,
                      "sortie": f"La tendance sur {lookback} jours s'est retournée",
                      "pourquoi": f"Tendance 1 mois : le prix est {sens} qu'il y a {lookback} jours ({pct:+.1f} %)"
                      if pct is not None else "Tendance 1 mois"})
    return out

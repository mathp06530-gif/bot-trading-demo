"""« DEUX CERVEAUX PAR MARCHÉ » (idée de Mathis, 25/11/2026).

Le 1er cerveau est la stratégie du marché (Cassure ou Tendance). Le 2e cerveau regarde le même graphique
autrement et donne son avis : +1 (achat), -1 (vente) ou 0 (pas d'avis). Chaque fonction renvoie un avis
par bougie de 4 h TERMINÉE, calculé uniquement avec le passé (le backtest et le bot utilisent ce fichier).

  avis_note      : note technique de ~20 indicateurs (bot/analyse.py), > +0,1 achat, < -0,1 vente.
  avis_structure : structure de marché (vidéo) : les 2 derniers sommets ET creux montent / descendent.
  avis_1h        : tendance 1 h (EMA 20 au-dessus de l'EMA 50 et prix au-dessus de l'EMA 20, ou l'inverse).
"""
import numpy as np
import pandas as pd

from bot.analyse import note_technique
from bot.strategie import ema, milieu

SEUIL_NOTE = 0.1
COTE_SOMMET = 2  # un sommet = plus haut que les 2 bougies avant et les 2 après (connu 2 bougies plus tard)


def avis_note(df: pd.DataFrame, seuil: float = SEUIL_NOTE) -> np.ndarray:
    note = note_technique(milieu(df)).note.values
    return np.where(note > seuil, 1, np.where(note < -seuil, -1, 0))


def avis_structure(df: pd.DataFrame, k: int = COTE_SOMMET) -> np.ndarray:
    m = milieu(df)
    h, l = m.high.values, m.low.values
    n = len(h)
    avis = np.zeros(n, dtype=int)
    sommets, creux = [], []
    for i in range(n):
        j = i - k  # bougie candidate, confirmée maintenant
        if j >= k:
            fen_h, fen_l = h[j - k:i + 1], l[j - k:i + 1]
            if h[j] == fen_h.max() and (fen_h == h[j]).sum() == 1:
                sommets.append(h[j])
            if l[j] == fen_l.min() and (fen_l == l[j]).sum() == 1:
                creux.append(l[j])
        if len(sommets) >= 2 and len(creux) >= 2:
            if sommets[-1] > sommets[-2] and creux[-1] > creux[-2]:
                avis[i] = 1
            elif sommets[-1] < sommets[-2] and creux[-1] < creux[-2]:
                avis[i] = -1
    return avis


def avis_1h(df4: pd.DataFrame, df1: pd.DataFrame) -> np.ndarray:
    if df1 is None or len(df1) < 60:
        return np.zeros(len(df4), dtype=int)
    c = milieu(df1).close
    r, s = ema(c, 20), ema(c, 50)
    a1 = np.where((r > s) & (c > r), 1, np.where((r < s) & (c < r), -1, 0))
    fin4 = df4.index + pd.Timedelta(hours=4)
    fin1 = df1.index + pd.Timedelta(hours=1)
    pos = np.searchsorted(fin1.values, fin4.values, side="right") - 1  # dernière bougie 1 h terminée
    return np.where(pos >= 0, a1[np.maximum(pos, 0)], 0)


NOMS = {1: "achat", -1: "vente", 0: "pas d'avis"}


def conseil(df4: pd.DataFrame, df1: pd.DataFrame | None) -> np.ndarray:
    """Le 2e cerveau = vote des 3 avis (note, structure, 1 h) : il faut au moins 2 avis dans le même sens."""
    total = avis_note(df4) + avis_structure(df4) + avis_1h(df4, df1)
    return np.where(np.abs(total) >= 2, np.sign(total), 0).astype(int)


def avis_detail(df4: pd.DataFrame, df1: pd.DataFrame | None) -> dict:
    """Avis de la DERNIÈRE bougie terminée, pour le Journal et l'application."""
    n, s, h = int(avis_note(df4)[-1]), int(avis_structure(df4)[-1]), int(avis_1h(df4, df1)[-1])
    total = n + s + h
    c = int(np.sign(total)) if abs(total) >= 2 else 0
    texte = (f"note des indicateurs : {NOMS[n]}, structure sommets/creux : {NOMS[s]}, tendance 1 h : {NOMS[h]}"
             f" -> 2e cerveau : {NOMS[c]}")
    return {"conseil": c, "note": n, "structure": s, "1h": h, "texte": texte}

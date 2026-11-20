"""« ANALYSER D'ABORD » (demande de Mathis, 20/11/2026) : avant d'ouvrir une position sur un marché, le bot
rejoue sa propre stratégie sur ce marché pendant les 12 derniers mois (avec le spread). Si elle y a perdu
de l'argent, il ne trade pas ce marché (il garde et gère les positions déjà ouvertes).

Test honnête (tendance 1 mois, choix sur l'an 1, vérif sur l'an 2) : 35 marchés sans tri +3 770 € puis -337 € ;
avec le tri +5 987 € puis +1 403 €. Le tri écarte surtout les mauvais marchés (11 perdants sur 14 reperdent).
"""
import os

import numpy as np
import pandas as pd

from bot.strategie import milieu

JOURS_ANALYSE = int(os.getenv("JOURS_ANALYSE", "365"))


def rejouer(df: pd.DataFrame, cible, jours: int = JOURS_ANALYSE) -> tuple[float, int]:
    """Résultat (en % du prix, cumulé) d'être en position `cible` (1, -1 ou 0, décidée à la clôture de chaque
    bougie et tenue jusqu'à la suivante), sur les `jours` derniers jours, spread payé à chaque changement."""
    m = milieu(df)
    c = m.close
    cible = pd.Series(np.asarray(cible, dtype=float), index=df.index).fillna(0)
    spread = ((df.close_ask - df.close_bid) / c).clip(lower=0)
    debut = df.index[-1] - pd.Timedelta(days=jours)
    fen = df.index >= debut
    rend = (cible.shift(1).fillna(0) * c.pct_change().fillna(0))[fen]
    changements = cible.diff().abs().fillna(0)[fen]
    cout = (changements * spread[fen] / 2)
    return float((rend - cout).sum() * 100), int((changements > 0).sum())


def verdict(df: pd.DataFrame, cible, jours: int = JOURS_ANALYSE) -> tuple[bool, str]:
    couverture = (df.index[-1] - df.index[0]).days
    if couverture < min(jours, 180):
        return False, f"pas assez d'historique pour analyser ({couverture} jours)"
    pct, n = rejouer(df, cible, jours)
    j = min(jours, couverture)
    if pct > 0:
        return True, f"sur {j} jours, la stratégie aurait gagné {pct:+.1f} % du prix ({n} changements)"
    return False, f"sur {j} jours, la stratégie aurait perdu ({pct:+.1f} % du prix) : marché écarté"

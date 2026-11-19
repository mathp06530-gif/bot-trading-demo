"""Stratégie de DÉMONSTRATION : croisement de deux moyennes mobiles exponentielles.

Même règle que le script TradingView (tradingview/strategie_demo.pine) :
  - EMA rapide au-dessus de l'EMA lente -> on veut être ACHETEUR (BUY)
  - EMA rapide en dessous de l'EMA lente -> on veut être VENDEUR (SELL)

Pour changer de stratégie plus tard, il suffit de remplacer la fonction `decider`.
"""

EMA_RAPIDE = 9
EMA_LENTE = 21


def ema(valeurs: list[float], periode: int) -> list[float | None]:
    """Moyenne mobile exponentielle, calculée comme ta.ema de TradingView
    (démarrage sur une moyenne simple des `periode` premières valeurs)."""
    resultat: list[float | None] = [None] * len(valeurs)
    if len(valeurs) < periode:
        return resultat
    alpha = 2 / (periode + 1)
    courant = sum(valeurs[:periode]) / periode
    resultat[periode - 1] = courant
    for i in range(periode, len(valeurs)):
        courant = alpha * valeurs[i] + (1 - alpha) * courant
        resultat[i] = courant
    return resultat


def decider(clotures: list[float]) -> dict:
    """Renvoie la direction souhaitée et une explication en français."""
    rapide = ema(clotures, EMA_RAPIDE)
    lente = ema(clotures, EMA_LENTE)
    if rapide[-1] is None or lente[-1] is None or len(clotures) < EMA_LENTE + 2:
        return {"direction": None, "croisement": False, "ema_rapide": rapide, "ema_lente": lente,
                "explication": "Pas assez de bougies pour calculer les moyennes."}

    direction = "BUY" if rapide[-1] > lente[-1] else "SELL"
    avant = "BUY" if rapide[-2] > lente[-2] else "SELL"
    croisement = direction != avant
    tendance = "haussière" if direction == "BUY" else "baissière"
    if croisement:
        explication = f"Croisement détecté : la tendance devient {tendance}."
    else:
        explication = f"Pas de nouveau croisement, la tendance reste {tendance}."
    return {"direction": direction, "croisement": croisement, "ema_rapide": rapide, "ema_lente": lente,
            "explication": explication}

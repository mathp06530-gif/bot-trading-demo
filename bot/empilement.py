"""EMPILEMENT : plusieurs positions en même temps sur le même marché (demande de Mathis, 20/11/2026).

Règle (« pyramide ») : on ajoute une position dans le MÊME sens seulement si le prix a avancé d'au
moins 1 R (la distance du stop) depuis la dernière entrée, et au plus EMPILER_MAX positions par marché.
On n'ajoute donc jamais à une position perdante. Chaque position a son propre stop garanti.
Backtest 2 ans (Tendance 4 h BTC + Cassure 4 h or/argent, 3 positions max) : beaucoup plus de gain
quand la tendance dure, mais des baisses bien plus fortes. C'est une EXPÉRIENCE en démo.
"""
import os

EMPILER_MAX = int(os.getenv("EMPILER_MAX", "1"))


def etages(niveaux, distance):
    """Nombre d'entrées distinctes (une entrée de la Tendance 4 h est coupée en 2 moitiés au même prix)."""
    n, dernier = 0, None
    for x in sorted(niveaux):
        if dernier is None or x - dernier > distance * 0.3:
            n += 1
        dernier = x
    return n


def peut_empiler(positions, sens, prix, distance, maximum=None):
    """positions : celles de la stratégie sur ce marché, dans le sens voulu. Renvoie (autorisé, explication)."""
    maximum = EMPILER_MAX if maximum is None else maximum
    if not positions:
        return True, ""
    if not sens or distance <= 0:
        return False, ""
    niveaux = [float(p["position"]["level"]) for p in positions]
    n = etages(niveaux, distance)
    if n >= maximum:
        return False, f"{n} position(s) ouverte(s) sur ce marché (maximum {maximum})"
    dernier = max(niveaux) if sens == "BUY" else min(niveaux)
    avance = (prix - dernier) * (1 if sens == "BUY" else -1)
    if avance < distance:
        return False, (f"position {n + 1}/{maximum} possible quand le prix aura avancé de "
                       f"{distance - avance:.2f} de plus dans le bon sens")
    return True, f"le prix a avancé de 1 R depuis la dernière entrée : position {n + 1}/{maximum} ajoutée"

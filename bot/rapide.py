"""Stratégie RAPIDE (expérimentale), séparée de la stratégie principale 4 h.

Mathis veut voir le bot trader souvent (10 à 30 trades par jour) pour comparer en direct.
Le backtest prévoit qu'elle PERD de l'argent : le spread (~50 $) mange les petits mouvements.
Son risque est donc minuscule : RISQUE_RAPIDE_PCT (0,1 %) du capital par trade.

Règles, sur des bougies de 5 minutes (prix milieu) :
  - EMA 9 au-dessus de l'EMA 50 -> on est ACHETEUR ; en dessous -> VENDEUR. Toujours en position.
  - Stop garanti à 1 % du prix. Si le stop est touché, on repart dans le sens de la tendance.
  - Les positions de cette stratégie sont repérées par leur numéro (dealId), le bot ne les
    mélange jamais avec celles de la stratégie 4 h.
"""
import math
import os

from bot.registre import noter_fermeture
from bot.strategie import ema

ACTIVE = os.getenv("RAPIDE", "oui").strip().lower() in ("oui", "1", "true", "on")
UNITE_RAPIDE = "MINUTE_5"
EMA_R, EMA_L = 9, 50
STOP_PCT = 1.0
RISQUE_RAPIDE_PCT = float(os.getenv("RISQUE_RAPIDE_PCT", "0.1"))
NOM = f"Rapide 5 min : EMA {EMA_R}/{EMA_L}, stop {STOP_PCT:g} %, risque {RISQUE_RAPIDE_PCT:g} % (expérimentale)"


def decider_rapide(clotures: list[float]) -> str | None:
    r, l = ema(clotures, EMA_R), ema(clotures, EMA_L)
    if len(clotures) < EMA_L + 2 or r[-1] is None or l[-1] is None:
        return None
    return "BUY" if r[-1] > l[-1] else "SELL"


def id_position(conf: dict) -> str | None:
    deals = conf.get("affectedDeals") or []
    return (deals[0].get("dealId") if deals else None) or conf.get("dealId")


def tour_rapide(api, donnees: dict, epic: str, positions: list, capital: float, eurusd: float, noter, quand: str = "") -> str:
    etat = donnees.setdefault("rapide", {"deals": [], "nom": NOM})
    etat["nom"] = NOM
    mes_ids = set(etat["deals"])
    miennes = [p for p in positions if p["position"]["dealId"] in mes_ids]
    etat["deals"] = [p["position"]["dealId"] for p in miennes]  # oublie celles fermées par le stop

    bougies = api.bougies(epic, UNITE_RAPIDE, 300)
    clotures = [(b["closePrice"]["bid"] + b["closePrice"]["ask"]) / 2 for b in bougies[:-1]]
    voulu = decider_rapide(clotures)
    if voulu is None or not bougies:
        return "Pas assez de bougies"
    etat["tendance"] = voulu

    for p in [p for p in miennes if p["position"]["direction"] != voulu]:
        conf = api.fermer(p["position"]["dealId"])
        if conf.get("dealStatus") == "ACCEPTED":
            noter_fermeture(donnees, p, conf, quand, "[Rapide] Croisement inverse")
        etat["deals"].remove(p["position"]["dealId"])
        noter("fermeture", epic, f"[Rapide] Croisement EMA {EMA_R}/{EMA_L} : position fermée "
              f"(gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
    if any(p["position"]["direction"] == voulu for p in miennes):
        return "Position conservée"

    prix = bougies[-1]["closePrice"]["ask" if voulu == "BUY" else "bid"]
    distance = prix * STOP_PCT / 100
    taille = math.floor(capital * RISQUE_RAPIDE_PCT / 100 * eurusd / distance / 0.0001) * 0.0001
    taille = round(max(taille, 0.0001), 4)
    conf = api.ouvrir(epic, voulu, taille, prix=prix, stop_distance=distance, garanti=True)
    mot = "ACHAT" if voulu == "BUY" else "VENTE"
    if conf.get("dealStatus") == "ACCEPTED":
        deal = id_position(conf)
        if deal:
            etat["deals"].append(deal)
        noter("ordre", epic, f"[Rapide] {mot} de {taille} à {float(conf.get('level') or prix):.2f}, "
              f"stop garanti à {distance:.0f} $.")
        return f"{mot} de {taille}"
    noter("erreur", epic, f"[Rapide] Ordre {mot} refusé : {conf.get('reason', conf.get('dealStatus', '?'))}")
    return "Ordre refusé"

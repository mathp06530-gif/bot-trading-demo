"""Stratégie RAPIDE 5 min sur l'OR et l'ARGENT (remise le 20/11/2026 à la demande de Mathis, test de 2 semaines).

Même logique que l'ancienne rapide du Bitcoin. Attention : en backtest (90 jours, 11 marchés), le trading
en bougies de 5 min ne gagnait pas après les frais. C'est une EXPÉRIENCE en démo.

Règles, sur des bougies de 5 minutes (prix milieu), pour chaque marché de RAPIDE_MARCHES :
  - EMA 9 au-dessus de l'EMA 50 -> signal ACHAT ; en dessous -> signal VENTE.
  - Le signal n'est suivi que s'il va dans le sens des tendances de fond 1 h (EMA 50/200) ET 4 h (EMA 20/200).
  - On n'ouvre que si les bandes de Bollinger s'élargissent (le marché se met à bouger)
    ET si l'ADX 14 (force de la tendance, bougies 5 min) dépasse ADX_RAPIDE_MIN (20).
    Test 20/11/2026 (5 mois de 5 min, or + argent, 2 moitiés) : l'ADX améliore les deux moitiés
    (-21 -> -20 R, puis +1 -> +6 R) ; RSI et ATR testés, rejetés (mieux sur une moitié, pire sur l'autre).
  - Stop garanti à 1 % du prix (ou le minimum imposé par Capital.com), stop suiveur à SUIVI_RAPIDE_PCT (2 %).
  - Taille : RISQUE_RAPIDE_PCT (1 %) du capital perdu au maximum, au moins la taille minimale du marché.
  - Les positions de cette stratégie sont repérées par leur numéro (dealId). Elle attend quand la
    cassure 4 h a une position dans l'autre sens sur le même marché (compte sans couverture).
"""
import math
import os
import statistics

from bot.empilement import peut_empiler
from bot.registre import noter_fermeture
from bot.strategie import adx, bougies_vers_df, ema, milieu
from bot.cassure import regles_marche, taux_devise

ACTIVE = os.getenv("RAPIDE", "non").strip().lower() in ("oui", "1", "true", "on")
UNITE_RAPIDE = "MINUTE_5"
EMA_R, EMA_L = 9, 50
STOP_PCT = 1.0
SUIVI_RAPIDE_PCT = float(os.getenv("SUIVI_RAPIDE_PCT", "2"))  # "0" = pas de stop suiveur
EMPILER_RAPIDE = int(os.getenv("EMPILER_RAPIDE", "1"))  # positions max par marché (empilement)
RISQUE_RAPIDE_PCT = float(os.getenv("RISQUE_RAPIDE_PCT", "1"))
LISTE = [m.strip() for m in os.getenv("RAPIDE_MARCHES", "GOLD,SILVER").split(",") if m.strip()]
ADX_RAPIDE_MIN = float(os.getenv("ADX_RAPIDE_MIN", "20"))  # 0 = pas de filtre ADX
FILTRE_BOLLINGER = os.getenv("FILTRE_BOLLINGER", "oui").strip().lower() in ("oui", "1", "true", "on")
NOM = f"Rapide 5 min : EMA {EMA_R}/{EMA_L} dans le sens des tendances 1 h et 4 h{", Bollinger qui s'élargissent" if FILTRE_BOLLINGER else ""}{f", ADX > {ADX_RAPIDE_MIN:g}" if ADX_RAPIDE_MIN > 0 else ""}, stop {STOP_PCT:g} %, suiveur {SUIVI_RAPIDE_PCT:g} %, risque {RISQUE_RAPIDE_PCT:g} % (expérimentale)"


def decider_rapide(clotures: list[float]) -> str | None:
    r, l = ema(clotures, EMA_R), ema(clotures, EMA_L)
    if len(clotures) < EMA_L + 2 or r[-1] is None or l[-1] is None:
        return None
    return "BUY" if r[-1] > l[-1] else "SELL"


def bollinger_relatif(clotures: list[float], n: int = 20, fenetre: int = 100) -> float | None:
    """Largeur des bandes de Bollinger (4 écarts-types / moyenne) divisée par sa médiane des `fenetre`
    dernières bougies. > 1 : le marché s'agite plus que d'habitude."""
    if len(clotures) < n + fenetre:
        return None
    largeurs = []
    for fin in range(len(clotures) - fenetre + 1, len(clotures) + 1):
        x = clotures[fin - n:fin]
        largeurs.append(4 * statistics.stdev(x) / statistics.fmean(x))
    mediane = statistics.median(largeurs)
    return largeurs[-1] / mediane if mediane else None


def sens_ema(clotures: list[float], rapide: int, lente: int) -> str | None:
    r, l = ema(clotures, rapide), ema(clotures, lente)
    if r[-1] is None or l[-1] is None:
        return None
    return "BUY" if r[-1] > l[-1] else "SELL"


def tendances_superieures(api, epic: str) -> tuple[str | None, str | None]:
    """Sens de la tendance de fond en 1 h (EMA 50/200) et en 4 h (EMA 20/200), bougies terminées."""
    milieux = lambda bs: [(b["closePrice"]["bid"] + b["closePrice"]["ask"]) / 2 for b in bs[:-1]]
    return (sens_ema(milieux(api.bougies(epic, "HOUR", 400)), 50, 200),
            sens_ema(milieux(api.bougies(epic, "HOUR_4", 400)), 20, 200))


def id_position(conf: dict) -> str | None:
    deals = conf.get("affectedDeals") or []
    return (deals[0].get("dealId") if deals else None) or conf.get("dealId")


def tour_rapide(api, donnees: dict, epic: str, positions: list, capital: float, eurusd: float, noter, quand: str = "",
                garde=None) -> str:
    etat = donnees.setdefault("rapide", {"deals": [], "nom": NOM})
    etat["nom"] = NOM
    ouverts = {p["position"]["dealId"] for p in positions}
    etat["deals"] = [d for d in etat.setdefault("deals", []) if d in ouverts]  # oublie celles fermées par le stop
    mes_ids = set(etat["deals"])
    miennes = [p for p in positions if p["position"]["dealId"] in mes_ids and p["market"]["epic"] == epic]
    marche = etat.setdefault("marches", {}).setdefault(epic, {})

    bougies = api.bougies(epic, UNITE_RAPIDE, 300)
    clotures = [(b["closePrice"]["bid"] + b["closePrice"]["ask"]) / 2 for b in bougies[:-1]]
    signal = decider_rapide(clotures)
    if signal is None or not bougies:
        return "Pas assez de bougies"
    t1, t4 = tendances_superieures(api, epic)
    etat["tendance"] = signal
    marche.update({"tendance": signal, "filtre": {"signal_5min": signal, "tendance_1h": t1, "tendance_4h": t4},
                   "prix": (bougies[-1]["closePrice"]["bid"] + bougies[-1]["closePrice"]["ask"]) / 2})
    voulu = signal if signal == t1 == t4 else None

    for p in [p for p in miennes if p["position"]["direction"] != voulu]:
        conf = api.fermer(p["position"]["dealId"])
        if conf.get("dealStatus") == "ACCEPTED":
            noter_fermeture(donnees, p, conf, quand, "[Rapide] Croisement inverse")
        etat["deals"].remove(p["position"]["dealId"])
        raison = f"Croisement EMA {EMA_R}/{EMA_L}" if voulu else "Plus d'accord avec la tendance de fond 1 h / 4 h"
        noter("fermeture", epic, f"[Rapide] {raison} : position fermée "
              f"(gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
    if voulu is None:
        mots = {"BUY": "hausse", "SELL": "baisse", None: "?"}
        return (f"À l'écart : signal 5 min en {mots[signal]}, mais tendance 1 h en {mots[t1]} "
                f"et 4 h en {mots[t4]} (pas d'accord)")
    gardees = [p for p in miennes if p["position"]["direction"] == voulu]
    empile = ""
    if gardees:
        res = suivre_stop(api, gardees, bougies[-1]["closePrice"], epic, noter)
        px = bougies[-1]["closePrice"]["ask" if voulu == "BUY" else "bid"]
        ok_e, empile = peut_empiler(gardees, voulu, px, px * STOP_PCT / 100, EMPILER_RAPIDE)
        marche["empilement"] = empile
        if not ok_e:
            return res

    # Sans mode couverture, un ordre inverse fermerait les positions de la stratégie 4 h : on attend.
    autres = [p for p in positions if p["market"]["epic"] == epic and p["position"]["dealId"] not in mes_ids]
    if any(p["position"]["direction"] != voulu for p in autres):
        return "En attente : la cassure 4 h est en position inverse"

    if FILTRE_BOLLINGER:
        bb = bollinger_relatif(clotures)
        marche["filtre"]["bollinger"] = None if bb is None else round(bb, 2)
        if bb is None or bb <= 1:
            return "En attente : marché trop calme (bandes de Bollinger étroites)"

    if ADX_RAPIDE_MIN > 0:
        force = float(adx(milieu(bougies_vers_df(bougies[:-1]))).iloc[-1])
        marche["filtre"]["adx"] = round(force, 1)
        if not force > ADX_RAPIDE_MIN:
            return f"En attente : tendance 5 min trop faible (ADX {force:.0f} ≤ {ADX_RAPIDE_MIN:g})"

    prix = bougies[-1]["closePrice"]["ask" if voulu == "BUY" else "bid"]
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    if regles["statut"] != "TRADEABLE":
        return "Marché fermé"
    mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
    distance = max(prix * STOP_PCT / 100, mini * 1.25)  # Capital.com mesure le minimum un peu plus loin (argent : ~1,12 %)
    taux = taux_devise(regles, eurusd, prix)
    pas = regles["pas"]
    taille = round(math.floor(capital * RISQUE_RAPIDE_PCT / 100 * taux / distance / pas) * pas, 6)
    if taille < regles["taille_min"]:
        return f"Refusé : capital trop faible pour la taille minimale ({regles['taille_min']})"
    if garde is not None:
        garde.taux[epic] = taux
        ok, raison = garde.autoriser(taille * distance / taux, distance)
        if not ok:
            return f"Refusé (garde-fous) : {raison}"
        stop = prix - distance if voulu == "BUY" else prix + distance
        garde.enregistrer({"market": {"epic": epic},
                           "position": {"level": prix, "stopLevel": stop, "size": taille, "direction": voulu}})
    conf = api.ouvrir(epic, voulu, taille, prix=prix, stop_distance=distance, garanti=True)
    mot = "ACHAT" if voulu == "BUY" else "VENTE"
    if conf.get("dealStatus") == "ACCEPTED":
        deal = id_position(conf)
        if deal:
            etat["deals"].append(deal)
        noter("ordre", epic, f"[Rapide] {'Empilement (' + empile + ') : ' if empile else ''}{mot} de {taille} à {float(conf.get('level') or prix):.2f}, "
              f"stop garanti à {distance:.2f} $.")
        return f"{mot} de {taille}"
    noter("erreur", epic, f"[Rapide] Ordre {mot} refusé : {conf.get('reason', conf.get('dealStatus', '?'))}")
    return "Ordre refusé"


def suivre_stop(api, gardees: list, prix: dict, epic: str, noter) -> str:
    """Stop suiveur : rapproche le stop garanti à SUIVI_RAPIDE_PCT % du prix actuel s'il protège mieux.
    Le stop ne recule jamais et reste au moins à STOP_PCT % du prix (minimum du stop garanti)."""
    if SUIVI_RAPIDE_PCT <= 0:
        return "Position conservée"
    resultat = "Position conservée"
    milieu = (prix["bid"] + prix["ask"]) / 2
    ecart = milieu * max(SUIVI_RAPIDE_PCT, STOP_PCT) / 100
    for p in gardees:
        pos = p["position"]
        actuel = pos.get("stopLevel")
        if pos["direction"] == "BUY":
            cible = milieu - ecart
            mieux = actuel is None or cible > float(actuel) + milieu * 0.001
        else:
            cible = milieu + ecart
            mieux = actuel is None or cible < float(actuel) - milieu * 0.001
        if not mieux:
            continue
        conf = api.modifier_stop(pos["dealId"], cible, bool(pos.get("guaranteedStop", True)))
        if conf.get("dealStatus") == "ACCEPTED":
            noter("stop", epic, f"[Rapide] Stop suiveur déplacé de {float(actuel or 0):.2f} à {cible:.2f} "
                  "pour garder le gain.")
            resultat = "Stop suiveur déplacé"
        else:
            noter("erreur", epic, f"[Rapide] Déplacement du stop refusé : {conf.get('reason', conf.get('dealStatus', '?'))}")
    return resultat

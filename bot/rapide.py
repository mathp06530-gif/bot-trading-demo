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
  - Protection du gain (25/11/2026) : dès qu'une position a été en gain d'au moins SORTIE_ENTREE_R (0,5 R,
    1 R = la distance du stop = 1 % du prix), le bot la ferme si une bougie 5 min se termine de nouveau au
    prix d'entrée ou en dessous (un gain qui disparaît ne devient pas une perte).
    Backtest or 5 min, 13/05 -> 25/11/2026, net de frais (backtest/sortie_rapide.py) : +9,4 R -> +10,1 R,
    mieux sur les deux moitiés, et pareil de 0,3 à 0,8 R. Rejetés car moins bons : prendre la moitié du gain
    à +1/+1,5/+2 R, suiveur qui se resserre après +1/+1,5/+2 R, stop garanti remonté au point d'entrée.
    Retesté le 25/11 avec la protection du gain (backtest/serrage.py) : stop qui garde 50 à 80 % du gain ou suit
    à 0,5-1,5 R après +1 à +3 R -> jamais mieux (9,5 R au mieux, autant que l'actuelle).
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
SORTIE_ENTREE_R = float(os.getenv("SORTIE_ENTREE_R", "0.5"))  # "0" = pas de protection du gain
# Stop qui se resserre (25/11/2026, demandé par Mathis pour le voir en vrai en démo) : dès que le gain a atteint
# GARDE_RAPIDE_APRES_R R, le stop garanti est remonté pour garder GARDE_RAPIDE_PCT % du meilleur gain.
# Backtest or 5 min (backtest/serrage.py) : 9,0 R au lieu de 9,5 R (un peu MOINS bien), choisi car c'est la
# variante qui agit vraiment et coûte le moins. EXPÉRIENCE : à juger au bilan (ordres séparés avant/après). "0" = aucun.
GARDE_RAPIDE_APRES_R = float(os.getenv("GARDE_RAPIDE_APRES_R", "1.5"))
GARDE_RAPIDE_PCT = float(os.getenv("GARDE_RAPIDE_PCT", "60"))
# 25/11/2026 (backtest/rapide_defauts.py, or 5 min, 13/05 -> 25/11) : sortie sur croisement inverse seulement
# s'il dure 3 bougies 5 min : +17,6 R -> +26,7 R (mieux sur les 2 moitiés). "1" = sortie immédiate (avant).
SORTIE_CONFIRMEE_RAPIDE = int(float(os.getenv("SORTIE_CONFIRMEE_RAPIDE", "3")))
ADX_RAPIDE_MIN = float(os.getenv("ADX_RAPIDE_MIN", "20"))  # 0 = pas de filtre ADX
FILTRE_BOLLINGER = os.getenv("FILTRE_BOLLINGER", "oui").strip().lower() in ("oui", "1", "true", "on")
NOM = f"Rapide 5 min : EMA {EMA_R}/{EMA_L} dans le sens des tendances 1 h et 4 h{", Bollinger qui s'élargissent" if FILTRE_BOLLINGER else ""}{f", ADX > {ADX_RAPIDE_MIN:g}" if ADX_RAPIDE_MIN > 0 else ""}, stop {STOP_PCT:g} %, suiveur {SUIVI_RAPIDE_PCT:g} %{f", sortie au prix d'entrée après +{SORTIE_ENTREE_R:g} R" if SORTIE_ENTREE_R > 0 else ""}{f", garde {GARDE_RAPIDE_PCT:g} % du gain après +{GARDE_RAPIDE_APRES_R:g} R" if GARDE_RAPIDE_APRES_R > 0 and GARDE_RAPIDE_PCT > 0 else ""}{f", sortie si le croisement inverse dure {SORTIE_CONFIRMEE_RAPIDE} bougies" if SORTIE_CONFIRMEE_RAPIDE > 1 else ""}, jusqu'à {EMPILER_RAPIDE} position(s), risque {RISQUE_RAPIDE_PCT:g} % (expérimentale)"


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
    if etat.get("nom") and etat["nom"] != NOM:  # changement de réglages : daté dans le Journal (bilan avant/après)
        noter("analyse", epic, f"[Rapide] Réglages changés à partir de maintenant : {NOM}. "
              f"Avant : {etat['nom']}. Le bilan sépare les trades d'avant et d'après.")
    etat["nom"] = NOM
    ouverts = {p["position"]["dealId"] for p in positions}
    etat["deals"] = [d for d in etat.setdefault("deals", []) if d in ouverts]  # oublie celles fermées par le stop
    meilleurs = etat.setdefault("meilleur", {})  # dealId -> {"depuis": bougie d'entrée, "prix": meilleur prix vu}
    for d in [d for d in meilleurs if d not in ouverts]:
        del meilleurs[d]
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

    # Croisement inverse CONFIRMÉ : on ne ferme que si le sens voulu n'est plus celui de la position sur les
    # SORTIE_CONFIRMEE_RAPIDE dernières bougies 5 min terminées (25/11 : moins de sorties sur un faux signal).
    recents = []
    for j in range(max(1, SORTIE_CONFIRMEE_RAPIDE)):
        s_j = decider_rapide(clotures[:len(clotures) - j]) if j else signal
        recents.append(s_j if s_j == t1 == t4 else None)
    a_fermer = [p for p in miennes if all(v != p["position"]["direction"] for v in recents)]
    for p in a_fermer:
        conf = api.fermer(p["position"]["dealId"])
        if conf.get("dealStatus") == "ACCEPTED":
            noter_fermeture(donnees, p, conf, quand, "[Rapide] Croisement inverse")
        etat["deals"].remove(p["position"]["dealId"])
        raison = f"Croisement EMA {EMA_R}/{EMA_L}" if voulu else "Plus d'accord avec la tendance de fond 1 h / 4 h"
        noter("fermeture", epic, f"[Rapide] {raison} (confirmé sur {len(recents)} bougies) : position fermée "
              f"(gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
    gardees = [p for p in miennes if p not in a_fermer]
    if gardees and SORTIE_ENTREE_R > 0:
        gardees = proteger_gain(api, donnees, etat, gardees, bougies, epic, noter, quand)
    if gardees and SORTIE_ENTREE_R > 0 and GARDE_RAPIDE_APRES_R > 0 and GARDE_RAPIDE_PCT > 0:
        garder_gain_rapide(api, donnees, etat, gardees, bougies, epic, noter)
    res = suivre_stop(api, gardees, bougies[-1]["closePrice"], epic, noter) if gardees else ""
    if voulu is None and not gardees:
        mots = {"BUY": "hausse", "SELL": "baisse", None: "?"}
        return (f"À l'écart : signal 5 min en {mots[signal]}, mais tendance 1 h en {mots[t1]} "
                f"et 4 h en {mots[t4]} (pas d'accord)")
    if gardees and gardees[0]["position"]["direction"] != voulu:
        return "Position gardée : le signal contraire n'est pas encore confirmé"
    empile = ""
    if gardees:
        px = bougies[-1]["closePrice"]["ask" if voulu == "BUY" else "bid"]
        ok_e, empile = peut_empiler(gardees, voulu, px, px * STOP_PCT / 100, EMPILER_RAPIDE)
        marche["empilement"] = empile
        if not ok_e:
            return res

    # Le moteur passe toutes les minutes (25/11) : au plus UNE entrée par bougie 5 min terminée et par marché,
    # comme dans le backtest (pas de nouvelle entrée sur le même signal juste après un stop, par exemple).
    signal_de = bougies[-2]["snapshotTimeUTC"] if len(bougies) > 1 else ""
    if signal_de and etat.setdefault("entree_bougie", {}).get(epic) == signal_de:
        return res or "En attente de la prochaine bougie 5 min (déjà entré sur celle-ci)"

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
        ok, raison = garde.autoriser(taille * distance / taux, distance, "rapide", epic)
        if not ok:
            return f"Refusé (garde-fous) : {raison}"
        stop = prix - distance if voulu == "BUY" else prix + distance
        garde.enregistrer({"market": {"epic": epic},
                           "position": {"level": prix, "stopLevel": stop, "size": taille, "direction": voulu}})
    conf = api.ouvrir(epic, voulu, taille, prix=prix, stop_distance=distance, garanti=True)
    mot = "ACHAT" if voulu == "BUY" else "VENTE"
    if conf.get("dealStatus") == "ACCEPTED":
        deal = id_position(conf)
        if signal_de:
            etat.setdefault("entree_bougie", {})[epic] = signal_de
        if deal:
            etat["deals"].append(deal)
            etat["meilleur"][deal] = {"depuis": bougies[-1]["snapshotTimeUTC"], "prix": float(conf.get("level") or prix)}
        noter("ordre", epic, f"[Rapide] {'Empilement (' + empile + ') : ' if empile else ''}{mot} de {taille} à {float(conf.get('level') or prix):.2f}, "
              f"stop garanti à {distance:.2f} $.")
        return f"{mot} de {taille}"
    noter("erreur", epic, f"[Rapide] Ordre {mot} refusé : {conf.get('reason', conf.get('dealStatus', '?'))}")
    return "Ordre refusé"


def proteger_gain(api, donnees: dict, etat: dict, gardees: list, bougies: list, epic: str, noter, quand: str) -> list:
    """Ferme une position qui a été en gain d'au moins SORTIE_ENTREE_R R et dont la dernière bougie 5 min
    TERMINÉE est revenue au prix d'entrée (ou pire). Renvoie les positions gardées.
    Le meilleur prix est suivi sur les bougies terminées depuis la bougie d'entrée (comme le backtest)."""
    meilleurs = etat.setdefault("meilleur", {})
    terminees = bougies[:-1]
    if not terminees:
        return gardees
    restent = []
    for p in gardees:
        pos = p["position"]
        deal, sens = pos["dealId"], 1 if pos["direction"] == "BUY" else -1
        entree = float(pos["level"])
        suivi = meilleurs.get(deal)
        if suivi is None:  # position ouverte avant cette règle : on suit à partir de son heure d'ouverture
            depuis = (pos.get("createdDateUTC") or bougies[-1]["snapshotTimeUTC"])[:16]
            suivi = meilleurs[deal] = {"depuis": depuis, "prix": entree}
        for b in terminees:
            if not _apres_entree(b["snapshotTimeUTC"], suivi["depuis"]):
                continue  # bougie d'avant l'entrée (celle qui contient l'heure d'entrée compte)
            cote = "highPrice" if sens > 0 else "lowPrice"
            extreme = (b[cote]["bid"] + b[cote]["ask"]) / 2
            suivi["prix"] = max(suivi["prix"], extreme) if sens > 0 else min(suivi["prix"], extreme)
        distance = entree * STOP_PCT / 100
        gain_max = (suivi["prix"] - entree) * sens / distance
        cloture = terminees[-1]["closePrice"]["bid" if sens > 0 else "ask"]
        if gain_max >= SORTIE_ENTREE_R and (cloture - entree) * sens <= 0:
            conf = api.fermer(deal)
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, quand, "[Rapide] Retour au prix d'entrée")
                if deal in etat["deals"]:
                    etat["deals"].remove(deal)
                meilleurs.pop(deal, None)
                noter("fermeture", epic, f"[Rapide] Le gain avait atteint {gain_max:.1f} R et le prix est revenu au "
                      f"prix d'entrée ({entree:.2f}) : position fermée pour ne pas transformer un gain en perte "
                      f"(gain/perte : {pos.get('upl', 0):.2f}).")
                continue
            noter("erreur", epic, f"[Rapide] Fermeture au prix d'entrée refusée : {conf.get('reason', conf.get('dealStatus', '?'))}")
        restent.append(p)
    return restent


def garder_gain_rapide(api, donnees: dict, etat: dict, gardees: list, bougies: list, epic: str, noter) -> None:
    """Dès +GARDE_RAPIDE_APRES_R R de gain (meilleur prix suivi par proteger_gain), remonte le stop garanti pour
    garder GARDE_RAPIDE_PCT % du meilleur gain. Ne recule jamais ; respecte la distance minimale Capital.com."""
    meilleurs = etat.get("meilleur", {})
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    prix = (bougies[-1]["closePrice"]["bid"] + bougies[-1]["closePrice"]["ask"]) / 2
    mini = (prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)) * 1.05
    for p in gardees:
        pos = p["position"]
        suivi = meilleurs.get(pos["dealId"])
        if not suivi:
            continue
        sens, entree, actuel = (1 if pos["direction"] == "BUY" else -1), float(pos["level"]), pos.get("stopLevel")
        distance = entree * STOP_PCT / 100
        gain_max = (suivi["prix"] - entree) * sens / distance
        if gain_max < GARDE_RAPIDE_APRES_R:
            continue
        cible = entree + GARDE_RAPIDE_PCT / 100 * (suivi["prix"] - entree)
        cible = min(cible, prix - mini) if sens > 0 else max(cible, prix + mini)
        if actuel is not None and (cible - float(actuel)) * sens <= prix * 0.001:
            continue
        conf = api.modifier_stop(pos["dealId"], cible, bool(pos.get("guaranteedStop", True)))
        if conf.get("dealStatus") == "ACCEPTED":
            noter("stop", epic, f"[Rapide] Le gain a atteint {gain_max:.1f} R : stop garanti remonté de "
                  f"{float(actuel or 0):.2f} à {cible:.2f} pour garder {GARDE_RAPIDE_PCT:g} % du meilleur gain.")
            pos["stopLevel"] = cible  # le stop suiveur de base part de ce nouveau niveau
        else:
            noter("erreur", epic, f"[Rapide] Remontée du stop refusée : {conf.get('reason', conf.get('dealStatus', '?'))}")


def _apres_entree(debut_bougie: str, entree: str) -> bool:
    """La bougie 5 min qui commence à `debut_bougie` est-elle celle de l'entrée ou une suivante ?"""
    b, e = debut_bougie[:16], entree[:16]  # « AAAA-MM-JJTHH:MM »
    minute = int(e[14:16]) // 5 * 5
    return b >= f"{e[:14]}{minute:02d}"


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

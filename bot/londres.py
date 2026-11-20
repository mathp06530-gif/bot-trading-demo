"""STRATÉGIE « CASSURE DE LONDRES » sur USD/JPY (choisie par Mathis le 20/11/2026, risque 5 %).

Testée le 20/11/2026 sur 2 ans de bougies 1 h Capital.com (12 marchés), avec le spread, sur 100 € :
USD/JPY gagne les deux années (+42 € puis +71 € à 5 % de risque, pire baisse -29 %, ~12 trades/mois),
et reste positive dans les 6 variantes de réglages essayées. Elle a été choisie parmi 12 marchés :
une part peut venir de la chance. C'est une EXPÉRIENCE en démo, pas une promesse.

Règles (heures UTC, bougies 1 h TERMINÉES) :
  ZONE   : plus haut et plus bas des bougies de 0 h à 6 h (la nuit asiatique).
  ENTRÉE : une bougie qui commence entre 7 h et 10 h clôture au-dessus de la zone -> ACHAT,
           en dessous -> VENTE. Un seul trade par jour.
  STOP   : stop GARANTI à la largeur de la zone (ou le minimum imposé par Capital.com).
  SORTIE : à 20 h UTC, la position est fermée (pas de frais de nuit).
  TAILLE : RISQUE_LONDRES_PCT (5 %) du capital perdu au maximum si le stop est touché.
"""
import math
import os

from bot.cassure import taux_devise
from bot.registre import noter_fermeture
from bot.sous_bots import regles_marche

ACTIVE_PAR_DEFAUT = os.getenv("LONDRES", "non").strip().lower() in ("oui", "1", "true", "on")
LISTE = [m.strip() for m in os.getenv("LONDRES_MARCHES", "USDJPY").split(",") if m.strip()]
RISQUE_LONDRES_PCT = float(os.getenv("RISQUE_LONDRES_PCT", "5"))
ZONE_DEBUT, ZONE_FIN, ENTREE_FIN, SORTIE = 0, 7, 10, 20  # heures UTC
NOM = f"Cassure de Londres : zone {ZONE_DEBUT} h-{ZONE_FIN} h UTC, entrée {ZONE_FIN} h-{ENTREE_FIN + 1} h, sortie {SORTIE} h"


def zone_du_jour(bougies: list, jour: str):
    """(plus haut, plus bas) des bougies 1 h de 0 h à 6 h UTC du jour, ou None s'il en manque."""
    nuit = [b for b in bougies if b["snapshotTimeUTC"][:10] == jour
            and ZONE_DEBUT <= int(b["snapshotTimeUTC"][11:13]) < ZONE_FIN]
    if len(nuit) < ZONE_FIN - ZONE_DEBUT - 1:  # on tolère une bougie manquante
        return None
    haut = max((b["highPrice"]["bid"] + b["highPrice"]["ask"]) / 2 for b in nuit)
    bas = min((b["lowPrice"]["bid"] + b["lowPrice"]["ask"]) / 2 for b in nuit)
    return haut, bas


def tour_londres(api, donnees: dict, epic: str, positions: list, capital: float, disponible: float, eurusd: float,
                 noter, garde, quand: str, peut_entrer: bool = True) -> dict:
    tous_deals = donnees.setdefault("deals_par_strategie", {}).setdefault("londres", [])
    etat = donnees.setdefault("londres", {}).setdefault(epic, {})
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    etat["nom"] = regles["nom"]
    miennes = [p for p in positions if p["market"]["epic"] == epic and p["position"]["dealId"] in tous_deals]
    jour, heure = quand[:10], int(quand[11:13])

    # 1) Sortie à 20 h UTC (ou une position d'un jour précédent)
    for p in miennes:
        ouverte = (p["position"].get("createdDateUTC") or quand)[:10]
        if heure >= SORTIE or ouverte < jour:
            conf = api.fermer(p["position"]["dealId"])
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, quand, "Fin de journée (cassure de Londres)")
            noter("fermeture", epic, f"Fin de journée : position fermée (gain/perte : {p['position'].get('upl', 0):.2f}).")
            etat["action"] = "Position fermée (fin de journée)"
            return etat
    if miennes:
        etat["action"] = "Position conservée jusqu'à 20 h UTC"
        return etat

    bougies = api.bougies(epic, "HOUR", 48)
    terminees = bougies[:-1]
    zone = zone_du_jour(terminees, jour)
    prix_achat, prix_vente = bougies[-1]["closePrice"]["ask"], bougies[-1]["closePrice"]["bid"]
    etat.update({"prix": (prix_achat + prix_vente) / 2, "jour": jour})
    if zone:
        etat.update({"plus_haut_20": round(zone[0], 3), "plus_bas_20": round(zone[1], 3)})
    if not peut_entrer:
        etat["action"] = "Désactivée"
        return etat
    if not zone:
        etat["action"] = "Zone de la nuit pas encore complète"
        return etat
    derniere = terminees[-1]
    h = int(derniere["snapshotTimeUTC"][11:13])
    if derniere["snapshotTimeUTC"][:10] != jour or not (ZONE_FIN <= h <= ENTREE_FIN):
        etat["action"] = "Hors de la fenêtre d'entrée (8 h-12 h à Paris)" if heure >= ZONE_FIN else "Attend la fin de la nuit"
        return etat
    entrees = donnees.setdefault("entrees", {})
    if entrees.get(f"londres:{epic}") == jour:
        etat["action"] = "Déjà un trade aujourd'hui"
        return etat
    cloture = (derniere["closePrice"]["bid"] + derniere["closePrice"]["ask"]) / 2
    haut, bas = zone
    voulu = "BUY" if cloture > haut else "SELL" if cloture < bas else None
    if not voulu:
        etat["action"] = "Le prix reste dans la zone de la nuit"
        return etat
    prix = prix_achat if voulu == "BUY" else prix_vente
    mot = "ACHAT" if voulu == "BUY" else "VENTE"
    mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
    distance = max(haut - bas, mini * 1.05)
    pas = regles["pas"]
    taux = taux_devise(regles, eurusd, prix)
    garde.taux[epic] = taux
    taille = math.floor(capital * RISQUE_LONDRES_PCT / 100 * taux / distance / pas) * pas
    taille_marge = math.floor(disponible * taux / (prix * regles["marge"]) * 0.5 / pas) * pas
    taille = round(min(taille, taille_marge), 6)
    refus = None
    if regles["statut"] != "TRADEABLE":
        refus = "marché fermé"
    elif any(p["market"]["epic"] == epic and p["position"]["direction"] != voulu for p in positions):
        refus = "une autre stratégie a une position dans l'autre sens sur ce marché"
    elif (prix_achat - prix_vente) > distance * 0.15:
        refus = "spread trop cher par rapport au stop"
    elif taille < regles["taille_min"]:
        refus = f"capital trop faible pour la taille minimale ({regles['taille_min']})"
    else:
        ok, raison = garde.autoriser(taille * distance / taux, distance)
        refus = None if ok else raison
    if refus:
        if etat.get("dernier_refus") != refus:
            noter("analyse", epic, f"Cassure de Londres ({mot}) mais ordre REFUSÉ : {refus}.")
        etat.update({"dernier_refus": refus, "action": f"Refusé : {refus}"})
        return etat
    conf = api.ouvrir(epic, voulu, taille, prix=prix, stop_distance=distance, garanti=True)
    if conf.get("dealStatus") == "ACCEPTED":
        entrees[f"londres:{epic}"] = jour
        deal = (conf.get("affectedDeals") or [{}])[0].get("dealId") or conf.get("dealId")
        if deal:
            tous_deals.append(deal)
        stop = prix - distance if voulu == "BUY" else prix + distance
        garde.enregistrer({"market": {"epic": epic}, "position": {"level": prix, "stopLevel": stop, "size": taille,
                                                                  "direction": voulu}})
        cote = "au-dessus du plus haut" if voulu == "BUY" else "sous le plus bas"
        noter("ordre", epic, f"Cassure de Londres : clôture {cote} de la nuit ({haut:.3f} / {bas:.3f}) : {mot} de "
              f"{taille} à {float(conf.get('level') or prix):.3f}, stop garanti à {distance:.3f}, sortie à 20 h UTC.")
        etat.pop("dernier_refus", None)
        etat["action"] = f"{mot} de {taille}"
    else:
        noter("erreur", epic, f"Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
        etat["action"] = "Erreur"
    return etat

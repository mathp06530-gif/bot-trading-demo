"""Un tour de bot : se connecte au compte DÉMO Capital.com, fait tourner chaque stratégie,
passe les ordres si besoin, puis met à jour docs/data.json pour l'application.

GitHub lance ce fichier toutes les minutes (voir .github/workflows/moteur.yml).
Lancement manuel :  python -m bot.main

NETTOYAGE DU 26/11/2026 (demande de Mathis : repartir proprement) : seules les stratégies prouvées
restent, la Cassure 4 h (or, argent) et la Rapide 5 min (or), avec les garde-fous. Tout le reste
(Tendance Bitcoin, Élan, Supertrend, usine, Avant la Fed, veille d'actus, simulateur, deux cerveaux)
est retiré. Sauvegarde complète de l'avant : branche « sauvegarde-26-11 » sur GitHub.

AJOUTER UNE STRATÉGIE : écrire bot/<nom>.py avec une fonction tour(...) (voir bot/cassure.py ou
bot/rapide.py), puis ajouter une ligne dans STRATEGIES ci-dessous. Rien d'autre à toucher.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot.capital import CapitalDemo, ErreurCapital
from bot.garde_fous import GardeFous, surveiller_series_de_stops
from bot import rapide as module_rapide
from bot import actualites
from bot.cassure import LISTE as MARCHES_CASSURE
from bot.cassure import NOM as NOM_CASSURE
from bot.cassure import RISQUE_CASSURE_PCT, tour_cassure
from bot.amelioration import reglages_du_moment
from bot import graphiques as module_graphiques
from bot.registre import noter_fermeture, synchroniser

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "docs" / "data.json"

MAX_JOURNAL = 1000
MAX_HISTORIQUE = 3000  # ~1 mois de points à raison d'un toutes les 15 min
MAX_JOURS = 3650  # un point par jour, sur 10 ans


def maintenant() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def charger() -> dict:
    try:
        return json.loads(FICHIER_DONNEES.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def sauver(donnees: dict):
    FICHIER_DONNEES.parent.mkdir(parents=True, exist_ok=True)
    FICHIER_DONNEES.write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")


def milieu(prix: dict) -> float:
    return (prix["bid"] + prix["ask"]) / 2


DESCRIPTION_CASSURE = ("Un sous-bot pour l'or et un pour l'argent : il achète quand le prix casse le plus haut "
                       "des 20 dernières bougies de 4 h (vend sous le plus bas), dans le sens de l'EMA 200, "
                       "avec stop garanti. Environ 4 trades par mois.")
DESCRIPTION_RAPIDE = ("Trade souvent sur des bougies de 5 min, sur l'or, seulement dans le sens des tendances "
                      "1 h et 4 h, avec stop garanti et stop suiveur.")


def _tour_cassure(api, donnees, ctx, peut_entrer):
    for epic in MARCHES_CASSURE:
        try:
            tour_cassure(api, donnees, epic, ctx["positions"], ctx["capital"], ctx["disponible"], ctx["eurusd"],
                         ctx["noter"], ctx["garde"], maintenant(), peut_entrer=peut_entrer)
        except Exception as e:  # un marché en erreur ne bloque pas les autres
            donnees.setdefault("cassure", {}).setdefault(epic, {})["action"] = "Erreur"
            ctx["noter"]("erreur", epic, str(e)[:300])


def _tour_rapide(api, donnees, ctx, peut_entrer):
    if not peut_entrer:  # la Rapide ne gère ses positions que quand elle est active (comme avant)
        return
    for epic in module_rapide.LISTE:
        try:
            res = module_rapide.tour_rapide(api, donnees, epic, api.positions(), ctx["capital"], ctx["eurusd"],
                                            ctx["noter"], maintenant(), ctx["garde"])
        except Exception as e:  # un marché en erreur ne bloque pas les autres
            res = "Erreur"
            ctx["noter"]("erreur", epic, f"[Rapide] {str(e)[:300]}")
        donnees.setdefault("rapide", {}).setdefault("marches", {}).setdefault(epic, {})["action"] = res


# Les stratégies qui tournent. Pour en ajouter une : une ligne ici (id, nom affiché, fonction du tour,
# active par défaut, fiche pour l'appli). L'ordre compte : la première passe en priorité.
STRATEGIES = [
    {"id": "cassure_4h", "nom": "Cassure 4 h (or et argent)", "tour": _tour_cassure, "active": True,
     "fiche": lambda: {"description": DESCRIPTION_CASSURE, "unite": "HOUR_4", "risque_pct": RISQUE_CASSURE_PCT,
                       "reglages": NOM_CASSURE, "marches": MARCHES_CASSURE}},
    {"id": "rapide", "nom": "Rapide 5 min (or)", "tour": _tour_rapide, "active": module_rapide.ACTIVE,
     "fiche": lambda: {"description": DESCRIPTION_RAPIDE, "unite": module_rapide.UNITE_RAPIDE,
                       "risque_pct": module_rapide.RISQUE_RAPIDE_PCT, "reglages": module_rapide.NOM,
                       "marches": module_rapide.LISTE}},
]

# Données laissées dans docs/data.json par les stratégies et outils retirés le 26/11/2026 (effacées une fois).
ANCIENNES_CLES = ("elan", "supertrend", "usine", "fed", "veille", "simulations", "deux_cerveaux_depuis",
                  "valeur_corrigee_2511", "tour_1min_2511", "bitcoin_retire", "_pauses_marches_notees",
                  "analyses", "empilement", "sous_bots", "petit_compte", "tendance_mois", "x5_or",
                  "x5_argent", "cassure_tous", "challenge", "challenge_tm", "challenge_suivi", "londres")
NETTOYAGE = "2026-11-26"


DEBUT_TEST = "2026-11-20T16:20:00Z"  # début du test de 2 semaines (17 h 20 à Paris), compte démo ramené à ~98 €


def repartir_du_test(donnees: dict):
    """Une seule fois : Mathis a baissé lui-même le solde démo (21 000 € -> ~98 €). Ce n'est pas une perte :
    les statistiques repartent du début du test, les anciens ordres sont mis de côté."""
    if donnees.get("debut_test") == DEBUT_TEST:
        return
    donnees["debut_test"] = DEBUT_TEST
    ordres = donnees.get("ordres", [])
    avant = [o for o in ordres if o.get("statut") == "ferme" and (o.get("ouvert_le") or "") < DEBUT_TEST]
    donnees.setdefault("ordres_avant_test", []).extend(avant)
    donnees["ordres"] = [o for o in ordres if o not in avant]
    donnees["historique"] = [h for h in donnees.get("historique", []) if h["date"] >= DEBUT_TEST]
    donnees["historique_jour"] = {}
    donnees.pop("valeur_depart", None)
    if donnees["historique"]:
        donnees["valeur_depart"] = donnees["historique"][0]["valeur"]
    g = donnees.get("garde_fous", {})
    g.pop("jour", None)
    g["plus_haut"] = 0
    g["coupe_circuit"] = False


def lire_activites(api, donnees: dict, positions: list) -> list:
    """Historique Capital.com des dernières heures, seulement s'il y a une fermeture à vérifier
    (position disparue, ou résultat encore estimé) : donne le VRAI prix de sortie au stop."""
    ouverts = {p["position"]["dealId"] for p in positions}
    limite = (datetime.now(timezone.utc) - timedelta(hours=20)).strftime("%Y-%m-%dT%H:%M:%S")
    a_verifier = [o for o in donnees.get("ordres", [])
                  if (o.get("statut") == "ouvert" and o["id"] not in ouverts)
                  or (o.get("statut") == "ferme" and o.get("resultat_estime") and (o.get("ferme_le") or "") >= limite)]
    if not a_verifier or not hasattr(api, "activites"):
        return []
    fin = datetime.now(timezone.utc)
    for heures in (20, 4):  # si la période est refusée, on réessaie plus court
        try:
            return api.activites((fin - timedelta(hours=heures)).strftime("%Y-%m-%dT%H:%M:%S"),
                                 fin.strftime("%Y-%m-%dT%H:%M:%S"))
        except Exception as e:  # pas bloquant : on garde l'estimation
            print(f"Historique Capital.com indisponible ({heures} h) : {e}")
    return []


def strategie_de(p: dict, ids_rapide: set) -> str:
    """Stratégie qui a ouvert une position Capital.com."""
    if p["position"]["dealId"] in ids_rapide:
        return "rapide"
    return "cassure_4h" if p["market"]["epic"] in MARCHES_CASSURE else "autre"


def nettoyer_une_fois(donnees: dict, noter):
    """26/11/2026 : efface de data.json ce que les stratégies retirées y avaient laissé.
    L'historique des ordres, le journal et la courbe du compte sont gardés."""
    if donnees.get("nettoyage") == NETTOYAGE:
        return
    donnees["nettoyage"] = NETTOYAGE
    for k in ANCIENNES_CLES:
        donnees.pop(k, None)
    donnees.get("entrees", {}).pop("BTCUSD", None)
    dps = donnees.get("deals_par_strategie", {})
    for k in [k for k in dps if k != "cassure"]:
        del dps[k]
    marches_r = donnees.get("rapide", {}).get("marches", {})
    for m in [m for m in marches_r if m not in module_rapide.LISTE]:
        del marches_r[m]  # ex. l'argent, retiré de la Rapide le 25/11
    noter("commande", "", "Nettoyage (26/11/2026, demande de Mathis) : le bot repart avec seulement la Cassure 4 h "
          "(or, argent) et la Rapide 5 min (or), plus les garde-fous. Élan, Supertrend, usine, Avant la Fed, veille "
          "d'actus, simulateur et Tendance Bitcoin sont retirés. Sauvegarde : branche « sauvegarde-26-11 ».")


def un_tour(donnees: dict, api: CapitalDemo, action: str = "", strategie: str = "toutes"):
    journal = donnees.setdefault("journal", [])

    def noter(type_, marche, texte, strat=None):
        ligne = {"date": maintenant(), "type": type_, "marche": marche, "texte": texte}
        if strat:
            ligne["strategie"] = strat
        journal.append(ligne)

    nettoyer_une_fois(donnees, noter)
    toutes = [s["id"] for s in STRATEGIES]
    noms = {s["id"]: s["nom"] for s in STRATEGIES}
    strategie = strategie if strategie in toutes else "toutes"
    cibles = toutes if strategie == "toutes" else [strategie]
    etats = donnees.setdefault("strategies", {})
    for k in [k for k in etats if k not in toutes]:
        del etats[k]  # stratégies retirées : plus affichées dans l'appli
    for s in STRATEGIES:
        etats.setdefault(s["id"], {}).setdefault("active", s["active"])
    if set(donnees.get("rapide", {}).get("deals", [])) and "marches" not in donnees["rapide"]:
        donnees["rapide"] = {"deals": []}  # ancienne rapide du Bitcoin : on repart de zéro
    lancer = set(cibles) if action == "lancer" else set()

    api.connexion()
    positions = api.positions()
    ids_rapide = set(donnees.get("rapide", {}).get("deals", []))
    strat_de = lambda p: strategie_de(p, ids_rapide)

    # --- Commandes envoyées depuis l'application (téléphone, tablette, PC) ---
    if action == "pause":
        donnees["pause"] = True
        noter("commande", "", "Bot mis en pause depuis l'application : il surveille mais ne passe plus d'ordres.")
    elif action == "reprendre":
        donnees["pause"] = False
        noter("commande", "", "Bot relancé depuis l'application.")
    elif action in ("activer", "desactiver"):
        for c in cibles:
            etats[c]["active"] = action == "activer"
        mot = "activée" if action == "activer" else "désactivée (elle garde ses positions, le stop suiveur continue)"
        noter("commande", "", f"Stratégie {' et '.join(noms[c] for c in cibles)} {mot} depuis l'application.")
    elif action == "lancer":
        noter("commande", "", f"Tour immédiat demandé pour : {', '.join(noms[c] for c in cibles)}.")
    elif action == "fermer":
        if strategie == "toutes":
            donnees["pause"] = True
        # « toutes » : on ferme TOUT ce qui est ouvert sur le compte, quel que soit le marché
        for p in [p for p in positions if strategie == "toutes" or strat_de(p) in cibles]:
            conf = api.fermer(p["position"]["dealId"])
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, maintenant(), "Fermée depuis l'application")
            noter("fermeture", p["market"]["epic"], f"Position fermée depuis l'application (gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}", strat_de(p))
        if strategie == "toutes":
            noter("commande", "", "Positions fermées et bot mis en pause. Appuie sur « Reprendre » pour le relancer.")
        else:
            etats[strategie]["active"] = False
            noter("commande", "", f"Positions de la stratégie {noms[strategie]} fermées, stratégie désactivée.")
        positions = api.positions()
    elif action == "analyser":
        noter("commande", "", "Analyse demandée depuis l'application.")
    en_pause = donnees.get("pause", False)

    compte0 = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    capital = float(compte0.get("balance", {}).get("balance") or 0)
    disponible = float(compte0.get("balance", {}).get("available") or capital)
    eurusd = api.taux_eurusd()
    # Capital.com : « balance » contient DÉJÀ le gain/perte latent (balance = deposit + profitLoss).
    # Ne jamais lui ajouter profitLoss (erreur corrigée le 25/11 : les hausses et baisses étaient doublées).
    garde = GardeFous(donnees, capital, positions, eurusd)
    if action == "reprendre":
        garde.rearmer()
    instant = datetime.now(timezone.utc)
    souci = actualites.mettre_a_jour(donnees, instant)
    if souci:
        noter("erreur", "", souci)
    garde.pause_actualite = actualites.annonce_en_cours(donnees, instant)
    donnees["actualites"]["pause"] = garde.pause_actualite
    donnees["actualites"]["prochaines"] = actualites.prochaines(donnees, instant)
    garde.pauses_marches = actualites.pauses_marches(donnees, instant)
    donnees["actualites"]["pauses_marches"] = garde.pauses_marches
    if garde.pause_actualite and donnees.get("_derniere_pause_notee") != garde.pause_actualite:
        noter("analyse", "", f"Pause : {garde.pause_actualite}. Aucune nouvelle position de "
              f"{actualites.PAUSE_AVANT_MIN} min avant à {actualites.PAUSE_APRES_MIN} min après.")
    donnees["_derniere_pause_notee"] = garde.pause_actualite
    api.sans_couverture()  # le stop garanti est interdit en mode couverture (hedging)

    # --- Chaque stratégie, dans l'ordre de STRATEGIES ---
    # Active : elle entre et sort. Désactivée : elle gère seulement ses positions (stop, sorties).
    # Pause générale : rien du tout, sauf « Lancer maintenant » depuis l'appli.
    ctx = {"positions": positions, "capital": capital, "disponible": disponible, "eurusd": eurusd, "garde": garde}
    for s in STRATEGIES:
        sid = s["id"]
        actif = (sid in lancer) or (not en_pause and etats[sid]["active"])
        if actif or not en_pause:
            ctx["noter"] = lambda t, m, x, sid=sid: noter(t, m, x, sid)
            s["tour"](api, donnees, ctx, actif)
        etats[sid].update({"nom": s["nom"], **s["fiche"](),
                           "action": "Actif" if actif else ("En pause" if en_pause else "Désactivée")})
    donnees.pop("_cache_marches", None)

    # État final du compte, après les ordres
    compte = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    solde = compte.get("balance", {})
    positions = api.positions()
    activites = lire_activites(api, donnees, positions)
    api.deconnexion()
    synchroniser(donnees, positions, maintenant(), activites, eurusd)
    ids_rapide = set(donnees.get("rapide", {}).get("deals", []))
    for o in donnees.get("ordres", []):
        if o["id"] in ids_rapide:
            o["strategie"] = "rapide"
        o.setdefault("strategie", "cassure_4h" if o["marche"] in MARCHES_CASSURE else "autre")
        if o.get("statut") == "ouvert" and "reglages" not in o:
            # réglages en vigueur à l'ouverture (auto-amélioration : on ne mélange jamais avant / après un changement)
            o["reglages"] = reglages_du_moment(o["strategie"])
    # Garde-fou : 3 stops perdants d'affilée sur une stratégie et un marché -> pause de 24 h pour ce couple
    surveiller_series_de_stops(donnees, maintenant(), noter)

    donnees["compte"] = {
        "nom": compte.get("accountName", "Démo"),
        "devise": compte.get("currency", ""),
        "solde": solde.get("balance"),
        "depot": solde.get("deposit"),
        "resultat_latent": solde.get("profitLoss"),
        "disponible": solde.get("available"),
    }
    donnees["positions"] = [
        {
            "marche": p["market"]["epic"],
            "nom": p["market"].get("instrumentName", p["market"]["epic"]),
            "sens": p["position"]["direction"],
            "taille": p["position"]["size"],
            "prix_entree": p["position"]["level"],
            "resultat": p["position"].get("upl"),
            "ouverte_le": p["position"].get("createdDateUTC"),
            # vrais niveaux chez Capital.com, pour les lignes du graphique de l'appli
            "id": p["position"]["dealId"],
            "stop": p["position"].get("stopLevel"),
            "stop_garanti": bool(p["position"].get("guaranteedStop")),
            "objectif": p["position"].get("profitLevel"),
            "strategie": strat_de(p),
        }
        for p in positions
    ]
    try:  # graphiques de l'appli (indicateurs, signaux, conditions) : n'influence aucune décision
        module_graphiques.publier(donnees, getattr(api, "vues", {}))
    except Exception as e:
        print(f"Graphiques non mis à jour : {e}")
    historique = donnees.setdefault("historique", [])
    if solde.get("balance") is not None:
        valeur = round(solde["balance"], 2)  # « balance » inclut déjà le latent (voir plus haut)
        historique.append({"date": maintenant(), "valeur": valeur})
        donnees.setdefault("historique_jour", {})[maintenant()[:10]] = valeur
        donnees.setdefault("valeur_depart", historique[0]["valeur"])


def principal() -> int:
    donnees = charger()
    donnees["reglages"] = {"strategies": [s["id"] for s in STRATEGIES],
                           "marches": sorted(set(MARCHES_CASSURE) | set(module_rapide.LISTE))}
    donnees.setdefault("journal", [])
    code = 0

    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    repartir_du_test(donnees)
    if not (cle and ident and mdp):
        msg = "Les secrets CAPITAL_API_KEY, CAPITAL_IDENTIFIER et CAPITAL_PASSWORD ne sont pas encore configurés sur GitHub."
        donnees["journal"].append({"date": maintenant(), "type": "erreur", "marche": "", "texte": msg})
        print(msg)
        code = 1
    else:
        try:
            un_tour(donnees, CapitalDemo(cle, ident, mdp), os.getenv("ACTION", "").strip().lower(),
                    os.getenv("STRATEGIE", "toutes").strip().lower() or "toutes")
            donnees["statut"] = "ok"
        except (ErreurCapital, Exception) as e:  # on garde une trace lisible de toute erreur
            donnees["journal"].append({"date": maintenant(), "type": "erreur", "marche": "", "texte": str(e)[:400]})
            donnees["statut"] = "erreur"
            print(f"ERREUR : {e}")
            code = 1

    donnees["derniere_execution"] = maintenant()
    donnees["journal"] = donnees["journal"][-MAX_JOURNAL:]
    donnees["historique"] = donnees.get("historique", [])[-MAX_HISTORIQUE:]
    jours = donnees.get("historique_jour", {})
    donnees["historique_jour"] = dict(sorted(jours.items())[-MAX_JOURS:])
    sauver(donnees)
    for ligne in donnees["journal"][-5:]:
        print(ligne["date"], ligne["type"], ligne["marche"], ligne["texte"])
    return code


if __name__ == "__main__":
    sys.exit(principal())

"""Un tour de bot : se connecte au compte DÉMO Capital.com, analyse le marché,
passe les ordres si besoin, puis met à jour docs/data.json pour le tableau de bord.

GitHub lance ce fichier automatiquement toutes les 5 minutes environ.
Lancement manuel :  python -m bot.main
"""
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bot.capital import CapitalDemo, ErreurCapital
from bot.rapide import ACTIVE as RAPIDE_ACTIVE
from bot.rapide import NOM as NOM_RAPIDE
from bot.rapide import RISQUE_RAPIDE_PCT, UNITE_RAPIDE
from bot.rapide import tour_rapide
from bot.garde_fous import GardeFous
from bot import actualites
from bot.sous_bots import LISTE as SOUS_BOTS
from bot.sous_bots import NOM as NOM_SB
from bot.sous_bots import RISQUE_SOUS_BOT_PCT, tour_sous_bot
from bot.cassure import LISTE as MARCHES_CASSURE
from bot.cassure import NOM as NOM_CASSURE
from bot.cassure import RISQUE_CASSURE_PCT, tour_cassure
from bot import cassure as module_cassure
from bot import tendance_mois as module_tm
from bot.registre import mettre_a_jour_prix, noter_fermeture, synchroniser
from bot.strategie import NOM as NOM_STRATEGIE
from bot.strategie import EMA_LENTE, EMA_RAPIDE, bougies_vers_df, decider

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "docs" / "data.json"

# Réglages (modifiables dans .github/workflows/bot.yml sans toucher au code)
MARCHES = [m.strip() for m in os.getenv("MARCHES", "BTCUSD").split(",") if m.strip()]
UNITE = os.getenv("UNITE", "HOUR_4")  # bougies de 4 h : c'est l'unité testée en backtest
RISQUE_PCT = float(os.getenv("RISQUE_PCT", "1"))  # % du capital perdu au maximum si le stop est touché
NB_BOUGIES = 1000  # ~5 mois de bougies 4 h, pour que l'EMA 200 soit fiable
STOP_GARANTI_MIN_PCT = 0.55  # Capital.com impose un stop garanti à 0,5 % minimum du prix (+ marge)
PAS_TAILLE = 0.0001  # plus petite taille de position en BTC chez Capital.com
TP_PARTIEL_ATR = float(os.getenv("TP_PARTIEL_ATR", "1"))  # moitié de la position avec un TP à N × ATR (0 = aucun)
MARGE = 0.5  # levier crypto 2:1 en Europe : il faut bloquer 50 % de la valeur

MAX_JOURNAL = 1000
MAX_HISTORIQUE = 3000  # ~1 mois de points à raison d'un toutes les 15 min
MAX_JOURS = 3650  # un point par jour, sur 10 ans
MAX_BOUGIES_GRAPHIQUE = 96  # 16 jours en bougies de 4 h


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


DESCRIPTION_SB = ("Un sous-bot par action ou ETF : il n'achète que si l'analyse technique (~20 indicateurs) "
                  "donne un achat fort dans une tendance haussière, avec SL garanti et TP.")
DESCRIPTION_CASSURE = ("Un sous-bot pour l'or et un pour l'argent : il achète quand le prix casse le plus haut "
                       "des 20 dernières bougies de 4 h (vend sous le plus bas), dans le sens de l'EMA 200, "
                       "avec stop garanti. Environ 4 trades par mois.")
DESCRIPTIONS = {
    "tendance_4h": "Suit les grosses tendances du Bitcoin sur des bougies de 4 h : peu de trades, la seule gagnante en backtest.",
    "rapide": "Trade souvent sur des bougies de 5 min avec un tout petit risque, pour comparer en direct (perdante en backtest).",
}


def un_tour(donnees: dict, api: CapitalDemo, action: str = "", strategie: str = "toutes"):
    journal = donnees.setdefault("journal", [])

    def noter(type_, marche, texte, strat=None):
        ligne = {"date": maintenant(), "type": type_, "marche": marche, "texte": texte}
        if strat:
            ligne["strategie"] = strat
        journal.append(ligne)

    noter_4h = lambda t, m, x: noter(t, m, x, "tendance_4h")
    noter_rapide = lambda t, m, x: noter(t, m, x, "rapide")

    toutes = ["tendance_4h", "rapide", "actions_etf", "cassure_4h", "petit_compte", "tendance_mois", "x5_or", "x5_argent", "cassure_tous"]
    strategie = strategie if strategie in toutes else "toutes"
    cibles = toutes if strategie == "toutes" else [strategie]
    etats = donnees.setdefault("strategies", {})
    etats.setdefault("tendance_4h", {}).setdefault("active", True)
    etats.setdefault("rapide", {}).setdefault("active", RAPIDE_ACTIVE)
    etats.setdefault("actions_etf", {}).setdefault("active", True)
    etats.setdefault("cassure_4h", {}).setdefault("active", True)
    etats.setdefault("petit_compte", {}).setdefault("active", module_cassure.PETIT_COMPTE)
    etats.setdefault("tendance_mois", {}).setdefault("active", module_tm.ACTIVE_PAR_DEFAUT)
    etats.setdefault("x5_or", {}).setdefault("active", module_cassure.X5_OR)
    etats.setdefault("x5_argent", {}).setdefault("active", module_cassure.X5_ARGENT)
    etats.setdefault("cassure_tous", {}).setdefault("active", module_cassure.CASSURE_TOUS)
    noms = {"tendance_4h": "Tendance 4 h", "rapide": "Rapide 5 min", "actions_etf": "Sous-bots actions et ETF",
            "cassure_4h": "Cassure 4 h (or et argent)", "petit_compte": "Petit compte risqué (100 €)",
            "tendance_mois": "Tendance 1 mois (11 marchés)",
            "x5_or": "Objectif x5 sur l'or (50 €)", "x5_argent": "Objectif x5 sur l'argent (50 €)",
            "cassure_tous": "Cassure 4 h (tous les marchés)"}
    lancer = set(cibles) if action == "lancer" else set()

    api.connexion()
    positions = api.positions()
    ids_rapide = set(donnees.get("rapide", {}).get("deals", []))
    ids_petit = set(donnees.get("deals_par_strategie", {}).get("petit_compte", []))
    ids_tm = set(donnees.get("deals_par_strategie", {}).get("tendance_mois", []))
    ids_x5 = set(donnees.get("deals_par_strategie", {}).get("x5_or", []))
    ids_x5a = set(donnees.get("deals_par_strategie", {}).get("x5_argent", []))
    ids_ct = set(donnees.get("deals_par_strategie", {}).get("cassure_tous", []))
    strat_de = lambda p: ("tendance_mois" if p["position"]["dealId"] in ids_tm else
                          "cassure_tous" if p["position"]["dealId"] in ids_ct else
                          "x5_or" if p["position"]["dealId"] in ids_x5 else
                          "x5_argent" if p["position"]["dealId"] in ids_x5a else
                          "actions_etf" if p["market"]["epic"] in SOUS_BOTS else
                          "petit_compte" if p["position"]["dealId"] in ids_petit else
                          "cassure_4h" if p["market"]["epic"] in MARCHES_CASSURE else
                          "rapide" if p["position"]["dealId"] in ids_rapide else "tendance_4h")

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
    analyses = {}

    compte0 = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    capital = float(compte0.get("balance", {}).get("balance") or 0)
    disponible = float(compte0.get("balance", {}).get("available") or capital)
    eurusd = api.taux_eurusd()
    valeur = capital + float(compte0.get("balance", {}).get("profitLoss") or 0)
    garde = GardeFous(donnees, valeur, positions, eurusd)
    # Devise de chaque marché ouvert hors dollar (DAX en €, USD/JPY en yens) : sinon le risque total serait faux
    for p in positions:
        epic = p["market"]["epic"]
        if epic in module_tm.LISTE and epic not in garde.taux:
            try:
                regles = module_cassure.regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
                garde.taux[epic] = module_cassure.taux_devise(regles, eurusd, float(p["position"]["level"]))
            except Exception:
                pass
    if action == "reprendre":
        garde.rearmer()
    instant = datetime.now(timezone.utc)
    souci = actualites.mettre_a_jour(donnees, instant)
    if souci:
        noter("erreur", "", souci)
    garde.pause_actualite = actualites.annonce_en_cours(donnees, instant)
    donnees["actualites"]["pause"] = garde.pause_actualite
    donnees["actualites"]["prochaines"] = actualites.prochaines(donnees, instant)
    if garde.pause_actualite and donnees.get("_derniere_pause_notee") != garde.pause_actualite:
        noter("analyse", "", f"Pause : {garde.pause_actualite}. Aucune nouvelle position de "
              f"{actualites.PAUSE_AVANT_MIN} min avant à {actualites.PAUSE_APRES_MIN} min après.")
    donnees["_derniere_pause_notee"] = garde.pause_actualite
    # Qui a le droit de trader à ce tour ? (la pause globale passe avant tout, sauf « lancer »)
    complet_4h = ("tendance_4h" in lancer) or (not en_pause and etats["tendance_4h"]["active"])
    suivi_4h = complet_4h or not en_pause  # désactivée : plus d'entrées ni de sorties, mais le stop suiveur continue
    tourne_rapide = ("rapide" in lancer) or (not en_pause and etats["rapide"]["active"])
    api.sans_couverture()  # le stop garanti est interdit en mode couverture (hedging)
    entrees = donnees.setdefault("entrees", {})  # bougie du dernier signal utilisé, par marché
    precedentes = donnees.get("analyses", {})

    for epic in MARCHES:
        bougies = api.bougies(epic, UNITE, NB_BOUGIES)
        fermees = bougies[:-1]  # la dernière bougie n'est pas encore terminée
        df = bougies_vers_df(fermees)
        signal = decider(df)
        prix = milieu(bougies[-1]["closePrice"]) if bougies else None
        prix_achat = bougies[-1]["closePrice"]["ask"] if bougies else None
        prix_vente = bougies[-1]["closePrice"]["bid"] if bougies else None
        sig = signal["sig"]

        mes_positions = [p for p in positions if p["market"]["epic"] == epic and p["position"]["dealId"] not in ids_rapide
                         and p["position"]["dealId"] not in ids_tm]
        voulu = signal["direction"]
        action = "Aucune action"
        deja_note = precedentes.get(epic, {}).get("explication") == signal["explication"]

        if not suivi_4h:
            action = "En pause (aucun ordre)"
        elif sig is None:
            noter_4h("info", epic, signal["explication"])
        else:
            if not complet_4h:
                action = "Désactivée (positions gardées, stop suiveur actif)"
            # 1) Sortie : la tendance n'est plus dans le sens de la position
            for p in [p for p in mes_positions if p["position"]["direction"] != voulu and complet_4h]:
                conf = api.fermer(p["position"]["dealId"])
                if conf.get("dealStatus") == "ACCEPTED":
                    noter_fermeture(donnees, p, conf, maintenant(), "Fin de la tendance (signal de sortie)")
                sens = "achat" if p["position"]["direction"] == "BUY" else "vente"
                noter_4h("fermeture", epic, f"{signal['explication']} Position à l'{sens} fermée (gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
                action = "Position fermée"
            gardees = [p for p in mes_positions if p["position"]["direction"] == voulu or not complet_4h]

            # 2) Stop suiveur : on rapproche le stop pour verrouiller les gains (jamais l'inverse)
            derniere = sig.iloc[-1]
            for p in gardees:
                pos = p["position"]
                actuel = pos.get("stopLevel")
                marge_mini = prix * STOP_GARANTI_MIN_PCT / 100
                if pos["direction"] == "BUY":
                    cible_stop = min(derniere.cloture - derniere.suivi, prix_vente - marge_mini)
                    mieux = actuel is None or cible_stop > float(actuel) + 1
                else:
                    cible_stop = max(derniere.cloture + derniere.suivi, prix_achat + marge_mini)
                    mieux = actuel is None or cible_stop < float(actuel) - 1
                if mieux:
                    conf = api.modifier_stop(pos["dealId"], cible_stop, bool(pos.get("guaranteedStop", True)))
                    ok = conf.get("dealStatus") == "ACCEPTED"
                    noter_4h("stop" if ok else "erreur", epic,
                          f"Stop suiveur déplacé de {float(actuel or 0):.2f} à {cible_stop:.2f} pour protéger le gain." if ok
                          else f"Déplacement du stop refusé : {conf.get('reason', conf.get('dealStatus', '?'))}")
                    action = "Stop remonté" if ok else action
                if action == "Aucune action":
                    action = "Position conservée"

            # 3) Entrée : seulement sur un signal NOUVEAU, jamais deux fois le même
            if not complet_4h:
                pass
            elif voulu and not gardees:
                if not signal["nouveau"]:
                    if not deja_note:
                        noter_4h("analyse", epic, f"{signal['explication']} Mais le signal n'est pas récent (il date du "
                              f"{signal['debut_etat'][:16]}) : on attend le prochain pour ne pas entrer en retard.")
                elif entrees.get(epic) == signal["debut_etat"]:
                    if not deja_note:
                        noter_4h("analyse", epic, "Ce signal a déjà été utilisé (position fermée par le stop) : on attend un nouveau signal.")
                else:
                    mot = "ACHAT" if voulu == "BUY" else "VENTE"
                    prix_entree = prix_achat if voulu == "BUY" else prix_vente
                    distance = max(float(derniere.stop), prix_entree * STOP_GARANTI_MIN_PCT / 100)
                    risque_usd = capital * RISQUE_PCT / 100 * eurusd
                    taille = math.floor(risque_usd / distance / PAS_TAILLE) * PAS_TAILLE
                    taille_marge = math.floor(disponible * eurusd / (prix_entree * MARGE) * 0.9 / PAS_TAILLE) * PAS_TAILLE
                    taille = round(min(taille, taille_marge), 4)
                    autorise, raison = garde.autoriser(taille * distance / eurusd, distance)
                    if taille < PAS_TAILLE:
                        noter_4h("erreur", epic, f"Capital trop faible pour ouvrir la plus petite position ({PAS_TAILLE} BTC).")
                    elif not autorise:
                        noter_4h("analyse", epic, f"{signal['explication']} Ordre REFUSÉ par les garde-fous : {raison}.")
                        action = "Refusé (garde-fous)"
                    else:
                        garde.enregistrer({"position": {"level": prix_entree, "stopLevel": prix_entree - distance, "size": taille}})
                        # Sans mode couverture, un ordre inverse annulerait les positions de la rapide :
                        # la stratégie 4 h est prioritaire, on ferme d'abord celles qui sont en sens inverse.
                        for p in [p for p in positions if p["market"]["epic"] == epic
                                  and p["position"]["dealId"] in ids_rapide and p["position"]["direction"] != voulu]:
                            conf = api.fermer(p["position"]["dealId"])
                            if conf.get("dealStatus") == "ACCEPTED":
                                noter_fermeture(donnees, p, conf, maintenant(), "Fermée : la stratégie 4 h est prioritaire")
                            noter("fermeture", epic, "Position de la stratégie rapide fermée : la stratégie 4 h, prioritaire, "
                                  "ouvre dans l'autre sens.", "rapide")
                        # Deux moitiés : l'une avec un TP proche (on encaisse vite), l'autre sans TP
                        # qui suit la tendance avec le stop suiveur (on capte les gros mouvements).
                        moitie = round(math.floor(taille / 2 / PAS_TAILLE) * PAS_TAILLE, 4)
                        tp = float(derniere.atr) * TP_PARTIEL_ATR if TP_PARTIEL_ATR > 0 and moitie >= PAS_TAILLE else None
                        parts = [(moitie, tp), (round(taille - moitie, 4), None)] if tp else [(taille, None)]
                        for t, obj in parts:
                            conf = api.ouvrir(epic, voulu, t, prix=prix_entree, stop_distance=distance, garanti=True,
                                              objectif_distance=obj)
                            statut = conf.get("dealStatus", "?")
                            if statut == "ACCEPTED":
                                entrees[epic] = signal["debut_etat"]
                                action = f"{mot} de {taille} {epic}"
                                texte_tp = f", TP à +{obj:.0f} $" if obj else ", sans TP (stop suiveur)"
                                noter_4h("ordre", epic, f"{signal['explication']} Ordre {mot} de {t} passé à "
                                      f"{float(conf.get('level') or prix_entree):.2f}, stop garanti à {distance:.0f} $"
                                      f"{texte_tp} (risque max ≈ {t * distance / eurusd:.2f} €).")
                            else:
                                noter_4h("erreur", epic, f"Ordre {mot} refusé par Capital.com : {conf.get('reason', statut)}")
            elif not voulu and (not deja_note or "tendance_4h" in lancer):
                noter_4h("analyse", epic, signal["explication"])
            if "tendance_4h" in lancer and action in ("Aucune action", "Position conservée"):
                noter_4h("analyse", epic, f"Tour immédiat : {signal['explication']} Décision : {action.lower()}.")

        clotures = list(sig.cloture) if sig is not None else [milieu(b["closePrice"]) for b in fermees]
        ema_r = [None if x != x else round(float(x), 2) for x in sig.ema_rapide] if sig is not None else []
        ema_l = [None if x != x else round(float(x), 2) for x in sig.ema_lente] if sig is not None else []
        if tourne_rapide:
            try:
                positions_now = api.positions()
                action_rapide = tour_rapide(api, donnees, epic, positions_now, capital, eurusd, noter_rapide, maintenant(), garde)
            except Exception as e:  # une erreur de la rapide ne doit pas bloquer la stratégie 4 h
                action_rapide = "Erreur"
                noter_rapide("erreur", epic, f"[Rapide] {str(e)[:300]}")
            if "rapide" in lancer:
                noter_rapide("analyse", epic, f"Tour immédiat de la stratégie rapide. Décision : {action_rapide.lower()}.")
        else:
            action_rapide = "En pause (aucun ordre)" if en_pause else "Désactivée"
        donnees.setdefault("rapide", {})["action"] = action_rapide
        etats["tendance_4h"].update({"nom": noms["tendance_4h"], "description": DESCRIPTIONS["tendance_4h"],
                                     "unite": UNITE, "risque_pct": RISQUE_PCT, "action": action, "tendance": voulu,
                                     "reglages": NOM_STRATEGIE})
        etats["rapide"].update({"nom": noms["rapide"], "description": DESCRIPTIONS["rapide"], "unite": UNITE_RAPIDE,
                                "risque_pct": RISQUE_RAPIDE_PCT, "action": action_rapide,
                                "tendance": donnees.get("rapide", {}).get("tendance"), "reglages": NOM_RAPIDE})

        mettre_a_jour_prix(donnees, epic, prix)
        n = MAX_BOUGIES_GRAPHIQUE
        analyses[epic] = {
            "prix": prix,
            "tendance": voulu,
            "explication": signal["explication"],
            "action": action,
            "graphique": {
                "dates": [b["snapshotTimeUTC"] for b in fermees][-n:],
                "clotures": clotures[-n:],
                "ema_rapide": ema_r[-n:],
                "ema_lente": ema_l[-n:],
            },
        }

    # --- Sous-bots actions et ETF : un par marché ---
    actif_sb = ("actions_etf" in lancer) or (not en_pause and etats["actions_etf"]["active"])
    if actif_sb or not en_pause:
        noter_sb = lambda t, m, x: noter(t, m, x, "actions_etf")
        # positions des autres stratégies (repérées par numéro) : les sous-bots ne les gèrent pas
        ids_autres = {d for ids in donnees.get("deals_par_strategie", {}).values() for d in ids}
        for epic in SOUS_BOTS:
            try:
                tour_sous_bot(api, donnees, epic, positions, capital, disponible, eurusd, noter_sb, garde,
                              maintenant(), peut_entrer=actif_sb, autres_ids=ids_autres)
            except Exception as e:  # un marché en erreur ne bloque pas les autres
                donnees.setdefault("sous_bots", {}).setdefault(epic, {})["action"] = "Erreur"
                noter_sb("erreur", epic, str(e)[:300])
    etats["actions_etf"].update({"nom": noms["actions_etf"], "description": DESCRIPTION_SB, "unite": "HOUR_4",
                                 "risque_pct": RISQUE_SOUS_BOT_PCT, "reglages": NOM_SB, "marches": SOUS_BOTS,
                                 "action": "Actif" if actif_sb else ("En pause" if en_pause else "Désactivée")})

    # --- Cassure 4 h : un sous-bot par marché (or et argent) ---
    actif_c = ("cassure_4h" in lancer) or (not en_pause and etats["cassure_4h"]["active"])
    if actif_c or not en_pause:
        noter_c = lambda t, m, x: noter(t, m, x, "cassure_4h")
        for epic in MARCHES_CASSURE:
            try:
                tour_cassure(api, donnees, epic, positions, capital, disponible, eurusd, noter_c, garde,
                             maintenant(), peut_entrer=actif_c)
            except Exception as e:  # un marché en erreur ne bloque pas les autres
                donnees.setdefault("cassure", {}).setdefault(epic, {})["action"] = "Erreur"
                noter_c("erreur", epic, str(e)[:300])
    etats["cassure_4h"].update({"nom": noms["cassure_4h"], "description": DESCRIPTION_CASSURE, "unite": "HOUR_4",
                                "risque_pct": RISQUE_CASSURE_PCT, "reglages": NOM_CASSURE, "marches": MARCHES_CASSURE,
                                "action": "Actif" if actif_c else ("En pause" if en_pause else "Désactivée")})

    # --- Cassure 4 h sur tous les autres marchés : petit risque, analyse du marché avant chaque entrée ---
    actif_ct = ("cassure_tous" in lancer) or (not en_pause and etats["cassure_tous"]["active"])
    if (actif_ct or not en_pause) and (actif_ct or ids_ct):
        noter_ct = lambda t, m, x: noter(t, m, f"[Cassure tous marchés] {x}", "cassure_tous")
        hors_liste_ct = sorted({p["market"]["epic"] for p in positions if p["position"]["dealId"] in ids_ct}
                               - set(module_cassure.LISTE_TOUS))
        for epic in module_cassure.LISTE_TOUS + hors_liste_ct:
            try:
                tour_cassure(api, donnees, epic, positions, capital, disponible, eurusd, noter_ct, garde,
                             maintenant(), peut_entrer=actif_ct and epic in module_cassure.LISTE_TOUS, cle="cassure_tous",
                             risque_pct=module_cassure.RISQUE_CASSURE_TOUS_PCT, analyse=module_cassure.analyse_cassure)
            except Exception as e:
                donnees.setdefault("cassure_tous", {}).setdefault(epic, {})["action"] = "Erreur"
                noter_ct("erreur", epic, str(e)[:300])
    etats["cassure_tous"].update({
        "nom": noms["cassure_tous"], "unite": "HOUR_4", "risque_pct": module_cassure.RISQUE_CASSURE_TOUS_PCT,
        "description": ("La cassure 4 h sur tous les autres marchés (actions, ETF, indices, devises, crypto, pétrole). "
                        "Avant chaque entrée, le bot rejoue la stratégie sur les 12 derniers mois de ce marché et "
                        "ne trade que s'il y a gagné. Petit risque."),
        "reglages": NOM_CASSURE, "marches": module_cassure.LISTE_TOUS,
        "action": "Actif" if actif_ct else ("En pause" if en_pause else "Désactivée")})

    # --- Petit compte risqué : même cassure, capital virtuel de 100 €, risque élevé, suivi à part ---
    actif_p = ("petit_compte" in lancer) or (not en_pause and etats["petit_compte"]["active"])
    capital_p = module_cassure.capital_petit_compte(donnees)
    if (actif_p or not en_pause) and (actif_p or ids_petit):
        noter_p = lambda t, m, x: noter(t, m, f"[Petit compte] {x}", "petit_compte")
        for epic in MARCHES_CASSURE:
            try:
                tour_cassure(api, donnees, epic, positions, capital_p, disponible, eurusd, noter_p, garde,
                             maintenant(), peut_entrer=actif_p and capital_p > 0, cle="petit_compte",
                             risque_pct=module_cassure.PETIT_RISQUE_PCT)
            except Exception as e:
                donnees.setdefault("petit_compte", {}).setdefault(epic, {})["action"] = "Erreur"
                noter_p("erreur", epic, str(e)[:300])
    etats["petit_compte"].update({
        "nom": noms["petit_compte"], "unite": "HOUR_4", "risque_pct": module_cassure.PETIT_RISQUE_PCT,
        "description": (f"Expérience : la cassure or + argent sur un capital VIRTUEL de "
                        f"{module_cassure.PETIT_CAPITAL_DEPART:g} € avec {module_cassure.PETIT_RISQUE_PCT:g} % de "
                        "risque par trade. Ordres réels sur le compte démo, résultats comptés à part."),
        "reglages": NOM_CASSURE, "marches": MARCHES_CASSURE,
        "capital_depart": module_cassure.PETIT_CAPITAL_DEPART,
        "action": "Actif" if actif_p else ("En pause" if en_pause else "Désactivée")})

    # --- Tendance 1 mois : un sous-bot par marché (12 marchés), décision sur les bougies jour ---
    actif_tm = ("tendance_mois" in lancer) or (not en_pause and etats["tendance_mois"]["active"])
    if (actif_tm or not en_pause) and (actif_tm or ids_tm):
        noter_tm = lambda t, m, x: noter(t, m, f"[Tendance 1 mois] {x}", "tendance_mois")
        # marchés de la liste + ceux où elle a encore une position (retirés de la liste : gérés jusqu'à la sortie)
        hors_liste = sorted({p["market"]["epic"] for p in positions if p["position"]["dealId"] in ids_tm} - set(module_tm.LISTE))
        for epic in module_tm.LISTE + hors_liste:
            try:
                tour_cassure(api, donnees, epic, positions, capital, disponible, eurusd, noter_tm, garde,
                             maintenant(), peut_entrer=actif_tm and epic in module_tm.LISTE, cle="tendance_mois",
                             risque_pct=module_tm.RISQUE_TENDANCE_MOIS_PCT, signaux=module_tm.signaux_tendance,
                             unite=module_tm.UNITE, analyse=module_tm.analyse_tendance if module_tm.ANALYSER else None)
            except Exception as e:
                donnees.setdefault("tendance_mois", {}).setdefault(epic, {})["action"] = "Erreur"
                noter_tm("erreur", epic, str(e)[:300])
    etats["tendance_mois"].update({
        "nom": noms["tendance_mois"], "unite": "DAY", "risque_pct": module_tm.RISQUE_TENDANCE_MOIS_PCT,
        "description": ("Un sous-bot par marché (or, argent, ETH, Nasdaq, S&P 500, DAX, pétrole, 4 devises) : "
                        "acheteur si le prix est plus haut qu'il y a 30 jours, vendeur sinon, stop garanti. "
                        "Test 2 ans : +2 403 € puis +1 054 €, pire baisse -7 %, ~20 trades/mois."),
        "reglages": module_tm.NOM, "marches": module_tm.LISTE,
        "action": "Actif" if actif_tm else ("En pause" if en_pause else "Désactivée")})

    # --- Objectif x5 (loterie) : capital virtuel de 50 € par marché, levier max, TP ≈ x5 / stop garanti ≈ -50 % ---
    for sid, epic, lev, obj, stop, test in module_cassure.X5_ESSAIS:
        ids_sid = set(donnees.get("deals_par_strategie", {}).get(sid, []))
        actif_x5 = (sid in lancer) or (not en_pause and etats[sid]["active"])
        capital_x5 = module_cassure.capital_petit_compte(donnees, sid, module_cassure.X5_CAPITAL_DEPART)
        if (actif_x5 or not en_pause) and (actif_x5 or ids_sid):
            noter_x5 = lambda t, m, x, sid=sid: noter(t, m, f"[Objectif x5] {x}", sid)
            try:
                # risque = levier × distance du stop (ex. 20 × 2,5 % = 50 % du capital virtuel si le stop est touché)
                tour_cassure(api, donnees, epic, positions, capital_x5, disponible, eurusd, noter_x5, garde,
                             maintenant(), peut_entrer=actif_x5 and capital_x5 > 5, cle=sid, risque_pct=lev * stop,
                             stop_pct=stop, objectif_pct=obj, sortie_signal=False)
            except Exception as e:
                donnees.setdefault(sid, {}).setdefault(epic, {})["action"] = "Erreur"
                noter_x5("erreur", epic, str(e)[:300])
        etats[sid].update({
            "nom": noms[sid], "unite": "HOUR_4", "risque_pct": lev * stop,
            "description": (f"Loterie en démo : capital VIRTUEL de {module_cassure.X5_CAPITAL_DEPART:g} €, levier 1:"
                            f"{lev:g}, entrée sur une cassure 4 h. Objectif +{obj:g} % du prix (x5), stop garanti "
                            f"-{stop:g} % (moitié du capital). {test}"),
            "reglages": NOM_CASSURE, "marches": [epic], "capital_depart": module_cassure.X5_CAPITAL_DEPART,
            "action": "Actif" if actif_x5 else ("En pause" if en_pause else "Désactivée")})
    donnees.pop("_cache_marches", None)

    # État final du compte, après les ordres
    compte = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    solde = compte.get("balance", {})
    positions = api.positions()
    api.deconnexion()
    synchroniser(donnees, positions, maintenant())
    ids_rapide = set(donnees.get("rapide", {}).get("deals", []))
    etats["petit_compte"]["capital"] = module_cassure.capital_petit_compte(donnees)
    for sid, *_ in module_cassure.X5_ESSAIS:
        etats[sid]["capital"] = module_cassure.capital_petit_compte(donnees, sid, module_cassure.X5_CAPITAL_DEPART)
    ids_petit = set(donnees.get("deals_par_strategie", {}).get("petit_compte", []))
    ids_tm = set(donnees.get("deals_par_strategie", {}).get("tendance_mois", []))
    for o in donnees.get("ordres", []):
        if o["id"] in ids_petit:
            o["strategie"] = "petit_compte"
        if o["id"] in ids_tm:
            o["strategie"] = "tendance_mois"
        if o["id"] in set(donnees.get("deals_par_strategie", {}).get("cassure_tous", [])):
            o["strategie"] = "cassure_tous"
        for sid, *_ in module_cassure.X5_ESSAIS:
            if o["id"] in set(donnees.get("deals_par_strategie", {}).get(sid, [])):
                o["strategie"] = sid
        if "strategie" not in o:
            o["strategie"] = ("actions_etf" if o["marche"] in SOUS_BOTS else
                              "cassure_4h" if o["marche"] in MARCHES_CASSURE else
                              "rapide" if o["id"] in ids_rapide else "tendance_4h")

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
        }
        for p in positions
    ]
    donnees["analyses"] = analyses
    historique = donnees.setdefault("historique", [])
    if solde.get("balance") is not None:
        valeur = round(solde["balance"] + (solde.get("profitLoss") or 0), 2)
        historique.append({"date": maintenant(), "valeur": valeur})
        donnees.setdefault("historique_jour", {})[maintenant()[:10]] = valeur
        donnees.setdefault("valeur_depart", historique[0]["valeur"])


def principal() -> int:
    donnees = charger()
    donnees["reglages"] = {"marches": MARCHES, "unite": UNITE, "risque_pct": RISQUE_PCT,
                           "strategie": NOM_STRATEGIE, "ema": [EMA_RAPIDE, EMA_LENTE], "strategie_rapide": NOM_RAPIDE if RAPIDE_ACTIVE else None}
    donnees.setdefault("journal", [])
    code = 0

    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
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

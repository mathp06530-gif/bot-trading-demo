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
from bot.rapide import tour_rapide
from bot.registre import mettre_a_jour_prix, noter_fermeture, synchroniser
from bot.strategie import NOM as NOM_STRATEGIE
from bot.strategie import bougies_vers_df, decider

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "docs" / "data.json"

# Réglages (modifiables dans .github/workflows/bot.yml sans toucher au code)
MARCHES = [m.strip() for m in os.getenv("MARCHES", "BTCUSD").split(",") if m.strip()]
UNITE = os.getenv("UNITE", "HOUR_4")  # bougies de 4 h : c'est l'unité testée en backtest
RISQUE_PCT = float(os.getenv("RISQUE_PCT", "1"))  # % du capital perdu au maximum si le stop est touché
NB_BOUGIES = 1000  # ~5 mois de bougies 4 h, pour que l'EMA 200 soit fiable
STOP_GARANTI_MIN_PCT = 0.55  # Capital.com impose un stop garanti à 0,5 % minimum du prix (+ marge)
PAS_TAILLE = 0.0001  # plus petite taille de position en BTC chez Capital.com
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


def un_tour(donnees: dict, api: CapitalDemo, action: str = ""):
    journal = donnees.setdefault("journal", [])
    noter = lambda type_, marche, texte: journal.append({"date": maintenant(), "type": type_, "marche": marche, "texte": texte})

    api.connexion()
    positions = api.positions()

    # --- Commandes envoyées depuis l'application (téléphone, tablette, PC) ---
    if action == "pause":
        donnees["pause"] = True
        noter("commande", "", "Bot mis en pause depuis l'application : il surveille mais ne passe plus d'ordres.")
    elif action == "reprendre":
        donnees["pause"] = False
        noter("commande", "", "Bot relancé depuis l'application.")
    elif action == "fermer":
        donnees["pause"] = True
        for p in [p for p in positions if p["market"]["epic"] in MARCHES]:
            conf = api.fermer(p["position"]["dealId"])
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, maintenant(), "Fermée depuis l'application")
            noter("fermeture", p["market"]["epic"], f"Position fermée depuis l'application (gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
        noter("commande", "", "Positions fermées et bot mis en pause. Appuie sur « Reprendre » pour le relancer.")
        positions = api.positions()
    elif action == "analyser":
        noter("commande", "", "Analyse demandée depuis l'application.")
    en_pause = donnees.get("pause", False)
    analyses = {}

    compte0 = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    capital = float(compte0.get("balance", {}).get("balance") or 0)
    disponible = float(compte0.get("balance", {}).get("available") or capital)
    eurusd = api.taux_eurusd()
    couverture = api.mode_couverture() if RAPIDE_ACTIVE else False
    ids_rapide = set(donnees.get("rapide", {}).get("deals", []))
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

        mes_positions = [p for p in positions if p["market"]["epic"] == epic and p["position"]["dealId"] not in ids_rapide]
        voulu = signal["direction"]
        action = "Aucune action"
        deja_note = precedentes.get(epic, {}).get("explication") == signal["explication"]

        if en_pause:
            action = "En pause (aucun ordre)"
        elif sig is None:
            noter("info", epic, signal["explication"])
        else:
            # 1) Sortie : la tendance n'est plus dans le sens de la position
            for p in [p for p in mes_positions if p["position"]["direction"] != voulu]:
                conf = api.fermer(p["position"]["dealId"])
                if conf.get("dealStatus") == "ACCEPTED":
                    noter_fermeture(donnees, p, conf, maintenant(), "Fin de la tendance (signal de sortie)")
                sens = "achat" if p["position"]["direction"] == "BUY" else "vente"
                noter("fermeture", epic, f"{signal['explication']} Position à l'{sens} fermée (gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
                action = "Position fermée"
            gardees = [p for p in mes_positions if p["position"]["direction"] == voulu]

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
                    noter("stop" if ok else "erreur", epic,
                          f"Stop suiveur déplacé de {float(actuel or 0):.2f} à {cible_stop:.2f} pour protéger le gain." if ok
                          else f"Déplacement du stop refusé : {conf.get('reason', conf.get('dealStatus', '?'))}")
                    action = "Stop remonté" if ok else action
                if action == "Aucune action":
                    action = "Position conservée"

            # 3) Entrée : seulement sur un signal NOUVEAU, jamais deux fois le même
            if voulu and not gardees:
                if not signal["nouveau"]:
                    if not deja_note:
                        noter("analyse", epic, f"{signal['explication']} Mais le signal n'est pas récent (il date du "
                              f"{signal['debut_etat'][:16]}) : on attend le prochain pour ne pas entrer en retard.")
                elif entrees.get(epic) == signal["debut_etat"]:
                    if not deja_note:
                        noter("analyse", epic, "Ce signal a déjà été utilisé (position fermée par le stop) : on attend un nouveau signal.")
                else:
                    mot = "ACHAT" if voulu == "BUY" else "VENTE"
                    prix_entree = prix_achat if voulu == "BUY" else prix_vente
                    distance = max(float(derniere.stop), prix_entree * STOP_GARANTI_MIN_PCT / 100)
                    risque_usd = capital * RISQUE_PCT / 100 * eurusd
                    taille = math.floor(risque_usd / distance / PAS_TAILLE) * PAS_TAILLE
                    taille_marge = math.floor(disponible * eurusd / (prix_entree * MARGE) * 0.9 / PAS_TAILLE) * PAS_TAILLE
                    taille = round(min(taille, taille_marge), 4)
                    if taille < PAS_TAILLE:
                        noter("erreur", epic, f"Capital trop faible pour ouvrir la plus petite position ({PAS_TAILLE} BTC).")
                    else:
                        conf = api.ouvrir(epic, voulu, taille, prix=prix_entree, stop_distance=distance, garanti=True)
                        statut = conf.get("dealStatus", "?")
                        action = f"{mot} de {taille} {epic}"
                        if statut == "ACCEPTED":
                            entrees[epic] = signal["debut_etat"]
                            risque = taille * distance / eurusd
                            noter("ordre", epic, f"{signal['explication']} Ordre {mot} de {taille} passé à "
                                  f"{float(conf.get('level') or prix_entree):.2f}, stop garanti à {distance:.0f} $ "
                                  f"(risque max ≈ {risque:.2f} €, soit {RISQUE_PCT:g} % du capital).")
                        else:
                            noter("erreur", epic, f"Ordre {mot} refusé par Capital.com : {conf.get('reason', statut)}")
            elif not voulu and not deja_note:
                noter("analyse", epic, signal["explication"])

        clotures = list(sig.cloture) if sig is not None else [milieu(b["closePrice"]) for b in fermees]
        ema_r = [None if x != x else round(float(x), 2) for x in sig.ema_rapide] if sig is not None else []
        ema_l = [None if x != x else round(float(x), 2) for x in sig.ema_lente] if sig is not None else []
        if RAPIDE_ACTIVE and not en_pause:
            if couverture:
                action_rapide = tour_rapide(api, donnees, epic, positions, capital, eurusd, noter, maintenant())
            else:
                action_rapide = "Impossible : le mode couverture (hedging) n'a pas pu être activé"
            donnees.setdefault("rapide", {})["action"] = action_rapide

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

    # État final du compte, après les ordres
    compte = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    solde = compte.get("balance", {})
    positions = api.positions()
    api.deconnexion()
    synchroniser(donnees, positions, maintenant())
    ids_rapide = set(donnees.get("rapide", {}).get("deals", []))
    for o in donnees.get("ordres", []):
        if "strategie" not in o:
            o["strategie"] = "rapide" if o["id"] in ids_rapide else "tendance_4h"

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
                           "strategie": NOM_STRATEGIE, "strategie_rapide": NOM_RAPIDE if RAPIDE_ACTIVE else None}
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
            un_tour(donnees, CapitalDemo(cle, ident, mdp), os.getenv("ACTION", "").strip().lower())
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

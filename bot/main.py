"""Un tour de bot : se connecte au compte DÉMO Capital.com, analyse le marché,
passe les ordres si besoin, puis met à jour docs/data.json pour le tableau de bord.

GitHub lance ce fichier automatiquement toutes les 15 minutes environ.
Lancement manuel :  python -m bot.main
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from bot.capital import CapitalDemo, ErreurCapital
from bot.registre import mettre_a_jour_prix, noter_fermeture, synchroniser
from bot.strategie import EMA_LENTE, EMA_RAPIDE, decider

RACINE = Path(__file__).resolve().parent.parent
FICHIER_DONNEES = RACINE / "docs" / "data.json"

# Réglages (modifiables dans .github/workflows/bot.yml sans toucher au code)
MARCHES = [m.strip() for m in os.getenv("MARCHES", "BTCUSD").split(",") if m.strip()]
TAILLE = float(os.getenv("TAILLE", "0.01"))
UNITE = os.getenv("UNITE", "MINUTE_15")
STOP_PCT = float(os.getenv("STOP_PCT", "3"))  # stop de sécurité en % du prix (0 = aucun)

MAX_JOURNAL = 300
MAX_HISTORIQUE = 3000  # ~1 mois de points à raison d'un toutes les 15 min
MAX_JOURS = 3650  # un point par jour, sur 10 ans
MAX_BOUGIES_GRAPHIQUE = 96  # 24 h en bougies de 15 min


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


def taille_valide(api: CapitalDemo, epic: str) -> float:
    """Respecte la taille minimale imposée par Capital.com pour ce marché."""
    try:
        mini = api.marche(epic)["dealingRules"]["minDealSize"]["value"]
        return max(TAILLE, float(mini))
    except Exception:
        return TAILLE


def un_tour(donnees: dict, api: CapitalDemo):
    journal = donnees.setdefault("journal", [])
    noter = lambda type_, marche, texte: journal.append({"date": maintenant(), "type": type_, "marche": marche, "texte": texte})

    api.connexion()
    positions = api.positions()
    analyses = {}

    for epic in MARCHES:
        bougies = api.bougies(epic, UNITE, 200)
        fermees = bougies[:-1]  # la dernière bougie n'est pas encore terminée
        clotures = [milieu(b["closePrice"]) for b in fermees]
        signal = decider(clotures)
        prix = milieu(bougies[-1]["closePrice"]) if bougies else None

        mes_positions = [p for p in positions if p["market"]["epic"] == epic]
        voulu = signal["direction"]
        action = "Aucune action"

        if voulu is None:
            noter("info", epic, signal["explication"])
        else:
            a_fermer = [p for p in mes_positions if p["position"]["direction"] != voulu]
            for p in a_fermer:
                conf = api.fermer(p["position"]["dealId"])
                if conf.get("dealStatus") == "ACCEPTED":
                    noter_fermeture(donnees, p, conf, maintenant(), "Signal inverse de la stratégie")
                sens = "achat" if p["position"]["direction"] == "BUY" else "vente"
                noter("fermeture", epic, f"Position à l'{sens} fermée (gain/perte : {p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
            deja_bon = any(p["position"]["direction"] == voulu for p in mes_positions)
            if not deja_bon:
                taille = taille_valide(api, epic)
                conf = api.ouvrir(epic, voulu, taille, STOP_PCT, prix)
                mot = "ACHAT" if voulu == "BUY" else "VENTE"
                statut = conf.get("dealStatus", "?")
                action = f"{mot} de {taille} {epic}"
                if statut == "ACCEPTED":
                    noter("ordre", epic, f"{signal['explication']} Ordre {mot} de {taille} passé à {float(conf.get('level') or prix):.2f}.")
                else:
                    noter("erreur", epic, f"Ordre {mot} refusé par Capital.com : {conf.get('reason', statut)}")
            else:
                action = "Position conservée"
                noter("analyse", epic, f"{signal['explication']} On garde la position.")

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
                "ema_rapide": signal["ema_rapide"][-n:],
                "ema_lente": signal["ema_lente"][-n:],
            },
        }

    # État final du compte, après les ordres
    compte = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    solde = compte.get("balance", {})
    positions = api.positions()
    api.deconnexion()
    synchroniser(donnees, positions, maintenant())

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
    donnees["reglages"] = {"marches": MARCHES, "taille": TAILLE, "unite": UNITE, "stop_pct": STOP_PCT,
                           "strategie": f"Croisement EMA {EMA_RAPIDE} / EMA {EMA_LENTE}"}
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
            un_tour(donnees, CapitalDemo(cle, ident, mdp))
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

"""« CHALLENGE PROP FIRM » en direct sur le compte démo (essai demandé par Mathis le 20/11/2026).

On joue un faux challenge de société de trading (« prop firm ») avec un capital VIRTUEL :
  - capital de départ : CHALLENGE_CAPITAL (10 000 €, comme un petit challenge FTMO) ;
  - RÉUSSI si la valeur atteint +CHALLENGE_OBJECTIF_PCT (10 %) ;
  - RATÉ si elle perd CHALLENGE_PERTE_JOUR_PCT (5 % du capital de départ) dans une même journée (heure de Paris),
    ou si elle tombe à -CHALLENGE_PERTE_MAX_PCT (10 %) du capital de départ.
Quand une tentative se termine, toutes ses positions sont fermées. Une nouvelle tentative démarre
le lendemain, pour compter combien de fois le bot réussit.

Stratégies jouées : nos deux stratégies qui tiennent en backtest, avec des tailles calculées sur le capital virtuel :
  - la cassure 4 h sur l'or et l'argent (clé « challenge »),
  - la tendance 1 mois sur 11 marchés (clé « challenge_tm »).
Les ordres sont réels sur le compte DÉMO, les résultats sont comptés à part. Ce n'est pas une vraie prop firm.
"""
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ACTIVE_PAR_DEFAUT = os.getenv("CHALLENGE", "non").strip().lower() in ("oui", "1", "true", "on")
CAPITAL = float(os.getenv("CHALLENGE_CAPITAL", "10000"))
OBJECTIF_PCT = float(os.getenv("CHALLENGE_OBJECTIF_PCT", "10"))
PERTE_JOUR_PCT = float(os.getenv("CHALLENGE_PERTE_JOUR_PCT", "5"))
PERTE_MAX_PCT = float(os.getenv("CHALLENGE_PERTE_MAX_PCT", "10"))
RISQUE_CASSURE_PCT = float(os.getenv("CHALLENGE_RISQUE_CASSURE_PCT", "0.5"))
RISQUE_TENDANCE_PCT = float(os.getenv("CHALLENGE_RISQUE_TENDANCE_PCT", "0.4"))
CLES = ("challenge", "challenge_tm")
PARIS = ZoneInfo("Europe/Paris")


def ids_challenge(donnees: dict) -> set:
    dps = donnees.get("deals_par_strategie", {})
    return {d for c in CLES for d in dps.get(c, [])}


def _realise(donnees: dict, ids: set) -> float:
    return sum(float(o.get("resultat") or 0) for o in donnees.get("ordres", [])
               if o["id"] in ids and o.get("statut") == "ferme")


def _latent(positions: list, ids: set) -> float:
    return sum(float(p["position"].get("upl") or 0) for p in positions if p["position"]["dealId"] in ids)


def _jour(quand: str) -> str:
    return datetime.fromisoformat(quand.replace("Z", "+00:00")).astimezone(PARIS).date().isoformat()


def _nouvelle(e: dict, donnees: dict, quand: str, ids: set):
    e.update({"tentative": len(e.get("tentatives", [])) + 1, "statut": "en cours", "debut": quand, "fin": None,
              "base_realise": round(_realise(donnees, ids), 2), "jour": _jour(quand), "debut_jour": CAPITAL,
              "valeur": CAPITAL, "plus_bas": CAPITAL, "plus_haut": CAPITAL, "a_fermer": False})


def suivre(donnees: dict, positions: list, quand: str, actif: bool) -> dict:
    """Met à jour la tentative en cours et applique les règles. Renvoie l'état (« statut », « a_fermer »…).
    À appeler APRÈS synchroniser(), pour que les positions fermées par un stop soient déjà comptées."""
    e = donnees.setdefault("challenge_suivi", {"tentatives": []})
    e.setdefault("tentatives", [])
    ids = ids_challenge(donnees)
    jour = _jour(quand)
    if "statut" not in e:
        if not actif:
            return e
        _nouvelle(e, donnees, quand, ids)
    elif e["statut"] != "en cours" and not e.get("a_fermer") and actif and jour > _jour(e["fin"]):
        _nouvelle(e, donnees, quand, ids)  # une nouvelle tentative le lendemain d'une tentative finie
    if e["statut"] != "en cours":
        return e
    valeur = round(CAPITAL + _realise(donnees, ids) - e["base_realise"] + _latent(positions, ids), 2)
    if jour != e["jour"]:
        e.update({"jour": jour, "debut_jour": e["valeur"]})  # valeur à minuit (heure de Paris)
    e.update({"valeur": valeur, "plus_bas": min(e["plus_bas"], valeur), "plus_haut": max(e["plus_haut"], valeur)})
    fin = None
    if valeur >= CAPITAL * (1 + OBJECTIF_PCT / 100):
        fin = ("réussi", f"objectif +{OBJECTIF_PCT:g} % atteint")
    elif valeur <= CAPITAL * (1 - PERTE_MAX_PCT / 100):
        fin = ("raté", f"perte maximale de {PERTE_MAX_PCT:g} % atteinte")
    elif valeur <= e["debut_jour"] - CAPITAL * PERTE_JOUR_PCT / 100:
        fin = ("raté", f"perte de {PERTE_JOUR_PCT:g} % dans la journée")
    if fin:
        jours = (datetime.fromisoformat(quand.replace("Z", "+00:00"))
                 - datetime.fromisoformat(e["debut"].replace("Z", "+00:00"))).total_seconds() / 86400
        e.update({"statut": fin[0], "raison": fin[1], "fin": quand, "a_fermer": True})
        e["tentatives"].append({"n": e["tentative"], "debut": e["debut"], "fin": quand, "statut": fin[0],
                                "raison": fin[1], "resultat": round(valeur - CAPITAL, 2), "jours": round(jours, 1)})
    return e


def bilan(e: dict) -> dict:
    t = e.get("tentatives", [])
    return {"tentatives_finies": len(t), "reussies": sum(1 for x in t if x["statut"] == "réussi"),
            "ratees": sum(1 for x in t if x["statut"] == "raté")}

"""Registre de tous les ordres passés par le bot (ouverts et fermés).

Chaque position Capital.com devient une ligne dans donnees["ordres"], avec son prix
d'entrée, son prix de sortie et son résultat. C'est ce qui alimente l'onglet « Ordres »
et les statistiques du tableau de bord.
"""


def _trouver(ordres: list, deal_id: str):
    return next((o for o in ordres if o["id"] == deal_id), None)


def noter_fermeture(donnees: dict, position: dict, conf: dict, quand: str, motif: str):
    """Le bot vient de fermer lui-même cette position."""
    ordres = donnees.setdefault("ordres", [])
    pos, marche = position["position"], position["market"]
    ordre = _trouver(ordres, pos["dealId"])
    if ordre is None:
        ordre = _depuis_position(position)
        ordres.append(ordre)
    sortie = conf.get("level") or (marche.get("offer") if pos["direction"] == "SELL" else marche.get("bid"))
    ordre.update({
        "statut": "ferme",
        "ferme_le": quand,
        "prix_sortie": sortie,
        "resultat": pos.get("upl"),
        "resultat_estime": False,
        "motif_sortie": motif,
    })


def synchroniser(donnees: dict, positions: list, quand: str):
    """Ajoute les nouvelles positions et repère celles fermées sans le bot (stop touché…)."""
    ordres = donnees.setdefault("ordres", [])
    ids_ouverts = set()
    for p in positions:
        deal_id = p["position"]["dealId"]
        ids_ouverts.add(deal_id)
        ordre = _trouver(ordres, deal_id)
        if ordre is None:
            ordres.append(_depuis_position(p))
        else:
            ordre["resultat"] = p["position"].get("upl")  # résultat en cours, mis à jour à chaque tour

    for o in ordres:
        if o["statut"] == "ouvert" and o["id"] not in ids_ouverts:
            # Fermée par Capital.com (stop) ou à la main : on estime avec le dernier prix vu,
            # sauf si ce prix avait déjà franchi le stop (le stop garanti a alors joué à son niveau).
            sens = 1 if o["sens"] == "BUY" else -1
            dernier, stop = o.get("dernier_prix"), o.get("stop")
            if dernier and stop and (dernier - stop) * sens <= 0:
                sortie = stop
            else:
                sortie = dernier or stop or o["prix_entree"]
            o.update({
                "statut": "ferme",
                "ferme_le": quand,
                "prix_sortie": sortie,
                "resultat": round((sortie - o["prix_entree"]) * o["taille"] * sens, 2),
                "resultat_estime": True,
                "motif_sortie": "Stop de sécurité ou fermeture manuelle",
            })


def mettre_a_jour_prix(donnees: dict, epic: str, prix: float | None):
    for o in donnees.get("ordres", []):
        if o["statut"] == "ouvert" and o["marche"] == epic and prix:
            o["dernier_prix"] = prix


def _depuis_position(p: dict) -> dict:
    pos, marche = p["position"], p["market"]
    return {
        "id": pos["dealId"],
        "marche": marche["epic"],
        "nom": marche.get("instrumentName", marche["epic"]),
        "sens": pos["direction"],
        "taille": pos["size"],
        "prix_entree": pos["level"],
        "stop": pos.get("stopLevel"),
        "stop_garanti": bool(pos.get("guaranteedStop")),
        "ouvert_le": (pos.get("createdDateUTC") or "")[:19] + "Z" if pos.get("createdDateUTC") else None,
        "statut": "ouvert",
        "resultat": pos.get("upl"),
        "ferme_le": None,
        "prix_sortie": None,
        "motif_sortie": None,
    }

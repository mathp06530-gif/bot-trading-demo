"""CHALLENGE PROP FIRM SIMULÉ sur les vrais résultats de la Super IA (aucun ordre, rien à payer).

Idée (vidéo « $0 to $1M FUNDED ») : une prop firm prête un compte si on réussit un challenge.
Ici on rejoue ce challenge, en virtuel, avec les prédictions jugées en direct :

  - compte virtuel de 100 000 $, objectif +10 % ; raté si la perte du jour (Paris) dépasse 5 % du départ
    ou si le compte descend sous 90 % ; après chaque fin (réussi ou raté) une nouvelle tentative démarre ;
  - seulement les 8 marchés à petits frais (or, argent, pétrole, US100, US500, DE40, EUR/USD, GBP/USD),
    ceux qu'on trouve aussi chez les prop firms ;
  - chaque prédiction devient un trade de h minutes, VRAI spread du moment payé ;
    une seule position à la fois par marché, taille fixée pour risquer ~RISQUE du compte sur un mouvement
    habituel (mouvement connu AVANT la prédiction), levier plafonné à LEVIER_MAX ;
  - un témoin « hasard » (pile ou face) prend exactement les mêmes trades : la Super IA doit faire mieux que lui.

Rejeu complet à chaque lancement (archives ia-archives + juges.json) avec une Super IA neuve : mêmes règles que
ia/super_ia.py (attente de 68 min, rien du futur). Écrit challenge.json.
Limites : perte du jour comptée sur les trades fermés (pas sur le latent) ; phase 1 seulement.
"""
import gzip
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from super_ia import EQUIPES, HS, PARIS, SuperIA, iso  # noqa: E402

FUSEAU = ZoneInfo("Europe/Paris")
MARCHES = ["GOLD", "SILVER", "OIL_CRUDE", "US100", "US500", "DE40", "EURUSD", "GBPUSD"]
CAPITAL = 100_000.0
OBJECTIF, PERTE_JOUR, PERTE_MAX = 0.10, 0.05, 0.10
RISQUE = 0.005       # part du compte en jeu sur un mouvement habituel
LEVIER_MAX = 30.0
PRIX_CHALLENGE = 500  # € indicatifs par tentative (ordre de grandeur d'un challenge 100 k), jamais payé
VARIANTES = [f"{e}_{p}" for e in EQUIPES for p in PARIS] + ["hasard"]


def pile_ou_face(ident):
    return hashlib.sha256(ident.encode()).digest()[0] % 2 == 1


class Challenge:
    def __init__(self):
        self.tentatives = []
        self.ouvert = {}  # marché -> échéance de la position en cours
        self._nouvelle(None)

    def _nouvelle(self, t):
        self.c = {"debut": t, "fin": None, "resultat": "en_cours", "solde": CAPITAL, "trades": 0, "justes": 0,
                  "plus_haut": CAPITAL, "plus_bas": CAPITAL, "jour": None, "depart_jour": CAPITAL, "courbe": []}
        self.tentatives.append(self.c)

    def trade(self, it, hausse, taille):
        """taille = exposition en part du compte (1 = tout le compte)."""
        c, t = self.c, it["ech"]
        if c["debut"] is None:
            c["debut"] = t
        jour = datetime.fromtimestamp(t, FUSEAU).date().isoformat()
        if jour != c["jour"]:
            c["jour"], c["depart_jour"] = jour, c["solde"]
        gain = ((it["mv"] if hausse else -it["mv"]) - it["sp"]) / 100  # mv et sp sont en % du prix
        c["solde"] = round(c["solde"] + c["solde"] * taille * gain, 2)
        c["trades"] += 1
        c["justes"] += int(hausse == bool(it["up"]))
        c["plus_haut"], c["plus_bas"] = max(c["plus_haut"], c["solde"]), min(c["plus_bas"], c["solde"])
        c["courbe"].append([t, round(100 * (c["solde"] / CAPITAL - 1), 3)])
        fin = None
        if c["solde"] >= CAPITAL * (1 + OBJECTIF):
            fin = "reussi"
        elif c["solde"] <= CAPITAL * (1 - PERTE_MAX):
            fin = "rate_total"
        elif c["depart_jour"] - c["solde"] >= CAPITAL * PERTE_JOUR:
            fin = "rate_jour"
        if fin:
            c["resultat"], c["fin"] = fin, t
            self._nouvelle(None)
            self.ouvert = {}

    def resume(self):
        finies = [c for c in self.tentatives if c["resultat"] != "en_cours"]
        cours = self.tentatives[-1]
        n = sum(c["trades"] for c in self.tentatives)
        j = sum(c["justes"] for c in self.tentatives)
        reussis = sum(c["resultat"] == "reussi" for c in finies)
        return {
            "tentatives": len(finies), "reussis": reussis,
            "rates_jour": sum(c["resultat"] == "rate_jour" for c in finies),
            "rates_total": sum(c["resultat"] == "rate_total" for c in finies),
            "trades": n, "justes": j,
            "cout_virtuel": PRIX_CHALLENGE * (len(finies) + (1 if cours["trades"] else 0)),
            "en_cours": {k: cours[k] for k in ("debut", "solde", "trades", "justes", "plus_haut", "plus_bas")}
                        | {"progres": round(100 * (cours["solde"] / CAPITAL - 1), 3), "courbe": cours["courbe"][-300:]},
            "historique": [{k: c[k] for k in ("debut", "fin", "resultat", "solde", "trades", "justes")} for c in finies][-50:],
        }


class SuperIAChallenge(SuperIA):
    def __init__(self):
        super().__init__(None)
        self.ch = {str(h): {v: Challenge() for v in VARIANTES} for h in HS}

    def apprendre(self, it, preds):
        if it["e"] in MARCHES and it["h"] in HS:
            mvh = self.e.get("mouvement", {}).get(it["e"])  # mouvement habituel connu AVANT ce résultat
            if mvh and mvh[1] >= 2 and mvh[0] > 0:
                habituel = mvh[0] * math.sqrt(it["h"]) / 100
                taille = min(LEVIER_MAX, RISQUE / max(habituel, 1e-9))
                t0 = it["ech"] - 60 * it["h"]
                for v in VARIANTES:
                    ch = self.ch[str(it["h"])][v]
                    if v == "hasard":
                        pr = preds.get("fixe") or preds.get("evolutive")
                        if not pr:
                            continue
                        hausse = pile_ou_face(it["id"])
                    else:
                        equipe, pari = v.split("_")
                        pr = preds.get(equipe)
                        if not pr or (pari == "sure" and not pr["sure"]):
                            continue
                        hausse = pr["q"] > 0.5
                    if t0 < ch.ouvert.get(it["e"], 0):
                        continue  # déjà une position sur ce marché
                    ch.ouvert[it["e"]] = it["ech"]
                    ch.trade(it, hausse, taille)
        super().apprendre(it, preds)


def lire(entree):
    entree = Path(entree)
    items = {}
    for f in sorted((entree / "archives").rglob("*.jsonl.gz")):
        with gzip.open(f, "rt") as g:
            for ligne in g:
                if ligne.strip():
                    it = json.loads(ligne)
                    items[it["id"]] = it
    try:
        for it in json.loads((entree / "juges.json").read_text()).get("items", []):
            items[it["id"]] = it
    except Exception:
        pass
    return sorted(items.values(), key=lambda it: it["ech"])


def calculer(items, maintenant=None):
    s = SuperIAChallenge()
    s.traiter(items, maintenant or time.time())
    return {"maj": iso(), "regles": {"capital": CAPITAL, "objectif": OBJECTIF, "perte_jour": PERTE_JOUR,
                                     "perte_max": PERTE_MAX, "risque": RISQUE, "levier_max": LEVIER_MAX,
                                     "prix_challenge": PRIX_CHALLENGE, "marches": MARCHES},
            "premier": iso(items[0]["ech"]) if items else None, "resultats_lus": len(items),
            "horizons": HS, "variantes": VARIANTES,
            "stats": {h: {v: c.resume() for v, c in d.items()} for h, d in s.ch.items()}}


if __name__ == "__main__":
    entree = sys.argv[1] if len(sys.argv) > 1 else "entree"
    sortie = sys.argv[2] if len(sys.argv) > 2 else "sortie"
    res = calculer(lire(entree))
    Path(sortie).mkdir(parents=True, exist_ok=True)
    (Path(sortie) / "challenge.json").write_text(json.dumps(res, ensure_ascii=False, separators=(",", ":")))
    for h, d in res["stats"].items():
        print(h, "min :", ", ".join(f'{v} {x["reussis"]}/{x["tentatives"]} ({x["en_cours"]["progres"]:+.2f} %, {x["trades"]} trades)' for v, x in d.items()))

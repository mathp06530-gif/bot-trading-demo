"""GARDE-FOUS : règles strictes vérifiées AVANT chaque ouverture de position,
quelle que soit la stratégie (BTC 4 h, rapide, sous-bots actions et ETF).

Si UNE seule règle n'est pas respectée, l'ordre est REFUSÉ et la raison est écrite dans le journal.
Les sorties (stop, fin de tendance, fermeture manuelle) ne sont jamais bloquées : on peut toujours
réduire le risque, jamais l'augmenter au-delà des limites.

  1. COUPE-CIRCUIT   : si le compte a perdu plus de PERTE_MAX_PCT (10 %) depuis son plus haut,
                       plus aucune nouvelle position (il faut « Reprendre » à la main dans l'appli).
  2. PERTE DU JOUR   : si le compte a perdu plus de PERTE_JOUR_PCT (3 %) depuis le début de la
                       journée (UTC), plus de nouvelle position jusqu'au lendemain.
  3. POSITIONS MAX   : au plus POSITIONS_MAX (12) positions ouvertes en même temps.
  4. RISQUE TOTAL    : la somme des pertes possibles (si tous les stops sont touchés) ne doit
                       jamais dépasser RISQUE_TOTAL_PCT (6 %) du capital, nouvel ordre compris.
  5. UN PAR MARCHÉ   : une stratégie n'a jamais deux trades ouverts sur le même marché
                       (vérifié dans chaque stratégie).
  6. STOP OBLIGATOIRE: aucun ordre sans stop garanti (vérifié ici : distance > 0).
  8. ACTUALITÉ      : pas de nouvelle position autour d'une grande annonce américaine (bot/actualites.py).
  7. MARCHÉ OUVERT, SPREAD, ÂGE DU SIGNAL, ÉCART DE PRIX : vérifiés dans chaque sous-bot.
"""
import os
from datetime import datetime, timezone

PERTE_MAX_PCT = float(os.getenv("PERTE_MAX_PCT", "10"))
PERTE_JOUR_PCT = float(os.getenv("PERTE_JOUR_PCT", "3"))
POSITIONS_MAX = int(os.getenv("POSITIONS_MAX", "12"))
RISQUE_TOTAL_PCT = float(os.getenv("RISQUE_TOTAL_PCT", "6"))


class GardeFous:
    def __init__(self, donnees: dict, valeur_compte: float, positions: list, eurusd: float):
        self.etat = donnees.setdefault("garde_fous", {})
        self.valeur = float(valeur_compte or 0)
        self.positions = list(positions)
        self.eurusd = eurusd or 1.0
        self.pause_actualite = None
        self.taux = {}  # epic -> unités de la devise du marché pour 1 € (sinon EUR/USD)  # raison de la pause si une grande annonce est proche
        jour = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.etat.get("jour") != jour:
            self.etat["jour"] = jour
            self.etat["debut_jour"] = self.valeur
        self.etat["plus_haut"] = max(float(self.etat.get("plus_haut") or 0), self.valeur)
        if self.valeur < self.etat["plus_haut"] * (1 - PERTE_MAX_PCT / 100):
            self.etat["coupe_circuit"] = True
        self.etat["regles"] = {"perte_max_pct": PERTE_MAX_PCT, "perte_jour_pct": PERTE_JOUR_PCT,
                               "positions_max": POSITIONS_MAX, "risque_total_pct": RISQUE_TOTAL_PCT}

    def rearmer(self):
        """Appelé quand Mathis appuie sur « Reprendre » : le plus haut repart de la valeur actuelle."""
        self.etat["coupe_circuit"] = False
        self.etat["plus_haut"] = self.valeur

    def risque_ouvert_eur(self) -> float:
        total = 0.0
        for p in self.positions:
            pos = p["position"]
            if pos.get("stopLevel") is None:
                continue
            sens = -1 if pos.get("direction") == "SELL" else 1
            perte = (float(pos["level"]) - float(pos["stopLevel"])) * sens  # <= 0 si le stop protège déjà un gain
            taux = self.taux.get(p.get("market", {}).get("epic"), self.eurusd)
            total += max(perte, 0.0) * float(pos["size"]) / taux
        return total

    def autoriser(self, risque_eur: float, distance_stop: float) -> tuple[bool, str]:
        """Renvoie (True, "") si l'ordre respecte TOUTES les règles, sinon (False, raison)."""
        if not distance_stop or distance_stop <= 0:
            return False, "ordre refusé : pas de stop"
        if self.pause_actualite:
            return False, self.pause_actualite
        if self.etat.get("coupe_circuit"):
            return False, (f"COUPE-CIRCUIT : le compte a perdu plus de {PERTE_MAX_PCT:g} % depuis son plus haut. "
                           "Aucune nouvelle position tant que tu n'as pas appuyé sur « Reprendre ».")
        if self.valeur < float(self.etat.get("debut_jour") or self.valeur) * (1 - PERTE_JOUR_PCT / 100):
            return False, f"perte du jour supérieure à {PERTE_JOUR_PCT:g} % : plus de nouvelle position avant demain"
        if len(self.positions) >= POSITIONS_MAX:
            return False, f"déjà {len(self.positions)} positions ouvertes (maximum {POSITIONS_MAX})"
        risque_total = self.risque_ouvert_eur() + risque_eur
        if self.valeur and risque_total > self.valeur * RISQUE_TOTAL_PCT / 100:
            return False, (f"risque total trop élevé ({risque_total:.0f} € si tous les stops sont touchés, "
                           f"maximum {self.valeur * RISQUE_TOTAL_PCT / 100:.0f} €)")
        return True, ""

    def enregistrer(self, position_fictive: dict):
        """Ajoute la position qu'on vient d'ouvrir pour que les ordres suivants du même tour en tiennent compte."""
        self.positions.append(position_fictive)

"""Petit client pour l'API officielle de Capital.com (compte DÉMO uniquement).

Documentation : https://open-api.capital.com/
"""
import time

import requests

# Adresse du serveur DÉMO. Le bot ne connaît volontairement pas l'adresse du compte réel.
URL_DEMO = "https://demo-api-capital.backend-capital.com"


class ErreurCapital(Exception):
    pass


class CapitalDemo:
    def __init__(self, cle_api: str, identifiant: str, mot_de_passe: str):
        self.base = URL_DEMO + "/api/v1"
        self.cle_api = cle_api
        self.identifiant = identifiant
        self.mot_de_passe = mot_de_passe
        self.http = requests.Session()
        self.http.headers.update({"Content-Type": "application/json"})

    # --- Outils internes ---------------------------------------------------
    def _requete(self, methode: str, chemin: str, **kwargs):
        for essai in range(3):
            rep = self.http.request(methode, self.base + chemin, timeout=30, **kwargs)
            if rep.status_code == 429 and essai < 2:  # trop de requêtes : on patiente
                time.sleep(2 * (essai + 1))
                continue
            break
        if rep.status_code >= 400:
            raise ErreurCapital(f"{methode} {chemin} -> {rep.status_code} : {rep.text[:300]}")
        return rep.json() if rep.text else {}

    # --- Connexion ---------------------------------------------------------
    def connexion(self):
        rep = self.http.post(
            self.base + "/session",
            headers={"X-CAP-API-KEY": self.cle_api},
            json={"identifier": self.identifiant, "password": self.mot_de_passe, "encryptedPassword": False},
            timeout=30,
        )
        if rep.status_code >= 400:
            raise ErreurCapital(
                f"Connexion refusée ({rep.status_code}). Vérifie la clé API, l'e-mail et le mot de passe "
                f"de la clé dans les secrets GitHub. Détail : {rep.text[:200]}"
            )
        self.http.headers.update({"CST": rep.headers["CST"], "X-SECURITY-TOKEN": rep.headers["X-SECURITY-TOKEN"]})
        return rep.json()

    def deconnexion(self):
        try:
            self._requete("DELETE", "/session")
        except Exception:
            pass

    # --- Compte et marchés -------------------------------------------------
    def comptes(self):
        return self._requete("GET", "/accounts").get("accounts", [])

    def sans_couverture(self) -> bool:
        """Désactive le « hedging » : Capital.com refuse le stop GARANTI (obligatoire sur ce compte)
        quand ce mode est actif. Renvoie True si le mode est bien désactivé."""
        try:
            if self._requete("GET", "/accounts/preferences").get("hedgingMode"):
                self._requete("PUT", "/accounts/preferences", json={"hedgingMode": False})
            return True
        except ErreurCapital:
            return False

    def marche(self, epic: str):
        return self._requete("GET", f"/markets/{epic}")

    def bougies(self, epic: str, resolution: str = "MINUTE_15", nombre: int = 200):
        donnees = self._requete("GET", f"/prices/{epic}", params={"resolution": resolution, "max": nombre})
        return donnees.get("prices", [])

    # --- Positions ---------------------------------------------------------
    def positions(self):
        return self._requete("GET", "/positions").get("positions", [])

    def ouvrir(self, epic: str, direction: str, taille: float, stop_pct: float | None = None, prix: float | None = None,
               stop_distance: float | None = None, garanti: bool = False, objectif_distance: float | None = None):
        corps = {"epic": epic, "direction": direction, "size": taille}
        if objectif_distance:
            corps["profitDistance"] = round(objectif_distance, 2)  # prise de bénéfice (TP) chez Capital.com
        if stop_distance:
            corps["stopDistance"] = round(stop_distance, 2)
        elif stop_pct and prix:
            corps["stopDistance"] = round(prix * stop_pct / 100, 2)
        if garanti and prix:
            corps["guaranteedStop"] = True
            corps["stopDistance"] = max(corps.get("stopDistance", 0), self.distance_stop_garanti(epic, prix))
        try:
            ref = self._requete("POST", "/positions", json=corps)["dealReference"]
        except ErreurCapital as e:
            # Certains comptes européens exigent un « stop garanti » sur chaque position.
            if "guaranteed-stop" not in str(e) or not prix:
                raise
            corps["guaranteedStop"] = True
            corps["stopDistance"] = max(corps.get("stopDistance", 0), self.distance_stop_garanti(epic, prix))
            ref = self._requete("POST", "/positions", json=corps)["dealReference"]
        return self.confirmation(ref)

    def distance_stop_garanti(self, epic: str, prix: float) -> float:
        """Distance minimale autorisée pour un stop garanti (en prix), avec une petite marge."""
        try:
            regle = self.marche(epic)["dealingRules"]["minGuaranteedStopDistance"]
            valeur = float(regle["value"])
            distance = prix * valeur / 100 if regle.get("unit") == "PERCENTAGE" else valeur
            return round(distance * 1.1, 2)
        except Exception:
            return round(prix * 0.05, 2)

    def modifier_stop(self, deal_id: str, niveau: float, garanti: bool = True):
        """Déplace le stop d'une position ouverte (stop suiveur géré par le bot)."""
        corps = {"stopLevel": round(niveau, 2)}
        if garanti:
            corps["guaranteedStop"] = True
        ref = self._requete("PUT", f"/positions/{deal_id}", json=corps).get("dealReference")
        return self.confirmation(ref) if ref else {}

    def taux_eurusd(self) -> float:
        """Combien de dollars vaut 1 euro (pour convertir le risque en euros vers le BTCUSD)."""
        try:
            s = self.marche("EURUSD")["snapshot"]
            return (float(s["bid"]) + float(s["offer"])) / 2
        except Exception:
            return 1.08

    def fermer(self, deal_id: str):
        ref = self._requete("DELETE", f"/positions/{deal_id}").get("dealReference")
        return self.confirmation(ref) if ref else {}

    def confirmation(self, reference: str):
        # La confirmation peut mettre une seconde à arriver.
        for _ in range(5):
            try:
                return self._requete("GET", f"/confirms/{reference}")
            except ErreurCapital:
                time.sleep(1)
        return {"dealStatus": "INCONNU", "dealReference": reference}

from datetime import datetime, timezone

from bot import fed


def t(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


def test_phases_autour_de_l_annonce_du_9_decembre():
    d = ["2026-12-09"]  # annonce mercredi 9/12 à 14 h New York (19 h UTC en hiver)
    assert fed.phase(t("2026-12-08 18:30"), d) == ("rien", None)         # veille 13 h 30 New York
    assert fed.phase(t("2026-12-08 19:05"), d) == ("entrer", "2026-12-09")  # veille 14 h 05
    assert fed.phase(t("2026-12-08 23:30"), d) == ("garder", "2026-12-09")  # veille 18 h 30
    assert fed.phase(t("2026-12-09 18:40"), d) == ("garder", "2026-12-09")  # jour J 13 h 40
    assert fed.phase(t("2026-12-09 18:55"), d) == ("sortir", "2026-12-09")  # jour J 13 h 55 : juste avant
    assert fed.phase(t("2026-12-20 12:00"), d) == ("rien", None)


def test_veille_du_lundi_est_le_vendredi():
    assert fed.phase(t("2027-02-05 19:30"), ["2027-02-08"]) == ("entrer", "2027-02-08")


def test_atr_jour_ignore_la_bougie_du_jour():
    b = [{k: {"bid": 100.0, "ask": 100.0} for k in ("openPrice", "closePrice")} |
         {"highPrice": {"bid": 101.0, "ask": 101.0}, "lowPrice": {"bid": 99.0, "ask": 99.0}} for _ in range(30)]
    b[-1]["highPrice"] = {"bid": 200.0, "ask": 200.0}  # journée en cours énorme : ne doit pas compter
    assert abs(fed.atr_jour(b) - 2.0) < 1e-9


class FausseApi:
    def __init__(self):
        self.ouverts, self.fermes = [], []

    def marche(self, epic):
        return {"snapshot": {"marketStatus": "TRADEABLE"},
                "dealingRules": {"minDealSize": {"value": 0.001}, "minSizeIncrement": {"value": 0.001},
                                 "minGuaranteedStopDistance": {"unit": "PERCENTAGE", "value": 0.5}},
                "instrument": {"marginFactor": 5, "currency": "USD", "name": "US Tech 100"}}

    def bougies(self, epic, unite, n):
        p = lambda x: {"bid": x, "ask": x + 1}
        return [{"openPrice": p(21000), "closePrice": p(21000), "highPrice": p(21150), "lowPrice": p(20850)}] * n

    def ouvrir(self, epic, sens, taille, **k):
        self.ouverts.append((epic, sens, taille, k))
        return {"dealStatus": "ACCEPTED", "dealId": "D1", "level": 21001}

    def fermer(self, deal):
        self.fermes.append(deal)
        return {"dealStatus": "ACCEPTED"}


def test_achat_la_veille_puis_fermeture_avant_l_annonce(monkeypatch):
    monkeypatch.setattr(fed, "DATES", ["2026-12-09"])
    api, donnees, journal = FausseApi(), {}, []
    noter = lambda *a: journal.append(a)
    res = fed.tour_fed(api, donnees, "US100", [], 93.0, 90.0, 1.05, noter, None, "q", instant=t("2026-12-08 19:05"))
    assert res.startswith("ACHAT") and api.ouverts[0][1] == "BUY"
    assert abs(api.ouverts[0][3]["stop_distance"] - 300) < 1e-6  # 1 ATR jour
    pos = [{"market": {"epic": "US100"}, "position": {"dealId": "D1", "direction": "BUY", "upl": 0.4}}]
    # pas de 2e entrée pour la même annonce
    assert "cours" in fed.tour_fed(api, donnees, "US100", pos, 93.0, 90.0, 1.05, noter, None, "q",
                                   instant=t("2026-12-09 15:00"))
    monkeypatch.setattr(fed, "noter_fermeture", lambda *a: None)
    fed.tour_fed(api, donnees, "US100", pos, 93.0, 90.0, 1.05, noter, None, "q", instant=t("2026-12-09 18:52"))
    assert api.fermes == ["D1"]

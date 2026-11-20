from bot import londres as lo


def b(jour, h, haut, bas, cl):
    p = lambda x: {"bid": x - 0.005, "ask": x + 0.005}
    return {"snapshotTimeUTC": f"{jour}T{h:02d}:00:00", "highPrice": p(haut), "lowPrice": p(bas),
            "closePrice": p(cl), "openPrice": p(cl)}


class Faux:
    def __init__(self, bougies):
        self.b, self.ouverts, self.fermes = bougies, [], []

    def marche(self, epic):
        return {"dealingRules": {"minDealSize": {"value": 100}, "minSizeIncrement": {"value": 1},
                                 "minGuaranteedStopDistance": {"unit": "PERCENTAGE", "value": 0.1}},
                "instrument": {"marginFactor": 3.33, "name": "USD/JPY", "currency": "JPY"},
                "snapshot": {"marketStatus": "TRADEABLE"}}

    def bougies(self, epic, unite, n):
        return self.b

    def ouvrir(self, epic, sens, taille, prix=None, stop_distance=None, garanti=True):
        self.ouverts.append((sens, taille, stop_distance))
        return {"dealStatus": "ACCEPTED", "level": prix, "affectedDeals": [{"dealId": "L1"}]}

    def fermer(self, deal):
        self.fermes.append(deal)
        return {"dealStatus": "ACCEPTED", "level": 151}


class Garde:
    taux = {}
    def autoriser(self, risque, dist): return True, ""
    def enregistrer(self, p): pass


J = "2026-11-23"
NUIT = [b(J, h, 151.0, 150.0, 150.5) for h in range(7)]


def test_achat_quand_le_prix_sort_par_le_haut_puis_fermeture_a_20h():
    api = Faux(NUIT + [b(J, 7, 151.6, 150.9, 151.5), b(J, 8, 151.6, 151.5, 151.55)])
    d = {}
    lo.tour_londres(api, d, "USDJPY", [], 98, 98, 1.08, lambda *a: None, Garde(), f"{J}T08:05:00Z")
    assert api.ouverts and api.ouverts[0][0] == "BUY"
    sens, taille, dist = api.ouverts[0]
    assert abs(dist - 1.0) < 1e-6
    assert taille * dist / (1.08 * 151.55) <= 98 * 0.05 + 0.01  # risque <= 5 %
    lo.tour_londres(api, d, "USDJPY", [], 98, 98, 1.08, lambda *a: None, Garde(), f"{J}T09:05:00Z")
    assert len(api.ouverts) == 1  # un seul trade par jour
    pos = [{"position": {"dealId": "L1", "direction": "BUY", "createdDateUTC": f"{J}T08:05:00", "upl": 2, "size": 400, "level": 151.5},
            "market": {"epic": "USDJPY"}}]
    lo.tour_londres(api, d, "USDJPY", pos, 98, 98, 1.08, lambda *a: None, Garde(), f"{J}T15:00:00Z")
    assert not api.fermes
    lo.tour_londres(api, d, "USDJPY", pos, 98, 98, 1.08, lambda *a: None, Garde(), f"{J}T20:05:00Z")
    assert api.fermes == ["L1"]


def test_rien_si_le_prix_reste_dans_la_zone_ou_hors_fenetre():
    api = Faux(NUIT + [b(J, 7, 150.9, 150.2, 150.6), b(J, 8, 150.7, 150.5, 150.6)])
    lo.tour_londres(api, {}, "USDJPY", [], 98, 98, 1.08, lambda *a: None, Garde(), f"{J}T08:05:00Z")
    api2 = Faux(NUIT + [b(J, h, 152, 151, 151.8) for h in range(7, 13)])
    lo.tour_londres(api2, {}, "USDJPY", [], 98, 98, 1.08, lambda *a: None, Garde(), f"{J}T13:05:00Z")
    assert not api.ouverts and not api2.ouverts

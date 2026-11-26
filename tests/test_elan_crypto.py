"""Bot à part Élan crypto : règles et un tour complet avec un faux compte (aucun vrai ordre)."""
from datetime import datetime, timedelta, timezone

import numpy as np

from elan_crypto import bot as E


def _bougies(closes, fin):
    out = []
    for k, c in enumerate(closes):
        t = fin - timedelta(hours=4) * (len(closes) - k)
        p = lambda x: {"bid": x, "ask": x + 0.5}
        out.append({"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"), "openPrice": p(c), "highPrice": p(c * 1.002),
                    "lowPrice": p(c * 0.998), "closePrice": p(c)})
    return out


class FauxCompte:
    def __init__(self, series, fin):
        self.series, self.fin, self.ordres, self.ouvertes, self.fermees = series, fin, [], [], []

    def connexion(self): pass
    def deconnexion(self): pass
    def positions(self): return self.ouvertes
    def comptes(self): return [{"preferred": True, "balance": {"balance": 100.0, "available": 100.0}}]
    def taux_eurusd(self): return 1.1
    def bougies(self, epic, unite, n): return _bougies(self.series[epic], self.fin)
    def marche(self, epic):
        c = self.series[epic][-1]
        return {"snapshot": {"bid": c, "offer": c + 0.5, "marketStatus": "TRADEABLE"},
                "dealingRules": {"minDealSize": {"value": 0.0001}, "minSizeIncrement": {"value": 0.0001},
                                 "minGuaranteedStopDistance": {"unit": "PERCENTAGE", "value": 0.1}},
                "instrument": {"marginFactor": 50, "currency": "USD", "name": epic}}
    def ouvrir(self, epic, direction, taille, **k):
        self.ordres.append((epic, direction, taille, k))
        self.ouvertes.append({"market": {"epic": epic}, "position": {"dealId": f"D{len(self.ordres)}", "upl": 0.0,
                                                                     "direction": direction}})
        return {"dealStatus": "ACCEPTED", "affectedDeals": [{"dealId": f"D{len(self.ordres)}"}], "level": 1000.0}
    def fermer(self, deal):
        self.fermees.append(deal)
        self.ouvertes = [p for p in self.ouvertes if p["position"]["dealId"] != deal]
        return {"dealStatus": "ACCEPTED"}


def test_signal_nouveau_dans_la_tendance():
    fin = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
    c = list(np.linspace(1000, 2000, 300)) + [1950] * 1  # longue hausse : sens +1 depuis longtemps -> pas nouveau
    s = E.signaux(E.bougies_vers_df(_bougies(c, fin)), 50)
    assert s["sens"] == 1 and not s["entree"]


def test_bougie_en_cours_retiree():
    fin = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
    b = _bougies([1.0] * 3, fin + timedelta(hours=4))  # la dernière commence à 12 h : pas terminée à 12 h
    assert len(E.bougies_terminees(b, fin)) == 2


def test_un_tour_achete_puis_ferme_sur_inversion(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "FICHIER_PRINCIPAL", tmp_path / "rien.json")
    fin = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
    # baisse puis forte reprise : l'élan 50 repasse à la hausse sur la dernière bougie, au-dessus de la moyenne 200
    base = list(np.linspace(1000, 3000, 250)) + list(np.linspace(3000, 2900, 49))
    hausse = base + [3001]
    series = {e: hausse for e in E.MARCHES}
    series["XRPUSD"] = [1.0] * 300
    api = FauxCompte(series, fin)
    d = E.un_tour({}, api, fin)
    achats = [o for o in api.ordres if o[1] == "BUY"]
    assert {o[0] for o in achats} == {"ETHUSD", "LTCUSD", "SOLUSD"}
    assert all(o[3]["garanti"] for o in achats) and len(d["deals"]) == 3
    # même bougie au tour suivant : pas de 2e achat
    E.un_tour(d, api, fin + timedelta(minutes=30))
    assert len(api.ordres) == 3
    # l'élan s'inverse -> fermeture
    api.series = {e: hausse + [2000] for e in E.MARCHES}
    api.series["XRPUSD"] = [1.0] * 301
    E.un_tour(d, api, fin + timedelta(hours=4))
    assert len(api.fermees) == 3 and not d["deals"] and len(d["ordres"]) == 3


def test_pas_d_entree_si_principal_en_pause(tmp_path, monkeypatch):
    f = tmp_path / "data.json"
    f.write_text('{"pause": true}')
    monkeypatch.setattr(E, "FICHIER_PRINCIPAL", f)
    fin = datetime(2026, 11, 26, 12, tzinfo=timezone.utc)
    c = list(np.linspace(1000, 3000, 250)) + list(np.linspace(3000, 2900, 49)) + [3001]
    api = FauxCompte({e: c for e in E.MARCHES}, fin)
    d = E.un_tour({}, api, fin)
    assert not api.ordres and "pause" in d["bilan"]["blocage"]

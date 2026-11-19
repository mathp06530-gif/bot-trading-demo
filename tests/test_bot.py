"""Tests sans connexion : on remplace Capital.com par un faux serveur."""
import json
import math
import os

import bot.main as main
from bot.strategie import decider, ema


def test_ema_comme_tradingview():
    v = ema([1, 2, 3, 4, 5], 3)
    assert v[:2] == [None, None]
    assert v[2] == 2  # moyenne simple des 3 premières
    assert math.isclose(v[3], 0.5 * 4 + 0.5 * 2)


def test_decider_tendance():
    hausse = [100 + i for i in range(60)]
    assert decider(hausse)["direction"] == "BUY"
    baisse = [200 - i for i in range(60)]
    assert decider(baisse)["direction"] == "SELL"
    assert decider([1, 2, 3])["direction"] is None


class FauxCapital:
    def __init__(self, prix):
        self.prix = prix
        self.ouvertes = []
        self.fermees = []

    def connexion(self): pass
    def deconnexion(self): pass
    def marche(self, epic): return {"dealingRules": {"minDealSize": {"value": 0.01}}}

    def bougies(self, epic, unite, n):
        return [{"snapshotTimeUTC": f"2026-11-19T{i // 4:02d}:{(i % 4) * 15:02d}:00",
                 "closePrice": {"bid": p - 1, "ask": p + 1}} for i, p in enumerate(self.prix)]

    def positions(self):
        return [{"position": {"dealId": d, "direction": s, "size": t, "level": 100, "upl": 1.5},
                 "market": {"epic": "BTCUSD", "instrumentName": "Bitcoin"}} for d, s, t in self.ouvertes]

    def ouvrir(self, epic, direction, taille, stop, prix):
        self.ouvertes.append((f"d{len(self.ouvertes) + len(self.fermees)}", direction, taille))
        return {"dealStatus": "ACCEPTED", "level": prix}

    def fermer(self, deal_id):
        self.fermees.append(deal_id)
        self.ouvertes = [o for o in self.ouvertes if o[0] != deal_id]
        return {"dealStatus": "ACCEPTED"}

    def comptes(self):
        return [{"preferred": True, "accountName": "Démo", "currency": "EUR",
                 "balance": {"balance": 10000, "deposit": 10000, "profitLoss": 1.5, "available": 9900}}]


def test_un_tour_ouvre_puis_retourne(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    faux = FauxCapital([100 + i for i in range(80)])
    d = {}
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["BUY"]

    main.un_tour(d, faux)  # même tendance : on ne fait rien
    assert len(faux.ouvertes) == 1 and not faux.fermees

    faux.prix = faux.prix + [180 - 3 * i for i in range(40)]  # le marché se retourne
    main.un_tour(d, faux)
    assert faux.fermees == ["d0"]
    assert [o[1] for o in faux.ouvertes] == ["SELL"]
    assert d["compte"]["solde"] == 10000
    assert len(d["historique"]) == 3
    assert any(l["type"] == "fermeture" for l in d["journal"])


def test_sans_secrets_ecrit_une_erreur(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"):
        monkeypatch.delenv(n, raising=False)
    assert main.principal() == 1
    d = json.loads((tmp_path / "data.json").read_text())
    assert d["journal"][-1]["type"] == "erreur"


def test_stop_garanti_si_exige(monkeypatch):
    from bot.capital import CapitalDemo, ErreurCapital
    api = CapitalDemo("k", "i", "p")
    envoyes = []

    def faux(methode, chemin, **kw):
        if chemin == "/positions":
            envoyes.append(dict(kw["json"]))
            if not kw["json"].get("guaranteedStop"):
                raise ErreurCapital('POST /positions -> 400 : {"errorCode":"error.vallidation.guaranteed-stop-loss.required"}')
            return {"dealReference": "o_1"}
        if chemin.startswith("/markets/"):
            return {"dealingRules": {"minGuaranteedStopDistance": {"unit": "PERCENTAGE", "value": 5}}}
        return {"dealStatus": "ACCEPTED"}

    monkeypatch.setattr(api, "_requete", faux)
    assert api.ouvrir("BTCUSD", "BUY", 0.01, 3, 1000)["dealStatus"] == "ACCEPTED"
    assert envoyes[-1]["guaranteedStop"] is True and envoyes[-1]["stopDistance"] == 55.0

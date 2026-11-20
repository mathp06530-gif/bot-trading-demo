"""Tests sans connexion : on remplace Capital.com par un faux serveur."""
import json
import math
import os

from datetime import datetime, timedelta, timezone

import bot.main as main
import bot.rapide as rapide
from bot.strategie import bougies_vers_df, decider, ema


def test_ema_comme_tradingview():
    v = ema([1, 2, 3, 4, 5], 3)
    assert v[:2] == [None, None]
    assert v[2] == 2  # moyenne simple des 3 premières
    assert math.isclose(v[3], 0.5 * 4 + 0.5 * 2)


def bougie(i, p, unite="HOUR_4"):
    pas = 4 * 3600 if unite == "HOUR_4" else 300
    t = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=pas * i)
    prix = lambda x: {"bid": x - 1, "ask": x + 1}
    return {"snapshotTimeUTC": t.strftime("%Y-%m-%dT%H:%M:%S"), "openPrice": prix(p), "highPrice": prix(p + 30),
            "lowPrice": prix(p - 30), "closePrice": prix(p)}


def serie_achat():
    """Baisse puis forte hausse ; renvoie les prix jusqu'à la bougie où le signal d'ACHAT apparaît."""
    prix = [20000 - 20 * i for i in range(250)] + [15000 + 120 * i for i in range(150)]
    for n in range(260, len(prix)):
        s = decider(bougies_vers_df([bougie(i, p) for i, p in enumerate(prix[:n])]))
        if s["direction"] == "BUY":
            assert s["nouveau"]
            return prix[:n], prix[n:]
    raise AssertionError("pas de signal d'achat")


def test_decider_tendance():
    debut, suite = serie_achat()
    s = decider(bougies_vers_df([bougie(i, p) for i, p in enumerate(debut)]))
    assert s["direction"] == "BUY" and "ACHETEUR" in s["explication"]
    tard = decider(bougies_vers_df([bougie(i, p) for i, p in enumerate(debut + suite[:20])]))
    assert tard["direction"] == "BUY" and not tard["nouveau"]  # signal trop vieux : pas d'entrée en retard
    assert decider(bougies_vers_df([bougie(i, 100) for i in range(50)]))["direction"] is None


class FauxCapital:
    def __init__(self, prix, prix_rapide=None):
        self.prix = prix
        self.prix_rapide = prix_rapide or [100 + i for i in range(80)]
        self.ouvertes = []  # (dealId, sens, taille, stop)
        self.fermees = []
        self.stops = []
        self.objectifs = []
        self.niveaux = {}
        self.epics = {}
        self.n = 0

    def connexion(self): pass
    def deconnexion(self): pass
    def taux_eurusd(self): return 1.0
    def sans_couverture(self): return True
    def marche(self, epic): return {"dealingRules": {"minDealSize": {"value": 0.0001}}}

    def bougies(self, epic, unite, n):
        serie = self.prix if unite == "HOUR_4" else self.prix_rapide
        return [bougie(i, p, unite) for i, p in enumerate(serie)] + [bougie(len(serie), serie[-1], unite)]

    def positions(self):
        return [{"position": {"dealId": d, "direction": s, "size": t, "level": self.niveaux.get(d, 100), "upl": 1.5, "stopLevel": st,
                              "guaranteedStop": True},
                 "market": {"epic": self.epics.get(d, "BTCUSD"), "instrumentName": "Bitcoin"}} for d, s, t, st in self.ouvertes]

    def ouvrir(self, epic, direction, taille, stop_pct=None, prix=None, stop_distance=None, garanti=False,
               objectif_distance=None):
        self.objectifs.append(objectif_distance)
        d = f"d{self.n}"
        self.n += 1
        self.niveaux[d] = prix
        self.epics[d] = epic
        self.ouvertes.append((d, direction, taille, prix - stop_distance if direction == "BUY" else prix + stop_distance))
        return {"dealStatus": "ACCEPTED", "level": prix, "affectedDeals": [{"dealId": d}]}

    def modifier_stop(self, deal_id, niveau, garanti=True):
        self.stops.append((deal_id, niveau))
        self.ouvertes = [(d, s, t, niveau if d == deal_id else st) for d, s, t, st in self.ouvertes]
        return {"dealStatus": "ACCEPTED"}

    def fermer(self, deal_id):
        self.fermees.append(deal_id)
        self.ouvertes = [o for o in self.ouvertes if o[0] != deal_id]
        return {"dealStatus": "ACCEPTED"}

    def comptes(self):
        return [{"preferred": True, "accountName": "Démo", "currency": "EUR",
                 "balance": {"balance": 10000, "deposit": 10000, "profitLoss": 1.5, "available": 9900}}]


def test_un_tour_entre_suit_et_sort(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", False)
    debut, suite = serie_achat()
    faux = FauxCapital(debut)
    d = {}
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["BUY", "BUY"]  # 2 moitiés : une avec TP, une sans
    assert faux.objectifs[0] > 0 and faux.objectifs[1] is None
    deal, _, _, stop = faux.ouvertes[0]
    distance = debut[-1] + 1 - stop
    taille = sum(o[2] for o in faux.ouvertes)
    assert math.isclose(taille * distance, 100, rel_tol=0.02)  # 1 % de 10 000 € risqué au total

    main.un_tour(d, faux)  # même signal : pas de nouvel achat
    assert len(faux.ouvertes) == 2 and not faux.fermees

    faux.prix = debut + suite[:30]  # le prix monte : le stop suiveur remonte
    main.un_tour(d, faux)
    assert faux.stops and faux.stops[-1][1] > stop and not faux.fermees

    faux.prix = faux.prix + [faux.prix[-1] - 150 * i for i in range(1, 120)]  # retournement
    main.un_tour(d, faux)
    assert faux.fermees == ["d0", "d1"] and not faux.ouvertes
    assert d["compte"]["solde"] == 10000
    assert any(l["type"] == "fermeture" for l in d["journal"])
    assert d["ordres"][0]["statut"] == "ferme" and d["ordres"][0]["strategie"] == "tendance_4h"


def test_apres_un_stop_pas_de_reentree_sur_le_meme_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", False)
    debut, _ = serie_achat()
    faux = FauxCapital(debut)
    d = {}
    main.un_tour(d, faux)
    faux.ouvertes = []  # stop touché chez Capital.com
    main.un_tour(d, faux)
    assert not faux.ouvertes


def test_strategie_rapide_separee(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    tendances = {"t": ("BUY", "BUY")}
    monkeypatch.setattr(rapide, "tendances_superieures", lambda api, epic: tendances["t"])
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", True)
    faux = FauxCapital([20000] * 300, [100 + i for i in range(80)])
    d = {}
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["BUY"]  # seule la rapide trade (pas de tendance 4 h)
    assert d["rapide"]["deals"] == ["d0"]
    faux.prix_rapide = faux.prix_rapide + [180 - 3 * i for i in range(60)]
    main.un_tour(d, faux)  # signal 5 min en baisse mais tendance de fond en hausse : on sort et on reste à l'écart
    assert faux.fermees == ["d0"] and not faux.ouvertes
    assert d["strategies"]["rapide"]["action"].startswith("À l'écart")
    tendances["t"] = ("SELL", "SELL")
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["SELL"]
    assert {o["strategie"] for o in d["ordres"]} == {"rapide"}


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


def test_commandes_pause_fermer_reprendre(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", False)
    faux = FauxCapital(serie_achat()[0])
    d = {}
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 2
    main.un_tour(d, faux, "fermer")
    assert not faux.ouvertes and d["pause"] is True
    main.un_tour(d, faux)  # en pause : aucun nouvel ordre
    assert not faux.ouvertes and d["analyses"]["BTCUSD"]["action"].startswith("En pause")
    main.un_tour(d, faux, "reprendre")  # relancé, mais ce signal a déjà servi : on attend le suivant
    assert not faux.ouvertes and d["pause"] is False
    assert d["ordres"][0]["motif_sortie"] == "Fermée depuis l'application"


def test_commandes_par_strategie(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(rapide, "tendances_superieures", lambda api, epic: ("BUY", "BUY"))
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", True)
    debut, suite = serie_achat()
    faux = FauxCapital(debut, [100 + i for i in range(80)])
    d = {}
    main.un_tour(d, faux, "desactiver", "rapide")  # la rapide ne trade plus, la 4 h oui
    assert d["strategies"]["rapide"]["active"] is False and d["strategies"]["tendance_4h"]["active"] is True
    assert len(faux.ouvertes) == 2 and not d["rapide"].get("deals")
    assert d["strategies"]["rapide"]["action"] == "Désactivée"
    assert {"nom", "description", "unite", "risque_pct", "action", "tendance"} <= set(d["strategies"]["tendance_4h"])

    main.un_tour(d, faux, "lancer", "rapide")  # tour immédiat de la rapide même désactivée
    assert len(faux.ouvertes) == 3 and d["rapide"]["deals"] == ["d2"]
    assert any(l.get("strategie") == "rapide" for l in d["journal"])
    assert any(l.get("strategie") == "tendance_4h" for l in d["journal"])

    main.un_tour(d, faux, "fermer", "tendance_4h")  # ferme seulement la 4 h et la désactive
    assert faux.fermees == ["d0", "d1"] and [o[0] for o in faux.ouvertes] == ["d2"]
    assert d["strategies"]["tendance_4h"]["active"] is False and not d.get("pause")

    faux.prix = debut + suite[:30]
    main.un_tour(d, faux, "activer", "toutes")
    assert d["strategies"]["tendance_4h"]["active"] and d["strategies"]["rapide"]["active"]


def test_rapide_attend_si_la_4h_est_en_sens_inverse(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(rapide, "tendances_superieures", lambda api, epic: ("SELL", "SELL"))
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", True)
    debut, _ = serie_achat()
    faux = FauxCapital(debut, [200 - i for i in range(80)])  # 4 h : achat ; rapide : vente
    d = {}
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["BUY", "BUY"]
    assert d["strategies"]["rapide"]["action"].startswith("En attente")


def test_fermeture_manuelle_estimee_au_dernier_prix():
    from bot.registre import synchroniser
    o = {"id": "x", "sens": "SELL", "taille": 0.01, "prix_entree": 62832, "stop": 64718,
         "dernier_prix": 63000, "statut": "ouvert"}
    d = {"ordres": [dict(o)]}
    synchroniser(d, [], "2026-11-19T18:30:00Z")
    assert d["ordres"][0]["prix_sortie"] == 63000 and d["ordres"][0]["resultat"] == -1.68
    d = {"ordres": [dict(o, dernier_prix=65000)]}  # le prix avait dépassé le stop
    synchroniser(d, [], "2026-11-19T18:30:00Z")
    assert d["ordres"][0]["prix_sortie"] == 64718


# --- Garde-fous ---------------------------------------------------------------
def _pos(level, stop, size, sens="BUY"):
    return {"position": {"level": level, "stopLevel": stop, "size": size, "direction": sens}}


def test_garde_fous_regles():
    from bot.garde_fous import GardeFous
    d = {}
    g = GardeFous(d, 10000, [], 1.0)
    assert g.autoriser(100, 50) == (True, "")
    assert not g.autoriser(100, 0)[0]  # jamais sans stop
    assert not g.autoriser(700, 50)[0]  # risque total > 6 %
    g = GardeFous(d, 10000, [_pos(100, 90, 50)], 1.0)  # 500 € déjà en jeu
    assert not g.autoriser(150, 5)[0] and g.autoriser(90, 5)[0]
    g = GardeFous(d, 10000, [_pos(100, 110, 50)], 1.0)  # stop au-dessus de l'entrée : gain verrouillé, 0 risque
    assert g.risque_ouvert_eur() == 0
    g = GardeFous(d, 10000, [_pos(100, 99, 1)] * 12, 1.0)
    assert "positions" in g.autoriser(10, 5)[1]
    g = GardeFous(d, 9650, [], 1.0)  # -3,5 % dans la journée
    assert "perte du jour" in g.autoriser(10, 5)[1]
    d2 = {"garde_fous": {"plus_haut": 12000}}
    g = GardeFous(d2, 10000, [], 1.0)  # -16 % depuis le plus haut
    assert "COUPE-CIRCUIT" in g.autoriser(10, 5)[1]
    g.rearmer()
    assert g.autoriser(10, 5)[0]


# --- Sous-bots actions et ETF ----------------------------------------------------
class FauxCapitalActions(FauxCapital):
    def __init__(self, prix_action, statut="TRADEABLE"):
        super().__init__([20000] * 300)
        self.prix_action, self.statut = prix_action, statut

    def marche(self, epic):
        if epic == "BTCUSD":
            return super().marche(epic)
        return {"snapshot": {"marketStatus": self.statut}, "instrument": {"name": epic, "marginFactor": 20},
                "dealingRules": {"minDealSize": {"value": 0.1}, "minSizeIncrement": {"value": 0.1},
                                 "minGuaranteedStopDistance": {"unit": "PERCENTAGE", "value": 5}}}

    def bougies(self, epic, unite, n):
        if epic == "BTCUSD":
            return super().bougies(epic, unite, n)
        return [bougie(i, p) for i, p in enumerate(self.prix_action)] + [bougie(len(self.prix_action), self.prix_action[-1])]


def serie_note_achat():
    from bot.strategie import signaux_note
    prix = [300 + 3 * i + 8 * ((i % 7) - 3) for i in range(260)] + [1100 - 10 * i for i in range(20)] + \
           [900 + 15 * i for i in range(60)]
    for n in range(262, len(prix)):
        c = signaux_note(bougies_vers_df([bougie(i, p) for i, p in enumerate(prix[:n])]), ventes=False).cible.values
        if c[-1] == 1 and c[-2] == 0:
            return prix[:n]
    raise AssertionError("pas de signal")


def test_sous_bot_achete_avec_stop_et_tp(tmp_path, monkeypatch):
    import bot.sous_bots as sb
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", False)
    monkeypatch.setattr(main, "SOUS_BOTS", ["NVDA"])
    faux = FauxCapitalActions(serie_note_achat())
    d = {"strategies": {"rapide": {"active": False}}}
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["BUY", "BUY"]
    assert faux.objectifs[0] > 0 and faux.objectifs[1] is None  # TP sur la moitié
    prix = faux.prix_action[-1] + 1
    assert all(prix - st >= prix * 0.05 for _, _, _, st in faux.ouvertes)  # stop >= minimum imposé (5 %)
    risque = sum(t * (prix - st) for _, _, t, st in faux.ouvertes)
    assert risque <= 10000 * sb.RISQUE_SOUS_BOT_PCT / 100 * 1.02
    assert d["sous_bots"]["NVDA"]["note"] >= 0.5 and d["ordres"][0]["strategie"] == "actions_etf"


def test_sous_bot_refuse_si_marche_ferme(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "RAPIDE_ACTIVE", False)
    monkeypatch.setattr(main, "SOUS_BOTS", ["NVDA"])
    faux = FauxCapitalActions(serie_note_achat(), statut="CLOSED")
    d = {"strategies": {"rapide": {"active": False}}}
    main.un_tour(d, faux)
    assert not faux.ouvertes and "marché fermé" in d["sous_bots"]["NVDA"]["action"]


def test_rapide_stop_suiveur_garde_le_gain():
    """Une vente rapide qui gagne beaucoup : le stop suit le prix à 2 % et ne recule jamais."""
    from bot import rapide
    api = FauxCapital([20000] * 10)
    api.ouvertes = [("r1", "SELL", 0.01, 101000.0)]  # vente à 100 000, stop à +1 %
    pos = api.positions()
    notes = []
    noter = lambda *a: notes.append(a)
    r = rapide.suivre_stop(api, pos, {"bid": 94990.0, "ask": 95010.0}, "BTCUSD", noter)
    assert r == "Stop suiveur déplacé"
    assert api.stops == [("r1", 95000.0 * 1.02)]  # 96 900 : le gain est en partie verrouillé
    # le prix remonte : le stop ne recule pas
    r = rapide.suivre_stop(api, api.positions(), {"bid": 97990.0, "ask": 98010.0}, "BTCUSD", noter)
    assert r == "Position conservée" and len(api.stops) == 1

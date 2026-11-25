"""Tests sans connexion : on remplace Capital.com par un faux serveur."""
import json
import math
import os

import pytest

from datetime import datetime, timedelta, timezone

import bot.main as main
from bot.strategie import bougies_vers_df, decider, ema


def test_ema_comme_tradingview():
    v = ema([1, 2, 3, 4, 5], 3)
    assert v[:2] == [None, None]
    assert v[2] == 2  # moyenne simple des 3 premières
    assert math.isclose(v[3], 0.5 * 4 + 0.5 * 2)


def bougie(i, p, unite="HOUR_4"):
    pas = {"HOUR_4": 4 * 3600, "DAY": 86400}.get(unite, 300)
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
    debut, _ = serie_achat()
    faux = FauxCapital(debut)
    d = {}
    main.un_tour(d, faux)
    faux.ouvertes = []  # stop touché chez Capital.com
    main.un_tour(d, faux)
    assert not faux.ouvertes


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


def test_pause_autour_des_grandes_annonces():
    from datetime import datetime, timezone
    from bot import actualites
    from bot.garde_fous import GardeFous
    donnees = {}
    t = datetime(2026, 12, 9, 18, 45, tzinfo=timezone.utc)
    assert actualites.mettre_a_jour(donnees, t, lire=lambda: [{"date": "2026-12-09T19:00Z", "titre": "FOMC Statement"}]) is None
    raison = actualites.annonce_en_cours(donnees, t)
    assert raison and "FOMC Statement" in raison and "20 h 00" in raison
    assert actualites.annonce_en_cours(donnees, datetime(2026, 12, 9, 20, 30, tzinfo=timezone.utc)) is None
    garde = GardeFous({}, 21000, [], 1.0)
    garde.pause_actualite = raison
    ok, pourquoi = garde.autoriser(10, 600)
    assert not ok and "pause actualité" in pourquoi


def test_calendrier_en_panne_le_bot_continue():
    from datetime import datetime, timezone
    from bot import actualites
    def panne():
        raise OSError("hors ligne")
    donnees = {}
    msg = actualites.mettre_a_jour(donnees, datetime(2026, 12, 9, tzinfo=timezone.utc), lire=panne)
    assert "indisponible" in msg
    assert actualites.annonce_en_cours(donnees, datetime(2026, 12, 9, tzinfo=timezone.utc)) is None


def test_cassure_identique_au_backtest():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backtest"))
    from strategies import cassure_donchian
    from bot.cassure import signaux_cassure
    prix = [2000 + 25 * ((i % 8) - 4) for i in range(250)] + [2000 + 45 * i for i in range(40)] + [3800 - 45 * i for i in range(60)]
    df = bougies_vers_df([bougie(i, p) for i, p in enumerate(prix)])
    a = signaux_cassure(df)
    b = cassure_donchian(df, entree=20, sortie=20, stop_atr=2, filtre_ema=200)
    assert (a.cible.values == b.cible.values).all() and (a.cible != 0).any()


def test_cassure_achete_or_avec_stop_garanti(tmp_path, monkeypatch):
    from bot.cassure import signaux_cassure
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "MARCHES_CASSURE", ["GOLD"])
    prix = [2000 + 25 * ((i % 8) - 4) for i in range(250)] + [2000 + 45 * i for i in range(40)]
    for n in range(240, 290):
        c = signaux_cassure(bougies_vers_df([bougie(i, p) for i, p in enumerate(prix[:n])])).cible.values
        if c[-1] == 1 and c[-2] == 0:
            break
    faux = FauxCapitalActions(prix[:n])
    d = {}
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["BUY"]
    _, _, taille, stop = faux.ouvertes[0]
    assert stop < prix[n - 1] and taille * (prix[n - 1] + 1 - stop) <= 10000 * 0.5 / 100 * 1.02
    assert d["ordres"][0]["strategie"] == "cassure_4h" and d["strategies"]["cassure_4h"]["action"] == "Actif"
    # tour suivant, même signal : pas de deuxième ordre
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 1




def test_commandes_par_strategie(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    debut, _ = serie_achat()
    faux = FauxCapital(debut)
    d = {"strategies": {"rapide": {"active": False}, "londres": {"active": True}}, "londres": {}}
    main.un_tour(d, faux, "desactiver", "tendance_4h")
    assert set(d["strategies"]) == {"tendance_4h", "cassure_4h", "rapide"}  # anciennes stratégies supprimées
    assert "londres" not in d
    assert d["strategies"]["tendance_4h"]["active"] is False and not faux.ouvertes
    main.un_tour(d, faux, "activer", "tendance_4h")
    assert d["strategies"]["tendance_4h"]["active"] and len(faux.ouvertes) == 2


def test_rapide_or_achete_dans_le_sens_des_tendances(tmp_path, monkeypatch):
    from bot import rapide
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "MARCHES", [])
    monkeypatch.setattr(rapide, "LISTE", ["GOLD"])
    monkeypatch.setattr(rapide, "FILTRE_BOLLINGER", False)
    monkeypatch.setattr(rapide, "ADX_RAPIDE_MIN", 0)
    monkeypatch.setattr(rapide, "tendances_superieures", lambda api, epic: ("BUY", "BUY"))
    debut, _ = serie_achat()
    faux = FauxCapital(debut, [100 + i for i in range(80)])
    d = {"strategies": {"rapide": {"active": True}}, "rapide": {"deals": ["vieux_btc"]}}
    main.un_tour(d, faux)
    assert [(o[1], faux.epics[o[0]]) for o in faux.ouvertes] == [("BUY", "GOLD")]
    assert d["rapide"]["deals"] == ["d0"] and d["strategies"]["rapide"]["active"]
    assert d["ordres"][0]["strategie"] == "rapide"
    assert d["rapide"]["marches"]["GOLD"]["action"].startswith("ACHAT")
    # le prix se retourne : la rapide ferme sa position
    faux.prix_rapide = faux.prix_rapide + [180 - 3 * i for i in range(60)]
    main.un_tour(d, faux)
    assert "d0" in faux.fermees


def test_repartir_du_test_ne_compte_pas_le_retrait():
    d = {"historique": [{"date": "2026-11-19T17:48:29Z", "valeur": 21000.0}, {"date": "2026-11-20T16:20:30Z", "valeur": 98.21}],
         "historique_jour": {"2026-11-19": 21069.4}, "valeur_depart": 21000.0,
         "ordres": [{"id": "a", "statut": "ferme", "ouvert_le": "2026-11-19T18:00:00Z", "resultat": -5}],
         "garde_fous": {"jour": "2026-11-20", "debut_jour": 21069, "plus_haut": 21000, "coupe_circuit": True}}
    main.repartir_du_test(d)
    assert d["valeur_depart"] == 98.21 and d["historique_jour"] == {} and len(d["historique"]) == 1
    assert d["ordres"] == [] and d["ordres_avant_test"][0]["id"] == "a"
    assert d["garde_fous"]["plus_haut"] == 0 and not d["garde_fous"]["coupe_circuit"] and "jour" not in d["garde_fous"]
    main.repartir_du_test(d)  # une seule fois
    assert len(d["ordres_avant_test"]) == 1


def test_empilement_seulement_si_le_prix_a_avance_d_un_r():
    from bot.empilement import peut_empiler
    pos = lambda lvl: {"position": {"level": lvl}}
    assert peut_empiler([], "BUY", 100, 10, 3)[0]
    assert not peut_empiler([pos(100)], "BUY", 105, 10, 3)[0]          # pas encore +1 R
    assert peut_empiler([pos(100)], "BUY", 110, 10, 3)[0]              # +1 R : 2e position
    assert not peut_empiler([pos(100), pos(100.5)], "BUY", 108, 10, 3)[0]  # 2 moitiés = 1 entrée
    assert peut_empiler([pos(100), pos(100.5)], "BUY", 111, 10, 3)[0]
    assert not peut_empiler([pos(100), pos(110), pos(120)], "BUY", 140, 10, 3)[0]  # maximum atteint
    assert peut_empiler([pos(100)], "SELL", 90, 10, 3)[0]
    assert not peut_empiler([pos(100)], "BUY", 200, 10, 1)[0]          # 1 = pas d'empilement


def test_tendance_empile_une_position_quand_le_prix_avance(tmp_path, monkeypatch):
    import bot.empilement as emp
    monkeypatch.setattr(emp, "EMPILER_MAX", 3)
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    debut, suite = serie_achat()
    faux = FauxCapital(debut)
    d = {}
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 2
    main.un_tour(d, faux)  # le prix n'a pas bougé : rien de plus
    assert len(faux.ouvertes) == 2
    faux.prix = debut + suite[:30]  # le prix monte nettement : une 2e entrée (2 moitiés)
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 4 and all(o[1] == "BUY" for o in faux.ouvertes)
    assert any("Empilement" in l["texte"] for l in d["journal"] if l["type"] == "ordre")


def test_cassure_empile_quand_le_prix_avance(tmp_path, monkeypatch):
    import bot.empilement as emp
    from bot.cassure import signaux_cassure
    monkeypatch.setattr(emp, "EMPILER_MAX", 3)
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "MARCHES_CASSURE", ["GOLD"])
    prix = [2000 + 25 * ((i % 8) - 4) for i in range(250)] + [2000 + 45 * i for i in range(80)]
    for n in range(240, 290):
        c = signaux_cassure(bougies_vers_df([bougie(i, p) for i, p in enumerate(prix[:n])])).cible.values
        if c[-1] == 1 and c[-2] == 0:
            break
    faux = FauxCapitalActions(prix[:n])
    d = {}
    main.un_tour(d, faux)
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 1
    vus = []
    for k in range(1, 40):  # le prix monte bougie après bougie
        faux.prix_action = prix[:n + k]
        main.un_tour(d, faux)
        vus.append(len(faux.ouvertes))
    assert 2 in vus and all(o[1] == "BUY" for o in faux.ouvertes)
    assert len(faux.ouvertes) == 3  # jamais plus de 3


def test_rapide_empile_quand_le_prix_avance(tmp_path, monkeypatch):
    from bot import rapide
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "MARCHES", [])
    monkeypatch.setattr(rapide, "LISTE", ["GOLD"])
    monkeypatch.setattr(rapide, "FILTRE_BOLLINGER", False)
    monkeypatch.setattr(rapide, "ADX_RAPIDE_MIN", 0)
    monkeypatch.setattr(rapide, "EMPILER_RAPIDE", 3)
    monkeypatch.setattr(rapide, "tendances_superieures", lambda api, epic: ("BUY", "BUY"))
    debut, _ = serie_achat()
    faux = FauxCapital(debut, [100 + i for i in range(80)])
    d = {"strategies": {"rapide": {"active": True}}}
    main.un_tour(d, faux)
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 1  # prix inchangé : pas de 2e position
    faux.prix_rapide = faux.prix_rapide + [180, 181, 182]  # +2 R environ
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 2 and any("Empilement" in l["texte"] for l in d["journal"])
    for k in range(10):
        faux.prix_rapide = faux.prix_rapide + [faux.prix_rapide[-1] + 5]
        main.un_tour(d, faux)
    assert len(faux.ouvertes) == 3


def test_cassure_entre_sur_un_nouveau_plus_haut_pendant_une_tendance_en_cours(tmp_path, monkeypatch):
    from bot.cassure import signaux_cassure
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "MARCHES_CASSURE", ["GOLD"])
    prix = [2000 + 25 * ((i % 8) - 4) for i in range(250)] + [2000 + 45 * i for i in range(40)]
    for n in range(240, 290):
        c = signaux_cassure(bougies_vers_df([bougie(i, p) for i, p in enumerate(prix[:n])])).cible.values
        if c[-1] == 1 and c[-2] == 0:
            break
    faux = FauxCapitalActions(prix[:n + 10])  # la cassure date de 10 bougies, mais chaque bougie fait un nouveau plus haut
    d = {}
    main.un_tour(d, faux)
    assert [o[1] for o in faux.ouvertes] == ["BUY"]
    faux2 = FauxCapitalActions(prix[:n + 10] + [prix[n + 9] - 30])  # dernière bougie sans nouveau plus haut : rien
    d2 = {}
    main.un_tour(d2, faux2)
    assert not faux2.ouvertes


def test_rapide_sort_au_prix_d_entree_apres_un_gain(tmp_path, monkeypatch):
    """Le prix monte de plus de 0,5 R puis revient au prix d'entrée : la rapide ferme (le gain ne devient pas une perte)."""
    from bot import rapide
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "MARCHES", [])
    monkeypatch.setattr(rapide, "LISTE", ["GOLD"])
    monkeypatch.setattr(rapide, "FILTRE_BOLLINGER", False)
    monkeypatch.setattr(rapide, "ADX_RAPIDE_MIN", 0)
    monkeypatch.setattr(rapide, "SUIVI_RAPIDE_PCT", 0)
    monkeypatch.setattr(rapide, "SORTIE_ENTREE_R", 0.5)
    monkeypatch.setattr(rapide, "tendances_superieures", lambda api, epic: ("BUY", "BUY"))
    debut, _ = serie_achat()
    faux = FauxCapital(debut, [3000 + i for i in range(80)])
    d = {"strategies": {"rapide": {"active": True}}}
    main.un_tour(d, faux)
    assert len(faux.ouvertes) == 1
    entree = faux.niveaux["d0"]
    main.un_tour(d, faux)  # rien n'a bougé : on garde (les bougies d'avant l'entrée ne comptent pas)
    assert not faux.fermees
    # les mèches des fausses bougies montent de 30 (= 1 R sur ~3080) : gain max >= 0,5 R ; clôture encore au-dessus
    faux.prix_rapide = faux.prix_rapide + [3090, 3095]
    main.un_tour(d, faux)
    assert not faux.fermees
    # la bougie se termine au prix d'entrée (EMA 9 toujours au-dessus de l'EMA 50) : sortie
    faux.prix_rapide = faux.prix_rapide + [entree - 1]
    main.un_tour(d, faux)
    assert faux.fermees == ["d0"]
    assert d["ordres"][0]["motif_sortie"] == "[Rapide] Retour au prix d'entrée"
    assert "d0" not in d["rapide"]["meilleur"]


def test_rapide_sans_gain_suffisant_ne_sort_pas(tmp_path, monkeypatch):
    from bot import rapide
    from bot.rapide import _apres_entree
    assert _apres_entree("2026-11-24T13:50:00", "2026-11-24T13:52:24.123")
    assert not _apres_entree("2026-11-24T13:45:00", "2026-11-24T13:52:24.123")
    assert _apres_entree("2026-11-24T14:00:00", "2026-11-24T13:52:24")
    monkeypatch.setattr(rapide, "SORTIE_ENTREE_R", 0.5)
    etat = {"deals": ["x"], "meilleur": {"x": {"depuis": "2026-01-01T00:00", "prix": 3000}}}
    pos = {"position": {"dealId": "x", "direction": "SELL", "level": 3000, "size": 0.01, "upl": -0.1},
           "market": {"epic": "GOLD", "instrumentName": "Gold"}}
    px = lambda x: {"bid": x - 0.5, "ask": x + 0.5}
    b = lambda t, h, l, c: {"snapshotTimeUTC": f"2026-01-01T00:{t:02d}:00", "highPrice": px(h), "lowPrice": px(l), "closePrice": px(c)}
    class Api:
        fermees = []
        def fermer(self, d): self.fermees.append(d); return {"dealStatus": "ACCEPTED"}
    api = Api()
    # vente : plus bas à 2990 = 0,33 R seulement, puis retour à 3001 -> on garde (le stop garanti protège)
    garde = rapide.proteger_gain(api, {}, etat, [pos], [b(0, 3002, 2990, 2995), b(5, 3003, 2996, 3001), b(10, 3001, 3001, 3001)],
                                 "GOLD", lambda *a: None, "2026-01-01T00:10:00Z")
    assert garde == [pos] and not api.fermees
    # plus bas à 2980 (0,67 R) puis clôture à 3000 -> sortie
    garde = rapide.proteger_gain(api, {}, etat, [pos], [b(15, 3001, 2980, 2990), b(20, 3001, 2995, 3000), b(25, 3000, 3000, 3000)],
                                 "GOLD", lambda *a: None, "2026-01-01T00:25:00Z")
    assert garde == [] and api.fermees == ["x"] and etat["deals"] == []


def test_cassure_resserre_le_stop_apres_un_gain(tmp_path, monkeypatch):
    """Après +1,5 R de gain, le stop garanti de la cassure est remonté pour garder 50 % du meilleur gain."""
    from bot import cassure
    from bot.cassure import signaux_cassure
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    monkeypatch.setattr(main, "MARCHES_CASSURE", ["GOLD"])
    prix = [2000 + 25 * ((i % 8) - 4) for i in range(250)] + [2000 + 45 * i for i in range(80)]
    for n in range(240, 290):
        c = signaux_cassure(bougies_vers_df([bougie(i, p) for i, p in enumerate(prix[:n])])).cible.values
        if c[-1] == 1 and c[-2] == 0:
            break
    faux = FauxCapitalActions(prix[:n])
    d = {}
    main.un_tour(d, faux)
    deal, _, _, stop0 = faux.ouvertes[0]
    entree = faux.niveaux[deal]
    dist = d["cassure_garde"][deal]["dist"]
    assert math.isclose(entree - stop0, dist)
    faux.prix_action = prix[:n] + [entree + 0.5 * dist]  # +0,5 R : rien ne bouge
    main.un_tour(d, faux)
    assert not faux.stops
    faux.prix_action = prix[:n] + [entree + 0.5 * dist, entree + 3 * dist, entree + 3 * dist]
    main.un_tour(d, faux)
    deals = [s for s in faux.stops if s[0] == deal]
    assert deals, "le stop aurait dû être remonté"
    meilleur = d["cassure_garde"][deal]["meilleur"]
    assert meilleur > entree + 3 * dist - 1
    assert deals[-1][1] > entree  # le trade ne peut plus finir en perte
    assert deals[-1][1] <= entree + cassure.GARDE_CASSURE_PCT / 100 * (meilleur - entree) + 1e-6
    assert any("50 % du meilleur gain" in l["texte"] for l in d["journal"])
    main.un_tour(d, faux)  # même prix : le stop ne bouge plus (et ne recule jamais)
    assert len([s for s in faux.stops if s[0] == deal]) == len(deals)

from bot import challenge as ch


def pos(deal, upl):
    return {"position": {"dealId": deal, "upl": upl}, "market": {"epic": "GOLD"}}


def donnees(ordres=()):
    return {"deals_par_strategie": {"challenge": ["a", "b"], "challenge_tm": ["c"]}, "ordres": list(ordres)}


def test_demarre_et_suit_la_valeur():
    d = donnees([{"id": "z", "statut": "ferme", "resultat": 999}])
    e = ch.suivre(d, [pos("a", 120), pos("x", -5000)], "2026-11-20T13:00:00Z", True)
    assert e["statut"] == "en cours" and e["tentative"] == 1
    assert e["valeur"] == ch.CAPITAL + 120  # les positions des autres stratégies ne comptent pas


def test_reussi_a_plus_10_pourcent_puis_nouvelle_tentative_le_lendemain():
    d = donnees()
    ch.suivre(d, [], "2026-11-20T10:00:00Z", True)
    e = ch.suivre(d, [pos("c", ch.CAPITAL * 0.10)], "2026-11-20T11:00:00Z", True)
    assert e["statut"] == "réussi" and e["a_fermer"]
    e["a_fermer"] = False
    d["ordres"].append({"id": "c", "statut": "ferme", "resultat": ch.CAPITAL * 0.10})
    e = ch.suivre(d, [], "2026-11-20T15:00:00Z", True)
    assert e["statut"] == "réussi"  # pas de nouvelle tentative le même jour
    e = ch.suivre(d, [], "2026-11-21T08:00:00Z", True)
    assert e["statut"] == "en cours" and e["tentative"] == 2 and e["valeur"] == ch.CAPITAL
    assert ch.bilan(e) == {"tentatives_finies": 1, "reussies": 1, "ratees": 0}


def test_rate_si_perte_de_5_pourcent_dans_la_journee():
    d = donnees()
    ch.suivre(d, [pos("a", 300)], "2026-11-20T10:00:00Z", True)
    ch.suivre(d, [pos("a", 300)], "2026-11-21T00:30:00Z", True)  # minuit Paris : la journée repart de 10 300
    e = ch.suivre(d, [pos("a", 300 - 450)], "2026-11-21T09:00:00Z", True)
    assert e["statut"] == "en cours"  # -150 au total, -450 dans la journée : encore OK
    e = ch.suivre(d, [pos("a", 300 - ch.CAPITAL * 0.05)], "2026-11-21T10:00:00Z", True)
    assert e["statut"] == "raté" and "journée" in e["raison"]


def test_rate_si_perte_totale_de_10_pourcent():
    d = donnees()
    ch.suivre(d, [], "2026-11-20T10:00:00Z", True)
    d["ordres"].append({"id": "b", "statut": "ferme", "resultat": -ch.CAPITAL * 0.04})
    ch.suivre(d, [], "2026-11-21T10:00:00Z", True)
    d["ordres"].append({"id": "c", "statut": "ferme", "resultat": -ch.CAPITAL * 0.04})
    assert ch.suivre(d, [], "2026-11-22T10:00:00Z", True)["statut"] == "en cours"
    d["ordres"].append({"id": "a", "statut": "ferme", "resultat": -ch.CAPITAL * 0.02})
    e = ch.suivre(d, [], "2026-11-24T10:00:00Z", True)
    assert e["statut"] == "raté" and "maximale" in e["raison"]


def test_inactif_ne_demarre_rien():
    d = donnees()
    assert "statut" not in ch.suivre(d, [], "2026-11-20T10:00:00Z", False)


def test_un_tour_avec_le_challenge_seul(tmp_path, monkeypatch):
    from bot import main
    from tests.test_bot import FauxCapital, serie_achat
    monkeypatch.setattr(main, "FICHIER_DONNEES", tmp_path / "data.json")
    debut, _ = serie_achat()
    faux = FauxCapital(debut)
    d = {"pause": False, "strategies": {s: {"active": s == "challenge"} for s in
         ["tendance_4h", "rapide", "actions_etf", "cassure_4h", "petit_compte", "tendance_mois", "x5_or",
          "x5_argent", "cassure_tous", "challenge"]}}
    main.un_tour(d, faux)
    s = d["strategies"]["challenge"]
    assert d["challenge_suivi"]["statut"] == "en cours"
    assert s["action"] == "Actif" and s["capital_depart"] == ch.CAPITAL
    assert not [l for l in d["journal"] if l["type"] == "erreur" and l.get("strategie") == "challenge"]
    # toutes les positions ouvertes appartiennent au challenge
    assert {o[0] for o in faux.ouvertes} <= ch.ids_challenge(d)

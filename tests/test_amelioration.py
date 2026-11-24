"""Tests de l'auto-amélioration hebdomadaire (sans connexion : prix synthétiques)."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from bot import amelioration as am

MAINTENANT = datetime(2026, 12, 13, 18, 0, tzinfo=timezone.utc)

REGLAGES = '''# commentaire
MARCHES="BTCUSD"
TP_PARTIEL_ATR="1"        # moitié avec TP
CASSURE_MARCHES="GOLD"
RAPIDE="oui"
RAPIDE_MARCHES="GOLD"
ADX_RAPIDE_MIN="20"             # filtre ADX
PERTE_MAX_PCT="50"
AUTO_AMELIORATION="auto"
AUTO_AMELIORATION_DEBUT="2026-12-05"
'''


def bougies(minutes: int, jours: int, graine: int, fin=MAINTENANT) -> pd.DataFrame:
    n = int(jours * 1440 / minutes)
    idx = pd.date_range(end=pd.Timestamp(fin) - pd.Timedelta(minutes=minutes), periods=n, freq=f"{minutes}min")
    rng = np.random.default_rng(graine)
    # marche au hasard avec des tendances (pour avoir des trades)
    pente = np.repeat(rng.normal(0, 0.002, n // 50 + 1), 50)[:n]
    close = 3000 * np.exp(np.cumsum(pente * (minutes / 240) ** 0.5 + rng.normal(0, 0.004 * (minutes / 240) ** 0.5, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    haut = np.maximum(open_, close) * (1 + abs(rng.normal(0, 0.001, n)))
    bas = np.minimum(open_, close) * (1 - abs(rng.normal(0, 0.001, n)))
    s = 0.3
    return pd.DataFrame({"open_bid": open_ - s, "open_ask": open_ + s, "high_bid": haut - s, "high_ask": haut + s,
                         "low_bid": bas - s, "low_ask": bas + s, "close_bid": close - s, "close_ask": close + s}, index=idx)


class FausseApi:
    def taux_eurusd(self):
        return 1.08

    def marche(self, epic):
        raise RuntimeError("hors ligne")


@pytest.fixture
def prix_synthetiques(monkeypatch):
    graines = {}

    def telecharger(api, epic, unite, jours):
        g = graines.setdefault((epic, unite), len(graines) + 1)
        return bougies(am.MINUTES[unite], jours, g)
    monkeypatch.setattr(am, "telecharger", telecharger)


def test_ecrire_reglage_garde_le_commentaire_et_refuse_les_garde_fous():
    t = am.ecrire_reglage(REGLAGES, "ADX_RAPIDE_MIN", 25)
    assert 'ADX_RAPIDE_MIN="25"             # filtre ADX' in t
    assert am.lire_reglages(t)["ADX_RAPIDE_MIN"] == "25"
    t = am.ecrire_reglage(t, "CASSURE_ENTREE", 30.0)  # absent : ajouté
    assert am.lire_reglages(t)["CASSURE_ENTREE"] == "30"
    for cle in ("PERTE_MAX_PCT", "PERTE_JOUR_PCT", "RISQUE_PCT", "RISQUE_RAPIDE_PCT"):
        with pytest.raises(ValueError):
            am.ecrire_reglage(t, cle, 99)


def test_bornes_respectent_les_tests_rejetes():
    assert min(am.REGLAGES["tendance_4h"]["SUIVI_TENDANCE_ATR"]) >= 4      # pas de suiveur serré
    assert min(v for v in am.REGLAGES["tendance_4h"]["TP_PARTIEL_ATR"] if v) >= 1  # pas de TP serré
    assert min(am.REGLAGES["rapide"]["SUIVI_RAPIDE_PCT"]) >= 2
    assert not any("RSI" in c or "ATR_MIN" in c for r in am.REGLAGES.values() for c in r)


def test_un_seul_cran_a_la_fois_et_valeurs_interdites():
    assert am.voisins("ADX_RAPIDE_MIN", 20.0) == [15, 25]
    assert am.voisins("ADX_RAPIDE_MIN", 15.0) == [20]
    assert am.voisins("FILTRE_BOLLINGER", "oui") == ["non"]
    v = am.variantes("rapide", {"ADX_RAPIDE_MIN": 20.0}, {"rapide.ADX_RAPIDE_MIN=25": "2026-12-31"}, "2026-12-13")
    assert v == [("ADX_RAPIDE_MIN", 15)]


def test_mode_suggestions_avant_la_date_de_debut():
    r = am.lire_reglages(REGLAGES)
    assert am.mode_effectif(r, datetime(2026, 11, 29, tzinfo=timezone.utc)) == "suggestions"
    assert am.mode_effectif(r, MAINTENANT) == "auto"
    assert am.mode_effectif({}, MAINTENANT) == "suggestions"


def score(R, R_1, R_2, trades=20, pire=-3.0):
    return {"R": R, "R_1": R_1, "R_2": R_2, "trades": trades, "pire_baisse_R": pire}


def test_ne_garde_une_variante_que_si_elle_gagne_sur_les_deux_moities():
    base = score(2, 1, 1)
    chance = {"reglage": "X", "score": score(6, 6, 0)}           # mieux au total, pire sur une moitié
    petite = {"reglage": "Y", "score": score(2.5, 1.2, 1.3)}       # trop peu d'amélioration
    risquee = {"reglage": "Z", "score": score(4, 2, 2, pire=-6)}   # pire baisse aggravée
    peu = {"reglage": "W", "score": score(5, 2.5, 2.5, trades=3)}  # pas assez de trades
    bonne = {"reglage": "B", "score": score(4, 2, 2)}
    assert am.meilleure_variante(base, [chance, petite, risquee, peu]) is None
    assert am.meilleure_variante(base, [chance, bonne, petite]) is bonne


def test_retour_en_arriere():
    assert am.faut_il_annuler({"R": -1.0}, {"R": 0.5})
    assert not am.faut_il_annuler({"R": 0.4}, {"R": 0.5})


def test_rapide_backtest_utilise_seulement_des_bougies_terminees():
    df5, df1, df4 = bougies(5, 20, 1), bougies(60, 30, 2), bougies(240, 60, 3)
    p = {"ADX_RAPIDE_MIN": 20.0, "FILTRE_BOLLINGER": "oui", "SUIVI_RAPIDE_PCT": 2.0}
    sig = am.signaux_rapide(df5, df1, df4, p)
    assert set(np.unique(sig.cible)) <= {-1, 0, 1}
    # couper l'avenir ne change pas les décisions passées
    coupe = am.signaux_rapide(df5.iloc[:3000], df1, df4, p)
    assert (coupe.cible.values == sig.cible.values[:3000]).all()


def test_semaine_complete_en_mode_auto(prix_synthetiques):
    etat = {}
    reglages = am.lire_reglages(REGLAGES)
    plan = am.calculer(FausseApi(), reglages, etat, MAINTENANT)
    assert set(plan["strategies"]) == {"tendance_4h", "cassure_4h", "rapide"}
    for res in plan["strategies"].values():
        assert res["base"] is not None, res.get("note")
        assert res["essais"]
    # On force un choix pour vérifier l'écriture, puis la vérification de la semaine suivante.
    res = plan["strategies"]["rapide"]
    res["choix"] = {"reglage": "ADX_RAPIDE_MIN", "avant": 20.0, "apres": 25, "score": score(5, 2, 3)}
    donnees = {"journal": [], "ordres": [
        {"statut": "ferme", "ferme_le": "2026-12-12T10:00:00Z", "resultat": 1.5, "strategie": "rapide"},
        {"statut": "ferme", "ferme_le": "2026-11-01T10:00:00Z", "resultat": -9, "strategie": "rapide"}]}
    texte, donnees, etat = am.appliquer(plan, REGLAGES, donnees, etat, MAINTENANT)
    assert am.lire_reglages(texte)["ADX_RAPIDE_MIN"] == "25"
    assert am.lire_reglages(texte)["PERTE_MAX_PCT"] == "50"
    assert etat["en_observation"]["rapide"]["apres"] == 25
    lignes = [l["texte"] for l in donnees["journal"]]
    assert any("CHANGEMENT ADOPTÉ" in l for l in lignes)
    assert any("Rapide 5 min +1.50 € (1 trade)" in l for l in lignes)
    assert donnees["amelioration"]["reglages"]["rapide"]["ADX_RAPIDE_MIN"] == 25

    # Semaine suivante : le nouveau réglage fait moins bien -> retour en arrière + valeur interdite
    suivant = MAINTENANT + pd.Timedelta(days=7)
    plan2 = {"strategies": {"rapide": {"base": score(1, 0, 1), "essais": [], "choix": None, "verification": {
        **etat["en_observation"]["rapide"], "score_nouveau": {"R": -2.0}, "score_ancien": {"R": 1.0}, "annuler": True}}}}
    texte2, donnees, etat = am.appliquer(plan2, texte, donnees, etat, suivant)
    assert am.lire_reglages(texte2)["ADX_RAPIDE_MIN"] == "20"
    assert "rapide.ADX_RAPIDE_MIN=25" in etat["interdits"]
    assert "rapide" not in etat["en_observation"]
    assert any("RETOUR EN ARRIÈRE" in l["texte"] for l in donnees["journal"])


def test_mode_suggestions_ne_change_rien():
    r = REGLAGES.replace('AUTO_AMELIORATION="auto"', 'AUTO_AMELIORATION="suggestions"')
    plan = {"strategies": {"rapide": {"base": score(1, 0, 1), "essais": [{}], "verification": None,
                                      "choix": {"reglage": "ADX_RAPIDE_MIN", "avant": 20.0, "apres": 25,
                                                "score": score(5, 2, 3)}}}}
    texte, donnees, etat = am.appliquer(plan, r, {}, {}, MAINTENANT)
    assert texte == r
    assert "rapide" not in etat["en_observation"]
    assert any("SUGGESTION" in l["texte"] for l in donnees["journal"])

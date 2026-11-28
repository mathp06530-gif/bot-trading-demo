"""Contrôles de la piste amplitude : pas de fuite, le spread est payé, le seuil s'abstient, l'embargo tient."""
import numpy as np
import pandas as pd

from ia import amplitude as A


def _prix(n=900, graine=1):
    rng = np.random.default_rng(graine)
    mid = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    return pd.DataFrame({"open": mid, "high": mid * 1.001, "low": mid * 0.999, "close": mid, "volume": 1.0}, index=idx)


def test_marche_plat_paye_le_spread_des_deux_cotes():
    idx = pd.date_range("2024-06-03 10:00", periods=4, freq="h")  # loin de 22 h UTC : pas de frais de nuit
    d = pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0}, index=idx)
    brut = A.vers_bid_ask(d, 0.02)
    from ia.predire import gains_trades
    achat, vente = gains_trades(brut, 1, 0.0, 0.0)
    # achat au ask, revente au bid : un prix immobile coûte exactement le spread, dans les deux sens
    assert abs(achat[0] * 100 + 0.02) < 1e-9
    assert abs(vente[0] * 100 + 0.02) < 1e-9


def test_frais_de_nuit_quand_on_passe_22h():
    idx = pd.date_range("2024-06-03 21:00", periods=3, freq="h")  # 21 h, 22 h, 23 h
    close = np.array([100.0, 100.2, 100.1])
    d = pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1.0}, index=idx)
    f = A.cibles(d, spread_pct=0.02, nuit_pct=0.01, minutes=60, saut_max=0.5)
    # la bougie de 21 h sort à 22 h : une nuit est comptée ; celle de 22 h sort à 23 h : aucune
    assert f.loc[idx[0], "cout"] == 0.03
    assert f.loc[idx[1], "cout"] == 0.02
    assert f.loc[idx[0], "gain_achat"] < f.loc[idx[0], "mv"] - 0.02


def test_pessimiste_sabstient_si_le_mouvement_reste_dans_le_spread():
    idx = pd.date_range("2024-01-01", periods=4, freq="h")
    f = pd.DataFrame({"cout": [0.05, 0.05, 0.05, 0.05], "mv": [0.1, -0.1, 0.01, -0.2],
                      "gain_achat": [0.05, -0.15, -0.04, -0.25], "gain_vente": [-0.15, 0.05, -0.06, 0.15]}, index=idx)
    pred = pd.DataFrame({"q25": [0.06, -0.02, -0.01, -0.04], "q50": [0.08, -0.04, 0.0, -0.11],
                         "q75": [0.1, -0.01, 0.02, -0.06], "k": [1.0, 1.0, np.nan, 2.0]}, index=idx)
    cote = A.cotes(pred, f)
    assert list(cote["pessimiste"]) == [1, 0, 0, -1]
    # médiane : k manquant -> on ne parie pas ; k=2 exige 2 fois le coût (0,11 > 0,10)
    assert list(cote["mediane"]) == [1, 0, 0, -1]


def test_features_ignorent_la_bougie_suivante():
    d = _prix()
    f1 = A.table(d, 0.01, 0.0, 60, 0.5)
    d2 = d.copy()
    d2.iloc[-1, d2.columns.get_loc("close")] *= 1.2
    f2 = A.table(d2, 0.01, 0.0, 60, 0.5)
    cols = [c for c in f1.columns if c not in A.CIBLES]
    pd.testing.assert_frame_equal(f1[cols], f2[cols])
    # la cible de la dernière bougie gardée voit la clôture suivante ; ses indicateurs, non
    assert f1.iloc[-1]["mv"] != f2.iloc[-1]["mv"]


def test_embargo_du_walk_forward():
    rng = np.random.default_rng(0)
    n = 2500
    idx = pd.date_range("2024-01-01", periods=n, freq="h")
    x = rng.normal(size=n)
    mv = np.roll(x, -1)  # prévisible, mais le test vérifie surtout les dates
    mv[-1] = 0.01
    f = pd.DataFrame({"x": x, "mv": mv, "cout": 0.01, "gain_achat": mv - 0.01, "gain_vente": -mv - 0.01, "y": mv > 0}, index=idx)
    A.ARBRES = 8
    A.MIN_TRAIN["60min"] = 80
    try:
        pred = A.marcher(f, 60)
    finally:
        A.ARBRES = int(__import__("os").getenv("AMPLITUDE_ARBRES", "80"))
        A.MIN_TRAIN["60min"] = 1800
    connus = pred.index[np.isfinite(pred["q50"])]
    assert len(connus) > 50
    # le premier mois prédit ne commence qu'une fois le minimum d'apprentissage passé
    assert connus.min() >= idx[80]


def test_melange_garde_les_rendements_mais_change_leur_ordre():
    d = _prix(400, 3)
    m = A.melanger(d, 7)
    r = np.diff(np.log(d.close.to_numpy()))
    s = np.diff(np.log(m.close.to_numpy()))
    assert not np.allclose(r, s)
    assert np.allclose(np.sort(r), np.sort(s))


def test_verdict_rejette_le_controle_melange_et_le_gain_negatif():
    bon = {"n": 200, "gain": 0.01, "reussite": 0.56, "sens_majoritaire": 0.51, "melange": 0.50,
           "marches_gagnants": 6, "mois": 8}
    assert A.verdict("pessimiste", bon, court=False, gain_choix=0.01) == "confirmée"
    assert A.verdict("pessimiste", bon, court=False, gain_choix=-0.01) == "prometteuse"
    assert A.verdict("pessimiste", {**bon, "melange": 0.55}, court=False) == "rejetée"
    assert A.verdict("pessimiste", {**bon, "gain": -0.01}, court=False) == "rejetée"
    assert A.verdict("pessimiste", bon, court=True) == "prometteuse"
    assert A.verdict(None, bon, court=False) == "rejetée"


def test_regle_choisie_sur_le_choix_pas_sur_le_juge():
    def bloc(gain_choix, reussite=0.50):
        return {"choix": {"gain": gain_choix, "reussite": reussite}, "juge": {"gain": 9.0, "reussite": 0.9}}

    def marche(pc, pm, mel_m=0.50):
        return {"reel": {"pessimiste": bloc(pc), "mediane": bloc(pm), "sens_seul": bloc(0)},
                "melange": {"pessimiste": bloc(0.0), "mediane": bloc(0.0, mel_m), "sens_seul": bloc(0)}}

    par = {e: marche(-0.02, 0.03) for e in ("GOLD", "SILVER", "EURUSD", "US100")}
    regle, gain = A.choisir_regle(par)
    assert regle == "mediane" and gain == 0.03
    # prix mélangés trop hauts : la médiane est éliminée, même si son gain jugé (ignoré) est énorme
    par2 = {e: marche(0.05, 0.08, mel_m=0.60) for e in ("GOLD", "SILVER", "EURUSD", "US100")}
    regle2, _ = A.choisir_regle(par2)
    assert regle2 == "pessimiste"

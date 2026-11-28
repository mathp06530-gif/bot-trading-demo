"""Le filtre d'amplitude ne change pas le sens du vote, et le test au hasard retire le même nombre de trades."""
import numpy as np
import pandas as pd

from ia.vote4h_amplitude import cotes_vote, choisir_k, hasard, mesurer, verdict


def test_le_filtre_garde_le_sens_du_vote():
    vote = np.array([0.8, 0.8, 0.2, 0.9, 0.1])
    q50 = np.array([0.05, 0.001, -0.05, -0.04, 0.0001])  # signes parfois contraires au vote
    cout = np.full(5, 0.01)
    top = np.array([True, True, True, False, True])
    seul, filtre = cotes_vote(vote, q50, cout, top, k=1.0)
    # le 2e et le 5e sont trop petits ; le 4e n'est pas dans le top 5 %
    assert list(seul) == [1, 1, -1, 0, -1]
    assert list(filtre) == [1, 0, -1, 0, 0]
    # le 3e vote baisse alors que la médiane est négative aussi : on garde la baisse du vote
    assert filtre[2] == -1


def test_k_fige_a_un():
    vote = np.array([0.9, 0.9])
    q50 = np.array([0.015, 0.005])
    cout = np.array([0.01, 0.01])
    top = np.array([True, True])
    _, k1 = cotes_vote(vote, q50, cout, top, k=1.0)
    _, k2 = cotes_vote(vote, q50, cout, top, k=2.0)
    assert list(k1) == [1, 0]
    assert list(k2) == [0, 0]


def test_hasard_retire_le_meme_nombre_et_reconnait_un_vrai_filtre():
    rng = np.random.default_rng(1)
    gains = rng.normal(0, 1, 400)
    garder = np.zeros(400, bool)
    garder[:80] = True  # les 80 premiers, pas meilleurs que le hasard
    gains[:80] += 2.0  # sauf si on les rend vraiment meilleurs
    h = hasard(gains, garder, n=200, graine=3)
    assert h["n_gardes"] == 80 and h["n_total"] == 400
    assert h["mieux"] >= 0.95


def test_hasard_rejette_un_filtre_qui_garde_les_pires():
    gains = np.linspace(-1, 1, 300)
    garder = np.zeros(300, bool)
    garder[:60] = True
    h = hasard(gains, garder, n=100, graine=0)
    assert h["n_gardes"] == 60 and h["mieux"] <= 0.05


def test_verdict():
    a = {"gain": 0.01, "n": 200}
    b = {"gain": 0.02, "n": 120, "marches_gagnants": 6, "reussite": 0.56, "sens_majoritaire": 0.51}
    assert verdict(a, b, 0.97, 0.50, True) == "confirmée"
    assert verdict(a, b, 0.70, 0.50, True) == "prometteuse"
    assert verdict(a, b, 0.97, 0.55, True) == "rejetée"
    assert verdict({"gain": 0.03, "n": 200}, b, 0.99, 0.50, True) == "rejetée"
    assert verdict(a, {"gain": -0.01, "n": 120, "marches_gagnants": 6, "reussite": 0.56, "sens_majoritaire": 0.51},
                   0.99, 0.50, True) == "rejetée"


def test_k_choisi_sur_le_choix_seulement():
    k, gain = choisir_k([(1.0, -0.01, 100), (1.5, 0.02, 80), (2.0, 0.05, 10)])
    assert k == 1.5 and gain == 0.02  # k=2 a trop peu de trades


def test_gain_paie_le_cout_et_compte_les_instants():
    idx = pd.date_range("2024-12-01", periods=4, freq="4h")
    cote = np.array([1, -1, 0, 1])
    mv = np.array([0.05, -0.02, 0.1, 0.0])
    cout = np.array([0.01, 0.01, 0.01, 0.01])
    r = mesurer(idx, cote, mv, cout, idx[0], idx[-1] + pd.Timedelta(days=1))
    assert r["n"] == 3 and r["instants"] == 3
    assert abs(r["gain"] - np.mean([0.04, 0.01, -0.01])) < 1e-4
    assert r["sens_majoritaire"] == round(2 / 3, 4)

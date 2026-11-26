import numpy as np
import pandas as pd

from bot import simulateur as S


def _bougies(n, unite_h=4, graine=0, derive=0.0):
    rng = np.random.default_rng(graine)
    c = 100 * np.exp(np.cumsum(rng.normal(derive, 0.01, n)))
    t = pd.date_range("2026-01-01", periods=n, freq=f"{unite_h}h", tz="UTC")
    out, prev = [], 100.0
    for ti, ci in zip(t, c):
        o = prev
        h, l = max(o, ci) * 1.002, min(o, ci) * 0.998
        px = lambda v: {"bid": v - 0.01, "ask": v + 0.01}
        out.append({"snapshotTimeUTC": ti.strftime("%Y-%m-%dT%H:%M:%S"), "openPrice": px(o), "highPrice": px(h),
                    "lowPrice": px(l), "closePrice": px(ci)})
        prev = ci
    return out


def test_symetrique_proche_de_50_50():
    b = _bougies(800)
    prix = (b[-1]["closePrice"]["bid"] + b[-1]["closePrice"]["ask"]) / 2
    p = {"id": "x", "sens": "BUY", "prix_entree": prix, "stop": prix * 0.97, "objectif": prix * 1.03}
    s = S.pour_position(p, b, "HOUR_4")
    assert s and abs(s["p_stop"] - s["p_objectif"]) < 12
    assert abs(s["p_stop"] + s["p_objectif"] + s["p_aucun"] - 100) < 0.5
    assert s["prix_p5"] < s["prix_median"] < s["prix_p95"]


def test_sans_tp_objectif_2R_et_vente():
    b = _bougies(400, unite_h=1)
    prix = (b[-1]["closePrice"]["bid"] + b[-1]["closePrice"]["ask"]) / 2
    p = {"id": "y", "sens": "SELL", "prix_entree": prix, "stop": prix * 1.01, "objectif": None}
    s = S.pour_position(p, b, "MINUTE_5")
    assert s["objectif_type"] == "gain de 2 R" and s["objectif"] < prix
    assert s["p_stop"] > s["p_objectif"]  # 2 R est plus loin que le stop


def test_stop_qui_protege_un_gain_et_peu_de_bougies():
    b = _bougies(400)
    prix = (b[-1]["closePrice"]["bid"] + b[-1]["closePrice"]["ask"]) / 2
    p = {"id": "z", "sens": "BUY", "prix_entree": prix * 0.9, "stop": prix * 0.95, "objectif": None}
    s = S.pour_position(p, b, "HOUR_4")
    assert s["stop_en_gain"] and s["objectif"] is None and s["p_objectif"] == 0
    assert S.pour_position(p, b[:30], "HOUR_4") is None


def test_publier_ne_plante_jamais():
    d = {"positions": [{"id": "a", "marche": "GOLD", "strategie": "rapide", "sens": "BUY", "prix_entree": 1, "stop": None}]}
    assert S.publier(d, {}, []) == {} and d["simulations"] == {}


def test_meme_resultat_pendant_une_bougie():
    b = _bougies(500)
    prix = (b[-1]["closePrice"]["bid"] + b[-1]["closePrice"]["ask"]) / 2
    p = {"id": "q", "sens": "BUY", "prix_entree": prix, "stop": prix * 0.98, "objectif": None}
    assert S.pour_position(p, b, "HOUR_4") == S.pour_position(p, b, "HOUR_4")

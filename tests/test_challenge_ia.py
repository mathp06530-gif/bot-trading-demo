"""Challenge prop firm simulé : règles +10 % / -5 % par jour / -10 % et une position à la fois par marché."""
from ia import challenge_ia as C


def _it(ech, mv, up=1, sp=0.0, e="GOLD", h=5):
    return {"id": f"{ech}|{e}|{h}", "t": C.iso(ech - 60 * h), "ech": ech, "e": e, "h": h, "mv": mv, "up": up, "sp": sp, "ty": "COMMODITIES"}


def test_objectif_reussi_puis_nouvelle_tentative():
    ch = C.Challenge()
    t = 1_800_000_000
    for k in range(20):
        ch.trade(_it(t + 60 * k, 1.0), True, 1.0)  # +1 % par trade
        if ch.tentatives[0]["resultat"] != "en_cours":
            break
    assert ch.tentatives[0]["resultat"] == "reussi"
    assert ch.c["solde"] == C.CAPITAL and len(ch.tentatives) == 2


def test_perte_du_jour_et_spread_paye():
    ch = C.Challenge()
    ch.trade(_it(1_800_000_000, 0.0, sp=0.1), True, 1.0)
    assert ch.c["solde"] == C.CAPITAL * (1 - 0.001)  # le spread seul coûte
    ch.trade(_it(1_800_000_060, -6.0, up=0), True, 1.0)
    assert ch.tentatives[0]["resultat"] == "rate_jour"


def test_une_position_par_marche_et_temoin_hasard():
    s = C.SuperIAChallenge()
    s.e["mouvement"] = {"GOLD": [0.05, 10]}
    preds = {"fixe": {"q": 0.7, "brut": 0.7, "sure": True}, "evolutive": {"q": 0.7, "brut": 0.7, "sure": False}}
    a = _it(1_800_000_300, 0.1) | {"p": {"sundial": 0.7}}
    b = _it(1_800_000_360, 0.1) | {"p": {"sundial": 0.7}}  # ouverte pendant a : ignorée
    s.apprendre(a, preds)
    s.apprendre(b, preds)
    d = s.ch["5"]
    assert d["fixe_toujours"].c["trades"] == 1 and d["fixe_sure"].c["trades"] == 1
    assert d["evolutive_sure"].c["trades"] == 0 and d["hasard"].c["trades"] == 1

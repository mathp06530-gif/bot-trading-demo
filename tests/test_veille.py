from datetime import datetime, timezone

from bot import actualites, veille
from bot.garde_fous import GardeFous

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Gold rises as Fed signals rate cuts</title><link>https://x/1</link><pubDate>Wed, 25 Nov 2026 14:00:00 GMT</pubDate></item>
<item><title>Tesla deliveries beat estimates</title><link>https://x/2</link><pubDate>Wed, 25 Nov 2026 15:00:00 +0000</pubDate></item>
</channel></rss>"""


def test_titres_classes_par_sujet():
    t = veille.lire_rss(RSS)
    assert t[0]["sujets"] == ["Fed / taux"] and t[0]["date"] == "2026-11-25T14:00Z"
    assert "résultats" in t[1]["sujets"]


def test_resultats_nasdaq():
    page = {"data": {"rows": [{"symbol": "AAPL", "time": "time-pre-market"}, {"symbol": "TSLA", "time": "time-after-hours"}]}}
    assert veille.lire_nasdaq(page, "TSLA", "2027-01-27") == "2027-01-27T21:05Z"
    assert veille.lire_nasdaq(page, "AAPL", "2027-01-27") == "2027-01-27T13:00Z"
    assert veille.lire_nasdaq({"data": None}, "TSLA", "2027-01-27") is None


def test_pause_tesla_autour_des_resultats_seulement_sur_tesla():
    d = {}
    t = datetime(2027, 1, 27, 12, tzinfo=timezone.utc)
    veille.mettre_a_jour(d, t, ["GOLD", "TSLA"], lire_titres=lambda s: veille.lire_rss(RSS),
                         lire_resultats=lambda a, m: {"TSLA": "2027-01-27T21:05Z"})
    assert len(d["veille"]["titres"]["GOLD"]) == 2
    p = actualites.pauses_marches(d, t)
    assert list(p) == ["TSLA"] and "résultats" in p["TSLA"]
    assert actualites.pauses_marches(d, datetime(2027, 1, 29, tzinfo=timezone.utc)) == {}
    garde = GardeFous({}, 100, [], 1.0)
    garde.pauses_marches = p
    assert not garde.autoriser(1, 10, "usine", "TSLA")[0]
    assert garde.autoriser(1, 10, "cassure_4h", "GOLD")[0]


def test_stocks_de_gaz_pause_seulement_le_gaz():
    d = {"actualites": {"annonces": [{"date": "2026-11-26T15:30Z", "titre": "Natural Gas Storage", "marches": ["NATURALGAS"]}]}}
    t = datetime(2026, 11, 26, 15, 20, tzinfo=timezone.utc)
    assert actualites.annonce_en_cours(d, t) is None  # pas de pause générale
    assert "Natural Gas Storage" in actualites.pauses_marches(d, t)["NATURALGAS"]


def test_source_en_panne_le_bot_continue():
    def panne(*a):
        raise OSError("hors ligne")
    d = {}
    soucis = veille.mettre_a_jour(d, datetime(2027, 1, 1, tzinfo=timezone.utc), ["GOLD", "TSLA"],
                                  lire_titres=panne, lire_resultats=panne)
    assert len(soucis) == 3 and d["veille"]["titres"]["GOLD"] == []

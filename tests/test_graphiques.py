"""Graphiques de l'appli : calculés à partir des bougies déjà vues, sans appel à Capital.com ni ordre."""
import json
import math
from datetime import datetime, timedelta, timezone

from bot import graphiques as G
from bot import usine


def fausses_bougies(n, pas_s, depart=3500.0, graine=1):
    t0 = datetime(2026, 11, 26, 8, 0, tzinfo=timezone.utc) - timedelta(seconds=pas_s * n)
    sortie, prix = [], depart
    for i in range(n):
        prix *= 1 + 0.004 * math.sin(i / 7 + graine) + 0.0015 * math.cos(i / 3)
        o, c = prix, prix * (1 + 0.002 * math.sin(i))
        h, l = max(o, c) * 1.002, min(o, c) * 0.998
        px = lambda x: {"bid": round(x - 0.1, 3), "ask": round(x + 0.1, 3)}
        sortie.append({"snapshotTimeUTC": (t0 + timedelta(seconds=pas_s * i)).strftime("%Y-%m-%dT%H:%M:%S"),
                       "openPrice": px(o), "highPrice": px(h), "lowPrice": px(l), "closePrice": px(c)})
    return sortie


def cache_complet():
    cache = {}
    for epic in ("GOLD", "SILVER", "ETHUSD", "NATURALGAS", "TSLA"):
        cache[(epic, "HOUR_4")] = fausses_bougies(1000, 14400)
        cache[(epic, "HOUR")] = fausses_bougies(400, 3600)
        cache[(epic, "MINUTE_5")] = fausses_bougies(300, 300)
    return cache


def test_tous_les_graphiques_sont_produits(tmp_path, monkeypatch):
    from bot import elan, supertrend, rapide
    monkeypatch.setattr(elan, "LISTE", ["GOLD", "SILVER"])
    monkeypatch.setattr(supertrend, "LISTE", ["ETHUSD"])
    monkeypatch.setattr(rapide, "LISTE", ["GOLD"])
    cache = cache_complet()
    t_entree = cache[("GOLD", "MINUTE_5")][-20]["snapshotTimeUTC"] + "Z"
    donnees = {"ordres": [{"id": "D1", "strategie": "rapide", "marche": "GOLD", "sens": "BUY", "ouvert_le": t_entree}]}
    G.publier(donnees, cache, tmp_path)
    index = json.loads((tmp_path / "index.json").read_text())
    ids = {g["id"] for g in index["graphiques"]}
    attendus = {"cassure_4h-GOLD", "cassure_4h-SILVER", "rapide-GOLD", "elan_4h-GOLD", "elan_4h-SILVER",
                "supertrend_4h-ETHUSD"} | {f"usine-{s['epic']}" for s in usine.STRATEGIES}
    assert attendus <= ids
    r = json.loads((tmp_path / "rapide-GOLD.json").read_text())
    assert len(r["bougies"]["t"]) == G.N_AFFICHE == len(r["lignes"][0]["v"])
    assert r["conditions"] and all("texte" in c for c in r["conditions"])
    assert "D1" in r["conditions_trades"]  # conditions au moment de l'entrée
    assert "rapide-GOLD" in donnees["graph_live"] and len(donnees["graph_live"]["rapide-GOLD"]) == 5
    u = json.loads((tmp_path / f"usine-{usine.STRATEGIES[0]['epic']}.json").read_text())
    assert u["oscillateur"] and u["oscillateur"]["histo"]


def test_fichier_reecrit_seulement_si_change(tmp_path):
    cache = cache_complet()
    assert G.publier({}, cache, tmp_path)  # 1er passage : fichiers écrits
    assert G.publier({}, cache, tmp_path) == []  # mêmes bougies : rien à réécrire (dépôt léger)


def test_sans_bougies_aucune_erreur(tmp_path):
    donnees = {}
    assert G.publier(donnees, {}, tmp_path) == []
    assert donnees["graph_live"] == {}

"""Télécharge l'historique BTCUSD du compte DÉMO Capital.com (bid + ask, donc spread réel)
et les conditions du marché (frais de nuit, stop garanti). Lancé par GitHub Actions.

Résultat : backtest/donnees/<EPIC>_<UNITE>.csv et backtest/donnees/<EPIC>_marche.json
"""
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.capital import CapitalDemo  # noqa: E402

DOSSIER = Path(__file__).resolve().parent / "donnees"
EPICS = [e.strip() for e in os.getenv("EPICS", "BTCUSD").split(",") if e.strip()]
TOUTES = {"MINUTE": (1, 90), "MINUTE_5": (5, 150), "MINUTE_15": (15, 400), "HOUR": (60, 730)}  # unité : (minutes, jours d'historique)
DEMANDES = {u: TOUTES[u] for u in os.getenv("UNITES", "MINUTE,MINUTE_15,HOUR").split(",")}


def telecharger(api, EPIC, unite, minutes, jours):
    fin = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    debut_total = fin - timedelta(days=jours)
    pas = timedelta(minutes=minutes * 900)
    lignes = {}
    a = fin
    vides = 0
    while a > debut_total and vides < 3:
        de = max(a - pas, debut_total)
        try:
            rep = api._requete("GET", f"/prices/{EPIC}", params={
                "resolution": unite, "max": 1000,
                "from": de.strftime("%Y-%m-%dT%H:%M:%S"), "to": a.strftime("%Y-%m-%dT%H:%M:%S")})
            prix = rep.get("prices", [])
        except Exception as e:
            print(f"{unite} {de} -> {a} : {e}")
            prix = []
        vides = vides + 1 if not prix else 0
        for b in prix:
            lignes[b["snapshotTimeUTC"]] = [
                b["snapshotTimeUTC"],
                b["openPrice"]["bid"], b["openPrice"]["ask"], b["highPrice"]["bid"], b["highPrice"]["ask"],
                b["lowPrice"]["bid"], b["lowPrice"]["ask"], b["closePrice"]["bid"], b["closePrice"]["ask"],
                b.get("lastTradedVolume", 0)]
        a = de
        time.sleep(0.3)
    with open(DOSSIER / f"{EPIC}_{unite}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask",
                    "close_bid", "close_ask", "volume"])
        for k in sorted(lignes):
            w.writerow(lignes[k])
    print(f"{unite} : {len(lignes)} bougies, de {min(lignes) if lignes else '-'} à {max(lignes) if lignes else '-'}")


def principal():
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    DOSSIER.mkdir(parents=True, exist_ok=True)
    for epic in EPICS:
        try:
            marche = api.marche(epic)
        except Exception as e:
            print(f"{epic} : marché introuvable ({e})")
            continue
        (DOSSIER / f"{epic}_marche.json").write_text(json.dumps(marche, indent=1, ensure_ascii=False))
        for unite, (minutes, jours) in DEMANDES.items():
            telecharger(api, epic, unite, minutes, jours)
    api.deconnexion()


if __name__ == "__main__":
    principal()

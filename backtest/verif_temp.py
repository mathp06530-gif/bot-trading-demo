import json, os, sys
sys.path.insert(0, ".")
from bot.capital import CapitalDemo
api = CapitalDemo(*(os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD")))
api.connexion()
def montrer(titre, chemin, **p):
    try:
        r = api._requete("GET", chemin, params=p)
    except Exception as e:
        r = str(e)
    print("=====", titre); print(json.dumps(r, indent=1)[:15000])
montrer("activity", "/history/activity", **{"from": "2026-11-25T12:00:00", "to": "2026-11-25T18:00:00", "detailed": "true"})
montrer("transactions", "/history/transactions", **{"from": "2026-11-25T12:00:00", "to": "2026-11-25T18:00:00"})
montrer("positions", "/positions")
api.deconnexion()

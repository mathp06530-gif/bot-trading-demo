"""Enregistre chaque minute le « Client Sentiment » Capital.com (part des clients acheteurs / vendeurs) et le prix
des 8 marchés à petits frais. Aucun ordre. Pas d'historique chez Capital.com : on le construit nous-mêmes, pour tester
vers le 11/12 si la foule (en contrarien) aide à prédire (piste 4 du rapport PISTES_BOOST).

Publication : branche « ia-sentiment », un fichier par jour (AAAA-MM-JJ.jsonl), ajouté (jamais écrasé).
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot.capital import CapitalDemo  # noqa: E402

MARCHES = ["GOLD", "SILVER", "OIL_CRUDE", "US100", "US500", "DE40", "EURUSD", "GBPUSD"]
DOSSIER = Path(os.getenv("SENTIMENT_DOSSIER", "sentiment_pub"))
DUREE = int(os.getenv("SENTIMENT_DUREE_S", "3420"))


def git(*a):
    return subprocess.run(["git", *a], cwd=DOSSIER, capture_output=True, text=True, timeout=120)


def preparer():
    url = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True).stdout.strip()
    auth = subprocess.run(["git", "config", "--get-regexp", r"http\..*\.extraheader"], capture_output=True, text=True).stdout
    DOSSIER.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(DOSSIER)])
    for ligne in auth.splitlines():
        k, v = ligne.split(" ", 1)
        git("config", k, v)
    git("remote", "add", "origin", url)
    git("config", "user.name", "bot-trading-demo")
    git("config", "user.email", "bot-trading-demo@users.noreply.github.com")


def envoyer(lignes):
    if not lignes:
        return True
    for essai in range(3):
        if git("fetch", "-q", "origin", "ia-sentiment").returncode == 0:
            git("checkout", "-q", "-f", "-B", "ia-sentiment", "FETCH_HEAD")
        else:
            git("checkout", "-q", "--orphan", "ia-sentiment")
        par_jour = {}
        for l in lignes:
            par_jour.setdefault(l["t"][:10], []).append(l)
        for jour, ls in par_jour.items():
            with open(DOSSIER / f"{jour}.jsonl", "a") as f:
                for l in ls:
                    f.write(json.dumps(l, separators=(",", ":")) + "\n")
        git("add", "-A")
        git("commit", "-qm", f"Sentiment {lignes[-1]['t']}")
        if git("push", "-q", "origin", "ia-sentiment").returncode == 0:
            return True
        time.sleep(5)
    return False


def principal():
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    preparer()
    debut, dernier_envoi, tampon, connecte = time.time(), time.time(), [], time.time()
    while time.time() - debut < DUREE:
        t0 = time.time()
        try:
            if time.time() - connecte > 480:  # la session expire après 10 min
                api.deconnexion()
                api.connexion()
                connecte = time.time()
            t = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            s = api._requete("GET", "/clientsentiment", params={"marketIds": ",".join(MARCHES)}).get("clientSentiments", [])
            m = api._requete("GET", "/markets", params={"epics": ",".join(MARCHES)}).get("marketDetails", [])
            prix = {}
            for x in m:
                sn = x.get("snapshot", {})
                prix[x.get("instrument", {}).get("epic")] = [sn.get("bid"), sn.get("offer"), sn.get("marketStatus")]
            for x in s:
                e = x.get("marketId")
                tampon.append({"t": t, "e": e, "long": x.get("longPositionPercentage"), "short": x.get("shortPositionPercentage"),
                               "bid": (prix.get(e) or [None])[0], "ask": (prix.get(e) or [None, None])[1],
                               "etat": (prix.get(e) or [None, None, None])[2]})
        except Exception as ex:
            print("erreur :", str(ex)[:200], flush=True)
        if time.time() - dernier_envoi > 600 and tampon:
            if envoyer(tampon):
                print(f"{len(tampon)} lignes envoyées", flush=True)
                tampon = []
            dernier_envoi = time.time()
        time.sleep(max(1.0, 60 - (time.time() - t0)))
    envoyer(tampon)
    api.deconnexion()


if __name__ == "__main__":
    principal()

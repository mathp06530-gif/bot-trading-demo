"""Boosts en test « à côté » des IA originales (aucun ordre, n'influence pas le direct).

Chaque heure : relit toutes les prédictions jugées (ia-archives + juges.json), refait le walk-forward
(entraînement uniquement sur ce qui était connu avant chaque heure testée) et publie boost.json sur la branche ia-boost.
Les chiffres « en direct » ne comptent que les heures APRÈS la mise en route (EN_DIRECT_DEPUIS) : des prédictions
que le correcteur n'avait jamais vues, faites heure par heure comme en vrai.
"""
import gzip
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ia.boost.tester as T  # noqa: E402

EN_DIRECT_DEPUIS = "2026-11-27T19:00:00Z"
HZ = [15, 5, 60]
DOSSIER = Path(os.getenv("BOOST_DOSSIER", "boost_pub"))
REPO = Path(__file__).resolve().parents[2]


def g(*a, cwd=REPO):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True).stdout


def charger():
    for b in ("ia-archives", "ia-journal"):
        subprocess.run(["git", "fetch", "-q", "origin", b], cwd=REPO)
    items = {}
    for f in g("ls-tree", "-r", "--name-only", "origin/ia-archives").decode().split():
        for ligne in gzip.decompress(g("show", f"origin/ia-archives:{f}")).decode().splitlines():
            if ligne.strip():
                x = json.loads(ligne); items[x["id"]] = x
    try:
        for x in json.loads(g("show", "origin/ia-journal:juges.json"))["items"]:
            items[x["id"]] = x
    except Exception:
        pass
    return list(items.values())


def stats(lst, depuis=None):
    if depuis:
        lst = [(s, x) for s, x in lst if x["t"] >= depuis]
    r = T.resume(lst)
    if not r:
        return None
    return {"n": r["n"], "instants": r["inst"], "reussite": round(r["acc"], 4), "gain": round(r["gain"], 5),
            "sens_majoritaire": round(r["maj"], 4)}


def principal():
    X = T.preparer(charger())
    T.MODELES = sorted({m for x in X for m in x["p"]})
    T.contexte(X)
    Y = T.preparer([{k: v for k, v in x.items() if k not in ("t0", "vote", "hp")} for x in T.melanger(X, 7)])
    T.contexte(Y)
    sortie = {"maj": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "en_direct_depuis": EN_DIRECT_DEPUIS,
              "marches": T.P8, "horizons": {}}
    for h in HZ:
        reel, faux = T.evaluer(X, h), T.evaluer(Y, h)
        sortie["horizons"][str(h)] = {s: {"en_direct": stats(lst, EN_DIRECT_DEPUIS), "test_complet": stats(lst),
                                          "prix_melanges": stats(faux.get(s, []))} for s, lst in reel.items()}
    DOSSIER.mkdir(exist_ok=True)
    (DOSSIER / "boost.json").write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps(sortie["horizons"].get("15", {}), ensure_ascii=False)[:2000])
    if os.getenv("BOOST_GIT", "oui") == "oui":
        url = g("config", "--get", "remote.origin.url").decode().strip()
        auth = [c for l in g("config", "--get-regexp", r"http\..*\.extraheader").decode().splitlines()
                for c in ("-c", "=".join(l.split(" ", 1)))]  # mêmes droits que le checkout du workflow
        for a in (["init", "-q"], ["checkout", "-q", "-b", "ia-boost"], ["add", "-A"],
                  ["-c", "user.name=bot-trading-demo", "-c", "user.email=bot-trading-demo@users.noreply.github.com", "commit", "-qm", "Boosts " + sortie["maj"]],
                  [*auth, "push", "-q", "-f", url, "ia-boost"]):
            r = subprocess.run(["git", *a], cwd=DOSSIER, capture_output=True, text=True)
            if r.returncode:
                print("git", a, r.stderr[:300])

if __name__ == "__main__":
    principal()

"""Essai des IA géantes : chargement, vitesse et sortie sur 80 séries de prix simulées. Écrit ia/geantes/ETAT.json."""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ia.geantes import Geantes  # noqa: E402

import os  # noqa: E402
rng0 = np.random.default_rng(1)
np.savez("entrainement_essai.npz", series=np.array([100 * np.exp(np.cumsum(rng0.normal(0, 5e-4, 1000))) for _ in range(20)], dtype=object))
os.environ["IA_ENTRAINEMENT"] = os.path.abspath("entrainement_essai.npz")
t0 = time.time()
g = Geantes(attente_chargement=1200)
charge = time.time() - t0
rng = np.random.default_rng(0)
n, L = 24, 512
prix = 100 * np.exp(np.cumsum(rng.normal(0, 5e-4, (n, L)), axis=1))
ohlcv = np.stack([prix, prix * 1.0003, prix * 0.9997, prix, np.full_like(prix, 10.0)], axis=2)
res = {"chargement_s": round(charge), "etat": g.etat, "tours": []}
for k in range(3):
    probas, infos = g.prevoir(prix, ohlcv, [5, 15, 30, 60], delai=60)
    res["tours"].append({"infos": infos, "exemple": {m: [round(float(x), 3) for x in p[:5]] for m, p in probas.items()}})
    print(json.dumps(res["tours"][-1], ensure_ascii=False)[:3000], flush=True)
g.fermer()
Path(sys.argv[1]).write_text(json.dumps(res, indent=1, ensure_ascii=False))

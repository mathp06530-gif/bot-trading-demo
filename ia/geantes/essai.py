"""Essai des IA géantes : chargement, vitesse et sortie sur 80 séries de prix simulées. Écrit ia/geantes/ETAT.json."""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ia.geantes import Geantes  # noqa: E402

t0 = time.time()
g = Geantes()
charge = time.time() - t0
rng = np.random.default_rng(0)
n, L = 80, 512
prix = 100 * np.exp(np.cumsum(rng.normal(0, 5e-4, (n, L)), axis=1))
ohlcv = np.stack([prix, prix * 1.0003, prix * 0.9997, prix, np.full_like(prix, 10.0)], axis=2)
res = {"chargement_s": round(charge), "etat": g.etat, "tours": []}
for k in range(3):
    probas, infos = g.prevoir(prix, ohlcv, 1, delai=120)
    res["tours"].append({"infos": infos, "exemple": {m: [round(float(x), 3) for x in p[:5]] for m, p in probas.items()}})
    print(json.dumps(res["tours"][-1], ensure_ascii=False)[:3000], flush=True)
g.fermer()
Path(sys.argv[1]).write_text(json.dumps(res, indent=1, ensure_ascii=False))

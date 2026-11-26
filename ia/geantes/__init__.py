"""Chef d'orchestre des IA géantes : un processus par famille, même entrée et même sortie pour toutes.

Une famille qui ne se charge pas, qui plante ou qui répond trop tard est mise de côté pour ce tour,
sans jamais bloquer les autres ni le journal.
"""
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

from ia.geantes.familles import FAMILLES

DEPOT = Path(__file__).resolve().parents[2]


class Geantes:
    def __init__(self, familles=None, attente_chargement=900):
        self.dossier = Path(tempfile.mkdtemp(prefix="geantes_"))
        self.proc, self.files, self.pret, self.etat = {}, {}, {}, {}
        self.numero = 0
        self.occupe = set()
        for f in familles or list(FAMILLES):
            py = DEPOT / ".venvs" / f / "bin" / "python"
            if not py.exists():
                for m in FAMILLES[f]["modeles"]:
                    self.etat[m] = "non installée"
                continue
            p = subprocess.Popen([str(py), str(DEPOT / "ia" / "geantes" / "travailleur.py"), f, str(DEPOT)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None, text=True, bufsize=1)
            q = queue.Queue()
            threading.Thread(target=self._lire, args=(p, q), daemon=True).start()
            self.proc[f], self.files[f] = p, q
        fin = time.time() + attente_chargement
        for f, q in self.files.items():
            try:
                r = json.loads(q.get(timeout=max(1, fin - time.time())))
            except Exception:
                r = {"pret": [], "erreurs": {m: "chargement trop long" for m in FAMILLES[f]["modeles"]}}
            self.pret[f] = r.get("pret", [])
            for m in r.get("pret", []):
                self.etat[m] = "prête"
            for m, e in r.get("erreurs", {}).items():
                self.etat[m] = e
            print(f"famille {f} : prêtes {self.pret[f]}, erreurs {r.get('erreurs')}", flush=True)

    @staticmethod
    def _lire(p, q):
        for ligne in p.stdout:
            q.put(ligne)

    def modeles(self):
        return [m for f in self.pret for m in self.pret[f]]

    def prevoir(self, prix, ohlcv, H=1, delai=40):
        """prix (n, L), ohlcv (n, L, 5) -> ({modèle: proba de hausse pour les k premiers marchés (k <= n)}, {modèle: secondes ou erreur})."""
        self.numero += 1
        entrees = {}
        envoyees, infos_avant = {}, {}
        for f, p in self.proc.items():
            if not self.pret.get(f) or p.poll() is not None:
                continue
            if f in self.occupe:  # encore sur la demande précédente : on la laisse finir, on saute ce tour
                if self.files[f].empty():
                    for m in self.pret[f]:
                        infos_avant[m] = "encore occupée (trop lente)"
                    continue
                while not self.files[f].empty():
                    self.files[f].get_nowait()
                self.occupe.discard(f)
            k = min(len(prix), int(FAMILLES[f].get("lot_max", len(prix))))  # les plus lentes : moins de marchés
            if k not in entrees:
                entrees[k] = self.dossier / f"e{self.numero}_{k}.npz"
                np.savez(entrees[k], prix=prix[:k].astype(np.float32), ohlcv=ohlcv[:k].astype(np.float32))
            entree = entrees[k]
            sortie = self.dossier / f"s{self.numero}_{f}.npz"
            try:
                p.stdin.write(json.dumps({"entree": str(entree), "sortie": str(sortie), "H": H}) + "\n")
                p.stdin.flush()
                envoyees[f] = sortie
            except Exception:
                continue
        probas, infos = {}, dict(infos_avant)
        fin = time.time() + delai
        for f, sortie in envoyees.items():
            try:
                r = json.loads(self.files[f].get(timeout=max(0.5, fin - time.time())))
            except Exception:
                self.occupe.add(f)
                for m in self.pret[f]:
                    infos[m] = "trop lente ce tour-ci"
                continue
            infos.update(r.get("ok", {}))
            infos.update(r.get("erreurs", {}))
            try:
                d = np.load(sortie)
                probas.update({k: d[k] for k in d.files})
            except Exception:
                pass
        return probas, infos

    def fermer(self):
        for p in self.proc.values():
            try:
                p.stdin.close()
                p.terminate()
            except Exception:
                pass

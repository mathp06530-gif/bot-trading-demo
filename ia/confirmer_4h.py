"""Confirmation de la piste « horizon 4 h, vote simple, ne jouer que ses 5 % plus sûrs » sur des ANNÉES JAMAIS VUES.

Le labo n°4 a jugé les 24 derniers mois (bougies 4 h). Ici on coupe les données AVANT ce début (fin = LABO_FIN)
et on juge les 36 mois précédents (fin 2021 -> fin 2024), avec EXACTEMENT les mêmes réglages, fixés à l'avance.
Prix mélangés refaits avec 5 graines différentes pour mesurer la vraie marge du hasard.

Usage : python ia/confirmer_4h.py <dossier_prix> <EPIC> <sortie.json>
        python ia/confirmer_4h.py bilan <dossier> <sortie.md>
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("LABO_MOIS_TEST", "36")
os.environ.setdefault("LABO_MOIS_CHAUFFE", "6")
os.environ.setdefault("LABO_H", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ia.multi_labo as L  # noqa: E402

FIN = pd.Timestamp(os.getenv("LABO_FIN", "2024-11-27"))
GRAINES = (7, 11, 13, 17, 19)
GARDE = ("Vote simple", "CHEF (IA unique)", "Aiguilleur (mixture of experts)", "Champion du mois")


def resume(res):
    return {n: {"toujours": res[n]["toujours"], "top5": res[n]["courbe"]["0.05"], "top10": res[n]["courbe"]["0.1"]}
            for n in GARDE if n in res}


def tester(dossier, epic, sortie):
    from ia.predire import lire
    d = lire(Path(dossier), epic, "HOUR_4")
    d = d[d.index < FIN]
    L.PURGE = pd.Timedelta(hours=10)
    croix = L.croises(dossier, epic, "HOUR_4", d.index)
    out = {"epic": epic, "fin": str(FIN), "reel": resume(L.tout(L.preparer(d, 240, croix=croix, epic=epic))), "melanges": []}
    for g in GRAINES:
        out["melanges"].append(resume(L.tout(L.preparer(d, 240, melange_graine=g, croix=croix, epic=epic))))
    Path(sortie).write_text(json.dumps(out, ensure_ascii=False))
    print(json.dumps(out["reel"], ensure_ascii=False)[:1500])


def bilan(dossier, sortie):
    R = [json.loads(p.read_text()) for p in sorted(Path(dossier).glob("*.json"))]
    lignes = ["# Confirmation « 4 h, ne jouer que les plus sûres » sur des années jamais vues", "",
              f"Bougies 4 h, période jugée : les 36 mois avant le {R[0]['fin'][:10] if R else '?'} (le labo n°4 jugeait les 24 mois d'après).",
              "Réglages identiques, fixés à l'avance. Prix mélangés : 5 graines.", "",
              "| Méta-cerveau | Version | Réussite | Gain après spread | Marchés gagnants | Mois positifs | Prix mélangés : réussite moy. (max) | gain moy. |",
              "|---|---|---|---|---|---|---|---|"]
    for n in GARDE:
        for v in ("toujours", "top10", "top5"):
            re_ = [r["reel"][n][v] for r in R if r["reel"].get(n, {}).get(v)]
            me = [m[n][v] for r in R for m in r["melanges"] if m.get(n, {}).get(v)]
            if not re_:
                continue
            mg = [np.mean([m[n][v]["reussite"] for m in r["melanges"] if m.get(n, {}).get(v)]) for r in R]
            lignes.append(f"| {n} | {v} | {100 * np.mean([x['reussite'] for x in re_]):.1f} % ({sum(x['n'] for x in re_)}) | "
                          f"{np.mean([x['gain'] for x in re_]):+.4f} % | {sum(x['gain'] > 0 for x in re_)}/{len(re_)} | "
                          f"{sum(x['mois_positifs'] for x in re_)}/{sum(x['mois'] for x in re_)} | "
                          f"{100 * np.mean([x['reussite'] for x in me]):.1f} % ({100 * max(mg):.1f} %) | {np.mean([x['gain'] for x in me]):+.4f} % |")
    Path(sortie).write_text("\n".join(lignes) + "\n")
    print("\n".join(lignes))


if __name__ == "__main__":
    if sys.argv[1] == "bilan":
        bilan(sys.argv[2], sys.argv[3])
    else:
        tester(*sys.argv[1:4])

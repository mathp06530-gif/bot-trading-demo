"""Confirmation de la surprise du labo n°3 : « fin de séance à l'envers » sur US100 / US500 / DE40.

Règle FIXÉE à l'avance (exactement celle du labo, en sens inverse) : sur les bougies qui commencent dans les
30 dernières minutes de la séance (US 21 h 30 - 22 h, DE40 17 h - 17 h 30, heure de Paris), parier CONTRE le
rendement depuis l'ouverture (US 15 h 30, DE40 9 h). Cible : sens de la bougie suivante.
Jugé sur la période AVANT les 12 mois du labo (jamais regardée pour cette règle), puis sur les 12 mois (rappel).
Contrôle : la même règle à d'autres heures de la séance (doit donner ~50 %), et prix mélangés.

Usage : python ia/fin_seance.py <dossier_prix> <sortie.md>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ia.predire import lire  # noqa: E402

SEANCE = {"US100": (15.5, 22.0), "US500": (15.5, 22.0), "DE40": (9.0, 17.5)}


def preparer(d, minutes, graine=None):
    mid = (d.close_bid + d.close_ask) / 2
    sp = (d.close_ask - d.close_bid) / mid * 100
    if graine is not None:
        r = np.log(mid).diff().fillna(0).to_numpy()
        mid = pd.Series(mid.iloc[0] * np.exp(np.cumsum(np.random.default_rng(graine).permutation(r))), index=d.index)
    loc = d.index.tz_localize("UTC").tz_convert("Europe/Paris")
    h = np.asarray(loc.hour + loc.minute / 60, float)
    jour = pd.Index(loc.date)
    ecart = (pd.Series(d.index, index=d.index).shift(-1) - pd.Series(d.index, index=d.index)).dt.total_seconds() / 60
    mv = (mid.shift(-1) / mid - 1) * 100
    return pd.DataFrame({"lm": np.log(mid).to_numpy(), "h": h, "jour": jour, "mv": mv.to_numpy(), "sp": sp.to_numpy(),
                         "ok": ((ecart <= 2 * minutes) & mv.notna() & (mv != 0)).to_numpy()}, index=d.index)


def regle(f, o, debut, fin):
    """Parie contre le rendement depuis l'ouverture o, sur les bougies qui commencent dans [debut, fin)."""
    ouv = pd.Series(np.where(np.abs(f.h - o) < 1e-6, f.lm, np.nan), index=f.index).groupby(f.jour.to_numpy()).transform("first")
    depuis = f.lm - ouv
    actif = f.ok & (f.h >= debut) & (f.h < fin) & depuis.notna() & (depuis != 0)
    x = f[actif]
    sens = -np.sign(depuis[actif])
    g = sens * x.mv - x.sp
    return {"n": int(actif.sum()), "jours": int(x.jour.nunique()), "reussite": float((sens * x.mv > 0).mean()) if len(x) else None,
            "gain": float(g.mean()) if len(x) else None, "brut": float((sens * x.mv).mean()) if len(x) else None,
            "t": float(g.mean() / (g.std() + 1e-12) * np.sqrt(len(g))) if len(x) > 1 else None}


def principal():
    dossier, sortie = Path(sys.argv[1]), sys.argv[2]
    L = ["# Fin de séance à l'envers : test de confirmation", "",
         "Règle fixée à l'avance (celle du labo n°3, inversée). « Avant » = période jamais regardée pour cette règle.", "",
         "| Bougies | Marché | Période | Paris (jours) | Réussite | Gain brut | Gain après spread | t | Même règle 1 h plus tôt | Prix mélangés |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for unite, minutes in (("MINUTE_15", 15), ("MINUTE_5", 5)):
        for e, (o, c) in SEANCE.items():
            d = lire(dossier, e, unite)
            if d is None:
                continue
            f, fm = preparer(d, minutes), preparer(d, minutes, graine=11)
            coupe = f.index.max() - pd.DateOffset(months=12)
            for nom, m in (("avant (jamais vue)", f.index < coupe), ("12 mois du labo", f.index >= coupe)):
                r = regle(f[m], o, c - 0.5, c)
                tem = regle(f[m], o, c - 1.5, c - 1.0)
                mel = regle(fm[m], o, c - 0.5, c)
                if not r["n"]:
                    continue
                L.append(f"| {unite} | {e} | {nom} | {r['n']} ({r['jours']}) | {100 * r['reussite']:.1f} % | {r['brut']:+.4f} % | "
                         f"{r['gain']:+.4f} % | {r['t']:.2f} | {100 * tem['reussite']:.1f} % | {100 * mel['reussite']:.1f} % |")
    Path(sortie).write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    principal()

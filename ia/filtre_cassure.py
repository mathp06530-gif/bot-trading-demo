"""Le vote 4 h de l'IA comme FILTRE sur la Cassure 4 h or / argent du bot (27/11/2026, demande de Mathis).
Aucun ordre, le bot en direct n'est PAS touché.

Cassure : exactement les signaux du bot (bot/cassure.py) et son moteur de backtest (backtest/moteur.py : spread,
stop garanti + prime, frais de nuit exacts, stop qui se resserre). Résultat en R (1 R = 1 % du capital risqué).
Vote : les 14 cerveaux du labo (ia/multi_labo.py), walk-forward mensuel, rien du futur ; il est lu à la bougie
du signal de cassure (la même clôture), l'ordre part à l'ouverture suivante comme dans le bot.

Filtres testés (une cassure refusée reste refusée jusqu'au signal suivant) :
  accord          : on ne prend la cassure que si le vote va dans le même sens ;
  accord_sur      : idem, et la confiance du vote >= sa médiane passée ;
  pas_contre_fort : on refuse seulement si le vote est CONTRE avec une confiance dans ses 20 % plus hautes.
Anti-triche : filtre choisi sur la 1re moitié de la période, jugé sur la 2e ; comparé à 500 filtres AU HASARD qui
refusent la même part de cassures (le vrai filtre doit faire mieux que ~95 % d'entre eux).

Usage : python ia/filtre_cassure.py <dossier_prix> <sortie.md>
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ["LABO_H"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ia.multi_labo as L  # noqa: E402
from backtest.moteur import Conditions, executer  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402

MARCHES = ["GOLD", "SILVER"]
HASARD = int(os.getenv("FC_HASARD", "500"))


def conditions(dossier, epic, prix):
    c = Conditions(taille_min=0.0, pas_taille=1e-6, eurusd=1.08, prime_stop_garanti_pct=0.1)
    p = Path(dossier) / f"{epic}_marche.json"
    if p.exists():
        m = json.loads(p.read_text())
        r, inst = m.get("dealingRules", {}), m.get("instrument", {})
        g = r.get("minGuaranteedStopDistance", {})
        if g.get("unit") == "PERCENTAGE":
            c.stop_garanti_min_pct = float(g["value"])
        elif g.get("value"):
            c.stop_garanti_min_pct = float(g["value"]) / prix * 100
        of = inst.get("overnightFee", {})
        c.frais_nuit_achat_pct = -float(of.get("longRate", -0.02))
        c.frais_nuit_vente_pct = -float(of.get("shortRate", -0.02))
    c.marge = 0.05
    return c


def vote(dossier, epic, d):
    L.PURGE = pd.Timedelta(hours=10)
    f = L.preparer(d, 240, croix=L.croises(dossier, epic, "HOUR_4", d.index), epic=epic)
    debut = f.index.min() + pd.DateOffset(months=15)  # ~2000 bougies 4 h de passé avant la 1re prédiction
    debut = debut.normalize().replace(day=1)
    bornes = [debut] + [b for b in pd.date_range(debut, f.index.max() + pd.Timedelta(days=31), freq="MS") if b > debut]
    P = L.cerveaux(f, list(zip(bornes[:-1], bornes[1:])))
    v = P.mean(axis=1)
    return v[P[L.APPRIS].notna().all(axis=1)]


def runs(cible):
    """Débuts de chaque « période de signal » (cible qui passe à ±1) et sa fin."""
    out, i = [], 0
    while i < len(cible):
        if cible[i] != 0 and (i == 0 or cible[i - 1] != cible[i]):
            j = i
            while j + 1 < len(cible) and cible[j + 1] == cible[i]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def filtrer(sig, refus):
    s = sig.copy()
    c = s.cible.to_numpy().copy()
    for (i, j) in refus:
        c[i:j + 1] = 0
    s["cible"] = c
    s.attrs = dict(sig.attrs)
    return s


def score(tr, debut, fin):
    t = tr[(tr.entree_le >= debut) & (tr.entree_le < fin)]
    r = (t.pnl_eur / 100).to_numpy(float)  # capital 10 000, risque 1 % -> 1 R = 100 €
    cb = np.r_[0, np.cumsum(r)]
    return {"R": round(float(r.sum()), 2), "trades": int(len(r)), "reussite": round(float((r > 0).mean() * 100), 1) if len(r) else 0,
            "pire_baisse_R": round(float((cb - np.maximum.accumulate(cb)).min()), 2)}


def principal():
    from ia.predire import lire
    dossier, sortie = sys.argv[1], sys.argv[2]
    lignes = ["# Le vote 4 h de l'IA comme filtre sur la Cassure 4 h du bot (or, argent)", "",
              "Moteur du bot (spread, stop garanti, frais de nuit, stop qui se resserre). R = 1 % du capital risqué par trade. "
              "Filtre choisi sur la 1re moitié, jugé sur la 2e. « Hasard » = 500 filtres qui refusent la même part de cassures au hasard.", ""]
    total = {}
    for epic in MARCHES:
        d = lire(Path(dossier), epic, "HOUR_4")
        if d is None:
            continue
        v = vote(dossier, epic, d)
        sig = signaux_cassure(d)
        cond = conditions(dossier, epic, float(d.close_bid.iloc[-1]))
        debut, fin = v.index.min(), d.index.max() + pd.Timedelta(days=1)
        milieu = debut + (fin - debut) / 2
        q = v.reindex(d.index).to_numpy()
        conf = np.abs(q - 0.5)
        cible = sig.cible.to_numpy()
        R = [(i, j) for (i, j) in runs(cible) if d.index[i] >= debut and q[i] == q[i]]
        hist = pd.Series(conf).rolling(3000, min_periods=300).median().shift(1).to_numpy()
        q80 = pd.Series(conf).rolling(3000, min_periods=300).quantile(0.8).shift(1).to_numpy()
        avec = lambda i: (q[i] > 0.5) == (cible[i] > 0)  # noqa: E731
        filtres = {"sans filtre (bot actuel)": [],
                   "accord": [(i, j) for (i, j) in R if not avec(i)],
                   "accord_sur": [(i, j) for (i, j) in R if not (avec(i) and conf[i] >= hist[i])],
                   "pas_contre_fort": [(i, j) for (i, j) in R if (not avec(i)) and conf[i] >= q80[i]]}
        rng = np.random.default_rng(0)
        base_tr = executer(d, sig, 10_000.0, 1.0, cond).trades
        lignes += [f"## {epic} ({len(R)} cassures avec un vote, {debut.date()} -> {d.index.max().date()})", "",
                   "| Filtre | Cassures refusées | 1re moitié (choix) | 2e moitié (jugée) | Tout | Hasard (même part refusée) : R médian tout | Mieux que le hasard |",
                   "|---|---|---|---|---|---|---|"]
        for nom, refus in filtres.items():
            tr = base_tr if not refus else executer(d, filtrer(sig, refus), 10_000.0, 1.0, cond).trades
            s1, s2, st = score(tr, debut, milieu), score(tr, milieu, fin), score(tr, debut, fin)
            total.setdefault(nom, []).append((s1, s2, st))
            if refus:
                hz = []
                for _ in range(HASARD):
                    k = rng.choice(len(R), size=len(refus), replace=False)
                    hz.append(score(executer(d, filtrer(sig, [R[x] for x in k]), 10_000.0, 1.0, cond).trades, debut, fin)["R"])
                hz = np.array(hz)
                mieux = f"{100 * (hz < st['R']).mean():.0f} % des hasards"
                med = f"{np.median(hz):+.1f} R"
            else:
                mieux, med = "—", "—"
            f = lambda s: f"{s['R']:+.1f} R · {s['trades']} trades · {s['reussite']:.0f} % · pire {s['pire_baisse_R']:.1f} R"  # noqa: E731
            lignes.append(f"| {nom} | {len(refus)}/{len(R)} | {f(s1)} | {f(s2)} | {f(st)} | {med} | {mieux} |")
        lignes.append("")
    lignes += ["## Panier or + argent", "", "| Filtre | 1re moitié | 2e moitié | Tout | pire baisse (pire des 2) |", "|---|---|---|---|---|"]
    for nom, xs in total.items():
        lignes.append(f"| {nom} | {sum(x[0]['R'] for x in xs):+.1f} R | {sum(x[1]['R'] for x in xs):+.1f} R | "
                      f"{sum(x[2]['R'] for x in xs):+.1f} R | {min(x[2]['pire_baisse_R'] for x in xs):.1f} R |")
    lignes += ["", "En euros : 1 R = 1 % du capital au risque du bot (Cassure : 3 %/trade en direct -> 1 R x 3). "
               "Sur 100 €, +10 R à 1 % = +10 € ; à 3 % = +30 €."]
    Path(sortie).write_text("\n".join(lignes) + "\n")
    print("\n".join(lignes))


if __name__ == "__main__":
    principal()

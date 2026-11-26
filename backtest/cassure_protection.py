"""Cassure 4 h or + argent : faut-il protéger le gain PLUS TÔT ? (analyse de la chute du 25-26/11/2026)

Le 25/11, les 2 ventes Cassure sont montées à +0,85 R (or) et +1,0 R (argent) puis ont fini au stop
(-2,38 € et -2,94 €). La règle actuelle (garder 50 % du meilleur gain après +1,5 R) ne s'est donc pas
déclenchée. Question : un seuil plus bas (+0,5 / +0,75 / +1 R), ou un stop remonté au prix d'entrée,
aurait-il fait mieux SUR DES DONNÉES JAMAIS VUES ?

Méthode (comme l'usine à stratégies) :
  - choix sur 2017 -> 31/12/2021 (entraînement) ;
  - vérification sur 01/2022 -> 06/2024 (validation) et 07/2024 -> aujourd'hui (test), jamais vus.
Une variante n'est retenue que si elle bat la règle actuelle sur les 3 périodes, sans aggraver la pire
baisse de plus de 1 R. Nettes de frais (spread, nuit, prime du stop garanti), simulateur de serrage.py.

En plus : combien de fois l'or et l'argent sont ouverts EN MÊME TEMPS dans le même sens (risque réel
3 % + 3 % = 6 % d'un coup), et ce que donnerait 1,5 % chacun dans ce cas (risque global, jamais changé
sans l'accord de Mathis).

Usage : python backtest/cassure_protection.py <dossier>   (données de backtest/usine.py telecharger)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from backtest.usine import conditions, lire  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402

DOSSIER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("donnees_usine")
COUPES = (pd.Timestamp("2022-01-01"), pd.Timestamp("2024-07-01"))
NOMS = ("entraînement 2017-2021", "validation 2022-06/2024", "test 07/2024-auj.")

VARIANTES = {"actuelle (garde 50 % après +1,5 R)": ("garde", 1.5, 0.5), "aucune protection": None}
for g in (0.5, 0.75, 1.0, 1.25):
    VARIANTES[f"prix d'entrée après +{g:g} R"] = ("garde", g, 0.0)
    for k in (0.25, 0.5, 0.7):
        VARIANTES[f"garde {int(k * 100)} % après +{g:g} R"] = ("garde", g, k)
for g in (1.5, 2.0):
    for k in (0.6, 0.7):
        VARIANTES[f"garde {int(k * 100)} % après +{g:g} R"] = ("garde", g, k)


def jeux():
    out = []
    for e in ("GOLD", "SILVER"):
        df = lire(DOSSIER, e, "HOUR_4")
        if df is None:
            print(f"{e} : pas de données")
            continue
        sig = signaux_cassure(df, entree=20, sortie=20)
        c = sig.cible.values
        neuf = np.r_[True, c[1:] != c[:-1]]
        cond = conditions(DOSSIER, e, float(df.close_bid.iloc[-1]))
        cond.setdefault("nuit_achat", 0.02)
        cond.setdefault("nuit_vente", 0.02)
        cond.setdefault("min_pct", 0.25)
        out.append((e, df, c, neuf, sig.stop.values, cond))
    return out


def periodes(t):
    r = []
    for a, b in ((None, COUPES[0]), (COUPES[0], COUPES[1]), (COUPES[1], None)):
        x = t
        if a is not None:
            x = x[x.date >= a]
        if b is not None:
            x = x[x.date < b]
        x = x.sort_values("date")
        c = np.concatenate([[0], np.cumsum(x.R.values)])
        r.append({"R": round(float(x.R.sum()), 2), "trades": int(len(x)),
                  "reussite": round(float((x.R > 0).mean() * 100), 1) if len(x) else 0.0,
                  "pire_baisse_R": round(float((c - np.maximum.accumulate(c)).min()), 2)})
    return r


def simultanes(js):
    """Trades (actuelle) avec date de sortie approx. : part des trades où l'autre métal est ouvert dans le même sens."""
    lignes = []
    for e, df, c, ok, st, cond in js:
        t = serrage.simuler(df, c, ok, st, None, cond, regle=VARIANTES["actuelle (garde 50 % après +1,5 R)"])
        sens = pd.Series(c, index=df.index)
        for d, R in zip(t.date, t.R):
            i = df.index.get_loc(d)
            sn = int(c[i - 1])
            apres = np.nonzero(c[i:] != sn)[0]
            fin = df.index[i + apres[0]] if len(apres) else df.index[-1]
            lignes.append({"epic": e, "debut": d, "fin": fin, "sens": sn, "R": R})
    t = pd.DataFrame(lignes)
    if t.empty:
        return {}
    double = []
    for i, x in t.iterrows():
        autre = t[(t.epic != x.epic) & (t.debut < x.fin) & (t.fin > x.debut) & (t.sens == x.sens)]
        double.append(len(autre) > 0)
    t["double"] = double
    t = t.sort_values("debut")
    res = {}
    for nom, poids in (("3 % chacun (actuel)", t.R.values),
                       ("1,5 % chacun quand les 2 sont ouverts", np.where(t.double, t.R.values * 0.5, t.R.values))):
        c = np.concatenate([[0], np.cumsum(poids)])
        apres = t.debut >= COUPES[0]
        c2 = np.concatenate([[0], np.cumsum(poids[apres.values])])
        res[nom] = {"R_total": round(float(poids.sum()), 1), "pire_baisse_R": round(float((c - np.maximum.accumulate(c)).min()), 1),
                    "R_jamais_vu_2022+": round(float(poids[apres.values].sum()), 1),
                    "pire_baisse_jamais_vu": round(float((c2 - np.maximum.accumulate(c2)).min()), 1)}
    res["part_trades_en_double"] = round(float(t.double.mean() * 100), 1)
    res["R_moyen_en_double"] = round(float(t.R[t.double].mean()), 2) if t.double.any() else None
    res["R_moyen_seul"] = round(float(t.R[~t.double].mean()), 2) if (~t.double).any() else None
    return res


def principal():
    js = jeux()
    print("Données :", {e: f"{df.index[0]:%d/%m/%Y} -> {df.index[-1]:%d/%m/%Y}" for e, df, *_ in js})
    res = {}
    for nom, regle in VARIANTES.items():
        tous = [serrage.simuler(df, c, ok, st, None, cond, regle=regle) for e, df, c, ok, st, cond in js]
        res[nom] = periodes(pd.concat(tous, ignore_index=True))
    base = res["actuelle (garde 50 % après +1,5 R)"]
    print(f"\n{'variante':38s}" + "".join(f"{n:>26s}" for n in NOMS))
    retenues = []
    for nom, p in sorted(res.items(), key=lambda kv: -kv[1][0]["R"]):
        ok = all(p[i]["R"] > base[i]["R"] and p[i]["pire_baisse_R"] >= base[i]["pire_baisse_R"] - 1 for i in range(3)) \
            and not nom.startswith("actuelle")
        if ok:
            retenues.append(nom)
        print(f"{nom:38s}" + "".join(f"{x['R']:9.1f} R {x['trades']:4d} tr {x['pire_baisse_R']:6.1f}" for x in p)
              + ("  <- MIEUX PARTOUT" if ok else ""))
    meilleure_entr = max((n for n in res if not n.startswith("actuelle")), key=lambda n: res[n][0]["R"])
    print(f"\nMeilleure sur l'entraînement seulement : {meilleure_entr} -> jamais vu : "
          f"{res[meilleure_entr][1]['R']} R / {res[meilleure_entr][2]['R']} R "
          f"(actuelle : {base[1]['R']} R / {base[2]['R']} R)")
    print("Retenues (mieux sur les 3 périodes) :", retenues or "aucune")
    s = simultanes(js)
    print("\nOr et argent ouverts en même temps :", json.dumps(s, ensure_ascii=False, indent=1))
    Path("backtest/resultats_cassure_protection.json").write_text(json.dumps(
        {"periodes": NOMS, "resultats": res, "retenues": retenues, "meilleure_entrainement": meilleure_entr,
         "simultanes": s}, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

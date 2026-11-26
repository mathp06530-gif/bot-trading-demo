"""Diversifier à budget égal (26/11/2026, demande de Mathis : « trader le dollar ou autres en gardant mon budget »).

On rejoue les DEUX stratégies déjà validées, avec leurs réglages ACTUELS (aucun réglage choisi ici, donc pas de
surapprentissage) sur d'autres marchés : grandes paires de devises, indice dollar, indices boursiers, autres
matières premières.
  - Cassure 4 h : canal 20 bougies, stop garanti à l'autre bord, garde 50 % du gain après +1,5 R, sans ré-entrée ;
  - Supertrend 10/3 4 h (comme sur l'ETH).
Frais réels (spread, frais de nuit, prime du stop garanti), puis frais x 1,5. Périodes : 2017-2021 / 01/2022-06/2024 /
07/2024-aujourd'hui. Un marché « tient » s'il gagne sur les 3 périodes et avec frais x 1,5 sur les années récentes.
Corrélation : R mensuels de chaque marché comparés à ceux de la Cassure or+argent (le pari actuel) : on ne veut pas
refaire un double pari. Enfin, portefeuille à RISQUE TOTAL ÉGAL : le même budget de risque réparti sur plus de
marchés, comparé à or+argent seuls.

Usage : python backtest/diversifier.py telecharger <dossier>  puis  python backtest/diversifier.py <dossier>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from backtest.audit_chiffres import cond_de, connecter  # noqa: E402
from backtest.reseaux import supertrend  # noqa: E402
from backtest.usine import lire  # noqa: E402
from backtest.web_large import resume, stresser  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402

serrage.NUITS_EXACTES = True
MARCHES = ("GOLD,SILVER,EURUSD,USDJPY,GBPUSD,AUDUSD,USDCAD,USDCHF,NZDUSD,EURJPY,GBPJPY,EURGBP,DXY,"
           "US500,US100,US30,RTY,DE40,UK100,FR40,EU50,J225,HK50,AU200,"
           "OIL_CRUDE,OIL_BRENT,COPPER,PLATINUM,PALLADIUM,NATURALGAS").split(",")


def telecharger(dossier: Path):
    from backtest import telecharger as t
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    api = connecter()
    for n, e in enumerate(MARCHES):
        if (dossier / f"{e}_HOUR_4.csv").exists():
            continue
        if n and n % 5 == 0:
            try:
                api.deconnexion()
            except Exception:
                pass
            api = connecter()
        try:
            (dossier / f"{e}_marche.json").write_text(json.dumps(api.marche(e), ensure_ascii=False))
            t.telecharger(api, e, "HOUR_4", 240, 3650)
        except Exception as x:
            print(f"{e} : échec ({str(x)[:120]})")
    api.deconnexion()


def cassure(df, cond):
    sig = signaux_cassure(df, entree=20, sortie=20)
    c = sig.cible.values
    ok = np.r_[True, c[1:] != c[:-1]]
    return serrage.simuler(df, c, ok, sig.stop.values, None, cond, regle=("garde", 1.5, 0.5))


def st(df, cond):
    v, ok, ds, _ = supertrend(df)
    return serrage.simuler(df, v, ok, ds, None, cond)


def mensuel(t):
    return t.set_index("date").R.resample("ME").sum() if len(t) else pd.Series(dtype=float)


def sharpe_mensuel(m):
    return round(float(m.mean() / m.std() * np.sqrt(12)), 2) if len(m) > 3 and m.std() > 0 else 0.0


def principal(dossier: Path):
    donnees = {e: lire(dossier, e, "HOUR_4") for e in MARCHES}
    donnees = {e: d for e, d in donnees.items() if d is not None and len(d) > 3000}
    res, mens = {"donnees": {e: f"{d.index[0]:%m/%Y}-{d.index[-1]:%m/%Y}" for e, d in donnees.items()}}, {}
    lignes = []
    for e, df in donnees.items():
        c = cond_de(dossier, e, df)
        ds, cs = stresser(df, c)
        for nom, f in (("Cassure 4 h", cassure), ("Supertrend 4 h", st)):
            t = f(df, c)
            s = resume(t)
            s2 = resume(f(ds, cs))
            tient = s["entrainement"] > 0 and s["validation"] > 0 and s["test"] > 0 and s2["validation"] + s2["test"] > 0
            mens[(nom, e)] = mensuel(t)
            lignes.append({"strategie": nom, "marche": e, **s, "stress_jamais_vu": round(s2["validation"] + s2["test"], 1),
                           "tient": tient, "sharpe_mensuel": sharpe_mensuel(mens[(nom, e)])})
        print(f"{e} : fait", flush=True)
    ref = (mens[("Cassure 4 h", "GOLD")].add(mens[("Cassure 4 h", "SILVER")], fill_value=0)) / 2
    ix = pd.date_range("2017-06-30", pd.Timestamp.now().normalize(), freq="ME")
    ref = ref.reindex(ix, fill_value=0)
    for x in lignes:
        m = mens[(x["strategie"], x["marche"])].reindex(ix, fill_value=0)
        x["correlation_avec_cassure_or_argent"] = round(float(m.corr(ref)), 2)
    res["marches"] = lignes
    # portefeuille à risque total égal : poids 1/N (même budget que or+argent à 50/50)
    elus = [x for x in lignes if x["tient"] and x["marche"] not in ("GOLD", "SILVER")
            and x["correlation_avec_cassure_or_argent"] < 0.5]
    paniers = {"or+argent seuls (actuel)": [("Cassure 4 h", "GOLD"), ("Cassure 4 h", "SILVER")],
               "or+argent + marchés qui tiennent": [("Cassure 4 h", "GOLD"), ("Cassure 4 h", "SILVER")]
               + [(x["strategie"], x["marche"]) for x in elus]}
    port = {}
    for nom, p in paniers.items():
        m = sum(mens[k].reindex(ix, fill_value=0) for k in p) / len(p)  # même risque total, réparti
        c = m.cumsum()
        port[nom] = {"marches": [f"{a} {b}" for a, b in p], "R_total_par_unite_de_risque": round(float(m.sum()), 1),
                     "R_2022_auj": round(float(m[m.index >= "2022-01-01"].sum()), 1),
                     "sharpe_mensuel": sharpe_mensuel(m), "sharpe_2022_auj": sharpe_mensuel(m[m.index >= "2022-01-01"]),
                     "pire_baisse": round(float((c - c.cummax()).min()), 2),
                     "mois_gagnants_pct": round(float((m > 0).mean() * 100), 0)}
    res["portefeuilles_risque_egal"] = port
    Path(__file__).resolve().parent.joinpath("resultats_diversifier.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False, default=str))
    for x in sorted(lignes, key=lambda x: -(x["validation"] + x["test"])):
        print(f"{'TIENT' if x['tient'] else '     '} {x['strategie']:15s} {x['marche']:10s} {x['entrainement']:7.1f} "
              f"{x['validation']:7.1f} {x['test']:7.1f} stress={x['stress_jamais_vu']:6.1f} corr={x['correlation_avec_cassure_or_argent']:5.2f} {x['trades']}")
    print(json.dumps(port, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "telecharger":
        telecharger(Path(sys.argv[2]))
    else:
        principal(Path(sys.argv[1]))

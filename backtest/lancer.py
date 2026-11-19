"""Lance tous les backtests : python backtest/lancer.py

1. Optimise chaque stratégie sur la 1re moitié de l'historique (« entraînement »).
2. Vérifie les meilleurs réglages sur la 2e moitié, jamais vue (« test »). C'est ce
   chiffre-là qui compte : une stratégie qui ne marche que sur l'entraînement est truquée
   par hasard.
3. Simule des milliers d'ordres de trades différents (Monte-Carlo) pour estimer
   les chances d'atteindre un objectif et le risque de tout perdre.
"""
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from moteur import Conditions, executer  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

DOSSIER = Path(__file__).resolve().parent / "donnees"

GRILLES = {
    "ema_croisement": {"rapide": [9], "lente": [21], "stop_pct": [3.0]},
    "tendance": {"rapide": [20, 50], "lente": [100, 200], "adx_min": [20, 25],
                 "stop_atr": [2.0, 3.0], "suivi_atr": [3.0, 5.0], "ventes": [True, False]},
    "donchian": {"entree": [20, 40, 55], "sortie": [10, 20], "stop_atr": [2.0, 3.0],
                 "filtre_ema": [0, 200], "ventes": [True, False]},
    "rsi_repli": {"n_rsi": [2, 3], "bas": [5, 10], "haut": [90, 95], "tendance": [100, 200],
                  "sortie_ema": [5, 10], "stop_atr": [2.0, 3.0], "ventes": [True, False]},
}

# Stratégies « minute par minute » (scalping) : grilles plus petites, le calcul est long
GRILLES_MINUTE = {
    "ema_croisement": {"rapide": [5, 9, 20], "lente": [21, 50], "stop_pct": [0.5, 1.0]},
    "tendance": {"rapide": [20, 50], "lente": [200], "adx_min": [25], "stop_atr": [3.0, 6.0],
                 "suivi_atr": [6.0, 10.0], "ventes": [True]},
    "donchian": {"entree": [30, 60, 120], "sortie": [15, 30], "stop_atr": [3.0, 6.0],
                 "filtre_ema": [200], "ventes": [True]},
    "rsi_repli": {"n_rsi": [2], "bas": [5, 10], "haut": [90, 95], "tendance": [200],
                  "sortie_ema": [5], "stop_atr": [3.0, 6.0], "ventes": [True]},
}


def charger(unite):
    df = pd.read_csv(DOSSIER / f"BTCUSD_{unite}.csv", parse_dates=["date"]).set_index("date")
    df.index = pd.to_datetime(df.index, utc=True)
    return df[~df.index.duplicated()].sort_index().dropna()


def charger_marche(epic, unite):
    df = pd.read_csv(DOSSIER / f"{epic}_{unite}.csv", parse_dates=["date"]).set_index("date")
    df.index = pd.to_datetime(df.index, utc=True)
    return df[~df.index.duplicated()].sort_index().dropna()


def conditions_marche(epic, dernier_prix):
    """Conditions réelles Capital.com d'un marché (taille mini, stop garanti, frais de nuit, marge, devise)."""
    c = Conditions()
    m = json.loads((DOSSIER / f"{epic}_marche.json").read_text())
    r, inst = m.get("dealingRules", {}), m.get("instrument", {})
    c.taille_min = float(r.get("minDealSize", {}).get("value", 1))
    c.pas_taille = float(r.get("minSizeIncrement", {}).get("value", c.taille_min))
    g = r.get("minGuaranteedStopDistance", {})
    if g.get("unit") == "PERCENTAGE":
        c.stop_garanti_min_pct = float(g["value"])
    elif g.get("value"):
        c.stop_garanti_min_pct = float(g["value"]) / dernier_prix * 100
    of = inst.get("overnightFee", {})
    c.frais_nuit_achat_pct = -float(of.get("longRate", -0.02))
    c.frais_nuit_vente_pct = -float(of.get("shortRate", -0.02))
    if inst.get("marginFactorUnit") == "PERCENTAGE" and inst.get("marginFactor"):
        c.marge = float(inst["marginFactor"]) / 100
    c.prime_stop_garanti_pct = 0.1
    devise = inst.get("currency", "USD")
    c.eurusd = {"USD": 1.08, "EUR": 1.0, "JPY": 1.08 * dernier_prix, "GBP": 0.85}.get(devise, 1.08)
    if epic == "USDJPY":
        c.eurusd = 1.08 * dernier_prix
    return c


def regrouper(df, regle):
    agg = {}
    for c in df.columns:
        agg[c] = "first" if c.startswith("open") else "max" if c.startswith("high") else \
            "min" if c.startswith("low") else "last" if c.startswith("close") else "sum"
    return df.resample(regle, label="left", closed="left").agg(agg).dropna()


def conditions_capital():
    c = Conditions()
    try:
        m = json.loads((DOSSIER / "BTCUSD_marche.json").read_text())
        r = m.get("dealingRules", {})
        c.taille_min = float(r.get("minDealSize", {}).get("value", c.taille_min))
        c.pas_taille = float(r.get("minSizeIncrement", {}).get("value", c.pas_taille))
        g = r.get("minGuaranteedStopDistance", {})
        if g.get("unit") == "PERCENTAGE":
            c.stop_garanti_min_pct = float(g["value"])
        inst = m.get("instrument", {})
        of = inst.get("overnightFee", {})
        if of:
            c.frais_nuit_achat_pct = -float(of.get("longRate", -c.frais_nuit_achat_pct))
            c.frais_nuit_vente_pct = -float(of.get("shortRate", -c.frais_nuit_vente_pct))
        if inst.get("marginFactor") and inst.get("marginFactorUnit") == "PERCENTAGE":
            c.marge = float(inst["marginFactor"]) / 100
        # prime du stop garanti : non fournie par l'API, on suppose 0,1 % (prudent)
        c.prime_stop_garanti_pct = float(inst.get("guaranteedStopPremium") or 0.1)
    except FileNotFoundError:
        pass
    return c


def combinaisons(grille):
    cles = list(grille)
    for v in itertools.product(*(grille[k] for k in cles)):
        yield dict(zip(cles, v))


def score(st):
    # rendement ajusté du risque, en pénalisant les stratégies avec trop peu de trades
    if st["trades"] < 15:
        return -1e9
    return st["gain_pct"] / max(abs(st["drawdown_max_pct"]), 5)


def monte_carlo(trades_pct, capital, objectif_eur, nb_trades_3_mois, n=5000, graine=1):
    """Tire au hasard des séquences de trades (en % du capital) et regarde
    combien atteignent l'objectif en 3 mois et combien tombent à presque zéro."""
    rng = np.random.default_rng(graine)
    if len(trades_pct) == 0 or nb_trades_3_mois <= 0:
        return {"objectif_atteint_pct": 0.0, "ruine_pct": 0.0, "median_eur": capital}
    tirages = rng.choice(trades_pct, size=(n, nb_trades_3_mois))
    courbes = capital * np.cumprod(1 + tirages / 100, axis=1)
    courbes = np.maximum(courbes, 0)
    final = courbes[:, -1]
    ruine = (courbes.min(axis=1) <= capital * 0.1).mean() * 100
    return {"objectif_atteint_pct": round(float((final >= capital + objectif_eur).mean() * 100), 1),
            "ruine_pct": round(float(ruine), 1),
            "median_eur": round(float(np.median(final)), 2),
            "pire_5pct_eur": round(float(np.percentile(final, 5)), 2),
            "meilleur_5pct_eur": round(float(np.percentile(final, 95)), 2)}


def principal():
    cond = conditions_capital()
    print("Conditions Capital.com :", cond)
    resultats = {"conditions": cond.__dict__, "strategies": {}}
    donnees = {"15min": charger("MINUTE_15"), "1h": charger("HOUR")}
    donnees["4h"] = regrouper(donnees["1h"], "4h")
    if (DOSSIER / "BTCUSD_MINUTE.csv").exists():
        donnees["1min"] = charger("MINUTE")
    for k, d in donnees.items():
        print(k, len(d), d.index[0], "->", d.index[-1])

    capital, risque = 20000.0, 1.0
    for nom, fn in STRATEGIES.items():
        unites = ["15min"] if nom == "ema_croisement" else ["1h", "4h"]
        if "1min" in donnees:
            unites = ["1min"] + unites
        for u in unites:
            df = donnees[u]
            coupe = df.index[len(df) // 2]
            ent, tst = df[df.index < coupe], df[df.index >= coupe]
            meilleurs = []
            grille = GRILLES_MINUTE[nom] if u == "1min" else GRILLES[nom]
            for p in combinaisons(grille):
                st = executer(ent, fn(ent, **p), capital, risque, cond).stats()
                meilleurs.append((score(st), p, st))
            meilleurs.sort(key=lambda x: -x[0])
            sc, p, st_ent = meilleurs[0]
            # on recalcule les indicateurs sur tout l'historique pour ne pas perdre le « chauffage »
            sig = fn(df, **p)
            res_tst = executer(tst, sig.loc[tst.index].assign(), capital, risque, cond)
            res_tst.trades.attrs = {}
            st_tst = res_tst.stats()
            res_tout = executer(df, sig, capital, risque, cond)
            cle = f"{nom}_{u}"
            resultats["strategies"][cle] = {"reglages": p, "entrainement": st_ent, "test": st_tst,
                                            "tout": res_tout.stats(),
                                            "trades_pct_test": list(np.round(res_tst.trades.pnl_eur / capital * 100 / risque, 4))}
            print(f"\n=== {cle} {p}\n  entraînement : {st_ent}\n  TEST         : {st_tst}")
    (DOSSIER.parent / "resultats.json").write_text(json.dumps(resultats, indent=1, default=str, ensure_ascii=False))


if __name__ == "__main__":
    principal()

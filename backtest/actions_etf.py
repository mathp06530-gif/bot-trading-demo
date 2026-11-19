"""Backtest des « sous-bots » actions et ETF : python backtest/actions_etf.py

Pour CHAQUE marché, plusieurs stratégies candidates sont testées sur la 1re année
(« entraînement »). On garde, par marché, celle qui a le mieux marché sur l'entraînement,
puis on la juge sur la 2e année jamais vue (« examen »). Aucun choix n'utilise l'examen.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lancer import charger_marche, conditions_marche, regrouper  # noqa: E402
from moteur import executer  # noqa: E402

from bot.strategie import signaux_note, signaux_tendance  # noqa: E402

DOSSIER = Path(__file__).resolve().parent / "donnees"
ACTIONS = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "META", "AMD", "GOOGL", "NFLX", "JPM"]
ETF = ["SPY", "QQQ", "IWM", "GLD", "TLT", "EEM", "XLK", "XLE", "VTI", "ARKK", "SLV", "XLF"]
CAPITAL, RISQUE = 20000.0, 1.0

CANDIDATES = {
    "tendance_4h": ("4h", lambda d: signaux_tendance(d)),
    "tendance_4h_note": ("4h", lambda d: signaux_tendance(d, note_min=0.1)),
    "note_4h": ("4h", lambda d: signaux_note(d)),
    "note_1h": ("1h", lambda d: signaux_note(d)),
    "tendance_1j": ("1D", lambda d: signaux_tendance(d)),
    "note_1j": ("1D", lambda d: signaux_note(d)),
    "tendance_4h_achat": ("4h", lambda d: signaux_tendance(d, ventes=False)),
    "note_4h_achat": ("4h", lambda d: signaux_note(d, ventes=False)),
    "note_1j_achat": ("1D", lambda d: signaux_note(d, ventes=False)),
    "tendance_1j_achat": ("1D", lambda d: signaux_tendance(d, ventes=False)),
}


def tester(epic):
    h = charger_marche(epic, "HOUR")
    coupe = h.index[len(h) // 2]
    lignes = []
    for nom, (unite, fn) in CANDIDATES.items():
        d = h if unite == "1h" else regrouper(h, unite)
        cond = conditions_marche(epic, float(d.close_bid.iloc[-1]))
        sig = fn(d)
        ent, ex = d.index < coupe, d.index >= coupe
        a = executer(d[ent], sig[ent], CAPITAL, RISQUE, cond).stats()
        b = executer(d[ex], sig[ex], CAPITAL, RISQUE, cond)
        bs = b.stats()
        lignes.append({"marche": epic, "strategie": nom, "entrainement_pct": a["gain_pct"], "trades_ent": a["trades"],
                       "examen_pct": bs["gain_pct"], "examen_dd": bs["drawdown_max_pct"], "trades_examen": bs["trades"],
                       "reussite_examen": bs["reussite_pct"], "courbe": b.courbe.resample("D").last().ffill() - CAPITAL})
    return lignes


def principal():
    tout = []
    for epic in ACTIONS + ETF:
        if (DOSSIER / f"{epic}_HOUR.csv").exists():
            tout += tester(epic)
    tab = pd.DataFrame(tout)
    # choix par marché sur l'ENTRAÎNEMENT seulement (au moins 5 trades)
    eligibles = tab[(tab.trades_ent >= 5)]
    choix = eligibles.sort_values("entrainement_pct", ascending=False).groupby("marche").head(1)
    choix = choix[choix.entrainement_pct > 0]
    aff = ["marche", "strategie", "entrainement_pct", "trades_ent", "examen_pct", "examen_dd", "trades_examen", "reussite_examen"]
    print("Toutes les combinaisons (moyenne par stratégie) :")
    print(tab.groupby("strategie")[["entrainement_pct", "examen_pct", "trades_examen"]].mean().round(2))
    print("\nChoix par marché (sur l'entraînement), puis résultat à l'examen :")
    print(choix[aff].sort_values("examen_pct", ascending=False).to_string(index=False))
    pf = pd.DataFrame({f"{r.marche}": r.courbe for r in choix.itertuples()}).ffill().fillna(0)
    total = CAPITAL + pf.sum(axis=1)
    pic = total.cummax()
    print(f"\nPortefeuille des {len(choix)} sous-bots retenus, à l'examen : {total.iloc[-1] - CAPITAL:+.0f} € "
          f"({(total.iloc[-1] / CAPITAL - 1) * 100:+.1f} %), pire baisse {((total - pic) / pic).min() * 100:.1f} %, "
          f"{int(choix.trades_examen.sum())} trades")
    (DOSSIER.parent / "resultats_actions_etf.json").write_text(json.dumps(
        {"toutes": tab.drop(columns="courbe").to_dict("records"), "choix": choix.drop(columns="courbe").to_dict("records")},
        indent=1, ensure_ascii=False, default=str))
    return tab, choix


if __name__ == "__main__":
    principal()

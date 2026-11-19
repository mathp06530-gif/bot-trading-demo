"""Stratégie Tendance 4 h appliquée telle quelle à plusieurs marchés.

Les réglages ont été choisis UNIQUEMENT sur la 1re année du Bitcoin. Pour tous les autres
marchés, c'est donc un examen 100 % sur données jamais vues : aucun réglage n'est adapté.

python backtest/multi_marches.py
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

from bot.strategie import signaux_tendance  # noqa: E402

DOSSIER = Path(__file__).resolve().parent / "donnees"
CAPITAL, RISQUE = 20000.0, 1.0


def principal():
    lignes, courbes, tous_trades = [], {}, []
    for f in sorted(DOSSIER.glob("*_HOUR.csv")):
        epic = f.name.replace("_HOUR.csv", "")
        df = regrouper(charger_marche(epic, "HOUR"), "4h")
        if len(df) < 400:
            continue
        cond = conditions_marche(epic, float(df.close_bid.iloc[-1]))
        sig = signaux_tendance(df)
        debut = df.index[0] + pd.Timedelta(days=40)  # temps de calcul de l'EMA 200
        m = df.index >= debut
        r = executer(df[m], sig[m], CAPITAL, RISQUE, cond)
        st = r.stats()
        coupe = df.index[len(df) // 2]
        st2 = executer(df[df.index >= coupe], sig[df.index >= coupe], CAPITAL, RISQUE, cond).stats()
        lignes.append({"marche": epic, **{k: st[k] for k in ("gain_pct", "drawdown_max_pct", "trades", "reussite_pct",
                                                              "profit_factor", "mois_positifs")},
                       "gain_2e_annee_pct": st2["gain_pct"], "spread_pct": round(float(((df.close_ask - df.close_bid) / df.close_bid).median() * 100), 3)})
        courbes[epic] = r.courbe.resample("D").last().ffill() - CAPITAL
        t = r.trades.copy()
        t["marche"] = epic
        tous_trades.append(t)
    tab = pd.DataFrame(lignes).sort_values("gain_pct", ascending=False)
    print(tab.to_string(index=False))
    pf = pd.DataFrame(courbes).ffill().fillna(0)
    total = CAPITAL + pf.sum(axis=1)
    pic = total.cummax()
    trades = pd.concat(tous_trades)
    jours = (total.index[-1] - total.index[0]).days
    print(f"\nPortefeuille de {len(courbes)} marchés, 1 % risqué par trade, capital {CAPITAL:.0f} € :")
    print(f"  gain {total.iloc[-1] - CAPITAL:+.0f} € ({(total.iloc[-1] / CAPITAL - 1) * 100:+.1f} %) en {jours} jours, "
          f"pire baisse {((total - pic) / pic).min() * 100:.1f} %, {len(trades)} trades ({len(trades) / jours * 30:.1f} par mois)")
    fen = []
    for d0 in pd.date_range(total.index[0], total.index[-1] - pd.Timedelta(days=91), freq="7D"):
        fen.append(total.asof(d0 + pd.Timedelta(days=91)) - total.asof(d0))
    fen = np.array(fen)
    print(f"  sur 3 mois ({len(fen)} périodes) : médiane {np.median(fen):+.0f} €, pire {fen.min():+.0f} €, "
          f"meilleure {fen.max():+.0f} €, périodes perdantes {np.mean(fen < 0) * 100:.0f} %")
    (DOSSIER.parent / "resultats_multi.json").write_text(json.dumps(
        {"marches": lignes, "portefeuille": {"gain_eur": round(float(total.iloc[-1] - CAPITAL), 2),
                                             "trades_par_mois": round(len(trades) / jours * 30, 1)}},
        indent=1, ensure_ascii=False, default=str))
    return tab, total, trades


if __name__ == "__main__":
    principal()

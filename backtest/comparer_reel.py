"""Backtest contre réalité (26/11/2026) : on rejoue les backtests de la Rapide 5 min (or) et de la Cassure 4 h
(or, argent) sur EXACTEMENT la période où le bot a tourné en démo, avec les vraies bougies Capital.com, puis on
compare trade par trade avec les ordres réels de docs/data.json (heure d'entrée, sens, prix, sortie, résultat en R).

Si le backtest « voit » des trades gagnants que le bot n'a pas eus, ou sort à des prix meilleurs que la réalité,
c'est qu'il triche ou qu'il est trop optimiste.

Usage (GitHub Actions, secrets Capital.com) : python backtest/comparer_reel.py [dossier]
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import rapide_defauts, serrage, telecharger  # noqa: E402
from bot.capital import CapitalDemo  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402

DOSSIER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("donnees_reel")
DEBUT = pd.Timestamp("2026-11-20 16:00")
RACINE = Path(__file__).resolve().parent.parent


def charger():
    DOSSIER.mkdir(parents=True, exist_ok=True)
    telecharger.DOSSIER = DOSSIER
    api = CapitalDemo(*(os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD")))
    api.connexion()
    for epic in ("GOLD", "SILVER"):
        (DOSSIER / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
        for unite, minutes, jours in (("MINUTE_5", 5, 20), ("HOUR", 60, 60), ("HOUR_4", 240, 400)):
            telecharger.telecharger(api, epic, unite, minutes, jours)
    api.deconnexion()


def lire(epic, unite):
    df = pd.read_csv(DOSSIER / f"{epic}_{unite}.csv", parse_dates=["date"]).set_index("date").sort_index()
    df.index = df.index.tz_localize(None) if df.index.tz is not None else df.index
    df = df[~df.index.duplicated()].dropna(subset=["close_bid", "close_ask"])
    return df


def reels(strategie, epic):
    d = json.loads((RACINE / "docs" / "data.json").read_text())
    out = []
    for o in d.get("ordres", []):
        if o.get("strategie") != strategie or o.get("marche") != epic or o.get("statut") != "ferme":
            continue
        s = 1 if o["sens"] == "BUY" else -1
        dist = abs(o["prix_entree"] - o["stop"])
        out.append({"entree_le": o["ouvert_le"][:16], "sens": o["sens"], "prix_entree": o["prix_entree"],
                    "sortie_le": (o.get("ferme_le") or "")[:16], "prix_sortie": o.get("prix_sortie"),
                    "R_prix": round((o["prix_sortie"] - o["prix_entree"]) * s / dist, 2) if o.get("prix_sortie") else None,
                    "eur": o.get("resultat"), "motif": o.get("motif_sortie")})
    return out


def rapide(cond_kw):
    d5, d1, d4 = lire("GOLD", "MINUTE_5"), lire("GOLD", "HOUR"), lire("GOLD", "HOUR_4")
    voulu, bb, force = rapide_defauts.preparer(d5, d1, d4)
    ok = (bb > 1) & (force > 20) & (voulu != 0)
    serrage.DOSSIER = DOSSIER
    cond = serrage.conditions("GOLD", float(d5.close_bid.iloc[-1]))
    cond["min_pct"] = min(cond["min_pct"], 1.0)
    t = rapide_defauts.simuler(d5, voulu, ok, cond, **cond_kw)
    t = t[t.date >= DEBUT]
    sens = {d: int(voulu[d5.index.get_loc(d) - 1]) for d in t.date}
    prix = {d: float(d5.open_ask.loc[d] if sens[d] > 0 else d5.open_bid.loc[d]) for d in t.date}
    return [{"entree_le": f"{d:%Y-%m-%dT%H:%M}", "sens": "BUY" if sens[d] > 0 else "SELL", "prix_entree": round(prix[d], 2),
             "R": round(float(r), 2), "raison": x} for d, r, x in zip(t.date, t.R, t.raison)]


def cassure(epic):
    serrage.DOSSIER = DOSSIER
    d4 = lire(epic, "HOUR_4")
    sig = signaux_cassure(d4, entree=20, sortie=20)
    c = sig.cible.values
    cond = serrage.conditions(epic, float(d4.close_bid.iloc[-1]))
    t = serrage.simuler(d4, c, np.r_[True, c[1:] != c[:-1]], sig.stop.values, None, cond, regle=("garde", 1.5, 0.5))
    t = t[t.date >= DEBUT - pd.Timedelta(days=10)]
    return [{"entree_le": f"{d:%Y-%m-%dT%H:%M}", "sens": "BUY" if c[d4.index.get_loc(d) - 1] > 0 else "SELL",
             "prix_entree": round(float(d4.open_bid.loc[d] if c[d4.index.get_loc(d) - 1] < 0 else d4.open_ask.loc[d]), 3),
             "R": round(float(r), 2), "raison": x} for d, r, x in zip(t.date, t.R, t.raison)]


def principal():
    if not (DOSSIER / "GOLD_MINUTE_5.csv").exists():
        charger()
    res = {"rapide_reel": reels("rapide", "GOLD"),
           "rapide_backtest_reglages_actuels": rapide(dict(suivi_pct=1.0, empiler=2, sortie_k=3)),
           "rapide_backtest_anciens_reglages": rapide(dict(suivi_pct=2.0, empiler=3, sortie_k=1)),
           "cassure_reel": reels("cassure_4h", "GOLD") + reels("cassure_4h", "SILVER"),
           "cassure_backtest_or": cassure("GOLD"), "cassure_backtest_argent": cassure("SILVER")}
    for k, v in res.items():
        print(f"\n=== {k} ({len(v)} trades)")
        for x in v:
            print("  ", json.dumps(x, ensure_ascii=False))
        rs = [x.get("R", x.get("R_prix")) for x in v if x.get("R", x.get("R_prix")) is not None]
        print(f"   total {sum(rs):+.2f} R sur {len(rs)} trades")
    (RACINE / "backtest" / "resultats_comparer_reel.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    principal()

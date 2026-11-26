"""Audit du 26/11/2026 : on REFAIT les chiffres des stratégies actives avec les corrections de l'audit.

Corrections testées (même données Capital.com démo que les backtests d'origine) :
  1. frais de nuit : l'ancien calcul ne les comptait jamais (pas de bougie à 22 h 00 en 4 h, ni en 5 min sur l'or) ;
  2. Cassure : le bot RENTRE aussi sur une nouvelle cassure pendant une tendance déjà en cours (code du bot,
     bot/cassure.py) alors que le backtest ne prenait que le 1er signal. Les 2 trades Cassure réels du 25/11
     sont de ce type : le backtest ne les avait jamais testés.
Périodes : entraînement 2017-2021, validation 01/2022-06/2024, test 07/2024-aujourd'hui (comme l'usine).

Usage : python backtest/audit_chiffres.py telecharger <dossier>  puis  python backtest/audit_chiffres.py <dossier>
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import rapide_defauts, serrage  # noqa: E402
from backtest.reseaux import supertrend  # noqa: E402
from backtest.smart_money import tenir  # noqa: E402
from backtest.usine import conditions, lire  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402
from bot.elan import signaux_elan  # noqa: E402

COUPES = (pd.Timestamp("2022-01-01"), pd.Timestamp("2024-07-01"))


def connecter():
    from bot.capital import CapitalDemo
    api = CapitalDemo(*(os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD")))
    for essai in range(12):
        try:
            api.connexion()
            return api
        except Exception as e:
            print(f"connexion {essai + 1} : {e}")
            time.sleep(25 + 5 * essai)
    raise SystemExit("connexion impossible")


def telecharger(dossier: Path):
    from backtest import telecharger as t
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    api = connecter()
    for epic in ("GOLD", "SILVER", "ETHUSD"):
        (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
        t.telecharger(api, epic, "HOUR_4", 240, 3650)
    api.deconnexion()
    api = connecter()
    for unite, minutes, jours in (("MINUTE_5", 5, 200), ("HOUR", 60, 400)):
        t.telecharger(api, "GOLD", unite, minutes, jours)
    api.deconnexion()


def periodes(t):
    out = []
    for a, b in ((None, COUPES[0]), (COUPES[0], COUPES[1]), (COUPES[1], None)):
        x = t
        if a is not None:
            x = x[x.date >= a]
        if b is not None:
            x = x[x.date < b]
        out.append(round(float(x.R.sum()), 1))
    c = np.r_[0, np.cumsum(t.sort_values("date").R.values)]
    return {"entrainement": out[0], "validation": out[1], "test": out[2], "total": round(float(t.R.sum()), 1),
            "trades": int(len(t)), "R_par_trade": round(float(t.R.mean()), 3) if len(t) else 0.0,
            "pire_baisse": round(float((c - np.maximum.accumulate(c)).min()), 1)}


def cond_de(dossier, epic, df):
    c = conditions(dossier, epic, float(df.close_bid.iloc[-1]))
    c.setdefault("nuit_achat", 0.02)
    c.setdefault("nuit_vente", 0.02)
    return c


def cassure(dossier, reentrees):
    tous = []
    for e in ("GOLD", "SILVER"):
        df = lire(dossier, e, "HOUR_4")
        sig = signaux_cassure(df, entree=20, sortie=20)
        c = sig.cible.values
        ok = np.r_[True, c[1:] != c[:-1]]
        if reentrees:  # comme le bot : nouvelle clôture au-delà du canal pendant une tendance en cours
            ok = ok | ((c == 1) & (sig.cloture > sig.haut).values) | ((c == -1) & (sig.cloture < sig.bas).values)
        t = serrage.simuler(df, c, ok, sig.stop.values, None, cond_de(dossier, e, df), regle=("garde", 1.5, 0.5))
        tous.append(t)
    return pd.concat(tous, ignore_index=True)


def st_eth(dossier):
    df = lire(dossier, "ETHUSD", "HOUR_4")
    v, ok, ds, _ = supertrend(df)
    return serrage.simuler(df, v, ok, ds, None, cond_de(dossier, "ETHUSD", df))


def elan(dossier):
    tous = []
    for e in ("GOLD", "SILVER"):
        df = lire(dossier, e, "HOUR_4")
        se = signaux_elan(df)
        cc = signaux_cassure(df, entree=20, sortie=20).cible.values
        s = np.where(cc == -se.sig.values, 0, se.sig.values)
        v, ok, ds = tenir(s, se.dist.values, len(df), 20)
        v = np.where(cc == -v, 0, v)
        tous.append(serrage.simuler(df, v, ok, ds, None, cond_de(dossier, e, df), dobj=ds * 2.0))
    return pd.concat(tous, ignore_index=True)


def rapide(dossier):
    d5, d1 = lire(dossier, "GOLD", "MINUTE_5"), lire(dossier, "GOLD", "HOUR")
    d4 = lire(dossier, "GOLD", "HOUR_4")
    voulu, bb, force = rapide_defauts.preparer(d5, d1, d4)
    ok = (bb > 1) & (force > 20) & (voulu != 0)
    cond = cond_de(dossier, "GOLD", d5)
    cond["min_pct"] = min(cond["min_pct"], 1.0)
    t = rapide_defauts.simuler(d5, voulu, ok, cond, suivi_pct=1.0, empiler=2, sortie_k=3)
    t = t[t.date >= d5.index[0] + pd.Timedelta(days=3)]
    c = np.r_[0, np.cumsum(t.R.values)]
    mil = t.date.min() + (t.date.max() - t.date.min()) / 2
    return {"total": round(float(t.R.sum()), 1), "moitie_1": round(float(t.R[t.date < mil].sum()), 1),
            "moitie_2": round(float(t.R[t.date >= mil].sum()), 1), "trades": int(len(t)),
            "R_par_trade": round(float(t.R.mean()), 3), "pire_baisse": round(float((c - np.maximum.accumulate(c)).min()), 1),
            "periode": f"{d5.index[0]:%d/%m/%Y} -> {d5.index[-1]:%d/%m/%Y}"}


def principal(dossier: Path):
    res = {}
    for nuits in (False, True):
        serrage.NUITS_EXACTES = nuits
        k = "frais de nuit comptés" if nuits else "ancien calcul (sans frais de nuit)"
        res[f"Cassure 4 h or+argent, 1er signal seulement | {k}"] = periodes(cassure(dossier, False))
        res[f"Cassure 4 h or+argent, avec re-entrées comme le bot | {k}"] = periodes(cassure(dossier, True))
        res[f"Supertrend 4 h ETH | {k}"] = periodes(st_eth(dossier))
        res[f"Élan 4 h or+argent | {k}"] = periodes(elan(dossier))
        try:
            res[f"Rapide 5 min or (réglages actuels) | {k}"] = rapide(dossier)
        except FileNotFoundError as e:
            print("Rapide : pas de données 5 min", e)
    for nom, v in res.items():
        print(f"{nom:90s} {json.dumps(v, ensure_ascii=False)}")
    Path(__file__).resolve().parent.joinpath("resultats_audit_chiffres.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    if sys.argv[1] == "telecharger":
        telecharger(Path(sys.argv[2]))
    else:
        principal(Path(sys.argv[1]))

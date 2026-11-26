"""Audit anti-triche (26/11/2026) : chaque backtest qui a validé une stratégie ACTIVE est rejoué sur des prix
TIRÉS AU HASARD (marche aléatoire, aucune tendance, aucun avantage possible).

Sur ces prix, une stratégie honnête doit perdre environ ses frais :
  - SANS frais (spread 0, nuit 0, prime 0) : résultat moyen par trade ~ 0 R (à la chance près) ;
  - AVEC frais : un peu négatif.
Si un backtest gagne nettement sur du hasard SANS frais, il « regarde le futur » (bug de triche).

Mêmes fonctions que les vrais backtests (aucune copie) :
  Cassure 4 h ........ backtest/serrage.simuler + bot/cassure.signaux_cassure (garde 50 % après +1,5 R)
  Rapide 5 min ....... backtest/rapide_defauts.simuler (réglages actuels : suiveur 1 %, 2 positions,
                       sortie confirmée 3 bougies, prix d'entrée après +0,5 R, garde 60 % après +1,5 R)
  Sorties (PR 32-34) . backtest/sortie_rapide.simuler (base, prix d'entrée, verrous) et serrage (gardes)
  Supertrend 4 h ..... backtest/reseaux.supertrend + serrage.simuler
  Élan 4 h ........... comme backtest/reseaux.actuelles (bot/elan.signaux_elan + smart_money.tenir)
  Usine / MACD ....... backtest/usine.simuler + bot/usine_regles (les 2 MACD actives + 400 combinaisons au hasard)
  Moteur général ..... backtest/moteur.executer (Tendance, Cassure)

Usage : python backtest/audit_hasard.py [nombre de graines, défaut 8]
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import rapide_defauts, serrage, sortie_rapide  # noqa: E402
from backtest import usine as U  # noqa: E402
from backtest.moteur import Conditions, executer  # noqa: E402
from backtest.reseaux import supertrend  # noqa: E402
from backtest.smart_money import tenir  # noqa: E402
from bot import usine_regles as R  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402
from bot.elan import signaux_elan  # noqa: E402
from bot.strategie import signaux_tendance  # noqa: E402

GRAINES = int(sys.argv[1]) if len(sys.argv) > 1 else 8


def marche_aleatoire(graine, jours, pas_min=5, sous_pas=5, vol_jour=0.012, spread_pct=0.012, debut="2017-01-02"):
    """Bougies de `pas_min` minutes (bid/ask) d'une marche aléatoire géométrique SANS dérive.
    Chaque bougie est faite de `sous_pas` petits pas (vrais plus haut / plus bas). Bourse ouverte 24 h/24."""
    rng = np.random.default_rng(graine)
    n = int(jours * 1440 / pas_min)
    sig = vol_jour / np.sqrt(1440 / pas_min * sous_pas)
    pas = rng.standard_normal((n, sous_pas)) * sig - sig ** 2 / 2  # martingale exacte sur le prix
    chemin = 2000 * np.exp(np.cumsum(pas.ravel())).reshape(n, sous_pas)
    ouv = np.r_[2000, chemin[:-1, -1]]
    haut = np.maximum(chemin.max(axis=1), ouv)
    bas = np.minimum(chemin.min(axis=1), ouv)
    clo = chemin[:, -1]
    idx = pd.date_range(debut, periods=n, freq=f"{pas_min}min")
    demi = spread_pct / 200
    d = {}
    for nom, x in (("open", ouv), ("high", haut), ("low", bas), ("close", clo)):
        d[f"{nom}_bid"], d[f"{nom}_ask"] = x * (1 - demi), x * (1 + demi)
    d["volume"] = 1.0
    return pd.DataFrame(d, index=idx)


def regrouper(df, regle):
    agg = {}
    for c in df.columns:
        agg[c] = "first" if c.startswith("open") else "max" if c.startswith("high") else "min" if c.startswith("low") \
            else "last" if c.startswith("close") else "sum"
    return df.resample(regle).agg(agg).dropna()


def sans_frais(df):
    m = df.copy()
    for k in ("open", "high", "low", "close"):
        mil = (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2
        m[f"{k}_bid"] = m[f"{k}_ask"] = mil
    return m


COND = {"avec": {"nuit_achat": 0.02, "nuit_vente": 0.02, "min_pct": 0.25, "prime_pct": 0.0},
        "sans": {"nuit_achat": 0.0, "nuit_vente": 0.0, "min_pct": 0.25, "prime_pct": 0.0}}


# --------------------------------------------------------------------------- un test par backtest
def t_cassure(d4, cond):
    sig = signaux_cassure(d4, entree=20, sortie=20)
    c = sig.cible.values
    return serrage.simuler(d4, c, np.r_[True, c[1:] != c[:-1]], sig.stop.values, None, cond,
                           regle=("garde", 1.5, 0.5)).R.values


def t_cassure_sans_garde(d4, cond):
    sig = signaux_cassure(d4, entree=20, sortie=20)
    c = sig.cible.values
    return serrage.simuler(d4, c, np.r_[True, c[1:] != c[:-1]], sig.stop.values, None, cond).R.values


def t_supertrend(d4, cond):
    v, ok, ds, _ = supertrend(d4)
    return serrage.simuler(d4, v, ok, ds, None, cond).R.values


def t_elan(d4, cond):
    se = signaux_elan(d4)
    cc = signaux_cassure(d4, entree=20, sortie=20).cible.values
    s = np.where(cc == -se.sig.values, 0, se.sig.values)
    v, ok, ds = tenir(s, se.dist.values, len(d4), 20)
    v = np.where(cc == -v, 0, v)
    return serrage.simuler(d4, v, ok, ds, None, cond, dobj=ds * 2.0).R.values


def t_tendance_moteur(d4, cond):
    sig = signaux_tendance(d4, adx_min=20, suivi_atr=5)
    c = Conditions(taille_min=0.0001, pas_taille=0.0001, stop_garanti_min_pct=cond["min_pct"],
                   frais_nuit_achat_pct=cond["nuit_achat"], frais_nuit_vente_pct=cond["nuit_vente"], eurusd=1.0)
    r = executer(d4, sig, 1e6, 1.0, c, levier_max=50)
    t = r.trades
    return (t.pnl_eur.values / 1e4) if len(t) else np.array([])  # ~ en R (1 % du capital, à peu près fixe)


def t_cassure_moteur(d4, cond):
    sig = signaux_cassure(d4, entree=20, sortie=20)
    c = Conditions(taille_min=0.0001, pas_taille=0.0001, stop_garanti_min_pct=cond["min_pct"],
                   frais_nuit_achat_pct=cond["nuit_achat"], frais_nuit_vente_pct=cond["nuit_vente"], eurusd=1.0)
    r = executer(d4, sig, 1e6, 1.0, c, levier_max=50)
    t = r.trades
    return (t.pnl_eur.values / 1e4) if len(t) else np.array([])


def _usine(d4, cond, spec):
    ind = R.Indicateurs(d4)
    P = U.Prix(d4, ind, {**cond, "devise": "USD", "nom": "", "taille_min": 1})
    voulu, ok, dstop, dobj = R.preparer(ind, spec)
    sig = np.nonzero(ok & (voulu != 0) & np.isfinite(ind.atr.values))[0]
    return np.array([x[1] for x in U.simuler(P, list(voulu), sig, list(dstop), list(dobj), spec["suiveur"],
                                             spec["duree"], 200, len(d4))])


ACTIVES = json.loads((Path(__file__).resolve().parent.parent / "bot" / "usine_strategies.json").read_text())


def t_macd_gaz(d4, cond):
    return _usine(d4, cond, ACTIVES[0]["spec"])


def t_macd_tesla(d4, cond):
    return _usine(d4, cond, ACTIVES[1]["spec"])


def t_usine_hasard(d4, cond, n=400, graine=0):
    """400 combinaisons de l'usine tirées au hasard (familles, réglages, filtres, stops, objectifs, suiveurs)."""
    rng = np.random.default_rng(graine)
    tout = list(U.combinaisons())
    r = []
    for _ in range(n):
        fam, pi, fl, se = tout[rng.integers(len(tout))]
        cle = (fam, pi, fl, se, rng.integers(len(R.STOPS)), rng.integers(len(R.OBJECTIFS)),
               rng.integers(len(R.SUIVEURS)), rng.integers(len(R.DUREES)))
        r.append(_usine(d4, cond, U.spec_de(cle)))
    return np.concatenate(r)


def t_rapide(d5, d1, d4, cond):
    voulu, bb, force = rapide_defauts.preparer(d5, d1, d4)
    ok = (bb > 1) & (force > 20) & (voulu != 0)
    c = {**cond, "min_pct": min(cond["min_pct"], 1.0)}
    return rapide_defauts.simuler(d5, voulu, ok, c, suivi_pct=1.0, empiler=2, sortie_k=3).R.values


def t_rapide_ancienne(d5, d1, d4, cond):
    voulu, bb, force = rapide_defauts.preparer(d5, d1, d4)
    ok = (bb > 1) & (force > 20) & (voulu != 0)
    return rapide_defauts.simuler(d5, voulu, ok, cond, suivi_pct=2.0, empiler=3, sortie_k=1).R.values


def t_sorties_rapide(d5, d1, d4, cond):
    """PR 32 (prix d'entrée après +0,5 R) avec le simulateur de backtest/sortie_rapide.py."""
    voulu, ok = sortie_rapide.cibles(d5, d1, d4)
    return sortie_rapide.simuler(d5, voulu, ok, cond, be=0.5).R.values


def t_verrou_rapide(d5, d1, d4, cond):
    voulu, ok = sortie_rapide.cibles(d5, d1, d4)
    return sortie_rapide.simuler(d5, voulu, ok, cond, verrou=[(1, 0), (2, 1), (3, 2)]).R.values


def t_garde_rapide(d5, d1, d4, cond):
    """PR 34 (garde 60 % après +1,5 R) avec le simulateur de backtest/serrage.py."""
    voulu, ok = sortie_rapide.cibles(d5, d1, d4)
    m = (d5.close_bid + d5.close_ask).values / 2
    c = {**cond, "min_pct": min(cond["min_pct"], 1.0)}
    return serrage.simuler(d5, voulu, ok, m * 0.01, m * 0.02, c, regle=("garde", 1.5, 0.6), be=0.5).R.values


TESTS_4H = {"Cassure 4 h (garde 50 % après +1,5 R)": t_cassure, "Cassure 4 h sans garde": t_cassure_sans_garde,
            "Supertrend 10/3 4 h": t_supertrend, "Élan 4 h": t_elan, "MACD gaz naturel (usine)": t_macd_gaz,
            "MACD Tesla (usine)": t_macd_tesla, "Usine : 400 combinaisons au hasard": t_usine_hasard,
            "Moteur général : Tendance 4 h": t_tendance_moteur, "Moteur général : Cassure 4 h": t_cassure_moteur}
TESTS_5M = {"Rapide 5 min (réglages actuels, PR 36)": t_rapide, "Rapide 5 min (anciens réglages)": t_rapide_ancienne,
            "Sortie au prix d'entrée +0,5 R (PR 32)": t_sorties_rapide, "Stop garanti en paliers": t_verrou_rapide,
            "Garde 60 % après +1,5 R (PR 34)": t_garde_rapide}


def resume(r):
    r = np.asarray(r, dtype=float)
    n = len(r)
    if n < 2:
        return {"trades": n, "R": float(r.sum()) if n else 0.0, "R_par_trade": 0.0, "t": 0.0}
    return {"trades": n, "R": round(float(r.sum()), 1), "R_par_trade": round(float(r.mean()), 4),
            "t": round(float(r.mean() / r.std(ddof=1) * np.sqrt(n)), 2)}


def principal():
    res = {}
    for g in range(GRAINES):
        # 4 h : 10 ans (comme l'usine), bougies 4 h construites à partir de pas de 15 min
        base = marche_aleatoire(1000 + g, 3650, pas_min=60, sous_pas=12)
        d4 = {"avec": regrouper(base, "4h")}
        d4["sans"] = sans_frais(d4["avec"])
        for nom, f in TESTS_4H.items():
            for k in ("avec", "sans"):
                serrage.PRIME_PCT = U.PRIME_PCT = 0.1 if k == "avec" else 0.0
                res.setdefault(nom, {}).setdefault(k, []).append(f(d4[k], COND[k]))
        # 5 min : 6 mois (comme le backtest de la Rapide), 1 h et 4 h construites à partir des mêmes prix
        b5 = marche_aleatoire(2000 + g, 180, pas_min=5, sous_pas=5)
        for k in ("avec", "sans"):
            d5 = b5 if k == "avec" else sans_frais(b5)
            d1, d4b = regrouper(d5, "1h"), regrouper(d5, "4h")
            serrage.PRIME_PCT = U.PRIME_PCT = 0.1 if k == "avec" else 0.0
            for nom, f in TESTS_5M.items():
                res.setdefault(nom, {}).setdefault(k, []).append(f(d5, d1, d4b, COND[k]))
        print(f"graine {g + 1}/{GRAINES} faite", flush=True)
    sortie = {}
    print(f"\n{'backtest':42s} {'SANS frais : R/trade':>21s} {'t':>6s} {'trades':>7s} | {'AVEC frais : R/trade':>21s} {'t':>6s}")
    for nom, v in res.items():
        s, a = resume(np.concatenate(v["sans"])), resume(np.concatenate(v["avec"]))
        par_graine = [round(float(np.sum(x)), 1) for x in v["sans"]]
        # Suspect = gagne sur du hasard MÊME APRÈS FRAIS. (Le « t » sans frais de l'usine est gonflé : ses 1,7 million
        # de trades viennent des mêmes 8 séries de prix ; son petit +0,007 R/trade vient du stop GARANTI exécuté
        # exactement à son niveau quand le prix saute au-delà : vrai chez Capital.com, payé par la prime.)
        triche = a["R_par_trade"] > 0 and a["t"] > 2
        sortie[nom] = {"sans_frais": s, "avec_frais": a, "R_sans_frais_par_graine": par_graine, "suspect": triche}
        print(f"{nom:42s} {s['R_par_trade']:+21.4f} {s['t']:6.2f} {s['trades']:7d} | {a['R_par_trade']:+21.4f} {a['t']:6.2f}"
              f"{'   <- SUSPECT (gagne sur du hasard)' if triche else ''}")
    Path(__file__).resolve().parent.joinpath("resultats_audit_hasard.json").write_text(
        json.dumps({"graines": GRAINES, "resultats": sortie}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    principal()

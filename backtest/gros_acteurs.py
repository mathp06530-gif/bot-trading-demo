"""Backtest « SUIVRE LES GROS ACTEURS » (idée de Mathis, 25/11/2026 : « les banques ne mettent pas 1 €,
ça doit se voir »).

Ce qu'on peut VRAIMENT voir gratuitement, et qu'on peut tester sur 2 ans sans tricher (rien du futur) :
  1. Le VOLUME de Capital.com (lastTradedVolume) : sur un CFD, ce n'est pas l'argent des banques mais
     le nombre de changements de prix. On vérifie d'abord s'il suit l'agitation du marché.
     - « volume fort »  : la bougie du signal a un volume >= 1,5 x la moyenne des 20 derniers jours
                          à la même heure (le volume dépend beaucoup de l'heure).
     - « VWAP 20 j »    : achat seulement au-dessus du prix moyen pondéré par le volume des 20 derniers
                          jours (vente seulement en dessous). C'est le prix de référence des gros ordres.
  2. Le rapport COT de la CFTC (gendarme américain) : chaque semaine, la position des « fonds »
     (managed money pour l'or et l'argent au COMEX, leveraged funds pour le Bitcoin au CME).
     Positions du mardi, publiées le vendredi 20 h 30 UTC : on ne s'en sert qu'à partir du LUNDI suivant.
     - « COT 1 sem »    : les fonds ont augmenté leur position dans le sens du trade la semaine passée ;
     - « COT 4 sem »    : pareil sur 4 semaines ;
     - « COT pas foule »: on n'entre pas si les fonds sont déjà au plus haut d'un an dans le sens du trade
                          (tout le monde est déjà dedans : contrarien, rang > 90 % sur 52 semaines).
Pour chaque filtre, si le filtre n'est pas d'accord : « refus » (pas d'entrée) ou « demi » (moitié de taille).
Une variante n'est « meilleure » que si elle fait plus de R sur les DEUX moitiés des 2 ans et que la pire
baisse ne s'aggrave pas de plus de 1 R (règles de l'auto-amélioration du dimanche).

Usage : python backtest/gros_acteurs.py [dossier]   (CSV de telecharger.py + cot/*.txt de la CFTC)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402
from bot.cerveaux import conseil  # noqa: E402
from bot.strategie import signaux_tendance  # noqa: E402

if len(sys.argv) > 1:
    serrage.DOSSIER = Path(sys.argv[1])
COT = {"GOLD": ("disagg", "GOLD - COMMODITY EXCHANGE", "m_money"),
       "SILVER": ("disagg", "SILVER - COMMODITY EXCHANGE", "m_money"),
       "BTCUSD": ("fin", "BITCOIN - CHICAGO MERCANTILE", "lev_money")}


def lire_cot(epic):
    """Position nette des fonds, par semaine, datée du jour où on peut l'utiliser (lundi 00 h UTC)."""
    genre, nom, qui = COT[epic]
    morceaux = []
    for f in sorted((serrage.DOSSIER / "cot" / genre).glob("*.txt")):
        d = pd.read_csv(f, low_memory=False)
        d.columns = [c.strip().lower() for c in d.columns]
        morceaux.append(d)
    d = pd.concat(morceaux, ignore_index=True)
    col_nom = next(c for c in d.columns if c.startswith("market_and_exchange"))
    col_date = next(c for c in d.columns if "yyyy-mm-dd" in c)
    lg = next(c for c in d.columns if c.startswith(qui) and "long_all" in c and "spread" not in c)
    ct = next(c for c in d.columns if c.startswith(qui) and "short_all" in c and "spread" not in c)
    d = d[d[col_nom].str.upper().str.startswith(nom)]
    d = d[~d[col_nom].str.upper().str.contains("MICRO")]
    s = pd.Series((d[lg].astype(float) - d[ct].astype(float)).values,
                  index=pd.to_datetime(d[col_date])).sort_index()
    s = s[~s.index.duplicated()]
    s.index = s.index + pd.Timedelta(days=6)  # mardi -> lundi suivant (publié le vendredi soir)
    print(f"COT {epic} : {len(s)} semaines, {s.index[0]:%d/%m/%Y} -> {s.index[-1]:%d/%m/%Y}, net actuel {s.iloc[-1]:.0f}")
    return s


def filtres(epic, df):
    """Avis de chaque filtre par bougie 4 h terminée : +1 (achat permis), -1 (vente permise), 0 (rien), 2 (les deux)."""
    n = len(df)
    m = (df.close_bid + df.close_ask) / 2
    vol = df.volume.astype(float)
    out = {}
    # volume fort : comparé aux 20 derniers jours à la même heure
    ref = vol.groupby(df.index.hour).transform(lambda v: v.shift(1).rolling(20, min_periods=10).mean())
    out["volume fort"] = np.where(vol >= 1.5 * ref, 2, 0)
    # VWAP 20 jours (bougies 4 h : ~6 par jour)
    tp = ((df.high_bid + df.high_ask) / 2 + (df.low_bid + df.low_ask) / 2 + m) / 3
    vwap = (tp * vol).rolling(120, min_periods=60).sum() / vol.rolling(120, min_periods=60).sum()
    out["VWAP 20 j"] = np.where(m > vwap, 1, np.where(m < vwap, -1, 0))
    try:
        s = lire_cot(epic)

        d1 = s.diff(1).reindex(df.index + pd.Timedelta(hours=4), method="ffill").values
        d4 = s.diff(4).reindex(df.index + pd.Timedelta(hours=4), method="ffill").values
        rang = s.rolling(52, min_periods=26).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
        rg = rang.reindex(df.index + pd.Timedelta(hours=4), method="ffill").values
        out["COT 1 sem"] = np.sign(np.nan_to_num(d1)).astype(int)
        out["COT 4 sem"] = np.sign(np.nan_to_num(d4)).astype(int)
        out["COT pas foule"] = np.where(np.isnan(rg), 2, np.where(rg > 0.9, -1, np.where(rg < 0.1, 1, 2)))
    except Exception as e:  # noqa: BLE001
        print(f"COT {epic} indisponible : {e}")
    return {k: np.asarray(v)[:n] for k, v in out.items()}


def diagnostic_volume(epic, df):
    m = (df.close_bid + df.close_ask) / 2
    mouv = ((df.high_bid + df.high_ask) / 2 - (df.low_bid + df.low_ask) / 2) / m
    v = df.volume.astype(float)
    print(f"Volume {epic} : {(v > 0).mean() * 100:.0f} % de bougies avec volume, médiane {v.median():.0f}, "
          f"corrélation avec l'amplitude de la bougie {v.corr(mouv):.2f}")


def jeux():
    j = []
    for e in ("GOLD", "SILVER"):
        df = serrage.lire(e, "HOUR_4")
        diagnostic_volume(e, df)
        sig = signaux_cassure(df, entree=20, sortie=20)
        c = sig.cible.values
        neuf = np.r_[True, c[1:] != c[:-1]]
        j.append(("cassure", e, df, c, neuf, sig.stop.values, None, None,
                  serrage.conditions(e, float(df.close_bid.iloc[-1])), 1.0, filtres(e, df)))
    e = "BTCUSD"
    df = serrage.lire(e, "HOUR_4")
    diagnostic_volume(e, df)
    sig = signaux_tendance(df, adx_min=20, suivi_atr=5)
    c = sig.cible.values
    neuf = np.r_[True, c[1:] != c[:-1]]
    try:
        neuf = neuf & (conseil(df, serrage.lire(e, "HOUR")) == c)  # en place : 2 avis sur 3 d'accord
    except Exception as ex:  # noqa: BLE001
        print(f"Deux cerveaux non appliqués : {ex}")
    cond = serrage.conditions(e, float(df.close_bid.iloc[-1]))
    f = filtres(e, df)
    j.append(("tendance", e + " moitié TP", df, c, neuf, sig.stop.values, sig.suivi.values, sig.atr.values, cond, 0.5, f))
    j.append(("tendance", e + " moitié sans TP", df, c, neuf, sig.stop.values, sig.suivi.values, None, cond, 0.5, f))
    return j


def evaluer(jx, regle, filtre=None, mode="refus", ans=2.0):
    fin = max(x[2].index[-1] for x in jx)
    debut = max(fin - pd.Timedelta(days=365 * ans), max(x[2].index[0] for x in jx) + pd.Timedelta(days=60))
    milieu_ = debut + (fin - debut) / 2
    tous = []
    for (_, e, df, c, ok, dstop, dsuivi, dobj, cond, w, fl) in jx:
        if filtre is None:
            accord = np.ones(len(df), dtype=bool)
        elif filtre not in fl:
            return None, None
        else:
            a = fl[filtre]
            accord = (a == 2) | ((a == c) & (c != 0))
        ok2 = ok & accord if mode == "refus" else ok
        t = serrage.simuler(df, c, ok2, dstop, dsuivi, cond, regle=regle, dobj=dobj)
        if len(t):
            i_sig = df.index.get_indexer(t.date) - 1
            poids = np.where(accord[i_sig], 1.0, 0.5 if mode == "demi" else 1.0)
            t["R"] = t.R * w * poids
        tous.append(t)
    return serrage.resumer(pd.concat(tous, ignore_index=True), debut, milieu_), (debut, milieu_, fin)


def principal():
    tout = jeux()
    sortie = {}
    for titre, strat, regle in (("Cassure 4 h or + argent", "cassure", ("garde", 1.5, 0.5)),
                                ("Tendance 4 h BTC (avec 2 cerveaux)", "tendance", None)):
        jx = [x for x in tout if x[0] == strat]
        base, periode = evaluer(jx, regle)
        res = {"actuelle": base}
        for filtre in ("volume fort", "VWAP 20 j", "COT 1 sem", "COT 4 sem", "COT pas foule"):
            for mode in ("refus", "demi"):
                r, _ = evaluer(jx, regle, filtre, mode)
                if r:
                    res[f"{filtre}, sinon {mode}"] = r
        print(f"\n=== {titre} : {periode[0]:%d/%m/%Y} -> {periode[2]:%d/%m/%Y} (moitié au {periode[1]:%d/%m/%Y})")
        print(f"{'variante':30s} {'R':>7s} {'an 1':>7s} {'an 2':>7s} {'trades':>6s} {'réuss.':>6s} {'baisse':>7s}")
        meilleures = []
        for nom, s in sorted(res.items(), key=lambda kv: -kv[1]["R"]):
            mieux = nom != "actuelle" and s["R_1"] > base["R_1"] and s["R_2"] > base["R_2"] \
                and s["pire_baisse_R"] >= base["pire_baisse_R"] - 1
            if mieux:
                meilleures.append(nom)
            print(f"{nom:30s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['reussite']:6.1f} "
                  f"{s['pire_baisse_R']:7.2f}{'  <- MIEUX' if mieux else ''}")
        sortie[titre] = {"periode": [str(p) for p in periode], "meilleures": meilleures, "resultats": res}
    (Path(__file__).resolve().parent / "resultats_gros_acteurs.json").write_text(
        json.dumps(sortie, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

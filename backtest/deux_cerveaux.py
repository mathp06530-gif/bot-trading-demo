"""Backtest « DEUX CERVEAUX PAR MARCHÉ » (idée de Mathis, 25/11/2026, après une vidéo où deux traders
confrontent leurs analyses avant d'entrer).

Cerveau 1 = la stratégie actuelle du marché (Cassure 4 h sur l'or et l'argent, Tendance 4 h sur le Bitcoin).
Cerveau 2 = une analyse DIFFÉRENTE, faite sur les mêmes bougies terminées (rien sur le futur) :
  - « note »      : note technique de ~20 indicateurs (bot/analyse.py), d'accord si > +0,1 (achat) / < -0,1 (vente) ;
  - « note forte »: la même note, mais > +0,5 (« achat fort ») / < -0,5 ;
  - « structure » : structure de marché comme dans la vidéo : les 2 derniers sommets ET les 2 derniers creux
                    montent (achat) ou descendent (vente) ;
  - « 1 h »       : la tendance 1 h va dans le même sens (EMA 20 / 50 en 1 h et prix du bon côté de l'EMA 20) ;
  - « conseil »   : les 3 avis ci-dessus votent, la majorité (2 sur 3) doit être d'accord.
Décision sur la TAILLE quand le cerveau 1 veut entrer :
  - d'accord      : taille normale (1) ;
  - pas d'accord  : « refus » = pas d'entrée, ou « demi » = moitié de la taille.
Une variante n'est « meilleure » que si elle fait plus de R sur les DEUX années et que la pire baisse
ne s'aggrave pas de plus de 1 R (mêmes règles que l'auto-amélioration du dimanche).

Usage : python backtest/deux_cerveaux.py [dossier]  (CSV de backtest/telecharger.py)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from bot.cerveaux import avis_1h, avis_note, avis_structure  # noqa: E402
from bot.cerveaux import conseil as conseil_live  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402
from bot.strategie import signaux_tendance  # noqa: E402

if len(sys.argv) > 1:
    serrage.DOSSIER = Path(sys.argv[1])


def avis_tous(df4, df1):
    n = avis_note(df4)
    s = avis_structure(df4)
    h = avis_1h(df4, df1)
    conseil = conseil_live(df4, df1)  # majorité des 3 avis (au moins 2 dans le même sens)
    return {"note": n, "note forte": avis_note(df4, 0.5), "structure": s, "1 h": h, "conseil": conseil}


def jeux_de(strat):
    jeux = []
    if strat == "cassure":
        for e in ("GOLD", "SILVER"):
            df = serrage.lire(e, "HOUR_4")
            sig = signaux_cassure(df, entree=20, sortie=20)
            c = sig.cible.values
            neuf = np.r_[True, c[1:] != c[:-1]]
            cond = serrage.conditions(e, float(df.close_bid.iloc[-1]))
            jeux.append((e, df, c, neuf, sig.stop.values, None, None, cond, 1.0,
                         avis_tous(df, serrage.lire(e, "HOUR"))))
    else:
        e = "BTCUSD"
        df = serrage.lire(e, "HOUR_4")
        sig = signaux_tendance(df, adx_min=20, suivi_atr=5)
        c = sig.cible.values
        neuf = np.r_[True, c[1:] != c[:-1]]
        cond = serrage.conditions(e, float(df.close_bid.iloc[-1]))
        av = avis_tous(df, serrage.lire(e, "HOUR"))
        jeux.append((e + " (moitié TP)", df, c, neuf, sig.stop.values, sig.suivi.values, sig.atr.values, cond, 0.5, av))
        jeux.append((e + " (moitié sans TP)", df, c, neuf, sig.stop.values, sig.suivi.values, None, cond, 0.5, av))
    return jeux


def evaluer(jeux, regle, avis=None, mode="refus", ans=2.0):
    fin = max(j[1].index[-1] for j in jeux)
    debut = max(fin - pd.Timedelta(days=365 * ans), max(j[1].index[0] for j in jeux) + pd.Timedelta(days=60))
    milieu_ = debut + (fin - debut) / 2
    tous = []
    for (e, df, c, ok, dstop, dsuivi, dobj, cond, w, av) in jeux:
        accord = np.ones(len(df), dtype=bool) if avis is None else (av[avis] == c) & (c != 0)
        ok2 = ok & accord if mode == "refus" else ok
        t = serrage.simuler(df, c, ok2, dstop, dsuivi, cond, regle=regle, dobj=dobj)
        if len(t):
            i_sig = df.index.get_indexer(t.date) - 1  # bougie du signal (entrée à la bougie suivante)
            poids = np.where(accord[i_sig], 1.0, 0.5 if mode == "demi" else 1.0)
            t["R"] = t.R * w * poids
        tous.append(t)
    return serrage.resumer(pd.concat(tous, ignore_index=True), debut, milieu_), (debut, milieu_, fin)


def principal():
    sortie = {}
    for titre, strat, regle in (("Cassure 4 h or + argent", "cassure", ("garde", 1.5, 0.5)),
                                ("Tendance 4 h BTC", "tendance", None)):
        jeux = jeux_de(strat)
        base, periode = evaluer(jeux, regle)
        res = {"actuelle (1 cerveau)": base}
        for avis in ("note", "note forte", "structure", "1 h", "conseil"):
            for mode in ("refus", "demi"):
                res[f"2 cerveaux : {avis}, désaccord = {mode}"], _ = evaluer(jeux, regle, avis, mode)
        print(f"\n=== {titre} : {periode[0]:%d/%m/%Y} -> {periode[2]:%d/%m/%Y} (moitié au {periode[1]:%d/%m/%Y})")
        print(f"{'variante':42s} {'R':>7s} {'an 1':>7s} {'an 2':>7s} {'trades':>6s} {'réuss.':>6s} {'baisse':>7s}")
        meilleures = []
        for nom, s in sorted(res.items(), key=lambda kv: -kv[1]["R"]):
            mieux = nom != "actuelle (1 cerveau)" and s["R_1"] > base["R_1"] and s["R_2"] > base["R_2"] \
                and s["pire_baisse_R"] >= base["pire_baisse_R"] - 1
            if mieux:
                meilleures.append(nom)
            print(f"{nom:42s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['reussite']:6.1f} "
                  f"{s['pire_baisse_R']:7.2f}{'  <- MIEUX' if mieux else ''}")
        sortie[titre] = {"periode": [str(p) for p in periode], "meilleures": meilleures, "resultats": res}
    (Path(__file__).resolve().parent / "resultats_deux_cerveaux.json").write_text(
        json.dumps(sortie, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

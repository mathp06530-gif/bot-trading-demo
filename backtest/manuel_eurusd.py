"""TRADING MANUEL EUR/USD (28/11/2026, demande de Mathis : apprendre une stratégie RAPIDE bien définie, à la main,
en démo). Aucun ordre : labo seulement.

On teste 4 stratégies simples, faisables à la main, sur les vraies bougies Capital.com (prix acheteur ET vendeur,
donc le vrai spread est payé à chaque trade) :
  A. « Cassure de Londres » : boîte = plus haut / plus bas d'une plage horaire, entrée à la clôture d'une bougie
     qui sort de la boîte, stop de l'autre côté (ou au milieu), objectif en R, tout fermé à 17 h 30 Paris.
  B. « Cassure de New York » : même chose sur la boîte 14 h 30 - 15 h 00 Paris, fermé à 21 h Paris.
  C. « Repli sur la moyenne » : tendance (EMA 20 > EMA 50 et prix > EMA 50), la bougie touche l'EMA 20 et clôture
     du bon côté -> entrée, stop sous la bougie, objectif en R. 9 h - 18 h Paris, 2 trades/jour max.
  D. « Rebond Bollinger » : clôture hors de la bande (20, 2) puis clôture de retour dedans -> entrée vers la
     moyenne, stop au-delà de l'extrême, objectif = moyenne 20. 9 h - 18 h Paris.

Anti-triche (règles du dépôt) :
  - signal lu sur une bougie CLÔTURÉE, entrée à l'ouverture de la suivante ;
  - si stop ET objectif sont touchés dans la même bougie : on compte le STOP (pessimiste) ;
  - réglages choisis sur la 1re période seulement (« choix »), jugés sur la 2e (« test », jamais vue) ;
  - tout est refait sur des prix MÉLANGÉS (doit donner ~0) ;
  - pas de frais de nuit : tout est fermé le jour même.

Usage : python backtest/manuel_eurusd.py <dossier_prix> <sortie.md> <sortie.json> [dossier_images]
"""
import json
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ia.predire import lire  # noqa: E402

PIP = 0.0001
EPIC = "EURUSD"
PART_CHOIX = 0.6  # 60 % du temps pour choisir, 40 % jamais vus pour juger


def h(x):
    """'9:30' -> 9.5"""
    a, b = x.split(":")
    return int(a) + int(b) / 60


def preparer(d):
    d = d.copy()
    paris = d.index.tz_localize("UTC").tz_convert("Europe/Paris")
    d["jour"] = paris.date
    d["heure"] = paris.hour + paris.minute / 60
    mid = (d.close_bid + d.close_ask) / 2
    d["mid"] = mid
    d["hi"] = (d.high_bid + d.high_ask) / 2
    d["lo"] = (d.low_bid + d.low_ask) / 2
    d["ema20"] = mid.ewm(span=20, adjust=False).mean()
    d["ema50"] = mid.ewm(span=50, adjust=False).mean()
    m20 = mid.rolling(20).mean()
    s20 = mid.rolling(20).std()
    d["bb_m"], d["bb_h"], d["bb_b"] = m20, m20 + 2 * s20, m20 - 2 * s20
    tr = np.maximum(d.hi - d.lo, np.maximum((d.hi - mid.shift()).abs(), (d.lo - mid.shift()).abs()))
    d["atr"] = tr.rolling(14).mean()
    return d


def simuler(d, i, sens, stop, objectif, fin_h):
    """Entrée à l'ouverture de la bougie i+1. Renvoie (R après spread, j de sortie, raison) ou None."""
    n = len(d)
    if i + 1 >= n:
        return None
    j = i + 1
    jour = d.jour.iat[i]
    if d.jour.iat[j] != jour or d.heure.iat[j] >= fin_h:
        return None
    entree = d.open_ask.iat[j] if sens > 0 else d.open_bid.iat[j]
    risque = (entree - stop) * sens
    if risque <= 0.5 * PIP:  # stop trop près (ou déjà dépassé à l'ouverture) : on ne prend pas
        return None
    while j < n:
        if d.jour.iat[j] != jour or d.heure.iat[j] >= fin_h:
            # clôture forcée à l'ouverture de la première bougie après l'heure de fin
            k = j if d.jour.iat[j] == jour else j - 1
            sortie = (d.open_bid.iat[k] if sens > 0 else d.open_ask.iat[k]) if k == j else \
                (d.close_bid.iat[k] if sens > 0 else d.close_ask.iat[k])
            return (sortie - entree) * sens / risque, k, "heure"
        if sens > 0:
            if d.low_bid.iat[j] <= stop:
                return (min(stop, d.open_bid.iat[j]) - entree) / risque, j, "stop"
            if objectif is not None and d.high_bid.iat[j] >= objectif:
                return (objectif - entree) / risque, j, "objectif"
        else:
            if d.high_ask.iat[j] >= stop:
                return (entree - max(stop, d.open_ask.iat[j])) / risque, j, "stop"
            if objectif is not None and d.low_ask.iat[j] <= objectif:
                return (entree - objectif) / risque, j, "objectif"
        j += 1
    return None


# --------------------------------------------------------------------------- stratégies
def cassure(d, boite, fin_entree, fin_h, stop_mode, r_obj, max_pips):
    """Boîte = [boite[0], boite[1]) heure de Paris. 1 trade par jour max."""
    trades = []
    debut_b, fin_b = h(boite[0]), h(boite[1])
    fe, fh = h(fin_entree), h(fin_h)
    for jour, g in d.groupby("jour", sort=True):
        b = g[(g.heure >= debut_b) & (g.heure < fin_b)]
        if len(b) < 2:
            continue
        haut, bas = b.hi.max(), b.lo.min()
        if (haut - bas) / PIP > max_pips or (haut - bas) / PIP < 3:
            continue
        apres = g[(g.heure >= fin_b) & (g.heure < fe)]
        for t, row in apres.iterrows():
            sens = 1 if row.mid > haut else -1 if row.mid < bas else 0
            if not sens:
                continue
            i = d.index.get_loc(t)
            milieu = (haut + bas) / 2
            stop = (bas if sens > 0 else haut) if stop_mode == "autre bord" else milieu
            ent = d.open_ask.iat[i + 1] if (i + 1 < len(d) and sens > 0) else d.open_bid.iat[min(i + 1, len(d) - 1)]
            obj = ent + sens * r_obj * abs(ent - stop) if r_obj else None
            res = simuler(d, i, sens, stop, obj, fh)
            if res:
                trades.append((t, sens, *res, stop, obj))
            break
    return trades


def repli(d, r_obj, marge_pips, max_jour=2, debut="9:00", fin="18:00", fin_h="18:30"):
    trades = []
    libre = -1
    nb = {}
    deb, fi, fh = h(debut), h(fin), h(fin_h)
    m, e20, e50 = d.mid.to_numpy(), d.ema20.to_numpy(), d.ema50.to_numpy()
    for i in range(60, len(d) - 1):
        if i <= libre:
            continue
        hr = d.heure.iat[i]
        if hr < deb or hr >= fi:
            continue
        jour = d.jour.iat[i]
        if nb.get(jour, 0) >= max_jour:
            continue
        haut_tend = e20[i] > e50[i] and m[i] > e50[i] and e50[i] > e50[i - 5]
        bas_tend = e20[i] < e50[i] and m[i] < e50[i] and e50[i] < e50[i - 5]
        o = (d.open_bid.iat[i] + d.open_ask.iat[i]) / 2
        if haut_tend and d.lo.iat[i] <= e20[i] and m[i] > e20[i] and m[i] > o:
            sens, stop = 1, d.lo.iat[i] - marge_pips * PIP
        elif bas_tend and d.hi.iat[i] >= e20[i] and m[i] < e20[i] and m[i] < o:
            sens, stop = -1, d.hi.iat[i] + marge_pips * PIP
        else:
            continue
        ent = d.open_ask.iat[i + 1] if sens > 0 else d.open_bid.iat[i + 1]
        obj = ent + sens * r_obj * abs(ent - stop)
        res = simuler(d, i, sens, stop, obj, fh)
        if res:
            trades.append((d.index[i], sens, *res, stop, obj))
            nb[jour] = nb.get(jour, 0) + 1
            libre = res[1]
    return trades


def bollinger(d, marge_pips, max_jour=3, debut="9:00", fin="18:00", fin_h="18:30"):
    trades = []
    libre = -1
    nb = {}
    deb, fi, fh = h(debut), h(fin), h(fin_h)
    m, bh, bb = d.mid.to_numpy(), d.bb_h.to_numpy(), d.bb_b.to_numpy()
    for i in range(30, len(d) - 1):
        if i <= libre:
            continue
        hr = d.heure.iat[i]
        if hr < deb or hr >= fi or nb.get(d.jour.iat[i], 0) >= max_jour:
            continue
        if m[i - 1] < bb[i - 1] and m[i] > bb[i]:
            sens, stop = 1, min(d.lo.iat[i - 1], d.lo.iat[i]) - marge_pips * PIP
        elif m[i - 1] > bh[i - 1] and m[i] < bh[i]:
            sens, stop = -1, max(d.hi.iat[i - 1], d.hi.iat[i]) + marge_pips * PIP
        else:
            continue
        obj = d.bb_m.iat[i]
        res = simuler(d, i, sens, stop, obj, fh)
        if res:
            trades.append((d.index[i], sens, *res, stop, obj))
            nb[d.jour.iat[i]] = nb.get(d.jour.iat[i], 0) + 1
            libre = res[1]
    return trades


def variantes():
    v = []
    for boite, sm, r, mx in product([("1:00", "9:00"), ("9:00", "10:00")], ["autre bord", "milieu"], [1.0, 1.5, 2.0, None], [40]):
        nom = f"A Cassure Londres boîte {boite[0]}-{boite[1]}, stop {sm}, objectif {'heure de fin' if r is None else f'{r} R'}"
        v.append((nom, lambda d, boite=boite, sm=sm, r=r, mx=mx: cassure(d, boite, "13:00", "17:30", sm, r, mx)))
    for sm, r in product(["autre bord", "milieu"], [1.0, 1.5, 2.0, None]):
        nom = f"B Cassure New York boîte 14:30-15:00, stop {sm}, objectif {'heure de fin' if r is None else f'{r} R'}"
        v.append((nom, lambda d, sm=sm, r=r: cassure(d, ("14:30", "15:00"), "17:00", "21:00", sm, r, 40)))
    for r, mg in product([1.0, 1.5, 2.0], [1, 3]):
        v.append((f"C Repli EMA 20, objectif {r} R, marge stop {mg} pips", lambda d, r=r, mg=mg: repli(d, r, mg)))
    for mg in (1, 3):
        v.append((f"D Rebond Bollinger, objectif moyenne 20, marge stop {mg} pips", lambda d, mg=mg: bollinger(d, mg)))
    return v


# --------------------------------------------------------------------------- mesures
def stats(trades, debut=None, fin=None):
    t = [x for x in trades if (debut is None or x[0] >= debut) and (fin is None or x[0] < fin)]
    if not t:
        return {"trades": 0}
    r = np.array([x[2] for x in t])
    mois = pd.Series(r, index=pd.DatetimeIndex([x[0] for x in t])).resample("MS").sum()
    courbe = np.cumsum(r)
    dd = float((np.maximum.accumulate(np.concatenate([[0], courbe]))[1:] - courbe).max())
    nb_mois = max(1, (t[-1][0] - t[0][0]).days / 30.4)
    perte_suite, s = 0, 0
    for x in r:
        s = s + 1 if x < 0 else 0
        perte_suite = max(perte_suite, s)
    return {"trades": len(t), "gagnants_pct": round(100 * float((r > 0).mean()), 1), "R_moyen": round(float(r.mean()), 3),
            "R_total": round(float(r.sum()), 1), "trades_mois": round(len(t) / nb_mois, 1),
            "R_mois": round(float(r.sum()) / nb_mois, 2), "pire_baisse_R": round(dd, 1),
            "mois_positifs_pct": round(100 * float((mois > 0).mean()), 0), "pertes_de_suite_max": perte_suite}


def melanger(d, graine):
    mid = (d.close_bid + d.close_ask) / 2
    r = np.random.default_rng(graine).permutation(np.log(mid).diff().fillna(0).to_numpy())
    k = mid.iloc[0] * np.exp(np.cumsum(r)) / mid.to_numpy()
    d = d.copy()
    for c in [c for c in d.columns if c != "volume"]:
        d[c] = d[c] * k
    return d


def ligne(nom, s):
    if not s.get("trades"):
        return f"| {nom} | 0 | | | | | | |"
    return (f"| {nom} | {s['trades']} ({s['trades_mois']}/mois) | {s['gagnants_pct']} % | {s['R_moyen']:+.3f} | "
            f"{s['R_total']:+.1f} | {s['R_mois']:+.2f} | {s['pire_baisse_R']} | {s['mois_positifs_pct']:.0f} % |")


def images(d, trades, dossier, nb=4, boite=None, unite_txt="15 min"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dossier.mkdir(parents=True, exist_ok=True)
    choisis = [x for x in trades if x[4] == "objectif"][-2:] + [x for x in trades if x[4] == "stop"][-1:] + \
              [x for x in trades if x[4] == "heure"][-1:]
    fichiers = []
    for n, (t, sens, r, j, raison, stop, obj) in enumerate(choisis[:nb], 1):
        i = d.index.get_loc(t)
        a, b = max(0, i - (40 if boite is None else 44)), min(len(d), j + 8)
        g = d.iloc[a:b]
        fig, ax = plt.subplots(figsize=(10, 5), dpi=110)
        fig.patch.set_facecolor("#0b0f0c")
        ax.set_facecolor("#0b0f0c")
        for k, (_, row) in enumerate(g.iterrows()):
            o = (row.open_bid + row.open_ask) / 2
            c = row.mid
            col = "#2ecc71" if c >= o else "#e74c3c"
            ax.plot([k, k], [row.lo, row.hi], color=col, lw=1)
            ax.add_patch(plt.Rectangle((k - 0.35, min(o, c)), 0.7, max(abs(c - o), PIP / 10), color=col))
        ax.plot(range(len(g)), g.ema20.to_numpy(), color="#3498db", lw=1, label="EMA 20")
        ax.plot(range(len(g)), g.ema50.to_numpy(), color="#9b59b6", lw=1, label="EMA 50")
        if boite is not None:
            jour_t = d.jour.iat[i]
            dans = [k for k in range(len(g)) if g.jour.iat[k] == jour_t and boite[0] <= g.heure.iat[k] < boite[1]]
            if dans:
                bh = g.hi.iloc[dans].max()
                bl = g.lo.iloc[dans].min()
                ax.add_patch(plt.Rectangle((dans[0] - 0.5, bl), len(dans), bh - bl, color="#f1c40f", alpha=0.12,
                                           label="boîte 1 h - 9 h"))
        ie, js = i + 1 - a, j - a
        ent = d.open_ask.iat[i + 1] if sens > 0 else d.open_bid.iat[i + 1]
        ax.hlines(ent, ie, js, colors="#f1c40f", lw=1.5, label="entrée")
        ax.hlines(stop, ie, js, colors="#e74c3c", lw=1.5, linestyles="--", label="stop")
        if obj is not None:
            ax.hlines(obj, ie, js, colors="#2ecc71", lw=1.5, linestyles="--", label="objectif")
        ax.annotate("ACHAT" if sens > 0 else "VENTE", (ie, ent), color="white", fontsize=11,
                    xytext=(ie - 6, ent + (8 if sens > 0 else -8) * PIP), arrowprops=dict(color="white", arrowstyle="->"))
        heures = [x.tz_localize("UTC").tz_convert("Europe/Paris").strftime("%H:%M") for x in g.index]
        pas = max(1, len(g) // 10)
        ax.set_xticks(range(0, len(g), pas))
        ax.set_xticklabels(heures[::pas], color="#9fb3a4", fontsize=8)
        ax.tick_params(axis="y", colors="#9fb3a4", labelsize=8)
        jour = t.tz_localize("UTC").tz_convert("Europe/Paris").strftime("%d/%m/%Y")
        ax.set_title(f"EUR/USD {unite_txt}, {jour} (heure de Paris) : {raison}, {r:+.2f} R après spread",
                     color="white", fontsize=11)
        ax.legend(facecolor="#0b0f0c", labelcolor="white", fontsize=8, loc="best")
        for s in ax.spines.values():
            s.set_color("#2a3a2e")
        f = dossier / f"exemple-{n}-{raison}.png"
        fig.tight_layout()
        fig.savefig(f, facecolor=fig.get_facecolor())
        plt.close(fig)
        fichiers.append(f.name)
    return fichiers


def principal():
    dossier, md, js = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    img = Path(sys.argv[4]) if len(sys.argv) > 4 else None
    sortie = {"cree": pd.Timestamp.now(tz="UTC").isoformat(), "unites": {}}
    lignes = ["# Trading manuel EUR/USD : quelle stratégie rapide tient la route ?", "",
              "Labo du 28/11/2026, bougies Capital.com démo (prix acheteur et vendeur : vrai spread payé), "
              "aucune position gardée la nuit. Résultats en **R** (1 R = la somme risquée sur un trade, "
              "par exemple 1 € avec 1 % de risque sur 100 €).", "",
              "Anti-triche : signal sur bougie clôturée, entrée à la bougie suivante, stop compté en premier si "
              "stop et objectif tombent dans la même bougie, réglages choisis sur la 1re période et jugés sur la "
              "2e (jamais vue), contrôle sur prix mélangés.", ""]
    meilleur_global = None
    for unite in ("MINUTE_15", "MINUTE_5"):
        brut = lire(dossier, EPIC, unite)
        if brut is None or len(brut) < 2000:
            lignes += [f"## {unite} : pas de données", ""]
            continue
        d = preparer(brut)
        debut, fin = d.index.min(), d.index.max()
        coupe = debut + (fin - debut) * PART_CHOIX
        spread = float(((d.close_ask - d.close_bid) / PIP).median())
        lignes += [f"## Bougies {unite.replace('MINUTE_', '')} min : {debut:%d/%m/%Y} au {fin:%d/%m/%Y}", "",
                   f"Spread médian : {spread:.2f} pips. Période de choix : jusqu'au {coupe:%d/%m/%Y}, "
                   f"période de test (jamais vue) : ensuite."]
        res = {}
        for nom, f in variantes():
            tr = f(d)
            res[nom] = (tr, stats(tr, None, coupe), stats(tr, coupe, None))
        # tri sur la période de CHOIX seulement
        ordre = sorted(res, key=lambda k: res[k][1].get("R_total", -1e9) if res[k][1].get("trades", 0) >= 30 else -1e9,
                       reverse=True)
        lignes += ["", "### Période de choix (tri par R total)", "",
                   "| Variante | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs |",
                   "|---|---|---|---|---|---|---|---|"]
        for k in ordre:
            lignes.append(ligne(k, res[k][1]))
        lignes += ["", "### Période de test jamais vue (même ordre)", "",
                   "| Variante | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs |",
                   "|---|---|---|---|---|---|---|---|"]
        for k in ordre:
            lignes.append(ligne(k, res[k][2]))
        # meilleure de chaque famille sur le choix, jugée sur le test + prix mélangés
        lignes += ["", "### Meilleure variante de chaque famille (choisie sur la 1re période)", ""]
        sortie["unites"][unite] = {"spread_pips": spread, "coupe": str(coupe), "familles": {}}
        for fam in "ABCD":
            ks = [k for k in ordre if k.startswith(fam)]
            if not ks:
                continue
            k = ks[0]
            fn = dict(variantes())[k]
            mel = [stats(fn(preparer(melanger(brut, g))), coupe, None) for g in (1, 2, 3)]
            r_mel = np.mean([m.get("R_moyen", 0) for m in mel])
            c, t = res[k][1], res[k][2]
            lignes += [f"- **{k}** : choix {c.get('R_moyen', 0):+.3f} R/trade ({c.get('trades', 0)} trades), "
                       f"**test {t.get('R_moyen', 0):+.3f} R/trade** ({t.get('trades', 0)} trades, "
                       f"{t.get('gagnants_pct', 0)} % gagnants, {t.get('R_mois', 0):+.2f} R/mois, "
                       f"mois positifs {t.get('mois_positifs_pct', 0):.0f} %), prix mélangés {r_mel:+.3f} R/trade."]
            sortie["unites"][unite]["familles"][fam] = {"variante": k, "choix": c, "test": t, "melange_R_moyen": r_mel}
            score = (t.get("R_moyen", -9), unite, k)
            if t.get("trades", 0) >= 20 and (meilleur_global is None or score[0] > meilleur_global[0]):
                meilleur_global = (score[0], unite, k, d, res[k][0])
        lignes.append("")
        sortie["unites"][unite]["toutes"] = {k: {"choix": res[k][1], "test": res[k][2]} for k in ordre}
    # ----- stratégie retenue pour la fiche (choisie pour sa régularité sur les 2 unités, pas sur le seul test)
    brut = lire(dossier, EPIC, "MINUTE_15")
    if brut is not None:
        d = preparer(brut)
        tr = cassure(d, ("1:00", "9:00"), "13:00", "17:30", "autre bord", 1.5, 40)
        debut, fin = d.index.min(), d.index.max()
        coupe = debut + (fin - debut) * PART_CHOIX
        tout = stats(tr)
        lignes += ["## Stratégie de la fiche : Cassure de Londres (boîte 1 h - 9 h, stop autre bord, objectif 1,5 R), 15 min", "",
                   "| Période | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs | Pertes de suite max |",
                   "|---|---|---|---|---|---|---|---|---|"]
        semestres = pd.date_range(debut.normalize().replace(day=1), fin + pd.Timedelta(days=183), freq="6MS")
        for a_, b_ in zip(semestres[:-1], semestres[1:]):
            st = stats(tr, a_, b_)
            if st.get("trades"):
                lignes.append(f"| {a_:%m/%Y} - {(b_ - pd.Timedelta(days=1)):%m/%Y} | {st['trades']} | {st['gagnants_pct']} % | "
                              f"{st['R_moyen']:+.3f} | {st['R_total']:+.1f} | {st['R_mois']:+.2f} | {st['pire_baisse_R']} | "
                              f"{st['mois_positifs_pct']:.0f} % | {st['pertes_de_suite_max']} |")
        lignes.append(f"| **Tout** | {tout['trades']} | {tout['gagnants_pct']} % | {tout['R_moyen']:+.3f} | {tout['R_total']:+.1f} | "
                      f"{tout['R_mois']:+.2f} | {tout['pire_baisse_R']} | {tout['mois_positifs_pct']:.0f} % | {tout['pertes_de_suite_max']} |")
        # tailles de boîte et de stop (en pips) pour calculer la taille de position à la main
        boites, stops = [], []
        for x in tr:
            i = d.index.get_loc(x[0])
            ent = d.open_ask.iat[i + 1] if x[1] > 0 else d.open_bid.iat[i + 1]
            stops.append(abs(ent - x[5]) / PIP)
        jours_ok = sum(1 for _ in tr)
        nb_jours = d.jour.nunique()
        raisons = pd.Series([x[4] for x in tr]).value_counts().to_dict()
        heures = pd.Series([x[0].tz_localize("UTC").tz_convert("Europe/Paris").hour for x in tr]).value_counts().sort_index().to_dict()
        lignes += ["", f"Stop moyen {np.mean(stops):.1f} pips (médiane {np.median(stops):.1f}, 10 % des trades > "
                   f"{np.percentile(stops, 90):.1f}). Trade pris {jours_ok} jours sur {nb_jours} jours de cotation. "
                   f"Sorties : {raisons}. Heure du signal (Paris) : {heures}.", ""]
        mel = [stats(cassure(preparer(melanger(brut, g)), ("1:00", "9:00"), "13:00", "17:30", "autre bord", 1.5, 40)) for g in (1, 2, 3, 4, 5)]
        lignes += [f"Prix mélangés (5 tirages) : R moyen {', '.join(f'{m.get(chr(82) + '_moyen', 0):+.3f}' for m in mel)}.", ""]
        sortie["fiche"] = {"tout": tout, "stop_pips_median": float(np.median(stops)), "stop_pips_p90": float(np.percentile(stops, 90)),
                           "sorties": raisons, "heures": heures, "melange": mel}
        if img is not None:
            sortie["images"] = images(d, tr, img, boite=(1, 9))
        sortie["derniers_trades"] = [
            {"date_paris": x[0].tz_localize("UTC").tz_convert("Europe/Paris").strftime("%d/%m/%Y %H:%M"),
             "sens": "achat" if x[1] > 0 else "vente", "R": round(x[2], 2), "sortie": x[4]} for x in tr[-15:]]
    if meilleur_global:
        _, unite, k, d, tr = meilleur_global
        lignes += ["## Meilleure sur période jamais vue (attention : ce choix-là regarde le test)", "",
                   f"{k} en {unite}.", ""]
        sortie["meilleure"] = {"unite": unite, "variante": k}
    md.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    js.write_text(json.dumps(sortie, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("\n".join(lignes))


if __name__ == "__main__":
    principal()

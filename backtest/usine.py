"""USINE À STRATÉGIES (26/11/2026, demande de Mathis : « étendre la fouille beaucoup plus loin »).

Elle fabrique et teste automatiquement des dizaines de milliers de stratégies sur tous les marchés de Capital.com,
puis ne garde que celles qui gagnent aussi sur des années de prix JAMAIS VUES pendant la fabrication.

Une stratégie = déclencheur × filtre × sens × stop × objectif × suiveur × durée max × unité de temps
(les briques sont dans bot/usine_regles.py, les mêmes que le bot utilise en démo) : ~45 800 combinaisons par marché
et par unité de temps (4 h et jour).

Découpage du temps (fixe, décidé AVANT de lancer) :
  - ENTRAÎNEMENT  : début de l'historique (~2017) -> 31/12/2021. Seule période qui sert à choisir.
  - VALIDATION    : 01/01/2022 -> 30/06/2024. Jamais vue pendant le choix.
  - TEST FINAL    : 01/07/2024 -> aujourd'hui. Jamais vue non plus.

Contre la « chance » (tester des milliers d'idées en fait toujours gagner quelques-unes par hasard) :
  1. Entraînement : au moins 30 trades (20 en jour), facteur de profit >= 1,2, t-stat >= 2.
  2. Robustesse : au moins 70 % des réglages VOISINS (un cran de plus ou de moins) gagnent aussi. Une stratégie qui
     ne marche qu'avec un réglage précis est un coup de chance.
  3. Jamais vu : gagne en validation ET au test final, sur au moins 60 % des années, et les voisins aussi.
  4. Frais réels (spread bid/ask de Capital.com, frais de nuit, prime du stop garanti) puis TEST DE STRESS :
     spread et frais de nuit x 1,5, elle doit rester gagnante.
  5. Pénalité du nombre d'essais : « Deflated Sharpe Ratio » (Bailey et López de Prado, 2014) sur les mois jamais
     vus, avec le nombre de stratégies réellement différentes essayées. >= 0,95 = « solide ».

Usage :
  python backtest/usine.py telecharger <dossier>            (GitHub Actions, avec les clés de la démo)
  python backtest/usine.py fouiller <dossier> <EPIC> <sortie.json>
  python backtest/usine.py bilan <dossier_resultats> <sortie.json>
"""
import itertools
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bot import usine_regles as R  # noqa: E402

DEBUT_VALIDATION = pd.Timestamp("2022-01-01")
DEBUT_TEST = pd.Timestamp("2024-07-01")
PRIME_PCT = 0.1  # prime du stop garanti (Capital.com), payée quand il est touché
MARCHES = ("GOLD,SILVER,PLATINUM,PALLADIUM,COPPER,OIL_CRUDE,OIL_BRENT,NATURALGAS,"
           "US500,US100,US30,RTY,DE40,UK100,FR40,EU50,J225,HK50,AU200,"
           "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,USDCHF,NZDUSD,EURGBP,EURJPY,GBPJPY,"
           "BTCUSD,ETHUSD,SOLUSD,XRPUSD,LTCUSD,"
           "AAPL,MSFT,NVDA,TSLA,AMZN,META,GOOGL")
DEJA_PRIS = {"GOLD", "SILVER", "ETHUSD", "BTCUSD"}  # marchés déjà tradés par le bot (ou retirés : BTC)
NORM = NormalDist()


# =========================================================================== 1. données
def telecharger(dossier: Path):
    from backtest import telecharger as t
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    for numero, epic in enumerate([e.strip() for e in os.getenv("EPICS", MARCHES).split(",") if e.strip()]):
        if numero and numero % 6 == 0:  # la session Capital.com expire après 10 min sans renouvellement
            api.deconnexion()
            api.connexion()
        try:
            (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
        except Exception as e:
            print(f"{epic} : marché introuvable ({str(e)[:120]})")
            continue
        for unite, minutes in (("HOUR_4", 240), ("DAY", 1440)):
            try:
                t.telecharger(api, epic, unite, minutes, 3650)
            except Exception as e:
                print(f"{epic} {unite} : échec ({str(e)[:120]})")
    api.deconnexion()


def lire(dossier: Path, epic: str, unite: str):
    f = dossier / f"{epic}_{unite}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["date"] = pd.to_datetime(d.date, utc=True).dt.tz_localize(None)
    d = d.dropna(subset=["close_bid"]).set_index("date").sort_index()
    d = d[~d.index.duplicated()]
    ecart = (d.close_ask - d.close_bid).median()
    if not ecart == ecart:  # aucun prix acheteur : spread inconnu, marché ignoré
        return None
    for x in ("open", "high", "low", "close"):  # l'historique ancien n'a parfois que le prix vendeur
        d[f"{x}_ask"] = d[f"{x}_ask"].fillna(d[f"{x}_bid"] + ecart)
    return d.astype(float, errors="ignore")


def conditions(dossier: Path, epic: str, prix: float) -> dict:
    p = dossier / f"{epic}_marche.json"
    m = json.loads(p.read_text()) if p.exists() else {}
    inst, regles = m.get("instrument", {}), m.get("dealingRules", {})
    nuit = inst.get("overnightFee", {})
    g = regles.get("minGuaranteedStopDistance", {})
    if g.get("unit") == "PERCENTAGE":
        mini = float(g["value"])
    elif g.get("value"):
        mini = float(g["value"]) / prix * 100
    else:
        mini = 0.25
    return {"nuit_achat": -float(nuit.get("longRate", -0.02) or 0), "nuit_vente": -float(nuit.get("shortRate", -0.02) or 0),
            "min_pct": mini, "devise": inst.get("currency", "USD"), "nom": inst.get("name", epic),
            "taille_min": float(regles.get("minDealSize", {}).get("value", 1) or 1)}


class Prix:
    """Colonnes en listes Python (boucle rapide), avec un multiplicateur de frais pour le test de stress."""

    def __init__(self, df: pd.DataFrame, ind: R.Indicateurs, cond: dict, cout: float = 1.0):
        mid = {k: ((df[f"{k}_bid"] + df[f"{k}_ask"]) / 2).values for k in ("open", "high", "low", "close")}
        demi = {k: ((df[f"{k}_ask"] - df[f"{k}_bid"]) / 2).values * cout for k in ("open", "high", "low", "close")}
        self.ob, self.oa = list(mid["open"] - demi["open"]), list(mid["open"] + demi["open"])
        self.hb, self.ha = list(mid["high"] - demi["high"]), list(mid["high"] + demi["high"])
        self.lb, self.la = list(mid["low"] - demi["low"]), list(mid["low"] + demi["low"])
        self.cb, self.ca = list(mid["close"] - demi["close"]), list(mid["close"] + demi["close"])
        self.mh, self.ml, self.mc = list(mid["high"]), list(mid["low"]), list(mid["close"])
        self.atr = list(ind.atr.values)
        t = df.index.values.astype("datetime64[s]").astype(np.int64)
        pas = np.median(np.diff(t)) if len(t) > 1 else 86400
        t2 = np.r_[t[1:], t[-1] + pas]
        jour = lambda x: np.floor((x - 22 * 3600) / 86400)  # frais de nuit : à chaque passage de 22 h UTC
        self.nuits = list((jour(t2) - jour(t)).clip(0, 4))
        self.nuit_achat, self.nuit_vente = cond["nuit_achat"] / 100 * cout, cond["nuit_vente"] / 100 * cout
        self.min_pct = cond["min_pct"] / 100
        self.dates = df.index


def simuler(P: Prix, voulu, signaux, dstop, dobj, ksuiv, duree, i0, i1):
    """Une position à la fois. signaux : indices (triés) des bougies avec une entrée permise. Renvoie [(i_entree, R)].
    Ordre dans une bougie : sortie sur signal (à l'ouverture), stop garanti, objectif, puis suiveur à la clôture."""
    ob, oa, hb, ha, lb, la, cb, ca = P.ob, P.oa, P.hb, P.ha, P.lb, P.la, P.cb, P.ca
    mh, ml, mc, atr, nuits = P.mh, P.ml, P.mc, P.atr, P.nuits
    trades = []
    k = int(np.searchsorted(signaux, i0 - 1))
    ns = len(signaux)
    while k < ns:
        s = signaux[k]
        i = s + 1
        if i >= i1:
            break
        pos = voulu[s]
        entree = oa[i] if pos > 0 else ob[i]
        dist = max(dstop[s], entree * P.min_pct)
        stop = entree - dist * pos
        o = dobj[s]
        obj = entree + o * pos if o == o else None
        meilleur, frais, taux = entree, 0.0, (P.nuit_achat if pos > 0 else P.nuit_vente)
        j, fin = i, None
        while j < i1:
            if j > i and (voulu[j - 1] != pos or (duree and j - i >= duree)):
                px = ob[j] if pos > 0 else oa[j]
                trades.append((i, ((px - entree) * pos - frais) / dist))
                fin = j - 1  # un nouveau signal sur la bougie précédente peut être pris tout de suite (retournement)
                break
            if (lb[j] <= stop) if pos > 0 else (ha[j] >= stop):
                trades.append((i, ((stop - entree) * pos - frais - abs(stop) * PRIME_PCT / 100) / dist))
                fin = j
                break
            if obj is not None and ((hb[j] >= obj) if pos > 0 else (la[j] <= obj)):
                px = max(obj, ob[j]) if pos > 0 else min(obj, oa[j])
                trades.append((i, ((px - entree) * pos - frais) / dist))
                fin = j
                break
            if nuits[j]:
                frais += nuits[j] * mc[j] * taux
            if ksuiv:
                if pos > 0:
                    meilleur = max(meilleur, mh[j])
                    cible = min(meilleur - ksuiv * atr[j], mc[j] * (1 - P.min_pct))
                    stop = max(stop, cible)
                else:
                    meilleur = min(meilleur, ml[j])
                    cible = max(meilleur + ksuiv * atr[j], mc[j] * (1 + P.min_pct))
                    stop = min(stop, cible)
            j += 1
        if fin is None:  # fin de la période : clôturée au dernier prix
            px = cb[i1 - 1] if pos > 0 else ca[i1 - 1]
            trades.append((i, ((px - entree) * pos - frais) / dist))
            break
        k = int(np.searchsorted(signaux, fin, side="left"))
    return trades


def stats(r) -> dict:
    r = np.asarray(r, dtype=float)
    n = len(r)
    if not n:
        return {"n": 0, "R": 0.0, "moy": 0.0, "t": 0.0, "pf": 0.0, "reussite": 0.0, "pire_baisse": 0.0}
    g, p = r[r > 0].sum(), -r[r < 0].sum()
    et = r.std(ddof=1) if n > 1 else 0.0
    c = np.r_[0, np.cumsum(r)]
    return {"n": n, "R": round(float(r.sum()), 2), "moy": round(float(r.mean()), 4),
            "t": round(float(r.mean() / et * math.sqrt(n)) if et > 0 else 0.0, 2),
            "pf": round(float(g / p) if p > 0 else 99.0, 3), "reussite": round(float((r > 0).mean() * 100), 1),
            "pire_baisse": round(float((c - np.maximum.accumulate(c)).min()), 2)}


# =========================================================================== 2. fouille d'un marché
def combinaisons():
    for fam, (_, grille, _) in R.FAMILLES.items():
        for pi in range(len(grille)):
            for fl, se in itertools.product(range(len(R.FILTRES)), range(len(R.SENS))):
                yield fam, pi, fl, se


def spec_de(cle) -> dict:
    fam, pi, fl, se, st, ob, su, du = cle
    return {"famille": fam, "p": list(R.FAMILLES[fam][1][pi]), "filtre": R.FILTRES[fl], "sens": R.SENS[se],
            "stop": R.STOPS[st], "objectif": R.OBJECTIFS[ob], "suiveur": R.SUIVEURS[su], "duree": R.DUREES[du]}


def voisins(cle):
    fam, pi, fl, se, st, ob, su, du = cle
    forme = R.FAMILLES[fam][2]
    coords = np.unravel_index(pi, forme)
    for axe in range(len(forme)):
        for d in (-1, 1):
            c = list(coords)
            c[axe] += d
            if 0 <= c[axe] < forme[axe]:
                yield (fam, int(np.ravel_multi_index(c, forme)), fl, se, st, ob, su, du)
    for pos, taille in ((4, len(R.STOPS)), (5, len(R.OBJECTIFS)), (6, len(R.SUIVEURS)), (7, len(R.DUREES))):
        for d in (-1, 1):
            v = list(cle)
            v[pos] += d
            if 0 <= v[pos] < taille:
                yield tuple(v)


def fouiller(dossier: Path, epic: str, sortie: Path, garder: int = 150):
    res = {"epic": epic, "essais": 0, "candidates": [], "unites": {}}
    for unite in R.UNITES:
        df = lire(dossier, epic, unite)
        if df is None or len(df) < 600 or df.index[0] > DEBUT_VALIDATION - pd.Timedelta(days=700):
            print(f"{epic} {unite} : historique trop court, ignoré")
            continue
        t0 = time.time()
        cond = conditions(dossier, epic, float(df.close_bid.iloc[-1]))
        ind = R.Indicateurs(df)
        P = Prix(df, ind, cond)
        iv = int(np.searchsorted(df.index.values, DEBUT_VALIDATION.to_datetime64()))
        n = len(df)
        mini = 30 if unite == "HOUR_4" else 20
        a = ind.atr.values
        cache = {}  # (fam, pi, fl, se) -> (voulu, signaux)
        distances = {(st, ob): (list(R.STOPS[st] * a), list(R.OBJECTIFS[ob] * R.STOPS[st] * a) if R.OBJECTIFS[ob]
                                else [float("nan")] * len(a))
                     for st in range(len(R.STOPS)) for ob in range(len(R.OBJECTIFS))}

        def jouer(cle, i0, i1, PP=P):
            fam, pi, fl, se, st, ob, su, du = cle
            if (fam, pi, fl, se) not in cache:
                sp = spec_de(cle)
                voulu, ok, _, _ = R.preparer(ind, sp)
                sig = np.nonzero(ok & (voulu != 0) & np.isfinite(a))[0]
                cache[(fam, pi, fl, se)] = (list(voulu), sig)
            voulu, sig = cache[(fam, pi, fl, se)]
            dstop, dobj = distances[(st, ob)]
            return simuler(PP, voulu, sig, dstop, dobj, R.SUIVEURS[su], R.DUREES[du], i0, i1)

        # --- Entraînement : toutes les combinaisons
        entr = {}
        for base in combinaisons():
            for st, ob, su, du in itertools.product(range(len(R.STOPS)), range(len(R.OBJECTIFS)),
                                                    range(len(R.SUIVEURS)), range(len(R.DUREES))):
                cle = (*base, st, ob, su, du)
                tr = jouer(cle, 200, iv)
                entr[cle] = stats([x[1] for x in tr])
            cache.pop(base, None)
        res["essais"] += len(entr)
        bons = [c for c, s in entr.items() if s["n"] >= mini and s["pf"] >= 1.2 and s["t"] >= 2.0]
        robustes = []
        for c in bons:
            v = [entr[x] for x in voisins(c) if x in entr]
            ok = [x for x in v if x["n"] >= mini // 2 and x["moy"] > 0]
            if len(v) >= 3 and len(ok) / len(v) >= 0.7:
                robustes.append(c)
        robustes.sort(key=lambda c: -entr[c]["t"])
        choisies = robustes[:garder]
        print(f"{epic} {unite} : {len(entr)} essais, {len(bons)} gagnantes à l'entraînement, {len(robustes)} robustes, "
              f"{len(choisies)} envoyées au jamais vu ({time.time() - t0:.0f} s)")
        res["unites"][unite] = {"essais": len(entr), "gagnantes": len(bons), "robustes": len(robustes),
                                "debut": str(df.index[0])[:10], "fin": str(df.index[-1])[:10], "bougies": n}

        # --- Jamais vu : validation + test final, stress x 1,5, voisins
        P15 = Prix(df, ind, cond, 1.5)
        dates = df.index
        med_dist = float(np.nanmedian(a[iv:]))
        for c in choisies:
            tr = jouer(c, iv, n)
            r = [x[1] for x in tr]
            d = [dates[x[0]] for x in tr]
            val = [x for x, y in zip(r, d) if y < DEBUT_TEST]
            tst = [x for x, y in zip(r, d) if y >= DEBUT_TEST]
            mois, annees = {}, {}
            for x, y in zip(r, d):
                mois[y.strftime("%Y-%m")] = mois.get(y.strftime("%Y-%m"), 0.0) + x
                annees[str(y.year)] = annees.get(str(y.year), 0.0) + x
            stress = stats([x[1] for x in jouer(c, iv, n, P15)])
            vo = [stats([x[1] for x in jouer(v, iv, n)]) for v in voisins(c)]
            sp = spec_de(c)
            res["candidates"].append({
                "epic": epic, "unite": unite, "spec": sp, "texte": R.decrire(sp),
                "entrainement": entr[c], "validation": stats(val), "test": stats(tst), "jamais_vu": stats(r),
                "stress": stress, "mois": {k: round(v, 3) for k, v in mois.items()},
                "annees": {k: round(v, 2) for k, v in annees.items()},
                "voisins_jamais_vu_positifs": round(sum(1 for x in vo if x["R"] > 0) / max(1, len(vo)), 2),
                "risque_taille_min": round(cond["taille_min"] * R.STOPS[c[4]] * med_dist, 4),
                "devise": cond["devise"], "nom": cond["nom"]})
            cache.clear() if len(cache) > 400 else None
        print(f"{epic} {unite} : jamais vu calculé ({time.time() - t0:.0f} s)")
    sortie.write_text(json.dumps(res, ensure_ascii=False))


# =========================================================================== 3. bilan (tous les marchés)
def esperance_max(n: int, variance: float) -> float:
    """Meilleur Sharpe attendu PAR HASARD parmi n essais indépendants sans aucun avantage (Bailey & López de Prado)."""
    if n <= 1:
        return 0.0
    g = 0.5772156649
    return math.sqrt(variance) * ((1 - g) * NORM.inv_cdf(1 - 1 / n) + g * NORM.inv_cdf(1 - 1 / (n * math.e)))


def deflated_sharpe(x: np.ndarray, sr0: float) -> float:
    t = len(x)
    if t < 3 or x.std(ddof=1) == 0:
        return 0.0
    sr = x.mean() / x.std(ddof=1)
    z = (x - x.mean()) / x.std(ddof=0)
    g3, g4 = float((z ** 3).mean()), float((z ** 4).mean())
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr ** 2
    return float(NORM.cdf((sr - sr0) * math.sqrt(t - 1) / math.sqrt(max(den, 1e-6))))


def taux_eur(devise: str) -> float:
    return {"EUR": 1.0, "USD": 1.08, "GBP": 0.85, "JPY": 165.0, "CHF": 0.95, "CAD": 1.5, "AUD": 1.65}.get(devise, 1.08)


def bilan(dossier: Path, sortie: Path, capital: float = 93.0):
    fichiers = sorted(dossier.glob("*.json"))
    tous = [json.loads(f.read_text()) for f in fichiers]
    essais = sum(r["essais"] for r in tous)
    cands = [c for r in tous for c in r["candidates"]]
    fin = max((max(c["mois"]) for c in cands if c["mois"]), default="2026-11")
    mois = pd.period_range("2022-01", fin, freq="M").strftime("%Y-%m").tolist()
    for c in cands:
        c["_serie"] = np.array([c["mois"].get(m, 0.0) for m in mois])
    # nombre de stratégies RÉELLEMENT différentes envoyées au jamais vu : groupes de séries corrélées (> 0,5) par marché
    groupes = 0
    for epic in {c["epic"] for c in cands}:
        reps = []
        for c in sorted([c for c in cands if c["epic"] == epic], key=lambda c: -c["entrainement"]["t"]):
            s = c["_serie"]
            if s.std() == 0:
                continue
            if not any(abs(np.corrcoef(s, r)[0, 1]) > 0.5 for r in reps):
                reps.append(s)
        groupes += len(reps)
    srs = [c["_serie"].mean() / c["_serie"].std(ddof=1) for c in cands if c["_serie"].std() > 0]
    variance = float(np.var(srs)) if len(srs) > 1 else 0.0
    sr0 = esperance_max(max(groupes, 1), variance)
    for c in cands:
        s = c["_serie"]
        c["dsr"] = round(deflated_sharpe(s, sr0), 3)
        an = [v for v in c["annees"].values()]
        c["annees_positives"] = round(sum(1 for v in an if v > 0) / max(1, len(an)), 2)
        risque_eur = c["risque_taille_min"] / taux_eur(c["devise"])
        c["risque_taille_min_eur"] = round(risque_eur, 2)
        c["faisable"] = risque_eur <= capital * 0.02
        c["controles"] = {
            "validation_gagnante": c["validation"]["n"] >= 8 and c["validation"]["R"] > 0,
            "test_final_gagnant": c["test"]["n"] >= 6 and c["test"]["R"] > 0,
            "60_pct_annees_gagnantes": c["annees_positives"] >= 0.6,
            "voisins_gagnants_jamais_vu": c["voisins_jamais_vu_positifs"] >= 0.6,
            "stress_frais_x1_5": c["stress"]["R"] > 0,
            "pire_baisse_ok": c["jamais_vu"]["pire_baisse"] > -20,
        }
        c["passe"] = all(c["controles"].values())
        c["solide"] = c["passe"] and c["dsr"] >= 0.95
        del c["_serie"]
    passent = sorted([c for c in cands if c["passe"]], key=lambda c: -c["dsr"])
    solides = [c for c in passent if c["solide"]]
    # une seule par marché (la meilleure), sur un marché libre, faisable avec le petit compte
    retenues, vus = [], set()
    for c in solides:
        if c["epic"] in vus or c["epic"] in DEJA_PRIS or not c["faisable"]:
            continue
        vus.add(c["epic"])
        retenues.append(c)
    resume = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "periodes": {"entrainement": "début -> 2021-12-31", "validation": "2022-01-01 -> 2024-06-30",
                     "test_final": "2024-07-01 -> fin"},
        "marches": len(tous), "essais": essais, "envoyees_jamais_vu": len(cands),
        "groupes_differents": groupes, "sharpe_mensuel_du_hasard": round(sr0, 3),
        "passent_controles": len(passent), "solides": len(solides), "retenues": len(retenues),
        "par_marche": {r["epic"]: r["unites"] for r in tous},
        "retenues_liste": retenues,
        "meilleures_50": passent[:50],
        "meilleures_sans_controle": sorted(cands, key=lambda c: -c["dsr"])[:30],
    }
    sortie.write_text(json.dumps(resume, ensure_ascii=False, indent=1))
    print(f"{len(tous)} marchés, {essais} stratégies essayées, {len(cands)} envoyées au jamais vu "
          f"({groupes} vraiment différentes), {len(passent)} passent les contrôles, {len(solides)} solides, "
          f"{len(retenues)} retenues. Sharpe mensuel du hasard : {sr0:.3f}")
    for c in passent[:25]:
        print(f"  {'SOLIDE ' if c['solide'] else '       '}{c['epic']:<10} {c['unite']:<6} DSR {c['dsr']:.2f}  "
              f"entr {c['entrainement']['R']:+7.1f} R  valid {c['validation']['R']:+6.1f} R  test {c['test']['R']:+6.1f} R "
              f"({c['jamais_vu']['n']} tr.)  stress {c['stress']['R']:+6.1f}  {c['texte']}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "telecharger":
        telecharger(Path(sys.argv[2]))
    elif cmd == "fouiller":
        fouiller(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), int(os.getenv("GARDER", "150")))
    elif cmd == "bilan":
        bilan(Path(sys.argv[2]), Path(sys.argv[3]))

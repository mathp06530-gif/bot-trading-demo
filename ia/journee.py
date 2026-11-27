"""STRATÉGIE MAISON « JOURNÉE » (27/11/2026, idée de Mathis : notre propre stratégie, de gros trades ouverts ET
fermés dans la journée pour ne jamais payer de frais de nuit, avec du levier). Aucun ordre : labo seulement.

Briques (toutes trouvées par NOS labos, rien de copié) :
  - le vote des 14 cerveaux (ia/multi_labo.py) sur bougies 15 min, cible = sens à 1 h, walk-forward mensuel ;
  - on n'entre qu'à un moment où sa confiance est dans ses x % plus hautes (seuil pris sur le passé seulement) ;
  - filtre optionnel « accord 4 h » : le vote 4 h (piste confirmée sur années jamais vues) va dans le même sens ;
  - 1 trade par marché et par jour, fenêtre d'entrée en heures UTC ;
  - sortie : stop suiveur en ATR 15 min, objectif/stop, ou clôture forcée à 21 h 45 UTC (avant les frais de nuit
    de 22 h UTC) : AUCUNE position gardée la nuit ;
  - + le « tiroir » fin de séance US100 / US500 à l'envers (règle fixe confirmée), 15 min, même journée.
Coûts : vrai spread (achat au prix acheteur, vente au prix vendeur). Pas de frais de nuit puisque tout est fermé avant.

Anti-triche : réglages choisis AVANT CHOIX_FIN, jugés après ; tout refait sur prix mélangés.
Portefeuille : levier x1 / x3 / x5 / x10 sur un capital partagé entre les marchés, intérêts composés, pire baisse,
mois négatifs, risque de ruine (2000 années tirées au hasard dans les vraies journées).

Usage : python ia/journee.py tester <dossier_prix> <EPIC> <sortie.json>
        python ia/journee.py bilan <dossier_resultats> <sortie.md> <sortie.json>
"""
import json
import os
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("LABO_H", "4")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ia.multi_labo as L  # noqa: E402

CHOIX_FIN = pd.Timestamp(os.getenv("JOURNEE_CHOIX_FIN", "2025-07-01"))
COUV = (0.02, 0.05, 0.1)
FILTRES = ("aucun", "accord_4h")
FENETRES = {"7h-19h UTC": (7, 19), "13h-19h UTC (séance US)": (13, 19)}
SORTIES = [("suiveur", 1.0), ("suiveur", 2.0), ("suiveur", 3.0), ("cloture", None), ("objectif", (1.5, 3.0))]
FERMETURE = 21.75  # 21 h 45 UTC : tout est fermé avant les frais de nuit de 22 h UTC
FIN_SEANCE = {"US100": (15.5, 22.0), "US500": (15.5, 22.0)}  # heures de Paris
GRAINE = 7
LEVIERS = (1, 3, 5, 10)


def nom_sortie(s):
    g, p = s
    if g == "suiveur":
        return f"stop suiveur {p} ATR"
    if g == "cloture":
        return "garder jusqu'à 21 h 45 UTC"
    return f"stop {p[0]} ATR / objectif {p[1]} ATR"


def melanger(d, graine):
    mid = (d.close_bid + d.close_ask) / 2
    r = np.random.default_rng(graine).permutation(np.log(mid).diff().fillna(0).to_numpy())
    k = mid.iloc[0] * np.exp(np.cumsum(r)) / mid.to_numpy()
    d = d.copy()
    for c in [c for c in d.columns if c != "volume"]:
        d[c] = d[c] * k
    return d


def vote(dossier, epic, d, unite, minutes, h, mois_chauffe, debut_min=None):
    L.H = h
    L.PURGE = max(pd.Timedelta(hours=2), pd.Timedelta(minutes=(h + 1) * minutes))
    f = L.preparer(d, minutes, croix=L.croises(dossier, epic, unite, d.index), epic=epic)
    debut = (f.index.min() + pd.DateOffset(months=mois_chauffe)).normalize().replace(day=1)
    if debut_min is not None:  # pas besoin de prédire avant le début des bougies 15 min
        debut = max(debut, pd.Timestamp(debut_min).normalize().replace(day=1))
    bornes = [debut] + [b for b in pd.date_range(debut, f.index.max() + pd.Timedelta(days=31), freq="MS") if b > debut]
    P = L.cerveaux(f, list(zip(bornes[:-1], bornes[1:])))
    v = P.mean(axis=1)
    return v[P[L.APPRIS].notna().all(axis=1)]


def journees(d, q, seuil, q4, couv, filtre, fenetre, sortie):
    """Simule la stratégie sur un marché. q : vote 15 min (index = bougie), seuil : seuil de confiance passé."""
    idx = d.index
    cb, ca = d.close_bid.to_numpy(), d.close_ask.to_numpy()
    hb, ha, lb, la = d.high_bid.to_numpy(), d.high_ask.to_numpy(), d.low_bid.to_numpy(), d.low_ask.to_numpy()
    ob, oa = d.open_bid.to_numpy(), d.open_ask.to_numpy()
    mid = (cb + ca) / 2
    hm, lm = (hb + ha) / 2, (lb + la) / 2
    tr = np.r_[np.nan, np.maximum(hm[1:] - lm[1:], np.maximum(np.abs(hm[1:] - mid[:-1]), np.abs(lm[1:] - mid[:-1])))]
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    fin_bougie = idx + pd.Timedelta(minutes=15)
    h_fin = np.asarray(fin_bougie.hour + fin_bougie.minute / 60, float)
    h_deb = np.asarray(idx.hour + idx.minute / 60, float)
    jour = np.asarray(idx.normalize())
    qv, sv = q.reindex(idx).to_numpy(), seuil.reindex(idx).to_numpy()
    q4v = q4.reindex(idx).to_numpy() if q4 is not None else np.full(len(idx), np.nan)
    a, b = FENETRES[fenetre]
    trades, i, n = [], 0, len(idx)
    g, p = sortie
    while i < n - 1:
        ok = (a <= h_deb[i] < b) and qv[i] == qv[i] and sv[i] == sv[i] and abs(qv[i] - 0.5) >= sv[i] and atr[i] == atr[i]
        if ok and filtre == "accord_4h":
            ok = q4v[i] == q4v[i] and (q4v[i] > 0.5) == (qv[i] > 0.5)
        if not ok:
            i += 1
            continue
        sens = 1 if qv[i] > 0.5 else -1
        A = atr[i]
        ent = ca[i] if sens > 0 else cb[i]
        stop = obj = None
        if g == "suiveur":
            stop = ent - sens * p * A
        elif g == "objectif":
            stop, obj = ent - sens * p[0] * A, ent + sens * p[1] * A
        meilleur, j, sortie_px = ent, i, None
        while j + 1 < n:
            j += 1
            if jour[j] != jour[i] or (idx[j] - idx[j - 1]) > pd.Timedelta(hours=2):  # nouvelle journée / trou : sortie à l'ouverture
                sortie_px = ob[j] if sens > 0 else oa[j]
                break
            o_, h_, l_ = (ob[j], hb[j], lb[j]) if sens > 0 else (oa[j], ha[j], la[j])
            if stop is not None and ((sens > 0 and l_ <= stop) or (sens < 0 and h_ >= stop)):
                sortie_px = (min(o_, stop) if sens > 0 else max(o_, stop))
                break
            if obj is not None and ((sens > 0 and h_ >= obj) or (sens < 0 and l_ <= obj)):
                sortie_px = (max(o_, obj) if sens > 0 else min(o_, obj))
                break
            dernier = j + 1 >= n or jour[j + 1] != jour[i] or (idx[j + 1] - idx[j]) > pd.Timedelta(hours=2)
            if h_fin[j] >= FERMETURE or dernier:  # clôture forcée avant 22 h UTC ou avant la pause du marché
                sortie_px = cb[j] if sens > 0 else ca[j]
                break
            if g == "suiveur":
                c_ = cb[j] if sens > 0 else ca[j]
                meilleur = max(meilleur, c_) if sens > 0 else min(meilleur, c_)
                stop = meilleur - p * A if sens > 0 else meilleur + p * A
        if sortie_px is None:
            break
        trades.append((str(idx[i]), round(float(sens * (sortie_px - ent) / mid[i] * 100), 5)))
        # un seul trade par marché et par jour : on saute au jour suivant
        k = j
        while k < n and jour[k] == jour[i]:
            k += 1
        i = max(k, j + 1)
    return trades


def fin_seance(d, epic):
    """Tiroir fin de séance (règle fixe confirmée) : bougies de 21 h 30 et 21 h 45 Paris, contre le mouvement depuis 15 h 30."""
    o, c = FIN_SEANCE[epic]
    mid = (d.close_bid + d.close_ask) / 2
    loc = d.index.tz_localize("UTC").tz_convert("Europe/Paris")
    h = np.asarray(loc.hour + loc.minute / 60, float)
    jour = np.array([str(x) for x in loc.date])
    lm = np.log(mid.to_numpy())
    ouv = pd.Series(np.where(np.abs(h - o) < 1e-6, lm, np.nan)).groupby(jour).transform("first").to_numpy()
    cb, ca = d.close_bid.to_numpy(), d.close_ask.to_numpy()
    out = []
    for i in range(len(d) - 1):
        if not (c - 0.5 <= h[i] < c) or not ouv[i] == ouv[i] or (d.index[i + 1] - d.index[i]) > pd.Timedelta(minutes=30):
            continue
        dep = lm[i] - ouv[i]
        if dep == 0:
            continue
        sens = -1 if dep > 0 else 1
        ent, sor = (ca[i], cb[i + 1]) if sens > 0 else (cb[i], ca[i + 1])
        out.append((str(d.index[i]), round(float(sens * (sor - ent) / mid.iloc[i] * 100), 5)))
    return out


def tester(dossier, epic, sortie):
    from ia.predire import lire
    d15, d4 = lire(Path(dossier), epic, "MINUTE_15"), lire(Path(dossier), epic, "HOUR_4")
    if d15 is None or len(d15) < 20000:
        print(epic, ": pas assez de bougies 15 min")
        return
    out = {"epic": epic, "reel": {}, "melange": {}}
    for cle, a15, a4 in (("reel", d15, d4), ("melange", melanger(d15, GRAINE), melanger(d4, GRAINE) if d4 is not None else None)):
        q = vote(dossier, epic, a15, "MINUTE_15", 15, 4, 2)
        q4 = None
        if a4 is not None:
            v4 = vote(dossier, epic, a4, "HOUR_4", 240, 1, 15, debut_min=a15.index.min())
            # vote 4 h connu à la clôture de sa bougie : on l'aligne sur la fin de la bougie 15 min
            s4 = pd.Series(v4.to_numpy(), index=v4.index + pd.Timedelta(minutes=240)).sort_index()
            q4 = pd.Series(s4.reindex(q.index + pd.Timedelta(minutes=15), method="ffill").to_numpy(), index=q.index)
        conf = (q - 0.5).abs()
        res = {}
        for couv in COUV:
            seuil = conf.rolling(L.FEN_SEUIL, min_periods=500).quantile(1 - couv).shift(1)
            for filtre, fen, so in product(FILTRES, FENETRES, SORTIES):
                if filtre == "accord_4h" and q4 is None:
                    continue
                res[f"{couv}|{filtre}|{fen}|{nom_sortie(so)}"] = journees(a15, q, seuil, q4, couv, filtre, fen, so)
        if epic in FIN_SEANCE:
            res["_fin_seance"] = fin_seance(a15, epic)
        out[cle] = res
        print(epic, cle, "fait", len(res), "réglages")
    Path(sortie).write_text(json.dumps(out, ensure_ascii=False))


# --------------------------------------------------------------------------- bilan et portefeuille
def stats_trades(tr, debut=None, fin=None):
    t = [x for x in tr if (debut is None or x[0] >= str(debut)) and (fin is None or x[0] < str(fin))]
    if not t:
        return None
    g = np.array([x[1] for x in t])
    return {"n": len(g), "reussite": float((g > 0).mean()), "gain": float(g.mean())}


def portefeuille(trades_par_marche, levier, capital, debut, fin, n_places):
    """Capital partagé : chaque trade mise capital x levier / n_places ; composé jour par jour."""
    jours = {}
    for tr in trades_par_marche:
        for t, g in tr:
            ts = pd.Timestamp(t)
            if debut <= ts < fin:
                jours.setdefault(ts.normalize(), []).append(g)
    if not jours:
        return None
    s = pd.Series({k: sum(v) for k, v in jours.items()}).sort_index()
    r = s / 100 * levier / n_places  # rendement du capital ce jour-là
    r = r.clip(lower=-1)
    eq = capital * np.cumprod(1 + r.to_numpy())
    eq_s = pd.Series(eq, index=s.index)
    mois = (1 + r).groupby([r.index.year, r.index.month]).prod() - 1
    pic = np.maximum.accumulate(np.r_[capital, eq])
    dd = float(((np.r_[capital, eq] - pic) / pic).min() * 100)
    nmois = max(1.0, (s.index[-1] - s.index[0]).days / 30.44)
    rend_mois = (eq[-1] / capital) ** (1 / nmois) - 1 if eq[-1] > 0 else -1
    # risque de ruine : 2000 années (252 jours de bourse) tirées au hasard parmi les vraies journées
    rng = np.random.default_rng(1)
    rr = r.to_numpy()
    jours_an = int(round(len(rr) / max(1e-9, (s.index[-1] - s.index[0]).days / 365.25)))
    tir = rng.choice(rr, size=(2000, max(1, jours_an)))
    chemins = np.cumprod(1 + tir, axis=1)
    return {"final": round(float(eq[-1]), 2), "par_mois_eur_debut": round(float(capital * rend_mois), 2),
            "par_mois_pct": round(100 * rend_mois, 2), "pire_baisse_pct": round(dd, 1),
            "mois_negatifs": f"{int((mois < 0).sum())}/{len(mois)}",
            "ruine_50": round(float((chemins.min(axis=1) <= 0.5).mean() * 100), 1),
            "ruine_90": round(float((chemins.min(axis=1) <= 0.1).mean() * 100), 1),
            "an_median_pct": round(float((np.median(chemins[:, -1]) - 1) * 100), 1),
            "jours": len(s), "trades": int(sum(len(v) for v in jours.values()))}


def bilan(dossier, md, sortie_json):
    R = [json.loads(p.read_text()) for p in sorted(Path(dossier).glob("*.json"))]
    R = [r for r in R if r.get("reel")]
    cles = sorted({k for r in R for k in r["reel"] if not k.startswith("_")})
    fin = max(pd.Timestamp(x[0]) for r in R for k in r["reel"] for x in r["reel"][k]) + pd.Timedelta(days=1)
    debut = min(pd.Timestamp(x[0]) for r in R for k in r["reel"] for x in r["reel"][k])
    lignes = []
    for k in cles:
        tous = [x for r in R for x in r["reel"].get(k, [])]
        mel = [x for r in R for x in r["melange"].get(k, [])]
        ch, ju = stats_trades(tous, None, CHOIX_FIN), stats_trades(tous, CHOIX_FIN, None)
        lignes.append({"cle": k, "choix": ch, "juge": ju, "melange": stats_trades(mel),
                       "gagnants_juge": sum(1 for r in R if (stats_trades(r["reel"].get(k, []), CHOIX_FIN) or {"gain": 0})["gain"] > 0),
                       "marches": len(R)})
    # choix : meilleur gain TOTAL (gain moyen x nombre de trades) sur la période de choix, gain moyen > 0, >= 150 trades
    ok = [x for x in lignes if x["choix"] and x["choix"]["n"] >= 150 and x["choix"]["gain"] > 0]
    ok.sort(key=lambda x: -x["choix"]["gain"] * x["choix"]["n"])
    choisi = ok[0] if ok else None
    fs = {e: [r["reel"].get("_fin_seance", []) for r in R if r["epic"] == e] for e in FIN_SEANCE}
    fs_tr = [t for v in fs.values() for x in v for t in x]
    fs_mel = [t for r in R for t in r["melange"].get("_fin_seance", [])]
    f = lambda s: "—" if not s else f"{100 * s['reussite']:.1f} % · {s['gain']:+.4f} % · {s['n']} trades"  # noqa: E731
    out = ["# Stratégie maison « Journée » : gros trades ouverts et fermés dans la journée (aucun frais de nuit)", "",
           f"{len(R)} marchés, bougies 15 min Capital.com ({debut.date()} -> {fin.date()}). Réglages choisis avant le "
           f"{CHOIX_FIN.date()}, jugés après. Coûts : vrai spread. Toutes les positions fermées avant 22 h UTC.",
           f"Essais comptés : {len(cles)} réglages x {len(R)} marchés (réel + prix mélangés).", "",
           "| Réglage (part plus sûre · filtre · fenêtre · sortie) | Choix | Jugé (jamais vu) | Marchés gagnants (jugé) | Prix mélangés |",
           "|---|---|---|---|---|"]
    ok_j = sorted([x for x in lignes if x["choix"]], key=lambda x: -(x["choix"]["gain"] * x["choix"]["n"]))[:20]
    for x in ok_j:
        out.append(f"| {x['cle']}{' **(CHOISI)**' if x is choisi else ''} | {f(x['choix'])} | {f(x['juge'])} | "
                   f"{x['gagnants_juge']}/{x['marches']} | {f(x['melange'])} |")
    out += ["", f"Réglages gagnants sur la période de choix : {sum(1 for x in lignes if x['choix'] and x['choix']['gain'] > 0)} sur {len(lignes)}.",
            "", "## Tiroir fin de séance US100 / US500 (règle fixe)", "",
            f"Choix : {f(stats_trades(fs_tr, None, CHOIX_FIN))} · Jugé : {f(stats_trades(fs_tr, CHOIX_FIN, None))} · "
            f"Prix mélangés : {f(stats_trades(fs_mel))}", ""]
    port = {}
    if choisi:
        tr_m = [r["reel"].get(choisi["cle"], []) for r in R]
        places = len(R) + 2
        out += ["## Portefeuille (réglage choisi + tiroir fin de séance), période JAMAIS VUE seulement", "",
                f"Capital partagé : chaque trade mise capital x levier / {places} (au plus {places} positions en même temps). "
                "Intérêts composés. Ruine = tomber sous 50 % (ou 10 %) du capital au moins une fois dans l'année "
                "(2000 années tirées au hasard dans les vraies journées).", "",
                "| Levier | 100 € : par mois (1er mois) | 1 000 € : par mois (1er mois) | % par mois | Pire baisse | Mois négatifs | Année médiane | Risque -50 % | Risque -90 % |",
                "|---|---|---|---|---|---|---|---|---|"]
        for lev in LEVIERS:
            p1 = portefeuille(tr_m + [fs_tr], lev, 100.0, CHOIX_FIN, fin, places)
            p2 = portefeuille(tr_m + [fs_tr], lev, 1000.0, CHOIX_FIN, fin, places)
            if not p1:
                continue
            port[str(lev)] = p1
            out.append(f"| x{lev} | {p1['par_mois_eur_debut']:+.2f} € | {p2['par_mois_eur_debut']:+.2f} € | {p1['par_mois_pct']:+.2f} % | "
                       f"{p1['pire_baisse_pct']:.1f} % | {p1['mois_negatifs']} | {p1['an_median_pct']:+.1f} % | {p1['ruine_50']:.1f} % | {p1['ruine_90']:.1f} % |")
        mel_m = [r["melange"].get(choisi["cle"], []) for r in R]
        pm = portefeuille(mel_m, 5, 100.0, debut, fin, places)
        if pm:
            out += ["", f"Contrôle prix mélangés, même réglage, x5 : {pm['par_mois_pct']:+.2f} % par mois, pire baisse {pm['pire_baisse_pct']:.1f} %."]
    Path(md).write_text("\n".join(out) + "\n")
    Path(sortie_json).write_text(json.dumps({"lignes": lignes, "choisi": choisi and choisi["cle"], "portefeuille": port}, ensure_ascii=False))
    print("\n".join(out))


if __name__ == "__main__":
    a = sys.argv
    if a[1] == "tester":
        tester(a[2], a[3], a[4])
    else:
        bilan(a[2], a[3], a[4])

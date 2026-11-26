"""STRATÉGIES QUI GAGNENT SUR 2 MOIS (26/11/2026, demande de Mathis : « 10 ans c'est trop, essaie sur 2 mois »).

On reprend TOUTES les stratégies de l'usine (backtest/usine.py, bot/usine_regles.py : ~45 800 combinaisons par marché
et par unité de temps, 4 h et jour) sur les ~40 marchés Capital.com démo, mais on les juge sur une fenêtre courte :

  - A = les 2 DERNIERS MOIS (61 jours jusqu'à aujourd'hui)       -> c'est là qu'on choisit les gagnantes
  - B = les 2 mois d'AVANT (jamais vus pendant le choix)          -> est-ce que la gagnante gagnait déjà avant ?
  - C = les 2 mois encore avant (jamais vus non plus)             -> 3e contrôle pour celles qui gagnent A ET B

Le piège : sur 2 mois, avec des millions d'essais, des milliers de stratégies gagnent PAR HASARD. Le bilan montre
donc aussi, pour les meilleures de A, combien gagnaient aussi sur B (si c'est ~50 %, c'est du pile ou face).

Frais réels (spread bid/ask, frais de nuit, prime du stop garanti), et frais x 1,5 pour les finalistes.
1 R = la perte si le stop est touché = 1 % du capital avec le risque des stratégies expérimentales (~0,93 €).

Usage :
  python backtest/deux_mois.py telecharger <dossier>              (GitHub Actions, avec les clés de la démo)
  python backtest/deux_mois.py fouiller <dossier> <EPIC> <sortie.json>
  python backtest/deux_mois.py bilan <dossier_resultats> <sortie.json> <sortie.md>
"""
import itertools
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.usine import MARCHES, Prix, combinaisons, conditions, lire, simuler, spec_de, stats  # noqa: E402
from bot import usine_regles as R  # noqa: E402

FENETRE = pd.Timedelta(days=61)
MINI = {"HOUR_4": 4, "DAY": 2}  # trades minimum sur 2 mois pour être classée
OCCUPES = {"GOLD", "SILVER", "ETHUSD", "NATURALGAS", "TSLA", "US100", "BTCUSD"}  # déjà tradés par le bot (ou retiré)
EUR_PAR_R = 0.93  # 1 % de ~93 €


def telecharger(dossier: Path):
    from backtest import telecharger as t
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    for numero, epic in enumerate([e.strip() for e in os.getenv("EPICS", MARCHES).split(",") if e.strip()]):
        if numero and numero % 6 == 0:  # la session Capital.com expire après 10 min
            api.deconnexion()
            api.connexion()
        try:
            (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
        except Exception as e:
            print(f"{epic} : marché introuvable ({str(e)[:120]})")
            continue
        # assez d'historique pour chauffer les indicateurs (moyenne 200) avant les 6 mois testés
        for unite, minutes, jours in (("HOUR_4", 240, 500), ("DAY", 1440, 1000)):
            try:
                t.telecharger(api, epic, unite, minutes, jours)
            except Exception as e:
                print(f"{epic} {unite} : échec ({str(e)[:120]})")
    # 26/11 (demande de Mathis) : les PETITS marchés aussi (moins de concurrence) : liste de backtest/web_large.py
    from backtest.web_large import trouver_petits
    api.deconnexion()
    api.connexion()
    petits = trouver_petits(api, dossier)
    for numero, epic in enumerate(petits):
        if numero % 6 == 0:
            api.deconnexion()
            api.connexion()
        try:
            (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
            for unite, minutes, jours in (("HOUR_4", 240, 500), ("DAY", 1440, 1000)):
                t.telecharger(api, epic, unite, minutes, jours)
        except Exception as e:
            print(f"{epic} : échec ({str(e)[:120]})")
    api.deconnexion()


def fouiller_groupe(dossier: Path, categorie: str, sortie: Path):
    """Fouille tous les petits marchés d'une catégorie (liste trouvée au téléchargement)."""
    f = dossier / "petits_marches.json"
    petits = json.loads(f.read_text()) if f.exists() else {}
    sortie.mkdir(parents=True, exist_ok=True)
    for epic, cat in petits.items():
        if cat == categorie and (dossier / f"{epic}_HOUR_4.csv").exists():
            try:
                fouiller(dossier, epic, sortie / f"{epic}.json", categorie=cat)
            except Exception as e:
                print(f"{epic} : erreur ({str(e)[:200]})")


def melanger(df: pd.DataFrame, graine: int = 7) -> pd.DataFrame:
    """CONTRÔLE DU HASARD : mêmes bougies (même volatilité, même spread) mais dans un ordre tiré au sort, sur les
    6 derniers mois testés. Aucune stratégie ne peut y avoir de vrai avantage : ce qui « gagne » là gagne par chance."""
    d = df.copy()
    debut = int(np.searchsorted(d.index.values, (d.index[-1] - 3 * FENETRE).to_datetime64()))
    cb = d.close_bid.values
    prec = np.r_[cb[0], cb[:-1]]
    rel = {c: d[c].values / prec for c in d.columns if c.endswith(("_bid", "_ask"))}  # bougie relative à la clôture d'avant
    ordre = np.arange(len(d))
    rng = np.random.default_rng(graine)
    ordre[debut:] = rng.permutation(ordre[debut:])
    nouv = {c: np.empty(len(d)) for c in rel}
    base = cb[debut - 1] if debut else cb[0]
    for i in range(len(d)):
        j = ordre[i]
        if i < debut:
            for c in rel:
                nouv[c][i] = d[c].values[i]
            continue
        for c in rel:
            nouv[c][i] = rel[c][j] * base
        base = nouv["close_bid"][i]
    for c in rel:
        d[c] = nouv[c]
    return d


def fouiller(dossier: Path, epic: str, sortie: Path, garder: int = 120, categorie: str = "grands marchés"):
    res = {"epic": epic, "categorie": categorie, "unites": {}, "hasard": {}, "top_A": [], "tiennent": []}
    for unite, variante in itertools.product(R.UNITES, ("vrai", "melange")):
        df = lire(dossier, epic, unite)
        if df is None or len(df) < 300:
            print(f"{epic} {unite} : pas assez de données")
            continue
        if variante == "melange":
            df = melanger(df)
        t0 = time.time()
        fin = df.index[-1]
        debA, debB, debC = fin - FENETRE, fin - 2 * FENETRE, fin - 3 * FENETRE
        cond = conditions(dossier, epic, float(df.close_bid.iloc[-1]))
        ind = R.Indicateurs(df)
        P = Prix(df, ind, cond)
        n = len(df)
        i0 = max(201, int(np.searchsorted(df.index.values, debC.to_datetime64())))
        dates = df.index.values
        cA, cB = debA.to_datetime64(), debB.to_datetime64()
        a = ind.atr.values
        distances = {(st, ob): (list(R.STOPS[st] * a), list(R.OBJECTIFS[ob] * R.STOPS[st] * a) if R.OBJECTIFS[ob]
                                else [float("nan")] * len(a))
                     for st in range(len(R.STOPS)) for ob in range(len(R.OBJECTIFS))}
        cles, tab = [], []  # tab : R_A, n_A, R_B, n_B, R_C, n_C
        for base in combinaisons():
            fam, pi, fl, se = base
            sp = spec_de((*base, 0, 0, 0, 0))
            voulu, ok, _, _ = R.preparer(ind, sp)
            sig = np.nonzero(ok & (voulu != 0) & np.isfinite(a))[0]
            voulu = list(voulu)
            for st, ob, su, du in itertools.product(range(len(R.STOPS)), range(len(R.OBJECTIFS)),
                                                    range(len(R.SUIVEURS)), range(len(R.DUREES))):
                dstop, dobj = distances[(st, ob)]
                tr = simuler(P, voulu, sig, dstop, dobj, R.SUIVEURS[su], R.DUREES[du], i0, n)
                ligne = [0.0, 0, 0.0, 0, 0.0, 0]
                for i, r in tr:
                    k = 0 if dates[i] >= cA else (2 if dates[i] >= cB else 4)
                    ligne[k] += r
                    ligne[k + 1] += 1
                cles.append((fam, pi, fl, se, st, ob, su, du))
                tab.append(ligne)
        tab = np.array(tab, dtype=float)
        RA, nA, RB, nB, RC, nC = tab.T
        mini = MINI[unite]
        classee = nA >= mini
        # calibrage : parmi les meilleures de A, combien gagnaient aussi en B ?
        ordre = np.argsort(-np.where(classee, RA, -1e9))
        nb = int(classee.sum())
        paliers = {}
        for nom, part in (("top_0.1%", 0.001), ("top_1%", 0.01), ("top_10%", 0.1), ("toutes", 1.0)):
            idx = ordre[:max(1, int(nb * part))] if nb else []
            idx = [i for i in idx if classee[i]]
            if idx:
                paliers[nom] = {"nb": len(idx), "R_A_moy": round(float(RA[idx].mean()), 2),
                                "R_B_moy": round(float(RB[idx].mean()), 2),
                                "B_positif_pct": round(float((RB[idx] > 0).mean() * 100), 1)}
        gagnent_A = classee & (RA > 0)
        gagnent_AB = gagnent_A & (nB >= mini) & (RB > 0)
        res["hasard" if variante == "melange" else "unites"][unite] = {
            "essais": len(cles), "classees": nb, "gagnent_A": int(gagnent_A.sum()), "gagnent_A_et_B": int(gagnent_AB.sum()),
            "gagnent_A_B_C": int((gagnent_AB & (nC >= mini) & (RC > 0)).sum()), "paliers": paliers,
            "A": [str(debA)[:10], str(fin)[:16]], "B": [str(debB)[:10], str(debA)[:10]], "C": [str(debC)[:10], str(debB)[:10]]}
        if variante == "melange":
            print(f"{epic} {unite} prix mélangés : {int(gagnent_A.sum())} gagnent A, {int(gagnent_AB.sum())} A et B")
            continue
        P15 = Prix(df, ind, cond, 1.5)

        def detail(i):
            c = cles[i]
            sp = spec_de(c)
            voulu, ok, _, _ = R.preparer(ind, sp)
            sig = np.nonzero(ok & (voulu != 0) & np.isfinite(a))[0]
            dstop, dobj = distances[(c[4], c[5])]
            tr = simuler(P15, list(voulu), sig, dstop, dobj, R.SUIVEURS[c[6]], R.DUREES[c[7]], i0, n)
            rA = [r for j, r in tr if dates[j] >= cA]
            vA = [r for j, r in simuler(P, list(voulu), sig, dstop, dobj, R.SUIVEURS[c[6]], R.DUREES[c[7]], i0, n)
                  if dates[j] >= cA]
            return {"epic": epic, "unite": unite, "spec": sp, "texte": R.decrire(sp),
                    "A": round(float(RA[i]), 2), "nA": int(nA[i]), "B": round(float(RB[i]), 2), "nB": int(nB[i]),
                    "C": round(float(RC[i]), 2), "nC": int(nC[i]), "A_stats": stats(vA),
                    "A_frais_x1_5": round(float(sum(rA)), 2), "categorie": categorie, "devise": cond["devise"], "nom": cond["nom"]}

        res["top_A"] += [detail(i) for i in ordre[:garder] if classee[i]]
        idx = np.nonzero(gagnent_AB)[0]
        idx = idx[np.argsort(-(RA[idx] + RB[idx]))][:garder]
        res["tiennent"] += [detail(i) for i in idx]
        print(f"{epic} {unite} : {len(cles)} essais, {int(gagnent_A.sum())} gagnent A, {int(gagnent_AB.sum())} A et B "
              f"({time.time() - t0:.0f} s)")
    sortie.write_text(json.dumps(res, ensure_ascii=False))


def bilan(dossier: Path, sortie: Path, md: Path):
    tous = [json.loads(f.read_text()) for f in sorted(dossier.glob("*.json"))]
    essais = sum(u["essais"] for r in tous for u in r["unites"].values())
    classees = sum(u["classees"] for r in tous for u in r["unites"].values())
    gA = sum(u["gagnent_A"] for r in tous for u in r["unites"].values())
    gAB = sum(u["gagnent_A_et_B"] for r in tous for u in r["unites"].values())
    gABC = sum(u["gagnent_A_B_C"] for r in tous for u in r["unites"].values())
    h = {k: sum(u[k] for r in tous for u in r.get("hasard", {}).values())
         for k in ("classees", "gagnent_A", "gagnent_A_et_B", "gagnent_A_B_C")}
    # calibrage global (pondéré par le nombre de stratégies de chaque palier)
    calib = {}
    for nom in ("top_0.1%", "top_1%", "top_10%", "toutes"):
        p = [u["paliers"][nom] for r in tous for u in r["unites"].values() if nom in u["paliers"]]
        tot = sum(x["nb"] for x in p)
        if tot:
            calib[nom] = {"nb": tot, "R_A_moy": round(sum(x["R_A_moy"] * x["nb"] for x in p) / tot, 2),
                          "R_B_moy": round(sum(x["R_B_moy"] * x["nb"] for x in p) / tot, 2),
                          "B_positif_pct": round(sum(x["B_positif_pct"] * x["nb"] for x in p) / tot, 1)}
    top = sorted([c for r in tous for c in r["top_A"]], key=lambda c: -c["A"])
    tiennent = [c for r in tous for c in r["tiennent"]]

    def une_par_marche(liste, cle):
        vu, out = set(), []
        for c in sorted(liste, key=cle):
            if (c["epic"], c["unite"]) not in vu:
                vu.add((c["epic"], c["unite"]))
                out.append(c)
        return out

    top_marche = une_par_marche(top, lambda c: -c["A"])
    # « tiennent » : gagnent A et B ; classées par le moins bon des deux (une seule bonne fenêtre ne suffit pas)
    ten = une_par_marche(tiennent, lambda c: -min(c["A"], c["B"]))
    # C (jamais utilisée pour choisir) : est-ce que les « tiennent » gagnaient encore avant ?
    ten_toutes = [c for c in tiennent if c["nC"] >= MINI[c["unite"]]]
    c_pos = round(sum(1 for c in ten_toutes if c["C"] > 0) / max(1, len(ten_toutes)) * 100, 1)
    exemple = next(u for r in tous for u in r["unites"].values())
    out = {"essais": essais, "classees": classees, "gagnent_A": gA, "gagnent_A_et_B": gAB, "gagnent_A_B_C": gABC,
           "hasard_prix_melanges": h, "fenetres": {k: exemple[k] for k in ("A", "B", "C")}, "calibrage": calib,
           "tiennent_C_positif_pct": c_pos, "top_A_par_marche": top_marche[:30], "tiennent_par_marche": ten[:30],
           "marches": {r["epic"]: {u: {k: v[k] for k in ("essais", "gagnent_A", "gagnent_A_et_B", "gagnent_A_B_C")}
                                   for u, v in r["unites"].items()} for r in tous}}
    sortie.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    L = ["# Stratégies qui gagnent sur 2 mois (26/11/2026)", "",
         f"Fenêtres : A (choix) {exemple['A'][0]} -> {exemple['A'][1][:10]} ; B (jamais vue) {exemple['B'][0]} -> "
         f"{exemple['B'][1]} ; C (jamais vue) {exemple['C'][0]} -> {exemple['C'][1]}.", "",
         f"**{essais} stratégies essayées** (usine : ~45 800 combinaisons x {len(tous)} marchés x 4 h et jour), "
         f"{classees} avec assez de trades sur A.", "",
         f"- gagnent sur A (2 derniers mois) : **{gA}**",
         f"- gagnent sur A ET B : **{gAB}**",
         f"- gagnent sur A, B ET C : **{gABC}**", "",
         f"Contrôle du hasard (mêmes bougies tirées au sort, aucun avantage possible) : {h['classees']} classées, "
         f"{h['gagnent_A']} gagnent sur A, {h['gagnent_A_et_B']} sur A et B, {h['gagnent_A_B_C']} sur A, B et C.", "",
         "## Le test du hasard : les meilleures des 2 derniers mois gagnaient-elles avant ?", "",
         "| Groupe (classé sur A) | Nb | R moyen sur A | R moyen sur B | % qui gagnaient sur B |", "|---|---|---|---|---|"]
    for nom, x in calib.items():
        L.append(f"| {nom} | {x['nb']} | {x['R_A_moy']} | {x['R_B_moy']} | {x['B_positif_pct']} % |")
    L += ["", f"Parmi les stratégies qui gagnent sur A ET B, {c_pos} % gagnaient aussi sur C (2 mois encore avant).", "",
          "## Top par marché sur les 2 derniers mois (A), avec les 2 mois d'avant (B) et encore avant (C)", "",
          "| Marché | Unité | Stratégie | R sur A (trades) | A frais x1,5 | R sur B (trades) | R sur C (trades) |",
          "|---|---|---|---|---|---|---|"]
    for c in top_marche[:20]:
        L.append(f"| {c['epic']} | {c['unite']} | {c['texte']} | {c['A']} ({c['nA']}) | {c['A_frais_x1_5']} | "
                 f"{c['B']} ({c['nB']}) | {c['C']} ({c['nC']}) |")
    L += ["", "## Celles qui gagnent sur A ET B (classées par la moins bonne des deux), avec C", "",
          "| Marché | Unité | Stratégie | R sur A (trades) | R sur B (trades) | R sur C (trades) | A frais x1,5 |",
          "|---|---|---|---|---|---|---|"]
    for c in ten[:20]:
        L.append(f"| {c['epic']} | {c['unite']} | {c['texte']} | {c['A']} ({c['nA']}) | {c['B']} ({c['nB']}) | "
                 f"{c['C']} ({c['nC']}) | {c['A_frais_x1_5']} |")
    petits = [c for c in ten if c.get("categorie", "grands marchés") != "grands marchés"]
    L += ["", "## Petits marchés seulement (gagnent sur A ET B)", "",
          "| Catégorie | Marché | Unité | Stratégie | R sur A (trades) | R sur B (trades) | R sur C (trades) | A frais x1,5 |",
          "|---|---|---|---|---|---|---|---|"]
    for c in petits[:20]:
        L.append(f"| {c.get('categorie')} | {c['epic']} | {c['unite']} | {c['texte']} | {c['A']} ({c['nA']}) | "
                 f"{c['B']} ({c['nB']}) | {c['C']} ({c['nC']}) | {c['A_frais_x1_5']} |")
    L += ["", "## Avec plus de risque : gain et pire chute sur les 2 derniers mois (sans intérêts composés)", "",
          "| Marché | Stratégie | Risque 1 % | Risque 3 % | Risque 5 % |", "|---|---|---|---|---|"]
    for c in ten[:10]:
        g, b = c["A"], c["A_stats"]["pire_baisse"]
        L.append(f"| {c['epic']} {c['unite']} | {c['texte']} | " +
                 " | ".join(f"{g * k:+.0f} % (chute {b * k:.0f} %)" for k in (1, 3, 5)) + " |")
    out["petits_tiennent"] = petits[:30]
    sortie.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    L += ["", f"1 R ≈ {EUR_PAR_R} € avec 1 % de risque sur ~93 €."]
    md.write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "telecharger":
        telecharger(Path(sys.argv[2]))
    elif action == "fouiller":
        fouiller(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
    elif action == "fouiller_groupe":
        fouiller_groupe(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
    elif action == "bilan":
        bilan(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))

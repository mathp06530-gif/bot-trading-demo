"""TEST DU SIMULATEUR « MACHINE À REMONTER LE TEMPS » (bot/simulateur.py, idée du skill trader-timemachine), 26/11/2026.

Deux questions, sur la Cassure 4 h or + argent (la stratégie principale, 3 %), 10 ans de bougies Capital.com :

  1. CALIBRATION : à chaque entrée, le simulateur annonce « stop d'abord X % / gain de 2 R d'abord Y % » en
     30 bougies (5 jours), à partir des 600 bougies 4 h PRÉCÉDENTES seulement. On regarde ensuite ce que le vrai prix a
     fait. Quand il dit 60 %, est-ce que ça arrive ~60 % du temps ? Et fait-il mieux qu'une simple moyenne fixe
     (le taux de stop d'abord observé sur 2017-2021) ? Mesure : score de Brier (plus bas = meilleur).
  2. FILTRE D'ENTRÉE : n'ouvrir que si la part « objectif d'abord » parmi les cas tranchés dépasse un seuil.
     Seuil choisi sur 2017-2021 UNIQUEMENT, jugé sur 01/2022-06/2024 et 07/2024-aujourd'hui (jamais vus), nets de
     frais (spread, nuit, prime du stop garanti), contrôle frais x1,5, contrôle sur 30 jeux de prix au hasard,
     contrôle anti-lookahead. Même règle « tient » que backtest/formateurs.py.

Usage : python backtest/time_machine.py <dossier>   (données de backtest/usine.py telecharger, EPICS=GOLD,SILVER)
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.formateurs import COUPES, NOMS, periodes, prix_au_hasard  # noqa: E402
from backtest.formateurs import simuler as backtester  # noqa: E402
from backtest.usine import conditions, lire  # noqa: E402
from bot import simulateur as S  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402
from bot.strategie import milieu  # noqa: E402

DOSSIER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("donnees_usine")
POOL = 600
HORIZON = 30
TIRAGES = 2000
SEUILS = [0.0, 0.28, 0.31, 0.34, 0.37, 0.40]  # 0 = règle actuelle (pas de filtre) ; équilibre à 2 R = 0,333
N_HASARD = int(os.getenv("N_HASARD", "30"))


def prevision(df, cond, i, sens, sig=None, m=None):
    """Ce que le simulateur annonce à l'ouverture de la bougie i (entrée), avec les seules bougies d'avant."""
    if i - 1 - POOL < 1:
        return None
    sig = sig if sig is not None else signaux_cassure(df, entree=20, sortie=20, stop_atr=2.0)
    m = m if m is not None else milieu(df)
    o, h, l, cl = (m[k].values for k in ("open", "high", "low", "close"))
    heures = df.index.hour.values
    prix = o[i]
    dist = max(sig.stop.values[i - 1], prix * cond["min_pct"] / 100)
    stop, obj = prix - dist * sens, prix + 2 * dist * sens
    a = i - POOL  # bougies a-1 .. i-1 : toutes TERMINÉES avant l'entrée (ouverture de la bougie i)
    ratios, hr = S.paquet(o[a - 1:i], h[a - 1:i], l[a - 1:i], cl[a - 1:i], heures[a - 1:i])
    res = S.simuler(ratios, prix, sens, stop, obj, HORIZON, tirages=TIRAGES, graine=i, heures=hr,
                    heure_depart=(int(heures[i]) - 4) % 24, pas_h=4)
    return {**res, "stop": stop, "obj": obj}


def trades_et_previsions(e, df, cond, cout=1.0):
    sig = signaux_cassure(df, entree=20, sortie=20, stop_atr=2.0)
    c = sig.cible.values
    ok = np.r_[True, c[1:] != c[:-1]]
    t = backtester(df, c, ok, sig.stop.values, cond, cout=cout)
    m = milieu(df)
    o, h, l, cl = (m[k].values for k in ("open", "high", "low", "close"))
    heures = df.index.hour.values
    pos_de = {d: i for i, d in enumerate(df.index)}
    lignes = []
    for _, tr in t.iterrows():
        i = pos_de[tr.date]
        sens = int(tr.sens)
        res = prevision(df, cond, i, sens, sig=sig, m=m)
        if res is None:
            lignes.append((np.nan, np.nan, np.nan))
            continue
        stop, obj = res["stop"], res["obj"]
        # ce que le vrai prix a fait (mêmes règles : même bougie = stop)
        vrai = 0.0  # 0 = ni l'un ni l'autre
        for j in range(i, min(i + HORIZON, len(df))):
            ts = l[j] <= stop if sens > 0 else h[j] >= stop
            to = h[j] >= obj if sens > 0 else l[j] <= obj
            if ts:
                vrai = -1.0
                break
            if to:
                vrai = 1.0
                break
        lignes.append((res["p_stop"], res["p_objectif"], vrai))
    t[["p_stop", "p_obj", "vrai"]] = pd.DataFrame(lignes, index=t.index)
    t["epic"] = e
    return t


def tous(donnees, cout=1.0):
    t = pd.concat([trades_et_previsions(e, df, cond, cout) for e, df, cond in donnees], ignore_index=True)
    return t.dropna(subset=["p_stop"]).sort_values("date").reset_index(drop=True)


def part_objectif(t):
    return (t.p_obj / (t.p_obj + t.p_stop).clip(lower=1e-9)).values


def calibration(t):
    ent = t[t.date < COUPES[0]]
    jv = t[t.date >= COUPES[0]]
    base = float((ent.vrai == -1).mean())
    y = (jv.vrai == -1).astype(float).values
    brier_sim = float(np.mean((jv.p_stop.values - y) ** 2))
    brier_fixe = float(np.mean((base - y) ** 2))
    tranches = []
    for a, b in ((0, .45), (.45, .5), (.5, .55), (.55, .6), (.6, .65), (.65, 1.01)):
        x = jv[(jv.p_stop >= a) & (jv.p_stop < b)]
        if len(x):
            tranches.append({"annonce_stop_pct": f"{a * 100:.0f}-{min(b, 1) * 100:.0f}", "trades": len(x),
                             "annonce_moyenne": round(float(x.p_stop.mean()) * 100, 1),
                             "vrai_stop_pct": round(float((x.vrai == -1).mean()) * 100, 1)})
    return {"taux_stop_2017_2021": round(base * 100, 1), "brier_simulateur": round(brier_sim, 4),
            "brier_moyenne_fixe": round(brier_fixe, 4),
            "amelioration_pct": round((1 - brier_sim / brier_fixe) * 100, 2),
            "ecart_type_annonces_pct": round(float(jv.p_stop.std()) * 100, 1),
            "tranches_jamais_vu": tranches, "trades_jamais_vu": int(len(jv))}


def filtre(t, base_t):
    essais = {}
    for s in SEUILS:
        w = (part_objectif(t) >= s).astype(float) if s else np.ones(len(t))
        essais[str(s)] = periodes(t, w)
    base = essais["0.0"]
    choix = max((k for k in essais if k != "0.0"), key=lambda k: essais[k][0]["score"])
    r = essais[choix]
    tient = all(r[i]["score"] > base[i]["score"] for i in (1, 2)) \
        and r[1]["R"] + r[2]["R"] >= 0.9 * (base[1]["R"] + base[2]["R"])
    return choix, essais, bool(tient)


def principal():
    donnees = []
    for e in ("GOLD", "SILVER"):
        df = lire(DOSSIER, e, "HOUR_4")
        if df is None:
            print(f"{e} : pas de données")
            continue
        donnees.append((e, df, conditions(DOSSIER, e, float(df.close_bid.iloc[-1]))))
    print("Données :", {e: f"{df.index[0]:%d/%m/%Y} -> {df.index[-1]:%d/%m/%Y} ({len(df)} bougies)" for e, df, _ in donnees})

    # anti-lookahead : la prévision faite à l'entrée d'un trade est identique si on efface toutes les bougies
    # APRÈS l'ouverture de la bougie d'entrée (signal, stop et paquet de bougies compris)
    erreurs = 0
    e, df, cond = donnees[0]
    t_full = trades_et_previsions(e, df, cond).dropna(subset=["p_stop"])
    for _, tr in t_full.sample(min(10, len(t_full)), random_state=1).iterrows():
        k = df.index.get_loc(tr.date)
        coupe = df.iloc[: k + 1].copy()
        # la bougie d'entrée ne garde que son ouverture (haut, bas, clôture inconnus à ce moment)
        for cote in ("bid", "ask"):
            for x in ("high", "low", "close"):
                coupe.iloc[-1, coupe.columns.get_loc(f"{x}_{cote}")] = coupe[f"open_{cote}"].iat[-1]
        p = prevision(coupe, cond, k, int(tr.sens))
        if p is None or not np.isclose(p["p_stop"], tr.p_stop):
            erreurs += 1
    print("Contrôle lookahead (0 = aucune fuite) :", erreurs)

    t = tous(donnees)
    cal = calibration(t)
    print("\n1. CALIBRATION (jamais vu 2022 -> auj.)", json.dumps(cal, ensure_ascii=False, indent=1))

    choix, essais, tient = filtre(t, None)
    print(f"\n2. FILTRE (seuil choisi sur 2017-2021 : {choix})")
    print(f"{'':28s}" + "".join(f"{n:>30s}" for n in NOMS))
    for k, p in essais.items():
        print(f"seuil {k:22s}" + "".join(f"{x['R']:8.1f} R {x['trades']:4d} tr DD {x['pire_baisse_R']:6.1f}" for x in p))
    stress = None
    if tient:
        ts = tous(donnees, cout=1.5)
        _, ess_s, _ = filtre(ts, None)
        b, r = ess_s["0.0"], ess_s[choix]
        stress = r
        tient = all(r[i]["score"] > b[i]["score"] for i in (1, 2)) and r[1]["R"] + r[2]["R"] >= 0.9 * (b[1]["R"] + b[2]["R"])
    print("Tient sur les vrais prix (et frais x1,5) :", tient)

    hasard = 0
    for g in range(N_HASARD):
        dh = [(e, prix_au_hasard(df, 1000 * g + j), cond) for j, (e, df, cond) in enumerate(donnees)]
        _, _, th = filtre(tous(dh), None)
        hasard += int(th)
    hasard_pct = round(100 * hasard / N_HASARD, 1)
    print(f"Sur {N_HASARD} jeux de prix au hasard, le filtre « tient » {hasard_pct} % du temps")
    retenu = tient and hasard_pct <= 10
    print("FILTRE RETENU :", retenu)
    Path("backtest/resultats_time_machine.json").write_text(json.dumps(
        {"lookahead_erreurs": erreurs, "calibration": cal, "filtre": {"seuil_choisi": choix, "essais": essais,
         "frais_x1_5": stress, "tient": tient, "hasard_pct_tient": hasard_pct, "retenu": retenu}},
        indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

"""Règles de gestion des pertes vues chez des formateurs / traders connus (demande de Mathis, 26/11/2026).

Point de départ : le 25/11, 2 ventes Cassure 4 h (or et argent, 3 % chacune) ont fini au stop (-5,30 €).
Mathis a demandé de ne pas écarter les vendeurs de formation. Les règles concrètes qui reviennent le plus
souvent chez eux et qui se codent, testées ici sur la Cassure 4 h or + argent (la stratégie qui a perdu) :

  A. « Trade dans le sens de l'unité supérieure » : n'acheter que si le cours JOURNALIER est au-dessus de sa
     moyenne (EMA n jours), ne vendre que s'il est dessous (multi-unités, très répandu en formation).
  B. « Stop temps » : si le trade n'a pas décollé après N bougies, on sort (« un bon trade marche vite »).
  C. « Stop hors de portée des chasseurs de stops » : stop plus large (2,5 / 3 / 4 ATR) à risque égal en %.
  D. « Après k pertes d'affilée, divise ta taille par 2 » jusqu'au prochain gain.
  E. « Trade ta courbe de gains » (Tom Basso, Van Tharp…) : demi-taille quand la courbe de la stratégie
     est sous sa moyenne des N derniers trades.
  F. « Jamais de position le week-end » : sortie le vendredi soir.
  G. « Perte max par semaine » : plus de nouvelle entrée de la semaine après -L R sur la stratégie.
  H. « Pas deux fois le même pari » (règle des Turtles sur les marchés liés) : pas de 2e métal ouvert dans le
     même sens (au lieu de 3 % + 3 %). (La version 1,5 % chacun a déjà été rejetée : backtest/cassure_protection.py.)

Méthode (comme l'usine à stratégies) :
  - réglage de chaque idée choisi sur 2017 -> 31/12/2021 UNIQUEMENT (meilleur gain / pire baisse) ;
  - jugé sur 01/2022 -> 06/2024 (validation) et 07/2024 -> aujourd'hui (test), jamais vus ;
  - nets de frais (spread bid/ask, nuit, prime du stop garanti) + contrôle avec frais x1,5 ;
  - « tient » = meilleur gain/pire baisse que la règle actuelle sur les 2 périodes jamais vues, ET au moins
    90 % de son gain jamais vu, ET pareil avec frais x1,5 ;
  - contrôle anti-hasard : même procédure sur 30 jeux de prix ALÉATOIRES (rendements des bougies mélangés) ;
    une idée qui « tient » aussi souvent sur du hasard que sur les vrais prix ne vaut rien ;
  - contrôle anti-lookahead : chaque signal recalculé sur des données coupées doit être identique.

Usage : python backtest/formateurs.py <dossier>   (données de backtest/usine.py telecharger, EPICS=GOLD,SILVER)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.usine import conditions, lire  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402
from bot.strategie import milieu  # noqa: E402

DOSSIER = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("donnees_usine")
COUPES = (pd.Timestamp("2022-01-01"), pd.Timestamp("2024-07-01"))
NOMS = ("entraînement 2017-2021", "validation 2022-06/2024", "test 07/2024-auj.")
PRIME_PCT = 0.1
GARDE = (1.5, 0.5)  # règle actuelle : garder 50 % du meilleur gain après +1,5 R
N_HASARD = int(__import__("os").getenv("N_HASARD", "30"))


# --------------------------------------------------------------------------- filtres sans lookahead
def ema_jour_veille(df, n):
    """Pour chaque bougie 4 h : (clôture de la VEILLE, EMA n jours de la veille), calculés avec les seules
    bougies 4 h des jours déjà terminés (aucune information du jour en cours)."""
    m = milieu(df)
    jour = m.close.groupby(m.index.normalize()).last()
    e = jour.ewm(span=n, adjust=False, min_periods=n).mean()
    veille_c, veille_e = jour.shift(1), e.shift(1)
    cle = m.index.normalize()
    return veille_c.reindex(cle).values, veille_e.reindex(cle).values


def filtre_jour(df, c, n):
    vc, ve = ema_jour_veille(df, n)
    ok_achat = vc > ve
    ok_vente = vc < ve
    return np.where(c > 0, ok_achat, np.where(c < 0, ok_vente, True))


# --------------------------------------------------------------------------- simulateur
def simuler(df, voulu, ok, dstop, cond, duree=None, gmin=0.0, weekend=False, cout=1.0):
    """Une position à la fois (copie de backtest/serrage.simuler + stop temps et sortie du vendredi).
    Renvoie date d'entrée, date de sortie, sens, R net, raison."""
    ob, hb, lb, cb = (df[c].values for c in ("open_bid", "high_bid", "low_bid", "close_bid"))
    ec = {x: (df[f"{x}_ask"].values - df[f"{x}_bid"].values) * cout for x in ("open", "high", "low", "close")}
    oa, ha, la, ca = ob + ec["open"], hb + ec["high"], lb + ec["low"], cb + ec["close"]
    dates = df.index
    heures, minutes, jours = dates.hour.values, dates.minute.values, dates.dayofweek.values
    nuit_a, nuit_v = cond["nuit_achat"] * cout, cond["nuit_vente"] * cout
    trades, pos, sortir = [], 0, None
    for i in range(1, len(df)):
        if pos and (voulu[i - 1] != pos or sortir):
            px = ob[i] if pos > 0 else oa[i]
            trades.append((d_entree, dates[i], pos, ((px - entree) * pos - frais) / dist, sortir or "signal"))
            pos, sortir = 0, None
        if not pos and voulu[i - 1] and ok[i - 1] and dstop[i - 1] == dstop[i - 1]:
            pos = int(voulu[i - 1])
            entree = oa[i] if pos > 0 else ob[i]
            dist = max(dstop[i - 1], entree * cond["min_pct"] / 100)
            stop = entree - dist * pos
            meilleur, frais, d_entree, i_entree = entree, 0.0, dates[i], i
        if not pos:
            continue
        if (lb[i] <= stop) if pos > 0 else (ha[i] >= stop):
            frais += abs(stop) * PRIME_PCT / 100
            trades.append((d_entree, dates[i], pos, ((stop - entree) * pos - frais) / dist, "stop"))
            pos = 0
            continue
        mid = (cb[i] + ca[i]) / 2
        if heures[i] == 22 and minutes[i] == 0:
            frais += mid * (nuit_a if pos > 0 else nuit_v) / 100
        haut = (hb[i] + ha[i]) / 2 if pos > 0 else (lb[i] + la[i]) / 2
        meilleur = max(meilleur, haut) if pos > 0 else min(meilleur, haut)
        gain_max = (meilleur - entree) * pos / dist
        if gain_max >= GARDE[0]:
            cible = entree + GARDE[1] * (meilleur - entree)
            limite = mid - mid * cond["min_pct"] / 100 * pos
            cible = min(cible, limite) if pos > 0 else max(cible, limite)
            stop = max(stop, cible) if pos > 0 else min(stop, cible)
        gain = ((cb[i] if pos > 0 else ca[i]) - entree) * pos / dist
        if duree and i - i_entree + 1 >= duree and gain < gmin and gain_max < GARDE[0]:
            sortir = "stop temps"
        if weekend and jours[i] == 4 and heures[i] >= 16:
            sortir = "vendredi"
    return pd.DataFrame(trades, columns=["date", "fin", "sens", "R", "raison"])


# --------------------------------------------------------------------------- tailles (D, E, G, H)
def poids_pertes(t, k):
    """D : x0,5 après k pertes d'affilée (connues avant l'entrée), jusqu'au prochain gain."""
    w = np.ones(len(t))
    for j in range(len(t)):
        passes = t[t.fin <= t.date.iat[j]].sort_values("fin").R.values
        n = 0
        for r in passes[::-1]:
            if r > 0:
                break
            n += 1
        if n >= k:
            w[j] = 0.5
    return w


def poids_courbe(t, n):
    """E : x0,5 quand la courbe (trades déjà clos, à taille pleine) est sous sa moyenne des n derniers points."""
    w = np.ones(len(t))
    for j in range(len(t)):
        passes = t[t.fin <= t.date.iat[j]].sort_values("fin").R.values
        if len(passes) < n:
            continue
        c = np.cumsum(passes)
        if c[-1] < c[-n:].mean():
            w[j] = 0.5
    return w


def poids_semaine(t, limite):
    """G : plus d'entrée de la semaine (lundi-dimanche) après -limite R réalisés dans la semaine."""
    w = np.ones(len(t))
    for j in range(len(t)):
        d = t.date.iat[j]
        lundi = d.normalize() - pd.Timedelta(days=d.dayofweek)
        x = t[(t.fin <= d) & (t.fin >= lundi)]
        if (x.R.values * w[x.index.values]).sum() <= -limite:
            w[j] = 0.0
    return w


def poids_un_metal(t):
    """H : pas de 2e métal dans le même sens tant que le 1er est ouvert."""
    w = np.ones(len(t))
    for j in range(len(t)):
        x = t.iloc[j]
        autre = t[(t.index != t.index[j]) & (t.epic != x.epic) & (t.sens == x.sens)
                  & (t.date < x.date) & (t.fin > x.date)]
        if (w[autre.index.values] > 0).any():
            w[j] = 0.0
    return w


# --------------------------------------------------------------------------- évaluation
def periodes(t, w):
    t = t.assign(Rw=t.R.values * w).sort_values("date")
    r = []
    for a, b in ((None, COUPES[0]), (COUPES[0], COUPES[1]), (COUPES[1], None)):
        x = t
        if a is not None:
            x = x[x.date >= a]
        if b is not None:
            x = x[x.date < b]
        c = np.concatenate([[0], np.cumsum(x.Rw.values)])
        pb = float((c - np.maximum.accumulate(c)).min())
        r.append({"R": round(float(x.Rw.sum()), 2), "trades": int((x.Rw != 0).sum()),
                  "pire_baisse_R": round(pb, 2), "score": round(float(x.Rw.sum()) / max(abs(pb), 1.0), 3)})
    return r


def jeux_de(donnees):
    out = []
    for e, df, cond in donnees:
        out.append((e, df, cond))
    return out


def trades_variante(donnees, idee, p, cout=1.0):
    tous = []
    for e, df, cond in donnees:
        sa = p if idee == "C" else 2.0
        sig = signaux_cassure(df, entree=20, sortie=20, stop_atr=sa)
        c = sig.cible.values
        ok = np.r_[True, c[1:] != c[:-1]]
        if idee == "A":
            ok = ok & filtre_jour(df, c, p)
        kw = {}
        if idee == "B":
            kw = {"duree": p[0], "gmin": p[1]}
        if idee == "F":
            kw = {"weekend": True}
        t = simuler(df, c, ok, sig.stop.values, cond, cout=cout, **kw)
        t["epic"] = e
        tous.append(t)
    t = pd.concat(tous, ignore_index=True).sort_values("date").reset_index(drop=True)
    if idee == "D":
        w = poids_pertes(t, p)
    elif idee == "E":
        w = poids_courbe(t, p)
    elif idee == "G":
        w = poids_semaine(t, p)
    elif idee == "H":
        w = poids_un_metal(t)
    else:
        w = np.ones(len(t))
    return t, w


IDEES = {
    "A": ("tendance journalière (EMA n jours)", [20, 50, 100, 200]),
    "B": ("stop temps (N bougies, gain mini)", [(n, g) for n in (6, 12, 18, 30, 48) for g in (0.0, 0.5)]),
    "C": ("stop plus large (ATR)", [1.5, 2.5, 3.0, 4.0]),
    "D": ("demi-taille après k pertes d'affilée", [1, 2, 3]),
    "E": ("demi-taille sous la moyenne de la courbe (n trades)", [10, 20, 30]),
    "F": ("sortie le vendredi soir", [None]),
    "G": ("perte max par semaine (R)", [1.0, 1.5, 2.0, 3.0]),
    "H": ("un seul métal à la fois dans le même sens", [None]),
}


def etudier(donnees, avec_stress=True):
    t0, w0 = trades_variante(donnees, "base", None)
    base = periodes(t0, w0)
    base_s = periodes(*trades_variante(donnees, "base", None, cout=1.5)) if avec_stress else None
    res = {"actuelle": base}
    if avec_stress:
        res["actuelle frais x1,5"] = base_s
    verdicts = {}
    for idee, (nom, params) in IDEES.items():
        essais = {}
        for p in params:
            essais[str(p)] = periodes(*trades_variante(donnees, idee, p))
        choix = max(essais, key=lambda k: essais[k][0]["score"])  # choisi sur 2017-2021 seulement
        r = essais[choix]
        tient = all(r[i]["score"] > base[i]["score"] for i in (1, 2)) \
            and r[1]["R"] + r[2]["R"] >= 0.9 * (base[1]["R"] + base[2]["R"])
        stress = None
        if avec_stress and tient:
            p = params[[str(x) for x in params].index(choix)]
            stress = periodes(*trades_variante(donnees, idee, p, cout=1.5))
            tient = all(stress[i]["score"] > base_s[i]["score"] for i in (1, 2)) \
                and stress[1]["R"] + stress[2]["R"] >= 0.9 * (base_s[1]["R"] + base_s[2]["R"])
        verdicts[idee] = {"nom": nom, "reglage_choisi_2017_2021": choix, "resultat": r, "frais_x1_5": stress,
                          "tient": bool(tient), "tous_les_reglages": essais}
    return res, verdicts


# --------------------------------------------------------------------------- contrôles
def prix_au_hasard(df, graine):
    """Mélange les rendements clôture->clôture des bougies (garde la forme de chaque bougie et le spread) :
    plus aucune tendance réelle, même volatilité."""
    rng = np.random.default_rng(graine)
    m = milieu(df)
    r = np.diff(np.log(m.close.values))
    r = rng.permutation(r)
    close = m.close.values[0] * np.exp(np.r_[0, np.cumsum(r)])
    fac = close / m.close.values
    out = df.copy()
    for col in df.columns:
        if col.split("_")[0] in ("open", "high", "low", "close") and col.endswith(("_bid", "_ask")):
            out[col] = df[col].values * fac
    return out


def controle_lookahead(df):
    """Le filtre journalier et les signaux calculés sur des données coupées doivent être identiques."""
    rng = np.random.default_rng(1)
    erreurs = 0
    sig_full = signaux_cassure(df, entree=20, sortie=20)
    vc_full, ve_full = ema_jour_veille(df, 50)
    for k in rng.integers(2000, len(df) - 1, 15):
        sub = df.iloc[: k + 1]
        s = signaux_cassure(sub, entree=20, sortie=20)
        vc, ve = ema_jour_veille(sub, 50)
        if s.cible.iat[-1] != sig_full.cible.iat[k]:
            erreurs += 1
        if not (np.isclose(vc[-1], vc_full[k]) and np.isclose(ve[-1], ve_full[k])):
            erreurs += 1
    return erreurs


def principal():
    donnees = []
    for e in ("GOLD", "SILVER"):
        df = lire(DOSSIER, e, "HOUR_4")
        if df is None:
            print(f"{e} : pas de données")
            continue
        cond = conditions(DOSSIER, e, float(df.close_bid.iloc[-1]))
        donnees.append((e, df, cond))
    print("Données :", {e: f"{df.index[0]:%d/%m/%Y} -> {df.index[-1]:%d/%m/%Y} ({len(df)} bougies)" for e, df, _ in donnees})
    look = {e: controle_lookahead(df) for e, df, _ in donnees}
    print("Contrôle lookahead (0 = aucune fuite) :", look)

    res, verdicts = etudier(donnees)
    print(f"\n{'':52s}" + "".join(f"{n:>30s}" for n in NOMS))
    for nom, p in res.items():
        print(f"{nom:52s}" + "".join(f"{x['R']:8.1f} R {x['trades']:4d} tr DD {x['pire_baisse_R']:6.1f}" for x in p))
    for idee, v in verdicts.items():
        p = v["resultat"]
        print(f"{idee} {v['nom'][:38]:38s} [{v['reglage_choisi_2017_2021']:>10s}]"
              + "".join(f"{x['R']:8.1f} R {x['trades']:4d} tr DD {x['pire_baisse_R']:6.1f}" for x in p)
              + ("  <- TIENT" if v["tient"] else ""))

    hasard = {k: 0 for k in IDEES}
    for g in range(N_HASARD):
        dh = [(e, prix_au_hasard(df, 1000 * g + j), cond) for j, (e, df, cond) in enumerate(donnees)]
        _, vh = etudier(dh, avec_stress=False)
        for k, v in vh.items():
            hasard[k] += int(v["tient"])
    hasard = {k: round(100 * v / N_HASARD, 1) for k, v in hasard.items()}
    print(f"\nSur {N_HASARD} jeux de prix au hasard, % de fois où l'idée « tient » (sans le contrôle frais x1,5) :", hasard)

    retenues = [k for k, v in verdicts.items() if v["tient"] and hasard[k] <= 10]
    print("Retenues (tiennent sur les vrais prix ET rarement sur du hasard) :", retenues or "aucune")
    Path("backtest/resultats_formateurs.json").write_text(json.dumps(
        {"periodes": NOMS, "lookahead_erreurs": look, "base": res, "idees": verdicts,
         "hasard_pct_tient": hasard, "retenues": retenues}, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

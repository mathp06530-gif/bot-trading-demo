"""Vote 4 h confirmé, filtré par l'amplitude (k = 1, figé).

On garde le SENS du vote simple des 14 cerveaux, seulement sur ses 5 % de moments les plus
sûrs (même règle que ia/CONFIRMATION_4H.md). On retire un trade seulement quand le mouvement
médian prévu (quantile 50 %, passé seulement) est plus petit que le spread + les frais de nuit.

Comparaison sur les mêmes bougies :
  (a) vote 4 h seul
  (b) vote 4 h + filtre |médiane| >= 1 × coût

k = 1 est figé. La grille {1 ; 1,5 ; 2} n'est lue que sur la période de choix, puis jugée
après, sans remplacer le test principal.

Période de choix : 2021-11-27 -> 2024-11-27. Période jugée : après le 2024-11-27.
Prix : bougies 4 h reconstruites depuis Dukascopy (horaire, gratuit). Le spread facturé est
le spread médian Capital.com (ia/resultats.json), plus les frais de nuit moyens publiés.
Les bougies Capital.com ne sont pas dans le dépôt.

Hasard : 500 filtres qui retirent le même nombre de trades. Significatif s'il bat 95 % d'entre eux
sur la période jugée (même barre que ia/filtre_cassure.py).

Aucun ordre. Ne touche pas au bot.

Usage : python -m ia.vote4h_amplitude
"""
import json
import lzma
import os
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

os.environ["LABO_H"] = "1"
os.environ.setdefault("LABO_PISTES", "oui")

import ia.multi_labo as L  # noqa: E402
from ia.amplitude import MARCHES, NUIT_PCT, SPREAD_PCT  # noqa: E402
from ia.predire import lire  # noqa: E402

# Réglages figés avant la période jugée.
K_FIGE = 1.0
K_GRILLE = (1.0, 1.5, 2.0)
CHOIX_DEBUT = pd.Timestamp("2021-11-27")
CHOIX_FIN = pd.Timestamp("2024-11-27")  # début de la période jugée
PART = 0.05
HASARD_N = 500
HASARD_GRAINE = 0
MIN_TRAIN_Q = 500
ARBRES = 80
TRAIN_MAX = 8000
SAUT_HEURE = 0.15
CACHE = Path(os.getenv("VOTE4H_CACHE", "/tmp/vote4h_cache"))
DUKA = {
    "EURUSD": ("EURUSD", 1e5), "GBPUSD": ("GBPUSD", 1e5), "GOLD": ("XAUUSD", 1e3),
    "SILVER": ("XAGUSD", 1e3), "OIL_CRUDE": ("LIGHTCMDUSD", 1e3), "US500": ("USA500IDXUSD", 1e3),
    "US100": ("USATECHIDXUSD", 1e3), "DE40": ("DEUIDXEUR", 1e3),
}
def preparer_labo():
    """Réglages du vote 4 h confirmé. Appelé au calcul, pas à l'import (les tests ne doivent rien changer)."""
    L.H = 1
    L.NUIT = True
    L.PURGE = pd.Timedelta(hours=10)
    for epic, pct in NUIT_PCT.items():
        L.NUIT_PCT[epic] = pct


# --------------------------------------------------------------------------- décisions pures (testées sans réseau)
def cotes_vote(vote, q50, cout, top, k):
    """Sens du vote sur le top 5 %. Le filtre ne change pas le sens : il retire les petits mouvements prévus."""
    vote = np.asarray(vote, float)
    q50 = np.asarray(q50, float)
    cout = np.asarray(cout, float)
    top = np.asarray(top, bool)
    sens = np.where(vote > 0.5, 1, np.where(vote < 0.5, -1, 0))
    univers = top & np.isfinite(q50) & np.isfinite(vote) & np.isfinite(cout) & (sens != 0)
    seul = np.where(univers, sens, 0)
    filtre = np.where(univers & (np.abs(q50) >= k * cout), sens, 0)
    return seul, filtre


def mesurer(index, cote, mv, cout, debut, fin):
    """Gain = sens × mouvement − coût (spread + nuit), comme le labo. Une bougie = un instant."""
    m = (np.asarray(cote) != 0) & np.asarray(index >= debut) & np.asarray(index < fin)
    if m.sum() == 0:
        return None
    sens = np.asarray(cote)[m]
    mouvement = np.asarray(mv, float)[m]
    cout_m = np.asarray(cout, float)[m]
    g = sens * mouvement - cout_m
    juste = sens * mouvement > 0
    idx = pd.DatetimeIndex(np.asarray(index)[m])
    mois = idx.to_period("M")
    gm = pd.Series(g).groupby(np.asarray(mois)).sum()
    bornes = pd.DatetimeIndex(index)
    t0 = max(pd.Timestamp(debut), bornes.min())
    t1 = min(pd.Timestamp(fin), bornes.max())
    span = max((t1 - t0).days / 30.44, 1 / 30.44)
    hausses = float((mouvement > 0).mean())
    return {
        "n": int(m.sum()), "instants": int(len(idx.unique())),
        "reussite": round(float(juste.mean()), 4), "gain": round(float(g.mean()), 5),
        "gain_total": round(float(g.sum()), 4), "trades_par_mois": round(float(m.sum() / span), 2),
        "mois_positifs": int((gm > 0).sum()), "mois": int(len(gm)),
        "sens_majoritaire": round(float(max(hausses, 1 - hausses)), 4),
        "debut": str(idx.min()), "fin": str(idx.max()),
        "gains": [round(float(x), 6) for x in g], "temps": [str(t) for t in idx],
    }


def hasard(gains, garder, n=HASARD_N, graine=HASARD_GRAINE):
    """Part des filtres au hasard (même nombre de trades gardés) que le vrai filtre bat sur le gain moyen."""
    g = np.asarray(gains, float)
    garder = np.asarray(garder, bool)
    n_keep = int(garder.sum())
    if n_keep < 30 or n_keep >= len(g):
        return None
    reel = float(g[garder].mean())
    rng = np.random.default_rng(graine)
    idx = np.arange(len(g))
    hs = np.array([g[rng.choice(idx, size=n_keep, replace=False)].mean() for _ in range(n)])
    return {"gain": round(reel, 5), "hasard_median": round(float(np.median(hs)), 5),
            "mieux": round(float((hs < reel).mean()), 4), "n_gardes": n_keep, "n_total": int(len(g)), "n_hasard": n}


def verdict(a, b, mieux, melange_acc, choix_mieux):
    """confirmée / prometteuse / rejetée. a et b sont les résumés jugés (gain, marches_gagnants, reussite, sens_majoritaire)."""
    if melange_acc is not None and melange_acc > 0.53:
        return "rejetée"
    if not b or b.get("gain") is None or b["gain"] <= 0 or not a or not (b["gain"] > a["gain"]):
        return "rejetée"
    significatif = mieux is not None and mieux >= 0.95
    if (significatif and choix_mieux and b.get("marches_gagnants", 0) >= 5
            and b.get("reussite", 0) > b.get("sens_majoritaire", 1)):
        return "confirmée"
    return "prometteuse"


def choisir_k(lignes):
    """Meilleur k de la grille sur la période de choix seulement (gain du filtre). Ne remplace pas k = 1."""
    meilleur, k_choisi = None, None
    for k, gain, n in lignes:
        if n < 30:
            continue
        if k_choisi is None or gain > meilleur:
            meilleur, k_choisi = gain, k
    return k_choisi, meilleur


# --------------------------------------------------------------------------- données Dukascopy -> bougies 4 h
def _mois(symbole, an, mois, div):
    dest = CACHE / "bi5" / f"{symbole}_{an}_{mois:02d}.bi5"
    if not dest.exists() or dest.stat().st_size < 50:
        url = f"https://www.dukascopy.com/datafeed/{symbole}/{an}/{mois - 1:02d}/BID_candles_hour_1.bi5"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=40) as rep:
                brut = rep.read()
        except Exception:
            return []
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(brut)
    else:
        brut = dest.read_bytes()
    try:
        raw = lzma.decompress(brut)
    except Exception:
        dest.unlink(missing_ok=True)
        return []
    debut = datetime(an, mois, 1)
    lignes = []
    inverses = 0
    for i in range(0, len(raw) - 23, 24):
        t, o, c, lo, hi, vol = struct.unpack(">IIIIIf", raw[i:i + 24])
        if o <= 0 or c <= 0:
            continue
        if lo > hi:
            lo, hi = hi, lo
            inverses += 1
        ts = debut + pd.Timedelta(seconds=int(t))
        lignes.append((ts, o / div, hi / div, lo / div, c / div, float(vol)))
    return lignes


def telecharger_4h(epic):
    """Bougies 4 h (open/high/low/close/volume). Les heures qui sautent de plus de 15 % sont retirées."""
    cache = CACHE / f"{epic}_4h.pkl"
    if cache.exists():
        return pd.read_pickle(cache)
    symbole, div = DUKA[epic]
    taches = [(symbole, an, mois, div) for an in range(2016, 2027) for mois in range(1, 13)
              if (an, mois) <= (2026, 11)]
    lignes = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for morceau in pool.map(lambda x: _mois(*x), taches):
            lignes.extend(morceau)
    if not lignes:
        return None
    d = pd.DataFrame(lignes, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date").sort_index()
    d = d[~d.index.duplicated(keep="last")]
    r = d["close"].pct_change().abs()
    d = d.loc[~(r > SAUT_HEURE)]
    x = d.copy()
    x["seau"] = x.index.floor("4h")
    g = x.groupby("seau").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                              close=("close", "last"), volume=("volume", "sum"), n=("close", "size"))
    g = g[g["n"] >= 3].drop(columns="n")
    cache.parent.mkdir(parents=True, exist_ok=True)
    g.to_pickle(cache)
    print(f"{epic} : {len(g)} bougies 4 h, {g.index.min()} -> {g.index.max()}", flush=True)
    return g


def ecrire_csv(dossier, epic, d):
    """Format lu par ia.predire.lire, spread Capital.com constant autour du milieu."""
    demi = SPREAD_PCT[epic]["4h"] / 100 / 2
    out = pd.DataFrame(index=d.index)
    for col in ("open", "high", "low", "close"):
        out[f"{col}_bid"] = d[col] * (1 - demi)
        out[f"{col}_ask"] = d[col] * (1 + demi)
    out["volume"] = d["volume"].to_numpy()
    out.insert(0, "date", out.index.strftime("%Y-%m-%d %H:%M:%S"))
    path = Path(dossier)
    path.mkdir(parents=True, exist_ok=True)
    out.to_csv(path / f"{epic}_HOUR_4.csv", index=False)


def melanger_ohlc(d, graine):
    mid = d["close"].to_numpy(float)
    r = np.zeros(len(mid))
    r[1:] = np.diff(np.log(np.clip(mid, 1e-12, None)))
    rng = np.random.default_rng(graine)
    r[1:] = rng.permutation(r[1:])
    nouveau = mid[0] * np.exp(np.cumsum(r))
    k = nouveau / mid
    out = d.copy()
    for col in ("open", "high", "low", "close"):
        out[col] = d[col].to_numpy(float) * k
    return out


# --------------------------------------------------------------------------- modèles
def quantile_median(f):
    """Quantile 50 % du mouvement suivant, un modèle par mois, trou ≥ 4 h."""
    import lightgbm as lgb
    horizon = pd.Timedelta(hours=4)
    cols = [c for c in f.columns if c not in ("mv", "sp", "y", "er16", "vrel")]
    X = f[cols].to_numpy(dtype=np.float32)
    y = f["mv"].to_numpy(float)
    q = np.full(len(f), np.nan)
    debuts = pd.date_range(f.index.min().normalize().replace(day=1), f.index.max() + pd.Timedelta(days=32), freq="MS")
    for debut in debuts:
        fin = debut + pd.DateOffset(months=1)
        tr = np.where(f.index < debut - horizon)[0][-TRAIN_MAX:]
        te = np.where((f.index >= debut) & (f.index < fin))[0]
        if len(tr) < MIN_TRAIN_Q or not len(te):
            continue
        m = lgb.LGBMRegressor(objective="quantile", alpha=0.5, n_estimators=ARBRES, learning_rate=0.05,
                              num_leaves=15, min_child_samples=80, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0, n_jobs=1)
        m.fit(X[tr], y[tr])
        q[te] = m.predict(X[te])
    return q


def chaine(dossier, epic):
    """Vote des 14 cerveaux + quantile médian, sur les bougies 4 h du dossier."""
    d = lire(Path(dossier), epic, "HOUR_4")
    if d is None or len(d) < 2500:
        print(epic, "pas assez de bougies", flush=True)
        return None
    preparer_labo()
    f = L.preparer(d, 240, croix=L.croises(dossier, epic, "HOUR_4", d.index), epic=epic)
    debut = (f.index.min() + pd.DateOffset(months=18)).normalize().replace(day=1)
    bornes = [debut] + [b for b in pd.date_range(debut, f.index.max() + pd.Timedelta(days=31), freq="MS") if b > debut]
    P = L.cerveaux(f, list(zip(bornes[:-1], bornes[1:])))
    vote = np.array(P.mean(axis=1), dtype=float)
    vote[P[L.APPRIS].isna().any(axis=1).to_numpy()] = np.nan
    q50 = quantile_median(f)
    top = L.couverture(np.asarray(vote, float), PART)
    return {"index": f.index, "vote": vote, "q50": q50, "cout": f["sp"].to_numpy(float),
            "mv": f["mv"].to_numpy(float), "top": np.asarray(top, bool)}


def evaluer(res):
    """(a) vote seul et (b) vote filtré, sur le choix et sur le jugé, pour k figé et la grille."""
    if res is None:
        return None
    out = {"k": {}}
    for k in K_GRILLE:
        seul, filtre = cotes_vote(res["vote"], res["q50"], res["cout"], res["top"], k)
        out["k"][str(k)] = {}
        for nom, cote in (("a", seul), ("b", filtre)):
            out["k"][str(k)][nom] = {
                "choix": mesurer(res["index"], cote, res["mv"], res["cout"], CHOIX_DEBUT, CHOIX_FIN),
                "juge": mesurer(res["index"], cote, res["mv"], res["cout"], CHOIX_FIN, res["index"].max() + pd.Timedelta(days=1)),
            }
        # hasard sur la période jugée : même univers (le vote top 5 %), on retire le même nombre
        univers = seul != 0
        juge = np.asarray(res["index"] >= CHOIX_FIN) & np.asarray(res["index"] < res["index"].max() + pd.Timedelta(days=1))
        m = univers & juge
        if m.sum() >= 30:
            g = np.where(seul[m] > 0, res["mv"][m], -res["mv"][m]) - res["cout"][m]
            garder = filtre[m] != 0
            out["k"][str(k)]["hasard_juge"] = hasard(g, garder)
        else:
            out["k"][str(k)]["hasard_juge"] = None
        choix_m = univers & np.asarray(res["index"] >= CHOIX_DEBUT) & np.asarray(res["index"] < CHOIX_FIN)
        if choix_m.sum() >= 30:
            g = np.where(seul[choix_m] > 0, res["mv"][choix_m], -res["mv"][choix_m]) - res["cout"][choix_m]
            out["k"][str(k)]["hasard_choix"] = hasard(g, filtre[choix_m] != 0)
        else:
            out["k"][str(k)]["hasard_choix"] = None
    return out


def _sans_series(bloc):
    if not bloc:
        return None
    return {k: v for k, v in bloc.items() if k not in ("gains", "temps")}


def resumer_marches(par, k, periode, cle, min_n=1):
    lignes = []
    temps = []
    for epic, ev in par.items():
        if not ev:
            continue
        bloc = ev["k"][str(k)][cle][periode]
        if bloc and bloc["n"] >= min_n:
            lignes.append(bloc)
            temps.extend(bloc["temps"])
    if not lignes:
        return None
    return {
        "n": int(sum(x["n"] for x in lignes)),
        "instants": int(len(set(temps))),
        "instants_somme": int(sum(x["instants"] for x in lignes)),
        "reussite": round(float(np.mean([x["reussite"] for x in lignes])), 4),
        "gain": round(float(np.mean([x["gain"] for x in lignes])), 5),
        "trades_par_mois": round(float(np.mean([x["trades_par_mois"] for x in lignes])), 2),
        "sens_majoritaire": round(float(np.mean([x["sens_majoritaire"] for x in lignes])), 4),
        "marches_gagnants": int(sum(x["gain"] > 0 for x in lignes)),
        "marches": len(lignes),
        "mois_positifs": int(sum(x["mois_positifs"] for x in lignes)),
        "mois": int(sum(x["mois"] for x in lignes)),
    }


def hasard_groupe(par, k, periode):
    """Tous les trades jugés (ou de choix) ensemble : un filtre au hasard retire le même nombre, tous marchés confondus."""
    gains, garder = [], []
    # on reconstruit depuis les séries stockées dans mesurer (même ordre)
    for ev in par.values():
        if not ev:
            continue
        b = ev["k"][str(k)]["b"][periode]
        a = ev["k"][str(k)]["a"][periode]
        if not a:
            continue
        idx_a = {t: i for i, t in enumerate(a["temps"])}
        mask = np.zeros(len(a["temps"]), bool)
        if b:
            for t in b["temps"]:
                if t in idx_a:
                    mask[idx_a[t]] = True
        gains.append(np.array(a["gains"], float))
        garder.append(mask)
    if not gains:
        return None
    return hasard(np.concatenate(gains), np.concatenate(garder))


def etudier(series):
    rapport = {"k_fige": K_FIGE, "choix": [str(CHOIX_DEBUT), str(CHOIX_FIN)], "marches": {}, "melange": {}}
    for nom, graine in (("marches", None), ("melange", 7)):
        dossier = CACHE / ("csv_melange" if graine else "csv_reel")
        if dossier.exists():
            for p in dossier.glob("*.csv"):
                p.unlink()
        for i, epic in enumerate(MARCHES):
            src = series.get(epic)
            if src is None or len(src) < 800:
                print(epic, "sans données", flush=True)
                continue
            if graine:
                src = melanger_ohlc(src, graine + 17 * (i + 1))
            ecrire_csv(dossier, epic, src)
        dest = rapport["marches"] if graine is None else rapport["melange"]
        for epic in MARCHES:
            print(f"=== {nom} {epic} ===", flush=True)
            ev = evaluer(chaine(dossier, epic))
            if ev is None:
                dest[epic] = None
                continue
            # on garde les listes (gains, temps) pour le hasard de groupe, pas dans le markdown
            dest[epic] = ev
            j = ev["k"][str(K_FIGE)]
            print(epic, "a", _sans_series(j["a"]["juge"]), "b", _sans_series(j["b"]["juge"]),
                  "hasard", j["hasard_juge"], flush=True)
            Path(__file__).resolve().parent.joinpath("vote4h_amplitude_resultats.json").write_text(
                json.dumps(rapport, default=str))
    return rapport


# --------------------------------------------------------------------------- rapport
def _pct(x):
    return "—" if x is None else f"{100 * x:.1f} %".replace(".", ",")


def _gain(x):
    return "—" if x is None else f"{x:+.4f} %".replace(".", ",")


def _ligne(s):
    if not s:
        return "ne parie pas | — | 0 | 0 | — | — | — | —"
    return (f"{_pct(s['reussite'])} | {_gain(s['gain'])} | {s['n']} ({s['instants']}) | {s['trades_par_mois']:.0f} | "
            f"{s['marches_gagnants']}/{s['marches']} | {s['mois_positifs']}/{s['mois']} | {_pct(s['sens_majoritaire'])}")


def ecrire(rapport, chemin):
    k = str(K_FIGE)
    a_j = resumer_marches(rapport["marches"], K_FIGE, "juge", "a")
    b_j = resumer_marches(rapport["marches"], K_FIGE, "juge", "b")
    a_c = resumer_marches(rapport["marches"], K_FIGE, "choix", "a")
    b_c = resumer_marches(rapport["marches"], K_FIGE, "choix", "b")
    hz = hasard_groupe(rapport["marches"], K_FIGE, "juge")
    hz_c = hasard_groupe(rapport["marches"], K_FIGE, "choix")
    mel_b = resumer_marches(rapport["melange"], K_FIGE, "juge", "b", min_n=30)
    mel_a = resumer_marches(rapport["melange"], K_FIGE, "juge", "a", min_n=30)
    choix_mieux = bool(b_c and a_c and b_c["gain"] > a_c["gain"])
    v = verdict(a_j, b_j, None if not hz else hz["mieux"], None if not mel_b else mel_b["reussite"], choix_mieux)
    # k secondaire, choisi seulement sur le choix
    grille = []
    for kk in K_GRILLE:
        bb = resumer_marches(rapport["marches"], kk, "choix", "b")
        grille.append((kk, None if not bb else bb["gain"], 0 if not bb else bb["n"]))
    k_sec, gain_sec = choisir_k(grille)
    L = ["# Vote 4 h filtré par l'amplitude", "",
         "On garde le sens du vote 4 h (14 cerveaux, seulement ses 5 % les plus sûrs).",
         "On retire un trade seulement quand le mouvement médian prévu est plus petit que le spread et les frais de nuit.",
         f"**k = {K_FIGE:g}** est figé. La période jugée commence le {CHOIX_FIN.date()}, et n'a servi à choisir aucun seuil.",
         "",
         f"## Verdict : {v}",
         ""]
    if a_j and b_j and hz:
        L.append(f"Sur la période jugée, le vote seul fait {_gain(a_j['gain'])} par trade "
                 f"({_pct(a_j['reussite'])} de bonnes réponses, sens majoritaire {_pct(a_j['sens_majoritaire'])}, "
                 f"{a_j['marches_gagnants']}/{a_j['marches']} marchés, {a_j['trades_par_mois']:.0f} trades/mois, "
                 f"{a_j['instants']} instants distincts).")
        L.append(f"Le filtre fait {_gain(b_j['gain'])} par trade ({_pct(b_j['reussite'])}, "
                 f"{b_j['marches_gagnants']}/{b_j['marches']} marchés, {b_j['trades_par_mois']:.0f} trades/mois, "
                 f"{b_j['instants']} instants). Il bat {100 * hz['mieux']:.0f} % des filtres au hasard.")
    if v == "confirmée":
        L.append("Le filtre gagne de l'argent, bat le vote seul, bat 95 % des filtres au hasard, et les prix mélangés restent sous 53 %.")
    elif v == "prometteuse":
        L.append("Le filtre est devant le vote seul sur la période jugée, mais un contrôle manque (hasard, choix, marchés ou sens majoritaire).")
    else:
        L.append("Le filtre est rejeté : sur la période jugée il gagne moins que le vote seul, et moins que des retraits au hasard.")
    L += ["",
          "Lecture : gain = moyenne des marchés, après spread et frais de nuit, en % du prix. "
          "Instants = horaires distincts (la même bougie sur deux marchés compte une fois dans le total, "
          "et une fois par marché dans la somme). « Mieux que le hasard » = part de 500 filtres qui retirent "
          "le même nombre de trades et font un gain moyen plus bas.",
          "",
          "| | Réussite | Gain / trade | Trades (instants) | Trades/mois | Marchés + | Mois + | Sens majoritaire |",
          "|---|---|---|---|---|---|---|---|"]
    L.append(f"| (a) vote seul, choix | {_ligne(a_c)} |")
    L.append(f"| (b) vote + amplitude, choix | {_ligne(b_c)} |")
    L.append(f"| (a) vote seul, jugé | {_ligne(a_j)} |")
    L.append(f"| (b) vote + amplitude, jugé | {_ligne(b_j)} |")
    L.append("")
    def _hz(h, titre):
        if not h:
            return f"{titre} : pas assez de trades pour le test au hasard."
        return (f"{titre} : le filtre bat {100 * h['mieux']:.0f} % des hasards "
                f"(tous les trades réunis : gain {_gain(h['gain'])}, médiane du hasard {_gain(h['hasard_median'])}, "
                f"{h['n_gardes']} trades gardés sur {h['n_total']}).")
    L += [_hz(hz_c, "Choix"), _hz(hz, "Jugé"), "",
          f"Prix mélangés, période jugée : vote seul {_pct(None if not mel_a else mel_a['reussite'])} "
          f"(gain {_gain(None if not mel_a else mel_a['gain'])}), "
          f"vote + amplitude {_pct(None if not mel_b else mel_b['reussite'])} "
          f"(gain {_gain(None if not mel_b else mel_b['gain'])}, marchés avec au moins 30 trades mélangés).",
          ""]
    chauds = []
    for epic, ev in rapport["melange"].items():
        if not ev:
            continue
        mb = ev["k"][str(K_FIGE)]["b"]["juge"]
        if mb and mb["n"] >= 30 and mb["reussite"] > 0.53:
            chauds.append(f"{epic} ({_pct(mb['reussite'])}, {mb['n']} trades)")
    if chauds:
        L.append("Sur un marché isolé, les prix mélangés dépassent 53 % pour : " + ", ".join(chauds) + ".")
        L.append("La réussite filtrée de ces marchés-là ne compte pas comme un signal.")
        L.append("")
    if k_sec is not None:
        bsec = resumer_marches(rapport["marches"], k_sec, "juge", "b")
        L.append(f"k choisi sur le choix seulement : **{k_sec:g}** (gain de choix {_gain(gain_sec)}). "
                 f"Sur la période jugée il fait {_gain(None if not bsec else bsec['gain'])} "
                 f"({_pct(None if not bsec else bsec['reussite'])}, "
                 f"{0 if not bsec else bsec['marches_gagnants']}/{0 if not bsec else bsec['marches']} marchés). "
                 "Ce n'est pas le test principal.")
        L.append("")
    L += ["## Par marché, période jugée, k = 1", "",
          "| Marché | (a) réussite | (a) gain | (a) trades | (b) réussite | (b) gain | (b) trades | (b) sens majoritaire | (b) mois + | (b) prix mélangés | Mieux que le hasard |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for epic in MARCHES:
        ev = rapport["marches"].get(epic)
        if not ev:
            L.append(f"| {epic} | pas assez de bougies | — | — | — | — | — | — | — | — | — |")
            continue
        a = ev["k"][k]["a"]["juge"]
        b = ev["k"][k]["b"]["juge"]
        h = ev["k"][k]["hasard_juge"]
        mb = (rapport["melange"].get(epic) or {}).get("k", {}).get(k, {}).get("b", {}).get("juge")
        mel = _pct(None if not mb or mb["n"] < 30 else mb["reussite"])
        mieux = "—" if not h else f"{100 * h['mieux']:.0f} %"
        def cell(s, champ):
            if not s or (champ in ("reussite", "gain") and s["n"] < 30):
                return "—" if not s else f"trop peu ({s['n']})"
            if champ == "reussite":
                return _pct(s["reussite"])
            if champ == "gain":
                return _gain(s["gain"])
            if champ == "n":
                return str(s["n"])
            if champ == "maj":
                return _pct(s["sens_majoritaire"])
            if champ == "mois":
                return f"{s['mois_positifs']}/{s['mois']}"
            return "—"
        L.append(f"| {epic} | {cell(a, 'reussite')} | {cell(a, 'gain')} | {cell(a, 'n')} | "
                 f"{cell(b, 'reussite')} | {cell(b, 'gain')} | {cell(b, 'n')} | {cell(b, 'maj')} | "
                 f"{cell(b, 'mois')} | {mel} | {mieux} |")
    L += ["",
          "## D'où viennent les prix",
          "",
          "Dukascopy, bougies horaires bid, regroupées en 4 h (au moins 3 heures), de 2016 à novembre 2026.",
          "Le spread collé autour du prix est le spread médian des bougies 4 h Capital.com (`ia/resultats.json`).",
          "GBPUSD 0,010 % et DE40 0,007 % viennent de `ia/FRAIS_COURTIERS.md`. Les frais de nuit sont la moyenne",
          "achat/vente publiée, ajoutée quand la bougie passe 22 h UTC. Ce n'est pas le spread de chaque minute",
          "Capital.com : aux heures où il s'élargit, le coût réel serait un peu plus haut.",
          "",
          "Le vote est celui du labo (`ia/multi_labo.py`) : 3 IA réentraînées chaque mois sur le passé et 11 règles,",
          "trou de 10 h, seuil des 5 % le plus sûr calculé sur les bougies précédentes seulement.",
          "Le quantile médian est le même type de modèle que `ia/amplitude.py` (LightGBM, 80 arbres), entraîné",
          "chaque mois avec un trou de 4 h. Il ne choisit pas le sens : le sens reste celui du vote.",
          "",
          "## Lecture du verdict",
          "",
          "Confirmée : sur la période jugée, (b) gagne de l'argent, bat (a), bat au moins 95 % des filtres au hasard,",
          "a une réussite au-dessus du sens majoritaire, au moins 5 marchés sur 8 sont positifs, les prix mélangés restent",
          "≤ 53 %, et (b) battait déjà (a) sur la période de choix.",
          "Les prix ne sont pas les bougies Capital.com du vote confirmé (55 à 56 %, +0,013 à +0,023 % par trade).",
          "Ici on compare (a) et (b) sur les mêmes bougies Dukascopy. Le vote seul, sur cette série, ne dépasse pas",
          "le sens majoritaire : son petit gain vient surtout de la hausse de fond, pas d'un taux de réussite supérieur.",
          "Prometteuse : (b) est devant (a) et gagne de l'argent, mais un de ces contrôles manque.",
          "Rejetée : (b) perd, ou ne bat pas (a), ou les prix mélangés dépassent 53 %.",
          ""]
    if v == "confirmée":
        L += ["## Test direct, sans l'activer",
              "",
              "Dans `ia/pistes_direct.py`, au moment où le vote 4 h décide de parier (top 5 %), calculer le quantile",
              "médian sur le passé seul. Si sa valeur absolue est plus petite que le spread du moment plus les frais",
              "de nuit de cette bougie, écrire « abstention » au lieu de « parie ». Juger ensuite comme les autres",
              "pistes, sans ordre, sur la branche à part. Rien n'est branché ici.",
              ""]
    else:
        L += ["## Suite",
              "",
              "Le vote 4 h seul reste la piste en test direct (`ia/pistes_direct.py`). Ce filtre n'y est pas ajouté.",
              ""]
    Path(chemin).write_text("\n".join(L) + "\n")
    meta = {"verdict": v, "k": K_FIGE, "k_secondaire": k_sec,
            "a_juge": a_j, "b_juge": b_j, "a_choix": a_c, "b_choix": b_c,
            "hasard_juge": hz, "hasard_choix": hz_c,
            "melange_a": mel_a, "melange_b": mel_b, "choix_mieux": choix_mieux}
    return meta


def principal():
    print("téléchargement", flush=True)
    series = {}
    for epic in MARCHES:
        series[epic] = telecharger_4h(epic)
    rapport = etudier(series)
    # alléger le json : les listes restent, c'est le détail utile et ce n'est pas énorme
    racine = Path(__file__).resolve().parent
    meta = ecrire(rapport, racine / "VOTE4H_AMPLITUDE.md")
    (racine / "vote4h_amplitude_resultats.json").write_text(json.dumps({"meta": meta, "brut": rapport}, default=str))
    print("VERDICT", meta["verdict"], flush=True)
    print(json.dumps(meta, default=str)[:2000], flush=True)


if __name__ == "__main__":
    principal()

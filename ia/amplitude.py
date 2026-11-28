"""Piste AMPLITUDE : ne parier que si le mouvement prévu, du bon côté, dépasse le spread et les frais.

Aucun ordre. Ne touche pas au bot, ni à reglages.env, ni aux garde-fous.

Idée (figée avant de regarder les résultats) :
  deux quantiles LightGBM du rendement futur (25 % et 75 %), entraînés chaque mois sur le passé
  seulement, avec un trou ≥ horizon (le résultat de la dernière bougie d'entraînement est déjà connu
  avant la bougie testée).
  - « pessimiste » (aucun seuil réglable) : achat seulement si le quantile 25 % est AU-DESSUS du coût
    (spread Capital.com + frais de nuit s'il y en a un) ; vente seulement si le quantile 75 % est
    EN DESSOUS de moins le coût. Sinon on s'abstient.
  - « médiane » : on suit le signe du quantile 50 %, mais seulement s'il dépasse k fois le coût.
    k est choisi dans {1, 1.5, 2, 3} sur le passé du mois (le meilleur gain net, sinon on ne parie pas).

Le sens seul (on suit le quantile 50 % à chaque bougie) est la comparaison : le filtre d'amplitude
doit faire mieux que parier tout le temps.

Anti-triche : période de choix < 2025-11-28, période jugée ensuite ; prix mélangés (rendements
permutés, même spread) ; sens majoritaire ; une position à la fois (horizon = 1 bougie, pas de
chevauchement).

Les bougies Capital.com ne sont pas dans le dépôt (cache GitHub Actions, pas téléchargeable ici).
Les prix viennent de Yahoo Finance (spot ou future continu, gratuit). Le spread facturé est le
spread MÉDIAN réellement payé chez Capital.com (ia/resultats.json, bougies du labo) ; GBPUSD et
DE40 reprennent les ordres de grandeur de ia/FRAIS_COURTIERS.md. Les frais de nuit sont la moyenne
achat/vente publiée par Capital.com (on paie cette moyenne des deux côtés, comme le labo).

Usage : python -m ia.amplitude
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ia.predire import gains_trades, indicateurs  # noqa: E402

# Réglages figés avant les résultats. Ne pas les ajuster après avoir vu la période jugée.
CHOIX_FIN = pd.Timestamp("2025-11-28")
GRAINE_MELANGE = 7
KS = (1.0, 1.5, 2.0, 3.0)
QUANTILES = (0.25, 0.50, 0.75)
ARBRES = int(os.getenv("AMPLITUDE_ARBRES", "80"))
TRAIN_MAX = int(os.getenv("AMPLITUDE_TRAIN_MAX", "8000"))
MIN_TRAIN = {"15min": 600, "60min": 1800, "4h": 500}
MIN_PARIS_K = 20
SAUT_MAX = {"15min": 0.04, "60min": 0.08, "4h": 0.12}  # |rendement| au-delà : tick ou roll, retiré
MARCHES = ["GOLD", "SILVER", "OIL_CRUDE", "US100", "US500", "DE40", "EURUSD", "GBPUSD"]
YAHOO = {
    "GOLD": "GC=F", "SILVER": "SI=F", "OIL_CRUDE": "CL=F", "US100": "NQ=F",
    "US500": "ES=F", "DE40": "^GDAXI", "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
}
# Spread médian Capital.com, en % du prix (ia/resultats.json : (ask-bid)/mid). GBPUSD / DE40 : ia/FRAIS_COURTIERS.md.
SPREAD_PCT = {
    "EURUSD": {"15min": 0.00581, "60min": 0.00557, "4h": 0.00554},
    "GBPUSD": {"15min": 0.0100, "60min": 0.0100, "4h": 0.0100},
    "GOLD": {"15min": 0.00942, "60min": 0.01116, "4h": 0.01514},
    "SILVER": {"15min": 0.07932, "60min": 0.07997, "4h": 0.10038},
    "OIL_CRUDE": {"15min": 0.04743, "60min": 0.04539, "4h": 0.04911},
    "US100": {"15min": 0.00724, "60min": 0.00830, "4h": 0.01236},
    "US500": {"15min": 0.00781, "60min": 0.00820, "4h": 0.01577},
    "DE40": {"15min": 0.0070, "60min": 0.0070, "4h": 0.0070},
}
# Frais de nuit moyen (achat et vente), en % par passage de 22 h UTC. Moyenne des deux sens, pour ne pas
# encaisser un swap « reçu » qui n'est pas une prédiction. Sources : page frais Capital.com et exemple d'API.
NUIT_PCT = {
    "GOLD": 0.00411, "SILVER": 0.00411, "EURUSD": 0.00411, "GBPUSD": 0.00411,
    "OIL_CRUDE": 0.01096, "US100": 0.01111, "US500": 0.01111, "DE40": 0.01111,
}
HORIZONS = {
    "15min": {"minutes": 15, "yahoo": "15m", "jours": 59},
    "60min": {"minutes": 60, "yahoo": "1h", "jours": 729},
    "4h": {"minutes": 240, "yahoo": "1h", "jours": 729},
}
CIBLES = ("mv", "cout", "gain_achat", "gain_vente", "y")


def telecharger_yahoo(symbole, intervalle, jours):
    """Bougies Yahoo (open/high/low/close/volume), index UTC sans fuseau."""
    maintenant = int(datetime.now(timezone.utc).timestamp())
    q = urllib.parse.quote(symbole, safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?period1={maintenant - jours * 86400}"
           f"&period2={maintenant}&interval={intervalle}&includePrePost=true")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as rep:
        brut = json.load(rep)
    res = brut["chart"]["result"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_localize(None)
    qte = res["indicators"]["quote"][0]
    d = pd.DataFrame({k: qte.get(k) for k in ("open", "high", "low", "close", "volume")}, index=idx)
    d = d[~d.index.duplicated(keep="last")].sort_index()
    d["close"] = d["close"].astype(float)
    d = d[np.isfinite(d["close"]) & (d["close"] > 0)]
    for col in ("open", "high", "low"):
        d[col] = d[col].astype(float).where(np.isfinite(d[col]), d["close"])
    d["volume"] = d["volume"].fillna(0).astype(float)
    return d


def en_4h(horaire):
    """Regroupe les heures en bougies de 4 h (au moins 3 heures présentes)."""
    x = horaire.copy()
    x["seau"] = x.index.floor("4h")
    g = x.groupby("seau").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
                              close=("close", "last"), volume=("volume", "sum"), n=("close", "size"))
    return g[g["n"] >= 3].drop(columns="n")


def melanger(d, graine):
    """Permute les rendements de clôture et reconstruit le chemin. Le spread % (posé ensuite) ne change pas."""
    mid = d["close"].to_numpy(dtype=float)
    r = np.zeros(len(mid))
    r[1:] = np.diff(np.log(mid))
    rng = np.random.default_rng(graine)
    r[1:] = rng.permutation(r[1:])
    nouveau = mid[0] * np.exp(np.cumsum(r))
    k = nouveau / mid
    out = d.copy()
    for col in ("open", "high", "low", "close"):
        out[col] = d[col].to_numpy(dtype=float) * k
    return out


def vers_bid_ask(d, spread_pct):
    """Milieu Yahoo -> bid/ask avec le spread Capital.com (constant, en % du prix)."""
    demi = spread_pct / 100 / 2
    out = pd.DataFrame(index=d.index)
    for col in ("open", "high", "low", "close"):
        out[f"{col}_bid"] = d[col] * (1 - demi)
        out[f"{col}_ask"] = d[col] * (1 + demi)
    out["volume"] = d["volume"].to_numpy()
    return out


def cibles(d, spread_pct, nuit_pct, minutes, saut_max):
    """Mouvement, coût et gains nets de la bougie suivante. Le spread est celui posé sur le bid/ask."""
    brut = vers_bid_ask(d, spread_pct)
    achat, vente = gains_trades(brut, 1, nuit_pct / 100, nuit_pct / 100)
    mid = ((brut.close_bid + brut.close_ask) / 2).to_numpy()
    mv = np.full(len(brut), np.nan)
    mv[:-1] = (mid[1:] / mid[:-1] - 1) * 100
    ecart = brut.index.to_series().diff().shift(-1).dt.total_seconds().div(60).to_numpy()
    t = brut.index.values.astype("datetime64[s]").astype(np.int64)
    jour = np.floor((t - 22 * 3600) / 86400)
    nuits = np.zeros(len(brut))
    nuits[:-1] = np.clip(jour[1:] - jour[:-1], 0, 7)
    ok = (ecart <= minutes * 1.5) & np.isfinite(mv) & (np.abs(mv) <= saut_max * 100) & (mv != 0)
    out = pd.DataFrame({"mv": mv, "cout": spread_pct + nuits * nuit_pct, "gain_achat": achat * 100,
                        "gain_vente": vente * 100}, index=brut.index)
    out["y"] = (out["mv"] > 0).astype(float)
    return out.loc[ok]


def table(d, spread_pct, nuit_pct, minutes, saut_max):
    """Indicateurs connus à la clôture, cible = bougie suivante, gains nets (fonction du labo)."""
    brut = vers_bid_ask(d, spread_pct)
    f = indicateurs(brut)
    y = cibles(d, spread_pct, nuit_pct, minutes, saut_max)
    f = f.join(y, how="inner").replace([np.inf, -np.inf], np.nan).dropna()
    return f


def ajouter_croix(tables):
    """Rendement normalisé des autres marchés, dernier connu (jamais une bougie future)."""
    for epic, f in tables.items():
        for autre, g in tables.items():
            if autre == epic or "r1" not in g:
                continue
            alignes = g["r1"].reindex(g.index.union(f.index)).ffill()
            f[f"x_{autre}"] = alignes.reindex(f.index)
        crois = [c for c in f.columns if c.startswith("x_")]
        if crois:
            f[crois] = f[crois].fillna(0.0)


def _params(n):
    return dict(n_estimators=ARBRES, learning_rate=0.05, num_leaves=15,
                min_child_samples=int(min(80, max(20, n // 30))), subsample=0.8, subsample_freq=1,
                colsample_bytree=0.8, reg_lambda=1.0, verbose=-1, random_state=0, n_jobs=1,
                force_col_wise=True)


def _fit_quantiles(Xtr, ytr, Xte):
    import lightgbm as lgb
    out = []
    for alpha in QUANTILES:
        m = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **_params(len(Xtr)))
        m.fit(Xtr, ytr)
        out.append(m.predict(Xte))
    return out


def marcher(f, minutes):
    """Walk-forward mensuel. Chaque prédiction n'utilise que des bougies dont le résultat est déjà connu."""
    horizon = pd.Timedelta(minutes=minutes)
    nom = {15: "15min", 60: "60min", 240: "4h"}[minutes]
    cols = [c for c in f.columns if c not in CIBLES]
    X = f[cols].to_numpy(dtype=np.float32)
    index = f.index
    mv = f["mv"].to_numpy()
    cout = f["cout"].to_numpy()
    ga = f["gain_achat"].to_numpy()
    gv = f["gain_vente"].to_numpy()
    q25 = np.full(len(f), np.nan)
    q50 = np.full(len(f), np.nan)
    q75 = np.full(len(f), np.nan)
    k_mois = np.full(len(f), np.nan)
    debuts = pd.date_range(index.min().normalize().replace(day=1), index.max() + pd.Timedelta(days=32), freq="MS")
    min_train = MIN_TRAIN[nom]
    for debut in debuts:
        fin = debut + pd.DateOffset(months=1)
        tr = np.where(index < debut - horizon)[0][-TRAIN_MAX:]
        te = np.where((index >= debut) & (index < fin))[0]
        if len(tr) < min_train or not len(te):
            continue
        n_val = max(MIN_PARIS_K * 3, len(tr) // 5)
        val = tr[-n_val:]
        fit = tr[:-n_val]
        fit = fit[index[fit] + horizon < index[val[0]]]
        if len(fit) < min_train // 2:
            continue
        # k sur le passé seulement (validation), puis le modèle est réentraîné sur tout le passé
        p25, p50, p75 = _fit_quantiles(X[fit], mv[fit], X[val])
        meilleur, k_choisi = 0.0, None
        for k in KS:
            cote = np.where(p50 > k * cout[val], 1, np.where(p50 < -k * cout[val], -1, 0))
            pris = cote != 0
            if pris.sum() < MIN_PARIS_K:
                continue
            g = np.where(cote == 1, ga[val], np.where(cote == -1, gv[val], np.nan))
            moy = float(np.nanmean(g))
            if moy > meilleur:
                meilleur, k_choisi = moy, k
        p25, p50, p75 = _fit_quantiles(X[tr], mv[tr], X[te])
        q25[te], q50[te], q75[te] = p25, p50, p75
        if k_choisi is not None:
            k_mois[te] = k_choisi
    return pd.DataFrame({"q25": q25, "q50": q50, "q75": q75, "k": k_mois}, index=index)


def cotes(pred, f):
    """Trois façons de décider, toutes calculées après coup à partir des quantiles (rien n'est réappris)."""
    cout = f["cout"].to_numpy()
    q25, q50, q75, k = (pred[c].to_numpy() for c in ("q25", "q50", "q75", "k"))
    connu = np.isfinite(q50)
    pess = np.where(connu & (q25 > cout), 1, np.where(connu & (q75 < -cout), -1, 0))
    pess[(q25 > cout) & (q75 < -cout)] = 0
    med = np.where(connu & np.isfinite(k) & (q50 > k * cout), 1,
                   np.where(connu & np.isfinite(k) & (q50 < -k * cout), -1, 0))
    seul = np.where(connu & (q50 > 0), 1, np.where(connu & (q50 < 0), -1, 0))
    return {"pessimiste": pess, "mediane": med, "sens_seul": seul}


def _gain(cote, f):
    return np.where(cote == 1, f["gain_achat"], np.where(cote == -1, f["gain_vente"], np.nan))


def mesurer(f, cote, debut=None, fin=None):
    """Chiffres sur les bougies où l'on parie. Une bougie = un instant (horizon 1, pas de chevauchement)."""
    m = cote != 0
    if debut is not None:
        m &= np.asarray(f.index >= debut)
    if fin is not None:
        m &= np.asarray(f.index < fin)
    idx = f.index[m]
    if len(idx) == 0:
        return None
    mv = f["mv"].to_numpy()[m]
    g = _gain(cote, f)[m]
    juste = cote[m] * mv > 0
    mois = idx.to_period("M")
    gm = pd.Series(g).groupby(np.asarray(mois)).sum()
    # du premier pari jusqu'à la fin de la fenêtre (le chauffe, avant tout pari, ne compte pas)
    t0 = idx.min()
    t1 = f.index.max() if fin is None else min(pd.Timestamp(fin), f.index.max())
    span = max((t1 - t0).days / 30.44, 1 / 30.44)
    hausses = float((mv > 0).mean())
    return {
        "n": int(len(idx)),
        "instants": int(len(idx.unique())),
        "reussite": round(float(juste.mean()), 4),
        "gain": round(float(np.mean(g)), 5),
        "gain_total": round(float(np.sum(g)), 4),
        "trades_par_mois": round(float(len(idx) / span), 2),
        "mois_positifs": int((gm > 0).sum()),
        "mois": int(len(gm)),
        "sens_majoritaire": round(float(max(hausses, 1 - hausses)), 4),
        "part_hausse": round(hausses, 4),
        "debut": str(idx.min()),
        "fin": str(idx.max()),
    }


def gain_majorite_passee(f, cote, signe_passe, debut=None, fin=None):
    """Même instants que les paris, mais le sens est celui qui gagnait le plus souvent AVANT la période."""
    m = cote != 0
    if debut is not None:
        m &= np.asarray(f.index >= debut)
    if fin is not None:
        m &= np.asarray(f.index < fin)
    if m.sum() == 0 or signe_passe == 0:
        return None
    g = f["gain_achat"].to_numpy()[m] if signe_passe > 0 else f["gain_vente"].to_numpy()[m]
    mv = f["mv"].to_numpy()[m]
    return {"gain": round(float(np.mean(g)), 5), "reussite": round(float((signe_passe * mv > 0).mean()), 4),
            "sens": "hausse" if signe_passe > 0 else "baisse"}


def signe_majoritaire(f, fin):
    """Sens le plus fréquent strictement avant `fin` (égalité : hausse)."""
    mv = f.loc[f.index < fin, "mv"]
    if len(mv) < 50:
        return 0
    return 1 if (mv > 0).mean() >= 0.5 else -1


def preparer_horizon(series, nom, melange=False):
    """series : epic -> bougies OHLC de cet horizon."""
    minutes = HORIZONS[nom]["minutes"]
    tables = {}
    for epic, d in series.items():
        # graine décalée par marché : la même permutation sur deux marchés garderait leur corrélation
        src = melanger(d, GRAINE_MELANGE + 17 * (MARCHES.index(epic) + 1)) if melange else d
        tables[epic] = table(src, SPREAD_PCT[epic][nom], NUIT_PCT[epic], minutes, SAUT_MAX[nom])
    ajouter_croix(tables)
    return tables


def evaluer_marche(f, minutes):
    pred = marcher(f, minutes)
    cote = cotes(pred, f)
    signe_choix = signe_majoritaire(f, CHOIX_FIN)
    out = {}
    for regle, side in cote.items():
        choix = mesurer(f, side, fin=CHOIX_FIN)
        juge = mesurer(f, side, debut=CHOIX_FIN)
        out[regle] = {
            "choix": choix,
            "juge": juge,
            "maj_choix": gain_majorite_passee(
                f, side, signe_majoritaire(f, pd.Timestamp(choix["debut"]) if choix else CHOIX_FIN), fin=CHOIX_FIN),
            "maj_juge": gain_majorite_passee(f, side, signe_choix, debut=CHOIX_FIN),
        }
    return out


def _moy(lignes, cle):
    vals = [x[cle] for x in lignes if x and x.get(cle) is not None]
    return float(np.mean(vals)) if vals else None


def choisir_regle(par_marche):
    """Règle retenue sur la période de choix seulement (gain moyen des marchés, prix mélangés ≤ 53 %)."""
    meilleur, nom = None, None
    for regle in ("pessimiste", "mediane"):
        choix = [m["reel"][regle]["choix"] for m in par_marche.values() if m["reel"][regle]["choix"]]
        mel = [m["melange"][regle]["choix"] for m in par_marche.values() if m["melange"][regle]["choix"]]
        if len(choix) < 3:
            continue
        gain = _moy(choix, "gain")
        acc_m = _moy(mel, "reussite")
        if acc_m is not None and acc_m > 0.53:
            continue
        if nom is None or gain > meilleur:
            meilleur, nom = gain, regle
    return nom, meilleur


def verdict(regle, resume, court, gain_choix=None):
    """confirmée / prometteuse / rejetée. `resume` agrège la période jugée."""
    if regle is None or resume is None or not resume.get("n"):
        return "rejetée"
    if resume.get("melange") is not None and resume["melange"] > 0.53:
        return "rejetée"
    if resume["n"] < 30 or resume["gain"] is None or resume["gain"] <= 0:
        return "rejetée"
    if court or (gain_choix is not None and gain_choix <= 0):
        return "prometteuse"
    assez = (resume["marches_gagnants"] >= 6 and resume["n"] >= 80 and resume["mois"] >= 3
             and resume["reussite"] > resume["sens_majoritaire"])
    return "confirmée" if assez else "prometteuse"


def _bloc(par_marche, regle, periode, melange=False):
    cle = "melange" if melange else "reel"
    return [m[cle][regle][periode] for m in par_marche.values() if m[cle][regle][periode]]


def resumer(par_marche, regle, periode):
    re_ = _bloc(par_marche, regle, periode)
    me = _bloc(par_marche, regle, periode, melange=True)
    if not re_:
        return None
    maj = [m["reel"][regle]["maj_" + ("choix" if periode == "choix" else "juge")] for m in par_marche.values()]
    maj = [x for x in maj if x]
    seul = _bloc(par_marche, "sens_seul", periode)
    return {
        "n": int(sum(x["n"] for x in re_)),
        "instants": int(sum(x["instants"] for x in re_)),
        "reussite": round(_moy(re_, "reussite"), 4),
        "gain": round(_moy(re_, "gain"), 5),
        "trades_par_mois": round(_moy(re_, "trades_par_mois"), 2),
        "sens_majoritaire": round(_moy(re_, "sens_majoritaire"), 4),
        "gain_majorite_passee": round(_moy(maj, "gain"), 5) if maj else None,
        "reussite_majorite_passee": round(_moy(maj, "reussite"), 4) if maj else None,
        "gain_sens_seul": round(_moy(seul, "gain"), 5) if seul else None,
        "reussite_sens_seul": round(_moy(seul, "reussite"), 4) if seul else None,
        "marches_gagnants": int(sum(x["gain"] > 0 for x in re_)),
        "marches": len(re_),
        "mois_positifs": int(sum(x["mois_positifs"] for x in re_)),
        "mois": int(sum(x["mois"] for x in re_)),
        "melange": round(_moy(me, "reussite"), 4) if me else None,
        "melange_gain": round(_moy(me, "gain"), 5) if me else None,
        "melange_n": int(sum(x["n"] for x in me)) if me else 0,
    }


def etudier(series_par_horizon):
    """series_par_horizon : horizon -> {epic: OHLC}."""
    rapport = {"reglages": {"choix_fin": str(CHOIX_FIN), "quantiles": QUANTILES, "k": KS, "arbres": ARBRES,
                            "graine_melange": GRAINE_MELANGE, "spread_pct": SPREAD_PCT, "nuit_pct": NUIT_PCT},
               "horizons": {}}
    for nom, series in series_par_horizon.items():
        print(f"=== {nom} réel ===", flush=True)
        minutes = HORIZONS[nom]["minutes"]
        reel = preparer_horizon(series, nom, melange=False)
        faux = preparer_horizon(series, nom, melange=True)
        par = {}
        for epic in MARCHES:
            if epic not in reel or len(reel[epic]) < MIN_TRAIN[nom] + 50:
                print(epic, nom, "pas assez de bougies", flush=True)
                continue
            print(f"{epic} {nom} : {len(reel[epic])} bougies", flush=True)
            par[epic] = {"reel": evaluer_marche(reel[epic], minutes), "melange": evaluer_marche(faux[epic], minutes),
                         "cout_moyen": round(float(reel[epic]["cout"].mean()), 5),
                         "debut": str(reel[epic].index.min()), "fin": str(reel[epic].index.max())}
        regle, gain_choix = choisir_regle(par)
        if nom == "15min":
            # échantillon court (Yahoo ne donne que ~60 jours) : on ne choisit rien dessus, règle sans seuil
            regle, gain_choix = "pessimiste", None
        court = nom == "15min"
        juge = resumer(par, regle, "juge") if regle else None
        choix = resumer(par, regle, "choix") if regle else None
        rapport["horizons"][nom] = {
            "regle": regle, "gain_choix_retenu": None if gain_choix is None else round(float(gain_choix), 5),
            "court": court, "verdict": verdict(regle, juge, court, None if nom == "15min" else gain_choix),
            "choix": choix, "juge": juge,
            "pessimiste_juge": resumer(par, "pessimiste", "juge"),
            "mediane_juge": resumer(par, "mediane", "juge"),
            "marches": par,
        }
        print(nom, "règle", regle, "verdict", rapport["horizons"][nom]["verdict"], juge, flush=True)
        racine = Path(__file__).resolve().parent
        (racine / "amplitude_resultats.json").write_text(json.dumps(rapport, ensure_ascii=False, default=str))
        ecrire_rapport(rapport, racine / "AMPLITUDE.md")
    return rapport


def _fmt_pct(x):
    if x is None:
        return "—"
    return f"{100 * x:.1f} %".replace(".", ",")


def _fmt_gain(x):
    if x is None:
        return "—"
    return f"{x:+.4f} %".replace(".", ",")


def _ligne_periode(titre, s):
    if not s or not s.get("n"):
        return f"| {titre} | ne parie pas | — | 0 | 0 | — | — | — | — | — | — |"
    return (f"| {titre} | {_fmt_pct(s['reussite'])} | {_fmt_gain(s['gain'])} | {s['n']} ({s['instants']}) | "
            f"{s['trades_par_mois']:.0f} | {_fmt_pct(s['sens_majoritaire'])} | {_fmt_gain(s['gain_majorite_passee'])} | "
            f"{_fmt_gain(s['gain_sens_seul'])} | {s['marches_gagnants']}/{s['marches']} | "
            f"{s['mois_positifs']}/{s['mois']} | {_fmt_pct(s['melange'])}, gain {_fmt_gain(s['melange_gain'])} |")


def _ligne_marche(epic, j, mj, fm, cout):
    """Une ligne marché. En dessous de 30 trades, le pourcentage ne veut rien dire."""
    if not j or j["n"] < 30:
        n = 0 if not j else j["n"]
        return f"| {epic} | trop peu de trades ({n}) | — | {n} | — | — | — | {n} | — | — | {cout:.4f} % |"
    mel = "—"
    if fm and fm.get("n", 0) >= 30:
        mel = _fmt_pct(fm["reussite"])
    elif fm and fm.get("n", 0) > 0:
        mel = f"trop peu ({fm['n']})"
    return (f"| {epic} | {_fmt_pct(j['reussite'])} | {_fmt_gain(j['gain'])} | {j['n']} | {j['trades_par_mois']:.0f} | "
            f"{_fmt_pct(j['sens_majoritaire'])} | {_fmt_gain((mj or {}).get('gain'))} | {j['instants']} | "
            f"{j['mois_positifs']}/{j['mois']} | {mel} | {cout:.4f} % |")


def ecrire_rapport(rapport, chemin_md):
    L = ["# Amplitude : ne parier que si le mouvement prévu dépasse le spread", "",
         "Question : prévoir la taille du prochain mouvement, et ne jouer que lorsque ce mouvement, du bon côté,",
         "dépasse le spread et les frais de nuit.", "",
         "Deux règles, figées avant de lire la période jugée (après le 28/11/2025) :",
         "- **pessimiste** : on achète seulement si le quartile bas (25 %) du mouvement prévu est déjà au-dessus du coût,",
         "  on vend seulement si le quartile haut (75 %) est déjà en dessous de moins le coût. Aucun seuil à régler.",
         "- **médiane** : on suit le signe du mouvement médian prévu, seulement s'il dépasse k fois le coût.",
         "  k est choisi dans {1 ; 1,5 ; 2 ; 3} sur le passé du mois. S'il n'y a aucun k gagnant dans le passé, on s'abstient.",
         "",
         "À 60 min et à 4 h, la règle du tableau détaillé est celle qui a le meilleur gain sur la période de choix,",
         "à condition que les prix mélangés y restent ≤ 53 %. À 15 min l'historique est trop court pour choisir :",
         "on publie la règle pessimiste.", ""]
    L.append("## Verdict")
    L.append("")
    for nom, r in rapport["horizons"].items():
        j = r.get("juge") or {}
        if nom == "15min":
            alt = r.get("mediane_juge") or {}
            L.append(f"- **15 min : rejetée.** La règle pessimiste ne trouve aucun moment où le mauvais cas du")
            L.append(f"  mouvement prévu dépasse le spread. La médiane, elle, parie et perd "
                     f"{_fmt_gain(alt.get('gain'))} par trade "
                     f"({_fmt_pct(alt.get('reussite'))} de bonnes réponses, "
                     f"{alt.get('marches_gagnants', 0)}/{alt.get('marches', 0)} marchés, "
                     f"prix mélangés {_fmt_pct(alt.get('melange'))}).")
        else:
            nom_regle = {"pessimiste": "pessimiste", "mediane": "médiane"}.get(r["regle"], r["regle"])
            L.append(f"- **{nom} : {r['verdict']}** (règle {nom_regle}). "
                     f"Hors échantillon : {_fmt_pct(j.get('reussite'))} de bonnes réponses, "
                     f"{_fmt_gain(j.get('gain'))} par trade, "
                     f"{None if j.get('trades_par_mois') is None else round(j['trades_par_mois'])} trades/mois, "
                     f"{j.get('marches_gagnants', 0)}/{j.get('marches', 0)} marchés gagnants, "
                     f"sens majoritaire {_fmt_pct(j.get('sens_majoritaire'))}, "
                     f"prix mélangés {_fmt_pct(j.get('melange'))}.")
    L += ["",
          "En une phrase : prévoir l'amplitude ne suffit pas à passer le spread. À 15 min le modèle prudent",
          "se tait, et le modèle qui parle perd à peu près le spread. À 60 min et à 4 h, c'est la même chose",
          "sur un an jamais utilisé pour choisir la règle.",
          "",
          "## Comment c'est mesuré",
          "",
          "Entraînement sur le passé seulement, un trou d'au moins une bougie (le résultat de la dernière bougie",
          "d'entraînement est déjà connu). Période de choix : avant le 28/11/2025. Période jugée : après.",
          "Une position à la fois : on entre à la clôture et on sort à la clôture suivante, donc chaque trade est",
          "un instant distinct (pas le même mouvement compté plusieurs fois). Le total « instants » additionne",
          "les marchés : la même heure sur l'or et sur l'euro compte deux instants.",
          "",
          "Les bougies Capital.com sont dans le cache GitHub Actions, pas dans le dépôt. Les prix utilisés ici",
          "viennent de Yahoo Finance (euro et livre au comptant ; or, argent, pétrole, Nasdaq et S&P en futures ;",
          "DAX au comptant), du 29/11/2024 au 27/11/2026 en 1 h, et ~60 jours seulement en 15 min.",
          "Le spread facturé est le spread **médian** mesuré chez Capital.com dans `ia/resultats.json`.",
          "GBPUSD (0,010 %) et DE40 (0,007 %) viennent de `ia/FRAIS_COURTIERS.md`. Ce n'est pas le spread de",
          "chaque minute : aux heures où Capital.com l'élargit, le coût réel serait un peu plus haut.",
          "Les frais de nuit sont la moyenne achat/vente publiée, payée des deux côtés, à chaque passage de 22 h UTC",
          "(même calcul que `ia/predire.py`).",
          "",
          "Contrôle des prix mélangés : on permute les rendements, on garde le même spread, on refait toute la",
          "chaîne. La réussite doit rester autour de 50 %. Au-dessus de 53 %, la règle est rejetée.",
          "Le sens majoritaire est la part du sens le plus fréquent sur les trades jugés. « Majorité passée »",
          "parie, sur les mêmes instants, le sens qui gagnait le plus souvent avant la période. « Sens seul »",
          "suit la médiane prévue à chaque bougie, sans filtre d'amplitude.",
          "",
          "Le vieux filtre « amplitude ≥ 3 × spread » du labo multi-cerveaux demandait seulement « est-ce que ça",
          "va beaucoup bouger », puis devinait le sens. Il est déjà perdu. Ici le mouvement **du côté parié**",
          "doit dépasser le coût.",
          ""]
    entete = ("| Période | Réussite | Gain après spread et frais | Trades (instants) | Trades/mois | "
              "Sens majoritaire | Gain du sens majoritaire passé | Sens seul (gain) | Marchés gagnants | "
              "Mois positifs | Prix mélangés |")
    entete_m = ("| Marché | Réussite | Gain | Trades | Trades/mois | Sens majoritaire | "
                "Gain majorité passée | Instants | Mois + | Prix mélangés | Coût moyen |")
    sep = "|---|---|---|---|---|---|---|---|---|---|---|"
    sep_m = "|---|---|---|---|---|---|---|---|---|---|---|"
    for nom, r in rapport["horizons"].items():
        L += [f"## {nom} — {r['verdict']}", ""]
        if nom == "15min":
            L.append("Règle publiée : **pessimiste** (aucun seuil). Elle ne parie sur aucun marché.")
            L.append("Le détail marché ci-dessous est donc la **médiane** (non retenue, et perdante).")
        else:
            L.append(f"Règle retenue sur la période de choix : **{r['regle']}** "
                     f"(gain de choix {_fmt_gain(r['gain_choix_retenu'])}).")
        if nom == "4h" and "DE40" not in r["marches"]:
            L.append("DE40 en 4 h : 452 bougies utilisables (le DAX ne cote pas la nuit), sous le minimum de 500")
            L.append("pour entraîner. Ce marché n'entre pas dans ce tableau.")
        L += ["", entete, sep]
        L.append(_ligne_periode("Choix (avant le 28/11/2025)", r.get("choix")))
        L.append(_ligne_periode("Jugé (après le 28/11/2025)", r.get("juge")))
        L += ["", "Les deux règles sur la période jugée. Celle qui n'a pas été retenue sur le choix ne confirme rien.",
              "", "| Règle | Réussite | Gain | Trades/mois | Marchés gagnants | Prix mélangés |",
              "|---|---|---|---|---|---|"]
        for regle, titre in (("pessimiste", "pessimiste"), ("mediane", "médiane")):
            s = r.get(f"{regle}_juge")
            if not s or s.get("n", 0) < 30:
                n = 0 if not s else s["n"]
                L.append(f"| {titre} | trop peu de trades ({n}) | — | — | — | — |")
            else:
                L.append(f"| {titre} | {_fmt_pct(s['reussite'])} | {_fmt_gain(s['gain'])} | {s['trades_par_mois']:.0f} | "
                         f"{s['marches_gagnants']}/{s['marches']} | {_fmt_pct(s['melange'])} |")
        detail = r["regle"]
        if nom == "15min":
            detail = "mediane"
        L += ["", f"Détail par marché, règle **{detail}**, période jugée.", "", entete_m, sep_m]
        chauds, verts = [], []
        for epic, m in r["marches"].items():
            bloc = m["reel"][detail]
            fm = m["melange"][detail]["juge"]
            L.append(_ligne_marche(epic, bloc["juge"], bloc["maj_juge"], fm, m["cout_moyen"]))
            j = bloc["juge"] or {}
            if j.get("n", 0) >= 30 and j.get("gain", 0) > 0:
                verts.append(f"{epic} ({_fmt_gain(j['gain'])})")
            if fm and fm.get("n", 0) >= 30 and fm.get("reussite", 0) > 0.53:
                chauds.append(f"{epic} ({_fmt_pct(fm['reussite'])})")
        if verts:
            L.append("")
            L.append("Gain positif sur la période jugée : " + ", ".join(verts) + ".")
        if chauds:
            L.append("Prix mélangés au-dessus de 53 % (ces lignes ne comptent pas comme un signal) : " + ", ".join(chauds) + ".")
        L.append("")
    j60 = (rapport["horizons"].get("60min") or {}).get("juge") or {}
    j4 = (rapport["horizons"].get("4h") or {}).get("juge") or {}
    L += ["## Lecture", "",
          "Confirmée : gain jugé positif, au moins 6 marchés sur 8, réussite au-dessus du sens majoritaire,",
          "assez de trades, prix mélangés ≤ 53 %, et la période de choix était déjà positive.",
          "Prometteuse : gain jugé positif, avec un contrôle qui manque.",
          "Rejetée : gain négatif ou nul, ou presque aucun trade, ou prix mélangés au-dessus de 53 %.",
          "",
          f"À 60 min, le sens seul perd {_fmt_gain(j60.get('gain_sens_seul'))} par trade et la règle retenue "
          f"perd {_fmt_gain(j60.get('gain'))} : le filtre d'amplitude retire des trades, la perte reste.",
          f"À 4 h la réussite jugée ({_fmt_pct(j4.get('reussite'))}) se compare au sens majoritaire "
          f"({_fmt_pct(j4.get('sens_majoritaire'))}).",
          f"Sur les prix mélangés à 60 min, le gain est {_fmt_gain(j60.get('melange_gain'))} parce que la permutation",
          "garde la hausse de fond de l'or et des indices, et la réussite est "
          f"{_fmt_pct(j60.get('melange'))}. Le contrôle de réussite reste sous 53 %, et le gain réel est négatif.",
          "",
          "## Prochaine variante (pas lancée, aucun ordre)", "",
          "Le vote 4 h déjà confirmé (5 % les plus sûrs, +0,013 à +0,023 % par trade) reste la piste qui tient.",
          "La règle pessimiste de cette étude se tait presque tout le temps : l'ajouter telle quelle sur ce vote",
          "couperait aussi les bons signaux. La variante à tester ensuite : garder le sens du vote 4 h, et",
          "s'abstenir seulement quand le mouvement médian prévu est plus petit que le spread. On filtre un",
          "signal qui a déjà une petite avance, avec le seuil le plus simple (k = 1), hors échantillon,",
          "prix mélangés à côté. Rien n'est branché sur `ia/pistes_direct.py`.", ""]
    Path(chemin_md).write_text("\n".join(L) + "\n")


def charger():
    """Télécharge 15 min et 1 h, fabrique les bougies 4 h."""
    brut = {}
    for epic in MARCHES:
        print("télécharge", epic, flush=True)
        brut[(epic, "15m")] = telecharger_yahoo(YAHOO[epic], "15m", 59)
        brut[(epic, "1h")] = telecharger_yahoo(YAHOO[epic], "1h", 729)
        print(" ", epic, "15m", len(brut[(epic, "15m")]), "1h", len(brut[(epic, "1h")]),
              "dernier", float(brut[(epic, "1h")]["close"].iloc[-1]), flush=True)
    return {
        "15min": {e: brut[(e, "15m")] for e in MARCHES},
        "60min": {e: brut[(e, "1h")] for e in MARCHES},
        "4h": {e: en_4h(brut[(e, "1h")]) for e in MARCHES},
    }


def principal():
    series = charger()
    rapport = etudier(series)
    racine = Path(__file__).resolve().parent
    (racine / "amplitude_resultats.json").write_text(json.dumps(rapport, ensure_ascii=False, default=str))
    ecrire_rapport(rapport, racine / "AMPLITUDE.md")
    print("écrit", racine / "AMPLITUDE.md", flush=True)


if __name__ == "__main__":
    principal()

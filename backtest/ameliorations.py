"""RECHERCHE « AMÉLIORER LES STRATÉGIES ACTUELLES » (26/11/2026, demande de Mathis).

Idées venues de la recherche (études, livres de trading systématique, forums quant), appliquées aux
stratégies ACTIVES sans changer leur cœur :
  Cassure 4 h or + argent (20/20, EMA 200, stop garanti 2 ATR, garde 50 % après +1,5 R, 1er signal)
  Supertrend 10/3 4 h ETH (+ test sur d'autres cryptos, maintenant que le Bitcoin est libre)

Familles testées :
  FILTRES (on garde ou on saute un trade au moment du signal) :
    momentum   : sens du prix sur L jours (Moskowitz-Ooi-Pedersen 2012, « time-series momentum »)
    efficacite : ratio d'efficacité de Kaufman sur N bougies >= seuil (marché qui avance « droit »)
    calme      : ATR 14 / ATR 100 <= seuil (cassure après une période calme, « contraction de volatilité »)
    agite      : ATR 14 / ATR 100 >= seuil (cassure quand la volatilité grimpe)
    jour_ema   : prix du bon côté de l'EMA N des bougies JOUR (filtre d'unité supérieure, multi-timeframe)
    jumeau     : or et argent : la Cassure de l'autre métal n'est pas dans le sens opposé / est dans le même sens
    achats     : achats seulement (l'or monte sur le long terme)
  TAILLE (même risque moyen, réparti autrement) :
    volatilite : risque x (ATR% médian 1 an / ATR% actuel), borné 0,5-2 (Harvey et al. 2018, Moreira-Muir 2017)
    correlation: or et argent déjà ouverts dans le même sens -> le 2e trade à x0,7 (ils bougent ensemble)
  SORTIES :
    chandelier : stop suiveur k ATR derrière le prix en plus de la sortie canal (LeBeau)
  EMPILEMENT : le bot ajoute jusqu'à 2 positions sur la Cassure (EMPILER_MAX=3) ; JAMAIS mesuré sur 10 ans.

Méthode (la même que l'usine, plus stricte) :
  1. Réglage choisi sur 2017-2021 SEULEMENT (meilleur Sharpe mensuel).
  2. Jugé sur 2022 -> aujourd'hui, jamais vu, en 2 morceaux (2022-mi-2024 et mi-2024-aujourd'hui), avec spread,
     frais de nuit, prime du stop garanti.
  3. « Bat l'existant » seulement si, sur le jamais vu : Sharpe mensuel meilleur sur les 2 morceaux, R total au
     moins 95 % de l'actuel, pire baisse pas pire, ET la moitié des réglages voisins mieux aussi.
  4. Correction pour le nombre d'essais : on refait TOUTE la sélection (choix sur 2017-2021 puis mesure) avec des
     filtres/tailles TIRÉS AU HASARD de même taux de coupe (500 tirages). p = part des tirages qui font aussi bien ;
     puis Bonferroni : p x nombre de familles testées doit rester < 0,05.
  5. Contrôle sur prix au hasard (marche aléatoire) pour les sorties et l'empilement : l'écart doit y être ~0.

Usage : python backtest/ameliorations.py telecharger <dossier>  puis  python backtest/ameliorations.py <dossier>
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import serrage  # noqa: E402
from backtest.audit_chiffres import connecter  # noqa: E402
from backtest.reseaux import supertrend  # noqa: E402
from backtest.usine import conditions, lire  # noqa: E402
from bot.cassure import signaux_cassure  # noqa: E402
from bot.strategie import atr, ema, milieu  # noqa: E402

C1, C2 = pd.Timestamp("2022-01-01"), pd.Timestamp("2024-07-01")
CRYPTOS = ("ETHUSD", "BTCUSD", "SOLUSD", "XRPUSD", "LTCUSD")
GARDE = ("garde", 1.5, 0.5)
TIRAGES = int(__import__("os").getenv("TIRAGES", "500"))
RNG = np.random.default_rng(2611)


# ----------------------------------------------------------------------------- données
def telecharger(dossier: Path):
    from backtest import telecharger as t
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    for groupe in (("GOLD", "SILVER", "ETHUSD"), ("BTCUSD", "SOLUSD", "XRPUSD", "LTCUSD")):
        api = connecter()
        for epic in groupe:
            try:
                (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
                t.telecharger(api, epic, "HOUR_4", 240, 3650)
            except Exception as e:  # marché absent : on continue
                print(epic, "impossible :", e)
        api.deconnexion()


def cond_de(dossier, epic, df):
    c = conditions(dossier, epic, float(df.close_bid.iloc[-1]))
    c.setdefault("nuit_achat", 0.02)
    c.setdefault("nuit_vente", 0.02)
    return c


# ----------------------------------------------------------------------------- mesures
def mesures(t, w=None):
    """t : trades (date, R). Renvoie les chiffres par période, avec un poids éventuel par trade."""
    t = t.sort_values("date").copy()
    t["Rw"] = t.R * (1.0 if w is None else w.reindex(t.index).values)
    out = {}
    for nom, a, b in (("entrainement", None, C1), ("jamais_vu", C1, None), ("j1", C1, C2), ("j2", C2, None)):
        x = t
        if a is not None:
            x = x[x.date >= a]
        if b is not None:
            x = x[x.date < b]
        deb = a or pd.Timestamp("2017-05-01")
        fin = b or pd.Timestamp("2026-11-30")
        mois = x.groupby(x.date.dt.to_period("M")).Rw.sum().reindex(pd.period_range(deb, fin, freq="M"), fill_value=0)
        c = np.r_[0, np.cumsum(x.Rw.values)]
        out[nom] = {"R": round(float(x.Rw.sum()), 1), "trades": int(len(x)),
                    "sharpe": round(float(mois.mean() / mois.std() * np.sqrt(12)) if mois.std() > 0 else 0.0, 3),
                    "baisse": round(float((c - np.maximum.accumulate(c)).min()), 1)}
    return out


def bat(m, base):
    """Règle « bat vraiment l'existant » sur le jamais vu."""
    j, b = m["jamais_vu"], base["jamais_vu"]
    return (m["j1"]["sharpe"] > base["j1"]["sharpe"] and m["j2"]["sharpe"] > base["j2"]["sharpe"]
            and j["R"] >= 0.95 * b["R"] and j["baisse"] >= b["baisse"])


# ----------------------------------------------------------------------------- stratégies de base
def base_cassure(dossier):
    """Trades de la Cassure telle que le bot la joue + infos au moment du signal."""
    marches = {}
    for e in ("GOLD", "SILVER"):
        df = lire(dossier, e, "HOUR_4")
        sig = signaux_cassure(df, entree=20, sortie=20)
        c = sig.cible.values
        ok = np.r_[True, c[1:] != c[:-1]]
        cond = cond_de(dossier, e, df)
        marches[e] = {"df": df, "sig": sig, "c": c, "ok": ok, "cond": cond}
    trades = pd.concat([serrage_trades(marches, e) for e in marches], ignore_index=True)
    return trades, marches


def serrage_trades(marches, e):
    m = marches[e]
    t = serrage.simuler(m["df"], m["c"], m["ok"], m["sig"].stop.values, None, m["cond"], regle=GARDE)
    t["epic"] = e
    t["i"] = m["df"].index.get_indexer(t.date) - 1
    t["sens"] = m["c"][t.i.values]
    return t


def base_supertrend(dossier, epic):
    df = lire(dossier, epic, "HOUR_4")
    if df is None or len(df) < 3000:
        return None, None
    v, ok, ds, _ = supertrend(df)
    cond = cond_de(dossier, epic, df)
    t = serrage.simuler(df, v, ok, ds, None, cond)
    t["epic"] = epic
    t["i"] = df.index.get_indexer(t.date) - 1
    t["sens"] = v[t.i.values]
    return t, {epic: {"df": df, "v": v, "ok": ok, "ds": ds, "cond": cond}}


# ----------------------------------------------------------------------------- indicateurs des filtres
def jour(df):
    m = milieu(df)
    j = m.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    return j


def au_signal(serie_jour, df):
    """Valeur JOUR connue au moment de la bougie 4 h (veille terminée : aucun futur)."""
    return serie_jour.shift(1).reindex(df.index.floor("1D"), method="ffill").values


def indicateurs(df):
    m = milieu(df)
    j = jour(df)
    out = {}
    for L in (63, 126, 252):
        out[f"mom{L}"] = np.sign(au_signal(j.close / j.close.shift(L) - 1, df))
    for N in (20, 50, 100):
        ch = (m.close - m.close.shift(N)).abs()
        bruit = m.close.diff().abs().rolling(N).sum()
        out[f"er{N}"] = (ch / bruit).values
    out["vr"] = (atr(m, 14) / atr(m, 100)).values
    for N in (20, 50, 100):
        out[f"jema{N}"] = np.sign(m.close.values - au_signal(ema(j.close, N), df))
    a = atr(m) / m.close
    out["atrpct"] = a.values
    out["atrmed"] = a.rolling(6 * 252, min_periods=600).median().values
    return out


FILTRES = {
    "momentum": [(f"sens du prix sur {L} jours", lambda I, s, L=L: I[f"mom{L}"] == s, i) for i, L in enumerate((63, 126, 252))],
    "efficacite": [(f"efficacité {N} bougies >= {k:g}", lambda I, s, N=N, k=k: I[f"er{N}"] >= k, (a, b))
                   for a, N in enumerate((20, 50, 100)) for b, k in enumerate((0.15, 0.25, 0.35))],
    "calme": [(f"ATR14/ATR100 <= {k:g}", lambda I, s, k=k: I["vr"] <= k, a) for a, k in enumerate((0.8, 0.9, 1.0, 1.1, 1.2))],
    "agite": [(f"ATR14/ATR100 >= {k:g}", lambda I, s, k=k: I["vr"] >= k, a) for a, k in enumerate((0.8, 0.9, 1.0, 1.1, 1.2))],
    "jour_ema": [(f"bon côté de l'EMA {N} jour", lambda I, s, N=N: I[f"jema{N}"] == s, a) for a, N in enumerate((20, 50, 100))],
    "achats": [("achats seulement", lambda I, s: s > 0, 0)],
}


def voisins(params, choisi):
    """Réglages voisins (une case à côté dans la grille)."""
    out = []
    for p in params:
        if p == choisi:
            continue
        if isinstance(p, tuple):
            if sum(abs(x - y) for x, y in zip(p, choisi)) == 1:
                out.append(p)
        elif abs(p - choisi) == 1:
            out.append(p)
    return out


def masque(trades, I_par_epic, f):
    keep = np.zeros(len(trades), dtype=bool)
    for e, I in I_par_epic.items():
        sel = (trades.epic == e).values
        if not sel.any():
            continue
        idx = trades.i.values[sel]
        Is = {k: np.asarray(v)[idx] for k, v in I.items()}
        keep[sel] = np.broadcast_to(np.asarray(f(Is, trades.sens.values[sel])), (int(sel.sum()),))
    return keep


def tester_famille(nom, variantes, trades, I_par_epic, base, extra_masques=None):
    """Choix sur 2017-2021, mesure sur le jamais vu, voisins, puis correction par tirages au hasard."""
    lignes = []
    for libelle, f, p in variantes:
        k = masque(trades, I_par_epic, f) if f is not None else extra_masques[libelle]
        m = mesures(trades[k])
        lignes.append({"variante": libelle, "param": p, "garde_pct": round(100 * k.mean(), 1), "m": m, "k": k})
    choisi = max(lignes, key=lambda x: x["m"]["entrainement"]["sharpe"])
    vs = [x for x in lignes if x["param"] in voisins([y["param"] for y in lignes], choisi["param"])]
    vois_ok = sum(bat(x["m"], base) for x in vs)
    gain = choisi["m"]["jamais_vu"]["sharpe"] - base["jamais_vu"]["sharpe"]
    # correction : même sélection avec des coupes au hasard de même taux
    ent = (trades.date < C1).values
    nul = []
    for _ in range(TIRAGES):
        best, best_s = None, -9
        for x in lignes:
            kk = RNG.random(len(trades)) < x["k"].mean()
            s = mesures_rapides(trades, kk, ent)
            if s[0] > best_s:
                best_s, best = s[0], s[1]
        nul.append(best)
    p = float((np.array(nul) >= choisi["m"]["jamais_vu"]["sharpe"]).mean())
    return {"famille": nom, "choisi_sur_2017_2021": choisi["variante"], "garde_pct": choisi["garde_pct"],
            "resultat": choisi["m"], "gain_sharpe_jamais_vu": round(gain, 3), "bat_existant": bat(choisi["m"], base),
            "voisins_mieux": f"{vois_ok}/{len(vs)}", "voisins_ok": (vois_ok * 2 >= len(vs)) if vs else True,
            "p_hasard": round(p, 3),
            "toutes": [{"variante": x["variante"], "garde_pct": x["garde_pct"], "entrainement": x["m"]["entrainement"],
                        "jamais_vu": x["m"]["jamais_vu"]} for x in lignes]}


def mesures_rapides(trades, k, ent, w=None):
    """(Sharpe entraînement, Sharpe jamais vu) sans tout le détail (pour les 500 tirages)."""
    r = trades.R.values * (1.0 if w is None else w)
    mois = trades.date.dt.to_period("M").values
    out = []
    for sel, deb, fin in ((k & ent, "2017-05", "2021-12"), (k & ~ent, "2022-01", "2026-11")):
        s = pd.Series(r[sel]).groupby(mois[sel]).sum().reindex(pd.period_range(deb, fin, freq="M"), fill_value=0)
        out.append(float(s.mean() / s.std() * np.sqrt(12)) if s.std() > 0 else 0.0)
    return out


# ----------------------------------------------------------------------------- tailles
def poids_volatilite(trades, I_par_epic, puissance):
    w = np.ones(len(trades))
    for e, I in I_par_epic.items():
        sel = (trades.epic == e).values
        idx = trades.i.values[sel]
        x = (I["atrmed"][idx] / I["atrpct"][idx]) ** puissance
        w[sel] = np.nan_to_num(np.clip(x, 0.5, 2.0), nan=1.0)
    ent = (trades.date < C1).values
    return w / w[ent].mean()  # même risque moyen que l'actuel sur 2017-2021


def poids_correlation(trades, k):
    """Le 2e trade ouvert dans le même sens qu'une position déjà ouverte sur l'autre métal : risque x k."""
    w = np.ones(len(trades))
    for n, (d, s, e) in enumerate(zip(trades.date, trades.sens, trades.epic)):
        autres = trades[(trades.epic != e) & (trades.sens == s) & (trades.date < d) & (trades.fin > d)]
        if len(autres):
            w[n] = k
    ent = (trades.date < C1).values
    return w / w[ent].mean()


def tester_poids(nom, variantes, trades, base):
    lignes = []
    for libelle, w, p in variantes:
        m = mesures(trades, pd.Series(w, index=trades.index))
        lignes.append({"variante": libelle, "param": p, "m": m, "w": w})
    choisi = max(lignes, key=lambda x: x["m"]["entrainement"]["sharpe"])
    vs = [x for x in lignes if x["param"] in voisins([y["param"] for y in lignes], choisi["param"])]
    vois_ok = sum(bat(x["m"], base) for x in vs)
    ent = (trades.date < C1).values
    tous = np.ones(len(trades), dtype=bool)
    nul = []
    for _ in range(TIRAGES):  # mêmes poids mélangés au hasard entre les trades
        best, best_s = None, -9
        for x in lignes:
            s = mesures_rapides(trades, tous, ent, RNG.permutation(x["w"]))
            if s[0] > best_s:
                best_s, best = s[0], s[1]
        nul.append(best)
    p = float((np.array(nul) >= choisi["m"]["jamais_vu"]["sharpe"]).mean())
    if nom == "taille_correlation":  # mélanger les poids casse le lien avec les positions simultanées : tirage non valable
        p = None
    return {"famille": nom, "choisi_sur_2017_2021": choisi["variante"], "resultat": choisi["m"],
            "gain_sharpe_jamais_vu": round(choisi["m"]["jamais_vu"]["sharpe"] - base["jamais_vu"]["sharpe"], 3),
            "bat_existant": bat(choisi["m"], base), "voisins_mieux": f"{vois_ok}/{len(vs)}",
            "voisins_ok": (vois_ok * 2 >= len(vs)) if vs else True, "p_hasard": None if p is None else round(p, 3),
            "toutes": [{"variante": x["variante"], "entrainement": x["m"]["entrainement"],
                        "jamais_vu": x["m"]["jamais_vu"]} for x in lignes]}


# ----------------------------------------------------------------------------- sorties et empilement (re-simulés)
def cassure_avec(marches, dsuivi_k=None, empiler=1):
    tous = []
    for e, m in marches.items():
        df, sig, c, ok, cond = m["df"], m["sig"], m["c"], m["ok"], m["cond"]
        ds = sig.atr.values * dsuivi_k if dsuivi_k else None
        t = serrage.simuler(df, c, ok, sig.stop.values, ds, cond, regle=GARDE)
        t["epic"] = e
        tous.append(t)
        if empiler > 1:
            tous.append(empilements(df, c, sig, cond, t, empiler, e))
    return pd.concat(tous, ignore_index=True)


def empilements(df, c, sig, cond, t, maxi, e):
    """Comme le bot (bot/empilement.py) : une position de plus dans le même sens quand le prix a avancé d'1 R
    (distance du stop) depuis la dernière entrée, au plus `maxi` positions ; chacune a son propre stop garanti,
    la même sortie canal et la même garde 50 %."""
    m = milieu(df)
    clo, st = m.close.values, sig.stop.values
    out = []
    idx = df.index
    for _, tr in t.iterrows():
        i0 = idx.get_loc(tr.date)
        i1 = idx.get_loc(tr.fin)
        s = c[i0 - 1]
        dernier = (df.open_ask.values[i0] if s > 0 else df.open_bid.values[i0])
        n = 1
        # le canal reste dans le même sens jusqu'à fin_canal (la base a pu sortir avant, au stop ou à la garde)
        fin_canal = i0
        while fin_canal < len(c) - 1 and c[fin_canal] == s:
            fin_canal += 1
        j = i0 + 1
        while j < min(fin_canal, i1 + 1) and n < maxi:  # le bot n'empile que si une position est encore ouverte
            if (clo[j - 1] - dernier) * s >= st[j - 1]:
                a, b = max(0, j - 2), min(len(df), fin_canal + 2)
                v = np.zeros(b - a, dtype=int)
                v[j - 1 - a: fin_canal - a] = s
                ok = np.zeros(b - a, dtype=bool)
                ok[j - 1 - a] = True
                x = serrage.simuler(df.iloc[a:b], v, ok, st[a:b], None, cond, regle=GARDE)
                if len(x):
                    out.append(x.iloc[:1])
                    dernier = df.open_ask.values[j] if s > 0 else df.open_bid.values[j]
                    n += 1
            j += 1
    r = pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["date", "R", "raison", "fin"])
    r["epic"] = e
    r["empilement"] = True
    return r


def controle_hasard_sorties():
    """Sur une marche aléatoire, ces variantes ne doivent rien apporter (sinon : biais du test)."""
    argv, sys.argv = sys.argv, sys.argv[:1]  # audit_hasard lit sys.argv à l'import
    from backtest.audit_hasard import marche_aleatoire, regrouper
    sys.argv = argv
    res = []
    for g in range(4):
        d5 = marche_aleatoire(100 + g, 3000, pas_min=60, sous_pas=12)
        d4 = regrouper(d5, "4h")
        sig = signaux_cassure(d4, entree=20, sortie=20)
        c = sig.cible.values
        mm = {"X": {"df": d4, "sig": sig, "c": c, "ok": np.r_[True, c[1:] != c[:-1]],
                    "cond": {"nuit_achat": 0.0, "nuit_vente": 0.0, "min_pct": 0.25}}}
        b = cassure_avec(mm).R.mean()
        res.append({"graine": g, "R_trade_actuel": round(float(b), 3),
                    "chandelier_4ATR": round(float(cassure_avec(mm, dsuivi_k=4).R.mean()), 3),
                    "empilement_3": round(float(cassure_avec(mm, empiler=3).R.mean()), 3)})
    return res


# ----------------------------------------------------------------------------- gagner vite : simulation honnête
def monte_carlo(R, trades_par_an, depart=93.0, ans=1.0, n=20000):
    """Tire au hasard des années de trades parmi les vrais trades jamais vus, capital composé."""
    out = {}
    k = int(trades_par_an * ans)
    for risque in (1, 3, 5, 10, 20, 30):
        tir = RNG.choice(R, size=(n, k))
        fac = np.clip(1 + tir * risque / 100, 0, None)
        chemin = depart * np.cumprod(fac, axis=1)
        fin = chemin[:, -1]
        pic = np.maximum.accumulate(np.c_[np.full(n, depart), chemin], axis=1)
        dd = ((np.c_[np.full(n, depart), chemin] - pic) / pic).min(axis=1)
        out[f"{risque} %"] = {"mediane_€": round(float(np.median(fin)), 0),
                              "chance_x10_%": round(float((fin >= 10 * depart).mean() * 100), 1),
                              "chance_perte_%": round(float((fin < depart).mean() * 100), 1),
                              "chance_baisse_50%_en_route": round(float((dd <= -0.5).mean() * 100), 1),
                              "chance_compte_sous_10€": round(float((fin < 10).mean() * 100), 1)}
    return out


# ----------------------------------------------------------------------------- principal
def principal(dossier: Path):
    res = {"methode": __doc__.split("Méthode")[1][:200].strip()}
    familles = []

    # ---------- Cassure or + argent
    trades, marches = base_cassure(dossier)
    base = mesures(trades)
    res["cassure_actuelle"] = base
    I = {e: indicateurs(m["df"]) for e, m in marches.items()}
    for nom, variantes in FILTRES.items():
        familles.append(("Cassure", tester_famille(nom, variantes, trades, I, base)))
    # jumeau : état de la Cassure de l'autre métal au moment du signal
    jum = {}
    for libelle, regle in (("l'autre métal pas en sens opposé", "pas_oppose"), ("l'autre métal dans le même sens", "meme")):
        k = np.zeros(len(trades), dtype=bool)
        for n, tr in enumerate(trades.itertuples()):
            autre = "SILVER" if tr.epic == "GOLD" else "GOLD"
            ma = marches[autre]
            j = ma["df"].index.searchsorted(trades.date.iat[n]) - 1
            etat = ma["c"][j] if j >= 0 else 0
            k[n] = (etat != -tr.sens) if regle == "pas_oppose" else (etat == tr.sens)
        jum[libelle] = k
    familles.append(("Cassure", tester_famille("jumeau", [(l, None, i) for i, l in enumerate(jum)], trades, I, base, jum)))
    familles.append(("Cassure", tester_poids("taille_volatilite",
                                             [(f"risque x (ATR médian/ATR)^{p:g}", poids_volatilite(trades, I, p), i)
                                              for i, p in enumerate((0.5, 1.0, 1.5))], trades, base)))
    familles.append(("Cassure", tester_poids("taille_correlation",
                                             [(f"2e métal même sens x{k:g}", poids_correlation(trades, k), i)
                                              for i, k in enumerate((0.5, 0.7, 0.85))], trades, base)))
    # sorties chandelier
    ch = []
    for i, k in enumerate((3, 4, 5, 6, 8)):
        m = mesures(cassure_avec(marches, dsuivi_k=k))
        ch.append({"variante": f"suiveur {k} ATR", "param": i, "m": m})
    choisi = max(ch, key=lambda x: x["m"]["entrainement"]["sharpe"])
    vs = [x for x in ch if abs(x["param"] - choisi["param"]) == 1]
    familles.append(("Cassure", {"famille": "chandelier", "choisi_sur_2017_2021": choisi["variante"], "resultat": choisi["m"],
                                 "gain_sharpe_jamais_vu": round(choisi["m"]["jamais_vu"]["sharpe"] - base["jamais_vu"]["sharpe"], 3),
                                 "bat_existant": bat(choisi["m"], base),
                                 "voisins_mieux": f"{sum(bat(x['m'], base) for x in vs)}/{len(vs)}",
                                 "voisins_ok": sum(bat(x["m"], base) for x in vs) * 2 >= len(vs), "p_hasard": None,
                                 "toutes": [{"variante": x["variante"], "entrainement": x["m"]["entrainement"],
                                             "jamais_vu": x["m"]["jamais_vu"]} for x in ch]}))
    # empilement : ce que le bot fait VRAIMENT (EMPILER_MAX=3) contre 1 seule position
    emp = {}
    for n in (1, 2, 3):
        t = cassure_avec(marches, empiler=n)
        emp[f"{n} position(s) max"] = {"tout": mesures(t), "positions_ajoutees": int(t.get("empilement", pd.Series(dtype=bool)).fillna(False).sum())}
    res["cassure_empilement"] = emp
    res["controle_hasard_sorties_empilement"] = controle_hasard_sorties()

    # ---------- Supertrend ETH + autres cryptos
    st = {}
    for epic in CRYPTOS:
        t, mm = base_supertrend(dossier, epic)
        if t is None:
            st[epic] = "pas assez de données"
            continue
        st[epic] = mesures(t)
        if epic == "ETHUSD":
            b = st[epic]
            Ie = {epic: indicateurs(mm[epic]["df"])}
            for nom in ("momentum", "efficacite", "calme", "agite", "jour_ema"):
                familles.append(("Supertrend ETH", tester_famille(nom, FILTRES[nom], t, Ie, b)))
            familles.append(("Supertrend ETH", tester_poids("taille_volatilite",
                                                            [(f"risque x (ATR médian/ATR)^{p:g}", poids_volatilite(t, Ie, p), i)
                                                             for i, p in enumerate((0.5, 1.0, 1.5))], t, b)))
            res["supertrend_trades_jamais_vu"] = t[t.date >= C1].R.round(3).tolist()
    res["supertrend_marches"] = st

    # ---------- verdict avec correction pour le nombre de familles
    nf = len(familles)
    verdicts = []
    for strat, f in familles:
        p = f["p_hasard"]
        f["p_corrige"] = None if p is None else round(min(1.0, p * nf), 3)
        f["solide"] = bool(f["bat_existant"] and f["voisins_ok"] and (p is None or p * nf < 0.05))
        verdicts.append({"strategie": strat, **{k: v for k, v in f.items() if k != "toutes"}})
    res["familles_testees"] = nf
    res["verdicts"] = verdicts
    res["details"] = [{"strategie": s, "famille": f["famille"], "toutes": f["toutes"]} for s, f in familles]

    # ---------- gagner beaucoup très vite : simulation sur les vrais trades jamais vus (Cassure + Supertrend)
    Rv = np.r_[trades[trades.date >= C1].R.values, np.array(res.get("supertrend_trades_jamais_vu", []))]
    par_an = len(Rv) / ((pd.Timestamp("2026-11-26") - C1).days / 365.25)
    res["gagner_vite"] = {"trades_par_an": round(par_an, 1), "R_moyen": round(float(Rv.mean()), 3),
                          "1_an_depuis_93€": monte_carlo(Rv, par_an)}

    for strat, f in familles:
        print(f"{strat:15s} {f['famille']:20s} choisi={f['choisi_sur_2017_2021']:40s} "
              f"jamais_vu={json.dumps(f['resultat']['jamais_vu'])} gain_sharpe={f['gain_sharpe_jamais_vu']:+.3f} "
              f"bat={f['bat_existant']} voisins={f['voisins_mieux']} p_corr={f['p_corrige']} SOLIDE={f['solide']}")
    print("Cassure actuelle :", json.dumps(base))
    print("Empilement :", json.dumps(emp))
    print("Hasard :", json.dumps(res["controle_hasard_sorties_empilement"]))
    print("Supertrend :", json.dumps(st))
    print("Gagner vite :", json.dumps(res["gagner_vite"], ensure_ascii=False))
    res.pop("supertrend_trades_jamais_vu", None)
    Path(__file__).resolve().parent.joinpath("resultats_ameliorations.json").write_text(
        json.dumps(res, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    if sys.argv[1] == "telecharger":
        telecharger(Path(sys.argv[2]))
    else:
        principal(Path(sys.argv[1]))

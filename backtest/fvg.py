"""STRATÉGIE « FVG + FIBONACCI » sur l'or et l'argent (26/11/2026, demande de Mathis).

Idée vue chez un ami (robot « FVG Anthony », or XAUUSD) : décisions sur bougies de 15 min, on repère un
« fair value gap » (FVG : trou laissé entre la bougie 1 et la bougie 3 d'un mouvement rapide), puis on entre
quand le prix revient dans la zone de Fibonacci 0,50 -> 0,78 du mouvement, stop sous le départ du mouvement,
sortie en 3 tiers. Achat et vente, 1 % de risque par trade.

Ce script répond à UNE question : est-ce que ça gagne vraiment, sur ~10 ans, frais compris, sur des années
JAMAIS VUES pendant le choix des réglages ? Même rigueur que l'usine à stratégies (backtest/usine.py) :
  - ENTRAÎNEMENT : début (~2017) -> 31/12/2021, seule période qui sert à choisir ;
  - VALIDATION   : 01/2022 -> 06/2024, jamais vue ;  TEST FINAL : 07/2024 -> aujourd'hui, jamais vu ;
  - voisins (un cran de plus/moins sur chaque réglage), 60 % des années gagnantes, frais x1,5 (stress),
    pire baisse > -20 R, « Deflated Sharpe » >= 0,95 (pénalité du nombre d'essais).

Règles simulées (bougies 15 min, prix acheteur/vendeur réels donc spread compris) :
  FVG haussier à la bougie i : plus bas(i) - plus haut(i-2) >= seuil (en ATR 14, ou 25 pips = 2,5 $ façon Anthony).
  Mouvement : départ A = plus bas des L dernières bougies, sommet B = plus haut des 3 bougies du FVG.
  Ordre limite d'achat au niveau Fibonacci f (0,5 / 0,618 / 0,705 / 0,78) du mouvement, actif « exp » bougies.
  Annulé si le prix repasse au-dessus de B avant d'être servi (option). Stop sous A (option : 10 % de marge).
  Options : confluence (le niveau doit être dans le trou du FVG), filtre de tendance (moyenne 800 bougies
  = moyenne 200 en 1 h), heures 7 h-20 h UTC seulement. Une position à la fois. Clôture forcée après 24 h.
  Sorties comparées : objectif unique (1 / 1,5 / 2 / 3 R ou sommet B) contre 3 tiers (1-2-3 R, avec ou sans
  stop au prix d'entrée après le 1er tiers ; ou B / extension 1,27 / 1,618).
  Pessimiste : si stop et objectif sont dans la même bougie, c'est le stop. Pas d'objectif sur la bougie d'entrée.

Usage :
  python backtest/fvg.py capital <dossier>         (GitHub Actions, clés de la démo)
  python backtest/fvg.py completer <dossier>       (début de l'historique par Dukascopy si Capital.com est trop court)
  python backtest/fvg.py fouiller <dossier> <sortie.json>
"""
import io
import itertools
import json
import lzma
import math
import os
import struct
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest.usine import (DEBUT_TEST, DEBUT_VALIDATION, conditions, deflated_sharpe,  # noqa: E402
                            esperance_max, lire, stats, taux_eur)

MARCHES = {"GOLD": "XAUUSD", "SILVER": "XAGUSD"}  # Capital.com -> Dukascopy (secours si l'historique 15 min est court)
PIP = {"GOLD": 0.1, "SILVER": 0.01}  # 1 pip MT5 (Exness) : 0,1 $ sur l'or
DUREE_MAX = 96  # bougies de 15 min = 24 h
COMPTE_EUR = 93.0

# ---------------------------------------------------------------------------- grille (décidée AVANT de lancer)
SEUILS = (0.15, 0.3, 0.5, 0.8)        # taille mini du trou en ATR 14
LOOKS = (8, 16, 32)                   # bougies pour trouver le départ du mouvement
FIBS = (0.5, 0.618, 0.705, 0.78)      # niveau d'entrée
STOPS = (0.0, 0.1)                    # marge du stop sous le départ (fraction du mouvement)
EXPS = (12, 48)                       # durée de vie de l'ordre (bougies)
ANNULS = (0, 1)                       # annuler si nouveau sommet avant l'entrée
CONFS = (0, 1)                        # niveau d'entrée dans le trou du FVG
TENDS = (0, 1)                        # filtre de tendance
SESS = (0, 1)                         # 7 h-20 h UTC seulement
AXES = (SEUILS, LOOKS, FIBS, STOPS, EXPS, ANNULS, CONFS, TENDS, SESS)
NOMS_AXES = ("seuil_atr", "depart_bougies", "fibo", "marge_stop", "vie_ordre", "annule_si_sommet", "confluence",
             "tendance", "heures_7_20")
# sorties : (nom, type cible, cibles, stop au prix d'entrée après le 1er tiers)
SORTIES = (
    ("unique 1 R", "R", (1, 1, 1), 0), ("unique 1,5 R", "R", (1.5, 1.5, 1.5), 0), ("unique 2 R", "R", (2, 2, 2), 0),
    ("unique 3 R", "R", (3, 3, 3), 0), ("unique sommet B", "F", (0, 0, 0), 0),
    ("3 tiers 1-2-3 R", "R", (1, 2, 3), 0), ("3 tiers 1-2-3 R + stop à l'entrée", "R", (1, 2, 3), 1),
    ("3 tiers B / 1,27 / 1,618", "F", (0, 0.27, 0.618), 0), ("3 tiers B / 1,27 / 1,618 + stop à l'entrée", "F", (0, 0.27, 0.618), 1),
)
UNIQUES = [k for k, s in enumerate(SORTIES) if s[0].startswith("unique")]
TIERS = [k for k, s in enumerate(SORTIES) if s[0].startswith("3 tiers")]


# =========================================================================== 1. données
def _p(*a):
    print(*a, flush=True)


def telecharger_capital(dossier: Path):
    """Bougies 15 min bid + ask de Capital.com (le courtier du bot), ~10 ans si elles existent."""
    from backtest import telecharger as t
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    for epic in MARCHES:
        api = CapitalDemo(cle, ident, mdp)
        api.connexion()
        (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
        debut = time.time()
        try:
            t.telecharger(api, epic, "MINUTE_15", 15, int(os.getenv("JOURS_CAPITAL", "3650")))
        except Exception as e:
            _p(f"{epic} MINUTE_15 Capital.com : échec ({str(e)[:150]})")
        _p(f"{epic} : Capital.com en {time.time() - debut:.0f} s")
        api.deconnexion()


def dukascopy(sym: str, debut: date, fin: date, ecart_rel: float) -> pd.DataFrame:
    """Bougies 1 min (prix vendeur) de Dukascopy (gratuit), regroupées en 15 min ; prix acheteur = vendeur + spread
    relatif de Capital.com (le vrai coût chez notre courtier)."""
    import threading

    import requests
    local = threading.local()

    def jour(d):
        if not hasattr(local, "s"):
            local.s = requests.Session()
            local.s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        url = f"https://datafeed.dukascopy.com/datafeed/{sym}/{d.year}/{d.month - 1:02d}/{d.day:02d}/BID_candles_min_1.bi5"
        for essai in range(3):
            try:
                r = local.s.get(url, timeout=10)
                if r.status_code == 404 or not r.content:
                    return None
                if r.status_code != 200:
                    raise RuntimeError(r.status_code)
                brut = lzma.decompress(r.content)
                n = len(brut) // 24
                v = np.frombuffer(brut[:n * 24], dtype=">u4").reshape(n, 6)
                t = pd.Timestamp(d) + pd.to_timedelta(v[:, 0].astype(np.int64), unit="s")
                p = v[:, 1:5].astype(float) / 1000.0  # open, close, low, high
                vol = np.frombuffer(brut[:n * 24], dtype=">f4").reshape(n, 6)[:, 5]
                return pd.DataFrame({"open": p[:, 0], "close": p[:, 1], "low": p[:, 2], "high": p[:, 3], "vol": vol}, index=t)
            except Exception:
                time.sleep(0.5 + essai)
        return None

    jours = [debut + timedelta(days=k) for k in range((fin - debut).days + 1)]
    jours = [d for d in jours if d.weekday() != 5]
    # diagnostic sur un jour connu (mercredi 2019-03-06) : code HTTP, taille, début de la réponse
    try:
        essai = requests.get(f"https://datafeed.dukascopy.com/datafeed/{sym}/2019/02/06/BID_candles_min_1.bi5", timeout=20,
                             headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"})
        _p(f"  diagnostic Dukascopy : HTTP {essai.status_code}, {len(essai.content)} octets, "
           f"type {essai.headers.get('content-type')}, début {essai.content[:16]!r}")
        if essai.content:
            _p(f"  décompressé : {len(lzma.decompress(essai.content))} octets")
    except Exception as e:
        _p(f"  diagnostic Dukascopy : erreur {type(e).__name__} {str(e)[:200]}")
    morceaux, t0 = [], time.time()
    with ThreadPoolExecutor(24) as ex:
        for k, m in enumerate(ex.map(jour, jours)):
            if m is not None and len(m):
                morceaux.append(m[m.vol > 0] if (m.vol > 0).mean() > 0.5 else m)
            if k % 500 == 0:
                _p(f"  {sym} : {k}/{len(jours)} jours ({time.time() - t0:.0f} s)")
    if not morceaux:
        raise SystemExit(f"{sym} : Dukascopy n'a renvoyé aucune bougie")
    _p(f"  {sym} : {len(morceaux)} jours reçus sur {len(jours)}")
    m = pd.concat(morceaux).sort_index()
    b = m.resample("15min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    d = pd.DataFrame({"date": b.index.strftime("%Y-%m-%dT%H:%M:%S")})
    for x in ("open", "high", "low", "close"):
        d[f"{x}_bid"], d[f"{x}_ask"] = b[x].values, b[x].values * (1 + ecart_rel)
    d["volume"] = 0
    return d


def completer(dossier: Path):
    """Si Capital.com n'a pas ~10 ans en 15 min, on complète le DÉBUT avec Dukascopy."""
    for epic, sym in MARCHES.items():
        f = dossier / f"{epic}_MINUTE_15.csv"
        cap = pd.read_csv(f) if f.exists() else pd.DataFrame()
        premier = pd.Timestamp(cap.date.min()) if len(cap) else pd.Timestamp("2100-01-01")
        _p(f"{epic} : Capital.com 15 min depuis {premier} ({len(cap)} bougies)")
        if premier <= pd.Timestamp("2017-06-01"):
            continue
        if len(cap):
            r = cap.dropna(subset=["close_ask"]).tail(20000)
            ecart = float(((r.close_ask - r.close_bid) / r.close_bid).median())
        else:
            ecart = 0.0002 if epic == "GOLD" else 0.0008
        fin = (premier - pd.Timedelta(days=1)).date() if len(cap) else datetime.now(timezone.utc).date()
        _p(f"{epic} : complété par Dukascopy ({sym}) de 2016-11 à {fin}, spread Capital.com {ecart * 100:.4f} %")
        duk = dukascopy(sym, date(2016, 11, 1), fin, ecart)
        tout = pd.concat([duk, cap[duk.columns]]) if len(cap) else duk
        tout.to_csv(f, index=False)
        (dossier / f"{epic}_source.txt").write_text(f"Dukascopy jusqu'au {fin} (spread de Capital.com), puis Capital.com\n")
        _p(f"{epic} : {len(tout)} bougies au total, depuis {tout.date.min()}")


# =========================================================================== 2. simulation vectorisée
class Donnees:
    def __init__(self, df: pd.DataFrame, cond: dict, cout: float = 1.0):
        mid = {k: ((df[f"{k}_bid"] + df[f"{k}_ask"]) / 2).values for k in ("open", "high", "low", "close")}
        demi = {k: ((df[f"{k}_ask"] - df[f"{k}_bid"]) / 2).values * cout for k in ("open", "high", "low", "close")}
        self.mo, self.mh, self.ml, self.mc = mid["open"], mid["high"], mid["low"], mid["close"]
        self.ob, self.oa = self.mo - demi["open"], self.mo + demi["open"]
        self.hb, self.ha = self.mh - demi["high"], self.mh + demi["high"]
        self.lb, self.la = self.ml - demi["low"], self.ml + demi["low"]
        self.cb, self.ca = self.mc - demi["close"], self.mc + demi["close"]
        self.glisse = float(np.nanmedian(demi["close"])) * 0.5  # glissement sur les stops : 1/4 de spread
        self.n = len(df)
        self.t = df.index
        pc = np.r_[self.mc[0], self.mc[:-1]]
        tr = np.maximum(self.mh - self.ml, np.maximum(abs(self.mh - pc), abs(self.ml - pc)))
        self.atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
        self.ema = pd.Series(self.mc).ewm(span=800, adjust=False).mean().values
        h = self.t.hour
        self.heures_ok = (h >= 7) & (h < 20)
        # nuits : nombre de passages à 22 h UTC depuis le début (frais de nuit)
        self.jour_frais = (self.t - pd.Timedelta(hours=22)).values.astype("datetime64[D]").astype(np.int64)
        self.nuit_achat = cond.get("nuit_achat", 0.02) / 100 * cout
        self.nuit_vente = cond.get("nuit_vente", 0.02) / 100 * cout
        self.annee = self.t.year.values
        self.mois = (self.t.year.values * 100 + self.t.month.values)
        self.cache = {}

    def fvg(self, seuil, look, pips=None):
        """Tous les FVG (haussiers +1, baissiers -1) : indices, sens, A (départ), B (sommet), bord du trou."""
        cle = (seuil, look, pips)
        if cle in self.cache:
            return self.cache[cle]
        mh, ml, n = self.mh, self.ml, self.n
        i = np.arange(max(look, 3), n - 1)
        mini = pips if pips is not None else seuil * self.atr[i - 1]
        haut = ml[i] - mh[i - 2] >= mini
        bas = ml[i - 2] - mh[i] >= mini
        bas_glis = pd.Series(ml).rolling(look, min_periods=1).min().values
        haut_glis = pd.Series(mh).rolling(look, min_periods=1).max().values
        b3h = np.maximum.reduce([mh[i], mh[i - 1], mh[i - 2]])
        b3l = np.minimum.reduce([ml[i], ml[i - 1], ml[i - 2]])
        ih, ib = i[haut], i[bas]
        res = (np.r_[ih, ib], np.r_[np.ones(len(ih)), -np.ones(len(ib))],
               np.r_[bas_glis[ih], haut_glis[ib]],                  # A : départ du mouvement
               np.r_[b3h[haut], b3l[bas]],                          # B : bout du mouvement
               np.r_[mh[ih - 2], ml[ib - 2]],                       # bord éloigné du trou
               np.r_[ml[ih], mh[ib]])                               # bord proche du trou
        o = np.argsort(res[0], kind="stable")
        res = tuple(r[o] for r in res)
        self.cache[cle] = res
        return res

    def entrees(self, p, pips=None):
        """Ordres limites servis : (indice, sens, prix d'entrée, stop, A, B)."""
        seuil, look, fib, marge, exp, annul, conf, tend, sess = p
        i, d, A, B, loin, proche = self.fvg(seuil, look, pips)
        jambe = (B - A) * d
        ok = jambe > 0
        if tend:
            ok &= (self.mc[i] - self.ema[i]) * d > 0
        if sess:
            ok &= self.heures_ok[i]
        niv = B - d * fib * jambe
        if conf:  # niveau d'entrée dans le trou (entre le bord éloigné et le bord proche)
            ok &= ((niv - loin) * d >= 0) & ((proche - niv) * d >= 0)
        stop = A - d * marge * jambe
        i, d, niv, stop, A, B, jambe = (x[ok] for x in (i, d, niv, stop, A, B, jambe))
        n = self.n
        servi = np.full(len(i), -1)
        prix = np.zeros(len(i))
        actif = np.ones(len(i), dtype=bool)
        ach = d > 0
        for k in range(1, exp + 1):
            j = np.minimum(i + k, n - 1)
            actif &= (i + k) < n
            touche = np.where(ach, self.la[j] <= niv, self.hb[j] >= niv)
            annule = np.where(ach, self.mh[j] > B, self.ml[j] < B) if annul else np.zeros(len(i), dtype=bool)
            neuf = actif & touche & ~annule
            servi[neuf] = j[neuf]
            prix[neuf] = np.where(ach, np.minimum(niv, self.oa[j]), np.maximum(niv, self.ob[j]))[neuf]
            actif &= ~(touche | annule)
        m = servi >= 0
        risque = (prix - stop) * d
        m &= risque > 0.05 * self.atr[np.maximum(servi, 0)]  # stop absurde (collé au prix) : ignoré
        o = np.argsort(servi[m], kind="stable")  # ordre chronologique des ENTRÉES (sinon le tri « une position
        return tuple(x[m][o] for x in (servi, d, prix, stop, A, B, jambe))  # à la fois » regarderait le futur)

    def sorties(self, e):
        """Pour chaque entrée et chaque sortie de SORTIES : (indice de fin, résultat en R). Matrices (sorties x entrées)."""
        servi, d, prix, stop, A, B, jambe = e
        ns, ne = len(SORTIES), len(servi)
        risque = (prix - stop) * d
        cibles = np.zeros((ns, 3, ne))
        be = np.zeros((ns, 1), dtype=bool)
        for k, (_, typ, cs, b) in enumerate(SORTIES):
            for t in range(3):
                cibles[k, t] = prix + d * cs[t] * risque if typ == "R" else B + d * cs[t] * jambe
            be[k] = bool(b)
        # une cible déjà dépassée à l'entrée (ex. B sous le prix servi) : prise au 1er tick suivant
        stop_c = np.broadcast_to(stop, (ns, ne)).copy()
        reste = np.ones((ns, ne))
        pnl = np.zeros((ns, ne))
        fait = np.zeros((ns, ne), dtype=bool)
        fin = np.full((ns, ne), -1)
        pris = np.zeros((ns, 3, ne), dtype=bool)
        ach = d > 0
        n = self.n
        for k in range(0, DUREE_MAX + 1):
            j = np.minimum(servi + k, n - 1)
            dernier = (k == DUREE_MAX) | (servi + k >= n - 1)
            bas = np.where(ach, self.lb[j], self.la[j])     # prix de sortie défavorable (côté vendeur pour un achat)
            haut = np.where(ach, self.hb[j], self.ha[j])
            ouv = np.where(ach, self.ob[j], self.oa[j])
            # stop
            touche = ~fait & np.where(ach, bas <= stop_c, haut >= stop_c)
            px = np.where(ach, np.minimum(stop_c, ouv) - self.glisse, np.maximum(stop_c, ouv) + self.glisse) if k \
                else np.where(ach, stop_c - self.glisse, stop_c + self.glisse)
            pnl += np.where(touche, reste * (px - prix) * d, 0)
            reste = np.where(touche, 0, reste)
            fin = np.where(touche, j, fin)
            fait |= touche
            if k:
                for t in range(3):
                    tt = ~fait & ~pris[:, t] & np.where(ach, haut >= cibles[:, t], bas <= cibles[:, t])
                    pxc = np.where(ach, np.maximum(cibles[:, t], ouv), np.minimum(cibles[:, t], ouv))
                    pnl += np.where(tt, (pxc - prix) * d / 3, 0)
                    reste = np.where(tt, reste - 1 / 3, reste)
                    pris[:, t] |= tt
                    if t == 0:
                        stop_c = np.where(tt & be, prix, stop_c)
                fini = ~fait & (reste < 1e-9)
                fin = np.where(fini, j, fin)
                fait |= fini
            if dernier.any():
                cl = np.where(ach, self.cb[j], self.ca[j])
                force = ~fait & dernier
                pnl += np.where(force, reste * (cl - prix) * d, 0)
                fin = np.where(force, j, fin)
                fait |= force
            if fait.all():
                break
        # frais de nuit
        nuits = np.maximum(self.jour_frais[np.maximum(fin, 0)] - self.jour_frais[servi], 0)
        taux = np.where(ach, self.nuit_achat, self.nuit_vente)
        pnl -= nuits * taux * prix
        return fin, pnl / risque

    def simuler(self, p, pips=None):
        """Renvoie, pour chaque sortie, la liste des trades (indice d'entrée, R) en une position à la fois."""
        e = self.entrees(p, pips)
        if not len(e[0]):
            return [(np.zeros(0, dtype=int), np.zeros(0)) for _ in SORTIES], e
        fin, r = self.sorties(e)
        servi = e[0]
        out = []
        for k in range(len(SORTIES)):
            garde = np.zeros(len(servi), dtype=bool)
            der = -1
            fk = fin[k]
            for q in range(len(servi)):
                if servi[q] > der:
                    garde[q] = True
                    der = fk[q]
            out.append((servi[garde], r[k][garde]))
        return out, e


# =========================================================================== 3. fouille + contrôles
def decoupe(D: Donnees, idx):
    t = D.t[idx]
    return t < DEBUT_VALIDATION, (t >= DEBUT_VALIDATION) & (t < DEBUT_TEST), t >= DEBUT_TEST


def resume_trades(D: Donnees, idx, r):
    a, v, t = decoupe(D, idx)
    ans = {}
    for y in np.unique(D.annee[idx]) if len(idx) else []:
        ans[int(y)] = round(float(r[D.annee[idx] == y].sum()), 2)
    return {"entrainement": stats(r[a]), "validation": stats(r[v]), "test": stats(r[t]), "jamais_vu": stats(r[v | t]),
            "annees": ans}


def mensuel(D: Donnees, idx, r, mois):
    s = pd.Series(r, index=D.mois[idx]).groupby(level=0).sum()
    return np.array([float(s.get(m, 0.0)) for m in mois])


def texte(p, s):
    seuil, look, fib, marge, exp, annul, conf, tend, sess = p
    return (f"FVG >= {seuil} ATR, départ {look} bougies, entrée Fibo {fib}, stop {'sous le départ' if not marge else '+10 %'}, "
            f"ordre {exp} bougies{', annulé si nouveau sommet' if annul else ''}{', dans le trou' if conf else ''}"
            f"{', avec la tendance' if tend else ''}{', 7h-20h UTC' if sess else ''} ; sortie {SORTIES[s][0]}")


def voisins(cle):
    p, s = cle
    pos = [AXES[a].index(p[a]) for a in range(len(AXES))]
    for a in range(len(AXES)):
        for dd in (-1, 1):
            q = pos[a] + dd
            if 0 <= q < len(AXES[a]):
                v = list(p)
                v[a] = AXES[a][q]
                yield (tuple(v), s)
    for dd in (-1, 1):  # sortie voisine dans la même famille (unique <-> unique, tiers <-> tiers)
        fam = UNIQUES if s in UNIQUES else TIERS
        q = fam.index(s) + dd
        if 0 <= q < len(fam):
            yield (p, fam[q])


def fouiller(dossier: Path, sortie: Path, garder: int = 40):
    t0 = time.time()
    resultat = {"date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "periodes": {"entrainement": "début -> 2021-12-31", "validation": "2022-01-01 -> 2024-06-30",
                             "test_final": "2024-07-01 -> fin"},
                "grille": dict(zip(NOMS_AXES, [list(a) for a in AXES])), "sorties": [s[0] for s in SORTIES],
                "marches": {}}
    tous_cands, essais = [], 0
    for epic in MARCHES:
        df = lire(dossier, epic, "MINUTE_15")
        if df is None or len(df) < 5000:
            print(f"{epic} : pas de données")
            continue
        cond = conditions(dossier, epic, float(df.close_bid.iloc[-1]))
        src = (dossier / f"{epic}_source.txt")
        D = Donnees(df, cond)
        S = Donnees(df, cond, cout=1.5)
        print(f"{epic} : {len(df)} bougies 15 min, {df.index[0]} -> {df.index[-1]}, spread médian "
              f"{float((df.close_ask - df.close_bid).median()):.3f}")
        fin_mois = df.index[-1].strftime("%Y-%m")
        mois_jv = [int(m.replace("-", "")) for m in pd.period_range("2022-01", fin_mois, freq="M").strftime("%Y-%m")]
        mois_tr = [int(m.replace("-", "")) for m in pd.period_range(df.index[0].strftime("%Y-%m"), "2021-12", freq="M").strftime("%Y-%m")]
        table = {}
        srs_tr = []
        for q, p in enumerate(itertools.product(*AXES)):
            if q % 500 == 0:
                _p(f"  {epic} : {q} réglages d'entrée testés ({time.time() - t0:.0f} s)")
            res, _ = D.simuler(p)
            for s, (idx, r) in enumerate(res):
                a, v, t = decoupe(D, idx)
                st = stats(r[a])
                table[(p, s)] = (st, float(r[v].sum()), float(r[t].sum()), int(v.sum()), int(t.sum()))
                if st["n"] >= 30:
                    x = mensuel(D, idx[a], r[a], mois_tr)
                    if x.std() > 0:
                        srs_tr.append(x.mean() / x.std(ddof=1))
        essais += len(table)
        _p(f"{epic} : {len(table)} combinaisons en {time.time() - t0:.0f} s")

        # comparaison des sorties (moyenne sur TOUTES les entrées, jamais vu) : 3 tiers contre sortie unique
        comp = {}
        for s, nom in enumerate(SORTIES):
            jv = [table[(p, s)][1] + table[(p, s)][2] for p in itertools.product(*AXES)]
            tr = [table[(p, s)][0]["R"] for p in itertools.product(*AXES)]
            comp[nom[0]] = {"entrainement_R_moyen": round(float(np.mean(tr)), 2), "jamais_vu_R_moyen": round(float(np.mean(jv)), 2),
                            "part_gagnante_jamais_vu": round(float(np.mean(np.array(jv) > 0)), 3)}

        # choix sur l'entraînement uniquement
        bons = [(k, v) for k, v in table.items() if v[0]["n"] >= 100 and v[0]["pf"] >= 1.1 and v[0]["t"] >= 2]
        bons.sort(key=lambda kv: -kv[1][0]["t"])
        cands = []
        for k, v in bons[:garder]:
            vs = [table[w] for w in voisins(k) if w in table]
            vois_tr = float(np.mean([w[0]["R"] > 0 for w in vs])) if vs else 0
            vois_jv = float(np.mean([w[1] + w[2] > 0 for w in vs])) if vs else 0
            res, e = D.simuler(k[0])
            idx, r = res[k[1]]
            rs, _ = S.simuler(k[0])
            idx_s, r_s = rs[k[1]]
            jv_s = D.t[idx_s] >= DEBUT_VALIDATION
            c = {"epic": epic, "params": dict(zip(NOMS_AXES, k[0])), "sortie": SORTIES[k[1]][0], "texte": texte(*k),
                 **resume_trades(D, idx, r), "voisins_entrainement_positifs": round(vois_tr, 2),
                 "voisins_jamais_vu_positifs": round(vois_jv, 2), "stress": stats(r_s[jv_s]),
                 "trades_par_mois": round(len(idx) / max(1, (D.t[-1] - D.t[0]).days / 30.4), 1),
                 "risque_median_pct_du_prix": round(float(np.median(np.abs(e[2] - e[3]) / e[2]) * 100), 3),
                 "stop_sous_mini_garanti_pct": round(float(np.mean(np.abs(e[2] - e[3]) / e[2] * 100 < cond.get("min_pct", 0.25))) * 100, 1),
                 "_serie": mensuel(D, idx[D.t[idx] >= DEBUT_VALIDATION], r[D.t[idx] >= DEBUT_VALIDATION], mois_jv)}
            cands.append(c)
        tous_cands += cands

        # version « Anthony » au plus près : FVG >= 25 pips, Fibo 0,618 (milieu de 0,50-0,78), 3 tiers 1-2-3 R + stop à l'entrée
        ref = {}
        for fib in (0.5, 0.618, 0.78):
            p = (0, 16, fib, 0.0, 48, 0, 0, 0, 0)
            res, _ = D.simuler(p, pips=25 * PIP[epic])
            for s in (TIERS[1], UNIQUES[2]):
                idx, r = res[s]
                ref[f"Fibo {fib}, {SORTIES[s][0]}"] = resume_trades(D, idx, r)
        resultat["marches"][epic] = {"bougies": len(df), "debut": str(df.index[0]), "fin": str(df.index[-1]),
                                     "source": src.read_text().strip() if src.exists() else "Capital.com",
                                     "spread_median": round(float((df.close_ask - df.close_bid).median()), 4),
                                     "conditions": cond, "combinaisons": len(table),
                                     "passent_filtre_entrainement": len(bons),
                                     "comparaison_sorties": comp, "version_anthony_25_pips": ref,
                                     "_srs": srs_tr}

    # Deflated Sharpe : meilleur Sharpe mensuel attendu PAR HASARD vu le nombre d'essais (prudent : tous les essais)
    srs = [x for m in resultat["marches"].values() for x in m.pop("_srs")]
    variance = float(np.var(srs)) if len(srs) > 1 else 0.0
    sr0 = esperance_max(max(essais, 1), variance)
    for c in tous_cands:
        s = c.pop("_serie")
        c["dsr"] = round(deflated_sharpe(s, sr0), 3)
        an = list(c["annees"].values())
        c["annees_positives"] = round(sum(v > 0 for v in an) / max(1, len(an)), 2)
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
        c["jamais_vu_eur_compte_93"] = round(c["jamais_vu"]["R"] * COMPTE_EUR * 0.01, 2)
    tous_cands.sort(key=lambda c: (-c["solide"], -c["passe"], -c["dsr"]))
    resultat.update({"essais": essais, "sharpe_mensuel_du_hasard": round(sr0, 3),
                     "candidates": len(tous_cands), "passent_controles": sum(c["passe"] for c in tous_cands),
                     "solides": sum(c["solide"] for c in tous_cands), "duree_s": round(time.time() - t0),
                     "meilleures": tous_cands[:40]})
    sortie.write_text(json.dumps(resultat, ensure_ascii=False, indent=1, default=float))
    print(f"\n{essais} essais, {len(tous_cands)} candidates, {resultat['passent_controles']} passent les contrôles, "
          f"{resultat['solides']} solides. Sharpe mensuel du hasard {sr0:.3f}")
    for c in tous_cands[:15]:
        print(f"  {'SOLIDE ' if c['solide'] else ('passe  ' if c['passe'] else '       ')}{c['epic']:<7} DSR {c['dsr']:.2f} "
              f"entr {c['entrainement']['R']:+7.1f} R ({c['entrainement']['n']})  valid {c['validation']['R']:+6.1f}  "
              f"test {c['test']['R']:+6.1f}  stress {c['stress']['R']:+6.1f}  {c['texte']}")
    for epic, m in resultat["marches"].items():
        print(f"\n{epic} — sorties (moyenne de toutes les entrées, R jamais vu) :")
        for nom, v in m["comparaison_sorties"].items():
            print(f"   {nom:<45} entr {v['entrainement_R_moyen']:+7.1f}  jamais vu {v['jamais_vu_R_moyen']:+7.1f}  "
                  f"gagnantes {v['part_gagnante_jamais_vu'] * 100:.0f} %")
        print(f"{epic} — version Anthony (25 pips) :")
        for nom, v in m["version_anthony_25_pips"].items():
            print(f"   {nom:<55} entr {v['entrainement']['R']:+7.1f} ({v['entrainement']['n']})  "
                  f"valid {v['validation']['R']:+7.1f}  test {v['test']['R']:+7.1f} ({v['test']['n']})")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "capital":
        telecharger_capital(Path(sys.argv[2]))
    elif cmd == "completer":
        completer(Path(sys.argv[2]))
    elif cmd == "fouiller":
        fouiller(Path(sys.argv[2]), Path(sys.argv[3]), int(os.getenv("GARDER", "40")))

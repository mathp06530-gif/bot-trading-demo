"""Backtest honnête des stratégies de Leo (chaîne leo-trading-algo), avec le moteur du dépôt
bot-trading-demo (backtest/moteur.py) : achat au prix ASK, vente au BID (spread réel Capital.com),
exécution à l'ouverture de la bougie SUIVANTE, frais de nuit réels, 1 % de risque par trade.

Stops : stops normaux (pas garantis), comme sur MetaTrader chez Leo -> on met le minimum du stop
garanti à 0 et la prime à 0 (hypothèse favorable : pas de glissement sur les stops).

Chaque stratégie est testée avec les réglages DONNÉS PAR LEO (aucune optimisation), sur 2 périodes :
la 1re moitié et la 2e moitié de l'historique disponible.

python backtest/leo.py   (données : workflow « Télécharger l historique » -> backtest/donnees ; arguments optionnels = filtre sur les noms)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ICI = Path(__file__).resolve().parent
REPO = ICI.parent
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO))
from lancer import charger_marche, conditions_marche, regrouper  # noqa: E402
from moteur import Conditions, executer  # noqa: E402
from strategies import _sortie, atr, ema, milieu, rsi  # noqa: E402

DON = REPO / "backtest" / "donnees"
CAPITAL, RISQUE = 20000.0, 1.0


# ---------------------------------------------------------------- données
def cond_normale(epic, df):
    c = conditions_marche(epic, float(df.close_bid.iloc[-1]))
    c.stop_garanti_min_pct, c.prime_stop_garanti_pct = 0.0, 0.0
    return c


def croise(a, b, op, nom):
    """Paire croisée synthétique (ex. EURGBP = EURUSD / GBPUSD), spread des deux jambes compris."""
    a, b = a.align(b, join="inner")
    out = pd.DataFrame(index=a.index)
    for k in ("open", "close"):
        if op == "div":
            out[f"{k}_bid"] = a[f"{k}_bid"] / b[f"{k}_ask"]
            out[f"{k}_ask"] = a[f"{k}_ask"] / b[f"{k}_bid"]
        else:
            out[f"{k}_bid"] = a[f"{k}_bid"] * b[f"{k}_bid"]
            out[f"{k}_ask"] = a[f"{k}_ask"] * b[f"{k}_ask"]
    for s in ("bid", "ask"):
        if op == "div":
            h = np.maximum(a[f"high_{s}"] / b[f"close_{s}"], a[f"close_{s}"] / b[f"low_{s}"])
            l_ = np.minimum(a[f"low_{s}"] / b[f"close_{s}"], a[f"close_{s}"] / b[f"high_{s}"])
        else:
            h = np.maximum(a[f"high_{s}"] * b[f"close_{s}"], a[f"close_{s}"] * b[f"high_{s}"])
            l_ = np.minimum(a[f"low_{s}"] * b[f"close_{s}"], a[f"close_{s}"] * b[f"low_{s}"])
        out[f"high_{s}"] = np.maximum.reduce([h, out[f"open_{s}"], out[f"close_{s}"]])
        out[f"low_{s}"] = np.minimum.reduce([l_, out[f"open_{s}"], out[f"close_{s}"]])
    out["volume"] = 0
    c = Conditions(taille_min=1, pas_taille=1, marge=0.0333, stop_garanti_min_pct=0, prime_stop_garanti_pct=0,
                   frais_nuit_achat_pct=0.01, frais_nuit_vente_pct=0.01,
                   eurusd={"EURGBP": 0.85, "AUDCAD": 1.08 * 1.38}[nom])
    return out, c


def marche(epic, unite):
    if epic == "EURGBP":
        return croise(charger_marche("EURUSD", unite), charger_marche("GBPUSD", unite), "div", "EURGBP")
    if epic == "AUDCAD":
        return croise(charger_marche("AUDUSD", unite), charger_marche("USDCAD", unite), "mul", "AUDCAD")
    df = charger_marche(epic, unite)
    return df, cond_normale(epic, df)


# ---------------------------------------------------------------- stratégies
def bollinger_scalp(df, n=20, k=2.5, filtre=None, fen_moy=100, marge_atr=0.1):
    """Vidéo iqaZRQyRDwo (M5, EURGBP). Clôture HORS des bandes -> on joue le retour : clôture au-dessus
    -> vente, en dessous -> achat. Sortie au retour sur la moyenne du milieu. Stop au-delà de la bougie
    d'entrée (+ petite marge). Filtre Leo : pas de trade si la largeur des bandes dépasse
    `filtre` x la largeur moyenne (il a utilisé 0,4)."""
    m = milieu(df)
    mid = m.close.rolling(n).mean()
    sd = m.close.rolling(n).std(ddof=0)
    haut, bas = mid + k * sd, mid - k * sd
    larg = (haut - bas)
    ok = pd.Series(True, index=m.index) if filtre is None else larg <= filtre * larg.rolling(fen_moy).mean()
    a = atr(m)
    cible = np.zeros(len(m), dtype=int)
    stop = np.full(len(m), np.nan)
    etat = 0
    c, mi, hi, lo = m.close.values, mid.values, m.high.values, m.low.values
    for i in range(len(m)):
        if etat == 1 and c[i] >= mi[i]:
            etat = 0
        elif etat == -1 and c[i] <= mi[i]:
            etat = 0
        if etat == 0 and ok.iat[i]:
            if c[i] > haut.iat[i]:
                etat = -1
            elif c[i] < bas.iat[i]:
                etat = 1
        cible[i] = etat
        stop[i] = (hi[i] - c[i] if etat == -1 else c[i] - lo[i]) + marge_atr * a.iat[i]
    return _sortie(cible, stop)


def larry_williams(df, frac=0.5, stop_frac=1.0, bailout=True, max_jours=5, h_ouverture=14):
    """Vidéo 1h-bPAFWT68 (Nasdaq 100, « cassure de volatilité » de Larry Williams).
    Boîte d'hier = plus haut - plus bas de la veille. Achat si le prix dépasse ouverture du jour
    (séance US, ~14 h UTC) + 0,5 x boîte ; vente si sous ouverture - 0,5 x boîte. Stop = 1 x boîte.
    Sortie : à la 1re ouverture de séance en profit (« bailout ») ou au bout de max_jours séances."""
    m = milieu(df)
    jour = m.index.normalize()
    d = m.groupby(jour).agg(h=("high", "max"), l=("low", "min"))
    boite = (d.h - d.l).shift(1).reindex(jour).values
    # ouverture de séance : 1re bougie à partir de h_ouverture UTC
    est_ouv = (m.index.hour == h_ouverture)
    ouv = pd.Series(np.where(est_ouv, m.open.values, np.nan), index=m.index).groupby(jour).transform("first").values
    apres = m.index.hour >= h_ouverture
    c = m.close.values
    cible = np.zeros(len(m), dtype=int)
    stop = np.full(len(m), np.nan)
    etat, entree, seances, jour_entree = 0, 0.0, 0, None
    for i in range(len(m)):
        if etat != 0:
            if est_ouv[i] and jour[i] != jour_entree:
                seances += 1
                profit = (c[i] - entree) * etat > 0
                if (bailout and profit) or seances >= max_jours:
                    etat = 0
        elif apres[i] and boite[i] == boite[i] and ouv[i] == ouv[i] and boite[i] > 0:
            if c[i] > ouv[i] + frac * boite[i]:
                etat, entree, seances, jour_entree = 1, c[i], 0, jour[i]
            elif c[i] < ouv[i] - frac * boite[i]:
                etat, entree, seances, jour_entree = -1, c[i], 0, jour[i]
            if etat:
                stop[i] = stop_frac * boite[i]
        cible[i] = etat
        if etat and stop[i] != stop[i]:
            stop[i] = stop_frac * boite[i] if boite[i] == boite[i] else np.nan
    return _sortie(cible, stop)


def repli_tendance(df, tend_h1=(50, 200), n_rsi=14, bas=40, haut=60, exclure_us=True, suivi_atr=2.0, stop_atr=2.0):
    """Vidéo yCpT-gQ2fgk (USD/JPY M5, « meilleur robot de scalping »). Leo ne donne PAS les règles exactes :
    tendance de fond (H1) + repli + entrée dans le sens de la tendance + trailing stop, hors session US.
    Notre traduction : tendance = EMA 50 > EMA 200 sur bougies 1 h ; repli = RSI 14 (5 min) passé sous 40
    puis qui repasse au-dessus de 40 -> achat (miroir pour la vente) ; stop 2 ATR ; stop suiveur 2 ATR ;
    pas d'entrée entre 13 h et 21 h UTC (séance US)."""
    m = milieu(df)
    h1 = m.close.resample("1h").last().dropna()
    f, s = ema(h1, tend_h1[0]), ema(h1, tend_h1[1])
    tend = np.sign(f - s).shift(1).reindex(m.index, method="ffill").fillna(0).values  # bougie 1 h terminée
    r = rsi(m.close, n_rsi).values
    a = atr(m)
    heure = m.index.hour
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(1, len(m)):
        if etat == 1 and tend[i] < 0 or etat == -1 and tend[i] > 0:
            etat = 0
        if etat == 0 and not (exclure_us and 13 <= heure[i] < 21):
            if tend[i] > 0 and r[i - 1] < bas <= r[i]:
                etat = 1
            elif tend[i] < 0 and r[i - 1] > haut >= r[i]:
                etat = -1
        cible[i] = etat
    return _sortie(cible, a * stop_atr, suivi=a * suivi_atr)


def lwma(s, n):
    w = np.arange(1, n + 1)
    return s.rolling(n).apply(lambda x: np.dot(x, w) / w.sum(), raw=True)


def rvi(m, n):
    num = (m.close - m.open)
    num = (num + 2 * num.shift(1) + 2 * num.shift(2) + num.shift(3)) / 6
    den = (m.high - m.low)
    den = (den + 2 * den.shift(1) + 2 * den.shift(2) + den.shift(3)) / 6
    return num.rolling(n).sum() / den.rolling(n).sum()


def cinq_logic_l1(df, env_n=90, env_pct=0.4, decl_mult=1.2, bb_n=12, bb_k=0.5, rvi_n=40, rvi_niv=0.06,
                  sortie_n=100, stop_pct=1.89, echelle=1.0):
    """Vidéo LNJSBcVg32o (« 5 Logic AUDCAD M30 », logique L1, réglages affichés à l'écran).
    Marché calme = bandes de Bollinger (12 ; 0,5) À L'INTÉRIEUR de l'enveloppe (MM 90 ; 0,4 %).
    Déclencheur = clôture au-delà d'une 2e enveloppe plus large (x 1,2). Sens confirmé par le RVI 40
    (> +0,06 pour vendre, < -0,06 pour acheter). Sortie : clôture qui recroise la moyenne mobile 100.
    Pas d'entrée entre 23 h et 2 h. Stop de secours -1,89 %. `echelle` = 0,5 pour passer de M30 à H1."""
    m = milieu(df)
    e = lambda n: max(2, int(round(n * echelle)))  # noqa: E731
    base = m.close.rolling(e(env_n)).mean()
    env_h, env_b = base * (1 + env_pct / 100), base * (1 - env_pct / 100)
    dec_h, dec_b = base * (1 + env_pct * decl_mult / 100), base * (1 - env_pct * decl_mult / 100)
    bm = m.close.rolling(e(bb_n)).mean()
    bsd = m.close.rolling(e(bb_n)).std(ddof=0)
    calme = ((bm + bb_k * bsd) < env_h) & ((bm - bb_k * bsd) > env_b)
    v = rvi(m, e(rvi_n))
    sortie = m.close.rolling(e(sortie_n)).mean()
    heure = m.index.hour
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    c = m.close.values
    for i in range(len(m)):
        if etat == 1 and c[i] > sortie.iat[i] or etat == -1 and c[i] < sortie.iat[i]:
            etat = 0
        if etat == 0 and calme.iat[i] and not (heure[i] >= 23 or heure[i] < 2):
            if c[i] > dec_h.iat[i] and v.iat[i] > rvi_niv:
                etat = -1
            elif c[i] < dec_b.iat[i] and v.iat[i] < -rvi_niv:
                etat = 1
        cible[i] = etat
    return _sortie(cible, m.close * stop_pct / 100)


def range_breakout(df, debut=0, fin=4, fin_jour=20, tp_mult=1.0):
    """Vidéos hO8S62iTbXA / SIGQ5iEumrA (« Range Breakout », son algo gratuit : or, GBP/JPY, USD/JPY…).
    Range = plus haut / plus bas entre `debut` et `fin` h UTC (Leo : 3 h-6 h heure du serveur MT5,
    soit ~0 h-4 h UTC). Ensuite, 1re clôture au-dessus du range -> achat, en dessous -> vente.
    Stop de l'autre côté du range, objectif = tp_mult x hauteur du range, tout fermé à `fin_jour` h UTC.
    Un seul trade par jour."""
    m = milieu(df)
    jour = m.index.normalize()
    h = m.index.hour
    dans = (h >= debut) & (h < fin)
    hh = m.high.where(dans).groupby(jour).transform("max").values
    ll = m.low.where(dans).groupby(jour).transform("min").values
    c = m.close.values
    cible = np.zeros(len(m), dtype=int)
    stop = np.full(len(m), np.nan)
    obj = np.full(len(m), np.nan)
    etat, fait, jcour = 0, False, None
    for i in range(len(m)):
        if jour[i] != jcour:
            jcour, fait = jour[i], False
            etat = 0
        if h[i] >= fin_jour:
            etat = 0
        elif etat == 0 and not fait and h[i] >= fin and hh[i] == hh[i]:
            rg = hh[i] - ll[i]
            if c[i] > hh[i]:
                etat, fait = 1, True
                stop[i], obj[i] = c[i] - ll[i], tp_mult * rg
            elif c[i] < ll[i]:
                etat, fait = -1, True
                stop[i], obj[i] = hh[i] - c[i], tp_mult * rg
        cible[i] = etat
    s = _sortie(cible, stop, objectif=obj)
    return s


def ict_balayage(df, n_mss=12, rr=2.0, fin_jour=20):
    """Vidéo 8bOs6n5wu98 (DAX, méthode « ICT » d'Impact Trading, version simplifiée et mécanique) :
    le prix passe sous le plus bas de la veille (PDL) puis reclôture au-dessus (balayage), puis casse le
    plus haut des `n_mss` dernières bougies (« MSS ») -> achat ; stop sous la mèche du balayage ;
    objectif 2R. Miroir avec le plus haut de la veille (PDH). Pas de FVG (trop subjectif à coder)."""
    m = milieu(df)
    jour = m.index.normalize()
    d = m.groupby(jour).agg(h=("high", "max"), l=("low", "min"))
    pdh = d.h.shift(1).reindex(jour).values
    pdl = d.l.shift(1).reindex(jour).values
    c, hi, lo = m.close.values, m.high.values, m.low.values
    hh = m.high.rolling(n_mss).max().shift(1).values
    ll = m.low.rolling(n_mss).min().shift(1).values
    hr = m.index.hour
    cible = np.zeros(len(m), dtype=int)
    stop = np.full(len(m), np.nan)
    obj = np.full(len(m), np.nan)
    etat, jcour, bas_bal, haut_bal, fait = 0, None, np.nan, np.nan, False
    for i in range(len(m)):
        if jour[i] != jcour:
            jcour, bas_bal, haut_bal, fait, etat = jour[i], np.nan, np.nan, False, 0
        if hr[i] >= fin_jour:
            etat = 0
            cible[i] = 0
            continue
        if lo[i] < pdl[i]:
            bas_bal = lo[i] if bas_bal != bas_bal else min(bas_bal, lo[i])
        if hi[i] > pdh[i]:
            haut_bal = hi[i] if haut_bal != haut_bal else max(haut_bal, hi[i])
        if etat == 0 and not fait:
            if bas_bal == bas_bal and c[i] > pdl[i] and c[i] > hh[i]:
                etat, fait = 1, True
                stop[i] = c[i] - bas_bal
                obj[i] = rr * stop[i]
            elif haut_bal == haut_bal and c[i] < pdh[i] and c[i] < ll[i]:
                etat, fait = -1, True
                stop[i] = haut_bal - c[i]
                obj[i] = rr * stop[i]
        cible[i] = etat
    return _sortie(cible, stop, objectif=obj)


def orb(df, tz="Europe/Paris", debut="09:00", duree_min=15, fin_entree="12:00", fermeture="17:30",
        tp_r=1.0, stop_milieu=False):
    """Replays « LIVE TRADING : Créer ton premier robot » (apJB_PvesRg, xsVrict_tgw) : range d'OUVERTURE.
    Range = plus haut / plus bas des `duree_min` premières minutes après l'ouverture (heure de Paris,
    changement d'heure compris). Clôture d'une bougie 5 min au-dessus du range -> achat, en dessous -> vente.
    Stop de l'autre côté du range (ou au milieu), objectif = tp_r x le risque, plus d'entrée après
    `fin_entree`, tout fermé à `fermeture`. Un trade par jour."""
    m = milieu(df)
    loc = m.index.tz_convert(tz)
    jour = loc.normalize()
    minutes = loc.hour * 60 + loc.minute
    hm = lambda s: int(s[:2]) * 60 + int(s[3:])  # noqa: E731
    d0, fe, fc = hm(debut), hm(fin_entree), hm(fermeture)
    dans = (minutes >= d0) & (minutes < d0 + duree_min)
    hh = m.high.where(dans).groupby(jour).transform("max").values
    ll = m.low.where(dans).groupby(jour).transform("min").values
    c = m.close.values
    cible = np.zeros(len(m), dtype=int)
    stop = np.full(len(m), np.nan)
    obj = np.full(len(m), np.nan)
    etat, fait, jcour = 0, False, None
    for i in range(len(m)):
        if jour[i] != jcour:
            jcour, fait, etat = jour[i], False, 0
        if minutes[i] >= fc:
            etat = 0
        elif etat == 0 and not fait and d0 + duree_min <= minutes[i] < fe and hh[i] == hh[i]:
            ref_h = (hh[i] + ll[i]) / 2 if stop_milieu else hh[i]
            ref_b = (hh[i] + ll[i]) / 2 if stop_milieu else ll[i]
            if c[i] > hh[i]:
                etat, fait = 1, True
                stop[i] = c[i] - ref_b
            elif c[i] < ll[i]:
                etat, fait = -1, True
                stop[i] = ref_h - c[i]
            if etat:
                obj[i] = tp_r * stop[i]
        cible[i] = etat
    return _sortie(cible, stop, objectif=obj)


def croisement_mm(df, n=50, stop_atr=2.0, suivi_atr=2.0):
    """Vidéos znm1EH3GlnI / 781i5iBaRYg (USD/JPY H1) : achat quand la moyenne pondérée (LWMA) passe au-dessus
    de la moyenne lissée (SMMA) de MÊME période, à la clôture de la bougie 1 h ; achats seulement ;
    stop à l'ouverture + stop suiveur. Leo ne donne ni la période ni les distances : on prend 50 (et 20)
    et 2 ATR. Sortie aussi au croisement inverse."""
    m = milieu(df)
    l = lwma(m.close, n)
    s = m.close.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    a = atr(m)
    cible = np.where(l > s, 1, 0)
    return _sortie(cible, a * stop_atr, suivi=a * suivi_atr)


def supertrend_dir(m, n=10, mult=3.0):
    a = atr(m, n)
    hl2 = (m.high + m.low) / 2
    up, dn = (hl2 + mult * a).values, (hl2 - mult * a).values
    c = m.close.values
    fu, fd = up.copy(), dn.copy()
    d = np.ones(len(m))
    for i in range(1, len(m)):
        fu[i] = up[i] if (up[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fd[i] = dn[i] if (dn[i] > fd[i - 1] or c[i - 1] < fd[i - 1]) else fd[i - 1]
        d[i] = 1 if c[i] > fu[i - 1] else -1 if c[i] < fd[i - 1] else d[i - 1]
    return pd.Series(d, index=m.index)


def nas_suivi_tendance(df, rapide=9, lente=21, sl_pct=0.8, tp_pct=1.5):
    """Replay Msd22smr7V0 (Nasdaq, « suivi de tendance », achats seulement) : SuperTrend (10 ; 3) haussier
    en H1 ET en H4, puis croisement de moyennes mobiles en M15 (périodes non données : EMA 9/21).
    Stop 0,8 %, objectif 1,5 %, sinon sortie au croisement inverse (le break-even à 0,5 % n'est pas simulé). Données 5 min regroupées en 15 min."""
    m = milieu(df)
    st = {}
    for r in ("1h", "4h"):
        b = m.resample(r, label="left", closed="left").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        sd = supertrend_dir(b)
        sd.index = sd.index + pd.Timedelta(r)  # connu seulement à la fin de la bougie
        st[r] = sd.reindex(m.index, method="ffill").fillna(0).values
    f, s = ema(m.close, rapide), ema(m.close, lente)
    croise_h = (f > s) & (f.shift() <= s.shift())
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(len(m)):
        if etat == 1 and f.iat[i] < s.iat[i]:  # croisement inverse : on libère le signal (sortie)
            etat = 0
        if etat == 0 and croise_h.iat[i] and st["1h"][i] > 0 and st["4h"][i] > 0:
            etat = 1
        cible[i] = etat
    return _sortie(cible, m.close * sl_pct / 100, objectif=m.close * tp_pct / 100)


def dca_intraday(df, mm=200, h_achat=0, h_vente=19, stop_pct=2.0):
    """Replays « LIVE ALGO RENTABLE » (RI0bpFWBYjo, YfmTn9-r18k, MiFJ_5YTnpE) : le « DCA intelligent ».
    Achat chaque matin à l'ouverture (~1 h 15 heure du serveur, ~0 h UTC), clôture le soir (21 h 45 serveur,
    ~19 h UTC) pour éviter les frais de nuit, achats seulement, et SEULEMENT si la clôture daily de la veille
    est au-dessus de la moyenne mobile 200 jours. Pas de stop chez Leo : stop de secours 2 % pour le calcul."""
    m = milieu(df)
    jour = m.index.normalize()
    cl = m.close.groupby(jour).last()
    ok = (cl > cl.rolling(mm).mean()).shift(1).reindex(jour).fillna(False).values
    h = m.index.hour
    cible = np.where(ok & (h >= h_achat) & (h < h_vente), 1, 0)
    # l'ordre part à l'ouverture de la bougie suivant le signal : on décale d'une bougie
    cible = np.r_[cible[1:], 0]
    return _sortie(cible, m.close * stop_pct / 100)


# ---------------------------------------------------------------- essais
ESSAIS = [
    # (nom lisible, fonction, réglages, marchés, unité de données, regroupement)
    ("Bollinger 5 min sans filtre", bollinger_scalp, {}, ["EURGBP", "EURUSD", "GBPUSD", "GOLD", "USDJPY"], "MINUTE_5", None),
    ("Bollinger 5 min filtre 0,4", bollinger_scalp, {"filtre": 0.4}, ["EURGBP", "EURUSD", "GBPUSD", "GOLD", "USDJPY"], "MINUTE_5", None),
    ("Larry Williams (fidèle)", larry_williams, {}, ["US100", "US500", "DE40"], "HOUR", None),
    ("Larry Williams (sans bailout, 5 j)", larry_williams, {"bailout": False}, ["US100", "US500", "DE40"], "HOUR", None),
    ("Repli dans la tendance 5 min", repli_tendance, {}, ["USDJPY", "GOLD", "EURUSD"], "MINUTE_5", None),
    ("5 Logic L1 (H1, périodes /2)", cinq_logic_l1, {"echelle": 0.5}, ["AUDCAD", "EURGBP", "EURUSD"], "HOUR", None),
    ("Range Breakout 0-4 h UTC (1 h)", range_breakout, {}, ["GOLD", "USDJPY", "GBPUSD", "EURJPY", "US100", "DE40"], "HOUR", None),
    ("Range Breakout 0-4 h UTC (5 min)", range_breakout, {}, ["GOLD", "USDJPY", "GBPUSD", "US100", "DE40"], "MINUTE_5", None),
    ("ICT balayage PDH/PDL (5 min)", ict_balayage, {}, ["DE40", "US100", "GOLD"], "MINUTE_5", None),
    ("ORB DAX 9h-9h15, objectif 1R", orb, {}, ["DE40"], "MINUTE_5", None),
    ("ORB DAX 9h-9h15, objectif 2R", orb, {"tp_r": 2.0}, ["DE40"], "MINUTE_5", None),
    ("ORB US 15h30-15h45, objectif 1R", orb, {"debut": "15:30", "fin_entree": "18:00", "fermeture": "21:45"}, ["US100", "US500"], "MINUTE_5", None),
    ("ORB US 15h30-15h45, objectif 2R", orb, {"debut": "15:30", "fin_entree": "18:00", "fermeture": "21:45", "tp_r": 2.0}, ["US100", "US500"], "MINUTE_5", None),
    ("ORB DAX 9h-10h (1 h), objectif 1R", orb, {"duree_min": 60}, ["DE40"], "HOUR", None),
    ("ORB US 15h-16h (1 h), objectif 1R", orb, {"debut": "15:00", "duree_min": 60, "fin_entree": "18:00", "fermeture": "21:00"}, ["US100", "US500"], "HOUR", None),
    ("Nasdaq suivi de tendance M15", nas_suivi_tendance, {}, ["US100", "US500", "GOLD"], "MINUTE_5", "15min"),
    ("DCA intraday + MM200 daily", dca_intraday, {}, ["US100", "US500", "DE40"], "HOUR", None),
    ("Croisement MM 1 h LWMA/SMMA 50", croisement_mm, {}, ["USDJPY", "GOLD", "US100"], "HOUR", None),
    ("Croisement MM 1 h LWMA/SMMA 20", croisement_mm, {"n": 20}, ["USDJPY", "GOLD", "US100"], "HOUR", None),
]


def tester(nom, fn, reglages, epics, unite, regle):
    lignes = []
    for epic in epics:
        try:
            df, cond = marche(epic, unite)
        except FileNotFoundError:
            continue
        if regle:
            df = regrouper(df, regle)
        sig = fn(df, **reglages)
        sig.index = df.index
        chauffe = df.index[0] + pd.Timedelta(days=290 if fn.__name__ == "dca_intraday" else 12 if unite == "HOUR" else 3)
        df, sig = df[df.index >= chauffe], sig[sig.index >= chauffe]
        coupe = df.index[len(df) // 2]
        res = {}
        for p, msk in (("P1", df.index < coupe), ("P2", df.index >= coupe)):
            r = executer(df[msk], sig[msk], CAPITAL, RISQUE, cond)
            st = r.stats()
            res[p] = {k: st[k] for k in ("gain_pct", "drawdown_max_pct", "trades", "reussite_pct", "profit_factor",
                                         "frais_eur")}
            res[p]["R"] = round(st["gain_eur"] / (CAPITAL * RISQUE / 100), 1)
            res[p]["du"], res[p]["au"] = str(df[msk].index[0].date()), str(df[msk].index[-1].date())
        lignes.append({"strategie": nom, "marche": epic, "unite": unite, **{f"{p}_{k}": v for p in res for k, v in res[p].items()}})
        print(f"{nom:36s} {epic:7s} P1 {res['P1']['gain_pct']:+7.1f}% ({res['P1']['trades']:4d} tr, R {res['P1']['R']:+6.1f}, DD {res['P1']['drawdown_max_pct']:6.1f})"
              f" | P2 {res['P2']['gain_pct']:+7.1f}% ({res['P2']['trades']:4d} tr, R {res['P2']['R']:+6.1f}, DD {res['P2']['drawdown_max_pct']:6.1f})", flush=True)
    return lignes


if __name__ == "__main__":
    choix = sys.argv[1:]
    tout = []
    for e in ESSAIS:
        if choix and not any(c.lower() in e[0].lower() for c in choix):
            continue
        tout += tester(*e)
    sortie = ICI / "resultats_leo.json"
    anciens = json.loads(sortie.read_text(encoding="utf-8")) if sortie.exists() and choix else []
    noms = {(l["strategie"], l["marche"], l["unite"]) for l in tout}
    anciens = [l for l in anciens if (l["strategie"], l["marche"], l["unite"]) not in noms]
    sortie.write_text(json.dumps(anciens + tout, indent=1, ensure_ascii=False), encoding="utf-8")

"""2e vague (25/11/2026) : stratégies trouvées par 3 recherches parallèles (réseaux, YouTube/TikTok, études/GitHub),
codées avec les réglages PUBLIÉS, testées sur 2 jeux de données :
  - 2 ans Capital.com (24/01/2025 -> aujourd'hui) ;
  - données JAMAIS VUES par le bot : Dukascopy 2015/2017 -> janvier 2025 (ANS=10).
Une idée « passe » seulement si elle gagne sur les DEUX moitiés de la période jamais vue (>= 30 trades) ET sur les
2 ans récents. Même moteur que les autres backtests (spread bid/ask, frais de nuit, prime du stop garanti).

Usage : [ANS=10] python backtest/reseaux2.py [dossier]
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import reseaux as r1  # noqa: E402
from backtest import serrage  # noqa: E402
from backtest.smart_money import base, tenir  # noqa: E402

if len(sys.argv) > 1:
    serrage.DOSSIER = Path(sys.argv[1])
ANS = r1.ANS


# --------------------------------------------------------------------------- outils
def jours(df):
    """Bougies JOUR (UTC) en prix milieu, construites à partir des bougies 1 h."""
    m = pd.DataFrame({k: (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2 for k in ("open", "high", "low", "close")})
    j = m.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    pc = j.close.shift()
    tr = pd.concat([j.high - j.low, (j.high - pc).abs(), (j.low - pc).abs()], axis=1).max(axis=1)
    j["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    return j


def vers_horaire(df, cible_j, dist_j, nouveaux=True):
    """cible_j : sens voulu (1/-1/0) décidé à la CLÔTURE du jour D, tenu pendant le jour D+1 (et ensuite si répété).
    Renvoie (voulu, ok, dstop, None) au format de serrage.simuler (qui lit la bougie i-1 pour agir à l'ouverture de i)."""
    t = cible_j.shift(1).reindex(df.index.floor("1D")).fillna(0).astype(int).values
    d = dist_j.shift(1).reindex(df.index.floor("1D")).values
    voulu = np.r_[t[1:], t[-1]]
    dstop = np.r_[d[1:], d[-1]]
    ok = np.r_[True, voulu[1:] != voulu[:-1]] if nouveaux else np.ones(len(voulu), dtype=bool)
    return voulu, ok, dstop, None


def rsi(c, n):
    return r1.rsi(np.asarray(c, dtype=float), n)


# --------------------------------------------------------------------------- idées (bougies jour, via 1 h)
def sma_jour(df, n):
    """BTC/or/argent : achat si clôture > SMA(n) jour, sinon rien (notebook notp1ssed SMA 40, Grayscale SMA 50)."""
    j = jours(df)
    return vers_horaire(df, (j.close > j.close.rolling(n).mean()).astype(int), 3 * j.atr)


def log_moyenne_7j(df):
    """BTC (Detzel 2021, Wei 2024) : achat si ln(clôture) > moyenne de ln(clôture) des 7 jours précédents."""
    j = jours(df)
    lc = np.log(j.close)
    return vers_horaire(df, (lc > lc.shift(1).rolling(7).mean()).astype(int), 3 * j.atr)


def momentum_semaine(df):
    """BTC (Liu & Tsyvinski, RFS) : rendement de la semaine > 80e centile des 104 dernières semaines -> achat 2 semaines."""
    j = jours(df)
    s = j.close.resample("W-SUN").last()
    r = s.pct_change()
    seuil = r.shift(1).rolling(104, min_periods=52).quantile(0.8)
    sig = (r > seuil)
    tenu = (sig | sig.shift(1).fillna(False)).astype(int)  # tenu 2 semaines
    c = tenu.reindex(j.index, method="ffill").shift(0).fillna(0).astype(int)
    # la décision de la semaine est connue le dimanche à la clôture : appliquée dès le lundi
    return vers_horaire(df, c, 3 * j.atr)


def surreaction_semaine(df, k=1.0):
    """Or/argent (Caporale, Gil-Alana & Plastun 2019) : semaine dont l'amplitude dépasse moyenne + k écarts-types
    (30 semaines) -> la semaine suivante dans le sens de cette semaine."""
    j = jours(df)
    w = j.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    amp = (w.high - w.low) / w.low
    seuil = amp.shift(1).rolling(30).mean() + k * amp.shift(1).rolling(30).std()
    sens = np.where(amp > seuil, np.where(w.close > w.open, 1, -1), 0)
    s = pd.Series(sens, index=w.index)
    # connu le vendredi soir -> tenu du lundi au vendredi suivant
    c = s.reindex(j.index, method="ffill").fillna(0).astype(int)
    fin_sem = pd.Series(j.index.dayofweek == 4, index=j.index)
    c = c.where(~fin_sem | (c.index.isin(w.index)), 0)
    return vers_horaire(df, c, (w.high - w.low).reindex(j.index, method="ffill"))


def tsmom_multi(df):
    """AQR (Hurst, Ooi, Pedersen) : moyenne des signes des rendements 1, 3 et 12 mois, revu chaque fin de mois,
    toujours acheteur ou vendeur. Stop garanti large (4 ATR jour) car le compte l'exige."""
    j = jours(df)
    c = j.close
    sig = np.sign(np.sign(c / c.shift(21) - 1) + np.sign(c / c.shift(63) - 1) + np.sign(c / c.shift(252) - 1))
    fin_mois = j.index.to_period("M") != pd.Index(j.index[1:].to_period("M").tolist() + [None])
    s = pd.Series(np.where(fin_mois, sig, np.nan), index=j.index).ffill().fillna(0).astype(int)
    return vers_horaire(df, s, 4 * j.atr)


def mom_24_mois(df):
    """Or (étude « extensive test of market timing in gold », CXO/Quantpedia) : acheté si rendement 24 mois > 0."""
    j = jours(df)
    c = j.close
    fin_mois = j.index.to_period("M") != pd.Index(j.index[1:].to_period("M").tolist() + [None])
    s = pd.Series(np.where(fin_mois, (c / c.shift(504) - 1 > 0).astype(float), np.nan), index=j.index).ffill().fillna(0)
    return vers_horaire(df, s.astype(int), 4 * j.atr)


def ichimoku_tk(df):
    """Ichimoku 9/26 jour (YouTube, étude HKUST) : acheté tant que Tenkan > Kijun."""
    j = jours(df)
    tk = (j.high.rolling(9).max() + j.low.rolling(9).min()) / 2
    kj = (j.high.rolling(26).max() + j.low.rolling(26).min()) / 2
    return vers_horaire(df, (tk > kj).astype(int), 3 * j.atr)


def heikin_lisse(df):
    """Heikin Ashi lissé SMA 10, jour (TraderHalai, TradingView) : acheteur si vert, vendeur si rouge. Stop 2 %."""
    j = jours(df)
    o, h, l, c = (j[k].rolling(10).mean() for k in ("open", "high", "low", "close"))
    hc = (o + h + l + c) / 4
    ho = hc.copy()
    for i in range(1, len(ho)):
        ho.iloc[i] = (ho.iloc[i - 1] + hc.iloc[i - 1]) / 2 if ho.iloc[i - 1] == ho.iloc[i - 1] else (o.iloc[i] + c.iloc[i]) / 2
    sens = np.where(hc > ho, 1, np.where(hc < ho, -1, 0))
    return vers_horaire(df, pd.Series(sens, index=j.index), j.close * 0.02)


def calendrier(df, jours_tenus):
    """jours_tenus : ensemble de dates (jour UTC) pendant lesquelles on est acheteur."""
    j = jours(df)
    s = pd.Series(0, index=j.index)
    lendemain = j.index + pd.Timedelta(days=1)
    s[np.isin(lendemain, list(jours_tenus))] = 1  # décidé la veille au soir
    return vers_horaire(df, s, 2 * j.atr)


def btc_jours_feries(df):
    """BTC (Quantpedia 2025) : achat à la clôture de la veille d'un jour férié US, vente à la clôture du lendemain."""
    from pandas.tseries.holiday import USFederalHolidayCalendar
    f = USFederalHolidayCalendar().holidays(start="2014-01-01", end="2027-12-31")
    tenus = set(f) | set(f + pd.Timedelta(days=1))
    return calendrier(df, tenus)


def or_vendredi(df):
    """Or (« Friday gold trade ») : achat le jeudi à la clôture, vente le vendredi à la clôture."""
    j = jours(df)
    return calendrier(df, set(j.index[j.index.dayofweek == 4]))


def btc_lundi(df):
    j = jours(df)
    return calendrier(df, set(j.index[j.index.dayofweek == 0]))


def or_janvier(df):
    j = jours(df)
    return calendrier(df, set(j.index[j.index.month == 1]))


def btc_21_23(df):
    """BTC (Quantpedia) : achat à 21 h UTC, vente à 23 h UTC, tous les jours."""
    h = df.index.hour.values
    voulu = np.isin(h, (20, 21)).astype(int)  # tenu pendant les bougies de 21 h et 22 h
    ok = np.r_[True, voulu[1:] != voulu[:-1]]
    return voulu, ok, r1.atr_jour(df), None


# --------------------------------------------------------------------------- idées 4 h (YouTube / GitHub)
def stoch_survente(df):
    """Or (Backtrex) : stochastique 14,3,3 qui remonte au-dessus de 20 -> achat, stop -2 %, objectif +7 %."""
    o, h, l, c, atr, e = base(df)
    ll, hh = pd.Series(l).rolling(14).min(), pd.Series(h).rolling(14).max()
    k = (100 * (pd.Series(c) - ll) / (hh - ll)).rolling(3).mean()
    d = k.rolling(3).mean()  # noqa: F841 (%D publié, non utilisé par la règle)
    sig = ((k > 20) & (k.shift(1) <= 20)).astype(int).values
    v, ok, ds = tenir(sig, c * 0.02, len(c), 200)
    return v, ok, ds, c * 0.07 * (ds == ds)


def englobante_rsi(df):
    """Or (classement TradePro, re-test Backtrex) : avalement haussier avec RSI 14 < 40 -> achat, stop -2 %, obj +4 %."""
    o, h, l, c, atr, e = base(df)
    po, pc_ = np.r_[o[0], o[:-1]], np.r_[c[0], c[:-1]]
    eng = (c > o) & (pc_ < po) & (c >= po) & (o <= pc_) & (rsi(c, 14) < 40)
    v, ok, ds = tenir(eng.astype(int), c * 0.02, len(c), 200)
    return v, ok, ds, c * 0.04 * (ds == ds)


def ema_8_21(df):
    """Or (Backtrex, en 4 h plutôt qu'1 h à cause du spread) : EMA 8 croise au-dessus de l'EMA 21 -> achat,
    stop -1,5 %, objectif +4,5 %."""
    o, h, l, c, atr, e = base(df)
    s = pd.Series(c)
    f, w = s.ewm(span=8, adjust=False).mean().values, s.ewm(span=21, adjust=False).mean().values
    sig = ((f > w) & (np.r_[f[0], f[:-1]] <= np.r_[w[0], w[:-1]])).astype(int)
    v, ok, ds = tenir(sig, c * 0.015, len(c), 300)
    return v, ok, ds, c * 0.045 * (ds == ds)


def inside_bar_ema50(df):
    """TradePro (re-test myncrypto) : bougie intérieure au-dessus de l'EMA 50 ; achat si une clôture casse son haut
    dans les 3 bougies ; stop sur l'EMA 50 ; objectif 1,5 R. Inverse pour la vente."""
    o, h, l, c, atr, e = base(df)
    e50 = pd.Series(c).ewm(span=50, adjust=False).mean().values
    n = len(c)
    sig, dist = np.zeros(n, dtype=int), np.full(n, np.nan)
    actif = None
    for i in range(1, n):
        if actif and i <= actif[3]:
            s_, hi, lo, _ = actif
            if s_ == 1 and c[i] > hi:
                sig[i], dist[i], actif = 1, max(c[i] - e50[i], 0.5 * atr[i]), None
            elif s_ == -1 and c[i] < lo:
                sig[i], dist[i], actif = -1, max(e50[i] - c[i], 0.5 * atr[i]), None
        elif actif:
            actif = None
        if h[i] < h[i - 1] and l[i] > l[i - 1]:
            if c[i] > e50[i] and c[i] > o[i]:
                actif = (1, h[i], l[i], i + 3)
            elif c[i] < e50[i] and c[i] < o[i]:
                actif = (-1, h[i], l[i], i + 3)
    v, ok, ds = tenir(sig, dist, n, 60)
    return v, ok, ds, ds * 1.5


def sma50_croisement(df):
    """Or 4 h (GitHub Decobyz/xauusd-trading-model, simplifié) : croisement du prix et de la SMA 50 -> dans ce sens,
    stop 1,5 ATR(20), objectif 2 R."""
    o, h, l, c, atr, e = base(df)
    sma = pd.Series(c).rolling(50).mean().values
    pc_, ps = np.r_[c[0], c[:-1]], np.r_[sma[0], sma[:-1]]
    sig = np.where((c > sma) & (pc_ <= ps), 1, np.where((c < sma) & (pc_ >= ps), -1, 0))
    a20 = pd.Series(np.maximum(h - l, abs(h - pc_))).ewm(alpha=1 / 20, adjust=False).mean().values
    v, ok, ds = tenir(sig, 1.5 * a20, len(c), 60)
    return v, ok, ds, ds * 2


def williams_cassure(df, k=0.5):
    """Larry Williams (concours Robbins 1987, « volatility breakout ») en jour : achat si le prix dépasse
    l'ouverture du jour + k × amplitude de la veille ; vente à la clôture du jour. Stop = k × amplitude.
    Approximation sur bougies 1 h : entrée à l'ouverture de la bougie qui suit la 1re clôture au-dessus du seuil."""
    m = pd.DataFrame({x: (df[f"{x}_bid"] + df[f"{x}_ask"]) / 2 for x in ("open", "high", "low", "close")})
    j = m.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    amp = (j.high - j.low).shift(1)
    jour = df.index.floor("1D")
    ouv = j.open.reindex(jour).values
    a = amp.reindex(jour).values
    c = m.close.values
    n = len(c)
    voulu, ok, dstop = np.zeros(n, dtype=int), np.zeros(n, dtype=bool), np.full(n, np.nan)
    dernier = np.r_[jour[1:] != jour[:-1], True]  # dernière bougie du jour : on sort à la clôture
    pris = None
    for i in range(n):
        if pris == jour[i]:
            voulu[i] = 0 if dernier[i] else 1
            continue
        if a[i] == a[i] and c[i] > ouv[i] + k * a[i] and not dernier[i]:
            voulu[i], ok[i], dstop[i], pris = 1, True, k * a[i], jour[i]
    dstop = pd.Series(dstop).ffill().values
    return voulu, ok, dstop, None


# --------------------------------------------------------------------------- traders gagnants vérifiés
def tortue_55_20(df):
    """Turtles (Richard Dennis), système 2, jour : achat sur clôture > plus haut 55 jours, sortie sous le plus bas
    20 jours (inverse pour la vente), stop 2 N (ATR 20). Sans ajout de positions (pyramidage déjà rejeté)."""
    j = jours(df)
    hh, ll = j.high.rolling(55).max().shift(1), j.low.rolling(55).min().shift(1)
    sx_l, sx_h = j.low.rolling(20).min().shift(1), j.high.rolling(20).max().shift(1)
    etat, cible = 0, []
    for c, a, b, x, y in zip(j.close, hh, ll, sx_l, sx_h):
        if etat == 1 and c < x:
            etat = 0
        elif etat == -1 and c > y:
            etat = 0
        if c > a:
            etat = 1
        elif c < b:
            etat = -1
        cible.append(etat)
    pc = j.close.shift()
    n = pd.concat([j.high - j.low, (j.high - pc).abs(), (j.low - pc).abs()], axis=1).max(axis=1).rolling(20).mean()
    return vers_horaire(df, pd.Series(cible, index=j.index), 2 * n)


def kotegawa(df, k=2.5):
    """« BNF » Takashi Kotegawa (méthode attribuée) : achat quand le prix est très sous sa moyenne 25 jours
    (ici clôture < SMA 25 - k ATR, adapté à l'or et au BTC), sortie au retour sur la moyenne ou après 5 jours."""
    j = jours(df)
    sma = j.close.rolling(25).mean()
    cible, tenu = [], 0
    for c, m, a in zip(j.close, sma, j.atr):
        if tenu:
            tenu = 0 if (c >= m or tenu >= 5) else tenu + 1
        elif c < m - k * a:
            tenu = 1
        cible.append(1 if tenu else 0)
    return vers_horaire(df, pd.Series(cible, index=j.index), 1.5 * j.atr)


def unger_compression(df):
    """Andrea Unger (champion du monde 2008-2010, style publié) : si l'amplitude d'hier est sous la moyenne
    20 jours (jour calme), achat si une clôture 1 h dépasse le plus haut d'hier, vente sous le plus bas ; sortie à
    la fin du jour ; stop 1 ATR jour."""
    m = pd.DataFrame({x: (df[f"{x}_bid"] + df[f"{x}_ask"]) / 2 for x in ("open", "high", "low", "close")})
    j = jours(df)
    amp = j.high - j.low
    calme = (amp < amp.rolling(20).mean().shift(1)).shift(1)
    jour = df.index.floor("1D")
    hh, ll = j.high.shift(1).reindex(jour).values, j.low.shift(1).reindex(jour).values
    ok_j = calme.reindex(jour).fillna(False).values
    a = j.atr.shift(1).reindex(jour).values
    c = m.close.values
    n = len(c)
    voulu, ok, dstop = np.zeros(n, dtype=int), np.zeros(n, dtype=bool), np.full(n, np.nan)
    dernier = np.r_[jour[1:] != jour[:-1], True]
    pris, sens = None, 0
    for i in range(n):
        if pris == jour[i]:
            voulu[i] = 0 if dernier[i] else sens
            continue
        if ok_j[i] and not dernier[i] and a[i] == a[i]:
            if c[i] > hh[i]:
                sens = 1
            elif c[i] < ll[i]:
                sens = -1
            else:
                continue
            voulu[i], ok[i], dstop[i], pris = sens, True, a[i], jour[i]
    return voulu, ok, pd.Series(dstop).ffill().values, None


# --------------------------------------------------------------------------- liste
def idees(d):
    G, S, B = "GOLD", "SILVER", "BTCUSD"
    h1 = {e: d[(e, "HOUR")] for e in (G, S, B)}
    h4 = {e: d[(e, "HOUR_4")] for e in (G, S, B)}
    res = {}

    def un(nom, marches, f, src):
        res[nom] = r1.jouer([(e, src[e], *f(src[e]), 1.0) for e in marches])

    for n in (40, 50):
        un(f"SMA {n} jour BTC (achat/rien)", (B,), lambda x: sma_jour(x, n), h1)
        un(f"SMA {n} jour or+argent (achat/rien)", (G, S), lambda x: sma_jour(x, n), h1)
    un("ln(prix) > moyenne 7 j BTC", (B,), log_moyenne_7j, h1)
    un("Momentum 1 semaine BTC (80e centile)", (B,), momentum_semaine, h1)
    un("Surréaction hebdo or+argent (1 écart-type)", (G, S), surreaction_semaine, h1)
    un("Tendance multi-horizon AQR 1/3/12 mois or+argent+BTC", (G, S, B), tsmom_multi, h1)
    un("Momentum 24 mois or+argent", (G, S), mom_24_mois, h1)
    un("Ichimoku Tenkan > Kijun jour BTC", (B,), ichimoku_tk, h1)
    un("Ichimoku Tenkan > Kijun jour or+argent", (G, S), ichimoku_tk, h1)
    un("Heikin Ashi lissé jour BTC", (B,), heikin_lisse, h1)
    un("Heikin Ashi lissé jour or+argent", (G, S), heikin_lisse, h1)
    un("BTC veille de jour férié US", (B,), btc_jours_feries, h1)
    un("Or jeudi soir -> vendredi soir", (G,), or_vendredi, h1)
    un("BTC lundi", (B,), btc_lundi, h1)
    un("Or en janvier", (G,), or_janvier, h1)
    un("BTC 21 h -> 23 h UTC", (B,), btc_21_23, h1)
    un("Stochastique survente 4 h or+argent", (G, S), stoch_survente, h4)
    un("Avalement + RSI < 40 4 h or+argent", (G, S), englobante_rsi, h4)
    un("EMA 8/21 4 h or+argent", (G, S), ema_8_21, h4)
    un("Inside bar + EMA 50 4 h or+argent", (G, S), inside_bar_ema50, h4)
    un("Inside bar + EMA 50 4 h BTC", (B,), inside_bar_ema50, h4)
    un("SMA 50 croisement 4 h or+argent", (G, S), sma50_croisement, h4)
    for k in (0.3, 0.5, 0.7):
        un(f"Larry Williams cassure {k:g} × amplitude, or+argent", (G, S), lambda x: williams_cassure(x, k), h1)
        un(f"Larry Williams cassure {k:g} × amplitude, BTC", (B,), lambda x: williams_cassure(x, k), h1)
    un("Tortues système 2 (55/20 jours) or+argent", (G, S), tortue_55_20, h1)
    un("Tortues système 2 (55/20 jours) BTC", (B,), tortue_55_20, h1)
    un("Kotegawa : très sous la moyenne 25 j, or+argent", (G, S), kotegawa, h1)
    un("Kotegawa : très sous la moyenne 25 j, BTC", (B,), kotegawa, h1)
    un("Unger : cassure après un jour calme, or+argent", (G, S), unger_compression, h1)
    un("Unger : cassure après un jour calme, BTC", (B,), unger_compression, h1)
    return res


def autres_marches(p):
    """Petites cryptos / memecoins (idée de Mathis du 25/11) : les meilleures idées appliquées marché par marché."""
    from bot.cassure import signaux_cassure
    res = {}
    for e in [x.strip() for x in os.getenv("AUTRES", "").split(",") if x.strip()]:
        try:
            h1, h4 = serrage.lire(e, "HOUR"), serrage.lire(e, "HOUR_4")
        except FileNotFoundError:
            print(f"{e} : pas de données (marché absent chez Capital.com ?)")
            continue
        sig = signaux_cassure(h4, entree=20, sortie=20)
        c = sig.cible.values
        essais = {
            "Cassure 20 4 h (actuelle or/argent)": [(e, h4, c, np.r_[True, c[1:] != c[:-1]], sig.stop.values, None, None, 1.0)],
            "TTM Squeeze 4 h": [(e, h4, *r1.squeeze(h4), 1.0)],
            "Supertrend 10/3 4 h": [(e, h4, *r1.supertrend(h4), 1.0)],
            "SMA 40 jour (achat/rien)": [(e, h1, *sma_jour(h1, 40), 1.0)],
            "Tortues 55/20 jour": [(e, h1, *tortue_55_20(h1), 1.0)],
            "ln(prix) > moyenne 7 j": [(e, h1, *log_moyenne_7j(h1), 1.0)],
        }
        for nom, jeux in essais.items():
            t = r1.jouer(jeux)
            s = r1.resume(t, (max(p[0], h1.index[0] + pd.Timedelta(days=60)), p[1], p[2]))
            res[f"{e} : {nom}"] = s
            print(f"{e + ' : ' + nom:56s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} "
                  f"{s['mois']:5.1f} {s['reussite']:6.1f} {s['pire_baisse_R']:7.2f}")
    return res


def principal():
    d = {(e, u): serrage.lire(e, u) for e in ("GOLD", "SILVER", "BTCUSD") for u in ("HOUR", "HOUR_4")}
    p = r1.periode([d[k] for k in d])
    print(f"Période : {p[0]:%d/%m/%Y} -> {p[2]:%d/%m/%Y} (moitié au {p[1]:%d/%m/%Y})")
    print(f"{'stratégie':56s} {'R':>7s} {'1re m.':>7s} {'2e m.':>7s} {'trades':>6s} {'/mois':>5s} {'réuss.':>6s} {'baisse':>7s}")
    sortie = {}
    for nom, t in sorted(idees(d).items(), key=lambda kv: -r1.resume(kv[1], p)["R"]):
        s = r1.resume(t, p)
        s["deux_moities"] = bool(s["R_1"] > 0 and s["R_2"] > 0 and s["trades"] >= 30)
        sortie[nom] = s
        print(f"{nom:56s} {s['R']:7.2f} {s['R_1']:7.2f} {s['R_2']:7.2f} {s['trades']:6d} {s['mois']:5.1f} "
              f"{s['reussite']:6.1f} {s['pire_baisse_R']:7.2f}{'  <- 2 moitiés +' if s['deux_moities'] else ''}")
    print(f"\n{sum(s['deux_moities'] for s in sortie.values())} idées sur {len(sortie)} gagnent sur les 2 moitiés.")
    sortie["_autres_marches"] = autres_marches(p)
    (Path(__file__).resolve().parent / f"resultats_reseaux2_{int(ANS)}ans.json").write_text(
        json.dumps({"periode": [str(x) for x in p], "resultats": sortie}, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    principal()

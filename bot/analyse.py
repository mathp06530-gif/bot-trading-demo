"""Module « analyse du marché » : la NOTE TECHNIQUE, sur le modèle des
« Technical Ratings » de TradingView (bibliothèque Pine open source « TechnicalRating »,
https://www.tradingview.com/script/jDWyb5PG-TechnicalRating).

Avant chaque trade, le bot consulte ~20 indicateurs classiques. Chacun vote :
+1 (achat), -1 (vente) ou 0 (neutre). On fait la moyenne de deux familles :
  - MOYENNES MOBILES (tendance) : SMA et EMA 10/20/30/50/100/200, Ichimoku, HMA 9.
    Achat si la moyenne est SOUS le prix, vente si elle est AU-DESSUS.
  - OSCILLATEURS (élan) : RSI, Stochastique, CCI, ADX, Awesome Oscillator, Momentum,
    MACD, Williams %R, Ultimate Oscillator.
Note finale = moyenne des deux, entre -1 et +1 :
  > +0,5 achat fort · > +0,1 achat · entre -0,1 et +0,1 neutre · < -0,1 vente · < -0,5 vente forte.
"""
import numpy as np
import pandas as pd


def _sma(s, n):
    return s.rolling(n, min_periods=n).mean()


def _ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _wma(s, n):
    poids = np.arange(1, n + 1)
    return s.rolling(n, min_periods=n).apply(lambda x: np.dot(x, poids) / poids.sum(), raw=True)


def _rsi(s, n=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    p = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + g / p)


def _vote(achat, vente):
    return np.where(achat, 1.0, np.where(vente, -1.0, 0.0))


def note_technique(m: pd.DataFrame) -> pd.DataFrame:
    """m : colonnes open/high/low/close (prix milieu). Renvoie note_ma, note_osc, note (-1..+1)."""
    c, h, l = m.close, m.high, m.low
    votes_ma = []
    for n in (10, 20, 30, 50, 100, 200):
        for f in (_sma, _ema):
            ma = f(c, n)
            votes_ma.append(np.where(ma.isna(), np.nan, _vote(ma < c, ma > c)))
    base_ichimoku = (h.rolling(26).max() + l.rolling(26).min()) / 2
    votes_ma.append(np.where(base_ichimoku.isna(), np.nan, _vote(base_ichimoku < c, base_ichimoku > c)))
    hma = _wma(2 * _wma(c, 4) - _wma(c, 9), 3)
    votes_ma.append(np.where(hma.isna(), np.nan, _vote(hma < c, hma > c)))

    votes_osc = []
    r = _rsi(c)
    votes_osc.append(_vote((r < 30) & (r > r.shift()), (r > 70) & (r < r.shift())))
    k = 100 * (c - l.rolling(14).min()) / (h.rolling(14).max() - l.rolling(14).min())
    k = k.rolling(3).mean()
    d = k.rolling(3).mean()
    votes_osc.append(_vote((k < 20) & (d < 20) & (k > d), (k > 80) & (d > 80) & (k < d)))
    tp = (h + l + c) / 3
    cci = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True))
    votes_osc.append(_vote((cci < -100) & (cci > cci.shift()), (cci > 100) & (cci < cci.shift())))
    up, down = h.diff(), -l.diff()
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / 14, adjust=False).mean()
    pdi = 100 * pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=m.index).ewm(alpha=1 / 14, adjust=False).mean() / atr
    ndi = 100 * pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=m.index).ewm(alpha=1 / 14, adjust=False).mean() / atr
    adx = (100 * (pdi - ndi).abs() / (pdi + ndi)).ewm(alpha=1 / 14, adjust=False).mean()
    votes_osc.append(_vote((adx > 20) & (pdi > ndi), (adx > 20) & (pdi < ndi)))
    ao = _sma((h + l) / 2, 5) - _sma((h + l) / 2, 34)
    votes_osc.append(_vote((ao > 0) & (ao > ao.shift()), (ao < 0) & (ao < ao.shift())))
    mom = c - c.shift(10)
    votes_osc.append(_vote(mom > mom.shift(), mom < mom.shift()))
    macd = _ema(c, 12) - _ema(c, 26)
    sig = _ema(macd, 9)
    votes_osc.append(_vote(macd > sig, macd < sig))
    wr = -100 * (h.rolling(14).max() - c) / (h.rolling(14).max() - l.rolling(14).min())
    votes_osc.append(_vote((wr < -80) & (wr > wr.shift()), (wr > -20) & (wr < wr.shift())))
    bp = c - pd.concat([l, c.shift()], axis=1).min(axis=1)
    trs = pd.concat([h, c.shift()], axis=1).max(axis=1) - pd.concat([l, c.shift()], axis=1).min(axis=1)
    uo = 100 * (4 * bp.rolling(7).sum() / trs.rolling(7).sum() + 2 * bp.rolling(14).sum() / trs.rolling(14).sum()
                + bp.rolling(28).sum() / trs.rolling(28).sum()) / 7
    votes_osc.append(_vote(uo > 70, uo < 30))

    with np.errstate(all="ignore"):
        pile = np.vstack(votes_ma)
        nb = np.sum(~np.isnan(pile), axis=0)
        note_ma = pd.Series(np.where(nb > 0, np.nansum(pile, axis=0) / np.maximum(nb, 1), np.nan), index=m.index)
    note_osc = pd.Series(np.mean(np.vstack(votes_osc), axis=0), index=m.index)
    note = (note_ma + note_osc) / 2
    return pd.DataFrame({"note_ma": note_ma, "note_osc": note_osc, "note": note})


def verdict(note: float) -> str:
    if note != note:
        return "inconnu"
    if note > 0.5:
        return "achat fort"
    if note > 0.1:
        return "achat"
    if note < -0.5:
        return "vente forte"
    if note < -0.1:
        return "vente"
    return "neutre"

"""Stratégies candidates. Chacune reçoit des bougies (prix milieu o/h/l/c) et renvoie
un DataFrame 'cible' (1, -1, 0), 'stop' (distance en $), 'objectif', 'suivi'.
Le signal d'une bougie n'utilise que des bougies terminées."""
import numpy as np
import pandas as pd


def milieu(df):
    return pd.DataFrame({k: (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2 for k in ("open", "high", "low", "close")})


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def atr(m, n=14):
    pc = m.close.shift()
    tr = pd.concat([m.high - m.low, (m.high - pc).abs(), (m.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def rsi(s, n):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    p = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    return 100 - 100 / (1 + g / p)


def adx(m, n=14):
    up, down = m.high.diff(), -m.low.diff()
    pdm = np.where((up > down) & (up > 0), up, 0.0)
    ndm = np.where((down > up) & (down > 0), down, 0.0)
    a = atr(m, n)
    pdi = 100 * pd.Series(pdm, index=m.index).ewm(alpha=1 / n, adjust=False).mean() / a
    ndi = 100 * pd.Series(ndm, index=m.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def _sortie(cible, stop, objectif=np.nan, suivi=np.nan, entree_nouvelle=True):
    """entree_nouvelle : après un stop, on attend un NOUVEAU signal avant de rentrer."""
    out = pd.DataFrame({"cible": cible, "stop": stop, "objectif": objectif, "suivi": suivi})
    out["cible"] = out.cible.fillna(0).astype(int)
    out.attrs["entree_nouvelle"] = entree_nouvelle
    return out


def ema_croisement(df, rapide=9, lente=21, stop_pct=3.0):
    """Stratégie actuelle du bot : toujours en position, dans le sens du croisement."""
    m = milieu(df)
    f, s = ema(m.close, rapide), ema(m.close, lente)
    cible = np.where(f > s, 1, -1)
    cible = np.where(s.isna(), 0, cible)
    return _sortie(cible, m.close * stop_pct / 100, entree_nouvelle=False)


def cassure_donchian(df, entree=20, sortie=10, stop_atr=2.0, ventes=True, filtre_ema=200):
    """Cassure du plus haut / plus bas des N dernières bougies (méthode « Turtle »)."""
    m = milieu(df)
    hh = m.high.rolling(entree).max().shift()
    ll = m.low.rolling(entree).min().shift()
    a = atr(m)
    tend = ema(m.close, filtre_ema) if filtre_ema else None
    acheter = m.close > hh
    vendre = m.close < ll
    if tend is not None:
        acheter &= m.close > tend
        vendre &= m.close < tend
    sx_l = m.low.rolling(sortie).min().shift()
    sx_h = m.high.rolling(sortie).max().shift()
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(len(m)):
        if etat == 1 and m.close.iat[i] < sx_l.iat[i]:
            etat = 0
        elif etat == -1 and m.close.iat[i] > sx_h.iat[i]:
            etat = 0
        if acheter.iat[i]:
            etat = 1
        elif vendre.iat[i] and ventes:
            etat = -1
        cible[i] = etat
    return _sortie(cible, a * stop_atr)


def retour_moyenne_rsi(df, n_rsi=2, bas=10, haut=90, tendance=200, sortie_ema=5, stop_atr=3.0, ventes=True):
    """Achat d'un repli court dans une tendance haussière (et l'inverse) — style Connors."""
    m = milieu(df)
    r, t, e, a = rsi(m.close, n_rsi), ema(m.close, tendance), ema(m.close, sortie_ema), atr(m)
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(len(m)):
        c = m.close.iat[i]
        if etat == 1 and c > e.iat[i]:
            etat = 0
        elif etat == -1 and c < e.iat[i]:
            etat = 0
        if etat == 0:
            if c > t.iat[i] and r.iat[i] < bas:
                etat = 1
            elif ventes and c < t.iat[i] and r.iat[i] > haut:
                etat = -1
        cible[i] = etat
    return _sortie(cible, a * stop_atr)


def etat_tendance(df, rapide=50, lente=200, adx_min=20, stop_atr=2.5, suivi_atr=3.0, ventes=True):
    """Version à états de tendance_ema : entrée si tendance nette, sortie au croisement inverse
    ou au stop suiveur."""
    m = milieu(df)
    f, s, a, x = ema(m.close, rapide), ema(m.close, lente), atr(m), adx(m)
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(len(m)):
        if s.isna().iat[i]:
            continue
        hausse = f.iat[i] > s.iat[i]
        if etat == 1 and not hausse:
            etat = 0
        elif etat == -1 and hausse:
            etat = 0
        if etat == 0 and x.iat[i] > adx_min:
            if hausse and m.close.iat[i] > f.iat[i]:
                etat = 1
            elif ventes and not hausse and m.close.iat[i] < f.iat[i]:
                etat = -1
        cible[i] = etat
    return _sortie(cible, a * stop_atr, suivi=a * suivi_atr)


STRATEGIES = {
    "ema_croisement": ema_croisement,
    "tendance": etat_tendance,
    "donchian": cassure_donchian,
    "rsi_repli": retour_moyenne_rsi,
}

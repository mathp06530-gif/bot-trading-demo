"""Stratégie « Tendance 4 h » : suivi de tendance filtré, avec stop garanti et stop suiveur.

Choisie après backtest sur 2 ans d'historique Capital.com (voir backtest/ et le rapport).
Le backtest et le bot utilisent EXACTEMENT ce fichier : ce qui a été testé est ce qui tourne.

Règles, sur des bougies de 4 heures (prix milieu entre achat et vente) :
  ENTRÉE ACHAT : EMA 20 au-dessus de l'EMA 200 (tendance haussière)
                 ET le prix au-dessus de l'EMA 20
                 ET ADX > 20 (la tendance est nette, pas un marché qui fait du yo-yo)
  ENTRÉE VENTE : l'inverse (EMA 20 sous l'EMA 200, prix sous l'EMA 20, ADX > 20)
  SORTIE       : l'EMA 20 recroise l'EMA 200 dans l'autre sens,
                 ou le stop est touché.
  STOP (SL)    : stop GARANTI à 2 × ATR (mouvement moyen d'une bougie) du prix d'entrée.
  TP PARTIEL   : la position est ouverte en 2 moitiés. La 1re a un TP à 1 × ATR (on encaisse
                 vite), la 2e n'a pas de TP et suit la tendance (on capte les gros mouvements).
                 Backtest : gain un peu plus faible (+8 % au lieu de +13 % sur l'examen) mais
                 pire baisse divisée par 2 (-4 % au lieu de -9 %). Réglage TP_PARTIEL_ATR.
  STOP SUIVEUR : à chaque bougie, le stop est remonté à 5 × ATR derrière le prix
                 pour verrouiller les gains. Il ne recule jamais.
  FRAIS        : pas d'entrée si le spread dépasse 10 % de la distance du stop.
  TAILLE       : calculée pour ne perdre que RISQUE_PCT % du capital si le stop est touché.
  Après un stop, on attend un NOUVEAU signal avant de reprendre position.
"""
import numpy as np
import pandas as pd

EMA_RAPIDE = 20
EMA_LENTE = 200
ADX_MIN = 20
STOP_ATR = 2.0
SUIVI_ATR = 5.0
SPREAD_MAX_PCT = 10.0
VENTES = True
NOM = f"Tendance 4 h : EMA {EMA_RAPIDE}/{EMA_LENTE} + ADX > {ADX_MIN}, stop {STOP_ATR:g} ATR, suiveur {SUIVI_ATR:g} ATR"


# --- Indicateurs (identiques à TradingView) -------------------------------------
def ema(valeurs, periode: int):
    """Moyenne mobile exponentielle. Accepte une liste (renvoie une liste, None au début)
    ou une Series pandas."""
    if isinstance(valeurs, pd.Series):
        return valeurs.ewm(span=periode, adjust=False, min_periods=periode).mean()
    resultat = [None] * len(valeurs)
    if len(valeurs) < periode:
        return resultat
    alpha = 2 / (periode + 1)
    courant = sum(valeurs[:periode]) / periode
    resultat[periode - 1] = courant
    for i in range(periode, len(valeurs)):
        courant = alpha * valeurs[i] + (1 - alpha) * courant
        resultat[i] = courant
    return resultat


def milieu(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({k: (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2 for k in ("open", "high", "low", "close")})


def atr(m: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = m.close.shift()
    tr = pd.concat([m.high - m.low, (m.high - pc).abs(), (m.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def adx(m: pd.DataFrame, n: int = 14) -> pd.Series:
    up, down = m.high.diff(), -m.low.diff()
    pdm = np.where((up > down) & (up > 0), up, 0.0)
    ndm = np.where((down > up) & (down > 0), down, 0.0)
    a = atr(m, n)
    pdi = 100 * pd.Series(pdm, index=m.index).ewm(alpha=1 / n, adjust=False).mean() / a
    ndi = 100 * pd.Series(ndm, index=m.index).ewm(alpha=1 / n, adjust=False).mean() / a
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


# --- Stratégie -----------------------------------------------------------------
def signaux_tendance(df: pd.DataFrame, rapide=EMA_RAPIDE, lente=EMA_LENTE, adx_min=ADX_MIN,
                     stop_atr=STOP_ATR, suivi_atr=SUIVI_ATR, ventes=VENTES,
                     objectif_atr=None, frais_max_pct=SPREAD_MAX_PCT, note_min=None) -> pd.DataFrame:
    """df : bougies avec colonnes open/high/low/close en _bid et _ask.
    Renvoie par bougie : cible (1 achat, -1 vente, 0 rien), stop (distance en $),
    objectif (distance ou NaN), suivi (distance du stop suiveur), et les indicateurs."""
    m = milieu(df)
    f, s, a, x = ema(m.close, rapide), ema(m.close, lente), atr(m), adx(m)
    spread = (df.close_ask - df.close_bid).values
    if note_min is not None:
        from bot.analyse import note_technique
        note = note_technique(m).note.values
    else:
        note = np.zeros(len(m))
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(len(m)):
        if np.isnan(s.iat[i]) or np.isnan(a.iat[i]):
            continue
        hausse = f.iat[i] > s.iat[i]
        if etat == 1 and not hausse:
            etat = 0
        elif etat == -1 and hausse:
            etat = 0
        if etat == 0 and x.iat[i] > adx_min:
            trop_cher = frais_max_pct and spread[i] > a.iat[i] * stop_atr * frais_max_pct / 100
            if not trop_cher:
                # filtre « analyse du marché » : la note technique doit confirmer le sens
                ok_achat = note_min is None or note[i] >= note_min
                ok_vente = note_min is None or note[i] <= -note_min
                if hausse and m.close.iat[i] > f.iat[i] and ok_achat:
                    etat = 1
                elif ventes and not hausse and m.close.iat[i] < f.iat[i] and ok_vente:
                    etat = -1
        cible[i] = etat
    out = pd.DataFrame({"cible": cible, "stop": a * stop_atr,
                        "objectif": a * objectif_atr if objectif_atr else np.nan,
                        "suivi": a * suivi_atr, "note": note, "ema_rapide": f, "ema_lente": s, "atr": a, "adx": x,
                        "cloture": m.close}, index=df.index)
    out.attrs["entree_nouvelle"] = True
    return out


def bougies_vers_df(bougies: list) -> pd.DataFrame:
    """Bougies de l'API Capital.com -> DataFrame (colonnes _bid / _ask)."""
    lignes = []
    for b in bougies:
        ligne = {"date": pd.Timestamp(b["snapshotTimeUTC"], tz="UTC")}
        for cle, nom in (("openPrice", "open"), ("highPrice", "high"), ("lowPrice", "low"), ("closePrice", "close")):
            ligne[f"{nom}_bid"] = b[cle]["bid"]
            ligne[f"{nom}_ask"] = b[cle]["ask"]
        lignes.append(ligne)
    return pd.DataFrame(lignes).set_index("date") if lignes else pd.DataFrame()


def decider(df: pd.DataFrame) -> dict:
    """À partir des bougies TERMINÉES, renvoie ce que le bot doit faire maintenant."""
    if len(df) < EMA_LENTE + 20:
        return {"direction": None, "nouveau": False, "debut_etat": None, "sig": None,
                "explication": f"Pas assez de bougies ({len(df)}) pour calculer l'EMA {EMA_LENTE}."}
    sig = signaux_tendance(df)
    c = sig.cible.values
    etat = int(c[-1])
    # bougie où l'état actuel a commencé
    j = len(c) - 1
    while j > 0 and c[j - 1] == etat:
        j -= 1
    derniere = sig.iloc[-1]
    tendance = "haussière" if derniere.ema_rapide > derniere.ema_lente else "baissière"
    if etat == 1:
        explication = f"Tendance haussière nette (ADX {derniere.adx:.0f}) : on veut être ACHETEUR."
    elif etat == -1:
        explication = f"Tendance baissière nette (ADX {derniere.adx:.0f}) : on veut être VENDEUR."
    elif derniere.adx <= ADX_MIN:
        explication = f"Tendance {tendance} mais trop faible (ADX {derniere.adx:.0f} ≤ {ADX_MIN}) : on attend."
    else:
        explication = f"Tendance {tendance}, mais le prix n'est pas encore du bon côté de l'EMA {EMA_RAPIDE} : on attend."
    return {
        "direction": {1: "BUY", -1: "SELL"}.get(etat),
        "nouveau": j >= len(c) - 2,  # l'état vient de commencer (dernière ou avant-dernière bougie)
        "debut_etat": str(sig.index[j]),
        "sig": sig,
        "explication": explication,
    }


def signaux_note(df: pd.DataFrame, seuil=0.5, sortie=0.0, tendance=200, stop_atr=STOP_ATR, suivi_atr=SUIVI_ATR,
                 ventes=True, frais_max_pct=SPREAD_MAX_PCT) -> pd.DataFrame:
    """Stratégie « Note technique » (pour les actions et ETF) :
    ACHAT quand la note technique dépasse +seuil (achat fort) ET le prix est au-dessus de l'EMA 200,
    VENTE quand elle passe sous -seuil ET le prix est sous l'EMA 200.
    SORTIE quand la note repasse de l'autre côté de `sortie` (l'analyse ne confirme plus), ou au stop."""
    from bot.analyse import note_technique
    m = milieu(df)
    note = note_technique(m).note.values
    t, a = ema(m.close, tendance), atr(m)
    spread = (df.close_ask - df.close_bid).values
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(len(m)):
        if np.isnan(t.iat[i]) or np.isnan(a.iat[i]) or np.isnan(note[i]):
            continue
        if etat == 1 and note[i] < sortie:
            etat = 0
        elif etat == -1 and note[i] > -sortie:
            etat = 0
        if etat == 0:
            trop_cher = frais_max_pct and spread[i] > a.iat[i] * stop_atr * frais_max_pct / 100
            if not trop_cher:
                if note[i] >= seuil and m.close.iat[i] > t.iat[i]:
                    etat = 1
                elif ventes and note[i] <= -seuil and m.close.iat[i] < t.iat[i]:
                    etat = -1
        cible[i] = etat
    out = pd.DataFrame({"cible": cible, "stop": a * stop_atr, "objectif": np.nan, "suivi": a * suivi_atr,
                        "note": note, "ema_lente": t, "atr": a, "cloture": m.close}, index=df.index)
    out.attrs["entree_nouvelle"] = True
    return out

"""Stratégie EXPÉRIMENTALE « ÉLAN DES GROS ACTEURS » 4 h sur l'OR et l'ARGENT (25/11/2026, idée de Mathis :
« les banques ne mettent pas 1 €, ça doit se voir »).

Idée : quand un gros acteur achète d'un coup, le prix monte si vite qu'il laisse un TROU entre les bougies
(le bas de la bougie qui vient de finir est au-dessus du haut d'il y a 2 bougies : personne n'a pu vendre
entre les deux). On suit cet élan. C'est l'inverse pour la vente.

Règles, sur des bougies de 4 h TERMINÉES (prix milieu) :
  - ACHAT si bas(maintenant) - haut(il y a 2 bougies) > TROU_MIN_ATR (0,25) × ATR 14, et prix au-dessus de l'EMA 200.
    VENTE si haut(maintenant) est sous le bas d'il y a 2 bougies du même écart, et prix sous l'EMA 200.
  - Stop garanti de l'autre côté du trou (+ 0,1 ATR). Objectif (TP chez Capital.com) à OBJECTIF_ELAN_R (2) R.
  - Sortie forcée après MAX_BOUGIES_ELAN (20) bougies de 4 h (~3 jours et demi de marché).
  - Une seule position par marché. Risque RISQUE_ELAN_PCT (1 %) du capital.
  - Elle ne gêne jamais les stratégies principales : pas d'entrée si une autre stratégie est dans l'autre sens
    sur le même marché (compte sans couverture), et elle ferme sa position si la Cassure veut aller dans l'autre sens.

Backtest 2 ans (backtest/smart_money.py, 25/11/2024 -> 25/11/2026, net de frais, or + argent) : +54 R sur
190 trades, 50 % gagnants, gagnante sur les 2 moitiés (+29 R puis +25 R), pire baisse -11,5 R.
Avec les règles de cohabitation avec la Cassure (version exacte du bot) : +44 R sur 185 trades (+23 R puis +21 R),
pire baisse -15,5 R.
31 réglages voisins sur 36 gagnaient aussi sur les 2 moitiés. Sur le Bitcoin : faible, pas utilisée.
LIMITES : 2 ans seulement, l'or et l'argent ont beaucoup monté (les achats font l'essentiel du gain),
et 243 variantes ont été essayées (une partie du résultat peut venir de la chance). Preuve FAIBLE : EXPÉRIENCE.
"""
import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from bot.cassure import regles_marche, taux_devise
from bot.registre import noter_fermeture
from bot.strategie import atr, bougies_vers_df, milieu

ACTIVE = os.getenv("ELAN", "oui").strip().lower() in ("oui", "1", "true", "on")
LISTE = [m.strip() for m in os.getenv("ELAN_MARCHES", "GOLD,SILVER").split(",") if m.strip()]
UNITE = "HOUR_4"
RISQUE_ELAN_PCT = float(os.getenv("RISQUE_ELAN_PCT", "1"))
TROU_MIN_ATR = float(os.getenv("TROU_MIN_ATR", "0.25"))
OBJECTIF_ELAN_R = float(os.getenv("OBJECTIF_ELAN_R", "2"))
MAX_BOUGIES_ELAN = int(float(os.getenv("MAX_BOUGIES_ELAN", "20")))
DEBUT = "2026-11-25"
NOM = (f"Élan des gros acteurs 4 h : trou > {TROU_MIN_ATR:g} ATR entre 3 bougies, dans le sens de l'EMA 200, "
       f"stop de l'autre côté du trou, objectif {OBJECTIF_ELAN_R:g} R, sortie après {MAX_BOUGIES_ELAN} bougies, "
       f"risque {RISQUE_ELAN_PCT:g} % (expérimentale)")
DESCRIPTION = ("Expérience lancée le 25/11/2026 : repère les bougies de 4 h où un gros ordre a fait sauter le prix "
               "(un « trou » entre les bougies) sur l'or et l'argent, et suit cet élan. Backtest 2 ans : +44 R, "
               "mais preuve faible (2 ans, marché très haussier).")


def signaux_elan(df: pd.DataFrame, trou_min_atr: float = TROU_MIN_ATR, tendance: bool = True) -> pd.DataFrame:
    """Par bougie TERMINÉE : sig (+1 achat, -1 vente, 0 rien), dist (distance du stop, en prix), atr, ema."""
    m = milieu(df) if "close_bid" in df else df
    a = atr(m)
    e = m.close.ewm(span=200, adjust=False).mean()
    h2, l2 = m.high.shift(2), m.low.shift(2)
    achat = (m.low - h2) > trou_min_atr * a
    vente = (l2 - m.high) > trou_min_atr * a
    if tendance:
        achat &= m.close > e
        vente &= m.close < e
    sig = np.where(achat, 1, np.where(vente, -1, 0))
    dist = np.where(sig == 1, m.close - h2, l2 - m.close) + 0.1 * a
    return pd.DataFrame({"sig": sig, "dist": dist, "atr": a, "ema": e, "cloture": m.close}, index=m.index)


def _id(conf: dict) -> str | None:
    deals = conf.get("affectedDeals") or []
    return (deals[0].get("dealId") if deals else None) or conf.get("dealId")


def tour_elan(api, donnees: dict, epic: str, positions: list, capital: float, disponible: float, eurusd: float,
              noter, garde, quand: str, peut_entrer: bool = True) -> str:
    etat = donnees.setdefault("elan", {})
    deals = etat.setdefault("deals", {})  # dealId -> {"epic", "bougie": bougie du signal}
    ouverts = {p["position"]["dealId"] for p in positions}
    for d in [d for d in deals if d not in ouverts]:
        del deals[d]
    marche = etat.setdefault("marches", {}).setdefault(epic, {})
    miennes = [p for p in positions if p["position"]["dealId"] in deals and p["market"]["epic"] == epic]

    bougies = api.bougies(epic, UNITE, 400)
    if len(bougies) < 250:
        return "Pas assez d'historique"
    df = bougies_vers_df(bougies[:-1])
    s = signaux_elan(df)
    der = s.iloc[-1]
    prix_achat, prix_vente = bougies[-1]["closePrice"]["ask"], bougies[-1]["closePrice"]["bid"]
    m = milieu(df)
    marche.update({"prix": round((prix_achat + prix_vente) / 2, 2), "ema200": round(float(der.ema), 2),
                   "atr": round(float(der.atr), 2),
                   "trou_achat_atr": round(float((m.low.iloc[-1] - m.high.iloc[-3]) / der.atr), 2),
                   "trou_vente_atr": round(float((m.low.iloc[-3] - m.high.iloc[-1]) / der.atr), 2)})

    # 1) Sorties : durée maximale atteinte, ou la Cassure veut aller dans l'autre sens (elle passe en priorité)
    cassure = (donnees.get("cassure") or {}).get(epic, {}).get("tendance")
    for p in miennes:
        info = deals[p["position"]["dealId"]]
        n = int((df.index > pd.Timestamp(info["bougie"])).sum())
        raison = None
        if n >= MAX_BOUGIES_ELAN:
            raison = f"durée maximale atteinte ({MAX_BOUGIES_ELAN} bougies de 4 h)"
        elif cassure and cassure != p["position"]["direction"]:
            raison = "la Cassure 4 h veut aller dans l'autre sens (elle passe en priorité)"
        if raison:
            conf = api.fermer(p["position"]["dealId"])
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, quand, f"[Élan] {raison}")
                del deals[p["position"]["dealId"]]
            noter("fermeture", epic, f"[Élan] Position fermée : {raison} (gain/perte : "
                  f"{p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
            return "Position fermée"
    if miennes:
        return f"Position en cours (objectif {OBJECTIF_ELAN_R:g} R ou sortie après {MAX_BOUGIES_ELAN} bougies)"
    if not peut_entrer:
        return "Désactivée"

    # 2) Entrée : seulement sur la DERNIÈRE bougie terminée, jamais deux fois le même signal
    if not der.sig:
        return "En attente d'un trou (élan d'un gros ordre)"
    voulu = "BUY" if der.sig > 0 else "SELL"
    mot = "ACHAT" if voulu == "BUY" else "VENTE"
    bougie = str(s.index[-1])
    entrees = donnees.setdefault("entrees", {})
    if entrees.get(f"elan:{epic}") == bougie:
        return "Signal déjà utilisé"
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    prix = prix_achat if voulu == "BUY" else prix_vente
    mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
    distance = max(float(der.dist), mini * 1.05)
    refus = None
    if regles["statut"] != "TRADEABLE":
        refus = "marché fermé"
    elif any(p["market"]["epic"] == epic and p["position"]["direction"] != voulu for p in positions):
        refus = "une autre stratégie a une position dans l'autre sens sur ce marché"
    elif cassure and cassure != voulu:
        refus = "la Cassure 4 h est dans l'autre sens"
    elif abs(prix - float(der.cloture)) > float(der.atr):
        refus = "le prix a trop bougé depuis le signal (écart > 1 ATR)"
    elif (prix_achat - prix_vente) > distance * 0.10:
        refus = "spread trop cher par rapport au stop"
    taux = taux_devise(regles, eurusd, prix)
    pas = regles["pas"]
    taille = math.floor(capital * RISQUE_ELAN_PCT / 100 * taux / distance / pas) * pas
    taille_marge = math.floor(disponible * taux / (prix * regles["marge"]) * 0.5 / pas) * pas
    taille = round(min(taille, taille_marge), 6)
    if not refus and taille < regles["taille_min"]:
        refus = f"capital trop faible pour la taille minimale ({regles['taille_min']})"
    if not refus and garde is not None:
        garde.taux[epic] = taux
        ok, raison = garde.autoriser(taille * distance / taux, distance, "elan_4h", epic)
        refus = None if ok else raison
    if refus:
        entrees[f"elan:{epic}"] = bougie  # comme le backtest : un signal non pris est perdu
        noter("analyse", epic, f"[Élan] Trou de gros ordre ({mot}) mais ordre REFUSÉ : {refus}.")
        return f"Refusé : {refus}"
    conf = api.ouvrir(epic, voulu, taille, prix=prix, stop_distance=distance, garanti=True,
                      objectif_distance=distance * OBJECTIF_ELAN_R)
    entrees[f"elan:{epic}"] = bougie
    if conf.get("dealStatus") != "ACCEPTED":
        noter("erreur", epic, f"[Élan] Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
        return "Refusé par Capital.com"
    deal = _id(conf)
    if deal:
        deals[deal] = {"epic": epic, "bougie": bougie}
    if garde is not None:
        stop = prix - distance if voulu == "BUY" else prix + distance
        garde.enregistrer({"market": {"epic": epic},
                           "position": {"level": prix, "stopLevel": stop, "size": taille, "direction": voulu}})
    noter("ordre", epic, f"[Élan] Trou de gros ordre sur la bougie 4 h de {bougie[:16]} : {mot} de {taille} à "
          f"{float(conf.get('level') or prix):.2f}, stop garanti à {distance:.2f}, objectif à "
          f"{distance * OBJECTIF_ELAN_R:.2f} (risque max ≈ {taille * distance / taux:.2f} €).")
    return f"{mot} de {taille}"


def premiere_fois(donnees: dict, noter) -> None:
    """Note une seule fois dans le Journal la date de début de l'expérience."""
    if donnees.setdefault("elan", {}).get("depuis"):
        return
    donnees["elan"]["depuis"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    noter("commande", "", "Nouveau (25/11/2026) : stratégie EXPÉRIMENTALE « Élan des gros acteurs » sur l'or et "
          "l'argent, risque 1 %. Elle suit les bougies de 4 h où un gros ordre a fait sauter le prix. "
          "Backtest 2 ans : +44 R sur 185 trades, mais preuve faible. Séparée des autres stratégies : "
          "elle ne change rien à la Cassure, à la Tendance ni à la Rapide.")

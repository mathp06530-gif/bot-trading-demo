"""STRATÉGIE « CASSURE 20 BOUGIES 4 h » (méthode des « Turtles »), un sous-bot par marché.

Testée le 20/11/2026 sur 2 ans de prix Capital.com, 35 marchés, avec le spread et les frais de nuit.
Réglages choisis sur la 1re année, vérifiés sur la 2e. Sur 35 marchés, seuls l'or et l'argent
gagnent les deux années. Panier or + argent, 0,5 % de risque : +3 296 € puis +3 051 € sur
21 000 €, pire baisse d'environ -9 %, environ 4 trades par mois. C'est une EXPÉRIENCE en démo,
pas une promesse.

Règles, sur des bougies de 4 heures TERMINÉES (prix milieu) :
  ACHAT  : la clôture dépasse le plus haut des 20 bougies précédentes ET le prix est au-dessus de l'EMA 200.
  VENTE  : la clôture passe sous le plus bas des 20 bougies précédentes ET le prix est sous l'EMA 200.
  SORTIE : un achat est fermé quand la clôture passe sous le plus bas des 20 dernières bougies
           (une vente : au-dessus du plus haut). Une cassure inverse retourne la position.
  STOP   : stop GARANTI à 2 × ATR (ou le minimum imposé par Capital.com, s'il est plus grand).
  TAILLE : RISQUE_CASSURE_PCT (0,5 %) du capital perdu au maximum si le stop est touché.
  REFUS  : marché fermé, signal ancien ou déjà utilisé, prix trop loin du signal, spread trop cher,
           taille trop petite, ou un des GARDE-FOUS (bot/garde_fous.py).
"""
import math
import os

import numpy as np
import pandas as pd

from bot.empilement import peut_empiler
from bot.registre import noter_fermeture
from bot.strategie import atr, bougies_vers_df, ema, milieu

LISTE = [m.strip() for m in os.getenv("CASSURE_MARCHES", "GOLD,SILVER").split(",") if m.strip()]
RISQUE_CASSURE_PCT = float(os.getenv("RISQUE_CASSURE_PCT", "0.5"))
# ENTREE et SORTIE sont réglables dans reglages.env (auto-amélioration hebdomadaire)
ENTREE = int(float(os.getenv("CASSURE_ENTREE", "20")))
SORTIE = int(float(os.getenv("CASSURE_SORTIE", "20")))
STOP_ATR, FILTRE_EMA = 2.0, 200
UNITE = "HOUR_4"
NOM = f"Cassure {ENTREE} bougies 4 h dans le sens de l'EMA {FILTRE_EMA}, stop garanti {STOP_ATR:g} ATR"


def signaux_cassure(df: pd.DataFrame, entree=ENTREE, sortie=SORTIE, stop_atr=STOP_ATR, filtre_ema=FILTRE_EMA,
                    ventes=True) -> pd.DataFrame:
    """Mêmes calculs que backtest/strategies.py:cassure_donchian (vérifié par un test)."""
    m = milieu(df)
    hh, ll = m.high.rolling(entree).max().shift(), m.low.rolling(entree).min().shift()
    a, t = atr(m), ema(m.close, filtre_ema)
    acheter = (m.close > hh) & (m.close > t)
    vendre = (m.close < ll) & (m.close < t)
    sx_l, sx_h = m.low.rolling(sortie).min().shift(), m.high.rolling(sortie).max().shift()
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
    return pd.DataFrame({"cible": cible, "stop": a * stop_atr, "atr": a, "haut": hh, "bas": ll,
                         "ema": t, "cloture": m.close}, index=df.index)


def taux_devise(regles: dict, eurusd: float, prix: float) -> float:
    """Combien d'unités de la devise du marché vaut 1 € (USD : EUR/USD ; EUR : 1 ; JPY : EUR/USD × USD/JPY)."""
    devise = regles.get("devise", "USD")
    if devise == "EUR":
        return 1.0
    if devise == "JPY":
        return eurusd * prix if prix > 20 else eurusd * 155.0
    if devise == "GBP":
        return eurusd / 1.27
    return eurusd


def regles_marche(api, epic: str, cache: dict) -> dict:
    if epic not in cache:
        m = api.marche(epic)
        r = m.get("dealingRules", {})
        g = r.get("minGuaranteedStopDistance", {})
        cache[epic] = {
            "statut": m.get("snapshot", {}).get("marketStatus", "TRADEABLE"),
            "taille_min": float(r.get("minDealSize", {}).get("value", 1)),
            "pas": float(r.get("minSizeIncrement", {}).get("value", r.get("minDealSize", {}).get("value", 1))),
            "stop_min_pct": float(g["value"]) if g.get("unit") == "PERCENTAGE" else None,
            "stop_min_points": float(g["value"]) if g.get("value") and g.get("unit") != "PERCENTAGE" else None,
            "marge": float(m.get("instrument", {}).get("marginFactor", 20)) / 100,
            "nom": m.get("instrument", {}).get("name", epic),
            "devise": m.get("instrument", {}).get("currency", "USD"),
        }
    return cache[epic]


def tour_cassure(api, donnees: dict, epic: str, positions: list, capital: float, disponible: float, eurusd: float,
                 noter, garde, quand: str, peut_entrer: bool = True, cle: str = "cassure",
                 risque_pct: float | None = None, signaux=None, unite: str = UNITE, analyse=None,
                 stop_pct: float | None = None, objectif_pct: float | None = None, sortie_signal: bool = True) -> dict:
    """cle : « cassure » (stratégie normale), « petit_compte » (capital virtuel, risque élevé) ou
    « tendance_mois » (signaux=bot/tendance_mois.py:signaux_tendance, unite="DAY").
    Un signal externe fournit ses textes dans sig.attrs : « pourquoi » (ordre), « sortie » (fermeture), « nom ».
    Chaque profil ne gère QUE ses propres positions (repérées par leur numéro dealId)."""
    risque_pct = RISQUE_CASSURE_PCT if risque_pct is None else risque_pct
    tous_deals = donnees.setdefault("deals_par_strategie", {}).setdefault(cle, [])
    etat = donnees.setdefault(cle, {}).setdefault(epic, {})
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    etat["nom"] = regles["nom"]
    miennes = [p for p in positions if p["market"]["epic"] == epic and p["position"]["dealId"] in tous_deals]
    bougies = api.bougies(epic, unite, 1000)
    if len(bougies) < (60 if signaux is not None else FILTRE_EMA + 30):
        etat.update({"action": "Pas assez d'historique"})
        return etat
    sig = (signaux or signaux_cassure)(bougies_vers_df(bougies[:-1]))
    externe = signaux is not None
    textes = sig.attrs if externe else {}
    der = sig.iloc[-1]
    c = sig.cible.values
    voulu = {1: "BUY", -1: "SELL"}.get(int(c[-1]))
    j = len(c) - 1
    while j > 0 and c[j - 1] == c[-1]:
        j -= 1
    debut = str(sig.index[j])
    # Nouvelle cassure pendant une tendance déjà en cours (clôture au-delà du canal des 20 bougies) :
    # le backtest la compte comme une entrée, le bot aussi (demande de Mathis, 20/11/2026).
    der0 = sig.iloc[-1]
    frais = (c[-1] == 1 and der0.cloture > der0.haut) or (c[-1] == -1 and der0.cloture < der0.bas)
    if frais and signaux is None:
        debut = str(sig.index[-1])
        j = len(c) - 1
    prix_achat, prix_vente = bougies[-1]["closePrice"]["ask"], bougies[-1]["closePrice"]["bid"]
    if "momentum_pct" in textes:
        etat["momentum_pct"] = textes["momentum_pct"]
    etat.update({"tendance": voulu, "prix": (prix_achat + prix_vente) / 2, "plus_haut_20": round(float(der.haut), 2),
                 "plus_bas_20": round(float(der.bas), 2), "ema200": round(float(der.ema), 2),
                 "atr": round(float(der.atr), 2)})
    action = "Aucune action"

    # 1) Sortie : fin de la cassure ou cassure inverse
    for p in [p for p in miennes if p["position"]["direction"] != voulu and sortie_signal]:
        conf = api.fermer(p["position"]["dealId"])
        if conf.get("dealStatus") == "ACCEPTED":
            noter_fermeture(donnees, p, conf, quand, textes.get("sortie", "Fin de la cassure"))
        raison = textes.get("sortie") or f"Le prix est repassé de l'autre côté du canal des {SORTIE} bougies"
        noter("fermeture", epic, f"{raison} : position fermée (gain/perte : {p['position'].get('upl', 0):.2f}).")
        action = "Position fermée"
    miennes = [p for p in miennes if p["position"]["direction"] == voulu or not sortie_signal]
    empile = ""
    if miennes:
        ok_e, empile = peut_empiler(miennes, voulu, prix_achat if voulu == "BUY" else prix_vente, float(der.stop))
        etat["empilement"] = empile
        if not (ok_e and peut_entrer and regles["statut"] == "TRADEABLE"):
            etat["action"] = "Position conservée"
            return etat

    # 2) Entrée, avec toutes les vérifications
    entrees = donnees.setdefault("entrees", {})
    cle_signal = f"{cle}:{epic}"
    if voulu and peut_entrer:
        prix = prix_achat if voulu == "BUY" else prix_vente
        refus = None
        if regles["statut"] != "TRADEABLE":
            refus = "marché fermé"
        elif not empile and j < len(c) - 2:
            refus = f"cassure trop ancienne (depuis le {debut[:16]})"
        elif not empile and entrees.get(cle_signal) == debut:
            refus = "signal déjà utilisé"
        if not refus and analyse is not None:
            ok_analyse, texte_analyse = analyse(bougies_vers_df(bougies[:-1]))
            etat["analyse"] = texte_analyse
            if not ok_analyse:
                refus = f"analyse du marché : {texte_analyse}"
        if refus:
            pass
        elif any(p["market"]["epic"] == epic and p["position"]["direction"] != voulu
                 and p["position"]["dealId"] not in tous_deals for p in positions):
            # compte sans couverture : un ordre opposé fermerait la position d'une autre stratégie
            refus = "une autre stratégie a une position dans l'autre sens sur ce marché"
        elif not empile and abs(prix - float(der.cloture)) > float(der.atr):
            refus = "le prix a trop bougé depuis le signal (écart > 1 ATR)"
        mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
        distance = max(prix * stop_pct / 100 if stop_pct else float(der.stop), mini * 1.05)
        if not refus and (prix_achat - prix_vente) > distance * 0.10:
            refus = "spread trop cher par rapport au stop"
        pas = regles["pas"]
        taux = taux_devise(regles, eurusd, prix)  # unités de la devise du marché pour 1 €
        garde.taux[epic] = taux
        taille = math.floor(capital * risque_pct / 100 * taux / distance / pas) * pas
        taille_marge = math.floor(disponible * taux / (prix * regles["marge"]) * 0.5 / pas) * pas
        taille = round(min(taille, taille_marge), 6)
        if not refus and taille < regles["taille_min"]:
            refus = f"capital trop faible pour la taille minimale ({regles['taille_min']})"
        if not refus:
            ok, raison = garde.autoriser(taille * distance / taux, distance,
                                        "cassure_4h" if cle == "cassure" else cle, epic)
            refus = None if ok else raison
        mot = "ACHAT" if voulu == "BUY" else "VENTE"
        if refus:
            if etat.get("dernier_refus") != refus:
                noter("analyse", epic, f"{textes.get('nom', 'Cassure')} ({mot}) mais ordre REFUSÉ : {refus}.")
            etat["dernier_refus"] = refus
            action = f"Refusé : {refus}"
        else:
            conf = api.ouvrir(epic, voulu, taille, prix=prix, stop_distance=distance, garanti=True,
                              objectif_distance=prix * objectif_pct / 100 if objectif_pct else None)
            if conf.get("dealStatus") == "ACCEPTED":
                entrees[cle_signal] = debut
                deal = (conf.get("affectedDeals") or [{}])[0].get("dealId") or conf.get("dealId")
                if deal:
                    tous_deals.append(deal)
                stop = prix - distance if voulu == "BUY" else prix + distance
                garde.enregistrer({"market": {"epic": epic}, "position": {"level": prix, "stopLevel": stop, "size": taille,
                                                "direction": voulu}})
                cote = "au-dessus du plus haut" if voulu == "BUY" else "sous le plus bas"
                pourquoi = textes.get("pourquoi") or f"Cassure : clôture {cote} des {ENTREE} dernières bougies de 4 h"
                if empile:
                    pourquoi = f"Empilement ({empile})"
                noter("ordre", epic, f"{pourquoi} : {mot} de {taille} "
                      f"à {float(conf.get('level') or prix):.2f}, stop garanti à {distance:.2f}.")
                action = f"{mot} de {taille}"
            else:
                noter("erreur", epic, f"Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
            etat.pop("dernier_refus", None)
    elif voulu and not peut_entrer:
        action = "Désactivé"
    etat["action"] = action
    return etat

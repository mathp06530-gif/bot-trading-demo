"""Stratégie EXPÉRIMENTALE « SUPERTREND 4 h » sur l'ETHEREUM (25/11/2026, trouvée sur les réseaux : indicateur
Supertrend 10/3, très partagé sur YouTube, TikTok et TradingView).

Pourquoi elle : sur 48 idées trouvées par la recherche (réseaux, forums, études, gagnants de concours), c'est la
seule qui gagne à la fois sur des données que le bot n'avait JAMAIS vues (Capital.com, 06/2017 -> 01/2025) et sur
les 2 dernières années, sur un marché où aucune autre stratégie ne trade (pas de conflit sur le compte sans
couverture). Réglages publiés, aucune optimisation.

Règles, sur des bougies de 4 h TERMINÉES (prix milieu) :
  - Ligne Supertrend : (haut + bas) / 2 ± 3 × ATR simple 10 bougies, qui ne recule jamais pendant une tendance.
  - Toujours dans le sens du Supertrend : quand la clôture franchit la ligne, on ferme et on se retourne.
  - Stop garanti à la ligne au moment de l'entrée (+ 0,1 ATR 14). Pas d'objectif, pas de suiveur.
  - Après un stop, on attend le prochain retournement. Risque RISQUE_SUPERTREND_PCT (1 %) du capital.

Backtest (backtest/reseaux.py et reseaux2.py, net de spread, frais de nuit et prime du stop garanti) :
  - jamais vu (30/06/2017 -> 23/01/2025) : +137,7 R sur 394 trades, +107,8 R puis +29,9 R, pire baisse -9,4 R ;
  - 2 dernières années (24/01/2025 -> 25/11/2026) : +9,8 R sur 110 trades, +3,3 R puis +6,5 R, pire baisse -9,8 R.
LIMITES : l'avantage a beaucoup baissé avec le temps (surtout gagné en 2017-2021) ; ~4-5 trades par mois,
33 % de trades gagnants (beaucoup de petites pertes, quelques gros gains). EXPÉRIENCE à juger après ~30 trades.
"""
import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from bot.cassure import regles_marche, taux_devise
from bot.registre import noter_fermeture
from bot.strategie import bougies_vers_df, milieu

ACTIVE = os.getenv("SUPERTREND", "oui").strip().lower() in ("oui", "1", "true", "on")
LISTE = [m.strip() for m in os.getenv("SUPERTREND_MARCHES", "ETHUSD").split(",") if m.strip()]
UNITE = "HOUR_4"
RISQUE_SUPERTREND_PCT = float(os.getenv("RISQUE_SUPERTREND_PCT", "1"))
PERIODE, MULT = 10, 3.0
DEBUT = "2026-11-25"
NOM = (f"Supertrend {PERIODE}/{MULT:g} 4 h : toujours dans le sens de la ligne, retournement quand elle est franchie, "
       f"stop garanti sur la ligne, risque {RISQUE_SUPERTREND_PCT:g} % (expérimentale)")
DESCRIPTION = ("Expérience lancée le 25/11/2026, trouvée sur les réseaux (Supertrend 10/3) : suit la tendance de "
               "l'Ethereum en 4 h. Seule idée sur 48 qui gagne sur des données jamais vues (2017-2025 : +138 R) "
               "ET sur les 2 dernières années (+10 R). Avantage en baisse : preuve moyenne.")


def signaux_supertrend(df: pd.DataFrame, n: int = PERIODE, mult: float = MULT) -> pd.DataFrame:
    """Par bougie TERMINÉE : sens (+1/-1), ligne, nouveau (retournement sur cette bougie), dist (stop), atr.
    Mêmes calculs que backtest/reseaux.py:supertrend (vérifié par un test)."""
    m = milieu(df) if "close_bid" in df else df
    h, l, c = m.high.values, m.low.values, m.close.values
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    a = pd.Series(tr).rolling(n).mean().bfill().values
    a14 = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values
    hl2 = (h + l) / 2
    up, dn = hl2 - mult * a, hl2 + mult * a
    d = np.ones(len(c), dtype=int)
    for i in range(1, len(c)):
        if c[i - 1] > up[i - 1]:
            up[i] = max(up[i], up[i - 1])
        if c[i - 1] < dn[i - 1]:
            dn[i] = min(dn[i], dn[i - 1])
        d[i] = 1 if (d[i - 1] == -1 and c[i] > dn[i - 1]) else -1 if (d[i - 1] == 1 and c[i] < up[i - 1]) else d[i - 1]
    ligne = np.where(d == 1, up, dn)
    nouveau = np.r_[True, d[1:] != d[:-1]]
    return pd.DataFrame({"sens": d, "ligne": ligne, "nouveau": nouveau, "dist": np.abs(c - ligne) + 0.1 * a14,
                         "atr": a14, "cloture": c}, index=m.index)


def _id(conf: dict) -> str | None:
    deals = conf.get("affectedDeals") or []
    return (deals[0].get("dealId") if deals else None) or conf.get("dealId")


def tour_supertrend(api, donnees: dict, epic: str, positions: list, capital: float, disponible: float,
                    eurusd: float, noter, garde, quand: str, peut_entrer: bool = True) -> str:
    etat = donnees.setdefault("supertrend", {})
    deals = etat.setdefault("deals", {})  # dealId -> {"epic", "bougie": bougie du signal}
    ouverts = {p["position"]["dealId"] for p in positions}
    for d in [d for d in deals if d not in ouverts]:
        del deals[d]
    marche = etat.setdefault("marches", {}).setdefault(epic, {})
    miennes = [p for p in positions if p["position"]["dealId"] in deals and p["market"]["epic"] == epic]

    bougies = api.bougies(epic, UNITE, 400)
    if len(bougies) < 100:
        return "Pas assez d'historique"
    df = bougies_vers_df(bougies[:-1])
    s = signaux_supertrend(df)
    der = s.iloc[-1]
    prix_achat, prix_vente = bougies[-1]["closePrice"]["ask"], bougies[-1]["closePrice"]["bid"]
    marche.update({"prix": round((prix_achat + prix_vente) / 2, 2), "ligne": round(float(der.ligne), 2),
                   "sens": int(der.sens), "atr": round(float(der.atr), 2)})
    voulu = "BUY" if der.sens > 0 else "SELL"
    mot = "ACHAT" if voulu == "BUY" else "VENTE"

    # 1) Sortie : la ligne a été franchie dans l'autre sens -> on ferme (puis on se retourne plus bas)
    for p in [p for p in miennes if p["position"]["direction"] != voulu]:
        conf = api.fermer(p["position"]["dealId"])
        if conf.get("dealStatus") == "ACCEPTED":
            noter_fermeture(donnees, p, conf, quand, "[Supertrend] la ligne a été franchie dans l'autre sens")
            del deals[p["position"]["dealId"]]
        noter("fermeture", epic, f"[Supertrend] Ligne franchie dans l'autre sens : position fermée (gain/perte : "
              f"{p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
    fermees = {p["position"]["dealId"] for p in miennes if p["position"]["direction"] != voulu}
    positions = [p for p in positions if p["position"]["dealId"] not in fermees]
    miennes = [p for p in miennes if p["position"]["direction"] == voulu]
    if miennes:
        return f"Position en cours ({'hausse' if voulu == 'BUY' else 'baisse'}, sortie si la ligne est franchie)"
    if not peut_entrer:
        return "Désactivée"

    # 2) Entrée : seulement sur un retournement de la DERNIÈRE bougie terminée, jamais deux fois le même
    if not der.nouveau:
        return f"En attente d'un retournement (sens actuel : {'hausse' if voulu == 'BUY' else 'baisse'})"
    bougie = str(s.index[-1])
    entrees = donnees.setdefault("entrees", {})
    if entrees.get(f"supertrend:{epic}") == bougie:
        return "Signal déjà utilisé"
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    prix = prix_achat if voulu == "BUY" else prix_vente
    mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
    distance = max(float(der.dist), mini * 1.05)
    refus = None
    if regles["statut"] != "TRADEABLE":
        refus = "marché fermé"
    elif any(p["market"]["epic"] == epic and p["position"]["direction"] != voulu for p in positions):
        refus = "une autre position est dans l'autre sens sur ce marché"
    elif abs(prix - float(der.cloture)) > float(der.atr):
        refus = "le prix a trop bougé depuis le signal (écart > 1 ATR)"
    elif (prix_achat - prix_vente) > distance * 0.10:
        refus = "spread trop cher par rapport au stop"
    taux = taux_devise(regles, eurusd, prix)
    pas = regles["pas"]
    taille = math.floor(capital * RISQUE_SUPERTREND_PCT / 100 * taux / distance / pas) * pas
    taille_marge = math.floor(disponible * taux / (prix * regles["marge"]) * 0.5 / pas) * pas
    taille = round(min(taille, taille_marge), 6)
    if not refus and taille < regles["taille_min"]:
        # petit compte : on accepte la taille minimale si elle ne risque pas plus de 2 × le risque prévu
        mini_eur = regles["taille_min"] * distance / taux
        if mini_eur <= capital * 2 * RISQUE_SUPERTREND_PCT / 100 and regles["taille_min"] <= taille_marge:
            taille = regles["taille_min"]
        else:
            refus = f"capital trop faible pour la taille minimale ({regles['taille_min']}, risque {mini_eur:.2f} €)"
    if not refus and garde is not None:
        garde.taux[epic] = taux
        ok, raison = garde.autoriser(taille * distance / taux, distance, "supertrend_4h", epic)
        refus = None if ok else raison
    if refus:
        entrees[f"supertrend:{epic}"] = bougie  # comme le backtest : un signal non pris est perdu
        noter("analyse", epic, f"[Supertrend] Retournement ({mot}) mais ordre REFUSÉ : {refus}.")
        return f"Refusé : {refus}"
    conf = api.ouvrir(epic, voulu, taille, prix=prix, stop_distance=distance, garanti=True)
    entrees[f"supertrend:{epic}"] = bougie
    if conf.get("dealStatus") != "ACCEPTED":
        noter("erreur", epic, f"[Supertrend] Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
        return "Refusé par Capital.com"
    deal = _id(conf)
    if deal:
        deals[deal] = {"epic": epic, "bougie": bougie}
    if garde is not None:
        stop = prix - distance if voulu == "BUY" else prix + distance
        garde.enregistrer({"market": {"epic": epic},
                           "position": {"level": prix, "stopLevel": stop, "size": taille, "direction": voulu}})
    noter("ordre", epic, f"[Supertrend] Retournement sur la bougie 4 h de {bougie[:16]} : {mot} de {taille} à "
          f"{float(conf.get('level') or prix):.2f}, stop garanti à {distance:.2f} "
          f"(risque max ≈ {taille * distance / taux:.2f} €).")
    return f"{mot} de {taille}"


def premiere_fois(donnees: dict, noter) -> None:
    """Note une seule fois dans le Journal la date de début de l'expérience."""
    if donnees.setdefault("supertrend", {}).get("depuis"):
        return
    donnees["supertrend"]["depuis"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    noter("commande", "", "Nouveau (25/11/2026) : stratégie EXPÉRIMENTALE « Supertrend 4 h » sur l'Ethereum, "
          "risque 1 %, trouvée sur les réseaux. Seule idée sur 48 qui gagne sur des données jamais vues "
          "(2017-2025 : +138 R) et sur les 2 dernières années (+10 R). Marché à part : elle ne change rien "
          "aux autres stratégies.")

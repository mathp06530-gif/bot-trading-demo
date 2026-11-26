"""Stratégies trouvées par l'USINE À STRATÉGIES (backtest/usine.py), jouées en démo, risque 1 % chacune.

La liste vient de bot/usine_strategies.json (une stratégie par marché, sur des marchés où aucune autre stratégie
du bot ne trade). Les règles sont celles de bot/usine_regles.py, exactement les mêmes que dans le backtest :
  - entrée à l'ouverture qui suit un signal NOUVEAU sur la dernière bougie terminée, jamais deux fois le même ;
  - stop GARANTI à k × ATR, objectif (TP) éventuel à x R, stop suiveur éventuel à k × ATR du meilleur prix
    (déplacé à chaque nouvelle bougie terminée), sortie si le signal s'inverse ou après N bougies.
"""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from bot import usine_regles as R
from bot.cassure import regles_marche, taux_devise
from bot.registre import noter_fermeture
from bot.strategie import bougies_vers_df

ACTIVE = os.getenv("USINE", "oui").strip().lower() in ("oui", "1", "true", "on")
RISQUE_USINE_PCT = float(os.getenv("RISQUE_USINE_PCT", "1"))
FICHIER = Path(__file__).resolve().parent / "usine_strategies.json"
DEBUT = "2026-11-26"


def charger() -> list:
    try:
        liste = json.loads(FICHIER.read_text())
    except Exception:
        return []
    exclus = {m.strip() for m in os.getenv("USINE_SANS", "").split(",") if m.strip()}
    return [s for s in liste if s["epic"] not in exclus]


STRATEGIES = charger()
LISTE = [s["epic"] for s in STRATEGIES]
NOM = f"Stratégies de l'usine, risque {RISQUE_USINE_PCT:g} % chacune (expérimentales)"
DESCRIPTION = ("Expérience lancée le 26/11/2026 : stratégies fabriquées et triées par l'usine (des dizaines de milliers "
               "d'essais sur ~40 marchés), gardées seulement si elles gagnent sur 2022-2026, des années jamais vues "
               "pendant la fabrication, même avec des frais x 1,5.")


def _id(conf: dict) -> str | None:
    deals = conf.get("affectedDeals") or []
    return (deals[0].get("dealId") if deals else None) or conf.get("dealId")


def nombre_bougies(unite: str) -> int:
    return 1000 if unite == "HOUR_4" else 700


def tour_usine(api, donnees: dict, strat: dict, positions: list, capital: float, disponible: float, eurusd: float,
               noter, garde, quand: str, peut_entrer: bool = True) -> str:
    epic, unite, spec = strat["epic"], strat["unite"], strat["spec"]
    etat = donnees.setdefault("usine", {})
    deals = etat.setdefault("deals", {})  # dealId -> {"epic", "bougie" (signal), "entree" (1re bougie), "sens"}
    ouverts = {p["position"]["dealId"] for p in positions}
    for d in [d for d in deals if d not in ouverts]:
        del deals[d]
    marche = etat.setdefault("marches", {}).setdefault(epic, {})
    miennes = [p for p in positions if p["position"]["dealId"] in deals and p["market"]["epic"] == epic]

    bougies = api.bougies(epic, unite, nombre_bougies(unite))
    if len(bougies) < 300:
        return "Pas assez d'historique"
    df = bougies_vers_df(bougies[:-1])  # la dernière bougie n'est pas terminée
    ind = R.Indicateurs(df)
    voulu, ok, dstop, dobj = R.preparer(ind, spec)
    v, atr = int(voulu[-1]), float(ind.atr.iloc[-1])
    m = ind.m
    prix_achat, prix_vente = bougies[-1]["closePrice"]["ask"], bougies[-1]["closePrice"]["bid"]
    marche.update({"prix": round((prix_achat + prix_vente) / 2, 5), "sens": v, "atr": round(atr, 5),
                   "regle": strat.get("texte", R.decrire(spec))})
    tag = f"[Usine {epic}]"

    # 1) Sorties : signal inversé / disparu, ou durée maximale atteinte (comme le backtest : à l'ouverture suivante)
    fermees = set()
    for p in miennes:
        pos = p["position"]
        info = deals[pos["dealId"]]
        sens = 1 if pos["direction"] == "BUY" else -1
        depuis = pd.Timestamp(info.get("entree") or pos.get("createdDateUTC") or df.index[-1])
        depuis = depuis.tz_localize("UTC") if depuis.tzinfo is None else depuis
        barres = int((df.index >= depuis).sum())
        raison = None
        if v != sens:
            raison = "le signal s'est inversé" if v else "le signal a disparu"
        elif spec.get("duree") and barres >= spec["duree"]:
            raison = f"durée maximale atteinte ({spec['duree']} bougies)"
        if raison:
            conf = api.fermer(pos["dealId"])
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, quand, f"{tag} {raison}")
                del deals[pos["dealId"]]
                fermees.add(pos["dealId"])
            noter("fermeture", epic, f"{tag} {raison[0].upper() + raison[1:]} : position fermée (gain/perte : "
                  f"{pos.get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
            continue
        # 2) Stop suiveur : k × ATR derrière le meilleur prix depuis l'entrée (bougies terminées), sans jamais reculer
        if spec.get("suiveur"):
            depuis_df = m[m.index >= depuis]
            if len(depuis_df):
                regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
                mini = float(m.close.iloc[-1]) * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
                if sens > 0:
                    cible = min(float(depuis_df.high.max()) - spec["suiveur"] * atr, float(m.close.iloc[-1]) - mini * 1.05)
                else:
                    cible = max(float(depuis_df.low.min()) + spec["suiveur"] * atr, float(m.close.iloc[-1]) + mini * 1.05)
                actuel = pos.get("stopLevel")
                if actuel is not None and (cible - float(actuel)) * sens > float(m.close.iloc[-1]) * 0.0005:
                    conf = api.modifier_stop(pos["dealId"], cible, bool(pos.get("guaranteedStop", True)))
                    if conf.get("dealStatus") == "ACCEPTED":
                        pos["stopLevel"] = cible
                        noter("stop", epic, f"{tag} Stop suiveur déplacé de {float(actuel):.5g} à {cible:.5g}.")
    positions = [p for p in positions if p["position"]["dealId"] not in fermees]
    miennes = [p for p in miennes if p["position"]["dealId"] not in fermees]
    if miennes:
        return f"Position en cours ({'hausse' if miennes[0]['position']['direction'] == 'BUY' else 'baisse'})"
    if not peut_entrer:
        return "Désactivée"

    # 3) Entrée : signal NOUVEAU sur la dernière bougie terminée
    if not (ok[-1] and v):
        return "En attente d'un signal"
    bougie = str(df.index[-1])
    entrees = donnees.setdefault("entrees", {})
    if entrees.get(f"usine:{epic}") == bougie:
        return "Signal déjà utilisé"
    voulu_txt = "BUY" if v > 0 else "SELL"
    mot = "ACHAT" if v > 0 else "VENTE"
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    prix = prix_achat if v > 0 else prix_vente
    mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
    distance = max(float(dstop[-1]), mini * 1.05)
    objectif = float(dobj[-1]) if dobj[-1] == dobj[-1] else None
    refus = None
    if regles["statut"] != "TRADEABLE":
        refus = "marché fermé"
    elif any(p["market"]["epic"] == epic and p["position"]["direction"] != voulu_txt for p in positions):
        refus = "une autre position est dans l'autre sens sur ce marché"
    elif abs(prix - float(m.close.iloc[-1])) > atr:
        refus = "le prix a trop bougé depuis le signal (écart > 1 ATR)"
    elif (prix_achat - prix_vente) > distance * 0.10:
        refus = "spread trop cher par rapport au stop"
    taux = taux_devise(regles, eurusd, prix) if regles.get("devise") != "JPY" or epic == "USDJPY" else None
    if taux is None and not refus:
        refus = "devise du marché non gérée"
    taille = 0.0
    if not refus:
        pas = regles["pas"]
        taille = math.floor(capital * RISQUE_USINE_PCT / 100 * taux / distance / pas) * pas
        taille_marge = math.floor(disponible * taux / (prix * regles["marge"]) * 0.5 / pas) * pas
        taille = round(min(taille, taille_marge), 6)
        if taille < regles["taille_min"]:
            mini_eur = regles["taille_min"] * distance / taux
            if mini_eur <= capital * 2 * RISQUE_USINE_PCT / 100 and regles["taille_min"] <= taille_marge:
                taille = regles["taille_min"]
            else:
                refus = f"capital trop faible pour la taille minimale ({regles['taille_min']}, risque {mini_eur:.2f} €)"
    if not refus and garde is not None:
        garde.taux[epic] = taux
        ok_g, raison = garde.autoriser(taille * distance / taux, distance, "usine", epic)
        refus = None if ok_g else raison
    if refus:
        entrees[f"usine:{epic}"] = bougie  # comme le backtest : un signal non pris est perdu
        noter("analyse", epic, f"{tag} Signal ({mot}) mais ordre REFUSÉ : {refus}.")
        return f"Refusé : {refus}"
    conf = api.ouvrir(epic, voulu_txt, taille, prix=prix, stop_distance=distance, garanti=True,
                      objectif_distance=objectif)
    entrees[f"usine:{epic}"] = bougie
    if conf.get("dealStatus") != "ACCEPTED":
        noter("erreur", epic, f"{tag} Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
        return "Refusé par Capital.com"
    deal = _id(conf)
    if deal:
        entree = bougies[-1]["snapshotTimeUTC"]  # 1re bougie de la position (celle en cours)
        deals[deal] = {"epic": epic, "bougie": bougie, "entree": entree, "sens": v}
    if garde is not None:
        stop = prix - distance * v
        garde.enregistrer({"market": {"epic": epic},
                           "position": {"level": prix, "stopLevel": stop, "size": taille, "direction": voulu_txt}})
    noter("ordre", epic, f"{tag} {strat.get('texte', '')} : {mot} de {taille} à {float(conf.get('level') or prix):.5g}, "
          f"stop garanti à {distance:.5g}{f', objectif à {objectif:.5g}' if objectif else ''} "
          f"(risque max ≈ {taille * distance / taux:.2f} €).")
    return f"{mot} de {taille}"


def premiere_fois(donnees: dict, noter) -> None:
    if not STRATEGIES or donnees.setdefault("usine", {}).get("depuis"):
        return
    donnees["usine"]["depuis"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    noter("commande", "", f"Nouveau (26/11/2026) : {len(STRATEGIES)} stratégie(s) EXPÉRIMENTALE(S) de l'usine à "
          f"stratégies, risque {RISQUE_USINE_PCT:g} % chacune, sur {', '.join(LISTE)}. Trouvées parmi des dizaines de "
          "milliers d'essais et gardées seulement si elles gagnent sur des années jamais vues (2022-2026).")

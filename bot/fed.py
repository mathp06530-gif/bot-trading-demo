"""Stratégie EXPÉRIMENTALE « AVANT LA FED » sur le Nasdaq 100 (US100), 26/11/2026, recherche « gains rapides ».

Idée connue (Lucca & Moench, Fed de New York, 2015) : les actions américaines montent en moyenne pendant les
24 h qui précèdent une annonce de la Fed (FOMC, 8 fois par an). Des chercheurs disent qu'elle a disparu après
2015 (Kurov, Wolfe & Gilbert 2021) : on l'a donc retestée nous-mêmes sur les prix Capital.com.

Règles (une seule idée testée, réglages choisis sur 2017-2021) :
  - ACHAT du US100 la veille de l'annonce à 14 h (heure de New York) ;
  - stop garanti à 1 × ATR 14 jours (amplitude moyenne d'une journée, calculée sur les jours terminés) ;
  - fermeture le jour de l'annonce à 13 h 50 (heure de New York), JUSTE AVANT l'annonce (on ne parie pas
    sur la décision elle-même). Une seule entrée par annonce. Risque RISQUE_FED_PCT (1 %) du capital.

Backtest 1 h Capital.com démo (backtest/asymetrie.py, spread, frais de nuit, prime du stop garanti comptés) :
  - 2017-2021 (réglages) +7,5 R ; 2022-06/2024 (jamais vu) +4,4 R ; 07/2024-2026 (jamais vu) +3,2 R ;
    ~80 annonces, ~0,19 R par trade. Même sens sur US500, US30 et DE40 aux 3 périodes.
  - Contrôle sur prix au hasard : entre +0,9 et +7,5 R au total (le hasard peut donc faire une partie de ça).
LIMITES : seulement 8 trades par an ; preuve FAIBLE à moyenne. Ce n'est PAS une méthode pour aller vite.
Les dates FOMC 2027 ne sont pas encore dans la liste : les ajouter dans FED_DATES (reglages.env).
"""
import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

from bot.cassure import regles_marche, taux_devise
from bot.registre import noter_fermeture

ACTIVE = os.getenv("FED", "oui").strip().lower() in ("oui", "1", "true", "on")
LISTE = [m.strip() for m in os.getenv("FED_MARCHES", "US100").split(",") if m.strip()]
RISQUE_FED_PCT = float(os.getenv("RISQUE_FED_PCT", "1"))
# Jours d'annonce FOMC (décision à 14 h New York). Source : calendrier publié par la Fed.
DATES = [d.strip() for d in os.getenv("FED_DATES", "2026-12-09").split(",") if d.strip()]
NY = ZoneInfo("America/New_York")
UNITE = "HOUR"
DEBUT = "2026-11-26"
NOM = (f"Achat la veille d'une annonce de la Fed à 14 h (New York), fermeture juste avant l'annonce, "
       f"stop garanti 1 ATR jour, risque {RISQUE_FED_PCT:g} % (expérimentale)")
DESCRIPTION = ("Expérience du 26/11/2026 : les actions américaines montent en moyenne la veille d'une annonce de la "
               "Fed. Achat du Nasdaq 100 la veille à 14 h (New York), vente juste avant l'annonce. Backtest 10 ans "
               "Capital.com : +7,5 R (2017-21), +4,4 R puis +3,2 R sur des années jamais vues. 8 trades par an, "
               "preuve faible à moyenne.")


def veille_ouvree(jour):
    v = jour - timedelta(days=1)
    while v.weekday() >= 5:
        v -= timedelta(days=1)
    return v


def phase(instant: datetime, dates=None) -> tuple[str, str | None]:
    """("entrer", date) : entre la veille 14 h et 18 h (New York) ; ("garder", date) : jusqu'au jour J 13 h 50 ;
    ("sortir", date) : jour J après 13 h 50 ; ("rien", None) sinon."""
    ny = instant.astimezone(NY)
    for d in dates if dates is not None else DATES:
        try:
            jour = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        v = veille_ouvree(jour)
        h = ny.hour + ny.minute / 60
        if ny.date() == v and 14 <= h < 18:
            return "entrer", d
        if (ny.date() == v and h >= 18) or (ny.date() == jour and h < 13 + 50 / 60):
            return "garder", d
        if ny.date() == jour or (ny.date() > jour and ny.date() <= jour + timedelta(days=4)):
            return "sortir", d
    return "rien", None


def atr_jour(bougies_jour: list, n: int = 14) -> float | None:
    """ATR 14 jours de Wilder sur les jours TERMINÉS (prix milieu), comme backtest/asymetrie.py:atr_jour."""
    b = bougies_jour[:-1]  # la dernière bougie jour est celle d'aujourd'hui, pas terminée
    if len(b) < n + 2:
        return None
    m = lambda x, k: (x[k]["bid"] + x[k]["ask"]) / 2
    h = np.array([m(x, "highPrice") for x in b])
    lo = np.array([m(x, "lowPrice") for x in b])
    c = np.array([m(x, "closePrice") for x in b])
    tr = np.maximum(h[1:] - lo[1:], np.maximum(abs(h[1:] - c[:-1]), abs(lo[1:] - c[:-1])))
    a = tr[0]
    for x in tr[1:]:
        a += (x - a) / n
    return float(a)


def _id(conf: dict) -> str | None:
    deals = conf.get("affectedDeals") or []
    return (deals[0].get("dealId") if deals else None) or conf.get("dealId")


def tour_fed(api, donnees: dict, epic: str, positions: list, capital: float, disponible: float, eurusd: float,
             noter, garde, quand: str, peut_entrer: bool = True, instant: datetime | None = None) -> str:
    instant = instant or datetime.now(timezone.utc)
    etat = donnees.setdefault("fed", {})
    deals = etat.setdefault("deals", {})  # dealId -> {"epic", "annonce"}
    ouverts = {p["position"]["dealId"] for p in positions}
    for d in [d for d in deals if d not in ouverts]:
        del deals[d]
    marche = etat.setdefault("marches", {}).setdefault(epic, {})
    miennes = [p for p in positions if p["position"]["dealId"] in deals and p["market"]["epic"] == epic]
    ph, annonce = phase(instant)
    futures = [d for d in DATES if d >= instant.astimezone(NY).strftime("%Y-%m-%d")]
    marche["prochaine_annonce"] = futures[0] if futures else None

    # 1) Sortie : juste avant l'annonce (ou si une position traîne après)
    if miennes and ph not in ("entrer", "garder"):
        for p in miennes:
            conf = api.fermer(p["position"]["dealId"])
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, quand, "[Fed] fermeture juste avant l'annonce de la Fed")
                del deals[p["position"]["dealId"]]
            noter("fermeture", epic, f"[Fed] Fermeture juste avant l'annonce de la Fed (gain/perte : "
                  f"{p['position'].get('upl', 0):.2f}). Statut : {conf.get('dealStatus', '?')}")
        return "Position fermée avant l'annonce"
    if miennes:
        return f"Position en cours, fermeture le {annonce} à 13 h 50 (New York), juste avant l'annonce"
    if not futures:
        return "Plus aucune date d'annonce connue : ajouter les dates FOMC dans FED_DATES (reglages.env)"
    if ph != "entrer":
        return f"En attente : achat la veille de l'annonce du {futures[0]} à 14 h (New York)"
    if not peut_entrer:
        return "Désactivée"
    entrees = donnees.setdefault("entrees", {})
    if entrees.get(f"fed:{epic}") == annonce:
        return "Déjà entré pour cette annonce"

    # 2) Entrée : achat avec stop garanti à 1 ATR jour
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    atr = atr_jour(api.bougies(epic, "DAY", 40))
    b = api.bougies(epic, "MINUTE", 2)
    if not b or atr is None:
        return "Pas assez d'historique"
    prix, prix_vente = b[-1]["closePrice"]["ask"], b[-1]["closePrice"]["bid"]
    marche.update({"prix": round((prix + prix_vente) / 2, 2), "atr_jour": round(atr, 2)})
    mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
    distance = max(atr, mini * 1.05)
    refus = None
    if regles["statut"] != "TRADEABLE":
        refus = "marché fermé"
    elif any(p["market"]["epic"] == epic and p["position"]["direction"] != "BUY" for p in positions):
        refus = "une autre position est en vente sur ce marché"
    elif (prix - prix_vente) > distance * 0.10:
        refus = "spread trop cher par rapport au stop"
    taux = taux_devise(regles, eurusd, prix)
    pas = regles["pas"]
    taille = math.floor(capital * RISQUE_FED_PCT / 100 * taux / distance / pas) * pas
    taille_marge = math.floor(disponible * taux / (prix * regles["marge"]) * 0.5 / pas) * pas
    taille = round(min(taille, taille_marge), 6)
    if not refus and taille < regles["taille_min"]:
        mini_eur = regles["taille_min"] * distance / taux
        if mini_eur <= capital * 2 * RISQUE_FED_PCT / 100 and regles["taille_min"] <= taille_marge:
            taille = regles["taille_min"]
        else:
            refus = f"capital trop faible pour la taille minimale ({regles['taille_min']}, risque {mini_eur:.2f} €)"
    if not refus and garde is not None:
        garde.taux[epic] = taux
        ok, raison = garde.autoriser(taille * distance / taux, distance, "fed", epic)
        refus = None if ok else raison
    if refus:
        noter("analyse", epic, f"[Fed] Veille de l'annonce du {annonce} : achat REFUSÉ pour l'instant : {refus}.")
        return f"Refusé : {refus}"
    conf = api.ouvrir(epic, "BUY", taille, prix=prix, stop_distance=distance, garanti=True)
    entrees[f"fed:{epic}"] = annonce
    if conf.get("dealStatus") != "ACCEPTED":
        noter("erreur", epic, f"[Fed] Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
        return "Refusé par Capital.com"
    deal = _id(conf)
    if deal:
        deals[deal] = {"epic": epic, "annonce": annonce}
    if garde is not None:
        garde.enregistrer({"market": {"epic": epic},
                           "position": {"level": prix, "stopLevel": prix - distance, "size": taille, "direction": "BUY"}})
    noter("ordre", epic, f"[Fed] Veille de l'annonce de la Fed du {annonce} : ACHAT de {taille} à "
          f"{float(conf.get('level') or prix):.2f}, stop garanti à {distance:.2f} (1 ATR jour, risque max ≈ "
          f"{taille * distance / taux:.2f} €). Fermeture demain 13 h 50 (New York), juste avant l'annonce.")
    return f"ACHAT de {taille}"


def premiere_fois(donnees: dict, noter) -> None:
    if donnees.setdefault("fed", {}).get("depuis"):
        return
    donnees["fed"]["depuis"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    noter("commande", "", "Nouveau (26/11/2026) : stratégie EXPÉRIMENTALE « Avant la Fed » sur le Nasdaq 100, "
          "risque 1 %. Achat la veille d'une annonce de la Fed, vente juste avant l'annonce. Backtest 10 ans : gagnante "
          "sur 2017-21 et sur les années jamais vues (+4,4 R puis +3,2 R), mais seulement 8 trades par an. "
          "Prochaine annonce : 9/12/2026.")

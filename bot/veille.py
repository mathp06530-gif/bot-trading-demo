"""VEILLE D'ACTUS (26/11/2026, idée reprise du skill trader-news).

Deux choses, toutes gratuites et sans clé :
  1. Les derniers titres Yahoo Finance de chaque marché tradé (flux RSS public), relus au plus une fois par heure,
     classés par sujet avec des mots-clés (résultats, analystes, banques centrales, géopolitique…) comme le skill.
     C'est de l'INFORMATION pour l'appli : le bot ne lit pas les titres pour décider (un programme qui
     « comprend » une actu se trompe trop souvent ; aucun test ne montre que ça aide).
  2. La date des prochains résultats trimestriels des ACTIONS tradées (Tesla), écrite dans reglages.env
     (RESULTATS_DATES="TSLA=2027-01-27") : Nasdaq bloque les serveurs de GitHub, aucune source gratuite fiable. actualites.pauses_marches() bloque les NOUVELLES positions sur cette action
     PAUSE_RESULTATS_H heures avant et après (le cours peut sauter de 10 % à l'ouverture suivante).
Si une source ne répond pas, le bot continue normalement.
"""
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={}&region=US&lang=en-US"
UA = {"User-Agent": "Mozilla/5.0 (bot-trading-demo)", "Accept": "application/json, text/xml, */*"}
SYMBOLES = {"GOLD": "GC=F", "SILVER": "SI=F", "ETHUSD": "ETH-USD", "BTCUSD": "BTC-USD", "NATURALGAS": "NG=F",
            "OIL_CRUDE": "CL=F", "US500": "^GSPC", "US100": "^NDX"}
ACTIONS = {"TSLA", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL"}  # marchés qui publient des résultats
PAR_MARCHE = 6

# Sujets (repris des mots-clés du skill, adaptés à l'or, l'argent, la crypto, le gaz et Tesla)
SUJETS = [
    ("résultats", r"\bearnings\b|\bresults\b|\bEPS\b|\bguidance\b|\bdeliveries\b|\brevenue\b"),
    ("analystes", r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|price target|\boutperform\b|\bunderperform\b"),
    ("Fed / taux", r"\bFed\b|\bFOMC\b|\bPowell\b|\brate (?:cut|hike)s?\b|\binterest rates?\b|\byields?\b"),
    ("inflation / emploi", r"\bCPI\b|\binflation\b|\bjobs\b|\bpayrolls\b|\bunemployment\b|\bPCE\b"),
    ("dollar", r"\bdollar\b|\bDXY\b|\bgreenback\b"),
    ("géopolitique", r"\bwar\b|\bsanctions?\b|\btariffs?\b|\bIran\b|\bRussia\b|\bUkraine\b|\bChina\b|\bMiddle East\b"),
    ("stocks / météo", r"\bstorage\b|\binventor(?:y|ies)\b|\bweather\b|\bcold\b|\bLNG\b|\bOPEC\b"),
    ("régulation", r"\bSEC\b|\bETF\b|\bregulat|\bapproval\b|\blawsuit\b|\bprobe\b"),
    ("risque", r"\brecall\b|\bhack|\bbreach\b|\boutage\b|\bcrash\b|\bplunge|\bselloff\b|\bsell-off\b"),
]


def sujets(titre: str) -> list[str]:
    return [nom for nom, motif in SUJETS if re.search(motif, titre, re.I)]


def lire_rss(texte: str) -> list[dict]:
    racine = ET.fromstring(texte)
    sortie = []
    for it in racine.iter("item"):
        titre = (it.findtext("title") or "").strip()
        if not titre:
            continue
        quand = None
        try:
            quand = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            pass
        sortie.append({"titre": titre, "lien": (it.findtext("link") or "").strip(),
                       "date": quand.strftime("%Y-%m-%dT%H:%MZ") if quand else None, "sujets": sujets(titre)})
    return sortie


def _titres(symbole: str) -> list[dict]:
    r = requests.get(RSS.format(symbole), headers=UA, timeout=15)
    r.raise_for_status()
    return lire_rss(r.text)


def resultats_reglages(texte: str) -> dict:
    """RESULTATS_DATES="TSLA=2027-01-27" (plusieurs : séparés par des virgules ; heure UTC facultative
    « TSLA=2027-01-27T21:05 »). Sans heure : après la clôture de New York, ~21 h 05 UTC."""
    sortie = {}
    for morceau in (texte or "").split(","):
        if "=" not in morceau:
            continue
        sym, quand = (x.strip() for x in morceau.split("=", 1))
        try:
            d = datetime.fromisoformat(quand if "T" in quand else quand + "T21:05")
        except ValueError:
            continue
        sortie[sym.upper()] = d.strftime("%Y-%m-%dT%H:%MZ")
    return sortie


def mettre_a_jour(donnees: dict, maintenant: datetime, marches: list[str], lire_titres=None, dates_resultats=None):
    """Relit les titres (1 fois par heure) et les dates de résultats (réglages). Renvoie la liste des soucis."""
    etat = donnees.setdefault("veille", {})
    soucis = []
    lu = etat.get("titres_lus_le")
    if not lu or maintenant - datetime.fromisoformat(lu) >= timedelta(hours=1):
        etat["titres_lus_le"] = maintenant.isoformat()
        titres = {}
        for m in marches:
            sym = SYMBOLES.get(m) or (m if m in ACTIONS else None)
            if not sym:
                continue
            try:
                titres[m] = (lire_titres or _titres)(sym)[:PAR_MARCHE]
            except Exception as e:  # jamais bloquant
                soucis.append(f"titres {m} indisponibles ({e})")
                titres[m] = etat.get("titres", {}).get(m, [])
        etat["titres"] = titres
    # Dates des résultats : aucune source gratuite ne répond depuis GitHub Actions (Nasdaq bloque les serveurs,
    # testé le 26/11/2026), donc on les écrit à la main dans reglages.env (Tesla les annonce ~3 semaines avant).
    etat["resultats"] = {a: q for a, q in (dates_resultats if dates_resultats is not None
                                           else resultats_reglages(os.getenv("RESULTATS_DATES", ""))).items()
                         if a in marches}
    return soucis

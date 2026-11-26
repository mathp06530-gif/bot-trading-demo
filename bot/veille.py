"""VEILLE D'ACTUS (26/11/2026, idée reprise du skill trader-news).

Deux choses, toutes gratuites et sans clé :
  1. Les derniers titres Yahoo Finance de chaque marché tradé (flux RSS public), relus au plus une fois par heure,
     classés par sujet avec des mots-clés (résultats, analystes, banques centrales, géopolitique…) comme le skill.
     C'est de l'INFORMATION pour l'appli : le bot ne lit pas les titres pour décider (un programme qui
     « comprend » une actu se trompe trop souvent ; aucun test ne montre que ça aide).
  2. La date des prochains résultats trimestriels des ACTIONS tradées (Tesla) : calendrier public de Nasdaq,
     relu une fois par jour. actualites.pauses_marches() bloque les NOUVELLES positions sur cette action
     PAUSE_RESULTATS_H heures avant et après (le cours peut sauter de 10 % à l'ouverture suivante).
Si une source ne répond pas, le bot continue normalement.
"""
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

RSS = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={}&region=US&lang=en-US"
NASDAQ = "https://api.nasdaq.com/api/calendar/earnings?date={}"
UA = {"User-Agent": "Mozilla/5.0 (bot-trading-demo)", "Accept": "application/json, text/xml, */*"}
SYMBOLES = {"GOLD": "GC=F", "SILVER": "SI=F", "ETHUSD": "ETH-USD", "BTCUSD": "BTC-USD", "NATURALGAS": "NG=F",
            "OIL_CRUDE": "CL=F", "US500": "^GSPC", "US100": "^NDX"}
ACTIONS = {"TSLA", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL"}  # marchés qui publient des résultats
JOURS_RESULTATS = 21   # on cherche les résultats dans les 3 prochaines semaines
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


def lire_nasdaq(donnees_json: dict, symbole: str, jour: str) -> str | None:
    """Heure UTC (approximative) des résultats de `symbole` ce jour-là, d'après une page du calendrier Nasdaq."""
    lignes = ((donnees_json or {}).get("data") or {}).get("rows") or []
    for l in lignes:
        if (l.get("symbol") or "").upper() == symbole:
            moment = (l.get("time") or "").lower()
            # après la clôture ~16 h 05 New York (21 h 05 UTC en hiver), avant l'ouverture ~8 h (13 h UTC)
            heure = "13:00" if "pre" in moment else "21:05"
            return f"{jour}T{heure}Z"
    return None


def _resultats(actions: list[str], maintenant: datetime) -> dict:
    trouves = {}
    for k in range(JOURS_RESULTATS):
        jour = (maintenant + timedelta(days=k)).strftime("%Y-%m-%d")
        r = requests.get(NASDAQ.format(jour), headers=UA, timeout=15)
        r.raise_for_status()
        for a in actions:
            if a not in trouves:
                q = lire_nasdaq(r.json(), a, jour)
                if q:
                    trouves[a] = q
        if len(trouves) == len(actions):
            break
    return trouves


def mettre_a_jour(donnees: dict, maintenant: datetime, marches: list[str], lire_titres=None, lire_resultats=None):
    """Relit les titres (1 fois par heure) et les dates de résultats (1 fois par jour). Renvoie la liste des soucis."""
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
    actions = sorted(set(marches) & ACTIONS)
    lu = etat.get("resultats_lus_le")
    if actions and (not lu or maintenant - datetime.fromisoformat(lu) >= timedelta(hours=24)):
        etat["resultats_lus_le"] = maintenant.isoformat()
        try:
            nouveaux = (lire_resultats or _resultats)(actions, maintenant)
            # on garde une date déjà connue tant que la pause d'après n'est pas finie
            anciens = {a: q for a, q in etat.get("resultats", {}).items()
                       if a in actions and q >= (maintenant - timedelta(days=2)).strftime("%Y-%m-%dT%H:%MZ")}
            etat["resultats"] = {**anciens, **nouveaux}
        except Exception as e:
            soucis.append(f"calendrier des résultats indisponible ({e})")
    return soucis

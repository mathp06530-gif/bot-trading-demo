"""ACTUALITÉS : pause autour des grandes annonces économiques américaines.

Source gratuite : le calendrier de la semaine de ForexFactory (flux JSON public, sans clé).
Le bot le relit au plus une fois par heure et ne garde que les annonces en dollar US
à FORT impact (Fed, emploi, inflation, ventes au détail…).

Règle : aucune NOUVELLE position de PAUSE_AVANT_MIN (30) minutes avant à PAUSE_APRES_MIN (60)
minutes après une de ces annonces. Les positions déjà ouvertes gardent leur stop garanti et
leurs règles de sortie habituelles.
Backtest (90 jours, stratégie rapide) : résultat presque identique (+17 € au lieu de +20 €).
C'est une sécurité contre les mouvements violents, pas une source de gains.
Si le calendrier ne répond pas, le bot continue normalement (il l'écrit dans le journal).
"""
import os
from datetime import datetime, timedelta, timezone

import requests

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
ACTIVE = os.getenv("PAUSE_ANNONCES", "oui").strip().lower() in ("oui", "1", "true", "on")
PAUSE_AVANT_MIN = int(os.getenv("PAUSE_AVANT_MIN", "30"))
PAUSE_APRES_MIN = int(os.getenv("PAUSE_APRES_MIN", "60"))


# Annonces de moindre impact global mais qui font bondir un marché précis : pause sur CE marché seulement.
# Vide depuis le nettoyage du 26/11/2026 (le gaz naturel n'est plus tradé). Exemple : {"Natural Gas Storage": ["NATURALGAS"]}
ANNONCES_MARCHE = {}


def _lire_calendrier() -> list[dict]:
    r = requests.get(URL, timeout=15, headers={"User-Agent": "bot-trading-demo"})
    r.raise_for_status()
    annonces = []
    for e in r.json():
        if e.get("country") != "USD" or not e.get("date"):
            continue
        quand = datetime.fromisoformat(e["date"]).astimezone(timezone.utc)
        a = {"date": quand.strftime("%Y-%m-%dT%H:%MZ"), "titre": e.get("title", "?")}
        if e.get("impact") == "High":
            annonces.append(a)
        else:  # annonces qui ne secouent qu'UN marché (ANNONCES_MARCHE)
            for mot, marches in ANNONCES_MARCHE.items():
                if mot.lower() in a["titre"].lower():
                    annonces.append({**a, "marches": marches})
    return sorted(annonces, key=lambda a: a["date"])


def mettre_a_jour(donnees: dict, maintenant: datetime, lire=None) -> str | None:
    """Relit le calendrier si besoin (au plus 1 fois par heure). Renvoie un message d'erreur ou None."""
    etat = donnees.setdefault("actualites", {})
    derniere = etat.get("lu_le")
    if derniere and maintenant - datetime.fromisoformat(derniere) < timedelta(hours=1):
        return None
    try:
        etat["annonces"] = (lire or _lire_calendrier)()
        etat["lu_le"] = maintenant.isoformat()
        return None
    except Exception as e:  # le bot ne doit jamais s'arrêter à cause du calendrier
        etat["lu_le"] = maintenant.isoformat()
        return f"Calendrier économique indisponible ({e}) : pas de pause annonces à ce tour."


def annonce_en_cours(donnees: dict, maintenant: datetime) -> str | None:
    """Renvoie la raison de la pause si une grande annonce US est proche, sinon None."""
    if not ACTIVE:
        return None
    for a in donnees.get("actualites", {}).get("annonces", []):
        if a.get("marches"):
            continue  # annonce propre à un marché : voir pauses_marches()
        quand = datetime.strptime(a["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        if quand - timedelta(minutes=PAUSE_AVANT_MIN) <= maintenant <= quand + timedelta(minutes=PAUSE_APRES_MIN):
            heure = quand.astimezone(_PARIS).strftime("%H h %M")
            return f"pause actualité : « {a['titre']} » (annonce américaine importante) à {heure}, heure de Paris"
    return None


def pauses_marches(donnees: dict, maintenant: datetime) -> dict:
    """{marché: raison} pour les pauses qui ne concernent qu'un marché (voir ANNONCES_MARCHE)."""
    if not ACTIVE:
        return {}
    sortie = {}
    for a in donnees.get("actualites", {}).get("annonces", []):
        if not a.get("marches"):
            continue
        quand = datetime.strptime(a["date"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
        if quand - timedelta(minutes=PAUSE_AVANT_MIN) <= maintenant <= quand + timedelta(minutes=PAUSE_APRES_MIN):
            heure = quand.astimezone(_PARIS).strftime("%H h %M")
            for m in a["marches"]:
                sortie.setdefault(m, f"pause actualité sur ce marché : « {a['titre']} » à {heure}, heure de Paris")
    return sortie


def prochaines(donnees: dict, maintenant: datetime, n: int = 5) -> list[dict]:
    """Les n prochaines grandes annonces, pour l'application."""
    lim = (maintenant - timedelta(minutes=PAUSE_APRES_MIN)).strftime("%Y-%m-%dT%H:%MZ")
    return [a for a in donnees.get("actualites", {}).get("annonces", []) if a["date"] >= lim][:n]


try:
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover
    _PARIS = timezone(timedelta(hours=1))

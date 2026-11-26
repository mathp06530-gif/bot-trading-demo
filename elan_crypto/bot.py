"""BOT À PART « ÉLAN CRYPTO » (26/11/2026, demande de Mathis : « on peut lancer les trois sur un bot à part »).

Complètement séparé du bot principal (bot/ : Cassure 4 h + Rapide 5 min) :
  - son propre code (ce dossier), son propre workflow (.github/workflows/elan_crypto.yml),
  - ses propres données (docs/elan_crypto.json) et sa propre page (docs/elan.html).
Seule chose en commun : le même compte DÉMO Capital.com (donc le même solde).

Stratégie (trouvée par la recherche « 2 mois », backtest/DEUX_MOIS.md) : ÉLAN 4 h dans le sens de la tendance.
  - sens voulu = hausse si le prix est plus haut qu'il y a N bougies de 4 h, baisse s'il est plus bas ;
  - on n'entre que quand ce sens VIENT de changer, et seulement s'il va dans le sens de la moyenne 200 ;
  - stop GARANTI à 1,5 ATR, pas d'objectif ; sortie quand le sens s'inverse.
  ATTENTION : gagnante sur les 4 derniers mois mais PAS prouvée (le hasard fait aussi bien sur 2 mois). Expérience.

Protection du bot principal (même compte) :
  - 1 % de risque par trade, 1 position max par marché : au pire 4 % du compte en jeu en même temps ;
  - plus aucune entrée si le bot principal est en pause ou si son coupe-circuit a sauté ;
  - coupe-circuit à part : plus d'entrée si ce bot a perdu 3 % du compte dans la journée ou 10 % depuis le départ.

Lancement : python -m elan_crypto.bot   (GitHub Actions toutes les 30 min, voir le workflow)
Couper : ELAN_CRYPTO="non" dans reglages.env (les positions ouvertes restent protégées par leur stop garanti).
"""
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from bot.capital import CapitalDemo
from bot.cassure import regles_marche, taux_devise
from bot.strategie import bougies_vers_df

RACINE = Path(__file__).resolve().parent.parent
FICHIER = RACINE / "docs" / "elan_crypto.json"
FICHIER_PRINCIPAL = RACINE / "docs" / "data.json"

ACTIF = os.getenv("ELAN_CRYPTO", "oui").strip().lower() in ("oui", "1", "true", "on")
RISQUE_PCT = float(os.getenv("RISQUE_ELAN_CRYPTO_PCT", "1"))
PERTE_JOUR_PCT = 3.0     # coupe-circuit à part : -3 % du compte dans la journée…
PERTE_TOTALE_PCT = 10.0  # …ou -10 % depuis le départ : plus de nouvelle entrée
STOP_ATR = 1.5
UNITE = "HOUR_4"
DUREE_BOUGIE = timedelta(hours=4)
# marché -> N (élan sur N bougies de 4 h), réglages trouvés par la recherche « 2 mois »
MARCHES = {"ETHUSD": 50, "LTCUSD": 50, "SOLUSD": 50, "XRPUSD": 200}
NOMS = {"ETHUSD": "Ethereum", "LTCUSD": "Litecoin", "SOLUSD": "Solana", "XRPUSD": "XRP"}
MAX_JOURNAL = 500


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def horodatage(t: datetime | None = None) -> str:
    return (t or maintenant()).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- règles (identiques au backtest)
def _wilder(x: pd.Series, n: int) -> pd.Series:
    return x.ewm(alpha=1 / n, adjust=False).mean()


def signaux(df: pd.DataFrame, n: int) -> dict:
    """df : bougies TERMINÉES (colonnes _bid/_ask). Renvoie le sens voulu sur la dernière bougie (+1/-1/0),
    si une entrée est permise (sens nouveau ET dans le sens de la moyenne 200), l'ATR 14 et le dernier prix."""
    m = pd.DataFrame({k: (df[f"{k}_bid"] + df[f"{k}_ask"]) / 2 for k in ("open", "high", "low", "close")})
    c = m.close
    sens = np.sign(c / c.shift(n) - 1).fillna(0).astype(int).values
    pc = c.shift()
    tr = pd.concat([m.high - m.low, (m.high - pc).abs(), (m.low - pc).abs()], axis=1).max(axis=1)
    atr = _wilder(tr, 14)
    sma = c.rolling(200).mean().values
    v = int(sens[-1])
    nouveau = len(sens) > 1 and v != 0 and v != sens[-2]
    tendance = (v > 0 and c.iloc[-1] > sma[-1]) or (v < 0 and c.iloc[-1] < sma[-1])
    return {"sens": v, "entree": bool(nouveau and tendance and len(c) > 200), "atr": float(atr.iloc[-1]),
            "prix": float(c.iloc[-1]), "sma200": float(sma[-1]) if sma[-1] == sma[-1] else None,
            "bougie": str(df.index[-1])}


def bougies_terminees(bougies: list, quand: datetime) -> list:
    """Enlève la bougie en cours (celle qui n'a pas encore 4 h)."""
    out = []
    for b in bougies:
        debut = pd.Timestamp(b["snapshotTimeUTC"], tz="UTC").to_pydatetime()
        if debut + DUREE_BOUGIE <= quand:
            out.append(b)
    return out


# --------------------------------------------------------------------------- données
def charger() -> dict:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def sauver(d: dict):
    d["journal"] = d.get("journal", [])[-MAX_JOURNAL:]
    FICHIER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def etat_principal() -> dict:
    try:
        p = json.loads(FICHIER_PRINCIPAL.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {"pause": bool(p.get("pause")), "coupe_circuit": bool(p.get("garde_fous", {}).get("coupe_circuit"))}


# --------------------------------------------------------------------------- un tour
def un_tour(d: dict, api, quand: datetime | None = None) -> dict:
    quand = quand or maintenant()
    q = horodatage(quand)
    journal = d.setdefault("journal", [])

    def noter(type_, marche, texte):
        journal.append({"date": q, "type": type_, "marche": marche, "texte": texte})

    if not d.get("depuis"):
        d["depuis"] = q
        noter("commande", "", "Démarrage du bot à part « Élan crypto » (expérimental, démo, 1 % par trade) sur "
              "Ethereum, Litecoin, Solana et XRP. Gagnant sur les 4 derniers mois, mais pas prouvé.")
    d["nom"] = "Élan crypto 4 h (bot à part, expérimental)"
    d["risque_pct"] = RISQUE_PCT
    d["actif"] = ACTIF
    d["dernier_tour"] = q
    deals = d.setdefault("deals", {})       # dealId -> infos de la position ouverte par CE bot
    ordres = d.setdefault("ordres", [])     # historique des trades de ce bot
    marches = d.setdefault("marches", {})

    api.connexion()
    positions = api.positions()
    compte = next((c for c in api.comptes() if c.get("preferred")), None) or (api.comptes() or [{}])[0]
    capital = float(compte.get("balance", {}).get("balance") or 0)
    disponible = float(compte.get("balance", {}).get("available") or capital)
    eurusd = api.taux_eurusd()
    d.setdefault("capital_depart", capital)
    par_id = {p["position"]["dealId"]: p for p in positions}

    # 1) Positions de ce bot fermées par Capital.com (stop garanti touché) : on enregistre le dernier résultat vu
    for deal, info in list(deals.items()):
        if deal not in par_id:
            res = info.get("resultat", 0.0)
            ordres.append({**info, "id": deal, "statut": "ferme", "ferme_le": q, "resultat": res,
                           "motif_sortie": "Stop garanti touché (résultat estimé)"})
            noter("fermeture", info["epic"], f"Position fermée par le stop garanti (≈ {res:.2f} €).")
            del deals[deal]
        else:
            info["resultat"] = float(par_id[deal]["position"].get("upl") or 0)

    # 2) Coupe-circuits (protègent le bot principal qui partage le compte)
    jour = q[:10]
    perdu_jour = -sum(o["resultat"] for o in ordres if (o.get("ferme_le") or "")[:10] == jour and o["resultat"] < 0)
    total = sum(o["resultat"] for o in ordres)
    latent = sum(i.get("resultat", 0.0) for i in deals.values())
    princ = etat_principal()
    blocage = None
    if not ACTIF:
        blocage = "bot coupé (ELAN_CRYPTO=non)"
    elif princ.get("pause") or princ.get("coupe_circuit"):
        blocage = "le bot principal est en pause ou son coupe-circuit a sauté"
    elif perdu_jour >= d["capital_depart"] * PERTE_JOUR_PCT / 100:
        blocage = f"perte du jour de ce bot ≥ {PERTE_JOUR_PCT:g} % du compte"
    elif total <= -d["capital_depart"] * PERTE_TOTALE_PCT / 100:
        blocage = f"perte totale de ce bot ≥ {PERTE_TOTALE_PCT:g} % du compte"
    d["bilan"] = {"realise": round(total, 2), "latent": round(latent, 2), "trades": len(ordres),
                  "gagnants": sum(1 for o in ordres if o["resultat"] > 0), "blocage": blocage}

    cache = d.setdefault("_cache_marches", {})
    for epic, n in MARCHES.items():
        etat = marches.setdefault(epic, {"nom": NOMS[epic], "n": n})
        try:
            bougies = bougies_terminees(api.bougies(epic, UNITE, 400), quand)
            if len(bougies) < 260:
                etat["action"] = "Pas assez d'historique"
                continue
            s = signaux(bougies_vers_df(bougies), n)
            etat.update({"sens": s["sens"], "prix": round(s["prix"], 5), "atr": round(s["atr"], 5),
                         "sma200": s["sma200"], "bougie": s["bougie"],
                         "regle": f"Élan {n} bougies de 4 h dans le sens de la moyenne 200, stop garanti {STOP_ATR:g} ATR"})
            miennes = [(k, i) for k, i in deals.items() if i["epic"] == epic]
            # sortie : le sens s'est inversé (ou a disparu)
            for k, i in miennes:
                if s["sens"] != i["sens"]:
                    p = par_id[k]
                    conf = api.fermer(k)
                    if conf.get("dealStatus") == "ACCEPTED":
                        res = float(p["position"].get("upl") or 0)
                        ordres.append({**i, "id": k, "statut": "ferme", "ferme_le": q, "resultat": res,
                                       "motif_sortie": "L'élan s'est inversé"})
                        del deals[k]
                        noter("fermeture", epic, f"Élan inversé : position fermée (≈ {res:.2f} €).")
                    else:
                        noter("erreur", epic, f"Fermeture refusée : {conf.get('reason', conf.get('dealStatus'))}")
            if any(i["epic"] == epic for i in deals.values()):
                etat["action"] = "Position en cours"
                continue
            if not s["entree"]:
                etat["action"] = "En attente d'un signal"
                continue
            if d.setdefault("signaux_utilises", {}).get(epic) == s["bougie"]:
                etat["action"] = "Signal déjà utilisé"
                continue
            d["signaux_utilises"][epic] = s["bougie"]
            if blocage:
                etat["action"] = f"Signal ignoré : {blocage}"
                noter("analyse", epic, f"Signal {'ACHAT' if s['sens'] > 0 else 'VENTE'} ignoré : {blocage}.")
                continue
            etat["action"] = entrer(api, d, epic, s, positions, capital, disponible, eurusd, cache, noter, q)
        except Exception as e:  # un marché en erreur ne bloque pas les autres
            etat["action"] = "Erreur"
            noter("erreur", epic, str(e)[:300])
    return d


def entrer(api, d, epic, s, positions, capital, disponible, eurusd, cache, noter, q) -> str:
    regles = regles_marche(api, epic, cache)
    v = s["sens"]
    direction = "BUY" if v > 0 else "SELL"
    mot = "ACHAT" if v > 0 else "VENTE"
    snap = api.marche(epic).get("snapshot", {})
    prix = float(snap.get("offer" if v > 0 else "bid") or s["prix"])
    mini = prix * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
    distance = max(STOP_ATR * s["atr"], mini * 1.05)
    if regles["statut"] != "TRADEABLE":
        return "Marché fermé"
    if any(p["market"]["epic"] == epic for p in positions):
        noter("analyse", epic, "Signal ignoré : une autre position est déjà ouverte sur ce marché.")
        return "Autre position sur ce marché"
    if abs(prix - s["prix"]) > s["atr"]:
        noter("analyse", epic, "Signal ignoré : le prix a trop bougé depuis la fin de la bougie.")
        return "Prix trop loin du signal"
    if float(snap.get("offer", prix)) - float(snap.get("bid", prix)) > distance * 0.10:
        noter("analyse", epic, "Signal ignoré : spread trop cher par rapport au stop.")
        return "Spread trop cher"
    taux = taux_devise(regles, eurusd, prix)
    pas = regles["pas"]
    taille = math.floor(capital * RISQUE_PCT / 100 * taux / distance / pas) * pas
    taille_marge = math.floor(disponible * taux / (prix * regles["marge"]) * 0.5 / pas) * pas
    taille = round(min(taille, taille_marge), 6)
    if taille < regles["taille_min"]:
        mini_eur = regles["taille_min"] * distance / taux
        if mini_eur <= capital * 1.5 * RISQUE_PCT / 100 and regles["taille_min"] <= taille_marge:
            taille = regles["taille_min"]
        else:
            noter("analyse", epic, f"Signal {mot} ignoré : capital trop faible pour la taille minimale "
                  f"({regles['taille_min']}, risque {mini_eur:.2f} €).")
            return "Capital trop faible"
    conf = api.ouvrir(epic, direction, taille, prix=prix, stop_distance=distance, garanti=True)
    if conf.get("dealStatus") != "ACCEPTED":
        noter("erreur", epic, f"Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
        return "Refusé par Capital.com"
    deals = conf.get("affectedDeals") or []
    deal = (deals[0].get("dealId") if deals else None) or conf.get("dealId") or conf.get("dealReference")
    niveau = float(conf.get("level") or prix)
    d["deals"][deal] = {"epic": epic, "nom": NOMS[epic], "sens": v, "direction": direction, "taille": taille,
                        "prix_entree": niveau, "stop": niveau - distance * v, "ouvert_le": q,
                        "risque_eur": round(taille * distance / taux, 2), "resultat": 0.0}
    noter("ordre", epic, f"{mot} de {taille} à {niveau:.5g}, stop garanti à {distance:.5g} "
          f"(risque max ≈ {taille * distance / taux:.2f} €).")
    return f"{mot} de {taille}"


def principal():
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    d = charger()
    api = CapitalDemo(cle, ident, mdp)
    try:
        un_tour(d, api)
    finally:
        sauver(d)
        api.deconnexion()


if __name__ == "__main__":
    principal()

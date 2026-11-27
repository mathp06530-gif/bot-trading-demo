"""TEST EN DIRECT (aucun ordre) des 2 pistes qui ont tenu sur des années jamais vues (27/11/2026) :

 1. « 4 h, vote simple, seulement ses 5 % les plus sûrs » : à chaque bougie 4 h terminée, sur les 8 marchés à
    petits frais, les 14 cerveaux du labo (3 IA apprises chaque mois sur le passé + 11 règles) votent sur le sens de
    la bougie 4 h suivante. On ne « parie » que si la confiance du vote est dans ses 5 % les plus hautes des 3000
    bougies précédentes (seuil pris sur le passé seulement). Réglages EXACTEMENT ceux du labo, fixés à l'avance.
    Historique : 2021-2024 54,9 % +0,023 %/trade après spread (6/8 marchés) ; 2024-2026 56,2 % +0,013 % (7/8).
 2. « Fin de séance à l'envers » sur US100 / US500 : sur les bougies 15 min qui commencent à 21 h 30 et 21 h 45
    (heure de Paris), parier CONTRE le rendement depuis l'ouverture de 15 h 30 ; jugé sur la bougie suivante.
    Historique : 54,0 % (US100) et 56,1 % (US500) sur la période jamais vue, ~0 après spread.

Chaque prédiction est écrite AVANT de connaître le résultat, jugée ensuite au vrai spread, jamais réécrite.
Publication : branche « ia-pistes », fichier pistes.json (lu par la page IA).

Usage : python -m ia.pistes_direct            (GitHub Actions, secrets Capital.com démo)
        python -m ia.pistes_direct local <dossier_csv>   (essai hors ligne, sans publier)
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

os.environ["LABO_H"] = "1"
os.environ.setdefault("LABO_PISTES", "oui")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ia.multi_labo as L  # noqa: E402

MARCHES = L.MARCHES
DEPUIS = pd.Timestamp(os.getenv("PISTES_DEPUIS", "2026-11-27T21:00:00"))  # UTC : seules les décisions après comptent
MOIS_CERVEAUX = 27          # mois de walk-forward recalculés à chaque passage (>= 3000 bougies 4 h de passé pour le seuil)
FEN, PART = L.FEN_SEUIL, 0.05
FIN_SEANCE = {"US100": (15.5, 22.0), "US500": (15.5, 22.0)}
DOSSIER_PUB = Path(os.getenv("PISTES_DOSSIER", "pistes_pub"))
DONNEES = Path(os.getenv("PISTES_DONNEES", "donnees_pistes"))
REFERENCES = {
    "quatre_h": [
        {"periode": "2021-2024 (36 mois jamais vus)", "reussite": 0.549, "gain": 0.0227, "n": 1733, "marches": "6/8", "melanges": 0.508},
        {"periode": "2024-2026 (24 mois jamais vus)", "reussite": 0.562, "gain": 0.013, "n": None, "marches": "7/8", "melanges": None}],
    "fin_seance": [
        {"periode": "avant les 12 derniers mois (jamais vue)", "US100": 0.540, "US500": 0.561, "gain": "~0"},
        {"periode": "12 derniers mois", "US100": 0.553, "US500": 0.579, "gain": "~+0,015 %"}],
}


# --------------------------------------------------------------------------- données Capital.com
def api_connectee():
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    return api


def _ligne(b):
    return [b["snapshotTimeUTC"], b["openPrice"].get("bid"), b["openPrice"].get("ask"), b["highPrice"].get("bid"),
            b["highPrice"].get("ask"), b["lowPrice"].get("bid"), b["lowPrice"].get("ask"), b["closePrice"].get("bid"),
            b["closePrice"].get("ask"), b.get("lastTradedVolume", 0)]


COLONNES = ["date", "open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask", "close_bid", "close_ask", "volume"]


def telecharger(api, epic, unite, minutes, jours):
    """Bougies [maintenant - jours, maintenant], par paquets de 900 ; garde l'existant du cache (fusion)."""
    fin = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    debut = fin - timedelta(days=jours)
    lignes, a, vides = {}, fin, 0
    while a > debut and vides < 3:
        de = max(a - timedelta(minutes=minutes * 900), debut)
        try:
            prix = api._requete("GET", f"/prices/{epic}", params={"resolution": unite, "max": 1000,
                                "from": de.strftime("%Y-%m-%dT%H:%M:%S"), "to": a.strftime("%Y-%m-%dT%H:%M:%S")}).get("prices", [])
        except Exception as e:
            print(epic, unite, de, e)
            prix = []
        vides = vides + 1 if not prix else 0
        for b in prix:
            lignes[b["snapshotTimeUTC"]] = _ligne(b)
        a = de
        time.sleep(0.25)
    neuf = pd.DataFrame(list(lignes.values()), columns=COLONNES)
    fichier = DONNEES / f"{epic}_{unite}.csv"
    if fichier.exists():
        neuf = pd.concat([pd.read_csv(fichier), neuf]).drop_duplicates("date", keep="last")
    neuf.sort_values("date").to_csv(fichier, index=False)
    print(f"{epic} {unite} : {len(neuf)} bougies (dont {len(lignes)} relues)")


def completes(d, minutes, maintenant):
    """Retire la bougie en cours (pas encore terminée)."""
    return d[d.index + pd.Timedelta(minutes=minutes) <= maintenant]


# --------------------------------------------------------------------------- piste 1 : 4 h, vote, 5 % plus sûres
def votes_4h(epic, maintenant):
    """Vote des 14 cerveaux sur chaque bougie 4 h terminée des MOIS_CERVEAUX derniers mois (walk-forward, passé seul),
    et décision « parie / s'abstient » avec le seuil des 5 % plus sûres des 3000 bougies précédentes."""
    from ia.predire import lire
    d = lire(DONNEES, epic, "HOUR_4")
    if d is None or len(d) < 4000:
        print(epic, ": pas assez de bougies 4 h")
        return None, None
    d = completes(d, 240, maintenant)
    # bougie fictive après la dernière bougie terminée : elle ne sert QU'À garder la dernière ligne (dont la cible
    # est encore inconnue) ; aucun indicateur ne regarde vers le futur, et cette ligne n'entre jamais dans l'apprentissage.
    fausse = d.iloc[[-1]].copy()
    fausse.index = fausse.index + pd.Timedelta(minutes=240)
    fausse[[c for c in d.columns if c != "volume"]] *= 1 + 1e-7
    dd = pd.concat([d, fausse])
    L.PURGE = pd.Timedelta(hours=10)
    croix = L.croises(DONNEES, epic, "HOUR_4", dd.index)
    f = L.preparer(dd, 240, croix=croix, epic=epic)
    debut = (f.index.max() - pd.DateOffset(months=MOIS_CERVEAUX)).normalize().replace(day=1)
    bornes = [debut] + [b for b in pd.date_range(debut, f.index.max() + pd.Timedelta(days=31), freq="MS") if b > debut]
    P = L.cerveaux(f, list(zip(bornes[:-1], bornes[1:])))
    v = P.mean(axis=1)
    v = v[(v.index >= debut) & P[L.APPRIS].notna().all(axis=1)]
    c = (v - 0.5).abs().to_numpy()
    seuils = np.array([np.quantile(c[max(0, i - FEN):i], 1 - PART) if i >= 500 else np.nan for i in range(len(c))])
    mid = (d.close_bid + d.close_ask) / 2
    sp = ((d.close_ask - d.close_bid) / mid * 100).clip(lower=0)
    out = pd.DataFrame({"q": v.to_numpy(), "seuil": seuils, "conf": c}, index=v.index)
    out["mid"], out["sp"] = mid.reindex(out.index), sp.reindex(out.index)
    return out, d


def juger_4h(p, d):
    t = pd.Timestamp(p["t"])
    apres = d.index[d.index > t]
    if not len(apres):
        return
    t2 = apres[0]
    if (t2 - t) > pd.Timedelta(minutes=480):  # marché fermé entre les deux (week-end) : le labo ne comptait pas ces cas
        p["statut"] = "non compté (marché fermé)"
        return
    m2 = float((d.close_bid[t2] + d.close_ask[t2]) / 2)
    mv = (m2 / p["mid"] - 1) * 100
    sens = 1 if p["q"] > 0.5 else -1
    p.update({"statut": "jugé", "t_fin": str(t2 + pd.Timedelta(minutes=240)), "mv": round(mv, 5),
              "juste": bool(sens * mv > 0), "gain": round(sens * mv - p["sp"], 5)})


# --------------------------------------------------------------------------- piste 2 : fin de séance à l'envers
def fin_seance(epic, d15, deja):
    """Toutes les bougies de 21 h 30 et 21 h 45 (Paris) depuis DEPUIS : sens = contre le rendement depuis 15 h 30."""
    o, c = FIN_SEANCE[epic]
    mid = (d15.close_bid + d15.close_ask) / 2
    sp = ((d15.close_ask - d15.close_bid) / mid * 100).clip(lower=0)
    loc = d15.index.tz_localize("UTC").tz_convert("Europe/Paris")
    h = np.asarray(loc.hour + loc.minute / 60, float)
    jour = np.array([str(x) for x in loc.date])
    neuves = []
    for i in range(len(d15) - 1):
        t = d15.index[i]
        if t < DEPUIS or not (c - 0.5 <= h[i] < c) or (epic, str(t)) in deja:
            continue
        j = np.where((jour == jour[i]) & (np.abs(h - o) < 1e-6))[0]
        if not len(j):
            continue
        depuis = float(np.log(mid.iloc[i]) - np.log(mid.iloc[j[0]]))
        t2 = d15.index[i + 1]
        if depuis == 0 or (t2 - t) > pd.Timedelta(minutes=30):
            continue
        sens = -1 if depuis > 0 else 1
        mv = float((mid.iloc[i + 1] / mid.iloc[i] - 1) * 100)
        neuves.append({"e": epic, "t": str(t), "heure_paris": f"{loc[i].hour:02d}:{loc[i].minute:02d}", "jour": jour[i],
                       "depuis_ouverture_pct": round(100 * depuis, 4), "sens": "hausse" if sens > 0 else "baisse",
                       "mv": round(mv, 5), "sp": round(float(sp.iloc[i]), 5), "juste": bool(sens * mv > 0),
                       "gain": round(sens * mv - float(sp.iloc[i]), 5)})
    return neuves


# --------------------------------------------------------------------------- bilan
def resume(liste):
    if not liste:
        return None
    g = np.array([x["gain"] for x in liste])
    return {"n": len(liste), "reussite": round(float(np.mean([x["juste"] for x in liste])), 4),
            "gain": round(float(g.mean()), 5), "gain_total": round(float(g.sum()), 4)}


def bilan(etat):
    jug = [p for p in etat["quatre_h"] if p.get("statut") == "jugé"]
    sur = [p for p in jug if p["parie"]]
    q = {"top5": resume(sur), "toujours": resume(jug),
         "par_marche": {e: resume([p for p in sur if p["e"] == e]) for e in MARCHES},
         "par_marche_toujours": {e: resume([p for p in jug if p["e"] == e]) for e in MARCHES}}
    fs = etat["fin_seance"]
    return {"quatre_h": q, "fin_seance": {"tous": resume(fs), **{e: resume([x for x in fs if x["e"] == e]) for e in FIN_SEANCE}}}


# --------------------------------------------------------------------------- publication (branche ia-pistes)
def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd or DOSSIER_PUB, capture_output=True, text=True, timeout=120)


def charger_etat():
    vide = {"quatre_h": [], "fin_seance": []}
    if os.getenv("PISTES_GIT", "oui") != "oui":
        f = DOSSIER_PUB / "pistes.json"
        return json.loads(f.read_text()) if f.exists() else vide
    url = git("config", "--get", "remote.origin.url", cwd=".").stdout.strip()
    auth = git("config", "--get-regexp", r"http\..*\.extraheader", cwd=".").stdout
    DOSSIER_PUB.mkdir(parents=True, exist_ok=True)
    git("init", "-q")
    for ligne in auth.splitlines():
        k, v = ligne.split(" ", 1)
        git("config", k, v)
    git("remote", "add", "origin", url)
    git("config", "user.name", "bot-trading-demo")
    git("config", "user.email", "bot-trading-demo@users.noreply.github.com")
    if git("fetch", "-q", "origin", "ia-pistes").returncode == 0:
        git("checkout", "-q", "-f", "-B", "ia-pistes", "FETCH_HEAD")
        f = DOSSIER_PUB / "pistes.json"
        if f.exists():
            e = json.loads(f.read_text())
            return {"quatre_h": e.get("quatre_h", []), "fin_seance": e.get("fin_seance", [])}
    else:
        git("checkout", "-q", "--orphan", "ia-pistes")
    return vide


def publier(sortie):
    DOSSIER_PUB.mkdir(parents=True, exist_ok=True)
    (DOSSIER_PUB / "pistes.json").write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")))
    if os.getenv("PISTES_GIT", "oui") != "oui":
        return
    git("add", "-A")
    git("commit", "-qm", "Pistes en direct " + sortie["maj"])
    for _ in range(3):
        r = git("push", "-q", "origin", "HEAD:ia-pistes")
        if r.returncode == 0:
            return
        print("push", r.stderr[:300])
        time.sleep(5)


# --------------------------------------------------------------------------- principal
def principal():
    local = len(sys.argv) > 2 and sys.argv[1] == "local"
    global DONNEES
    if local:
        DONNEES = Path(sys.argv[2])
        os.environ["PISTES_GIT"] = "non"
    maintenant = pd.Timestamp(os.getenv("PISTES_MAINTENANT") or datetime.now(timezone.utc).replace(tzinfo=None))
    etat = charger_etat()
    deja4 = {(p["e"], p["t"]) for p in etat["quatre_h"]}
    dejaf = {(p["e"], p["t"]) for p in etat["fin_seance"]}
    api = None
    if not local:
        DONNEES.mkdir(parents=True, exist_ok=True)
        api = api_connectee()
        for e in MARCHES:  # 4 h : tout l'historique si pas en cache, sinon les 60 derniers jours (fusion)
            jours = 60 if (DONNEES / f"{e}_HOUR_4.csv").exists() else 3650
            try:
                telecharger(api, e, "HOUR_4", 240, jours)
            except Exception as x:
                print(e, "échec", x)
        for e in FIN_SEANCE:
            try:
                telecharger(api, e, "MINUTE_15", 15, 5)
            except Exception as x:
                print(e, "15 min échec", x)
        api.deconnexion()
    from ia.predire import lire
    if os.getenv("PISTES_FORCER") != "oui":  # rien de neuf (aucune bougie 4 h terminée, aucune fin de séance) : on s'arrête
        neuf = False
        for e in MARCHES:
            d = lire(DONNEES, e, "HOUR_4")
            if d is not None and len(d):
                t = completes(d, 240, maintenant).index.max()
                neuf |= (e, str(t)) not in deja4 and t + pd.Timedelta(minutes=240) >= DEPUIS
        for e in FIN_SEANCE:
            d15 = lire(DONNEES, e, "MINUTE_15")
            neuf |= d15 is not None and bool(fin_seance(e, completes(d15, 15, maintenant), dejaf))
        if not neuf and etat["quatre_h"]:
            print("Rien de neuf depuis le dernier passage.")
            return
    en_cours = []
    for e in MARCHES:
        try:
            v, d = votes_4h(e, maintenant)
        except Exception as x:
            print(e, "votes échec", x)
            continue
        if v is None:
            continue
        for p in etat["quatre_h"]:  # on juge d'abord ce qui attendait
            if p["e"] == e and p.get("statut") == "en attente":
                juger_4h(p, d)
        for t, r in v.iterrows():
            decide = t + pd.Timedelta(minutes=240)  # décision prise à la clôture de la bougie t
            if decide < DEPUIS or (e, str(t)) in deja4 or not r.seuil == r.seuil:
                continue
            p = {"e": e, "t": str(t), "decide_a": str(decide), "q": round(float(r.q), 5), "conf": round(float(r.conf), 5),
                 "seuil": round(float(r.seuil), 5), "parie": bool(r.conf >= r.seuil), "mid": float(r.mid),
                 "sp": round(float(r.sp), 5), "statut": "en attente", "ecrit_a": str(maintenant)}
            juger_4h(p, d)
            etat["quatre_h"].append(p)
            deja4.add((e, str(t)))
        der = v.iloc[-1]
        en_cours.append({"e": e, "t": str(v.index[-1]), "fin": (v.index[-1] + pd.Timedelta(minutes=480)).isoformat(),
                         "q": round(float(der.q), 4), "parie": bool(der.conf >= der.seuil),
                         "conf": round(float(der.conf), 4), "seuil": round(float(der.seuil), 4)})
        print(f"{e} : vote {der.q:.3f} conf {der.conf:.4f} seuil {der.seuil:.4f} -> {'PARIE' if der.conf >= der.seuil else 'abstention'}")
    for e in FIN_SEANCE:
        d15 = lire(DONNEES, e, "MINUTE_15")
        if d15 is None:
            continue
        neuves = fin_seance(e, completes(d15, 15, maintenant), dejaf)
        etat["fin_seance"].extend(neuves)
        print(e, "fin de séance :", len(neuves), "nouvelles")
    sortie = {"maj": maintenant.isoformat() + "Z", "depuis": DEPUIS.isoformat() + "Z", "en_cours": en_cours,
              "stats": bilan(etat), "references": REFERENCES,
              "quatre_h": etat["quatre_h"][-4000:], "fin_seance": etat["fin_seance"][-2000:]}
    print(json.dumps(sortie["stats"], ensure_ascii=False)[:1200])
    publier(sortie)


if __name__ == "__main__":
    principal()

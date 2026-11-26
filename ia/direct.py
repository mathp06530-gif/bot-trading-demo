"""Journal EN DIRECT des IA (système à part du bot, AUCUN ordre passé).

Chaque heure, GitHub Actions lance ce script pour ~55 minutes :
  1. il réentraîne les IA de ia/predire.py sur les ~20 derniers jours de bougies 1 min de chaque marché ;
  2. chaque minute, chaque IA prédit si le prix sera plus haut ou plus bas :
       - à la fin de la minute en cours (« 1 min ») ;
       - 40 secondes plus tard (« 40 s », jugé avec le prix affiché par Capital.com) ;
  3. il note le résultat réel, le taux de réussite par IA et par marché, et ce qu'aurait donné un trade
     (spread payé) ; tout est écrit dans docs/ia/journal.json, affiché par docs/ia.html.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ia import predire  # noqa: E402

MARCHES = [e.strip() for e in os.getenv("IA_MARCHES", "GOLD,US100,BTCUSD,EURUSD").split(",") if e.strip()]
DUREE = int(os.getenv("IA_DUREE_S", str(54 * 60)))
JOURNAL = Path(__file__).resolve().parent.parent / "docs" / "ia" / "journal.json"
GARDER = 400  # dernières prédictions affichées


def maintenant():
    return datetime.now(timezone.utc)


def vers_df(bougies):
    lignes = [[b["snapshotTimeUTC"]] + [b[f"{k}Price"][c] for k in ("open", "high", "low", "close") for c in ("bid", "ask")]
              + [b.get("lastTradedVolume", 0)] for b in bougies]
    d = pd.DataFrame(lignes, columns=["date", "open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask",
                                      "close_bid", "close_ask", "volume"])
    d["date"] = pd.to_datetime(d.date, utc=True).dt.tz_localize(None)
    return d.set_index("date").sort_index().astype(float)


def prix_affiche(api, epic):
    s = api.marche(epic).get("snapshot", {})
    if s.get("marketStatus") != "TRADEABLE" or s.get("bid") is None:
        return None
    return (float(s["bid"]) + float(s["offer"])) / 2, float(s["offer"]) - float(s["bid"])


def charger_journal():
    try:
        j = json.loads(JOURNAL.read_text())
    except Exception:
        j = {}
    j.setdefault("stats", {})
    j.setdefault("dernieres", [])
    return j


def compter(j, epic, modele, horizon, juste, gain):
    for cle in (modele, f"{modele}|{epic}"):
        s = j["stats"].setdefault(cle, {}).setdefault(horizon, {"n": 0, "justes": 0, "gain_pct": 0.0})
        s["n"] += 1
        s["justes"] += int(juste)
        s["gain_pct"] = round(s["gain_pct"] + gain * 100, 5)


def enregistrer(j, message):
    j["maj"] = maintenant().strftime("%Y-%m-%dT%H:%M:%SZ")
    j["dernieres"] = j["dernieres"][-GARDER:]
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    JOURNAL.write_text(json.dumps(j, ensure_ascii=False, separators=(",", ":")))
    if os.getenv("IA_GIT", "oui") != "oui":
        return
    br = os.getenv("GITHUB_REF_NAME", "main")
    cmd = (f'git add docs/ia/journal.json && (git diff --cached --quiet || git commit -qm "{message}") && '
           f'for i in 1 2 3 4 5; do git pull -q --rebase origin {br} && git push -q origin HEAD:{br} && exit 0; sleep 3; done')
    subprocess.run(["bash", "-c", cmd], check=False)


def principal():
    from backtest import telecharger as t
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    debut = time.time()
    tmp = Path("donnees_direct")
    tmp.mkdir(exist_ok=True)
    t.DOSSIER = tmp
    ia = {}
    for epic in MARCHES:  # 1. entraînement sur les 20 derniers jours
        try:
            t.telecharger(api, epic, "MINUTE", 1, 20)
            d = predire.lire(tmp, epic, "MINUTE")
            F, S = predire.indicateurs(d), predire.sequences(d)
            mid = ((d.close_bid + d.close_ask) / 2).values
            fut = np.r_[mid[1:] - mid[:-1], np.nan]
            y = np.where(fut > 0, 1.0, np.where(fut < 0, 0.0, np.nan))
            ok = F.notna().all(axis=1).values & ~np.isnan(y) & (np.arange(len(d)) >= predire.SEQ + 200)
            ii = np.where(ok)[0][-predire.TRAIN_MAX:]
            Xs = np.stack([S[i - predire.SEQ + 1:i + 1] for i in ii])
            ia[epic] = predire.entrainer(F.values[ii], Xs, y[ii])
            print(f"{epic} : {len(ii)} bougies d'entraînement, IA : {', '.join(ia[epic])}", flush=True)
        except Exception as e:
            print(f"{epic} : entraînement impossible ({str(e)[:200]})", flush=True)
    j = charger_journal()
    j["marches"], j["modeles"] = MARCHES, predire.MODELES[:6]
    attente = []  # prédictions à juger
    derniere_session, dernier_commit = time.time(), time.time()
    while time.time() - debut < DUREE:
        # attendre la 2e seconde de la minute suivante
        time.sleep(max(0.0, 62 - maintenant().second - maintenant().microsecond / 1e6) % 60)
        if time.time() - derniere_session > 8 * 60:  # la session Capital.com expire après 10 min
            try:
                api.deconnexion()
            except Exception:
                pass
            api.connexion()
            derniere_session = time.time()
        heure = maintenant()
        # juger les prédictions dont l'échéance est passée
        reste = []
        for p in attente:
            try:
                if p["horizon"] == "1 min" and heure.timestamp() >= p["echeance"]:
                    d = vers_df(api.bougies(p["epic"], "MINUTE", 3))
                    if pd.Timestamp(p["bougie"]) not in d.index:
                        continue
                    b = d.loc[pd.Timestamp(p["bougie"])]
                    fin = (b.close_bid + b.close_ask) / 2
                elif p["horizon"] == "40 s" and heure.timestamp() >= p["echeance"] - 1:
                    pa = prix_affiche(api, p["epic"])
                    if pa is None:
                        continue
                    fin = pa[0]
                else:
                    reste.append(p)
                    continue
            except Exception as e:
                print(f"jugement impossible : {str(e)[:120]}")
                continue
            if fin == p["depart"]:
                p["resultat"] = "inchangé"
                j["dernieres"].append(p)
                continue
            hausse = fin > p["depart"]
            for m, sens in p["sens"].items():
                gain = (fin - p["depart"]) / p["depart"] * (1 if sens == "hausse" else -1) - p["spread"] / p["depart"]
                compter(j, p["epic"], m, p["horizon"], (sens == "hausse") == hausse, gain)
            p["resultat"] = "hausse" if hausse else "baisse"
            p["fin"] = fin
            j["dernieres"].append(p)
        attente = reste
        # nouvelles prédictions
        for epic, fonctions in ia.items():
            try:
                d = vers_df(api.bougies(epic, "MINUTE", 400))
                if len(d) < 300:
                    continue
                d_fini = d.iloc[:-1]  # la dernière bougie est celle qui se forme
                if (heure.replace(tzinfo=None) - d_fini.index[-1]).total_seconds() > 150:
                    continue  # marché fermé
                F, S = predire.indicateurs(d_fini), predire.sequences(d_fini)
                x = F.values[-1:]
                if np.isnan(x).any():
                    continue
                xs = S[-predire.SEQ:][None]
                probas = {m: float(f(x, xs)[0]) for m, f in fonctions.items()}
                probas["vote"] = float(np.mean(list(probas.values())))
                sens = {m: "hausse" if p > 0.5 else "baisse" for m, p in probas.items()}
                b = d_fini.iloc[-1]
                depart = (b.close_bid + b.close_ask) / 2
                attente.append({"epic": epic, "horizon": "1 min", "heure": heure.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "bougie": str(d.index[-1]), "echeance": (d.index[-1] + pd.Timedelta(minutes=1))
                                .tz_localize("UTC").timestamp() + 2, "depart": depart,
                                "spread": float(b.close_ask - b.close_bid), "sens": sens,
                                "probas": {m: round(p, 3) for m, p in probas.items()}})
                pa = prix_affiche(api, epic)
                if pa:
                    attente.append({"epic": epic, "horizon": "40 s", "heure": heure.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "echeance": time.time() + 40, "depart": pa[0], "spread": pa[1], "sens": sens,
                                    "probas": {m: round(p, 3) for m, p in probas.items()}})
            except Exception as e:
                print(f"{epic} : prédiction impossible ({str(e)[:150]})", flush=True)
        # le jugement à 40 s tombe pendant la minute : petite boucle d'attente
        while any(p["horizon"] == "40 s" for p in attente) and time.time() < min(p["echeance"] for p in attente if p["horizon"] == "40 s") + 1:
            time.sleep(0.5)
        for p in [p for p in attente if p["horizon"] == "40 s"]:
            try:
                pa = prix_affiche(api, p["epic"])
            except Exception:
                pa = None
            attente.remove(p)
            if pa is None or pa[0] == p["depart"]:
                continue
            hausse = pa[0] > p["depart"]
            for m, sens in p["sens"].items():
                gain = (pa[0] - p["depart"]) / p["depart"] * (1 if sens == "hausse" else -1) - p["spread"] / p["depart"]
                compter(j, p["epic"], m, "40 s", (sens == "hausse") == hausse, gain)
            p["resultat"], p["fin"] = ("hausse" if hausse else "baisse"), pa[0]
            j["dernieres"].append(p)
        if time.time() - dernier_commit > 5 * 60:
            enregistrer(j, "IA en direct : journal des prédictions")
            dernier_commit = time.time()
    enregistrer(j, "IA en direct : journal des prédictions")
    api.deconnexion()


if __name__ == "__main__":
    principal()

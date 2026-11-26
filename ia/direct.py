"""Journal EN DIRECT de toutes les IA sur tous les marchés Capital.com (système à part du bot, AUCUN ordre).

Chaque heure, GitHub Actions lance ce script pour ~50 minutes :
  1. liste tous les marchés Capital.com (une fois par jour) et repère ceux qui sont ouverts ;
  2. entraîne les IA « maison » (ia/predire.py) sur des bougies 1 min de ~30 grands marchés mélangés ;
  3. démarre les IA géantes (ia/geantes : Chronos, TimesFM, Kronos, Sundial…), chacune dans son processus ;
  4. chaque minute, prend le lot suivant de marchés ouverts (rotation), et TOUTES les IA reçoivent les mêmes
     512 dernières bougies 1 min et rendent la probabilité que le prix soit plus haut 60 s plus tard ;
  5. 60 s après, le vrai prix est relevé : réussite par IA, par marché, par famille de marchés, et ce qu'aurait
     donné un trade (spread payé). Un « arbitre » pondère le vote par les résultats réels.
Tout est publié sur la branche « ia-journal » (fichier journal.json), lu par la page docs/ia.html.
"""
import json
import math
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ia import predire  # noqa: E402
from ia.geantes.familles import EXCLUES, FAMILLES, MAISON, NOMS  # noqa: E402

DUREE = int(os.getenv("IA_DUREE_S", str(50 * 60)))
LOT = int(os.getenv("IA_LOT", "24"))  # marchés prédits par minute (rotation sur tous les marchés ouverts)
L = 512  # bougies données à chaque IA
DOSSIER = Path(os.getenv("IA_JOURNAL_DIR", "journal_ia"))  # copie locale de la branche ia-journal
BRANCHE = "ia-journal"
GRANDS = ["GOLD", "SILVER", "OIL_CRUDE", "NATURALGAS", "COPPER", "US500", "US100", "US30", "DE40", "UK100", "FR40",
          "J225", "HK50", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "EURJPY", "BTCUSD", "ETHUSD", "SOLUSD",
          "XRPUSD", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"]


def maintenant():
    return datetime.now(timezone.utc)


def iso(t=None):
    return (t or maintenant()).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- publication (branche sans historique)
def git(*args, check=False):
    return subprocess.run(["git", *args], cwd=DOSSIER, capture_output=True, text=True, check=check)


def preparer_branche():
    depot = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True).stdout.strip()
    if not (DOSSIER / ".git").exists():
        DOSSIER.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(DOSSIER)])
        # l'en-tête d'authentification de actions/checkout est recopié pour pouvoir pousser
        auth = subprocess.run(["git", "config", "--get-regexp", r"http\..*\.extraheader"], capture_output=True, text=True).stdout
        for ligne in auth.splitlines():
            k, v = ligne.split(" ", 1)
            git("config", k, v)
        git("remote", "add", "origin", depot)
        git("config", "user.name", "bot-trading-demo")
        git("config", "user.email", "bot-trading-demo@users.noreply.github.com")
    if git("fetch", "-q", "--depth", "1", "origin", BRANCHE).returncode == 0:
        git("checkout", "-q", "-f", "-B", BRANCHE, "FETCH_HEAD")


def lire_json(nom, defaut):
    try:
        return json.loads((DOSSIER / nom).read_text())
    except Exception:
        return defaut


def publier(fichiers: dict):
    for nom, contenu in fichiers.items():
        (DOSSIER / nom).write_text(json.dumps(contenu, ensure_ascii=False, separators=(",", ":")))
    if os.getenv("IA_GIT", "oui") != "oui":
        return
    git("checkout", "-q", "--orphan", "tmp")  # un seul commit, pas d'historique : le dépôt ne grossit pas
    git("add", "-A")
    git("commit", "-qm", f"Journal des IA {iso()}")
    git("branch", "-q", "-D", BRANCHE)
    git("branch", "-q", "-m", BRANCHE)
    r = git("push", "-q", "-f", "origin", BRANCHE)
    if r.returncode:
        print("publication impossible :", r.stderr[:300], flush=True)


# --------------------------------------------------------------------------- marchés
def lister_marches(api):
    """Tous les marchés de Capital.com, en parcourant l'arbre de navigation (une fois par jour)."""
    vus, marches, a_voir = set(), {}, [n["id"] for n in api._requete("GET", "/marketnavigation").get("nodes", [])]
    while a_voir and len(vus) < 3000:
        nid = a_voir.pop()
        if nid in vus:
            continue
        vus.add(nid)
        try:
            r = api._requete("GET", f"/marketnavigation/{nid}", params={"limit": 500})
        except Exception as e:
            print(f"navigation {nid} : {str(e)[:100]}")
            time.sleep(1)
            continue
        a_voir += [n["id"] for n in r.get("nodes", [])]
        for m in r.get("markets", []):
            if m.get("epic"):
                marches[m["epic"]] = {"nom": m.get("instrumentName", m["epic"]), "type": m.get("instrumentType", "?")}
        time.sleep(0.12)
    return marches


def instantanes(api, epics):
    """Prix affichés (milieu, spread, ouvert ?) de nombreux marchés, 50 par appel."""
    out = {}
    for i in range(0, len(epics), 50):
        try:
            r = api._requete("GET", "/markets", params={"epics": ",".join(epics[i:i + 50])})
        except Exception as e:
            print(f"instantanés : {str(e)[:120]}")
            continue
        for m in r.get("marketDetails", r.get("markets", [])):
            ins, s = m.get("instrument", m), m.get("snapshot", m)
            epic = ins.get("epic") or m.get("epic")
            bid, ask = s.get("bid"), s.get("offer")
            if epic and bid is not None and ask is not None:
                out[epic] = {"mid": (float(bid) + float(ask)) / 2, "spread": float(ask) - float(bid),
                             "ouvert": s.get("marketStatus") == "TRADEABLE"}
    return out


def trier_ouverts(etat, tous):
    """Marchés ouverts, du spread le plus faible au plus fort : la rotation passe sur tous, les plus liquides d'abord."""
    o = [e for e in tous if etat.get(e, {}).get("ouvert") and etat[e]["mid"] > 0]
    return sorted(o, key=lambda e: etat[e]["spread"] / etat[e]["mid"])


def vers_df(bougies):
    lignes = [[b["snapshotTimeUTC"]] + [b[f"{k}Price"][c] for k in ("open", "high", "low", "close") for c in ("bid", "ask")]
              + [b.get("lastTradedVolume", 0)] for b in bougies]
    d = pd.DataFrame(lignes, columns=["date", "open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask",
                                      "close_bid", "close_ask", "volume"])
    d["date"] = pd.to_datetime(d.date, utc=True).dt.tz_localize(None)
    return d.set_index("date").sort_index().astype(float)


# --------------------------------------------------------------------------- IA maison (un seul jeu pour tous les marchés)
SERIES = []  # bougies 1 min des grands marchés, aussi données aux IA de recherche (N-BEATS, TFT…) pour s'entraîner


def entrainer_maison(api, ouverts):
    choix = [e for e in GRANDS if e in ouverts] or list(ouverts)[:30]
    X, Xs, Y = [], [], []
    for epic in choix[:30]:
        try:
            d = vers_df(api.bougies(epic, "MINUTE", 1000))
        except Exception:
            continue
        if len(d) < 600:
            continue
        F, S = predire.indicateurs(d), predire.sequences(d)
        mid = ((d.close_bid + d.close_ask) / 2).values
        fut = np.r_[mid[1:] - mid[:-1], np.nan]
        y = np.where(fut > 0, 1.0, np.where(fut < 0, 0.0, np.nan))
        ok = F.notna().all(axis=1).values & ~np.isnan(y) & (np.arange(len(d)) >= predire.SEQ + 200)
        ii = np.where(ok)[0]
        X.append(F.values[ii]); Xs.append(np.stack([S[i - predire.SEQ + 1:i + 1] for i in ii])); Y.append(y[ii])
        SERIES.append(mid)
        time.sleep(0.1)
    if not X:
        return {}
    X, Xs, Y = np.concatenate(X), np.concatenate(Xs), np.concatenate(Y)
    print(f"IA maison : {len(Y)} bougies d'entraînement sur {len(choix[:30])} marchés", flush=True)
    return predire.entrainer(X, Xs, Y)


# --------------------------------------------------------------------------- statistiques
def stats_vides(modeles):
    return {"modeles": modeles, "marches": [], "n": [], "justes": [], "gain": [], "jour": {}, "types": {}}


def index_marche(st, epic):
    if epic not in st["marches"]:
        st["marches"].append(epic)
        for k in ("n", "justes", "gain"):
            st[k].append([0] * len(st["modeles"]) if k != "gain" else [0.0] * len(st["modeles"]))
    return st["marches"].index(epic)


def index_modele(st, m):
    if m not in st["modeles"]:
        st["modeles"].append(m)
        for k in ("n", "justes", "gain"):
            for ligne in st[k]:
                ligne.append(0 if k != "gain" else 0.0)
    return st["modeles"].index(m)


def compter(st, epic, typ, jour, m, juste, gain):
    i, j = index_marche(st, epic), index_modele(st, m)
    st["n"][i][j] += 1
    st["justes"][i][j] += int(juste)
    st["gain"][i][j] = round(st["gain"][i][j] + gain, 6)
    for cle, groupe in ((jour, "jour"), (typ, "types")):
        d = st[groupe].setdefault(cle, {}).setdefault(m, [0, 0])
        d[0] += 1
        d[1] += int(juste)


def totaux(st):
    n = np.array(st["n"]).sum(0) if st["n"] else np.zeros(len(st["modeles"]))
    j = np.array(st["justes"]).sum(0) if st["n"] else np.zeros(len(st["modeles"]))
    return {m: (int(n[k]), int(j[k])) for k, m in enumerate(st["modeles"])}


def poids_arbitre(st):
    """Poids de chaque IA = avance sur 50 % qui reste APRÈS avoir retiré l'erreur possible due au hasard
    (borne basse à ~84 %). Une IA qui ne fait pas mieux que le hasard, ou trop peu jugée, a un poids 0."""
    w = {}
    for m, (n, j) in totaux(st).items():
        if m in ("vote", "arbitre") or n < 500:
            continue
        acc = j / n
        w[m] = max(0.0, acc - 0.5 - math.sqrt(0.25 / n))
    return w


# --------------------------------------------------------------------------- boucle principale
def principal():
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    debut = time.time()
    preparer_branche()
    univers = lire_json("marches.json", {})
    if not univers.get("marches") or time.time() - univers.get("t", 0) > 86400:
        try:
            m = lister_marches(api)
        except Exception as e:
            print(f"liste des marchés impossible : {str(e)[:200]}", flush=True)
            m = {}
        if m:
            univers = {"t": time.time(), "maj": iso(), "marches": m}
    if not univers.get("marches"):  # navigation indisponible : au moins les grands marchés
        univers = {"t": 0, "maj": iso(), "marches": {e: {"nom": e, "type": "?"} for e in GRANDS}}
    tous = list(univers.get("marches", {}))
    print(f"{len(tous)} marchés Capital.com connus", flush=True)
    etat = instantanes(api, tous)
    ouverts = trier_ouverts(etat, tous)
    print(f"{len(ouverts)} ouverts maintenant", flush=True)

    maison = entrainer_maison(api, set(ouverts))
    if SERIES:
        np.savez("entrainement_ia.npz", series=np.array(SERIES, dtype=object))
        os.environ["IA_ENTRAINEMENT"] = os.path.abspath("entrainement_ia.npz")
    from ia.geantes import Geantes
    geantes = Geantes(attente_chargement=900, familles=[f for f in os.getenv("IA_FAMILLES", " ".join(FAMILLES)).split() if f])
    modeles = list(maison) + geantes.modeles() + ["vote", "arbitre"]
    st = lire_json("stats.json", None) or stats_vides(modeles)
    for m in modeles:
        index_modele(st, m)
    vivant = lire_json("vivant.json", {})
    vivant.update({"debut_tour": iso(), "marches_connus": len(tous), "marches_ouverts": len(ouverts), "lot": LOT,
                   "etat_ia": {**{m: "prête" for m in maison}, **geantes.etat}, "noms": NOMS,
                   "familles_maison": list(MAISON), "familles": {f: list(v["modeles"]) for f, v in FAMILLES.items()},
                   "exclues": EXCLUES})
    vivant.setdefault("probas", {})
    vivant.setdefault("dernieres", [])
    vivant.setdefault("vitesse", {})
    curseur = int(vivant.get("curseur", 0))
    attente = []
    derniere_session, derniere_pub, dernier_etat = time.time(), 0.0, time.time()
    pool = ThreadPoolExecutor(6)
    fond = ThreadPoolExecutor(1)
    tache_etat = tache_pub = None
    while time.time() - debut < DUREE:
        time.sleep(max(0.0, 60.5 - (maintenant().second + maintenant().microsecond / 1e6)) % 60)
        t_tour = time.time()
        if t_tour - derniere_session > 8 * 60:  # la session Capital.com expire après 10 min
            try:
                api.deconnexion()
            except Exception:
                pass
            api.connexion()
            derniere_session = time.time()
        if tache_etat is not None and tache_etat.done():
            try:
                ouverts = trier_ouverts(tache_etat.result(), tous)
                curseur = 0
            except Exception:
                pass
            tache_etat = None
        if t_tour - dernier_etat > 15 * 60 and tache_etat is None:  # marchés qui ouvrent / ferment (en arrière-plan)
            tache_etat = fond.submit(instantanes, api, tous)
            dernier_etat = time.time()
        etapes = {}
        # 1. juger les prédictions arrivées à échéance (60 s)
        dues = [p for p in attente if p["echeance"] <= time.time()]
        if dues:
            prix = instantanes(api, sorted({p["epic"] for p in dues}))
            for p in dues:
                attente.remove(p)
                fin = prix.get(p["epic"])
                if not fin or fin["mid"] == p["depart"]:
                    continue  # prix inchangé ou indisponible : non jugé
                hausse = fin["mid"] > p["depart"]
                jour = p["heure"][:10]
                for m, pr in p["probas"].items():
                    sens = 1 if pr > 0.5 else -1
                    gain = (sens * (fin["mid"] - p["depart"]) - p["spread"]) / p["depart"] * 100
                    compter(st, p["epic"], p["type"], jour, m, (sens > 0) == hausse, gain)
                vivant["dernieres"].append({"t": p["heure"], "epic": p["epic"], "vote": round(p["probas"]["vote"], 3),
                                            "arbitre": round(p["probas"]["arbitre"], 3),
                                            "reel": "hausse" if hausse else "baisse",
                                            "variation_pct": round((fin["mid"] / p["depart"] - 1) * 100, 4)})
            vivant["dernieres"] = vivant["dernieres"][-300:]
        # 2. nouveau lot de marchés (rotation)
        if not ouverts:
            continue
        lot = [ouverts[(curseur + k) % len(ouverts)] for k in range(min(LOT, len(ouverts)))]
        curseur = (curseur + len(lot)) % max(1, len(ouverts))

        def bougies(e):
            try:
                return e, vers_df(api.bougies(e, "MINUTE", L + 8))
            except Exception:
                return e, None
        t0 = time.time()
        donnees = {e: d for e, d in pool.map(bougies, lot) if d is not None and len(d) >= 320}
        etapes["bougies_s"] = round(time.time() - t0, 1)
        donnees = {e: d.iloc[-L:] for e, d in donnees.items()
                   if (maintenant().replace(tzinfo=None) - d.index[-1]).total_seconds() < 180}
        if not donnees:
            continue
        # prix EN TEMPS RÉEL juste avant le calcul : la bougie 1 min en cours est mise à jour avec le dernier prix
        frais = instantanes(api, list(donnees))
        t_frais = time.time()
        for e, d in list(donnees.items()):
            if e not in frais:
                continue
            d = d.copy()
            m, sp = frais[e]["mid"], frais[e]["spread"]
            d.iloc[-1, d.columns.get_loc("close_bid")] = m - sp / 2
            d.iloc[-1, d.columns.get_loc("close_ask")] = m + sp / 2
            for c, f in (("high_bid", max), ("high_ask", max), ("low_bid", min), ("low_ask", min)):
                d.iloc[-1, d.columns.get_loc(c)] = f(d[c].iloc[-1], d[c.replace("high", "close").replace("low", "close")].iloc[-1])
            donnees[e] = d
        epics = list(donnees)
        probas = {e: {} for e in epics}
        # IA maison
        Xf, Xsq, ok = [], [], []
        for e in epics:
            d = donnees[e]
            F, S = predire.indicateurs(d), predire.sequences(d)
            x = F.values[-1]
            if np.isnan(x).any():
                continue
            Xf.append(x); Xsq.append(S[-predire.SEQ:]); ok.append(e)
        if ok:
            Xf, Xsq = np.array(Xf), np.array(Xsq, dtype=np.float32)
            for m, f in maison.items():
                t0 = time.time()
                try:
                    pr = f(Xf, Xsq)
                    for e, p in zip(ok, pr):
                        probas[e][m] = float(p)
                    vivant["vitesse"][m] = round(time.time() - t0, 2)
                except Exception as ex:
                    vivant["etat_ia"][m] = f"erreur : {str(ex)[:150]}"
        # IA géantes : même entrée pour toutes
        n_max = max(len(donnees[e]) for e in epics)
        prix_mat, ohlcv = [], []
        for e in epics:
            d = donnees[e]
            mid = {k: ((d[f"{k}_bid"] + d[f"{k}_ask"]) / 2).values for k in ("open", "high", "low", "close")}
            arr = np.stack([mid["open"], mid["high"], mid["low"], mid["close"], d.volume.values], 1)
            arr = np.vstack([np.repeat(arr[:1], n_max - len(arr), 0), arr])  # complété au début si moins de 512 bougies
            ohlcv.append(arr)
            prix_mat.append(arr[:, 3])
        etapes["ia_maison_s"] = round(time.time() - t_frais, 1)
        t0 = time.time()
        reste = max(5.0, 40 - (time.time() - t_tour))
        pg, infos = geantes.prevoir(np.array(prix_mat), np.array(ohlcv), 1, delai=reste)
        for m, pr in pg.items():
            for e, p in zip(epics, pr):
                probas[e][m] = float(p)
        for m, v in infos.items():
            if isinstance(v, (int, float)):
                vivant["vitesse"][m] = v
                vivant["etat_ia"][m] = "prête"
            else:
                vivant["etat_ia"][m] = v
        # vote + arbitre, puis prix de départ
        w = poids_arbitre(st)
        etapes["ia_geantes_s"] = round(time.time() - t0, 1)
        depart = instantanes(api, epics)
        heure = iso()
        for e in epics:
            pe = probas[e]
            if not pe or e not in depart:
                continue
            ps = list(pe.values())
            pe["vote"] = float(np.mean(ps))
            tw = sum(w.get(m, 0) for m in pe if m != "vote")
            pe["arbitre"] = float(sum(w.get(m, 0) * p for m, p in pe.items() if m != "vote") / tw) if tw > 0 else pe["vote"]
            attente.append({"epic": e, "type": univers["marches"].get(e, {}).get("type", "?"), "heure": heure,
                            "echeance": time.time() + 60, "depart": depart[e]["mid"], "spread": depart[e]["spread"],
                            "probas": pe})
            vivant["probas"][e] = {"t": heure, "p": {m: round(p, 3) for m, p in pe.items()}}
        vivant["delais"] = {"prix_frais_vers_prediction_s": round(time.time() - t_frais, 1),
                            "debut_minute_vers_prediction_s": round(time.time() - t_tour, 1),
                            "marches_predits": len(epics)}
        vivant.setdefault("historique_delais", []).append([heure, vivant["delais"]["prix_frais_vers_prediction_s"]])
        vivant["historique_delais"] = vivant["historique_delais"][-120:]
        vivant["poids_arbitre"] = {m: round(v, 4) for m, v in w.items()}
        vivant["curseur"] = curseur
        vivant["duree_tour_s"] = round(time.time() - t_tour, 1)
        vivant["etapes"] = etapes
        # on ne garde que les probabilités de la dernière heure
        limite = iso(datetime.fromtimestamp(time.time() - 3600, timezone.utc))
        vivant["probas"] = {e: v for e, v in vivant["probas"].items() if v["t"] >= limite}
        if time.time() - derniere_pub > 3 * 60 and (tache_pub is None or tache_pub.done()):
            vivant["maj"] = iso()
            copie = json.loads(json.dumps({"stats.json": st, "vivant.json": vivant, "marches.json": univers}))
            tache_pub = fond.submit(publier, copie)  # en arrière-plan : la minute suivante n'attend pas
            derniere_pub = time.time()
    if tache_pub is not None:
        tache_pub.result()
    vivant["maj"] = iso()
    publier({"stats.json": st, "vivant.json": vivant, "marches.json": univers})
    geantes.fermer()
    api.deconnexion()


if __name__ == "__main__":
    random.seed(0)
    principal()

"""SUPER IA : moteur À PART (aucun ordre, aucune influence sur le test des autres IA).

Il lit le journal publié par ia/direct.py (branche ia-journal, fichier juges.json : chaque prédiction jugée à
5, 15, 30 et 60 min avec les probabilités de toutes les IA) et rejoue les événements DANS L'ORDRE DU TEMPS :
  - à l'heure t où la prédiction a été faite, la Super IA donne SA probabilité, avec uniquement ce qu'elle
    savait à t (résultats arrivés à échéance avant t) ;
  - à l'échéance, le résultat réel la corrige (poids, recalibrage, seuil de confiance, équipe).
Le moteur attend 68 min avant de traiter un instant, pour être sûr d'avoir reçu tous les résultats d'avant :
aucune information du futur.

Variantes, bien séparées (chacune a ses propres chiffres) :
  équipe  « fixe »      : Sundial, TiDE, TCN, N-BEATS, N-HiTS
          « évolutive » : part des mêmes, remplace un membre qui faiblit par une IA qui fait mieux en direct
                          (changements notés avec l'heure et la raison)
  pari    « toujours »  : donne une direction à chaque fois
          « sûre »      : ne parie que sur ses ~25 % de cas les plus confiants (taux de couverture suivi)
Poids : exponentiels (Hedge, perte logarithmique), par horizon, avec poids propres à l'or et à l'argent,
puis par famille de marchés, puis tous marchés (repli tant qu'un niveau n'a pas assez de résultats).
"""
import json
import math
import os
import subprocess
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FUSEAU = ZoneInfo("Europe/Paris")
from pathlib import Path

HS = [5, 15, 30, 60]
NOYAU = ["sundial", "tide", "tcn", "nbeats", "nhits"]
PRIORITE = {"GOLD": "Or", "SILVER": "Argent"}
# Vue « frais bas » : seulement les prédictions où le VRAI spread Capital.com du moment était petit,
# et la même chose limitée aux heures liquides (chevauchement Londres / New York, heure de Paris).
SPREAD_BAS = 0.03            # % du prix
HEURES_LIQUIDES = (14.5, 17.5)  # 14 h 30 - 17 h 30, heure de Paris
# Vue « mouvement > frais » : on ne compte que les prédictions où le mouvement HABITUEL de ce marché sur cet horizon
# (moyenne des résultats déjà connus AVANT la prédiction) vaut au moins RATIO_MIN fois le spread du moment.
RATIO_MIN = 3.0
EQUIPES = ["fixe", "evolutive"]
PARIS = ["toujours", "sure"]
ETA = 0.05
MIN_MARCHE, MIN_FAMILLE = 150, 300
COUVERTURE, FENETRE_CONF = 0.25, 400
FENETRE_EQUIPE, MIN_CANDIDAT, AVANCE = 1500, 300, 0.01
ATTENTE = 68 * 60  # secondes : un instant n'est traité que quand tous les résultats d'avant sont publiés
DOSSIER = Path(os.getenv("SUPER_DOSSIER", "super_ia"))
BRANCHE, SOURCE = "ia-super", "ia-journal"


def iso(t=None):
    return datetime.fromtimestamp(t if t is not None else time.time(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _lg(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def _sig(x):
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, x))))


def etat_vide():
    return {"version": 1, "coupure": 0, "logw": {}, "vus": {}, "calib": {}, "conf": {}, "recents": {},
            "equipe": {str(h): list(NOYAU) for h in HS}, "changements": [], "attente": {}, "faits": [],
            "stats": {}, "dernieres": []}


class SuperIA:
    def __init__(self, e=None):
        self.e = e or etat_vide()

    # ------------------------------------------------------------------ prédiction
    def _groupes(self, it):
        g = []
        if it["e"] in PRIORITE:
            g.append("m:" + it["e"])
        g += ["f:" + it["ty"], "tout"]
        return g

    def _cle_poids(self, it):
        for g in self._groupes(it):
            cle = f'{it["h"]}|{g}'
            mini = MIN_MARCHE if g.startswith("m:") else MIN_FAMILLE if g.startswith("f:") else 0
            if self.e["vus"].get(cle, 0) >= mini:
                return cle
        return f'{it["h"]}|tout'

    def membres(self, equipe, h):
        return NOYAU if equipe == "fixe" else self.e["equipe"][str(h)]

    def prevoir(self, it, equipe):
        pr = {m: p for m, p in it["p"].items() if m in self.membres(equipe, it["h"])}
        if not pr:
            return None
        lw = self.e["logw"].get(self._cle_poids(it), {})
        haut = max(lw.get(m, 0.0) for m in pr)
        w = {m: math.exp(lw.get(m, 0.0) - haut) for m in pr}
        brut = sum(w[m] * pr[m] for m in pr) / sum(w.values())
        a, b = self.e["calib"].get(f'{equipe}|{it["h"]}', [1.0, 0.0])
        q = _sig(a * _lg(brut) + b)
        conf = self.e["conf"].get(f'{equipe}|{it["h"]}', [])
        seuil = sorted(conf)[int(len(conf) * (1 - COUVERTURE))] if len(conf) >= 50 else 1.0
        sure = abs(q - 0.5) >= seuil
        conf.append(round(abs(q - 0.5), 5))
        del conf[:-FENETRE_CONF]
        self.e["conf"][f'{equipe}|{it["h"]}'] = conf
        return {"q": round(q, 4), "brut": round(brut, 4), "sure": sure}

    # ------------------------------------------------------------------ correction après le résultat
    def apprendre(self, it, preds):
        y = it["up"]
        for g in self._groupes(it):  # poids de TOUTES les IA (pour pouvoir en recruter de nouvelles)
            cle = f'{it["h"]}|{g}'
            lw = self.e["logw"].setdefault(cle, {})
            for m, p in it["p"].items():
                p = min(max(p, 1e-4), 1 - 1e-4)
                perte = -(y * math.log(p) + (1 - y) * math.log(1 - p))
                lw[m] = round(lw.get(m, 0.0) - ETA * (perte - math.log(2)), 5)  # 0 = aussi bien que le hasard
            self.e["vus"][cle] = self.e["vus"].get(cle, 0) + 1
        for equipe, pr in preds.items():  # recalibrage (descente de gradient sur la perte logistique)
            cle = f'{equipe}|{it["h"]}'
            a, b = self.e["calib"].get(cle, [1.0, 0.0])
            x = _lg(pr["brut"])
            err = _sig(a * x + b) - y
            self.e["calib"][cle] = [round(min(20.0, max(0.0, a - 0.01 * err * x)), 5), round(min(1.0, max(-1.0, b - 0.01 * err)), 5)]
            hausse = pr["q"] > 0.5
            gain = (it["mv"] if hausse else -it["mv"]) - it["sp"]
            for pari in PARIS:
                if pari == "sure" and not pr["sure"]:
                    continue
                self._compter(f"{equipe}_{pari}", it, hausse == bool(y), gain, pr.get("r"))
        mv = self.e.setdefault("mouvement", {}).setdefault(it["e"], [0.0, 0])
        a = abs(it["mv"]) / math.sqrt(it["h"])  # mouvement ramené à 1 minute (il grandit comme la racine du temps)
        mv[0] = round(0.8 * mv[0] + 0.2 * a, 6) if mv[1] else round(a, 6)  # moyenne glissante
        mv[1] += 1
        # réussite récente de chaque IA (pour l'équipe évolutive)
        rec = self.e["recents"].setdefault(str(it["h"]), {})
        for m, p in it["p"].items():
            r = rec.setdefault(m, [])
            r.append(int((p > 0.5) == bool(y)))
            del r[:-FENETRE_EQUIPE]
        sp = self.e.setdefault("spreads", {}).setdefault(it["e"], [0.0, 0, 0])
        sp[0] = round(sp[0] + it["sp"], 6)
        sp[1] += 1
        sp[2] += int(it["sp"] <= SPREAD_BAS)
        self.e["dernieres"].append({"t": it["t"], "e": it["e"], "h": it["h"], "up": y, "mv": it["mv"],
                                    **{equipe: [pr["q"], int(pr["sure"])] for equipe, pr in preds.items()}})
        del self.e["dernieres"][:-300]

    def _compter(self, variante, it, juste, gain, ratio=None):
        st = self.e["stats"].setdefault(str(it["h"]), {}).setdefault(variante, {"n": 0, "j": 0, "g": 0.0, "familles": {}, "marches": {}})
        vide = {"n": 0, "j": 0, "g": 0.0}
        cases = [st, st["familles"].setdefault(it["ty"], dict(vide)), st["marches"].setdefault(it["e"], dict(vide))]
        t0 = datetime.fromtimestamp(it["ech"] - 60 * it["h"], FUSEAU)
        heure = t0.hour + t0.minute / 60
        hh = f"{t0.hour:02d}"
        cases.append(st.setdefault("heures", {}).setdefault(hh, dict(vide)))
        if it["sp"] <= SPREAD_BAS:
            cases.append(st.setdefault("frais_bas", dict(vide)))
            cases.append(st.setdefault("heures_frais_bas", {}).setdefault(hh, dict(vide)))
            if HEURES_LIQUIDES[0] <= heure < HEURES_LIQUIDES[1]:
                cases.append(st.setdefault("frais_bas_liquide", dict(vide)))
        if ratio is not None and ratio >= RATIO_MIN:
            cases.append(st.setdefault("mouvement_ok", dict(vide)))
            if HEURES_LIQUIDES[0] <= heure < HEURES_LIQUIDES[1]:
                cases.append(st.setdefault("mouvement_ok_liquide", dict(vide)))
        for d in cases:
            d["n"] += 1
            d["j"] += int(juste)
            d["g"] = round(d["g"] + gain, 5)

    def revoir_equipe(self, h, quand):
        """Équipe évolutive : le membre le plus faible sort si une autre IA fait nettement mieux (plus que le hasard
        ne peut l'expliquer) sur leurs FENETRE_EQUIPE derniers résultats (au moins MIN_CANDIDAT résultats)."""
        rec = self.e["recents"].get(str(h), {})
        score = {m: sum(r) / len(r) for m, r in rec.items() if len(r) >= MIN_CANDIDAT}
        eq = self.e["equipe"][str(h)]
        presents = [m for m in eq if m in score]
        candidats = sorted((m for m in score if m not in eq), key=score.get, reverse=True)
        if not presents or not candidats:
            return
        faible = min(presents, key=score.get)
        meilleur = candidats[0]
        n = min(len(rec[meilleur]), len(rec[faible]))
        marge = max(AVANCE, 2 * math.sqrt(0.5 / n))  # écart nettement plus grand que le hasard
        if score[meilleur] > score[faible] + marge:
            eq[eq.index(faible)] = meilleur
            self.e["changements"].append({"t": iso(quand), "h": h, "entre": meilleur, "sort": faible,
                                          "raison": f"{100 * score[meilleur]:.1f} % contre {100 * score[faible]:.1f} % sur les derniers résultats"})
            del self.e["changements"][:-100]

    # ------------------------------------------------------------------ rejeu dans l'ordre du temps
    def traiter(self, items, maintenant):
        coupure = maintenant - ATTENTE
        premiers = [it["ech"] - 60 * it["h"] for it in items]
        avant = self.e["coupure"] or (min(premiers) - 1 if premiers else coupure)
        faits = set(self.e["faits"])
        ev = []
        for it in items:
            if it["h"] not in HS:
                continue
            t0 = it["ech"] - 60 * it["h"]
            if avant < t0 <= coupure and it["id"] not in faits:
                ev.append((t0, 0, it))  # 0 : une prédiction passe avant une correction au même instant
            if avant < it["ech"] <= coupure:
                ev.append((it["ech"], 1, it))
        ev.sort(key=lambda x: (x[0], x[1]))
        n_pred = n_corr = 0
        for t, genre, it in ev:
            if genre == 0:
                faits.add(it["id"])
                preds = {eq: p for eq in EQUIPES if (p := self.prevoir(it, eq))}
                mvh = self.e.setdefault("mouvement", {}).get(it["e"])  # connu avant t : pas de triche
                ratio = round(mvh[0] * math.sqrt(it["h"]) / max(it["sp"], 1e-9), 3) if mvh and mvh[1] >= 2 else None
                for p in preds.values():
                    p["r"] = ratio
                if preds:
                    self.e["attente"][it["id"]] = preds
                    n_pred += 1
            else:
                preds = self.e["attente"].pop(it["id"], None)
                if preds:
                    self.apprendre(it, preds)
                    n_corr += 1
                    if self.e["vus"].get(f'{it["h"]}|tout', 0) % 200 == 0:
                        self.revoir_equipe(it["h"], t)
        self.e["coupure"] = coupure
        garde = {it["id"] for it in items}
        self.e["faits"] = [i for i in faits if i in garde]
        self.e["attente"] = {i: p for i, p in self.e["attente"].items() if i in garde}
        return n_pred, n_corr


# ---------------------------------------------------------------------- git (lecture du journal, publication)
def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=DOSSIER, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 1, "", "délai dépassé")


def preparer():
    depot = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True).stdout.strip()
    if not (DOSSIER / ".git").exists():
        DOSSIER.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(DOSSIER)])
        auth = subprocess.run(["git", "config", "--get-regexp", r"http\..*\.extraheader"], capture_output=True, text=True).stdout
        for ligne in auth.splitlines():
            k, v = ligne.split(" ", 1)
            git("config", k, v)
        git("remote", "add", "origin", depot)
        git("config", "user.name", "bot-trading-demo")
        git("config", "user.email", "bot-trading-demo@users.noreply.github.com")
    if git("fetch", "-q", "--depth", "1", "origin", BRANCHE).returncode == 0:
        git("checkout", "-q", "-f", "-B", BRANCHE, "FETCH_HEAD")


def lire_journal():
    if os.getenv("SUPER_JUGES"):  # essais locaux
        return json.loads(Path(os.environ["SUPER_JUGES"]).read_text()).get("items", [])
    if git("fetch", "-q", "--depth", "1", "origin", SOURCE).returncode:
        return []
    r = git("show", "FETCH_HEAD:juges.json")
    try:
        return json.loads(r.stdout).get("items", []) if r.returncode == 0 else []
    except Exception:
        return []


def publier(s):
    tableau = {"maj": iso(), "horizons": HS, "noyau": NOYAU, "priorite": PRIORITE, "equipes": EQUIPES, "paris": PARIS,
               "equipe_evolutive": s.e["equipe"], "changements": s.e["changements"], "stats": s.e["stats"],
               "dernieres": s.e["dernieres"][-150:], "coupure": iso(s.e["coupure"]) if s.e["coupure"] else None,
               "couverture_visee": COUVERTURE, "spread_bas": SPREAD_BAS, "ratio_min": RATIO_MIN, "heures_liquides": HEURES_LIQUIDES,
               "spreads": {e: {"moyen": round(v[0] / v[1], 5), "n": v[1], "bas": round(v[2] / v[1], 3)}
                           for e, v in s.e.get("spreads", {}).items() if v[1]}}
    (DOSSIER / "super_etat.json").write_text(json.dumps(s.e, separators=(",", ":")))
    (DOSSIER / "super.json").write_text(json.dumps(tableau, ensure_ascii=False, separators=(",", ":")))
    if os.getenv("SUPER_GIT", "oui") != "oui":
        return
    git("checkout", "-q", "--orphan", "tmp")
    git("add", "-A")
    git("commit", "-qm", f"Super IA {iso()}")
    git("branch", "-q", "-D", BRANCHE)
    git("branch", "-q", "-m", BRANCHE)
    r = git("push", "-q", "-f", "origin", BRANCHE)
    if r.returncode:
        print("publication impossible :", r.stderr[:300], flush=True)


def principal():
    preparer()
    try:
        e = json.loads((DOSSIER / "super_etat.json").read_text())
    except Exception:
        e = None
    s = SuperIA(e)
    debut = time.time()
    duree = int(os.getenv("SUPER_DUREE_S", "3300"))
    while True:
        items = lire_journal()
        maintenant = float(os.getenv("SUPER_MAINTENANT", "0")) or time.time()
        n_pred, n_corr = s.traiter(items, maintenant)
        print(f"{iso()} : {len(items)} résultats lus, {n_pred} prédictions, {n_corr} corrections", flush=True)
        publier(s)
        if time.time() - debut > duree or os.getenv("SUPER_UNE_FOIS"):
            break
        time.sleep(120)


if __name__ == "__main__":
    principal()

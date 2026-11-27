"""IA UNIQUE « multi-cerveaux » : toutes les IA à l'intérieur, sans mélanger leurs avis à l'aveugle.

Moteur À PART (aucun ordre, n'influence ni le direct ni la Super IA ni les boosts).

Idée (recherche du 27/11, voir ia/MULTI_CERVEAUX.md) :
- chaque IA est un CERVEAU qui garde son identité ; on ajoute pour chacun son « cerveau miroir » (le sens inverse),
  utile quand une IA se trompe de façon régulière (collée à l'ancienne tendance pendant un retournement) ;
  plus deux cerveaux simples : « suiveur » (continue le dernier mouvement connu) et « contrarien » (son miroir) ;
- un MÉTA-CERVEAU décide qui écouter selon le RÉGIME du marché, calculé uniquement avec ce qui était connu
  à l'instant de la prédiction :
    * tendance / retournement / neutre : réussite récente du « suiveur » (sur les 30 derniers résultats connus) ;
    * calme / agité : mouvement récent du marché comparé à son habitude ;
  pour chaque régime, des poids « Fixed Share » (Herbster & Warmuth : suivre le meilleur expert même quand il
  change ; une part des poids est redistribuée à chaque pas pour qu'un cerveau oublié puisse revenir vite) ;
  tant qu'un régime n'a pas assez de résultats, le méta-cerveau utilise les poids tous régimes confondus ;
- abstention (« ne parie que si sûr ») : seuil de confiance choisi sur le PASSÉ seulement, pour le meilleur gain
  moyen après le vrai spread ; si aucun seuil n'est positif sur le passé, il ne parie pas.

Anti-triche : rejeu dans l'ordre du temps ; une prédiction faite à t0 n'utilise que des résultats dont
l'échéance est <= t0 ; au même instant, la prédiction passe AVANT la correction. Contrôle « prix mélangés » :
on redistribue les résultats au hasard entre les prédictions et on refait tout : il faut retomber vers 50 %.

Usage : python -m ia.multi_cerveaux            (lit ia-archives + ia-journal, publie ia-multi/multi.json)
        python -m ia.multi_cerveaux tous.json  (essai local, n'envoie rien)
"""
import gzip
import json
import math
import os
import random
import subprocess
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
P8 = ["GOLD", "SILVER", "OIL_CRUDE", "US100", "US500", "DE40", "EURUSD", "GBPUSD"]
HS = [5, 15, 30, 60]
EN_DIRECT_DEPUIS = "2026-11-27T20:00:00Z"   # chiffres « en direct » : seulement des prédictions faites après la mise en route
ETA = 1.0          # vitesse d'apprentissage (perte logarithmique)
ALPHA = 0.02       # part redistribuée à chaque pas (Fixed Share)
MIN_REGIME = 60    # résultats minimum dans un régime avant d'utiliser ses propres poids
FEN_SUIVEUR = 30   # derniers résultats pour mesurer « tendance ou retournement »
SEUILS = (0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.15)
MIN_PARIS_SEUIL = 40
DOSSIER = Path(os.getenv("MULTI_DOSSIER", "multi_pub"))
REPO = Path(__file__).resolve().parents[1]


def ts(t):
    return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()


def iso(t=None):
    return datetime.fromtimestamp(t if t is not None else datetime.now().timestamp(), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clip(p):
    return min(max(p, 1e-3), 1 - 1e-3)


class Poids:
    """Poids Fixed Share sur des cerveaux qui ne sont pas toujours tous présents (« experts endormis »)."""

    def __init__(self):
        self.lw = {}
        self.n = 0

    def melange(self, avis):
        if not avis:
            return 0.5
        lw = {m: self.lw.get(m, 0.0) for m in avis}
        haut = max(lw.values())
        w = {m: math.exp(v - haut) for m, v in lw.items()}
        s = sum(w.values())
        return sum(w[m] * avis[m] for m in avis) / s

    def apprendre(self, avis, y):
        if not avis:
            return
        for m, p in avis.items():
            p = _clip(p)
            self.lw[m] = self.lw.get(m, 0.0) + ETA * math.log(p if y else 1 - p)
        # Fixed Share sur les cerveaux présents : normalisation, puis redistribution d'une part ALPHA
        pres = list(avis)
        haut = max(self.lw[m] for m in pres)
        w = {m: math.exp(self.lw[m] - haut) for m in pres}
        s = sum(w.values())
        for m in pres:
            self.lw[m] = math.log((1 - ALPHA) * w[m] / s + ALPHA / len(pres))
        self.n += 1

    def top(self, k=6):
        if not self.lw:
            return []
        haut = max(self.lw.values())
        w = {m: math.exp(v - haut) for m, v in self.lw.items()}
        s = sum(w.values())
        return sorted(((m, round(v / s, 4)) for m, v in w.items()), key=lambda x: -x[1])[:k]


class MultiCerveaux:
    def __init__(self, miroirs=True, regimes=True):
        self.miroirs, self.regimes = miroirs, regimes
        self.poids = defaultdict(Poids)                      # (h, régime) -> poids
        self.dernier = {}                                    # (marché, h) -> dernier résultat connu (sens)
        self.suiveur = defaultdict(lambda: deque(maxlen=FEN_SUIVEUR))   # h -> réussite récente du suiveur
        self.mvt = defaultdict(lambda: deque(maxlen=5))      # marché -> derniers mouvements ramenés à 1 min
        self.mvt_moy = defaultdict(lambda: [0.0, 0])         # marché -> moyenne de long terme
        self.passe = defaultdict(list)                       # h -> (confiance, gain après frais) connus

    # ------------------------------------------------------------------ régime connu à t0
    def regime(self, it):
        if not self.regimes:
            return "tous"
        s = self.suiveur[it["h"]]
        acc = sum(s) / len(s) if len(s) >= 10 else 0.5
        tend = "tendance" if acc >= 0.56 else "retournement" if acc <= 0.44 else "neutre"
        r, (m, n) = self.mvt[it["e"]], self.mvt_moy[it["e"]]
        vol = "agite" if r and n >= 10 and sum(r) / len(r) > 1.3 * m else "calme"
        return f"{tend}|{vol}"

    def avis(self, it):
        a = {}
        for m, p in it["p"].items():
            a[m] = _clip(p)
            if self.miroirs:
                a["~" + m] = 1 - a[m]
        d = self.dernier.get((it["e"], it["h"]))
        if d is not None:
            a["suiveur"] = 0.6 if d else 0.4
            a["contrarien"] = 0.4 if d else 0.6
        return a

    def prevoir(self, it):
        a = self.avis(it)
        reg = self.regime(it)
        cle = (it["h"], reg)
        pw = self.poids[cle] if self.poids[cle].n >= MIN_REGIME else self.poids[(it["h"], "tous")]
        q = pw.melange(a)
        # seuil de confiance choisi sur le passé (8 marchés, même horizon) pour le meilleur gain après frais
        sure = _sure(self.passe[it["h"]], q)
        return {"q": q, "sure": sure, "regime": reg, "a": a}

    # ------------------------------------------------------------------ correction à l'échéance
    def apprendre(self, it, pr):
        y = it["up"]
        a = pr["a"]
        self.poids[(it["h"], pr["regime"])].apprendre(a, y)
        if pr["regime"] != "tous":
            self.poids[(it["h"], "tous")].apprendre(a, y)
        if it["e"] in P8:
            gain = (it["mv"] if pr["q"] > 0.5 else -it["mv"]) - it["sp"]
            self.passe[it["h"]].append((abs(pr["q"] - 0.5), gain))
            del self.passe[it["h"]][:-2000]
        d = self.dernier.get((it["e"], it["h"]))
        if d is not None:
            self.suiveur[it["h"]].append(int(d == y))
        self.dernier[(it["e"], it["h"])] = y
        v = abs(it["mv"]) / math.sqrt(it["h"])
        self.mvt[it["e"]].append(v)
        m = self.mvt_moy[it["e"]]
        m[0] = (m[0] * m[1] + v) / (m[1] + 1)
        m[1] += 1


CHEFS = {"regimes": {"miroirs": True, "regimes": True}, "global": {"miroirs": True, "regimes": False},
         "sans_miroirs": {"miroirs": False, "regimes": True}}


def rejouer(items, **opts):
    """Rejeu dans l'ordre du temps. Trois étages :
    1) les cerveaux (chaque IA, son miroir, suiveur, contrarien) ;
    2) trois méta-cerveaux (par régime, tous régimes, sans miroirs) + le vote simple ;
    3) le CHEF : Fixed Share sur ces quatre avis (il suit celui qui marche en ce moment, par horizon).
    Si opts est donné, on ne fait tourner qu'un méta-cerveau (contrôles)."""
    metas = {"seul": MultiCerveaux(**opts)} if opts else {k: MultiCerveaux(**o) for k, o in CHEFS.items()}
    chef = defaultdict(Poids)
    passe = defaultdict(list)
    ev = []
    for it in items:
        if it["h"] not in HS or not it.get("p"):
            continue
        t0 = it["ech"] - 60 * it["h"]
        ev.append((t0, 0, it))
        ev.append((it["ech"], 1, it))
    ev.sort(key=lambda x: (x[0], x[1]))
    attente, sortie = {}, []
    for _, genre, it in ev:
        if genre == 0:
            prs = {k: m.prevoir(it) for k, m in metas.items()}
            vote = sum(it["p"].values()) / len(it["p"])
            if opts:
                pr = prs["seul"]
                q, sure, reg = pr["q"], pr["sure"], pr["regime"]
                avis = None
            else:
                avis = {k: pr["q"] for k, pr in prs.items()}
                avis["vote"] = vote
                q = chef[it["h"]].melange(avis)
                reg = prs["regimes"]["regime"]
                sure = _sure(passe[it["h"]], q)
            attente[it["id"]] = (prs, avis, q)
            sortie.append({"it": it, "q": q, "sure": sure, "regime": reg, "vote": vote})
        else:
            x = attente.pop(it["id"], None)
            if x:
                prs, avis, q = x
                for k, m in metas.items():
                    m.apprendre(it, prs[k])
                if avis:
                    chef[it["h"]].apprendre(avis, it["up"])
                    if it["e"] in P8:
                        passe[it["h"]].append((abs(q - 0.5), (it["mv"] if q > 0.5 else -it["mv"]) - it["sp"]))
                        del passe[it["h"]][:-2000]
    return sortie, (metas, chef, passe)


def _sure(passe, q):
    passe = passe[-600:]
    seuil, meilleur = None, 0.0
    for s in SEUILS:
        g = [x for c, x in passe if c >= s]
        if len(g) >= MIN_PARIS_SEUIL and sum(g) / len(g) > meilleur:
            meilleur, seuil = sum(g) / len(g), s
    return seuil is not None and abs(q - 0.5) >= seuil


def resume(lst):
    if not lst:
        return None
    n = len(lst)
    j = sum(s == bool(x["up"]) for s, x in lst)
    g = [((x["mv"] if s else -x["mv"]) - x["sp"]) for s, x in lst]
    hausses = sum(x["up"] for _, x in lst)
    return {"n": n, "instants": len({x["t"] for _, x in lst}), "reussite": round(j / n, 4),
            "gain": round(sum(g) / n, 5), "sens_majoritaire": round(max(hausses, n - hausses) / n, 4)}


def variantes(sortie, h, depuis=None, filtre=None):
    """{nom: liste de (prédit hausse ?, item)} sur les 8 marchés pour l'horizon h."""
    v = defaultdict(list)
    for s in sortie:
        it = s["it"]
        if it["h"] != h or it["e"] not in P8 or (depuis and it["t"] < depuis) or (filtre and not filtre(it)):
            continue
        v["IA unique : toujours"].append((s["q"] > 0.5, it))
        if s["sure"]:
            v["IA unique : seulement si sûre"].append((s["q"] > 0.5, it))
        v["Vote simple (référence)"].append((s["vote"] > 0.5, it))
    return v


def melanger(items, graine):
    """Prix mélangés : on redistribue au hasard les résultats (sens + mouvement) entre prédictions du même horizon."""
    r = random.Random(graine)
    Y = [dict(x) for x in items]
    for h in {x["h"] for x in Y}:
        grp = [y for y in Y if y["h"] == h]
        res = [(y["up"], y["mv"]) for y in grp]
        r.shuffle(res)
        for y, (u, mv) in zip(grp, res):
            y["up"], y["mv"] = u, mv
    return Y


def en_cours(attente, metas, chef, passe):
    """Prédictions de l'IA unique pour les prédictions des IA pas encore jugées (8 marchés), avec l'état appris."""
    der = {}
    for a in attente:
        if a.get("epic") in P8 and a.get("h") in HS and a.get("probas"):
            k = (a["epic"], a["h"])
            if k not in der or a["heure"] > der[k]["heure"]:
                der[k] = a
    out = []
    for (e, h), a in sorted(der.items()):
        it = {"e": e, "h": h, "p": {m: float(v) for m, v in a["probas"].items() if v == v}, "t": a["heure"]}
        prs = {k: m.prevoir(it) for k, m in metas.items()}
        avis = {k: pr["q"] for k, pr in prs.items()}
        avis["vote"] = sum(it["p"].values()) / len(it["p"])
        q = chef[h].melange(avis)
        out.append({"e": e, "h": h, "t": a["heure"], "ech": round(a["echeance"]), "q": round(q, 4),
                    "sure": int(_sure(passe[h], q)), "regime": prs["regimes"]["regime"],
                    "regime_seul": round(prs["regimes"]["q"], 4), "vote": round(avis["vote"], 4)})
    return out


def heure_paris(it):
    d = datetime.fromtimestamp(ts(it["t"]), PARIS)
    return d.hour + d.minute / 60


def analyser(items, graines=(1, 2, 3, 4, 5), attente=None):
    items = [x for x in items if x.get("p") and x["h"] in HS]
    reel, (metas, chef, passe) = rejouer(items)
    mc = metas["regimes"]
    sans_reg, _ = rejouer(items, regimes=False)
    sans_mir, _ = rejouer(items, miroirs=False)
    seul_reg, _ = rejouer(items, regimes=True)
    faux = [rejouer(melanger(items, g))[0] for g in graines]
    out = {"maj": iso(), "en_direct_depuis": EN_DIRECT_DEPUIS, "marches": P8, "horizons": {},
           "reglages": {"eta": ETA, "alpha": ALPHA, "min_regime": MIN_REGIME, "fen_suiveur": FEN_SUIVEUR},
           "regimes_actuels": {}, "qui_ecouter": {}}
    for h in HS:
        V = variantes(reel, h)
        D = variantes(reel, h, EN_DIRECT_DEPUIS)
        M = variantes(reel, h, filtre=lambda it: heure_paris(it) < 12.5)
        A = variantes(reel, h, filtre=lambda it: heure_paris(it) >= 12.5)
        F = [variantes(f, h) for f in faux]
        bloc = {}
        for nom, lst in V.items():
            fm = [resume(f.get(nom, [])) for f in F]
            fm = [x for x in fm if x]
            bloc[nom] = {"test_complet": resume(lst), "en_direct": resume(D.get(nom, [])),
                         "matin": resume(M.get(nom, [])), "apres_midi": resume(A.get(nom, [])),
                         "prix_melanges": {"reussite_moy": round(sum(x["reussite"] for x in fm) / len(fm), 4) if fm else None,
                                           "reussite_max": max((x["reussite"] for x in fm), default=None),
                                           "gain_moy": round(sum(x["gain"] for x in fm) / len(fm), 5) if fm else None}}
        out.setdefault("chef", {})[str(h)] = chef[h].top(4)
        for nom, srt in (("Méta-cerveau régimes seul", seul_reg), ("Sans régimes (contrôle)", sans_reg), ("Sans cerveaux miroirs (contrôle)", sans_mir)):
            bloc[nom] = {"test_complet": resume(variantes(srt, h)["IA unique : toujours"]),
                         "en_direct": resume(variantes(srt, h, EN_DIRECT_DEPUIS)["IA unique : toujours"])}
        out["horizons"][str(h)] = bloc
        cles = [k for k in mc.poids if k[0] == h]
        out["qui_ecouter"][str(h)] = {k[1]: {"resultats": mc.poids[k].n, "top": mc.poids[k].top()} for k in cles}
        der = [s for s in reel if s["it"]["h"] == h and s["it"]["e"] in P8]
        if der:
            out["regimes_actuels"][str(h)] = der[-1]["regime"]
    out["en_cours"] = en_cours(attente or [], metas, chef, passe)
    out["dernieres"] = [{"t": s["it"]["t"], "e": s["it"]["e"], "h": s["it"]["h"], "q": round(s["q"], 4),
                         "sure": int(s["sure"]), "regime": s["regime"], "up": s["it"]["up"]}
                        for s in reel if s["it"]["e"] in P8][-120:]
    return out


# ---------------------------------------------------------------------- lecture et publication
def g(*a, cwd=REPO):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True).stdout


def charger_attente():
    try:
        return json.loads(g("show", "origin/ia-journal:attente.json"))
    except Exception:
        return []


def charger():
    for b in ("ia-archives", "ia-journal"):
        subprocess.run(["git", "fetch", "-q", "origin", b], cwd=REPO)
    items = {}
    for f in g("ls-tree", "-r", "--name-only", "origin/ia-archives").decode().split():
        for ligne in gzip.decompress(g("show", f"origin/ia-archives:{f}")).decode().splitlines():
            if ligne.strip():
                x = json.loads(ligne)
                items[x["id"]] = x
    try:
        for x in json.loads(g("show", "origin/ia-journal:juges.json"))["items"]:
            items[x["id"]] = x
    except Exception:
        pass
    return list(items.values())


def publier(sortie):
    DOSSIER.mkdir(exist_ok=True)
    (DOSSIER / "multi.json").write_text(json.dumps(sortie, ensure_ascii=False, separators=(",", ":")))
    if os.getenv("MULTI_GIT", "oui") != "oui":
        return
    url = g("config", "--get", "remote.origin.url").decode().strip()
    auth = [c for l in g("config", "--get-regexp", r"http\..*\.extraheader").decode().splitlines()
            for c in ("-c", "=".join(l.split(" ", 1)))]
    for a in (["init", "-q"], ["checkout", "-q", "-b", "ia-multi"], ["add", "-A"],
              ["-c", "user.name=bot-trading-demo", "-c", "user.email=bot-trading-demo@users.noreply.github.com",
               "commit", "-qm", "IA unique " + sortie["maj"]],
              [*auth, "push", "-q", "-f", url, "ia-multi"]):
        r = subprocess.run(["git", *a], cwd=DOSSIER, capture_output=True, text=True)
        if r.returncode:
            print("git", a[-1], r.stderr[:300])


def principal():
    if len(sys.argv) > 1:
        items = json.load(open(sys.argv[1]))
        os.environ["MULTI_GIT"] = "non"
        attente = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else []
    else:
        items = charger()
        attente = charger_attente()
    out = analyser(items, attente=attente)
    for h in ("15", "5", "60", "30"):
        for nom, b in out["horizons"][h].items():
            t = b["test_complet"]
            if t:
                pm = b.get("prix_melanges", {})
                print(f"{h:>2} min | {nom:34s} | n={t['n']:5d} inst={t['instants']:4d} | {100 * t['reussite']:.1f} % "
                      f"| gain {t['gain']:+.4f} % | maj {100 * t['sens_majoritaire']:.1f} % "
                      f"| mélangés {pm.get('reussite_moy')} max {pm.get('reussite_max')}")
    publier(out)


if __name__ == "__main__":
    principal()

"""SIMULATEUR « MACHINE À REMONTER LE TEMPS » (26/11/2026, idée reprise du skill trader-timemachine).

Pour chaque position ouverte, il rejoue la suite du marché des milliers de fois à partir des VRAIES bougies
récentes de ce marché (méthode de Monte-Carlo par tirage de bougies) et compte combien de fois le prix touche :
  - le stop d'abord ;
  - l'objectif d'abord (le TP s'il existe, sinon un gain de 2 R : 2 fois la distance entrée -> stop) ;
  - ni l'un ni l'autre avant l'horizon (4 h pour la Rapide 5 min, 5 jours pour les stratégies 4 h).

Comment se fait un tirage : chaque bougie passée devient 4 rapports à la clôture d'avant (ouverture, plus haut,
plus bas, clôture). On part du prix actuel et on enchaîne des bougies tirées au hasard dans ce paquet (en 4 h, de
préférence à la même heure de la journée, comme le skill qui garde l'heure de la séance). Si une bougie touche le
stop ET l'objectif, on compte le stop (prudent).

Ce module ne passe AUCUN ordre et ne change AUCUNE décision : c'est une information pour l'appli.
LIMITES, dites honnêtement : le stop est supposé fixe (les stops suiveurs bougent en vrai) ; le tirage au hasard
efface toute tendance, donc le résultat dépend surtout de la distance du stop et de l'objectif face à la
volatilité récente. Ce n'est pas une prédiction. Le test sur 10 ans (backtest/time_machine.py) dit s'il est bien
« calibré » (quand il annonce 30 %, est-ce que ça arrive ~30 % du temps ?) et s'il sert de filtre d'entrée.
"""
import hashlib
import math

import numpy as np
import pandas as pd

TIRAGES = 4000
HORIZON = {"MINUTE_5": 48, "MINUTE_15": 32, "HOUR": 24, "HOUR_4": 30, "DAY": 10}
TEXTE_HORIZON = {"MINUTE_5": "4 h", "MINUTE_15": "8 h", "HOUR": "24 h", "HOUR_4": "5 jours", "DAY": "10 jours"}
POOL_MAX = 1000          # bougies récentes utilisées au maximum
POOL_MIN = 60            # en dessous : pas de simulation (trop peu d'historique)
PAR_CRENEAU_MIN = 30     # tirage « même heure » seulement si chaque heure a au moins 30 bougies
OBJECTIF_R = 2.0


def paquet(o, h, l, c, heures=None):
    """Rapports (o, h, l, c) / clôture précédente, et l'heure de chaque bougie (ou None)."""
    o, h, l, c = (np.asarray(x, dtype=float) for x in (o, h, l, c))
    pc = c[:-1]
    r = np.column_stack([o[1:] / pc, h[1:] / pc, l[1:] / pc, c[1:] / pc])
    ok = np.isfinite(r).all(axis=1) & (pc > 0)
    hr = None if heures is None else np.asarray(heures)[1:][ok]
    return r[ok], hr


def simuler(ratios, prix, sens, stop, objectif, horizon, tirages=TIRAGES, graine=19, heures=None, heure_depart=None,
            pas_h=None):
    """Monte-Carlo vectorisé. sens = +1 achat / -1 vente. Renvoie les probabilités (0-1) et les prix à l'horizon.
    heures/heure_depart/pas_h : tirage dans la même heure de la journée (bougies 4 h)."""
    rng = np.random.default_rng(graine)
    n = len(ratios)
    if heures is not None and heure_depart is not None and pas_h:
        creneaux = {hh: np.flatnonzero(heures == hh) for hh in np.unique(heures)}
        if creneaux and min(len(v) for v in creneaux.values()) >= PAR_CRENEAU_MIN:
            idx = np.empty((tirages, horizon), dtype=int)
            for j in range(horizon):
                hh = (heure_depart + pas_h * (j + 1)) % 24
                pool = creneaux.get(hh)
                if pool is None:
                    pool = np.arange(n)
                idx[:, j] = pool[rng.integers(0, len(pool), tirages)]
        else:
            idx = rng.integers(0, n, (tirages, horizon))
    else:
        idx = rng.integers(0, n, (tirages, horizon))
    r = ratios[idx]                                   # (tirages, horizon, 4)
    cl = prix * np.cumprod(r[:, :, 3], axis=1)
    avant = np.column_stack([np.full(tirages, prix), cl[:, :-1]])
    hi, lo = avant * r[:, :, 1], avant * r[:, :, 2]
    if sens > 0:
        touche_stop = lo <= stop
        touche_obj = hi >= objectif if objectif is not None else np.zeros_like(touche_stop)
    else:
        touche_stop = hi >= stop
        touche_obj = lo <= objectif if objectif is not None else np.zeros_like(touche_stop)
    inf = horizon + 1
    t_stop = np.where(touche_stop.any(axis=1), touche_stop.argmax(axis=1), inf)
    t_obj = np.where(touche_obj.any(axis=1), touche_obj.argmax(axis=1), inf)
    stop_d = (t_stop <= t_obj) & (t_stop < inf)       # même bougie : on compte le stop
    obj_d = (t_obj < t_stop)
    fin = cl[:, -1]
    return {"p_stop": float(stop_d.mean()), "p_objectif": float(obj_d.mean()),
            "p_aucun": float(1 - stop_d.mean() - obj_d.mean()),
            "p_gain_fin": float(((obj_d) | (~stop_d & ((fin - prix) * sens > 0))).mean()),
            "prix_p5": float(np.percentile(fin, 5)), "prix_median": float(np.median(fin)),
            "prix_p95": float(np.percentile(fin, 95))}


def verdict(p_obj, p_stop, r_obj):
    """Même logique que le skill : parmi les tirages qui touchent un côté, l'objectif doit gagner au moins
    1 fois sur (1 + R) pour être à l'équilibre (50 % à 1 R, 33 % à 2 R)."""
    if r_obj is None or p_obj + p_stop < 0.05:
        return "Le prix touche rarement le stop ou l'objectif d'ici là : c'est le prix à l'horizon qui décidera."
    part = p_obj / (p_obj + p_stop)
    equilibre = 1 / (1 + r_obj)
    ecart = (part - equilibre) * 100
    if abs(ecart) < 5:
        return "Proche de l'équilibre (pile ou face pondéré par le gain visé) : aucun avantage visible."
    cote = "l'objectif" if ecart > 0 else "le stop"
    return f"{'Penche' if abs(ecart) < 15 else 'Penche nettement'} vers {cote} ({part * 100:.0f} % des cas tranchés, équilibre {equilibre * 100:.0f} %)."


def _graine(*morceaux) -> int:
    return int(hashlib.sha1("|".join(map(str, morceaux)).encode()).hexdigest()[:8], 16)


def _mid(b, k):
    return (b[k]["bid"] + b[k]["ask"]) / 2


def pour_position(p: dict, bougies: list, unite: str) -> dict | None:
    """Simulation d'une position de data.json (sens, prix_entree, stop, objectif) avec les bougies Capital.com
    déjà lues pendant le tour. La bougie en cours ne sert qu'au prix de départ, jamais au paquet."""
    if not bougies or len(bougies) < POOL_MIN + 2 or p.get("stop") is None or p.get("prix_entree") is None:
        return None
    sens = 1 if p.get("sens") == "BUY" else -1
    faites = bougies[:-1][-POOL_MAX:]
    o, h, l, c = ([_mid(b, k) for b in faites] for k in ("openPrice", "highPrice", "lowPrice", "closePrice"))
    temps = pd.to_datetime([b["snapshotTimeUTC"] for b in faites], utc=True)
    heures = temps.hour.values if unite == "HOUR_4" else None
    ratios, hr = paquet(o, h, l, c, heures)
    if len(ratios) < POOL_MIN:
        return None
    prix = _mid(bougies[-1], "closePrice")
    entree, stop = float(p["prix_entree"]), float(p["stop"])
    if (prix - stop) * sens <= 0:  # déjà au-delà du stop (le courtier va fermer)
        return None
    risque = (entree - stop) * sens  # > 0 si le stop est encore du côté de la perte
    objectif, r_obj, quoi = p.get("objectif"), None, None
    if objectif is not None:
        objectif = float(objectif)
        quoi = "TP"
        r_obj = (objectif - entree) * sens / risque if risque > 0 else None
    elif risque > 0:
        objectif = entree + OBJECTIF_R * risque * sens
        r_obj, quoi = OBJECTIF_R, f"gain de {OBJECTIF_R:g} R"
    if objectif is not None and (objectif - prix) * sens <= 0:
        objectif, r_obj, quoi = None, None, None  # déjà dépassé
    horizon = HORIZON.get(unite, 30)
    debut = pd.Timestamp(bougies[-1]["snapshotTimeUTC"], tz="UTC")
    graine = _graine(p.get("id"), bougies[-1]["snapshotTimeUTC"])  # stable pendant une bougie (pas de clignotement)
    res = simuler(ratios, prix, sens, stop, objectif, horizon, graine=graine, heures=hr,
                  heure_depart=int(debut.hour) if hr is not None else None, pas_h=4 if hr is not None else None)
    d = 5 if abs(prix) < 10 else 2
    sortie = {k: (round(v * 100, 1) if k.startswith("p_") else round(v, d)) for k, v in res.items()}
    sortie.update({"objectif": round(objectif, d) if objectif is not None else None, "objectif_type": quoi,
                   "objectif_r": round(r_obj, 2) if r_obj is not None else None,
                   "stop_en_gain": risque <= 0, "horizon": TEXTE_HORIZON.get(unite, f"{horizon} bougies"),
                   "tirages": TIRAGES, "bougies_utilisees": int(len(ratios)), "prix_depart": round(prix, d),
                   "calcule_sur": bougies[-1]["snapshotTimeUTC"],
                   "verdict": (verdict(res["p_objectif"], res["p_stop"], r_obj) if objectif is not None else
                               "Le stop protège déjà un gain : seule compte la chance qu'il soit touché d'ici là.")})
    return sortie


def unite_de(p: dict, strategies_usine: list) -> str:
    if p.get("strategie") == "rapide":
        return "MINUTE_5"
    if p.get("strategie") == "usine":
        for s in strategies_usine:
            if s["epic"] == p.get("marche"):
                return s["unite"]
    return "HOUR_4"


def publier(donnees: dict, cache: dict, strategies_usine: list) -> dict:
    """Écrit donnees["simulations"] = {id de position: résultat}. Jamais bloquant."""
    sims = {}
    for p in donnees.get("positions", []):
        try:
            u = unite_de(p, strategies_usine)
            s = pour_position(p, cache.get((p.get("marche"), u)) or [], u)
        except Exception as e:  # pragma: no cover - une erreur ici ne doit jamais gêner le bot
            print(f"Simulation non calculée pour {p.get('marche')} : {e}")
            s = None
        if s and not any(isinstance(v, float) and math.isnan(v) for v in s.values()):
            sims[p["id"]] = s
    donnees["simulations"] = sims
    return sims

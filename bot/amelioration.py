"""AUTO-AMÉLIORATION HEBDOMADAIRE (demandée par Mathis le 24/11/2026).

Chaque semaine (dimanche soir), le bot :
  1. fait le bilan de SES VRAIS TRADES de la semaine, stratégie par stratégie, et le compare à la semaine d'avant ;
  2. VÉRIFIE le changement adopté la semaine précédente : sur la semaine qui vient de passer (des prix qu'il
     n'avait jamais vus au moment du choix), le nouveau réglage a-t-il fait mieux que l'ancien ?
     Si non, il REVIENT EN ARRIÈRE tout seul et n'essaiera plus cette valeur pendant 4 semaines ;
  3. CHERCHE une nouvelle amélioration : pour chaque stratégie, il essaie de petites variantes de ses réglages
     (un seul réglage, d'un seul cran) sur l'historique récent des prix Capital.com, avec le spread et les frais.
     Il ne garde une variante que si elle bat le réglage actuel sur les DEUX moitiés de la période (sinon c'est
     de la chance), d'au moins GAIN_MIN_R, avec assez de trades et une pire baisse qui ne se dégrade pas ;
  4. écrit tout dans le Journal de l'appli et dans docs/amelioration.json.

Au plus UN changement par stratégie et par semaine, pour savoir exactement ce qui a marché ou non.

Ce qu'il ne touche JAMAIS : le risque par trade, les garde-fous (-50 %, -15 %/jour, positions max, risque total,
pause annonces), les marchés, l'empilement. Les valeurs déjà testées et rejetées (TP serrés, stops suiveurs serrés,
filtres RSI/ATR) sont hors des bornes.

Mode (reglages.env) : AUTO_AMELIORATION = "auto" (applique), "suggestions" (propose sans rien changer) ou "non".
Avant AUTO_AMELIORATION_DEBUT, le mode « auto » se comporte en « suggestions » (pour ne pas fausser le bilan du test).

Les résultats sont comptés en R : 1 R = la perte prévue si le stop est touché (1 % du capital). +3 R = trois fois
le risque d'un trade gagné. Ça permet de comparer les réglages quel que soit le capital.

Lancement : python -m bot.amelioration calculer   (GitHub Actions, avec les clés Capital.com)
            python -m bot.amelioration appliquer   (écrit reglages.env, data.json, amelioration.json)
"""
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from backtest.moteur import Conditions, executer
from bot.cassure import signaux_cassure
from bot.strategie import adx, ema, milieu, signaux_tendance

RACINE = Path(__file__).resolve().parent.parent
FICHIER_REGLAGES = RACINE / "reglages.env"
FICHIER_DONNEES = RACINE / "docs" / "data.json"
FICHIER_ETAT = RACINE / "docs" / "amelioration.json"
FICHIER_PLAN = RACINE / "amelioration_plan.json"  # résultat du calcul, lu par « appliquer » (non versionné)

CAPITAL_VIRTUEL = 10_000.0  # capital du backtest : assez grand pour que la taille minimale ne fausse rien
RISQUE_R_PCT = 1.0          # 1 R = 1 % du capital virtuel
GAIN_MIN_R = 1.0            # amélioration minimale sur la période pour adopter un changement
TRADES_MIN = 8              # en dessous, pas assez de trades pour conclure : on ne change rien
DD_TOLERANCE_R = 1.0        # la pire baisse (en R) ne doit pas s'aggraver de plus que ça
RECUL_MIN_R = 0.25          # retour en arrière si le nouveau réglage fait au moins 0,25 R de moins sur la semaine
INTERDIT_SEMAINES = 4       # une valeur annulée n'est plus essayée pendant 4 semaines

# Réglages que l'auto-amélioration a le droit de bouger, avec leurs valeurs permises (dans l'ordre des crans).
# Bornes choisies pour ne JAMAIS reproposer ce qui a été testé et rejeté (TP serrés, stops suiveurs serrés).
REGLAGES = {
    "tendance_4h": {
        "ADX_TENDANCE_MIN": [15, 18, 20, 22, 25, 28, 30],          # force minimale de la tendance
        "SUIVI_TENDANCE_ATR": [4, 4.5, 5, 5.5, 6, 7],              # stop suiveur (jamais plus serré que 4 ATR)
        "TP_PARTIEL_ATR": [1, 1.5, 2, 2.5, 3, 0],                 # TP de la 1re moitié (0 = pas de TP)
    },
    "cassure_4h": {
        "CASSURE_ENTREE": [15, 20, 25, 30, 40, 55],                # cassure des N dernières bougies
        "CASSURE_SORTIE": [10, 15, 20, 25],                         # sortie sur N bougies
    },
    "rapide": {
        "ADX_RAPIDE_MIN": [15, 20, 25, 30],                         # force minimale (bougies 5 min)
        "FILTRE_BOLLINGER": ["oui", "non"],                         # n'entrer que si le marché s'agite
        "SUIVI_RAPIDE_PCT": [2, 2.5, 3, 4],                         # stop suiveur (jamais plus serré que 2 %)
    },
}
DEFAUTS = {"ADX_TENDANCE_MIN": 20, "SUIVI_TENDANCE_ATR": 5, "TP_PARTIEL_ATR": 1, "CASSURE_ENTREE": 20,
           "CASSURE_SORTIE": 20, "ADX_RAPIDE_MIN": 20, "FILTRE_BOLLINGER": "oui", "SUIVI_RAPIDE_PCT": 2}
NOMS = {"tendance_4h": "Tendance 4 h", "cassure_4h": "Cassure 4 h", "rapide": "Rapide 5 min"}
EXPLICATIONS = {
    "ADX_TENDANCE_MIN": "force minimale de la tendance (ADX)", "SUIVI_TENDANCE_ATR": "stop suiveur (en ATR)",
    "TP_PARTIEL_ATR": "TP de la 1re moitié (en ATR, 0 = aucun)", "CASSURE_ENTREE": "bougies de la cassure d'entrée",
    "CASSURE_SORTIE": "bougies du canal de sortie", "ADX_RAPIDE_MIN": "force minimale de la tendance 5 min (ADX)",
    "FILTRE_BOLLINGER": "filtre des bandes de Bollinger", "SUIVI_RAPIDE_PCT": "stop suiveur (en %)",
}
# Garde-fous : l'auto-amélioration refuse d'écrire ces clés, quoi qu'il arrive.
INTOUCHABLES = {"PERTE_MAX_PCT", "PERTE_JOUR_PCT", "POSITIONS_MAX", "RISQUE_TOTAL_PCT", "RISQUE_PCT",
                "RISQUE_CASSURE_PCT", "RISQUE_RAPIDE_PCT", "PAUSE_ANNONCES", "MARCHES", "CASSURE_MARCHES",
                "RAPIDE_MARCHES", "EMPILER_MAX", "EMPILER_RAPIDE", "RAPIDE"}
assert not INTOUCHABLES & {c for r in REGLAGES.values() for c in r}


# --- reglages.env --------------------------------------------------------------------------------
def lire_reglages(texte: str) -> dict:
    out = {}
    for ligne in texte.splitlines():
        m = re.match(r'\s*([A-Z_][A-Z0-9_]*)="([^"]*)"', ligne)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def ecrire_reglage(texte: str, cle: str, valeur) -> str:
    """Remplace la valeur de CLE="..." en gardant le commentaire de la ligne (ou ajoute la ligne à la fin)."""
    if cle in INTOUCHABLES:
        raise ValueError(f"{cle} est un garde-fou : l'auto-amélioration n'a pas le droit d'y toucher")
    valeur = format_valeur(valeur)
    motif = re.compile(rf'^(\s*{cle}=)"[^"]*"', re.M)
    if motif.search(texte):
        return motif.sub(lambda m: f'{m.group(1)}"{valeur}"', texte, count=1)
    return texte.rstrip("\n") + f'\n{cle}="{valeur}"\n'


def format_valeur(v) -> str:
    if isinstance(v, str):
        return v
    return f"{float(v):g}"


def valeur(reglages: dict, cle: str):
    brut = reglages.get(cle, DEFAUTS[cle])
    if isinstance(DEFAUTS[cle], str):
        return str(brut).strip().lower()
    return float(brut)


def parametres(reglages: dict, strategie: str) -> dict:
    return {cle: valeur(reglages, cle) for cle in REGLAGES[strategie]}


def mode_effectif(reglages: dict, aujourdhui: datetime) -> str:
    mode = reglages.get("AUTO_AMELIORATION", "suggestions").strip().lower()
    if mode not in ("auto", "suggestions", "non"):
        mode = "suggestions"
    debut = reglages.get("AUTO_AMELIORATION_DEBUT", "").strip()
    if mode == "auto" and debut and aujourdhui.strftime("%Y-%m-%d") < debut:
        return "suggestions"
    return mode


# --- Variantes ----------------------------------------------------------------------------------
def voisins(cle: str, actuel) -> list:
    """Les valeurs à un cran de la valeur actuelle (une seule modification à la fois)."""
    permis = REGLAGES_PAR_CLE[cle]
    if actuel in permis:
        i = permis.index(actuel)
        return [permis[j] for j in (i - 1, i + 1) if 0 <= j < len(permis)]
    # valeur hors liste (réglée à la main) : on propose les deux valeurs permises les plus proches
    if isinstance(actuel, str):
        return [v for v in permis if v != actuel][:1]
    nums = sorted((v for v in permis if isinstance(v, (int, float)) and v), key=lambda v: abs(v - actuel))
    return nums[:2]


REGLAGES_PAR_CLE = {c: v for r in REGLAGES.values() for c, v in r.items()}


def variantes(strategie: str, actuels: dict, interdits: dict, aujourdhui: str) -> list[tuple[str, object]]:
    out = []
    for cle, v in actuels.items():
        for n in voisins(cle, v):
            if interdits.get(f"{strategie}.{cle}={format_valeur(n)}", "") > aujourdhui:
                continue
            out.append((cle, n))
    return out


# --- Backtests (mêmes règles que le bot en direct) -------------------------------------------------
def _signaux_avec_suivi(sig: pd.DataFrame, suivi) -> pd.DataFrame:
    sig = sig.copy()
    sig["suivi"] = suivi
    return sig


def trades_tendance(df: pd.DataFrame, p: dict, cond: Conditions) -> pd.DataFrame:
    """Tendance 4 h : deux moitiés (l'une avec TP à TP_PARTIEL_ATR × ATR, l'autre sans), comme le bot."""
    sig = signaux_tendance(df, adx_min=p["ADX_TENDANCE_MIN"], suivi_atr=p["SUIVI_TENDANCE_ATR"])
    tp = p["TP_PARTIEL_ATR"]
    if tp and tp > 0:
        avec_tp = signaux_tendance(df, adx_min=p["ADX_TENDANCE_MIN"], suivi_atr=p["SUIVI_TENDANCE_ATR"], objectif_atr=tp)
        morceaux = [executer(df, avec_tp, CAPITAL_VIRTUEL, RISQUE_R_PCT / 2, cond).trades,
                    executer(df, sig, CAPITAL_VIRTUEL, RISQUE_R_PCT / 2, cond).trades]
        return pd.concat([m for m in morceaux if len(m)] or [morceaux[0]], ignore_index=True)
    return executer(df, sig, CAPITAL_VIRTUEL, RISQUE_R_PCT, cond).trades


def trades_cassure(df: pd.DataFrame, p: dict, cond: Conditions) -> pd.DataFrame:
    sig = signaux_cassure(df, entree=int(p["CASSURE_ENTREE"]), sortie=int(p["CASSURE_SORTIE"]))
    return executer(df, sig, CAPITAL_VIRTUEL, RISQUE_R_PCT, cond).trades


def _tendance_alignee(df_sup: pd.DataFrame, rapide: int, lente: int, duree: pd.Timedelta,
                      quand: pd.DatetimeIndex) -> np.ndarray:
    """Sens (+1/-1/0) de la tendance d'une unité supérieure, connu à chaque instant `quand`
    (seules les bougies TERMINÉES comptent, comme dans le bot)."""
    m = milieu(df_sup)
    r, l = ema(m.close, rapide), ema(m.close, lente)
    sens = pd.Series(np.where(r > l, 1, np.where(r < l, -1, 0)), index=m.index + duree)
    sens[l.isna().values] = 0
    return sens.reindex(quand, method="ffill").fillna(0).astype(int).values


def signaux_rapide(df5: pd.DataFrame, df1h: pd.DataFrame, df4h: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Rapide 5 min, vectorisée pour le backtest : EMA 9/50 dans le sens des tendances 1 h (EMA 50/200)
    et 4 h (EMA 20/200), entrée seulement si Bollinger s'élargit (option) et ADX > ADX_RAPIDE_MIN.
    Une position est gardée tant que les trois sens restent d'accord. Stop 1 %, suiveur SUIVI_RAPIDE_PCT %."""
    m = milieu(df5)
    fin = df5.index + pd.Timedelta(minutes=5)  # instant où la bougie 5 min est terminée
    s5 = np.sign((ema(m.close, 9) - ema(m.close, 50)).fillna(0).values).astype(int)
    t1 = _tendance_alignee(df1h, 50, 200, pd.Timedelta(hours=1), fin)
    t4 = _tendance_alignee(df4h, 20, 200, pd.Timedelta(hours=4), fin)
    voulu = np.where((s5 == t1) & (s5 == t4), s5, 0)
    largeur = 4 * m.close.rolling(20).std() / m.close.rolling(20).mean()
    bb = (largeur / largeur.rolling(100).median()).values
    force = adx(m).values
    avec_bb = p["FILTRE_BOLLINGER"] == "oui"
    adx_min = p["ADX_RAPIDE_MIN"]
    cible = np.zeros(len(m), dtype=int)
    etat = 0
    for i in range(len(m)):
        if etat and etat != voulu[i]:
            etat = 0
        if not etat and voulu[i]:
            ok_bb = (not avec_bb) or (bb[i] == bb[i] and bb[i] > 1)
            ok_adx = adx_min <= 0 or (force[i] == force[i] and force[i] > adx_min)
            if ok_bb and ok_adx:
                etat = int(voulu[i])
        cible[i] = etat
    suivi = p["SUIVI_RAPIDE_PCT"]
    out = pd.DataFrame({"cible": cible, "stop": m.close * 0.01,
                        "suivi": m.close * max(suivi, 1.0) / 100 if suivi > 0 else np.nan}, index=df5.index)
    out.attrs["entree_nouvelle"] = False  # le bot rentre de nouveau dès que les filtres le permettent
    return out


def trades_rapide(donnees: dict, p: dict, cond: Conditions) -> pd.DataFrame:
    df5, df1h, df4h = donnees["MINUTE_5"], donnees["HOUR"], donnees["HOUR_4"]
    return executer(df5, signaux_rapide(df5, df1h, df4h, p), CAPITAL_VIRTUEL, RISQUE_R_PCT, cond).trades


# --- Mesure et décision -------------------------------------------------------------------------
def mesurer(trades: pd.DataFrame, debut: pd.Timestamp, fin: pd.Timestamp, milieu_: pd.Timestamp) -> dict:
    """Score en R des trades ouverts dans [debut, fin), et sur chacune des deux moitiés."""
    un_r = CAPITAL_VIRTUEL * RISQUE_R_PCT / 100
    t = trades[(trades.entree_le >= debut) & (trades.entree_le < fin)].sort_values("entree_le") if len(trades) else trades
    r = (t.pnl_eur / un_r).values.astype(float) if len(t) else np.array([])
    m1 = (t.entree_le < milieu_).values if len(t) else np.array([], dtype=bool)
    courbe = np.concatenate([[0.0], np.cumsum(r)])
    pire = float((courbe - np.maximum.accumulate(courbe)).min())
    return {"R": round(float(r.sum()), 2), "trades": int(len(r)),
            "R_1": round(float(r[m1].sum()), 2),
            "R_2": round(float(r[~m1].sum()), 2),
            "pire_baisse_R": round(pire, 2),
            "reussite_pct": round(float((r > 0).mean() * 100), 1) if len(r) else 0.0}


def meilleure_variante(base: dict, essais: list[dict]) -> dict | None:
    """Garde la variante qui bat le réglage actuel sur les DEUX moitiés, d'au moins GAIN_MIN_R au total,
    avec assez de trades et sans aggraver la pire baisse. None si aucune ne passe."""
    valables = []
    for e in essais:
        s = e["score"]
        if s["trades"] < TRADES_MIN or base["trades"] < TRADES_MIN // 2:
            continue
        if s["R"] - base["R"] < GAIN_MIN_R:
            continue
        if s["R_1"] < base["R_1"] or s["R_2"] < base["R_2"]:
            continue
        if s["pire_baisse_R"] < base["pire_baisse_R"] - DD_TOLERANCE_R:
            continue
        valables.append(e)
    return max(valables, key=lambda e: e["score"]["R"]) if valables else None


def faut_il_annuler(score_nouveau: dict, score_ancien: dict) -> bool:
    """Vérification du changement de la semaine passée, sur la semaine qui vient de s'écouler."""
    return score_nouveau["R"] < score_ancien["R"] - RECUL_MIN_R


# --- Vrais trades de la semaine -------------------------------------------------------------------
def bilan_reel(ordres: list, debut: str, fin: str) -> dict:
    """Trades RÉELS fermés entre debut et fin, par stratégie : nombre, total en €, % gagnants."""
    out = {}
    for o in ordres:
        if o.get("statut") != "ferme" or not (debut <= (o.get("ferme_le") or "") < fin):
            continue
        s = out.setdefault(o.get("strategie", "?"), {"trades": 0, "total_eur": 0.0, "gagnants": 0})
        res = float(o.get("resultat") or 0)
        s["trades"] += 1
        s["total_eur"] = round(s["total_eur"] + res, 2)
        s["gagnants"] += res > 0
    return out


# --- Données Capital.com --------------------------------------------------------------------------
MINUTES = {"MINUTE_5": 5, "HOUR": 60, "HOUR_4": 240}


def telecharger(api, epic: str, unite: str, jours: float) -> pd.DataFrame:
    fin = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    debut_total = fin - timedelta(days=jours)
    pas = timedelta(minutes=MINUTES[unite] * 900)
    lignes, a, vides = {}, fin, 0
    while a > debut_total and vides < 4:
        de = max(a - pas, debut_total)
        try:
            prix = api._requete("GET", f"/prices/{epic}", params={
                "resolution": unite, "max": 1000, "from": de.strftime("%Y-%m-%dT%H:%M:%S"),
                "to": a.strftime("%Y-%m-%dT%H:%M:%S")}).get("prices", [])
        except Exception as e:  # trou de données (week-end, jour férié) : on continue
            print(f"  {epic} {unite} {de:%Y-%m-%d} : {e}")
            prix = []
        vides = vides + 1 if not prix else 0
        for b in prix:
            lignes[b["snapshotTimeUTC"]] = b
        a = de
        time.sleep(0.25)
    # la dernière bougie n'est peut-être pas terminée : on l'enlève
    bougies = [lignes[k] for k in sorted(lignes)][:-1]
    rows = [{"date": pd.Timestamp(b["snapshotTimeUTC"], tz="UTC"),
             **{f"{n}_{c}": b[k][c] for k, n in (("openPrice", "open"), ("highPrice", "high"),
                                                 ("lowPrice", "low"), ("closePrice", "close")) for c in ("bid", "ask")}}
            for b in bougies]
    df = pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()
    print(f"  {epic} {unite} : {len(df)} bougies")
    return df


def conditions_marche(api, epic: str, eurusd: float, prix: float) -> Conditions:
    c = Conditions(taille_min=0.0, pas_taille=1e-6, eurusd=eurusd, prime_stop_garanti_pct=0.1)
    try:
        m = api.marche(epic)
        r, inst = m.get("dealingRules", {}), m.get("instrument", {})
        g = r.get("minGuaranteedStopDistance", {})
        if g.get("unit") == "PERCENTAGE":
            c.stop_garanti_min_pct = float(g["value"])
        elif g.get("value"):
            c.stop_garanti_min_pct = float(g["value"]) / prix * 100
        of = inst.get("overnightFee", {})
        c.frais_nuit_achat_pct = -float(of.get("longRate", -0.02))
        c.frais_nuit_vente_pct = -float(of.get("shortRate", -0.02))
        if inst.get("marginFactor") and inst.get("marginFactorUnit") == "PERCENTAGE":
            c.marge = float(inst["marginFactor"]) / 100
        if inst.get("currency") == "EUR":
            c.eurusd = 1.0
    except Exception as e:
        print(f"  {epic} : conditions par défaut ({e})")
    c.marge = min(c.marge, 0.05)  # capital virtuel : la marge ne doit pas limiter la taille dans le test
    return c


# --- Calcul complet ---------------------------------------------------------------------------------
JOURS_4H = 365      # période de test des stratégies 4 h
JOURS_RAPIDE = 56   # période de test de la rapide (8 semaines de bougies 5 min)
CHAUFFE_4H = 60     # jours en plus pour que l'EMA 200 en 4 h soit fiable


def evaluer(strategie: str, donnees_marches: dict, p: dict, conds: dict, debut, fin, milieu_) -> dict:
    total = []
    for epic, d in donnees_marches.items():
        if strategie == "tendance_4h":
            total.append(trades_tendance(d["HOUR_4"], p, conds[epic]))
        elif strategie == "cassure_4h":
            total.append(trades_cassure(d["HOUR_4"], p, conds[epic]))
        else:
            total.append(trades_rapide(d, p, conds[epic]))
    total = [t for t in total if len(t)]
    trades = pd.concat(total, ignore_index=True) if total else pd.DataFrame(columns=["entree_le", "pnl_eur", "raison"])
    return mesurer(trades, debut, fin, milieu_)


def calculer(api, reglages: dict, etat: dict, maintenant: datetime) -> dict:
    """Fait tous les backtests et renvoie le PLAN (rien n'est encore écrit)."""
    eurusd = api.taux_eurusd()
    marches = {
        "tendance_4h": [m.strip() for m in reglages.get("MARCHES", "BTCUSD").split(",") if m.strip()],
        "cassure_4h": [m.strip() for m in reglages.get("CASSURE_MARCHES", "GOLD,SILVER").split(",") if m.strip()],
        "rapide": [m.strip() for m in reglages.get("RAPIDE_MARCHES", "GOLD").split(",") if m.strip()]
        if reglages.get("RAPIDE", "non").lower() in ("oui", "1", "true", "on") else [],
    }
    cache, conds = {}, {}

    def donnees(epic, unites_jours):
        for unite, jours in unites_jours:
            if (epic, unite) not in cache:
                cache[(epic, unite)] = telecharger(api, epic, unite, jours)
        return {u: cache[(epic, u)] for u, _ in unites_jours}

    aujourdhui = maintenant.strftime("%Y-%m-%d")
    fin = pd.Timestamp(maintenant)
    derniere = etat.get("en_observation", {})
    plan = {"date": maintenant.strftime("%Y-%m-%dT%H:%M:%SZ"), "strategies": {}}
    for strat, liste in marches.items():
        res = {"marches": liste, "actuels": {}, "base": None, "essais": [], "verification": None, "choix": None}
        plan["strategies"][strat] = res
        if not liste:
            res["note"] = "stratégie désactivée"
            continue
        try:
            if strat == "rapide":
                jours = JOURS_RAPIDE
                d = {e: donnees(e, [("MINUTE_5", jours + 2), ("HOUR", jours + 12), ("HOUR_4", jours + 45)]) for e in liste}
            else:
                jours = JOURS_4H
                d = {e: donnees(e, [("HOUR_4", jours + CHAUFFE_4H)]) for e in liste}
            d = {e: v for e, v in d.items() if all(len(x) > 250 for x in v.values())}
            if not d:
                res["note"] = "pas assez d'historique téléchargé"
                continue
            for e, v in d.items():
                if e not in conds:
                    unite = "MINUTE_5" if strat == "rapide" else "HOUR_4"
                    der = v[unite].iloc[-1]
                    conds[e] = conditions_marche(api, e, eurusd, float((der.close_bid + der.close_ask) / 2))
            debut = fin - pd.Timedelta(days=jours)
            milieu_ = debut + (fin - debut) / 2
            actuels = parametres(reglages, strat)
            res["actuels"] = actuels
            base = evaluer(strat, d, actuels, conds, debut, fin, milieu_)
            res["base"] = base

            # 1) Vérifier le changement de la semaine passée (sur les prix vus DEPUIS ce changement)
            obs = derniere.get(strat)
            if obs:
                depuis = pd.Timestamp(obs["date"])
                ancien = dict(actuels, **{obs["reglage"]: obs["avant"]})
                s_nouv = evaluer(strat, d, actuels, conds, depuis, fin, depuis)
                s_anc = evaluer(strat, d, ancien, conds, depuis, fin, depuis)
                res["verification"] = {**obs, "score_nouveau": s_nouv, "score_ancien": s_anc,
                                       "annuler": faut_il_annuler(s_nouv, s_anc)}
                if res["verification"]["annuler"]:
                    continue  # on revient en arrière cette semaine, sans chercher autre chose

            # 2) Chercher une amélioration (un seul réglage, d'un seul cran)
            for cle, v in variantes(strat, actuels, etat.get("interdits", {}), aujourdhui):
                p = dict(actuels, **{cle: v})
                res["essais"].append({"reglage": cle, "avant": actuels[cle], "apres": v,
                                      "score": evaluer(strat, d, p, conds, debut, fin, milieu_)})
            res["choix"] = meilleure_variante(base, res["essais"])
        except Exception as e:  # une stratégie en erreur ne bloque pas les autres
            res["note"] = f"erreur : {str(e)[:200]}"
    return plan


# --- Application du plan ----------------------------------------------------------------------------
def appliquer(plan: dict, reglages_texte: str, donnees: dict, etat: dict, maintenant: datetime) -> tuple[str, dict, dict]:
    """Écrit les décisions. Renvoie (nouveau reglages.env, data.json, amelioration.json)."""
    reglages = lire_reglages(reglages_texte)
    mode = mode_effectif(reglages, maintenant)
    quand = maintenant.strftime("%Y-%m-%dT%H:%M:%SZ")
    aujourdhui = maintenant.strftime("%Y-%m-%d")
    journal = donnees.setdefault("journal", [])
    etat.setdefault("historique", [])
    etat.setdefault("interdits", {})
    etat.setdefault("en_observation", {})
    etat.setdefault("semaines", [])

    def noter(texte, strat=None):
        ligne = {"date": quand, "type": "amelioration", "marche": "", "texte": texte}
        if strat:
            ligne["strategie"] = strat
        journal.append(ligne)

    # Bilan des vrais trades de la semaine, comparé à la semaine d'avant
    debut_sem = (maintenant - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    reel = bilan_reel(donnees.get("ordres", []), debut_sem, quand)
    avant = etat["semaines"][-1]["reel"] if etat["semaines"] else None
    morceaux = []
    for s in ("tendance_4h", "cassure_4h", "rapide"):
        r = reel.get(s, {"trades": 0, "total_eur": 0.0})
        texte = f"{NOMS[s]} {r['total_eur']:+.2f} € ({r['trades']} trade{'s' if r['trades'] > 1 else ''})"
        if avant is not None:
            a = avant.get(s, {"total_eur": 0.0})
            texte += f", semaine d'avant {a['total_eur']:+.2f} €"
        morceaux.append(texte)
    if mode != "non":
        noter("Bilan de la semaine (vrais trades) : " + " ; ".join(morceaux) + ".")
    etat["semaines"] = (etat["semaines"] + [{"date": quand, "reel": reel}])[-52:]

    if mode == "non":
        etat.update({"dernier_passage": quand, "mode": mode})
        return reglages_texte, donnees, etat

    texte = reglages_texte
    for strat, res in plan.get("strategies", {}).items():
        nom = NOMS.get(strat, strat)
        if res.get("note") and not res.get("base"):
            if res["note"] != "stratégie désactivée":
                noter(f"{nom} : pas d'analyse cette semaine ({res['note']}).", strat)
            continue
        base = res.get("base") or {}
        ver = res.get("verification")
        if ver:
            sn, sa = ver["score_nouveau"], ver["score_ancien"]
            cle, av, ap = ver["reglage"], ver["avant"], ver["apres"]
            explic = EXPLICATIONS.get(cle, cle)
            if ver["annuler"]:
                if mode == "auto" and valeur(reglages, cle) == ap:
                    texte = ecrire_reglage(texte, cle, av)
                    etat["interdits"][f"{strat}.{cle}={format_valeur(ap)}"] = \
                        (maintenant + timedelta(weeks=INTERDIT_SEMAINES)).strftime("%Y-%m-%d")
                    etat["historique"].append({"date": quand, "strategie": strat, "reglage": cle, "avant": ap,
                                               "apres": av, "statut": "annulé", "score": sn, "score_ancien": sa})
                    noter(f"{nom} : RETOUR EN ARRIÈRE. Le changement de la semaine dernière ({explic} "
                          f"{format_valeur(av)} → {format_valeur(ap)}) a fait moins bien sur les nouveaux prix "
                          f"({sn['R']:+.1f} R contre {sa['R']:+.1f} R avec l'ancien réglage). On remet "
                          f"{format_valeur(av)} et on n'essaiera plus {format_valeur(ap)} pendant {INTERDIT_SEMAINES} semaines.", strat)
                etat["en_observation"].pop(strat, None)
                continue
            noter(f"{nom} : le changement de la semaine dernière ({explic} {format_valeur(av)} → {format_valeur(ap)}) "
                  f"est CONFIRMÉ ({sn['R']:+.1f} R contre {sa['R']:+.1f} R avec l'ancien réglage sur la semaine).", strat)
            etat["historique"].append({"date": quand, "strategie": strat, "reglage": cle, "avant": av, "apres": ap,
                                       "statut": "confirmé", "score": sn, "score_ancien": sa})
            etat["en_observation"].pop(strat, None)

        choix = res.get("choix")
        resume = (f"réglages actuels : {base.get('R', 0):+.1f} R sur {base.get('trades', 0)} trades en backtest "
                  f"({base.get('R_1', 0):+.1f} R puis {base.get('R_2', 0):+.1f} R)")
        if not choix:
            raison = ("pas assez de trades pour conclure" if base.get("trades", 0) < TRADES_MIN // 2
                      else "aucune variante ne fait mieux sur les deux moitiés de la période")
            noter(f"{nom} : {len(res.get('essais', []))} variantes testées, on garde tout tel quel ({raison} ; {resume}).", strat)
            continue
        cle, av, ap, s = choix["reglage"], choix["avant"], choix["apres"], choix["score"]
        explic = EXPLICATIONS.get(cle, cle)
        detail = (f"{s['R']:+.1f} R contre {base['R']:+.1f} R ({s['R_1']:+.1f} / {s['R_2']:+.1f} R sur les deux moitiés, "
                  f"{s['trades']} trades)")
        if mode == "auto":
            texte = ecrire_reglage(texte, cle, ap)
            etat["en_observation"][strat] = {"date": quand, "reglage": cle, "avant": av, "apres": ap}
            etat["historique"].append({"date": quand, "strategie": strat, "reglage": cle, "avant": av, "apres": ap,
                                       "statut": "adopté", "score": s, "score_ancien": base})
            noter(f"{nom} : CHANGEMENT ADOPTÉ, {explic} {format_valeur(av)} → {format_valeur(ap)} : {detail}. "
                  "Il sera vérifié dimanche prochain et annulé s'il fait moins bien.", strat)
        else:
            etat["historique"].append({"date": quand, "strategie": strat, "reglage": cle, "avant": av, "apres": ap,
                                       "statut": "suggestion", "score": s, "score_ancien": base})
            noter(f"{nom} : SUGGESTION (rien n'est changé avant le {reglages.get('AUTO_AMELIORATION_DEBUT', '?')}), "
                  f"{explic} {format_valeur(av)} → {format_valeur(ap)} : {detail}.", strat)

    etat["historique"] = etat["historique"][-200:]
    etat["interdits"] = {k: v for k, v in etat["interdits"].items() if v > aujourdhui}
    etat.update({"dernier_passage": quand, "mode": mode, "plan": plan})
    donnees["amelioration"] = {"dernier_passage": quand, "mode": mode,
                               "debut_auto": reglages.get("AUTO_AMELIORATION_DEBUT", ""),
                               "en_observation": etat["en_observation"],
                               "historique": etat["historique"][-12:],
                               "reglages": {s: parametres(lire_reglages(texte), s) for s in REGLAGES}}
    return texte, donnees, etat


def _json_sur(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return str(o)


def principal(commande: str) -> int:
    maintenant = datetime.now(timezone.utc)
    etat = json.loads(FICHIER_ETAT.read_text(encoding="utf-8")) if FICHIER_ETAT.exists() else {}
    if commande == "calculer":
        reglages = lire_reglages(FICHIER_REGLAGES.read_text(encoding="utf-8"))
        if mode_effectif(reglages, maintenant) == "non":
            FICHIER_PLAN.write_text(json.dumps({"date": maintenant.isoformat(), "strategies": {}}))
            return 0
        dernier = etat.get("dernier_passage", "")
        if dernier and os.getenv("FORCER", "") != "oui" and \
                dernier > (maintenant - timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ"):
            print(f"Déjà fait cette semaine ({dernier}) : rien à faire.")
            return 0
        from bot.capital import CapitalDemo
        api = CapitalDemo(*(os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD")))
        api.connexion()
        try:
            plan = calculer(api, reglages, etat, maintenant)
        finally:
            api.deconnexion()
        FICHIER_PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1, default=_json_sur), encoding="utf-8")
        for s, r in plan["strategies"].items():
            print(s, json.dumps({k: r.get(k) for k in ("base", "choix", "verification", "note")}, default=_json_sur)[:600])
        return 0
    if commande == "appliquer":
        if not FICHIER_PLAN.exists():
            print("Pas de plan calculé : rien à appliquer.")
            return 0
        plan = json.loads(FICHIER_PLAN.read_text(encoding="utf-8"))
        donnees = json.loads(FICHIER_DONNEES.read_text(encoding="utf-8")) if FICHIER_DONNEES.exists() else {}
        texte, donnees, etat = appliquer(plan, FICHIER_REGLAGES.read_text(encoding="utf-8"), donnees, etat, maintenant)
        FICHIER_REGLAGES.write_text(texte, encoding="utf-8")
        FICHIER_DONNEES.write_text(json.dumps(donnees, ensure_ascii=False, indent=1, default=_json_sur), encoding="utf-8")
        FICHIER_ETAT.write_text(json.dumps(etat, ensure_ascii=False, indent=1, default=_json_sur), encoding="utf-8")
        return 0
    print("Usage : python -m bot.amelioration calculer|appliquer")
    return 2


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1] if len(sys.argv) > 1 else ""))

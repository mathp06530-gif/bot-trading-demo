"""GRAPHIQUES DE L'APPLI (26/11/2026, demande de Mathis : « voir tout ce que le bot analyse sur le graphique »).

Ce module ne passe AUCUN ordre et ne change AUCUNE décision : il relit les bougies déjà téléchargées pendant le
tour (aucun appel en plus à Capital.com) et recalcule, avec les MÊMES fonctions que les stratégies, les
indicateurs que chaque stratégie regarde. Il écrit un petit fichier par graphique dans docs/graphiques/ :
  - les bougies terminées (150 dernières) ;
  - les lignes d'indicateurs (EMA, canal de cassure, Bollinger, Supertrend, MACD, ADX…) ;
  - les signaux repérés par la stratégie (flèches) ;
  - la liste des conditions de la stratégie sur la dernière bougie terminée (remplie ou pas) ;
  - pour chaque trade, les conditions telles qu'elles étaient sur la bougie du signal.
Un fichier n'est réécrit que si son contenu change (une fois par bougie terminée), pour ne pas alourdir le dépôt.
La bougie en cours, elle, va dans data.json (« graph_live ») à chaque tour. Les lignes d'entrée, de stop et de TP
viennent des positions de data.json (les vrais niveaux chez Capital.com).

Capital.com ne permet pas, par son API, de dessiner sur ses propres graphiques : les stops et TP y sont visibles
(ce sont de vrais ordres attachés aux positions), mais les indicateurs et les flèches ne le sont que dans l'appli.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from bot import cassure as module_cassure
from bot import elan as module_elan
from bot import rapide as module_rapide
from bot import supertrend as module_supertrend
from bot import usine as module_usine
from bot import usine_regles as R
from bot.strategie import adx, bougies_vers_df, ema, milieu

DOSSIER = Path(__file__).resolve().parent.parent / "docs" / "graphiques"
N_AFFICHE = 150
DUREES = {"MINUTE": 60, "MINUTE_5": 300, "MINUTE_15": 900, "MINUTE_30": 1800, "HOUR": 3600, "HOUR_4": 14400,
          "DAY": 86400, "WEEK": 604800}
MOTS = {1: "hausse", -1: "baisse", 0: "aucun"}


def _dec(prix) -> int:
    return 5 if prix is not None and abs(prix) < 10 else 2


def _nombre(x, d):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else round(x, d)


def _liste(valeurs, d, n=N_AFFICHE):
    return [_nombre(v, d) for v in list(valeurs)[-n:]]


def _fx(x, d):
    return f"{x:.{d}f}".replace(".", ",") if x is not None and not (isinstance(x, float) and math.isnan(x)) else "?"


def _secondes(index) -> list[int]:
    return [int(pd.Timestamp(t).timestamp()) for t in index]


def _cond(texte: str, ok) -> dict:
    return {"texte": texte, "ok": None if ok is None else bool(ok)}


def _base(epic, unite, df, id_, strategie, titre, regle):
    m = milieu(df)
    d = _dec(float(m.close.iloc[-1]))
    return d, m, {
        "id": id_, "strategie": strategie, "marche": epic, "unite": unite, "titre": titre, "regle": regle,
        "decimales": d,
        "bougies": {"t": _secondes(m.index[-N_AFFICHE:]), "o": _liste(m.open, d), "h": _liste(m.high, d),
                    "l": _liste(m.low, d), "c": _liste(m.close, d)},
        "lignes": [], "oscillateur": None, "marqueurs": [], "conditions": [], "conditions_trades": {},
    }


def _marqueurs(g, index, sens, texte_achat, texte_vente):
    """Flèches des signaux de la stratégie (bougies affichées seulement)."""
    t = _secondes(index)
    debut = g["bougies"]["t"][0] if g["bougies"]["t"] else 0
    for i, s in enumerate(sens):
        if s and t[i] >= debut:
            g["marqueurs"].append({"t": t[i], "sens": "BUY" if s > 0 else "SELL",
                                   "texte": texte_achat if s > 0 else texte_vente})


def _index_signal(index, unite, quand: str):
    """Position de la dernière bougie TERMINÉE au moment `quand` (celle sur laquelle le bot a décidé)."""
    try:
        t = pd.Timestamp(quand)
        t = t.tz_localize("UTC") if t.tzinfo is None else t
    except (ValueError, TypeError):
        return None
    fin = pd.Series(index, dtype="datetime64[ns, UTC]") + pd.Timedelta(seconds=DUREES.get(unite, 0))
    ok = np.flatnonzero((fin <= t + pd.Timedelta(seconds=90)).values)
    return int(ok[-1]) if len(ok) else None


def _trades(g, donnees, strategie, epic, index, unite, conditions):
    for o in donnees.get("ordres", []):
        if o.get("strategie") != strategie or o.get("marche") != epic or not o.get("ouvert_le"):
            continue
        i = _index_signal(index, unite, o["ouvert_le"])
        if i is None or i < 1:
            continue
        try:
            g["conditions_trades"][o["id"]] = conditions(i, 1 if o.get("sens") == "BUY" else -1)
        except Exception:  # un trade trop ancien pour les bougies disponibles : on passe
            continue


# --- Une fonction par stratégie --------------------------------------------------------------------------------
def graph_cassure(epic, bougies, donnees):
    df = bougies_vers_df(bougies[:-1])
    if len(df) < 210:
        return None
    s = module_cassure.signaux_cassure(df)
    d, m, g = _base(epic, "HOUR_4", df, f"cassure_4h-{epic}", "cassure_4h", f"Cassure 4 h · {epic}",
                    module_cassure.NOM)
    n = module_cassure.ENTREE
    g["lignes"] = [
        {"nom": f"Plus haut {n} bougies", "couleur": "#16c784", "v": _liste(s.haut, d), "style": "tirets"},
        {"nom": f"Plus bas {n} bougies", "couleur": "#ea3943", "v": _liste(s.bas, d), "style": "tirets"},
        {"nom": f"EMA {module_cassure.FILTRE_EMA}", "couleur": "#f5a524", "v": _liste(s.ema, d)},
    ]
    nouveau = np.r_[0, np.diff(s.cible.values)]
    entrees = np.where((nouveau != 0) & (s.cible.values != 0), s.cible.values, 0)
    _marqueurs(g, df.index, entrees, "Cassure du plus haut", "Cassure du plus bas")

    def conditions(i, sens=None):
        c, hh, ll, e, a = (float(s[k].iat[i]) for k in ("cloture", "haut", "bas", "ema", "atr"))
        sens = sens or (1 if c > e else -1)
        if sens > 0:
            return [_cond(f"Prix au-dessus de l'EMA 200 ({_fx(c, d)} > {_fx(e, d)}) : tendance haussière", c > e),
                    _cond(f"Clôture au-dessus du plus haut des {n} bougies ({_fx(c, d)} > {_fx(hh, d)})", c > hh),
                    _cond(f"Stop garanti à 2 ATR ({_fx(2 * a, d)})", True)]
        return [_cond(f"Prix sous l'EMA 200 ({_fx(c, d)} < {_fx(e, d)}) : tendance baissière", c < e),
                _cond(f"Clôture sous le plus bas des {n} bougies ({_fx(c, d)} < {_fx(ll, d)})", c < ll),
                _cond(f"Stop garanti à 2 ATR ({_fx(2 * a, d)})", True)]

    g["conditions"] = conditions(len(df) - 1)
    _trades(g, donnees, "cassure_4h", epic, df.index, "HOUR_4", conditions)
    return g


def graph_elan(epic, bougies, donnees):
    df = bougies_vers_df(bougies[:-1])
    if len(df) < 210:
        return None
    s = module_elan.signaux_elan(df)
    d, m, g = _base(epic, "HOUR_4", df, f"elan_4h-{epic}", "elan_4h", f"Élan 4 h · {epic}", module_elan.NOM)
    g["lignes"] = [{"nom": "EMA 200", "couleur": "#f5a524", "v": _liste(s.ema, d)}]
    _marqueurs(g, df.index, s.sig.values, "Trou haussier (gros acheteur)", "Trou baissier (gros vendeur)")
    k = module_elan.TROU_MIN_ATR

    def conditions(i, sens=None):
        c, e, a = float(s.cloture.iat[i]), float(s.ema.iat[i]), float(s.atr.iat[i])
        sens = sens or (1 if c > e else -1)
        if sens > 0:
            trou = float(m.low.iat[i] - m.high.iat[i - 2]) if i >= 2 else float("nan")
            return [_cond(f"Trou haussier entre 3 bougies : {_fx(trou / a, 2)} ATR (il faut > {k:g})", trou > k * a),
                    _cond(f"Prix au-dessus de l'EMA 200 ({_fx(c, d)} > {_fx(e, d)})", c > e),
                    _cond(f"Objectif (TP) à {module_elan.OBJECTIF_ELAN_R:g} fois le stop", True)]
        trou = float(m.low.iat[i - 2] - m.high.iat[i]) if i >= 2 else float("nan")
        return [_cond(f"Trou baissier entre 3 bougies : {_fx(trou / a, 2)} ATR (il faut > {k:g})", trou > k * a),
                _cond(f"Prix sous l'EMA 200 ({_fx(c, d)} < {_fx(e, d)})", c < e),
                _cond(f"Objectif (TP) à {module_elan.OBJECTIF_ELAN_R:g} fois le stop", True)]

    g["conditions"] = conditions(len(df) - 1)
    _trades(g, donnees, "elan_4h", epic, df.index, "HOUR_4", conditions)
    return g


def graph_supertrend(epic, bougies, donnees):
    df = bougies_vers_df(bougies[:-1])
    if len(df) < 50:
        return None
    s = module_supertrend.signaux_supertrend(df)
    d, m, g = _base(epic, "HOUR_4", df, f"supertrend_4h-{epic}", "supertrend_4h", f"Supertrend 4 h · {epic}",
                    module_supertrend.NOM)
    haut = np.where(s.sens.values == 1, s.ligne.values, np.nan)
    bas = np.where(s.sens.values == -1, s.ligne.values, np.nan)
    g["lignes"] = [{"nom": "Supertrend (hausse)", "couleur": "#16c784", "v": _liste(haut, d)},
                   {"nom": "Supertrend (baisse)", "couleur": "#ea3943", "v": _liste(bas, d)}]
    flips = np.where(s.nouveau.values, s.sens.values, 0)
    flips[0] = 0
    _marqueurs(g, df.index, flips, "Retournement à la hausse", "Retournement à la baisse")

    def conditions(i, sens=None):
        c, ligne, sns = float(s.cloture.iat[i]), float(s.ligne.iat[i]), int(s.sens.iat[i])
        sens = sens or sns
        mot = "au-dessus" if sens > 0 else "sous"
        return [_cond(f"Prix {mot} de la ligne Supertrend ({_fx(c, d)} / {_fx(ligne, d)})", sns == sens),
                _cond("Retournement sur cette bougie (signal nouveau)", bool(s.nouveau.iat[i]) and sns == sens),
                _cond(f"Stop garanti juste derrière la ligne ({_fx(float(s.dist.iat[i]), d)})", True)]

    g["conditions"] = conditions(len(df) - 1)
    _trades(g, donnees, "supertrend_4h", epic, df.index, "HOUR_4", conditions)
    return g


def _sens_prefixe(cache, epic, unite, rapide, lente, avant: int):
    """Sens EMA rapide/lente sur les bougies terminées avant l'instant `avant` (en secondes)."""
    bs = cache.get((epic, unite)) or []
    duree = DUREES[unite]
    cl = [(b["closePrice"]["bid"] + b["closePrice"]["ask"]) / 2 for b in bs
          if pd.Timestamp(b["snapshotTimeUTC"], tz="UTC").timestamp() + duree <= avant]
    if len(cl) < lente:
        return None
    return module_rapide.sens_ema(cl, rapide, lente)


def graph_rapide(epic, bougies, donnees, cache):
    df = bougies_vers_df(bougies[:-1])
    if len(df) < 130:
        return None
    clotures = list(milieu(df).close)
    d, m, g = _base(epic, "MINUTE_5", df, f"rapide-{epic}", "rapide", f"Rapide 5 min · {epic}", module_rapide.NOM)
    r, l = ema(clotures, module_rapide.EMA_R), ema(clotures, module_rapide.EMA_L)
    mil, et = m.close.rolling(20).mean(), m.close.rolling(20).std()
    force = adx(m)
    g["lignes"] = [
        {"nom": f"EMA {module_rapide.EMA_R}", "couleur": "#22d3ee", "v": _liste(r, d)},
        {"nom": f"EMA {module_rapide.EMA_L}", "couleur": "#8b5cf6", "v": _liste(l, d)},
        {"nom": "Bollinger haute", "couleur": "rgba(139,151,173,.55)", "v": _liste(mil + 2 * et, d), "style": "points"},
        {"nom": "Bollinger basse", "couleur": "rgba(139,151,173,.55)", "v": _liste(mil - 2 * et, d), "style": "points"},
    ]
    g["oscillateur"] = {"nom": "ADX (force de la tendance)", "seuil": module_rapide.ADX_RAPIDE_MIN or None,
                        "lignes": [{"nom": "ADX", "couleur": "#f5a524", "v": _liste(force, 1)}]}
    sens = np.array([0 if a is None or b is None else (1 if a > b else -1) for a, b in zip(r, l)])
    croise = np.r_[0, np.where(np.diff(sens) != 0, sens[1:], 0)]
    croise[sens == 0] = 0
    _marqueurs(g, df.index, croise, f"EMA {module_rapide.EMA_R} passe au-dessus", f"EMA {module_rapide.EMA_R} passe dessous")
    t = _secondes(df.index)

    def conditions(i, voulu=None):
        a, b = r[i], l[i]
        if a is None or b is None:
            return []
        s5 = 1 if a > b else -1
        voulu = voulu or s5
        mot = MOTS[voulu]
        decision = t[i] + 300  # le bot décide une fois la bougie 5 min terminée
        t1 = _sens_prefixe(cache, epic, "HOUR", 50, 200, decision)
        t4 = _sens_prefixe(cache, epic, "HOUR_4", 20, 200, decision)
        v = "BUY" if voulu > 0 else "SELL"
        sortie = [_cond(f"5 min : EMA {module_rapide.EMA_R} {'au-dessus' if voulu > 0 else 'sous'} de l'EMA "
                        f"{module_rapide.EMA_L} ({_fx(a, d)} / {_fx(b, d)})", s5 == voulu),
                  _cond(f"Tendance 1 h (EMA 50/200) en {mot}" + ("" if t1 else " (inconnue)"), None if t1 is None else t1 == v),
                  _cond(f"Tendance 4 h (EMA 20/200) en {mot}" + ("" if t4 else " (inconnue)"), None if t4 is None else t4 == v)]
        if module_rapide.FILTRE_BOLLINGER:
            bb = module_rapide.bollinger_relatif(clotures[:i + 1])
            sortie.append(_cond(f"Bandes de Bollinger qui s'élargissent (largeur relative {_fx(bb, 2)} > 1)",
                                None if bb is None else bb > 1))
        if module_rapide.ADX_RAPIDE_MIN > 0:
            x = float(force.iat[i])
            sortie.append(_cond(f"ADX 5 min {_fx(x, 0)} > {module_rapide.ADX_RAPIDE_MIN:g} (tendance assez forte)",
                                x > module_rapide.ADX_RAPIDE_MIN))
        sortie.append(_cond(f"Stop garanti à {module_rapide.STOP_PCT:g} % du prix", True))
        return sortie

    g["conditions"] = conditions(len(df) - 1)
    _trades(g, donnees, "rapide", epic, df.index, "MINUTE_5", conditions)
    return g


def graph_usine(strat, bougies, donnees):
    epic, unite, spec = strat["epic"], strat["unite"], strat["spec"]
    df = bougies_vers_df(bougies[:-1])
    if len(df) < 300:
        return None
    ind = R.Indicateurs(df)
    voulu, ok, dstop, dobj = R.preparer(ind, spec)
    d, m, g = _base(epic, unite, df, f"usine-{epic}", "usine", f"Usine · {epic}", strat.get("texte", R.decrire(spec)))
    c = ind.c
    if spec["famille"] == "macd":
        a, b, sg = spec["p"]
        ligne = c.ewm(span=a, adjust=False).mean() - c.ewm(span=b, adjust=False).mean()
        signal = ligne.ewm(span=sg, adjust=False).mean()
        g["oscillateur"] = {"nom": f"MACD {a}/{b}/{sg}", "seuil": None,
                            "lignes": [{"nom": "MACD", "couleur": "#22d3ee", "v": _liste(ligne, d + 1)},
                                       {"nom": "Signal", "couleur": "#f5a524", "v": _liste(signal, d + 1)}],
                            "histo": _liste(ligne - signal, d + 1)}
    if spec["filtre"] == "t200":
        g["lignes"].append({"nom": "Moyenne 200", "couleur": "#f5a524", "v": _liste(ind.sma200, d)})
    _marqueurs(g, df.index, np.where(ok, voulu, 0), "Signal d'achat (usine)", "Signal de vente (usine)")
    nom_f = R.NOMS_FAMILLES.get(spec["famille"], spec["famille"])

    def conditions(i, sens=None):
        v = int(voulu[i])
        sens = sens or v or 1
        sortie = []
        if spec["famille"] == "macd":
            x, y = float(ligne.iat[i]), float(signal.iat[i])
            sortie.append(_cond(f"MACD {'au-dessus' if sens > 0 else 'sous'} de sa ligne de signal "
                                f"({_fx(x, d + 1)} / {_fx(y, d + 1)})", v == sens))
        else:
            sortie.append(_cond(f"{nom_f} : signal en {MOTS[sens]}", v == sens))
        nouveau = i > 0 and int(voulu[i - 1]) != v and v != 0
        sortie.append(_cond("Signal nouveau sur cette bougie", nouveau and v == sens))
        f = spec["filtre"]
        if f == "adx20m":
            x = float(ind.adx.iat[i])
            sortie.append(_cond(f"Marché calme : ADX {_fx(x, 0)} < 20", x < 20))
        elif f == "adx25":
            x = float(ind.adx.iat[i])
            sortie.append(_cond(f"Tendance forte : ADX {_fx(x, 0)} > 25", x > 25))
        elif f in ("volh", "volb"):
            x = float(ind.atr.iat[i] / ind.atr100.iat[i])
            sortie.append(_cond(f"Volatilité {'en hausse' if f == 'volh' else 'en baisse'} (ATR 14 / ATR 100 = "
                                f"{_fx(x, 2)} {'>' if f == 'volh' else '<'} 1)", x > 1 if f == "volh" else x < 1))
        elif f == "t200":
            x, s200 = float(c.iat[i]), float(ind.sma200.iat[i])
            sortie.append(_cond(f"Dans le sens de la moyenne 200 ({_fx(x, d)} / {_fx(s200, d)})",
                                x > s200 if sens > 0 else x < s200))
        sortie.append(_cond(f"Stop garanti à {spec['stop']:g} ATR"
                            + (f", objectif (TP) à {spec['objectif']:g} R" if spec.get("objectif") else ", sans TP"), True))
        return sortie

    g["conditions"] = conditions(len(df) - 1)
    _trades(g, donnees, "usine", epic, df.index, unite, conditions)
    return g


# --- Assemblage ------------------------------------------------------------------------------------------------
def construire(donnees: dict, cache: dict) -> list[dict]:
    """Tous les graphiques possibles avec les bougies vues pendant ce tour (une erreur n'en bloque aucun autre)."""
    a_faire = []
    for epic in module_cassure.LISTE:
        a_faire.append(lambda e=epic: graph_cassure(e, cache.get((e, "HOUR_4")) or [], donnees))
    for epic in module_rapide.LISTE:
        a_faire.append(lambda e=epic: graph_rapide(e, cache.get((e, "MINUTE_5")) or [], donnees, cache))
    for epic in module_elan.LISTE:
        a_faire.append(lambda e=epic: graph_elan(e, cache.get((e, "HOUR_4")) or [], donnees))
    for epic in module_supertrend.LISTE:
        a_faire.append(lambda e=epic: graph_supertrend(e, cache.get((e, "HOUR_4")) or [], donnees))
    for strat in module_usine.STRATEGIES:
        a_faire.append(lambda s=strat: graph_usine(s, cache.get((s["epic"], s["unite"])) or [], donnees))
    graphs = []
    for f in a_faire:
        try:
            g = f()
        except Exception as e:  # jamais bloquant pour le bot
            print(f"Graphique non calculé : {e}")
            continue
        if g:
            graphs.append(g)
    return graphs


def attendus() -> list[tuple]:
    """(id, stratégie, marché, unité, titre) de chaque graphique, d'après les réglages."""
    sortie = [(f"cassure_4h-{e}", "cassure_4h", e, "HOUR_4", f"Cassure 4 h · {e}") for e in module_cassure.LISTE]
    sortie += [(f"rapide-{e}", "rapide", e, "MINUTE_5", f"Rapide 5 min · {e}") for e in module_rapide.LISTE]
    sortie += [(f"elan_4h-{e}", "elan_4h", e, "HOUR_4", f"Élan 4 h · {e}") for e in module_elan.LISTE]
    sortie += [(f"supertrend_4h-{e}", "supertrend_4h", e, "HOUR_4", f"Supertrend 4 h · {e}")
               for e in module_supertrend.LISTE]
    sortie += [(f"usine-{s['epic']}", "usine", s["epic"], s["unite"], f"Usine · {s['epic']}")
               for s in module_usine.STRATEGIES]
    return sortie


def _ecrire_si_change(chemin: Path, contenu: dict) -> bool:
    texte = json.dumps(contenu, ensure_ascii=False, separators=(",", ":"))
    if chemin.exists() and chemin.read_text(encoding="utf-8") == texte:
        return False
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte, encoding="utf-8")
    return True


def publier(donnees: dict, cache: dict, dossier: Path | None = None) -> list[str]:
    """Écrit docs/graphiques/*.json (seulement ceux qui changent) et la bougie en cours dans donnees["graph_live"]."""
    dossier = dossier or DOSSIER
    graphs = construire(donnees, cache)
    ecrits = []
    live = {}
    for g in graphs:
        if _ecrire_si_change(dossier / f"{g['id']}.json", g):
            ecrits.append(g["id"])
        bs = cache.get((g["marche"], g["unite"])) or []
        if bs:
            b, d = bs[-1], g["decimales"]
            mid = lambda k: _nombre((b[k]["bid"] + b[k]["ask"]) / 2, d)
            live[g["id"]] = [int(pd.Timestamp(b["snapshotTimeUTC"], tz="UTC").timestamp()),
                             mid("openPrice"), mid("highPrice"), mid("lowPrice"), mid("closePrice")]
    # Liste des graphiques prévus par les réglages. Un graphique pas recalculé à ce tour (stratégie en pause…)
    # garde son dernier fichier ; seuls ceux d'une stratégie retirée des réglages sont effacés.
    prevus = attendus()
    liste = [{"id": i, "strategie": s, "marche": m, "unite": u, "titre": t} for i, s, m, u, t in prevus
             if (dossier / f"{i}.json").exists()]
    _ecrire_si_change(dossier / "index.json", {"graphiques": liste})
    for vieux in dossier.glob("*.json"):
        if vieux.stem != "index" and vieux.stem not in {p[0] for p in prevus}:
            vieux.unlink()
    donnees["graph_live"] = live
    return ecrits

"""SOUS-BOTS ACTIONS ET ETF : un sous-bot par marché, tous avec la même stratégie.

Stratégie « Note technique 4 h » (achat seulement), testée sur 2 ans de prix Capital.com :
  ANALYSE  : à chaque bougie de 4 h terminée, le sous-bot calcule la NOTE TECHNIQUE du marché
             (bot/analyse.py : ~20 indicateurs qui votent, de -1 à +1).
  ACHAT    : seulement si la note est un « achat fort » (≥ +0,5) ET le prix est au-dessus de
             l'EMA 200 (tendance de fond haussière). Jamais de vente à découvert sur les actions.
  REFUS    : marché fermé, signal de plus d'une bougie, signal déjà utilisé, spread > 10 % du stop,
             prix qui a sauté de plus d'1 ATR depuis le signal, ou n'importe quel GARDE-FOU
             (bot/garde_fous.py : coupe-circuit, perte du jour, positions max, risque total).
  SL       : stop GARANTI à 2 × ATR, ou plus si Capital.com impose un minimum (ex. 7,5 % sur Tesla).
  TP       : la moitié de la position a un TP à 2 × ATR (on encaisse), l'autre moitié n'en a pas.
  SUIVEUR  : le stop remonte à 5 × ATR sous le prix à chaque bougie, il ne redescend jamais.
  SORTIE   : quand la note repasse sous 0 (l'analyse ne confirme plus la hausse).
  TAILLE   : RISQUE_SOUS_BOT_PCT (0,5 %) du capital perdu au maximum par trade.

Résultat du backtest (examen = 2e année jamais vue, 10 marchés, 0,5 % de risque) : environ +3 %,
5 marchés gagnants sur 10. C'est faible et incertain : une EXPÉRIENCE en démo, pas une promesse.
"""
import math
import os

from bot.registre import noter_fermeture
from bot.strategie import bougies_vers_df, signaux_note

ACTIONS = ["TSLA", "NVDA", "AAPL", "MSFT", "GOOGL"]
ETF = ["SPY", "QQQ", "GLD", "XLK", "IWM"]
LISTE = [m.strip() for m in os.getenv("SOUS_BOTS", ",".join(ACTIONS + ETF)).split(",") if m.strip()]
RISQUE_SOUS_BOT_PCT = float(os.getenv("RISQUE_SOUS_BOT_PCT", "0.5"))
TP_ATR = 2.0
UNITE = "HOUR_4"
NOM = "Note technique 4 h (achat seulement), SL garanti 2 ATR, TP 2 ATR sur la moitié, suiveur 5 ATR"


def regles_marche(api, epic: str, cache: dict) -> dict:
    if epic not in cache:
        m = api.marche(epic)
        r = m.get("dealingRules", {})
        g = r.get("minGuaranteedStopDistance", {})
        cache[epic] = {
            "statut": m.get("snapshot", {}).get("marketStatus", "TRADEABLE"),
            "taille_min": float(r.get("minDealSize", {}).get("value", 1)),
            "pas": float(r.get("minSizeIncrement", {}).get("value", r.get("minDealSize", {}).get("value", 1))),
            "stop_min_pct": float(g["value"]) if g.get("unit") == "PERCENTAGE" else None,
            "stop_min_points": float(g["value"]) if g.get("value") and g.get("unit") != "PERCENTAGE" else None,
            "marge": float(m.get("instrument", {}).get("marginFactor", 20)) / 100,
            "nom": m.get("instrument", {}).get("name", epic),
            "devise": m.get("instrument", {}).get("currency", "USD"),
        }
    return cache[epic]


def tour_sous_bot(api, donnees: dict, epic: str, positions: list, capital: float, disponible: float, eurusd: float,
                  noter, garde, quand: str, peut_entrer: bool = True) -> dict:
    etat = donnees.setdefault("sous_bots", {}).setdefault(epic, {})
    regles = regles_marche(api, epic, donnees.setdefault("_cache_marches", {}))
    etat["nom"] = regles["nom"]
    miennes = [p for p in positions if p["market"]["epic"] == epic]

    bougies = api.bougies(epic, UNITE, 1000)
    if len(bougies) < 230:
        etat.update({"action": "Pas assez d'historique", "note": None})
        return etat
    df = bougies_vers_df(bougies[:-1])
    sig = signaux_note(df, ventes=False)
    der = sig.iloc[-1]
    c = sig.cible.values
    voulu = "BUY" if c[-1] == 1 else None
    j = len(c) - 1
    while j > 0 and c[j - 1] == c[-1]:
        j -= 1
    debut = str(sig.index[j])
    prix_achat, prix_vente = bougies[-1]["closePrice"]["ask"], bougies[-1]["closePrice"]["bid"]
    etat.update({"note": round(float(der.note), 2), "tendance": voulu, "prix": (prix_achat + prix_vente) / 2})
    action = "Aucune action"

    # 1) Sortie : l'analyse ne confirme plus la hausse
    if voulu is None:
        for p in miennes:
            conf = api.fermer(p["position"]["dealId"])
            if conf.get("dealStatus") == "ACCEPTED":
                noter_fermeture(donnees, p, conf, quand, "Note technique repassée sous 0")
            noter("fermeture", epic, f"Note technique {der.note:+.2f} : la hausse n'est plus confirmée, position fermée "
                  f"(gain/perte : {p['position'].get('upl', 0):.2f}).")
            action = "Position fermée"
        miennes = []

    # 2) Stop suiveur
    for p in miennes:
        pos = p["position"]
        mini = prix_vente * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
        cible_stop = min(float(der.cloture - der.suivi), prix_vente - mini * 1.05)
        if pos.get("stopLevel") is None or cible_stop > float(pos["stopLevel"]) + 0.01:
            conf = api.modifier_stop(pos["dealId"], cible_stop, True)
            if conf.get("dealStatus") == "ACCEPTED":
                noter("stop", epic, f"Stop suiveur remonté à {cible_stop:.2f}.")
                action = "Stop remonté"
        if action == "Aucune action":
            action = "Position conservée"

    # 3) Entrée, avec toutes les vérifications
    entrees = donnees.setdefault("entrees", {})
    if voulu and not miennes and peut_entrer:
        refus = None
        if regles["statut"] != "TRADEABLE":
            refus = "marché fermé"
        elif j < len(c) - 2:
            refus = f"signal trop ancien (depuis le {debut[:16]})"
        elif entrees.get(epic) == debut:
            refus = "signal déjà utilisé"
        elif abs(prix_achat - float(der.cloture)) > float(der.atr):
            refus = "le prix a trop bougé depuis le signal (écart > 1 ATR)"
        distance = float(der.stop)
        mini = prix_achat * (regles["stop_min_pct"] or 0) / 100 or (regles["stop_min_points"] or 0)
        distance = max(distance, mini * 1.05)
        if not refus and (prix_achat - prix_vente) > distance * 0.10:
            refus = "spread trop cher par rapport au stop"
        risque_eur = capital * RISQUE_SOUS_BOT_PCT / 100
        pas = regles["pas"]
        taille = math.floor(risque_eur * eurusd / distance / pas) * pas
        taille_marge = math.floor(disponible * eurusd / (prix_achat * regles["marge"]) * 0.5 / pas) * pas
        taille = round(min(taille, taille_marge), 6)
        if not refus and taille < regles["taille_min"]:
            refus = f"capital trop faible pour la taille minimale ({regles['taille_min']})"
        if not refus:
            ok, raison = garde.autoriser(taille * distance / eurusd, distance)
            refus = None if ok else raison
        if refus:
            if etat.get("dernier_refus") != refus:
                noter("analyse", epic, f"Note {der.note:+.2f} (achat fort) mais ordre REFUSÉ : {refus}.")
            etat["dernier_refus"] = refus
            action = f"Refusé : {refus}"
        else:
            moitie = round(math.floor(taille / 2 / pas) * pas, 6)
            parts = [(moitie, float(der.atr) * TP_ATR), (round(taille - moitie, 6), None)] if moitie >= regles["taille_min"] \
                else [(taille, None)]
            for t, obj in parts:
                conf = api.ouvrir(epic, "BUY", t, prix=prix_achat, stop_distance=distance, garanti=True,
                                  objectif_distance=obj)
                if conf.get("dealStatus") == "ACCEPTED":
                    entrees[epic] = debut
                    garde.enregistrer({"position": {"level": prix_achat, "stopLevel": prix_achat - distance, "size": t}})
                    noter("ordre", epic, f"Note technique {der.note:+.2f} (achat fort), prix au-dessus de l'EMA 200 : "
                          f"ACHAT de {t} à {float(conf.get('level') or prix_achat):.2f}, stop garanti à -{distance:.2f}"
                          + (f", TP à +{obj:.2f}" if obj else ", sans TP (stop suiveur)") + ".")
                    action = f"ACHAT de {taille}"
                else:
                    noter("erreur", epic, f"Ordre refusé par Capital.com : {conf.get('reason', conf.get('dealStatus'))}")
            etat.pop("dernier_refus", None)
    elif voulu and not peut_entrer and not miennes:
        action = "Désactivé"
    etat["action"] = action
    return etat

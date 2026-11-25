"""Moteur de backtest réaliste pour un CFD Capital.com.

- Achat au prix ASK, vente au prix BID : le spread réel est payé à chaque trade.
- Ordres exécutés à l'ouverture de la bougie SUIVANT le signal (pas de triche sur le futur).
- Stop garanti : sortie exactement au niveau du stop, prime payée si le stop est touché.
- Frais de nuit (financement) prélevés chaque jour à 22 h UTC tant qu'une position est ouverte.
- Taille calculée pour risquer un % fixe du capital, arrondie au pas du courtier,
  et limitée par la marge disponible (levier crypto UE = 2:1).
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Conditions:
    taille_min: float = 0.01          # BTC
    pas_taille: float = 0.01
    marge: float = 0.5                # 50 % de marge = levier 2:1
    stop_garanti_min_pct: float = 1.0  # distance mini du stop garanti, en % du prix
    prime_stop_garanti_pct: float = 0.0  # prime payée si le stop garanti est touché, en % de la valeur
    frais_nuit_achat_pct: float = 0.0616  # % de la valeur par nuit (coût)
    frais_nuit_vente_pct: float = 0.0616
    eurusd: float = 1.08


@dataclass
class Resultat:
    capital_initial: float
    courbe: pd.Series
    trades: pd.DataFrame
    refus: int = 0
    infos: dict = field(default_factory=dict)

    def stats(self) -> dict:
        c = self.courbe
        t = self.trades
        final = float(c.iloc[-1])
        pic = c.cummax()
        dd = float(((c - pic) / pic).min() * 100)
        jours = max((c.index[-1] - c.index[0]).total_seconds() / 86400, 1)
        mensuel = c.resample("ME").last()
        rend_mois = mensuel.pct_change().dropna() * 100
        gagnants = t[t.pnl_eur > 0] if len(t) else t
        perdants = t[t.pnl_eur <= 0] if len(t) else t
        pf = (gagnants.pnl_eur.sum() / -perdants.pnl_eur.sum()) if len(perdants) and perdants.pnl_eur.sum() < 0 else np.nan
        return {
            "final": round(final, 2),
            "gain_eur": round(final - self.capital_initial, 2),
            "gain_pct": round((final / self.capital_initial - 1) * 100, 2),
            "par_3_mois_pct": round(((final / self.capital_initial) ** (91 / jours) - 1) * 100, 2) if final > 0 else -100,
            "drawdown_max_pct": round(dd, 2),
            "trades": int(len(t)),
            "reussite_pct": round(len(gagnants) / len(t) * 100, 1) if len(t) else 0,
            "profit_factor": round(float(pf), 2) if pf == pf else None,
            "frais_eur": round(float(t.frais_eur.sum()), 2) if len(t) else 0,
            "mois_positifs": f"{int((rend_mois > 0).sum())}/{len(rend_mois)}",
            "refus_taille": self.refus,
            "jours": round(jours),
        }


def executer(df: pd.DataFrame, signaux: pd.DataFrame, capital: float, risque_pct: float,
             cond: Conditions, levier_max: float | None = None, taille_fixe: float | None = None) -> Resultat:
    """df : bougies (open_bid, open_ask, high_bid, ..., close_ask) indexées par date UTC.
    signaux : colonnes 'cible' (1 achat, -1 vente, 0 rien), 'stop' (distance en prix),
              'objectif' (distance en prix ou NaN), 'suivi' (distance du stop suiveur ou NaN)."""
    ob, oa = df.open_bid.values, df.open_ask.values
    hb, ha = df.high_bid.values, df.high_ask.values
    lb, la = df.low_bid.values, df.low_ask.values
    cb, ca = df.close_bid.values, df.close_ask.values
    dates = df.index
    cible = signaux.cible.values
    dstop = signaux.stop.values
    dobj = signaux.objectif.values if "objectif" in signaux else np.full(len(df), np.nan)
    dsuivi = signaux.suivi.values if "suivi" in signaux else np.full(len(df), np.nan)
    entree_nouvelle = bool(signaux.attrs.get("entree_nouvelle", True))
    garde = signaux.attrs.get("garde")  # (seuil en R, part du gain gardée) : stop qui se resserre après un gain

    eq = capital
    courbe = np.empty(len(df))
    pos = 0
    taille = entree = stop = obj = 0.0
    dist0 = meilleur = 0.0
    frais_trade = 0.0
    date_entree = None
    trades = []
    refus = 0

    def fermer(i, prix, raison, prime=0.0):
        nonlocal eq, pos, frais_trade
        pnl_usd = (prix - entree) * taille * pos
        frais = prime + frais_trade
        pnl = pnl_usd / cond.eurusd - frais
        eq += pnl_usd / cond.eurusd - prime
        trades.append({"entree_le": date_entree, "sortie_le": dates[i], "sens": "ACHAT" if pos > 0 else "VENTE",
                       "taille": taille, "prix_entree": entree, "prix_sortie": prix, "raison": raison,
                       "pnl_eur": pnl, "frais_eur": frais})
        pos = 0
        frais_trade = 0.0

    for i in range(len(df)):
        # 1) Ouverture de la bougie : on applique le signal de la bougie précédente
        if i > 0:
            c = cible[i - 1]
            if pos != 0 and c != pos:
                fermer(i, ob[i] if pos > 0 else oa[i], "signal")
            frais_signal = (not entree_nouvelle) or i < 2 or cible[i - 2] != c
            if pos == 0 and c != 0 and frais_signal and eq > 0 and dstop[i - 1] == dstop[i - 1]:
                prix = oa[i] if c > 0 else ob[i]
                dist = max(dstop[i - 1], prix * cond.stop_garanti_min_pct / 100)
                risque_eur = eq * risque_pct / 100
                t = np.floor(risque_eur * cond.eurusd / dist / cond.pas_taille) * cond.pas_taille
                t_marge = np.floor(eq * cond.eurusd / (prix * cond.marge) / cond.pas_taille) * cond.pas_taille
                if levier_max:
                    t_marge = min(t_marge, np.floor(eq * cond.eurusd * levier_max / prix / cond.pas_taille) * cond.pas_taille)
                t = round(min(t, t_marge), 8)
                if taille_fixe:
                    t = taille_fixe if taille_fixe * prix * cond.marge <= eq * cond.eurusd else 0
                if t >= cond.taille_min:
                    pos, taille, entree = int(c), t, prix
                    dist0, meilleur = dist, prix
                    stop = prix - dist * pos
                    obj = prix + dobj[i - 1] * pos if dobj[i - 1] == dobj[i - 1] else np.nan
                    date_entree = dates[i]
                else:
                    refus += 1
        # 2) Pendant la bougie : stop garanti puis objectif (le stop est supposé touché en premier)
        if pos > 0:
            if lb[i] <= stop:
                fermer(i, stop, "stop",
                       taille * stop * cond.prime_stop_garanti_pct / 100 / cond.eurusd)
            elif obj == obj and hb[i] >= obj:
                fermer(i, max(obj, ob[i]), "objectif")
        elif pos < 0:
            if ha[i] >= stop:
                fermer(i, stop, "stop", taille * stop * cond.prime_stop_garanti_pct / 100 / cond.eurusd)
            elif obj == obj and la[i] <= obj:
                fermer(i, min(obj, oa[i]), "objectif")
        # 3) Clôture : frais de nuit à 22 h UTC, stop suiveur
        if pos != 0:
            if dates[i].hour == 22 and dates[i].minute == 0:
                taux = cond.frais_nuit_achat_pct if pos > 0 else cond.frais_nuit_vente_pct
                f = taille * (cb[i] + ca[i]) / 2 * taux / 100 / cond.eurusd
                eq -= f
                frais_trade += f
            if dsuivi[i] == dsuivi[i]:
                milieu = (cb[i] + ca[i]) / 2
                stop = max(stop, milieu - dsuivi[i]) if pos > 0 else min(stop, milieu + dsuivi[i])
            if garde:
                m = (cb[i] + ca[i]) / 2
                haut = (hb[i] + ha[i]) / 2 if pos > 0 else (lb[i] + la[i]) / 2
                meilleur = max(meilleur, haut) if pos > 0 else min(meilleur, haut)
                if (meilleur - entree) * pos >= garde[0] * dist0:
                    c_ = entree + garde[1] * (meilleur - entree)
                    lim = m - m * cond.stop_garanti_min_pct / 100 * pos
                    c_ = min(c_, lim) if pos > 0 else max(c_, lim)
                    stop = max(stop, c_) if pos > 0 else min(stop, c_)
        latent = ((cb[i] - entree) if pos > 0 else (entree - ca[i])) * taille / cond.eurusd if pos else 0.0
        courbe[i] = eq + latent
        if courbe[i] <= 0:
            courbe[i:] = 0
            eq = 0
            break

    if pos != 0:
        fermer(len(df) - 1, cb[-1] if pos > 0 else ca[-1], "fin du test")
        courbe[-1] = eq
    tr = pd.DataFrame(trades, columns=["entree_le", "sortie_le", "sens", "taille", "prix_entree", "prix_sortie",
                                       "raison", "pnl_eur", "frais_eur"])
    return Resultat(capital, pd.Series(courbe, index=dates), tr, refus)

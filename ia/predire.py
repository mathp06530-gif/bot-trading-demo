"""Système SÉPARÉ du bot : plusieurs IA qui prédisent la direction (hausse / baisse) des marchés.

Demande de Mathis du 26/11/2026. Ne passe AUCUN ordre, ne touche à aucune stratégie du bot.

IA mises en compétition (chacune réentraînée sur le passé seulement, puis jugée sur des bougies jamais vues) :
  logistique  régression logistique (repère simple)
  foret       forêt aléatoire
  lightgbm    gradient boosting LightGBM
  neurones    réseau de neurones (MLP)
  lstm        réseau LSTM qui lit les 32 dernières bougies dans l'ordre
  vote        moyenne des probabilités des 5 IA
  empilement  régression logistique qui apprend, sur une période de validation, à qui faire confiance

Test « walk-forward » : la 2e moitié de l'historique est découpée en 8 blocs ; pour chaque bloc, les IA sont
entraînées sur ce qui précède (au plus TRAIN_MAX bougies, avec un trou de H bougies pour ne rien voir du futur),
puis prédisent le bloc. On mesure :
  - la PRÉCISION (bonnes directions / prédictions) sur toutes les bougies, et quand l'IA est « sûre d'elle » ;
  - le GAIN après spread réel (achat au prix acheteur, vente au prix vendeur) et frais de nuit.
Le seuil de confiance est choisi sur la période de validation (jamais sur le bloc jugé).

Usage :
  python ia/predire.py telecharger <dossier> <EPIC>          (GitHub Actions, secrets Capital.com démo)
  python ia/predire.py tester <dossier> <EPIC> <UNITE> <sortie.json>
  python ia/predire.py bilan <dossier_resultats> <ia/RESULTATS.md> <ia/resultats.json>
"""
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

UNITES = {"MINUTE": (1, 365), "MINUTE_5": (5, 365), "MINUTE_15": (15, 700), "HOUR": (60, 1100), "HOUR_4": (240, 3650)}
HORIZONS = {"MINUTE": (1, 5), "MINUTE_5": (1, 12), "MINUTE_15": (1, 4), "HOUR": (1, 4), "HOUR_4": (1, 6)}
TRAIN_MAX = int(os.getenv("TRAIN_MAX", "60000"))
BLOCS = int(os.getenv("BLOCS", "8"))
SEQ = 32
MODELES = ["logistique", "foret", "lightgbm", "neurones", "lstm", "vote", "empilement"]
SEUILS = [0.0, 0.02, 0.05, 0.08, 0.12, 0.16]  # marge autour de 50 % : 0.05 = on n'agit que si p > 55 % ou p < 45 %


# --------------------------------------------------------------------------- données
def telecharger(dossier: Path, epic: str):
    from backtest import telecharger as t
    from bot.capital import CapitalDemo
    cle, ident, mdp = (os.getenv(n, "").strip() for n in ("CAPITAL_API_KEY", "CAPITAL_IDENTIFIER", "CAPITAL_PASSWORD"))
    api = CapitalDemo(cle, ident, mdp)
    api.connexion()
    dossier.mkdir(parents=True, exist_ok=True)
    t.DOSSIER = dossier
    (dossier / f"{epic}_marche.json").write_text(json.dumps(api.marche(epic), ensure_ascii=False))
    for unite, (minutes, jours) in UNITES.items():
        try:
            t.telecharger(api, epic, unite, minutes, jours)
        except Exception as e:
            print(f"{epic} {unite} : échec ({str(e)[:150]})")
        api.deconnexion()  # la session expire après 10 min : on la renouvelle entre deux unités
        time.sleep(1)
        api.connexion()
    api.deconnexion()


def lire(dossier: Path, epic: str, unite: str):
    f = dossier / f"{epic}_{unite}.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["date"] = pd.to_datetime(d.date, utc=True).dt.tz_localize(None)
    d = d.dropna(subset=["close_bid"]).set_index("date").sort_index()
    d = d[~d.index.duplicated()]
    ecart = (d.close_ask - d.close_bid).median()
    if not ecart == ecart:
        return None
    for x in ("open", "high", "low", "close"):
        d[f"{x}_ask"] = d[f"{x}_ask"].fillna(d[f"{x}_bid"] + ecart)
    return d.astype(float)


def frais_nuit(dossier: Path, epic: str):
    p = dossier / f"{epic}_marche.json"
    m = json.loads(p.read_text()) if p.exists() else {}
    nuit = m.get("instrument", {}).get("overnightFee", {})
    return -float(nuit.get("longRate", -0.02)) / 100, -float(nuit.get("shortRate", -0.02)) / 100


# --------------------------------------------------------------------------- indicateurs (passé seulement)
def indicateurs(d: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c = ((d[f"{k}_bid"] + d[f"{k}_ask"]) / 2 for k in ("open", "high", "low", "close"))
    lc = np.log(c)
    r1 = lc.diff()
    f = pd.DataFrame(index=d.index)
    vol50 = r1.rolling(50).std()
    for k in (1, 2, 3, 5, 10, 20, 50, 100):
        f[f"r{k}"] = (lc - lc.shift(k)) / (vol50 * math.sqrt(k))
    f["vol10"] = r1.rolling(10).std() / vol50
    f["vol50"] = vol50 / r1.rolling(500, min_periods=100).std()
    g = r1.clip(lower=0).ewm(alpha=1 / 14).mean()
    p = (-r1).clip(lower=0).ewm(alpha=1 / 14).mean()
    f["rsi"] = (100 - 100 / (1 + g / p.replace(0, np.nan))).fillna(50)
    for n in (20, 50, 200):
        f[f"ema{n}"] = (c / c.ewm(span=n).mean() - 1) / (vol50 * math.sqrt(n))
    e12, e26 = c.ewm(span=12).mean(), c.ewm(span=26).mean()
    m = e12 - e26
    f["macd"] = (m - m.ewm(span=9).mean()) / (c * vol50)
    for n in (20, 100):
        hh, ll = h.rolling(n).max(), l.rolling(n).min()
        f[f"pos{n}"] = ((c - ll) / (hh - ll).replace(0, np.nan)).where(hh.notna(), np.nan).fillna(0.5).where(hh.notna())
    ampl = (h - l).replace(0, np.nan)
    f["corps"] = ((c - o) / ampl).fillna(0)  # bougie plate (haut = bas) : fréquent en 1 min
    f["meche_h"] = ((h - np.maximum(o, c)) / ampl).fillna(0)
    f["meche_b"] = ((np.minimum(o, c) - l) / ampl).fillna(0)
    f["ampl"] = (h - l) / c / vol50
    v = d["volume"].replace(0, np.nan)
    f["volume"] = np.log(v / v.rolling(50, min_periods=1).mean()).fillna(0)
    f["spread"] = (d.close_ask - d.close_bid) / c / vol50
    heure = d.index.hour + d.index.minute / 60
    f["h_sin"], f["h_cos"] = np.sin(2 * np.pi * heure / 24), np.cos(2 * np.pi * heure / 24)
    f["jour"] = d.index.dayofweek
    return f.replace([np.inf, -np.inf], np.nan)


def sequences(d: pd.DataFrame) -> np.ndarray:
    """Pour le LSTM : 3 séries normalisées (rendement, amplitude, volume) sur les SEQ dernières bougies."""
    c = (d.close_bid + d.close_ask) / 2
    r = np.log(c).diff()
    s = r.rolling(200, min_periods=50).std()
    a = ((d.high_bid + d.high_ask) / 2 - (d.low_bid + d.low_ask) / 2) / c
    v = np.log(d.volume.replace(0, np.nan)).fillna(0)
    base = np.stack([(r / s).clip(-6, 6).fillna(0).values,
                     (a / s / 2).clip(0, 10).fillna(0).values,
                     ((v - v.rolling(200, min_periods=50).mean()) / (v.rolling(200, min_periods=50).std() + 1e-9))
                     .clip(-5, 5).fillna(0).values], axis=1).astype(np.float32)
    return base


# --------------------------------------------------------------------------- IA
def entrainer_lstm(Xs, y, graine=0):
    import torch
    torch.manual_seed(graine)
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    class Reseau(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = torch.nn.LSTM(3, 32, batch_first=True)
            self.sortie = torch.nn.Sequential(torch.nn.Dropout(0.2), torch.nn.Linear(32, 1))

        def forward(self, x):
            _, (hdn, _) = self.lstm(x)
            return self.sortie(hdn[-1]).squeeze(-1)

    net = Reseau()
    opt = torch.optim.Adam(net.parameters(), lr=2e-3)
    X = torch.from_numpy(Xs)
    Y = torch.from_numpy(y.astype(np.float32))
    perte = torch.nn.BCEWithLogitsLoss()
    for _ in range(3):
        ordre = torch.randperm(len(X))
        for i in range(0, len(X), 512):
            j = ordre[i:i + 512]
            opt.zero_grad()
            perte(net(X[j]), Y[j]).backward()
            opt.step()
    net.eval()

    def predire(Xn):
        with torch.no_grad():
            return torch.sigmoid(torch.cat([net(torch.from_numpy(Xn[i:i + 4096])) for i in range(0, len(Xn), 4096)])).numpy()
    return predire


def entrainer(X, Xs, y):
    from lightgbm import LGBMClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    mods = {
        "logistique": make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=500)),
        "foret": RandomForestClassifier(n_estimators=200, max_depth=8, min_samples_leaf=100, n_jobs=-1, random_state=0),
        "lightgbm": LGBMClassifier(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=200,
                                   subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0),
        "neurones": make_pipeline(StandardScaler(), MLPClassifier((64, 32), alpha=1e-3, early_stopping=True,
                                                                  max_iter=50, random_state=0)),
    }
    fonctions = {}
    for nom, m in mods.items():
        m.fit(X, y)
        fonctions[nom] = (lambda m: lambda Xn, Xsn: m.predict_proba(Xn)[:, 1])(m)
    try:
        f = entrainer_lstm(Xs, y)
        fonctions["lstm"] = lambda Xn, Xsn: f(Xsn)
    except Exception as e:  # LSTM indisponible : les autres IA continuent
        print(f"LSTM ignoré : {str(e)[:200]}")
    return fonctions


# --------------------------------------------------------------------------- gain réel d'une prédiction
def gains_trades(d, H, nuit_achat, nuit_vente):
    """Rendement net (en fraction) d'un achat et d'une vente ouverts à la clôture de la bougie i, fermés H bougies
    plus tard : achat au prix acheteur (ask), revente au prix vendeur (bid), et inversement ; frais de nuit compris."""
    mid = ((d.close_bid + d.close_ask) / 2).values
    ask, bid = d.close_ask.values, d.close_bid.values
    t = d.index.values.astype("datetime64[s]").astype(np.int64)
    n = len(d)
    achat, vente = np.full(n, np.nan), np.full(n, np.nan)
    achat[:n - H] = (bid[H:] - ask[:n - H]) / mid[:n - H]
    vente[:n - H] = (bid[:n - H] - ask[H:]) / mid[:n - H]
    jour = np.floor((t - 22 * 3600) / 86400)
    nuits = np.zeros(n)
    nuits[:n - H] = (jour[H:] - jour[:n - H]).clip(0, 7)
    achat -= nuits * nuit_achat
    vente -= nuits * nuit_vente
    return achat, vente


def evaluer(p, y, ga, gv, marge, H):
    """Précision et gain quand |p - 0.5| > marge. Pour H > 1, une décision toutes les H bougies (pas de
    chevauchement, sinon le même mouvement serait compté plusieurs fois)."""
    idx = np.arange(len(p))
    sel = (np.abs(p - 0.5) > marge) & ~np.isnan(ga) & (idx % H == 0)
    if sel.sum() == 0:
        return None
    sens = np.where(p[sel] > 0.5, 1, -1)
    gains = np.where(sens > 0, ga[sel], gv[sel])
    ok = ~np.isnan(y[sel])
    juste = ((sens[ok] > 0) == (y[sel][ok] > 0.5))
    return {"n": int(sel.sum()), "justes": int(juste.sum()), "jugees": int(ok.sum()), "gains": gains}


# --------------------------------------------------------------------------- test walk-forward
def tester(dossier: Path, epic: str, unite: str, sortie: Path):
    d = lire(dossier, epic, unite)
    res = {"epic": epic, "unite": unite}
    if d is None or len(d) < 3000:
        res["erreur"] = "pas assez de données"
        sortie.write_text(json.dumps(res))
        print(res)
        return
    nuit_a, nuit_v = frais_nuit(dossier, epic)
    F = indicateurs(d)
    S = sequences(d)
    mid = ((d.close_bid + d.close_ask) / 2).values
    res.update({"debut": str(d.index[0]), "fin": str(d.index[-1]), "bougies": len(d),
                "spread_pct": float(((d.close_ask - d.close_bid) / mid).median() * 100)})
    t0 = time.time()
    for H in HORIZONS[unite]:
        fut = np.full(len(d), np.nan)
        fut[:-H] = mid[H:] - mid[:-H]
        y = np.where(fut > 0, 1.0, np.where(fut < 0, 0.0, np.nan))  # égalités (prix inchangé) : non jugées
        ga, gv = gains_trades(d, H, nuit_a, nuit_v)
        valide = F.notna().all(axis=1).values & (np.arange(len(d)) >= SEQ + 200)
        n = len(d)
        debut_test = n // 2
        bornes = np.linspace(debut_test, n - H, BLOCS + 1).astype(int)
        collecte = {m: {"p": [], "y": [], "ga": [], "gv": [], "marge": [], "bloc": []} for m in MODELES}
        for b in range(BLOCS):
            a, z = bornes[b], bornes[b + 1]
            fin_train = a - H  # trou de H bougies : la cible de la dernière bougie d'entraînement est connue en a
            deb_train = max(0, fin_train - TRAIN_MAX)
            i_tr = np.arange(deb_train, fin_train)
            i_tr = i_tr[valide[i_tr] & ~np.isnan(y[i_tr])]
            coupe = int(len(i_tr) * 0.8)
            i_fit, i_val = i_tr[:coupe - H], i_tr[coupe:]
            i_te = np.arange(a, z)
            i_te = i_te[valide[i_te]]
            if len(i_fit) < 2000 or len(i_te) < 50:
                continue
            Xseq = lambda ii: np.stack([S[i - SEQ + 1:i + 1] for i in ii])  # noqa: E731
            fonctions = entrainer(F.values[i_fit], Xseq(i_fit), y[i_fit])
            Xv, Xsv, Xt, Xst = F.values[i_val], Xseq(i_val), F.values[i_te], Xseq(i_te)
            pv = {k: f(Xv, Xsv) for k, f in fonctions.items()}
            pt = {k: f(Xt, Xst) for k, f in fonctions.items()}
            base = list(fonctions)
            pv["vote"], pt["vote"] = np.mean([pv[k] for k in base], 0), np.mean([pt[k] for k in base], 0)
            from sklearn.linear_model import LogisticRegression
            empil = LogisticRegression(C=1.0).fit(np.column_stack([pv[k] for k in base]), y[i_val])
            pt["empilement"] = empil.predict_proba(np.column_stack([pt[k] for k in base]))[:, 1]
            # pour choisir la marge de l'empilement sans tricher : validation croisée en 2 sur la validation
            moit = len(i_val) // 2
            pe = np.empty(len(i_val))
            for x, w in ((slice(0, moit), slice(moit, None)), (slice(moit, None), slice(0, moit))):
                m2 = LogisticRegression(C=1.0).fit(np.column_stack([pv[k][x] for k in base]), y[i_val][x])
                pe[w] = m2.predict_proba(np.column_stack([pv[k][w] for k in base]))[:, 1]
            pv["empilement"] = pe
            for m in MODELES:
                if m not in pt:
                    continue
                # marge choisie sur la validation : la meilleure moyenne nette avec au moins 30 décisions
                meilleure, gain_max = None, 0.0
                for marge in SEUILS:
                    e = evaluer(pv[m], y[i_val], ga[i_val], gv[i_val], marge, H)
                    if e and e["n"] >= 30 and np.mean(e["gains"]) > gain_max:
                        meilleure, gain_max = marge, float(np.mean(e["gains"]))
                c = collecte[m]
                c["p"].append(pt[m]); c["y"].append(y[i_te]); c["ga"].append(ga[i_te]); c["gv"].append(gv[i_te])
                c["marge"].append(np.full(len(i_te), -1.0 if meilleure is None else meilleure))
                c["bloc"].append(np.full(len(i_te), b))
            print(f"{epic} {unite} H={H} bloc {b + 1}/{BLOCS} ({time.time() - t0:.0f} s)", flush=True)
        res[f"H{H}"] = resumer(collecte, H)
    res["duree_s"] = round(time.time() - t0)
    sortie.write_text(json.dumps(res, indent=1))


def resumer(collecte, H):
    out = {}
    for m, c in collecte.items():
        if not c["p"]:
            continue
        p, y, ga, gv = (np.concatenate(c[k]) for k in ("p", "y", "ga", "gv"))
        marge, bloc = np.concatenate(c["marge"]), np.concatenate(c["bloc"])
        idx = np.arange(len(p))
        ok = ~np.isnan(y)
        prec = float(np.mean((p[ok] > 0.5) == (y[ok] > 0.5)))
        hausse = float(np.mean(y[ok]))
        # « quand l'IA est sûre d'elle » : les 10 % de prédictions les plus tranchées (pour la précision seulement)
        conf = np.abs(p - 0.5)
        s10 = ok & (conf >= np.quantile(conf, 0.9))
        prec10 = float(np.mean((p[s10] > 0.5) == (y[s10] > 0.5)))
        # trading : marge choisie sur la validation de chaque bloc, une décision toutes les H bougies
        sel = (marge >= 0) & (conf > marge) & ~np.isnan(ga) & (idx % H == 0)
        sens = np.where(p[sel] > 0.5, 1, -1)
        g = np.where(sens > 0, ga[sel], gv[sel])
        oks = ~np.isnan(y[sel])
        prec_tr = float(np.mean((sens[oks] > 0) == (y[sel][oks] > 0.5))) if oks.any() else None
        moitie = bloc[sel] < (bloc.max() + 1) / 2
        t = float(np.mean(g) / (np.std(g) / math.sqrt(len(g)))) if len(g) > 2 and np.std(g) > 0 else 0.0
        out[m] = {"precision": round(prec * 100, 2), "jugees": int(ok.sum()), "part_hausse": round(hausse * 100, 2),
                  "precision_sure_10pct": round(prec10 * 100, 2),
                  "trades": int(sel.sum()), "precision_trades": None if prec_tr is None else round(prec_tr * 100, 2),
                  "gain_moyen_pct": round(float(np.mean(g)) * 100, 5) if len(g) else 0.0,
                  "gain_total_pct": round(float(np.sum(g)) * 100, 3),
                  "gain_moitie1_pct": round(float(np.sum(g[moitie])) * 100, 3),
                  "gain_moitie2_pct": round(float(np.sum(g[~moitie])) * 100, 3), "t": round(t, 2)}
    return out


# --------------------------------------------------------------------------- bilan
def bilan(dossier: Path, md: Path, sortie_json: Path):
    lignes, tous = [], []
    for f in sorted(dossier.glob("*.json")):
        r = json.loads(f.read_text())
        tous.append(r)
        for H in (k for k in r if k.startswith("H")):
            for m, s in r[H].items():
                lignes.append({"epic": r["epic"], "unite": r["unite"], "H": int(H[1:]), "modele": m, **s})
    nb = max(1, sum(1 for x in lignes if x["trades"] > 0))
    from statistics import NormalDist
    t_seuil = NormalDist().inv_cdf(1 - 0.05 / (2 * nb))  # Bonferroni : beaucoup d'essais => la chance fait des « records »
    for x in lignes:
        x["solide"] = bool(x["trades"] >= 100 and x["t"] >= t_seuil and x["gain_moitie1_pct"] > 0 and x["gain_moitie2_pct"] > 0)
    sortie_json.write_text(json.dumps({"t_seuil": round(t_seuil, 2), "essais": nb, "marches": tous, "lignes": lignes},
                                      indent=1, ensure_ascii=False))
    df = pd.DataFrame(lignes)
    out = ["# IA qui prédisent la direction : résultats sur données jamais vues", "",
           f"{len(tous)} couples marché x unité, {nb} essais (marché x unité x horizon x IA).",
           f"Une IA est « solide » si : au moins 100 trades, gain net positif sur les deux moitiés du test, "
           f"et t >= {t_seuil:.2f} (seuil corrigé pour le nombre d'essais).", ""]
    if df.empty:
        md.write_text("\n".join(out + ["Aucun résultat."]))
        return
    out += ["## Précision moyenne par IA (toutes bougies, tous marchés)", "",
            "| IA | précision | précision quand sûre (10 %) | trades | gain net total (%) |", "|---|---|---|---|---|"]
    for m, g in df.groupby("modele"):
        out.append(f"| {m} | {g.precision.mean():.2f} % | {g.precision_sure_10pct.mean():.2f} % | {g.trades.sum()} | "
                   f"{g.gain_total_pct.sum():+.1f} |")
    out += ["", "## Précision par unité et horizon (moyenne des marchés, meilleure IA)", "",
            "| unité | horizon (bougies) | meilleure IA | précision | quand sûre | gain net |", "|---|---|---|---|---|---|"]
    for (u, H), g in df.groupby(["unite", "H"]):
        b = g.groupby("modele").precision.mean().idxmax()
        gb = g[g.modele == b]
        out.append(f"| {u} | {H} | {b} | {gb.precision.mean():.2f} % | {gb.precision_sure_10pct.mean():.2f} % | "
                   f"{gb.gain_total_pct.sum():+.1f} % |")
    out += ["", "## Précision par marché (vote, horizon 1 bougie)", "", "| marché | unité | précision | quand sûre | spread % | gain net |",
            "|---|---|---|---|---|---|"]
    spreads = {(r["epic"], r["unite"]): r.get("spread_pct") for r in tous}
    for _, x in df[(df.modele == "vote") & (df.H == 1)].sort_values(["epic", "unite"]).iterrows():
        sp = spreads.get((x.epic, x.unite))
        out.append(f"| {x.epic} | {x.unite} | {x.precision:.2f} % | {x.precision_sure_10pct:.2f} % | "
                   f"{'-' if sp is None else f'{sp:.3f}'} | {x.gain_total_pct:+.1f} % |")
    sol = df[df.solide]
    out += ["", "## Solides", ""]
    out += [f"- {x.epic} {x.unite} H={x.H} {x.modele} : précision {x.precision} %, {x.trades} trades, "
            f"gain {x.gain_total_pct:+.2f} %, t={x.t}" for _, x in sol.iterrows()] or ["Aucune."]
    top = df[df.trades >= 100].sort_values("t", ascending=False).head(15)
    out += ["", "## 15 meilleurs t (avant correction)", "", "| marché | unité | H | IA | précision trades | trades | gain net | moitié 1 | moitié 2 | t |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for _, x in top.iterrows():
        out.append(f"| {x.epic} | {x.unite} | {x.H} | {x.modele} | {x.precision_trades} % | {x.trades} | "
                   f"{x.gain_total_pct:+.2f} % | {x.gain_moitie1_pct:+.2f} | {x.gain_moitie2_pct:+.2f} | {x.t} |")
    md.write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    action = sys.argv[1]
    if action == "telecharger":
        telecharger(Path(sys.argv[2]), sys.argv[3])
    elif action == "tester":
        tester(Path(sys.argv[2]), sys.argv[3], sys.argv[4], Path(sys.argv[5]))
    elif action == "bilan":
        bilan(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))

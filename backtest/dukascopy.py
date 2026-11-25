"""Convertit les bougies 1 h de Dukascopy (bid et ask séparés, gratuites, depuis 2015) au format des backtests
(backtest/telecharger.py), pour tester sur des données que le bot n'a JAMAIS vues (avant les 2 ans de Capital.com).

Les bougies 4 h sont reconstruites à partir des bougies 1 h, avec le MÊME découpage horaire que celles de
Capital.com (lu dans backtest/donnees/<EPIC>_HOUR_4.csv), pour que les frais de nuit tombent pareil.

Usage : python backtest/dukascopy.py <dossier_dukascopy> <dossier_sortie>
"""
import shutil
import sys
from pathlib import Path

import pandas as pd

SOURCE, SORTIE = Path(sys.argv[1]), Path(sys.argv[2])
CAPITAL = Path(__file__).resolve().parent / "donnees"
EPICS = {"xauusd": "GOLD", "xagusd": "SILVER", "btcusd": "BTCUSD"}


def lire(instr, prix):
    fichiers = sorted(SOURCE.glob(f"{instr}_{prix}*.csv"))
    if not fichiers:
        return None
    df = pd.concat(pd.read_csv(f) for f in fichiers)
    t = df["timestamp"]
    if pd.api.types.is_numeric_dtype(t):  # millisecondes par défaut (au cas où : secondes ou microsecondes)
        unite = "us" if t.max() > 1e14 else "ms" if t.max() > 1e11 else "s"
        df["date"] = pd.to_datetime(t, unit=unite)
    else:
        df["date"] = pd.to_datetime(t, utc=True).dt.tz_localize(None)
    return df.drop_duplicates("date").set_index("date").sort_index()[["open", "high", "low", "close"]]


def principal():
    SORTIE.mkdir(parents=True, exist_ok=True)
    for instr, epic in EPICS.items():
        b, a = lire(instr, "bid"), lire(instr, "ask")
        if b is None or a is None:
            print(f"{epic} : fichiers Dukascopy absents")
            continue
        j = b.join(a, lsuffix="_bid", rsuffix="_ask", how="inner").dropna()
        j = j[(j.high_bid > j.low_bid) | (j.open_bid != j.close_bid)]  # heures sans cotation (week-end) retirées
        j["volume"] = 0
        cols = ["open_bid", "open_ask", "high_bid", "high_ask", "low_bid", "low_ask", "close_bid", "close_ask", "volume"]
        j[cols].to_csv(SORTIE / f"{epic}_HOUR.csv", index_label="date", date_format="%Y-%m-%dT%H:%M:%S")
        decal = 0
        ref = CAPITAL / f"{epic}_HOUR_4.csv"
        if ref.exists():
            h = pd.to_datetime(pd.read_csv(ref, usecols=["date"]).date).dt.hour % 4
            decal = int(h.mode().iloc[0])
        q = j.resample("4h", offset=f"{decal}h").agg({
            "open_bid": "first", "open_ask": "first", "high_bid": "max", "high_ask": "max",
            "low_bid": "min", "low_ask": "min", "close_bid": "last", "close_ask": "last", "volume": "sum"}).dropna()
        q[cols].to_csv(SORTIE / f"{epic}_HOUR_4.csv", index_label="date", date_format="%Y-%m-%dT%H:%M:%S")
        m = CAPITAL / f"{epic}_marche.json"
        if m.exists():
            shutil.copy(m, SORTIE / m.name)
        print(f"{epic} : {len(j)} bougies 1 h et {len(q)} bougies 4 h (décalage {decal} h), "
              f"de {j.index[0]:%d/%m/%Y} à {j.index[-1]:%d/%m/%Y}, spread moyen {(j.close_ask - j.close_bid).mean():.3f}")


if __name__ == "__main__":
    principal()

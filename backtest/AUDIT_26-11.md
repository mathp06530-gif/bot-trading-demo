# Audit anti-triche des backtests (26/11/2026)

Question de Mathis : nos backtests « trichent »-ils (regard vers le futur), comme celui du FVG ?

## 1. Prix tirés au hasard (backtest/audit_hasard.py, 8 graines, 10 ans en 4 h, 6 mois en 5 min)

Sur une marche aléatoire, toutes les stratégies actives perdent à peu près leurs frais. Aucune ne gagne
après frais. Aucun regard vers le futur.

| Backtest | R/trade sans frais | R/trade avec frais |
|---|---|---|
| Cassure 4 h (garde 50 %) | +0,04 (bruit) | -0,08 |
| Supertrend 4 h | -0,01 | -0,06 |
| Élan 4 h | +0,01 | -0,11 |
| MACD gaz / Tesla (usine) | 0,00 / +0,01 | -0,04 / -0,02 |
| Usine (400 combinaisons) | +0,007 | -0,03 |
| Rapide 5 min (PR 36) | 0,00 | -0,01 |
| Sorties PR 32 / 34 | 0,00 | -0,02 |

## 2. Relecture du code

- Signaux sur bougies terminées, entrée à l'ouverture suivante, stop avant objectif dans une même bougie,
  indicateurs des unités supérieures (1 h, 4 h) pris seulement une fois la bougie finie : OK partout.
- **Bug trouvé (coût, pas triche)** : les frais de nuit n'étaient JAMAIS comptés (test « bougie de 22 h 00 »,
  qui n'existe ni en 4 h ni en 5 min sur l'or). Corrigé dans serrage, moteur, rapide_defauts, sortie_rapide
  (l'usine les comptait déjà bien).

## 3. Backtest contre trades réels (backtest/comparer_reel.py)

- Rapide : le backtest retrouve 13 des 13 entrées réelles à la même minute, à 1-2 $ près. Réel +0,57 R,
  backtest +1,9 R sur la même période (réglages changés en cours de route). Pas de triche.
- **Cassure : les 2 trades réels du 25/11 sont des « re-entrées » (nouvelle cassure pendant une baisse déjà
  en cours) que le backtest ne prenait jamais.** Le bot jouait donc une version non testée.

## 4. Chiffres refaits (backtest/audit_chiffres.py, 10 ans Capital.com)

| | 2017-21 | 2022-mi-24 | mi-24-auj. | Total |
|---|---|---|---|---|
| Cassure, ancien calcul | +12,3 | +16,7 | +63,5 | +92,5 R |
| Cassure, frais de nuit comptés | +6,6 | +14,6 | +59,4 | +80,6 R |
| Cassure comme le bot jouait (re-entrées) | +1,3 | +1,6 | +52,0 | +54,9 R |
| Supertrend ETH | +104,5 | +14,0 | +10,3 | +128,8 R |
| Élan | +20,9 | -44,2 | +40,0 | +16,6 R (pire baisse -99 R) |
| Rapide 5 min (6 mois) | | | | +26,3 R, 333 trades |

Décision : re-entrées Cassure coupées (CASSURE_REENTREES="non"), le bot joue maintenant la version testée.
À retenir : l'essentiel des gains de la Cassure vient de la hausse de l'or depuis mi-2024 ; hors de cette
période l'avantage est faible.

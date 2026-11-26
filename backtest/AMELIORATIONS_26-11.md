# Recherche « améliorer les stratégies actuelles » (26/11/2026)

Banc : backtest/ameliorations.py (workflow ameliorations.yml). Réglage choisi sur 2017-2021, jugé sur 2022 -> 26/11/2026
(jamais vu, en 2 morceaux), spread + frais de nuit + prime du stop garanti, voisins, 500 tirages au hasard, Bonferroni
sur 16 familles. Détail : backtest/resultats_ameliorations.json.

## Verdict : 0 idée sur 16 ne bat la version actuelle

Cassure or+argent actuelle, jamais vu : +74,0 R, 246 trades, Sharpe mensuel 0,89, pire baisse -12,3 R.

| Idée (réglage choisi sur 2017-2021) | Jamais vu | Sharpe | Verdict |
|---|---|---|---|
| Momentum 63 j (Moskowitz 2012) | +51,4 R | 0,66 | moins bien |
| Efficacité de Kaufman | +2,3 R (2 trades) | - | moins bien |
| Cassure après calme (ATR14/ATR100 <= 0,8) | +4,2 R | 0,32 | moins bien |
| Cassure quand ça s'agite (>= 0,9) | +46,5 R | 0,86 | moins bien |
| EMA 20 jour (multi-unités) | +73,8 R | 0,88 | pareil |
| Achats seulement | +67,7 R | 0,83 | moins bien |
| L'autre métal dans le même sens | +63,4 R | 0,85 | moins bien |
| Taille selon volatilité (Harvey 2018) | +78,7 R | 0,80 | moins bien (plus de R, plus irrégulier) |
| Or + argent ensemble : 2e à x0,5 | +72,5 R | 0,86 | moins bien |
| Suiveur chandelier 4 ATR | +51,3 R | 0,84 | moins bien |

Supertrend ETH (jamais vu +24,3 R, Sharpe 0,40) : aucun filtre ne passe (meilleur : taille selon volatilité, +50,6 R,
p = 0,35 avant correction : hasard).

## Empilement Cassure (le bot l'utilise : EMPILER_MAX=3, jamais mesuré sur 10 ans)

| | 2017-21 | 2022-mi-24 | mi-24-auj. | pire baisse 2017-21 |
|---|---|---|---|---|
| 1 position | +11,5 R (Sharpe 0,14) | +14,6 R (0,46) | +59,4 R (1,21) | -32,9 R |
| 2 positions max | +50,3 R | +16,1 R (0,44) | +98,9 R (1,03) | -36,1 R |
| 3 positions max (actuel) | +69,8 R | +8,6 R (0,22) | +121,2 R (0,91) | -50,0 R |

Plus de R mais moins réguliers et des baisses bien plus fortes (chaque position risque 3 %). Sur prix au hasard,
l'empilement perd un peu plus que 1 position (-0,03 R/trade).

## Supertrend sur d'autres cryptos (jamais vu)
BTC +37,6 / +10,0 R (positif les 2 morceaux) ; SOL -33,4 / +4,1 ; XRP -38,9 / +14,5 ; LTC -17,9 / -27,7.

## « Gagner beaucoup très vite » : 1 an depuis 93 €, vrais trades jamais vus Cassure + Supertrend (111 trades/an)
| Risque/trade | Médiane | Chance x10 | Chance de finir en perte | Chance de -50 % en route |
|---|---|---|---|---|
| 1 % | 109 € | 0 % | 21 % | 0 % |
| 3 % | 134 € | 0,2 % | 25 % | 8 % |
| 5 % | 147 € | 3,6 % | 29 % | 44 % |
| 10 % | 128 € | 12 % | 42 % | 97 % |
| 20 % | 24 € | 11 % | 68 % | 100 % |
Chiffres optimistes (période de forte hausse de l'or incluse).

# Stratégies qui gagnent sur 2 mois (26/11/2026)

Fenêtres : A (choix) 2026-09-26 -> 2026-11-26 ; B (jamais vue) 2026-07-27 -> 2026-09-26 ; C (jamais vue) 2026-05-27 -> 2026-07-27.

**8608896 stratégies essayées** (usine : ~45 800 combinaisons x 94 marchés x 4 h et jour), 2599488 avec assez de trades sur A.

- gagnent sur A (2 derniers mois) : **926921**
- gagnent sur A ET B : **220002**
- gagnent sur A, B ET C : **74801**

Contrôle du hasard (mêmes bougies tirées au sort, aucun avantage possible) : 2730768 classées, 940151 gagnent sur A, 240452 sur A et B, 85523 sur A, B et C.

## Le test du hasard : les meilleures des 2 derniers mois gagnaient-elles avant ?

| Groupe (classé sur A) | Nb | R moyen sur A | R moyen sur B | % qui gagnaient sur B |
|---|---|---|---|---|
| top_0.1% | 2505 | 5.57 | -0.98 | 26.7 % |
| top_1% | 25907 | 4.04 | -0.85 | 27.6 % |
| top_10% | 259873 | 2.16 | -0.65 | 30.0 % |
| toutes | 2599488 | -0.69 | -0.54 | 33.3 % |

Parmi les stratégies qui gagnent sur A ET B, 35.0 % gagnaient aussi sur C (2 mois encore avant).

## Top par marché sur les 2 derniers mois (A), avec les 2 mois d'avant (B) et encore avant (C)

| Marché | Unité | Stratégie | R sur A (trades) | A frais x1,5 | R sur B (trades) | R sur C (trades) |
|---|---|---|---|---|---|---|
| ETHUSD | HOUR_4 | Élan 50, vente seulement, seulement si la volatilité baisse, stop garanti 1.5 ATR | 19.04 (7) | 19.06 | -5.96 (13) | -1.3 (4) |
| SG25 | HOUR_4 | Élan 100, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR | 18.17 (4) | 17.86 | -1.2 (1) | 12.26 (11) |
| HK50 | HOUR_4 | Élan 20, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR | 17.78 (16) | 17.02 | -0.16 (1) | 5.82 (6) |
| AVAXUSD | HOUR_4 | Rebond sur plus bas 20, achat et vente, stop garanti 1.5 ATR, suiveur 3 ATR | 17.46 (31) | 11.68 | -1.79 (21) | -2.38 (27) |
| SILVER | HOUR_4 | Élan 50, vente seulement, seulement si la volatilité baisse, stop garanti 1.5 ATR | 16.44 (4) | 16.44 | -3.93 (8) | -1.95 (11) |
| BTCUSD | HOUR_4 | Élan 50, vente seulement, dans le sens de la moyenne 200, stop garanti 1.5 ATR, suiveur 3 ATR | 15.7 (7) | 15.69 | -0.45 (2) | -2.43 (8) |
| SOLUSD | HOUR_4 | Élan 50, vente seulement, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 15.6 (5) | 15.26 | -2.94 (8) | -1.05 (3) |
| US30 | HOUR_4 | Clôture en bas de bougie 0.1, achat et vente, stop garanti 1.5 ATR, 20 bougies max | 14.35 (42) | 14.02 | -7.72 (32) | -3.65 (33) |
| USDMXN | HOUR_4 | Clôture en bas de bougie 0.1, achat et vente, seulement si tendance forte (ADX > 25), stop garanti 1.5 ATR, objectif 3 R, suiveur 3 ATR, 20 bougies max | 14.3 (25) | 13.93 | -4.68 (9) | -0.98 (11) |
| IT40 | HOUR_4 | Élan 20, achat et vente, stop garanti 1.5 ATR | 14.24 (15) | 13.81 | -5.08 (26) | -5.16 (16) |
| AUDUSD | HOUR_4 | Élan 20, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 14.12 (7) | 13.7 | -1.04 (12) | -6.5 (19) |
| COPPER | HOUR_4 | Élan 100, achat et vente, seulement si tendance forte (ADX > 25), stop garanti 1.5 ATR | 14.11 (4) | 13.91 | -2.52 (5) | -0.64 (3) |
| PLATINUM | HOUR_4 | Croisement de moyennes 5/20, vente seulement, seulement si la volatilité baisse, stop garanti 1.5 ATR | 14.09 (5) | 13.53 | -5.72 (7) | 1.12 (6) |
| SP35 | HOUR_4 | Élan 20, achat et vente, seulement si la volatilité baisse, stop garanti 1.5 ATR, 20 bougies max | 13.72 (5) | 13.55 | -5.33 (17) | -10.35 (17) |
| XLMUSD | HOUR_4 | Élan 50, vente seulement, stop garanti 1.5 ATR | 13.32 (5) | 4.59 | -6.03 (7) | -2.73 (12) |
| EURGBP | HOUR_4 | Supertrend 14/2, achat et vente, seulement si tendance forte (ADX > 25), stop garanti 1.5 ATR | 12.79 (4) | 9.77 | -3.06 (2) | 2.32 (3) |
| DE40 | HOUR_4 | MACD 12/26/9, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR, objectif 1 R | 12.58 (15) | 12.43 | -0.72 (9) | 0.46 (6) |
| USDNOK | HOUR_4 | Élan 20, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 12.09 (7) | 11.72 | -8.46 (13) | 3.65 (14) |
| FR40 | HOUR_4 | MACD 24/52/18, achat et vente, stop garanti 1.5 ATR | 11.87 (8) | 11.38 | 2.31 (6) | -3.28 (10) |
| XRPUSD | HOUR_4 | Élan 200, vente seulement, seulement si la volatilité baisse, stop garanti 1.5 ATR | 11.82 (8) | 11.31 | -1.85 (4) | -0.6 (4) |

## Celles qui gagnent sur A ET B (classées par la moins bonne des deux), avec C

| Marché | Unité | Stratégie | R sur A (trades) | R sur B (trades) | R sur C (trades) | A frais x1,5 |
|---|---|---|---|---|---|---|
| ETHUSD | HOUR_4 | Élan 50, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | 12.94 (10) | 16.07 (23) | 0.22 (4) | 12.87 |
| LINKUSD | HOUR_4 | Élan 100, achat et vente, seulement si tendance forte (ADX > 25), stop garanti 1.5 ATR | 11.47 (5) | 11.98 (6) | -5.0 (10) | 11.21 |
| USDMXN | HOUR_4 | Croisement de moyennes 5/20, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 10.99 (4) | 19.68 (9) | -8.23 (12) | 10.75 |
| LTCUSD | HOUR_4 | Élan 50, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | 10.64 (5) | 14.13 (8) | -2.85 (5) | 10.36 |
| AVAXUSD | HOUR_4 | Élan 100, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 11.52 (4) | 10.4 (25) | -5.36 (15) | 11.33 |
| XRPUSD | HOUR_4 | Élan 200, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | 10.62 (7) | 9.14 (7) | -2.37 (4) | 10.32 |
| SOLUSD | HOUR_4 | Élan 50, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | 8.96 (10) | 11.53 (17) | -0.76 (3) | 8.29 |
| GOLD | HOUR_4 | MACD 12/26/9, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR, suiveur 3 ATR, 20 bougies max | 8.53 (13) | 8.05 (11) | -3.48 (13) | 8.54 |
| BTCUSD | HOUR_4 | Cassure du canal 20, achat et vente, seulement si la volatilité baisse, stop garanti 1.5 ATR, suiveur 3 ATR | 7.9 (8) | 17.99 (5) | -3.34 (7) | 7.84 |
| FR40 | HOUR_4 | Sortie des bandes de Bollinger 20/2, achat et vente, stop garanti 1.5 ATR, 20 bougies max | 8.13 (7) | 7.61 (5) | -2.81 (6) | 7.91 |
| USDCAD | HOUR_4 | Élan 20, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR | 7.29 (16) | 12.09 (9) | 2.29 (14) | 6.03 |
| ADAUSD | HOUR_4 | Supertrend 7/2, achat et vente, seulement si la volatilité baisse, stop garanti 1.5 ATR, objectif 3 R | 7.9 (10) | 6.85 (5) | -5.73 (9) | 7.62 |
| XLMUSD | HOUR_4 | Clôture en bas de bougie 0.1, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR, objectif 3 R | 8.51 (8) | 6.3 (23) | -0.66 (16) | 7.91 |
| OIL_CRUDE | HOUR_4 | Croisement de moyennes 5/20, achat et vente, seulement si la volatilité baisse, stop garanti 2.5 ATR | 6.2 (5) | 6.23 (5) | 4.29 (10) | 6.11 |
| USDPLN | HOUR_4 | Sortie des bandes de Bollinger 20/2, achat seulement, stop garanti 1.5 ATR | 6.07 (4) | 7.21 (4) | -1.19 (7) | 3.07 |
| AUDUSD | HOUR_4 | Élan 20, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR | 11.15 (12) | 6.03 (6) | -2.94 (3) | 10.69 |
| HK50 | HOUR_4 | Élan 50, vente seulement, stop garanti 1.5 ATR, objectif 3 R, suiveur 3 ATR | 8.13 (7) | 5.93 (6) | 2.82 (2) | 7.9 |
| SOLUSD | DAY | MACD 12/26/9, achat et vente, stop garanti 1.5 ATR | 5.84 (2) | 6.35 (3) | -0.93 (2) | 5.82 |
| UNIUSD | HOUR_4 | Élan 100, achat et vente, stop garanti 1.5 ATR | 5.7 (15) | 30.15 (4) | 1.83 (9) | 4.87 |
| UK100 | HOUR_4 | MACD 12/26/9, vente seulement, seulement si la volatilité baisse, stop garanti 1.5 ATR, suiveur 3 ATR, 20 bougies max | 6.4 (10) | 5.67 (4) | -4.44 (4) | 6.33 |

## Petits marchés seulement (gagnent sur A ET B)

| Catégorie | Marché | Unité | Stratégie | R sur A (trades) | R sur B (trades) | R sur C (trades) | A frais x1,5 |
|---|---|---|---|---|---|---|---|
| petites cryptos | LINKUSD | HOUR_4 | Élan 100, achat et vente, seulement si tendance forte (ADX > 25), stop garanti 1.5 ATR | 11.47 (5) | 11.98 (6) | -5.0 (10) | 11.21 |
| devises exotiques | USDMXN | HOUR_4 | Croisement de moyennes 5/20, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 10.99 (4) | 19.68 (9) | -8.23 (12) | 10.75 |
| petites cryptos | AVAXUSD | HOUR_4 | Élan 100, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 11.52 (4) | 10.4 (25) | -5.36 (15) | 11.33 |
| petits indices | GOLD | HOUR_4 | MACD 12/26/9, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR, suiveur 3 ATR, 20 bougies max | 8.53 (13) | 8.05 (11) | -3.48 (13) | 8.54 |
| petites cryptos | ADAUSD | HOUR_4 | Supertrend 7/2, achat et vente, seulement si la volatilité baisse, stop garanti 1.5 ATR, objectif 3 R | 7.9 (10) | 6.85 (5) | -5.73 (9) | 7.62 |
| petites cryptos | XLMUSD | HOUR_4 | Clôture en bas de bougie 0.1, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR, objectif 3 R | 8.51 (8) | 6.3 (23) | -0.66 (16) | 7.91 |
| devises exotiques | USDPLN | HOUR_4 | Sortie des bandes de Bollinger 20/2, achat seulement, stop garanti 1.5 ATR | 6.07 (4) | 7.21 (4) | -1.19 (7) | 3.07 |
| petites cryptos | UNIUSD | HOUR_4 | Élan 100, achat et vente, stop garanti 1.5 ATR | 5.7 (15) | 30.15 (4) | 1.83 (9) | 4.87 |
| petites cryptos | DOTUSD | HOUR_4 | MACD 24/52/18, vente seulement, stop garanti 1.5 ATR, objectif 2 R | 6.26 (10) | 5.5 (7) | -3.13 (7) | 6.17 |
| petites cryptos | BCHUSD | HOUR_4 | Élan 20, achat et vente, seulement si la volatilité monte, stop garanti 1.5 ATR | 5.42 (12) | 16.7 (11) | 7.41 (4) | 4.47 |
| matières premières secondaires | UKSUGAR | HOUR_4 | Croisement de moyennes 5/20, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR, 20 bougies max | 7.47 (4) | 4.99 (4) | 3.51 (7) | 7.28 |
| petits indices | SP35 | HOUR_4 | Clôture en bas de bougie 0.3, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 5.82 (32) | 4.65 (20) | -1.84 (25) | 5.27 |
| matières premières secondaires | CORN | HOUR_4 | Croisement de moyennes 5/20, achat et vente, seulement si la volatilité baisse, stop garanti 1.5 ATR | 4.33 (6) | 11.14 (7) | -3.05 (3) | 3.94 |
| matières premières secondaires | COFFEEARABICA | HOUR_4 | Clôture en bas de bougie 0.2, achat et vente, stop garanti 1.5 ATR, objectif 2 R, suiveur 3 ATR | 6.33 (32) | 4.32 (39) | -7.51 (29) | 5.49 |
| petits indices | IT40 | HOUR_4 | Clôture en bas de bougie 0.2, vente seulement, seulement si la volatilité baisse, stop garanti 1.5 ATR, objectif 2 R, 20 bougies max | 4.31 (9) | 4.69 (12) | -0.42 (14) | 4.19 |
| matières premières secondaires | USCOTTON | HOUR_4 | Supertrend 10/2, achat et vente, stop garanti 1.5 ATR, objectif 3 R, suiveur 3 ATR | 6.57 (6) | 4.06 (7) | -1.55 (12) | 4.31 |
| devises exotiques | USDNOK | HOUR_4 | Supertrend 7/2, achat et vente, stop garanti 1.5 ATR | 7.51 (7) | 3.94 (4) | 1.12 (6) | 2.87 |
| petites actions | PLTR | HOUR_4 | MACD 24/52/18, achat et vente, stop garanti 2.5 ATR, objectif 3 R, 20 bougies max | 3.78 (8) | 3.82 (5) | 4.57 (7) | 3.63 |
| matières premières secondaires | RR | HOUR_4 | Clôture en bas de bougie 0.2, achat et vente, seulement si la volatilité baisse, stop garanti 1.5 ATR, objectif 3 R, suiveur 3 ATR, 20 bougies max | 3.76 (8) | 3.57 (5) | -3.2 (3) | 3.19 |
| petites cryptos | DOTUSD | DAY | Élan 20, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | 3.51 (2) | 5.98 (3) | -0.41 (1) | 3.49 |

## Avec plus de risque : gain et pire chute sur les 2 derniers mois (sans intérêts composés)

| Marché | Stratégie | Risque 1 % | Risque 3 % | Risque 5 % |
|---|---|---|---|---|
| ETHUSD HOUR_4 | Élan 50, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | +13 % (chute -3 %) | +39 % (chute -9 %) | +65 % (chute -15 %) |
| LINKUSD HOUR_4 | Élan 100, achat et vente, seulement si tendance forte (ADX > 25), stop garanti 1.5 ATR | +11 % (chute -1 %) | +34 % (chute -4 %) | +57 % (chute -7 %) |
| USDMXN HOUR_4 | Croisement de moyennes 5/20, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | +11 % (chute -1 %) | +33 % (chute -3 %) | +55 % (chute -5 %) |
| LTCUSD HOUR_4 | Élan 50, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | +11 % (chute -1 %) | +32 % (chute -3 %) | +53 % (chute -5 %) |
| AVAXUSD HOUR_4 | Élan 100, achat et vente, seulement si marché calme (ADX < 20), stop garanti 1.5 ATR | +12 % (chute -0 %) | +35 % (chute -1 %) | +58 % (chute -2 %) |
| XRPUSD HOUR_4 | Élan 200, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | +11 % (chute -3 %) | +32 % (chute -8 %) | +53 % (chute -13 %) |
| SOLUSD HOUR_4 | Élan 50, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR | +9 % (chute -4 %) | +27 % (chute -13 %) | +45 % (chute -22 %) |
| GOLD HOUR_4 | MACD 12/26/9, achat et vente, dans le sens de la moyenne 200, stop garanti 1.5 ATR, suiveur 3 ATR, 20 bougies max | +9 % (chute -2 %) | +26 % (chute -6 %) | +43 % (chute -10 %) |
| BTCUSD HOUR_4 | Cassure du canal 20, achat et vente, seulement si la volatilité baisse, stop garanti 1.5 ATR, suiveur 3 ATR | +8 % (chute -6 %) | +24 % (chute -17 %) | +40 % (chute -28 %) |
| FR40 HOUR_4 | Sortie des bandes de Bollinger 20/2, achat et vente, stop garanti 1.5 ATR, 20 bougies max | +8 % (chute -2 %) | +24 % (chute -7 %) | +41 % (chute -12 %) |

1 R ≈ 0.93 € avec 1 % de risque sur ~93 €.

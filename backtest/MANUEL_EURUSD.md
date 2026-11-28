# Trading manuel EUR/USD : quelle stratégie rapide tient la route ?

Labo du 28/11/2026, bougies Capital.com démo (prix acheteur et vendeur : vrai spread payé), aucune position gardée la nuit. Résultats en **R** (1 R = la somme risquée sur un trade, par exemple 1 € avec 1 % de risque sur 100 €).

Anti-triche : signal sur bougie clôturée, entrée à la bougie suivante, stop compté en premier si stop et objectif tombent dans la même bougie, réglages choisis sur la 1re période et jugés sur la 2e (jamais vue), contrôle sur prix mélangés.

## Bougies 15 min : 29/12/2024 au 27/11/2026

Spread médian : 0.60 pips. Période de choix : jusqu'au 21/02/2026, période de test (jamais vue) : ensuite.

### Période de choix (tri par R total)

| Variante | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs |
|---|---|---|---|---|---|---|---|
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif heure de fin | 259 (18.9/mois) | 38.6 % | +0.012 | +3.0 | +0.22 | 18.9 | 47 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 2.0 R | 259 (18.9/mois) | 40.2 % | -0.010 | -2.5 | -0.18 | 21.1 | 40 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.5 R | 259 (18.9/mois) | 42.5 % | -0.012 | -3.0 | -0.22 | 15.7 | 53 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.5 R | 165 (12.1/mois) | 43.6 % | -0.022 | -3.6 | -0.26 | 12.9 | 40 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 2.0 R | 165 (12.1/mois) | 43.0 % | -0.024 | -3.9 | -0.29 | 11.8 | 40 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.0 R | 258 (18.9/mois) | 47.7 % | -0.028 | -7.1 | -0.52 | 23.3 | 47 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 2.0 R | 165 (12.1/mois) | 35.2 % | -0.046 | -7.6 | -0.55 | 18.0 | 47 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.0 R | 259 (18.9/mois) | 47.5 % | -0.031 | -8.0 | -0.58 | 18.5 | 47 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.0 R | 165 (12.1/mois) | 44.8 % | -0.050 | -8.3 | -0.61 | 13.1 | 40 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif heure de fin | 165 (12.1/mois) | 43.0 % | -0.058 | -9.6 | -0.70 | 14.0 | 40 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.5 R | 258 (18.9/mois) | 38.8 % | -0.039 | -10.1 | -0.74 | 26.0 | 47 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif heure de fin | 165 (12.1/mois) | 33.9 % | -0.075 | -12.4 | -0.91 | 21.4 | 40 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 2.0 R | 258 (18.9/mois) | 34.1 % | -0.059 | -15.2 | -1.11 | 24.9 | 40 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif heure de fin | 258 (18.9/mois) | 28.3 % | -0.060 | -15.4 | -1.13 | 33.3 | 40 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif heure de fin | 242 (17.7/mois) | 37.6 % | -0.067 | -16.3 | -1.19 | 21.7 | 40 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.0 R | 242 (17.7/mois) | 46.3 % | -0.074 | -17.9 | -1.31 | 19.6 | 20 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.0 R | 165 (12.1/mois) | 43.6 % | -0.109 | -18.0 | -1.31 | 20.0 | 27 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.5 R | 165 (12.1/mois) | 37.0 % | -0.110 | -18.1 | -1.33 | 20.3 | 47 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.5 R | 242 (17.7/mois) | 39.3 % | -0.114 | -27.7 | -2.02 | 30.8 | 27 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.0 R | 242 (17.7/mois) | 43.4 % | -0.132 | -32.0 | -2.34 | 34.0 | 20 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 3 pips | 460 (33.6/mois) | 38.3 % | -0.070 | -32.2 | -2.35 | 38.0 | 27 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 2.0 R | 242 (17.7/mois) | 37.6 % | -0.134 | -32.3 | -2.36 | 34.0 | 33 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 3 pips | 474 (34.6/mois) | 46.6 % | -0.070 | -33.2 | -2.42 | 35.5 | 20 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.5 R | 242 (17.7/mois) | 34.3 % | -0.147 | -35.7 | -2.61 | 40.5 | 27 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 3 pips | 454 (33.2/mois) | 33.7 % | -0.093 | -42.1 | -3.08 | 50.9 | 27 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 1 pips | 475 (34.7/mois) | 32.0 % | -0.095 | -45.2 | -3.30 | 48.9 | 33 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 1 pips | 483 (35.3/mois) | 37.1 % | -0.098 | -47.2 | -3.45 | 51.1 | 40 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif heure de fin | 242 (17.7/mois) | 23.6 % | -0.204 | -49.4 | -3.61 | 59.8 | 27 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 2.0 R | 242 (17.7/mois) | 27.7 % | -0.207 | -50.1 | -3.66 | 52.5 | 13 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 1 pips | 493 (36.0/mois) | 44.6 % | -0.119 | -58.9 | -4.30 | 62.5 | 7 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 1 pips | 712 (51.9/mois) | 38.8 % | -0.103 | -73.4 | -5.35 | 84.9 | 20 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 3 pips | 704 (51.3/mois) | 42.8 % | -0.105 | -73.6 | -5.37 | 81.3 | 27 % |

### Période de test jamais vue (même ordre)

| Variante | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs |
|---|---|---|---|---|---|---|---|
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif heure de fin | 175 (19.2/mois) | 39.4 % | -0.050 | -8.7 | -0.95 | 14.3 | 40 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 2.0 R | 175 (19.2/mois) | 40.0 % | -0.072 | -12.7 | -1.39 | 13.4 | 20 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.5 R | 175 (19.2/mois) | 40.6 % | -0.097 | -17.0 | -1.87 | 17.3 | 30 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.5 R | 143 (15.7/mois) | 55.9 % | +0.065 | +9.2 | +1.01 | 7.1 | 70 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 2.0 R | 143 (15.7/mois) | 53.8 % | +0.054 | +7.7 | +0.85 | 7.8 | 60 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.0 R | 175 (19.2/mois) | 41.1 % | -0.177 | -31.0 | -3.40 | 31.5 | 20 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 2.0 R | 143 (15.7/mois) | 51.7 % | +0.196 | +28.0 | +3.07 | 10.9 | 80 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.0 R | 175 (19.2/mois) | 46.9 % | -0.061 | -10.7 | -1.18 | 12.3 | 30 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.0 R | 143 (15.7/mois) | 58.0 % | +0.079 | +11.2 | +1.23 | 6.0 | 80 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif heure de fin | 143 (15.7/mois) | 53.8 % | +0.060 | +8.6 | +0.94 | 8.9 | 60 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.5 R | 175 (19.2/mois) | 36.6 % | -0.149 | -26.1 | -2.86 | 27.1 | 20 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif heure de fin | 143 (15.7/mois) | 47.6 % | +0.173 | +24.7 | +2.71 | 14.3 | 60 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 2.0 R | 175 (19.2/mois) | 32.6 % | -0.173 | -30.3 | -3.33 | 30.9 | 20 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif heure de fin | 175 (19.2/mois) | 28.0 % | -0.231 | -40.5 | -4.44 | 41.0 | 30 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif heure de fin | 179 (19.7/mois) | 41.9 % | +0.081 | +14.4 | +1.59 | 13.0 | 60 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.0 R | 179 (19.7/mois) | 51.4 % | +0.030 | +5.4 | +0.60 | 12.1 | 70 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.0 R | 143 (15.7/mois) | 60.1 % | +0.180 | +25.8 | +2.83 | 9.9 | 70 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.5 R | 143 (15.7/mois) | 54.5 % | +0.193 | +27.6 | +3.03 | 9.1 | 90 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.5 R | 179 (19.7/mois) | 46.4 % | +0.056 | +10.1 | +1.11 | 8.8 | 60 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.0 R | 179 (19.7/mois) | 47.5 % | -0.044 | -7.9 | -0.87 | 20.4 | 50 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 3 pips | 305 (33.6/mois) | 39.0 % | -0.071 | -21.6 | -2.37 | 27.9 | 30 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 2.0 R | 179 (19.7/mois) | 44.7 % | +0.118 | +21.0 | +2.32 | 7.1 | 60 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 3 pips | 316 (34.8/mois) | 46.8 % | -0.066 | -20.8 | -2.29 | 25.2 | 20 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.5 R | 179 (19.7/mois) | 40.8 % | -0.010 | -1.8 | -0.20 | 18.4 | 60 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 3 pips | 294 (32.4/mois) | 36.4 % | -0.045 | -13.2 | -1.45 | 25.2 | 40 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 1 pips | 313 (34.5/mois) | 33.9 % | -0.080 | -25.1 | -2.77 | 37.2 | 30 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 1 pips | 323 (35.6/mois) | 38.7 % | -0.072 | -23.2 | -2.55 | 34.1 | 40 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif heure de fin | 179 (19.7/mois) | 28.5 % | +0.040 | +7.1 | +0.78 | 23.2 | 60 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 2.0 R | 179 (19.7/mois) | 36.3 % | +0.029 | +5.3 | +0.58 | 20.1 | 60 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 1 pips | 330 (36.3/mois) | 45.5 % | -0.098 | -32.3 | -3.56 | 33.0 | 30 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 1 pips | 477 (52.3/mois) | 38.8 % | -0.109 | -52.1 | -5.72 | 61.5 | 30 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 3 pips | 464 (50.9/mois) | 43.8 % | -0.100 | -46.4 | -5.09 | 53.0 | 40 % |

### Meilleure variante de chaque famille (choisie sur la 1re période)

- **A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.5 R** : choix -0.022 R/trade (165 trades), **test +0.065 R/trade** (143 trades, 55.9 % gagnants, +1.01 R/mois, mois positifs 70 %), prix mélangés -0.039 R/trade.
- **B Cassure New York boîte 14:30-15:00, stop autre bord, objectif heure de fin** : choix +0.012 R/trade (259 trades), **test -0.050 R/trade** (175 trades, 39.4 % gagnants, -0.95 R/mois, mois positifs 40 %), prix mélangés -0.161 R/trade.
- **C Repli EMA 20, objectif 1.5 R, marge stop 3 pips** : choix -0.070 R/trade (460 trades), **test -0.071 R/trade** (305 trades, 39.0 % gagnants, -2.37 R/mois, mois positifs 30 %), prix mélangés -0.326 R/trade.
- **D Rebond Bollinger, objectif moyenne 20, marge stop 1 pips** : choix -0.103 R/trade (712 trades), **test -0.109 R/trade** (477 trades, 38.8 % gagnants, -5.72 R/mois, mois positifs 30 %), prix mélangés -0.371 R/trade.

## Bougies 5 min : 28/11/2025 au 27/11/2026

Spread médian : 0.70 pips. Période de choix : jusqu'au 05/07/2026, période de test (jamais vue) : ensuite.

### Période de choix (tri par R total)

| Variante | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs |
|---|---|---|---|---|---|---|---|
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.0 R | 106 (15.2/mois) | 56.6 % | +0.061 | +6.5 | +0.93 | 10.6 | 62 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.5 R | 106 (15.2/mois) | 54.7 % | +0.032 | +3.4 | +0.49 | 9.6 | 62 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 2.0 R | 106 (15.2/mois) | 52.8 % | -0.017 | -1.8 | -0.26 | 11.5 | 38 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 2.0 R | 106 (15.2/mois) | 38.7 % | -0.018 | -1.9 | -0.27 | 20.7 | 50 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.5 R | 106 (15.2/mois) | 41.5 % | -0.019 | -2.0 | -0.29 | 20.5 | 62 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif heure de fin | 146 (20.8/mois) | 39.0 % | -0.015 | -2.2 | -0.32 | 20.1 | 25 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.0 R | 142 (20.3/mois) | 48.6 % | -0.018 | -2.5 | -0.36 | 12.4 | 62 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 2.0 R | 146 (20.8/mois) | 39.7 % | -0.039 | -5.7 | -0.82 | 17.2 | 25 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif heure de fin | 106 (15.2/mois) | 52.8 % | -0.054 | -5.8 | -0.82 | 12.3 | 38 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.0 R | 142 (20.3/mois) | 47.2 % | -0.053 | -7.5 | -1.07 | 19.5 | 50 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 2.0 R | 142 (20.3/mois) | 32.4 % | -0.062 | -8.7 | -1.25 | 22.3 | 25 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 2.0 R | 142 (20.3/mois) | 38.0 % | -0.073 | -10.4 | -1.48 | 21.1 | 38 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.0 R | 146 (20.8/mois) | 47.3 % | -0.076 | -11.0 | -1.57 | 17.9 | 38 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.0 R | 106 (15.2/mois) | 44.3 % | -0.112 | -11.8 | -1.70 | 20.0 | 25 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.5 R | 146 (20.8/mois) | 40.4 % | -0.090 | -13.2 | -1.88 | 21.8 | 25 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.5 R | 142 (20.3/mois) | 39.4 % | -0.097 | -13.8 | -1.97 | 21.8 | 38 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.5 R | 146 (20.8/mois) | 36.3 % | -0.110 | -16.1 | -2.30 | 24.5 | 50 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif heure de fin | 142 (20.3/mois) | 36.6 % | -0.127 | -18.0 | -2.58 | 21.4 | 38 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.0 R | 146 (20.8/mois) | 43.8 % | -0.128 | -18.7 | -2.67 | 25.0 | 25 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.5 R | 142 (20.3/mois) | 35.2 % | -0.134 | -19.0 | -2.71 | 24.0 | 25 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 3 pips | 303 (43.2/mois) | 31.7 % | -0.066 | -20.0 | -2.86 | 35.2 | 38 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif heure de fin | 106 (15.2/mois) | 34.9 % | -0.193 | -20.4 | -2.93 | 24.4 | 25 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif heure de fin | 146 (20.8/mois) | 24.7 % | -0.151 | -22.1 | -3.15 | 38.6 | 25 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 3 pips | 304 (43.4/mois) | 36.2 % | -0.097 | -29.6 | -4.22 | 36.1 | 25 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 2.0 R | 146 (20.8/mois) | 29.5 % | -0.205 | -29.9 | -4.27 | 37.2 | 25 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 3 pips | 305 (43.5/mois) | 44.9 % | -0.105 | -32.0 | -4.56 | 36.0 | 25 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif heure de fin | 142 (20.3/mois) | 23.2 % | -0.242 | -34.4 | -4.90 | 36.3 | 38 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 1 pips | 305 (43.5/mois) | 43.9 % | -0.121 | -37.0 | -5.28 | 46.0 | 12 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 1 pips | 305 (43.5/mois) | 34.8 % | -0.136 | -41.4 | -5.91 | 53.4 | 25 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 1 pips | 305 (43.5/mois) | 28.5 % | -0.151 | -45.9 | -6.56 | 60.9 | 25 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 3 pips | 456 (64.8/mois) | 46.5 % | -0.107 | -48.8 | -6.93 | 55.4 | 25 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 1 pips | 456 (65.1/mois) | 37.3 % | -0.166 | -75.5 | -10.78 | 80.8 | 12 % |

### Période de test jamais vue (même ordre)

| Variante | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs |
|---|---|---|---|---|---|---|---|
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.0 R | 84 (17.7/mois) | 53.6 % | +0.008 | +0.7 | +0.14 | 6.3 | 60 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.5 R | 84 (17.7/mois) | 52.4 % | +0.039 | +3.3 | +0.69 | 6.3 | 80 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 2.0 R | 84 (17.7/mois) | 48.8 % | +0.021 | +1.8 | +0.37 | 6.9 | 60 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 2.0 R | 84 (17.7/mois) | 48.8 % | +0.173 | +14.5 | +3.07 | 6.0 | 80 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.5 R | 84 (17.7/mois) | 52.4 % | +0.176 | +14.8 | +3.12 | 5.0 | 60 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif heure de fin | 95 (20.1/mois) | 37.9 % | +0.005 | +0.5 | +0.11 | 12.5 | 40 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.0 R | 99 (20.9/mois) | 51.5 % | +0.005 | +0.5 | +0.11 | 7.4 | 60 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 2.0 R | 95 (20.1/mois) | 37.9 % | -0.088 | -8.4 | -1.77 | 11.1 | 20 % |
| A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif heure de fin | 84 (17.7/mois) | 48.8 % | +0.074 | +6.3 | +1.32 | 6.1 | 60 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.0 R | 99 (20.9/mois) | 48.5 % | -0.053 | -5.3 | -1.11 | 19.6 | 40 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 2.0 R | 99 (20.9/mois) | 35.4 % | -0.026 | -2.6 | -0.55 | 15.0 | 40 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 2.0 R | 99 (20.9/mois) | 44.4 % | +0.103 | +10.2 | +2.16 | 9.0 | 80 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.0 R | 95 (20.1/mois) | 43.2 % | -0.111 | -10.5 | -2.22 | 12.2 | 20 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif 1.0 R | 84 (17.7/mois) | 58.3 % | +0.149 | +12.5 | +2.63 | 5.0 | 80 % |
| B Cassure New York boîte 14:30-15:00, stop autre bord, objectif 1.5 R | 95 (20.1/mois) | 37.9 % | -0.113 | -10.7 | -2.26 | 11.4 | 20 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif 1.5 R | 99 (20.9/mois) | 45.5 % | +0.048 | +4.7 | +1.00 | 8.9 | 80 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.5 R | 95 (20.1/mois) | 35.8 % | -0.141 | -13.4 | -2.83 | 17.5 | 20 % |
| A Cassure Londres boîte 9:00-10:00, stop autre bord, objectif heure de fin | 99 (20.9/mois) | 42.4 % | +0.292 | +28.9 | +6.11 | 11.5 | 80 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 1.0 R | 95 (20.1/mois) | 44.2 % | -0.111 | -10.5 | -2.22 | 11.5 | 20 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif 1.5 R | 99 (20.9/mois) | 41.4 % | -0.014 | -1.4 | -0.29 | 15.3 | 40 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 3 pips | 207 (43.7/mois) | 37.2 % | +0.101 | +20.9 | +4.41 | 23.2 | 40 % |
| A Cassure Londres boîte 1:00-9:00, stop milieu, objectif heure de fin | 84 (17.7/mois) | 44.0 % | +0.301 | +25.3 | +5.34 | 6.1 | 60 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif heure de fin | 95 (20.1/mois) | 27.4 % | -0.137 | -13.0 | -2.74 | 22.2 | 40 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 3 pips | 209 (44.1/mois) | 43.5 % | +0.081 | +16.9 | +3.58 | 19.5 | 60 % |
| B Cassure New York boîte 14:30-15:00, stop milieu, objectif 2.0 R | 95 (20.1/mois) | 29.5 % | -0.187 | -17.8 | -3.75 | 21.6 | 20 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 3 pips | 210 (44.3/mois) | 49.5 % | -0.010 | -2.0 | -0.43 | 24.0 | 60 % |
| A Cassure Londres boîte 9:00-10:00, stop milieu, objectif heure de fin | 99 (20.9/mois) | 27.3 % | +0.320 | +31.7 | +6.68 | 24.8 | 60 % |
| C Repli EMA 20, objectif 1.0 R, marge stop 1 pips | 210 (44.3/mois) | 46.7 % | -0.067 | -14.0 | -2.96 | 20.0 | 20 % |
| C Repli EMA 20, objectif 1.5 R, marge stop 1 pips | 210 (44.3/mois) | 37.6 % | -0.062 | -13.1 | -2.76 | 30.0 | 60 % |
| C Repli EMA 20, objectif 2.0 R, marge stop 1 pips | 210 (44.3/mois) | 33.3 % | -0.005 | -1.1 | -0.23 | 25.0 | 40 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 3 pips | 312 (65.9/mois) | 47.4 % | -0.136 | -42.3 | -8.93 | 44.7 | 0 % |
| D Rebond Bollinger, objectif moyenne 20, marge stop 1 pips | 313 (66.1/mois) | 37.7 % | -0.188 | -58.8 | -12.40 | 66.1 | 0 % |

### Meilleure variante de chaque famille (choisie sur la 1re période)

- **A Cassure Londres boîte 1:00-9:00, stop autre bord, objectif 1.0 R** : choix +0.061 R/trade (106 trades), **test +0.008 R/trade** (84 trades, 53.6 % gagnants, +0.14 R/mois, mois positifs 60 %), prix mélangés -0.086 R/trade.
- **B Cassure New York boîte 14:30-15:00, stop autre bord, objectif heure de fin** : choix -0.015 R/trade (146 trades), **test +0.005 R/trade** (95 trades, 37.9 % gagnants, +0.11 R/mois, mois positifs 40 %), prix mélangés -0.026 R/trade.
- **C Repli EMA 20, objectif 2.0 R, marge stop 3 pips** : choix -0.066 R/trade (303 trades), **test +0.101 R/trade** (207 trades, 37.2 % gagnants, +4.41 R/mois, mois positifs 40 %), prix mélangés -0.258 R/trade.
- **D Rebond Bollinger, objectif moyenne 20, marge stop 3 pips** : choix -0.107 R/trade (456 trades), **test -0.136 R/trade** (312 trades, 47.4 % gagnants, -8.93 R/mois, mois positifs 0 %), prix mélangés -0.252 R/trade.

## Stratégie de la fiche : Cassure de Londres (boîte 1 h - 9 h, stop autre bord, objectif 1,5 R), 15 min

| Période | Trades | Gagnants | R moyen | R total | R / mois | Pire baisse (R) | Mois positifs | Pertes de suite max |
|---|---|---|---|---|---|---|---|---|
| 12/2024 - 05/2025 | 47 | 42.6 % | +0.033 | +1.5 | +0.33 | 6.6 | 50 % | 9 |
| 06/2025 - 11/2025 | 83 | 47.0 % | +0.039 | +3.3 | +0.56 | 5.7 | 50 % | 7 |
| 12/2025 - 05/2026 | 80 | 50.0 % | -0.065 | -5.2 | -0.89 | 11.7 | 33 % | 5 |
| 06/2026 - 11/2026 | 98 | 54.1 % | +0.062 | +6.0 | +1.04 | 4.0 | 67 % | 4 |
| **Tout** | 308 | 49.4 % | +0.018 | +5.6 | +0.25 | 15.9 | 50 % | 9 |

Stop moyen 28.1 pips (médiane 27.6, 10 % des trades > 38.7). Trade pris 308 jours sur 600 jours de cotation. Sorties : {'heure': 173, 'stop': 94, 'objectif': 41}. Heure du signal (Paris) : {9: 163, 10: 70, 11: 37, 12: 38}.

Prix mélangés (5 tirages) : R moyen -0.032, -0.014, -0.064, -0.076, -0.005.

## Meilleure sur période jamais vue (attention : ce choix-là regarde le test)

C Repli EMA 20, objectif 2.0 R, marge stop 3 pips en MINUTE_5.


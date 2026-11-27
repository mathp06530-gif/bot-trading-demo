# Labo n°5 « gros gains » : sorties, seuils, taille, plus de marchés (vote 4 h confirmé)

8 marchés d'origine, 20 marchés nouveaux. Frais de nuit Capital.com COMPTÉS. Réglage choisi sur 2021-11-27 -> 2024-11-27 (8 marchés d'origine), puis jugé ailleurs.
Essais comptés : 84 réglages x 28 marchés x (réel + 2 mélangés).

Lecture : réussite · gain moyen par trade après spread et frais de nuit · trades · marchés gagnants · gain cumulé par mois en % d'UNE mise (somme des marchés, une position à la fois par marché).

| Réglage | Choix 2021-2024 (8 marchés) | Jugé 2024-2026 (8 marchés) | Marchés NOUVEAUX 2021-2026 | Prix mélangés (réussite · gain) |
|---|---|---|---|---|
| 0.05|tenir 1 x 4 h (base actuelle) | 51.9 % · +0.010 % · 1506 trades · 5/8 marchés · +0.44 %/mois | 53.7 % · +0.012 % · 1034 trades · 5/8 marchés · +0.53 %/mois | 45.8 % · -0.053 % · 6590 trades · 6/20 marchés · -5.84 %/mois | 44.4 % · -0.061 % |
| 0.05|stop suiveur 1.5 ATR / max 6 x 4 h (CHOISI) | 46.0 % · +0.051 % · 1162 trades · 5/8 marchés · +1.68 %/mois | 44.7 % · +0.021 % · 804 trades · 5/8 marchés · +0.70 %/mois | 41.8 % · -0.070 % · 5140 trades · 7/20 marchés · -6.04 %/mois | 38.6 % · -0.347 % |
| 0.05|stop suiveur 1.0 ATR / max 12 x 4 h | 35.8 % · +0.046 % · 1132 trades · 6/8 marchés · +1.47 %/mois | 37.5 % · +0.010 % · 787 trades · 3/8 marchés · +0.33 %/mois | 32.4 % · -0.057 % · 5154 trades · 6/20 marchés · -4.96 %/mois | 22.9 % · -0.527 % |
| 0.05|stop suiveur 1.0 ATR / max 6 x 4 h | 39.4 % · +0.041 % · 1222 trades · 5/8 marchés · +1.42 %/mois | 40.4 % · +0.024 % · 845 trades · 6/8 marchés · +0.85 %/mois | 34.7 % · -0.060 % · 5426 trades · 5/20 marchés · -5.43 %/mois | 28.4 % · -0.434 % |
| 0.05|stop 1.5 ATR / objectif 3.0 ATR / max 6 x 4 h | 48.4 % · +0.039 % · 1160 trades · 4/8 marchés · +1.30 %/mois | 47.7 % · +0.018 % · 799 trades · 4/8 marchés · +0.59 %/mois | 44.0 % · -0.069 % · 5140 trades · 6/20 marchés · -5.99 %/mois | 43.2 % · -0.215 % |
| 0.05|stop suiveur 2.0 ATR / max 12 x 4 h | 43.0 % · +0.040 % · 996 trades · 4/8 marchés · +1.14 %/mois | 44.4 % · -0.001 % · 680 trades · 4/8 marchés · -0.04 %/mois | 42.2 % · -0.062 % · 4419 trades · 6/20 marchés · -4.57 %/mois | 37.7 % · -0.396 % |
| 0.05|tenir 3 x 4 h | 53.5 % · +0.028 % · 1332 trades · 5/8 marchés · +1.04 %/mois | 52.5 % · +0.001 % · 914 trades · 4/8 marchés · +0.00 %/mois | 47.7 % · -0.057 % · 5814 trades · 5/20 marchés · -5.61 %/mois | 48.2 % · -0.043 % |
| 0.05|stop 1.5 ATR / objectif 2.0 ATR / max 3 x 4 h | 52.5 % · +0.026 % · 1352 trades · 5/8 marchés · +1.00 %/mois | 52.1 % · +0.008 % · 922 trades · 5/8 marchés · +0.28 %/mois | 46.8 % · -0.064 % · 5896 trades · 5/20 marchés · -6.32 %/mois | 46.7 % · -0.108 % |
| 0.05|stop 1.5 ATR / objectif 3.0 ATR / max 3 x 4 h | 52.3 % · +0.026 % · 1346 trades · 5/8 marchés · +0.99 %/mois | 51.8 % · +0.023 % · 921 trades · 5/8 marchés · +0.89 %/mois | 46.5 % · -0.060 % · 5869 trades · 6/20 marchés · -5.95 %/mois | 46.0 % · -0.157 % |
| 0.05|stop 1.0 ATR / objectif 3.0 ATR / max 6 x 4 h | 41.7 % · +0.028 % · 1207 trades · 3/8 marchés · +0.97 %/mois | 42.3 % · +0.032 % · 826 trades · 5/8 marchés · +1.11 %/mois | 36.6 % · -0.061 % · 5350 trades · 6/20 marchés · -5.46 %/mois | 34.6 % · -0.305 % |
| 0.05|stop 2.0 ATR / objectif 2.0 ATR / max 3 x 4 h | 53.3 % · +0.023 % · 1346 trades · 5/8 marchés · +0.89 %/mois | 52.4 % · -0.005 % · 918 trades · 3/8 marchés · -0.20 %/mois | 47.7 % · -0.057 % · 5863 trades · 4/20 marchés · -5.58 %/mois | 48.1 % · -0.050 % |
| 0.05|stop 2.0 ATR / objectif 3.0 ATR / max 3 x 4 h | 53.1 % · +0.023 % · 1340 trades · 5/8 marchés · +0.86 %/mois | 52.1 % · +0.011 % · 917 trades · 3/8 marchés · +0.42 %/mois | 47.4 % · -0.053 % · 5837 trades · 7/20 marchés · -5.14 %/mois | 47.4 % · -0.100 % |
| 0.05|stop suiveur 1.5 ATR / max 12 x 4 h | 39.1 % · +0.027 % · 1037 trades · 3/8 marchés · +0.79 %/mois | 39.9 % · +0.003 % · 720 trades · 4/8 marchés · +0.07 %/mois | 36.7 % · -0.057 % · 4656 trades · 8/20 marchés · -4.43 %/mois | 30.2 % · -0.489 % |
| 0.05|tenir 2 x 4 h | 52.0 % · +0.019 % · 1403 trades · 6/8 marchés · +0.75 %/mois | 53.6 % · -0.009 % · 954 trades · 6/8 marchés · -0.39 %/mois | 46.7 % · -0.056 % · 6125 trades · 6/20 marchés · -5.79 %/mois | 46.9 % · -0.057 % |
| 0.05|stop suiveur 2.0 ATR / max 6 x 4 h | 48.6 % · +0.019 % · 1147 trades · 5/8 marchés · +0.62 %/mois | 49.3 % · +0.003 % · 781 trades · 4/8 marchés · +0.09 %/mois | 45.3 % · -0.070 % · 5039 trades · 4/20 marchés · -5.93 %/mois | 44.2 % · -0.253 % |
| 0.05|stop 1.0 ATR / objectif 2.0 ATR / max 6 x 4 h | 42.9 % · +0.016 % · 1243 trades · 3/8 marchés · +0.58 %/mois | 42.6 % · -0.014 % · 848 trades · 4/8 marchés · -0.52 %/mois | 37.4 % · -0.079 % · 5478 trades · 5/20 marchés · -7.27 %/mois | 36.6 % · -0.229 % |

Réglages jetés (gagnants aussi sur prix mélangés) : 12. Réglages sans gain sur la période de choix : 59 sur 84.

## En euros (réglage choisi, jugé hors période de choix)

Capital x levier partagé entre les marchés (ex. 100 € x 5 = 500 € répartis sur les marchés), une position à la fois par marché. Capital.com : jusqu'à 20x sur indices et or, 30x sur devises. Gain ET pire baisse sont multipliés par le levier.

| Où | Levier | 100 € : par mois | 1 000 € : par mois | Pire baisse (en % de la mise, par marché) |
|---|---|---|---|---|
| 8 marchés, 2024-2026 | 1x | +0.09 € | +0.88 € | 34.6 % |
| 8 marchés, 2024-2026 | 5x | +0.44 € | +4.39 € | 173.1 % |
| 8 marchés, 2024-2026 | 10x | +0.88 € | +8.79 € | 346.2 % |
| marchés nouveaux, 2021-2026 | 1x | -0.30 € | -3.02 € | 145.3 % |
| marchés nouveaux, 2021-2026 | 5x | -1.51 € | -15.11 € | 726.7 % |
| marchés nouveaux, 2021-2026 | 10x | -3.02 € | -30.21 € | 1453.4 % |

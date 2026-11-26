# IA qui prédisent la direction : résultats sur données jamais vues

40 couples marché x unité, 369 essais (marché x unité x horizon x IA).
Une IA est « solide » si : au moins 100 trades, gain net positif sur les deux moitiés du test, et t >= 3.82 (seuil corrigé pour le nombre d'essais).

## Précision moyenne par IA (toutes bougies, tous marchés)

| IA | précision | précision quand sûre (10 %) | trades | gain net total (%) |
|---|---|---|---|---|
| empilement | 51.59 % | 53.37 % | 19951 | -213.9 |
| foret | 51.33 % | 52.85 % | 18274 | -456.8 |
| lightgbm | 51.09 % | 52.75 % | 14863 | -270.5 |
| logistique | 51.30 % | 52.68 % | 16570 | -240.8 |
| lstm | 51.33 % | 52.58 % | 17466 | -354.5 |
| neurones | 51.09 % | 52.36 % | 20325 | -353.1 |
| vote | 51.46 % | 53.14 % | 15009 | -296.2 |

## Précision par unité et horizon (moyenne des marchés, meilleure IA)

| unité | horizon (bougies) | meilleure IA | précision | quand sûre | gain net |
|---|---|---|---|---|---|
| HOUR | 1 | empilement | 51.84 % | 53.86 % | -27.4 % |
| HOUR | 4 | empilement | 52.25 % | 55.90 % | +6.0 % |
| HOUR_4 | 1 | empilement | 52.31 % | 53.69 % | -15.5 % |
| HOUR_4 | 6 | lstm | 51.97 % | 52.73 % | -96.1 % |
| MINUTE | 1 | vote | 51.10 % | 50.61 % | -1.7 % |
| MINUTE | 5 | vote | 50.83 % | 48.57 % | -2.4 % |
| MINUTE_15 | 1 | empilement | 51.73 % | 54.28 % | -16.1 % |
| MINUTE_15 | 4 | empilement | 51.90 % | 54.50 % | -35.4 % |
| MINUTE_5 | 1 | empilement | 51.32 % | 53.48 % | -0.6 % |
| MINUTE_5 | 12 | foret | 51.45 % | 52.94 % | -25.8 % |

## Précision par marché (vote, horizon 1 bougie)

| marché | unité | précision | quand sûre | spread % | gain net |
|---|---|---|---|---|---|
| BTCUSD | HOUR | 51.77 % | 57.07 % | 0.067 | -6.7 % |
| BTCUSD | HOUR_4 | 54.26 % | 57.21 % | 0.262 | -16.0 % |
| BTCUSD | MINUTE | 51.81 % | 55.01 % | 0.066 | +0.0 % |
| BTCUSD | MINUTE_15 | 52.14 % | 55.53 % | 0.058 | +0.0 % |
| BTCUSD | MINUTE_5 | 51.57 % | 55.92 % | 0.066 | +0.0 % |
| ETHUSD | HOUR | 52.15 % | 57.08 % | 0.087 | -15.2 % |
| ETHUSD | HOUR_4 | 53.35 % | 55.36 % | 0.302 | +10.8 % |
| ETHUSD | MINUTE | 51.80 % | 54.76 % | 0.078 | +0.0 % |
| ETHUSD | MINUTE_15 | 53.23 % | 57.91 % | 0.071 | -13.2 % |
| ETHUSD | MINUTE_5 | 52.63 % | 56.64 % | 0.078 | +0.0 % |
| EURUSD | HOUR | 51.29 % | 53.80 % | 0.006 | -1.5 % |
| EURUSD | HOUR_4 | 51.07 % | 52.67 % | 0.006 | -4.4 % |
| EURUSD | MINUTE | 50.54 % | 48.05 % | 0.006 | +0.0 % |
| EURUSD | MINUTE_15 | 51.26 % | 54.26 % | 0.006 | +0.0 % |
| EURUSD | MINUTE_5 | 50.94 % | 53.67 % | 0.006 | +0.0 % |
| GOLD | HOUR | 50.79 % | 53.82 % | 0.011 | -0.4 % |
| GOLD | HOUR_4 | 50.93 % | 53.82 % | 0.015 | -6.6 % |
| GOLD | MINUTE | 51.16 % | 50.67 % | 0.014 | +0.0 % |
| GOLD | MINUTE_15 | 51.69 % | 53.47 % | 0.009 | +2.1 % |
| GOLD | MINUTE_5 | 50.91 % | 51.50 % | 0.011 | +0.0 % |
| OIL_CRUDE | HOUR | 50.46 % | 52.59 % | 0.045 | -3.9 % |
| OIL_CRUDE | HOUR_4 | 50.60 % | 50.60 % | 0.049 | -25.1 % |
| OIL_CRUDE | MINUTE | 51.11 % | 51.89 % | 0.046 | +0.0 % |
| OIL_CRUDE | MINUTE_15 | 51.03 % | 50.91 % | 0.047 | -5.5 % |
| OIL_CRUDE | MINUTE_5 | 51.38 % | 52.46 % | 0.045 | -2.1 % |
| SILVER | HOUR | 51.18 % | 54.79 % | 0.080 | +7.2 % |
| SILVER | HOUR_4 | 51.21 % | 53.49 % | 0.100 | +0.0 % |
| SILVER | MINUTE | 50.88 % | 49.33 % | 0.120 | +0.0 % |
| SILVER | MINUTE_15 | 51.05 % | 54.96 % | 0.079 | -5.8 % |
| SILVER | MINUTE_5 | 51.11 % | 52.73 % | 0.084 | +0.0 % |
| US100 | HOUR | 52.61 % | 55.27 % | 0.008 | +5.9 % |
| US100 | HOUR_4 | 52.50 % | 58.50 % | 0.012 | +21.5 % |
| US100 | MINUTE | 50.74 % | 46.32 % | 0.007 | -1.7 % |
| US100 | MINUTE_15 | 51.31 % | 52.38 % | 0.007 | -1.8 % |
| US100 | MINUTE_5 | 50.67 % | 51.95 % | 0.006 | -0.3 % |
| US500 | HOUR | 52.60 % | 55.72 % | 0.008 | +5.4 % |
| US500 | HOUR_4 | 52.77 % | 52.32 % | 0.016 | +0.7 % |
| US500 | MINUTE | 50.75 % | 48.88 % | 0.008 | +0.0 % |
| US500 | MINUTE_15 | 51.39 % | 54.37 % | 0.008 | +0.1 % |
| US500 | MINUTE_5 | 51.04 % | 53.71 % | 0.008 | +0.0 % |

## Solides

Aucune.

## 15 meilleurs t (avant correction)

| marché | unité | H | IA | précision trades | trades | gain net | moitié 1 | moitié 2 | t |
|---|---|---|---|---|---|---|---|---|---|
| US100 | HOUR | 1 | lightgbm | 55.43 % | 737 | +18.25 % | +1.62 | +16.63 | 2.41 |
| GOLD | MINUTE_15 | 4 | logistique | 58.43 % | 178 | +12.68 % | +13.86 | -1.18 | 2.05 |
| SILVER | HOUR | 4 | empilement | 57.22 % | 194 | +36.53 % | +41.70 | -5.17 | 2.01 |
| US100 | MINUTE_15 | 4 | lightgbm | 54.46 % | 620 | +12.31 % | +1.04 | +11.27 | 1.59 |
| US500 | HOUR_4 | 1 | logistique | 60.51 % | 195 | +9.36 % | +0.00 | +9.36 | 1.5 |
| GOLD | HOUR_4 | 6 | empilement | 54.69 % | 437 | +46.48 % | +2.45 | +44.03 | 1.49 |
| US500 | MINUTE_15 | 4 | lightgbm | 53.98 % | 176 | +4.32 % | +0.84 | +3.48 | 1.48 |
| US500 | HOUR | 1 | foret | 54.1 % | 184 | +4.10 % | -0.04 | +4.14 | 1.45 |
| GOLD | HOUR | 4 | foret | 54.29 % | 676 | +26.45 % | +22.76 | +3.69 | 1.39 |
| US100 | HOUR | 4 | neurones | 58.11 % | 604 | +16.54 % | +0.34 | +16.20 | 1.36 |
| US500 | HOUR | 1 | vote | 54.88 % | 546 | +5.44 % | -0.77 | +6.21 | 1.26 |
| US500 | HOUR | 1 | empilement | 54.58 % | 262 | +3.98 % | +0.60 | +3.37 | 1.24 |
| US500 | HOUR_4 | 6 | lightgbm | 55.5 % | 200 | +18.46 % | +13.24 | +5.21 | 1.23 |
| US100 | HOUR_4 | 1 | lightgbm | 54.94 % | 830 | +21.15 % | +15.58 | +5.57 | 1.23 |
| US100 | HOUR_4 | 1 | lstm | 56.76 % | 935 | +24.55 % | +10.72 | +13.83 | 1.22 |

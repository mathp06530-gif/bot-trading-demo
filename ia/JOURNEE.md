# Stratégie maison « Journée » : gros trades ouverts et fermés dans la journée (aucun frais de nuit)

8 marchés, bougies 15 min Capital.com (2024-12-30 -> 2026-11-28). Réglages choisis avant le 2025-07-01, jugés après. Coûts : vrai spread. Toutes les positions fermées avant 22 h UTC.
Essais comptés : 60 réglages x 8 marchés (réel + prix mélangés).

| Réglage (part plus sûre · filtre · fenêtre · sortie) | Choix | Jugé (jamais vu) | Marchés gagnants (jugé) | Prix mélangés |
|---|---|---|---|---|
| 0.1|aucun|7h-19h UTC|garder jusqu'à 21 h 45 UTC **(CHOISI)** | 51.2 % · +0.0649 % · 668 trades | 48.1 % · -0.0233 % · 2640 trades | 2/8 | 50.3 % · -0.0282 % · 3440 trades |
| 0.1|accord_4h|7h-19h UTC|garder jusqu'à 21 h 45 UTC | 53.3 % · +0.0700 % · 523 trades | 49.0 % · -0.0158 % · 2159 trades | 2/8 | 47.7 % · -0.0389 % · 2644 trades |
| 0.05|aucun|7h-19h UTC|garder jusqu'à 21 h 45 UTC | 52.9 % · +0.0541 % · 501 trades | 48.1 % · +0.0178 % · 2083 trades | 4/8 | 49.2 % · -0.0263 % · 2758 trades |
| 0.05|accord_4h|7h-19h UTC|garder jusqu'à 21 h 45 UTC | 54.3 % · +0.0613 % · 376 trades | 48.3 % · -0.0009 % · 1607 trades | 3/8 | 48.1 % · -0.0301 % · 1886 trades |
| 0.1|aucun|13h-19h UTC (séance US)|stop suiveur 3.0 ATR | 43.4 % · +0.0387 % · 488 trades | 39.3 % · -0.0399 % · 2122 trades | 2/8 | 41.3 % · -0.0963 % · 2718 trades |
| 0.1|accord_4h|13h-19h UTC (séance US)|stop suiveur 2.0 ATR | 41.5 % · +0.0498 % · 342 trades | 38.2 % · -0.0296 % · 1551 trades | 2/8 | 32.2 % · -0.1632 % · 1728 trades |
| 0.1|accord_4h|13h-19h UTC (séance US)|stop suiveur 3.0 ATR | 44.7 % · +0.0419 % · 342 trades | 41.0 % · -0.0223 % · 1551 trades | 3/8 | 40.5 % · -0.1125 % · 1728 trades |
| 0.1|accord_4h|13h-19h UTC (séance US)|stop 1.5 ATR / objectif 3.0 ATR | 39.8 % · +0.0382 % · 342 trades | 35.5 % · -0.0388 % · 1551 trades | 2/8 | 34.2 % · -0.1123 % · 1728 trades |
| 0.1|aucun|13h-19h UTC (séance US)|stop 1.5 ATR / objectif 3.0 ATR | 37.9 % · +0.0222 % · 488 trades | 33.5 % · -0.0459 % · 2122 trades | 0/8 | 34.8 % · -0.0925 % · 2718 trades |
| 0.1|aucun|13h-19h UTC (séance US)|stop suiveur 2.0 ATR | 40.2 % · +0.0152 % · 488 trades | 36.0 % · -0.0353 % · 2122 trades | 1/8 | 32.6 % · -0.1416 % · 2718 trades |
| 0.1|aucun|7h-19h UTC|stop suiveur 3.0 ATR | 36.4 % · +0.0073 % · 668 trades | 35.6 % · -0.0243 % · 2640 trades | 1/8 | 32.8 % · -0.1713 % · 3440 trades |
| 0.05|accord_4h|13h-19h UTC (séance US)|stop 1.5 ATR / objectif 3.0 ATR | 38.9 % · +0.0224 % · 203 trades | 36.8 % · -0.0409 % · 1068 trades | 2/8 | 33.2 % · -0.1112 % · 1116 trades |
| 0.1|aucun|13h-19h UTC (séance US)|garder jusqu'à 21 h 45 UTC | 49.0 % · +0.0086 % · 488 trades | 46.1 % · -0.0352 % · 2122 trades | 3/8 | 49.2 % · -0.0033 % · 2718 trades |
| 0.1|aucun|7h-19h UTC|stop suiveur 2.0 ATR | 33.8 % · +0.0063 % · 668 trades | 33.3 % · -0.0338 % · 2640 trades | 0/8 | 26.5 % · -0.1833 % · 3440 trades |
| 0.1|accord_4h|13h-19h UTC (séance US)|garder jusqu'à 21 h 45 UTC | 50.0 % · +0.0078 % · 342 trades | 47.5 % · -0.0168 % · 1551 trades | 2/8 | 47.3 % · -0.0310 % · 1728 trades |
| 0.05|aucun|13h-19h UTC (séance US)|stop 1.5 ATR / objectif 3.0 ATR | 37.1 % · +0.0073 % · 294 trades | 35.3 % · -0.0386 % · 1455 trades | 2/8 | 34.9 % · -0.0949 % · 1846 trades |
| 0.05|accord_4h|13h-19h UTC (séance US)|stop suiveur 2.0 ATR | 40.9 % · +0.0103 % · 203 trades | 39.3 % · -0.0231 % · 1068 trades | 2/8 | 33.0 % · -0.1427 % · 1116 trades |
| 0.02|accord_4h|7h-19h UTC|garder jusqu'à 21 h 45 UTC | 53.2 % · +0.0012 % · 222 trades | 50.1 % · +0.0153 % · 909 trades | 6/8 | 49.5 % · -0.0335 % · 1055 trades |
| 0.05|aucun|7h-19h UTC|stop suiveur 2.0 ATR | 34.5 % · -0.0021 % · 501 trades | 35.3 % · -0.0186 % · 2083 trades | 3/8 | 27.7 % · -0.1786 % · 2758 trades |
| 0.1|accord_4h|7h-19h UTC|stop suiveur 3.0 ATR | 38.6 % · -0.0026 % · 523 trades | 36.1 % · -0.0217 % · 2159 trades | 2/8 | 32.7 % · -0.1718 % · 2644 trades |

Réglages gagnants sur la période de choix : 18 sur 60.

## Tiroir fin de séance US100 / US500 (règle fixe)

Choix : 51.5 % · +0.0067 % · 487 trades · Jugé : 52.1 % · +0.0082 % · 1419 trades · Prix mélangés : 45.5 % · -0.0072 % · 1907 trades

## Portefeuille (réglage choisi + tiroir fin de séance), période JAMAIS VUE seulement

Capital partagé : chaque trade mise capital x levier / 10 (au plus 10 positions en même temps). Intérêts composés. Ruine = tomber sous 50 % (ou 10 %) du capital au moins une fois dans l'année (2000 années tirées au hasard dans les vraies journées).

| Levier | 100 € : par mois (1er mois) | 1 000 € : par mois (1er mois) | % par mois | Pire baisse | Mois négatifs | Année médiane | Risque -50 % | Risque -90 % |
|---|---|---|---|---|---|---|---|---|
| x1 | -0.31 € | -3.13 € | -0.31 % | -7.7 % | 7/17 | -3.8 % | 0.0 % | 0.0 % |
| x3 | -1.04 € | -10.41 € | -1.04 % | -22.6 % | 7/17 | -12.0 % | 0.1 % | 0.0 % |
| x5 | -1.90 € | -19.03 € | -1.90 % | -36.5 % | 7/17 | -20.8 % | 11.9 % | 0.0 % |
| x10 | -4.64 € | -46.41 € | -4.64 % | -65.0 % | 8/17 | -43.7 % | 57.1 % | 0.8 % |

Contrôle prix mélangés, même réglage, x5 : -2.52 % par mois, pire baisse -50.1 %.

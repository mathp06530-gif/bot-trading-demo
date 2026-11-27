# Le vote 4 h de l'IA comme filtre sur la Cassure 4 h du bot (or, argent)

Moteur du bot (spread, stop garanti, frais de nuit, stop qui se resserre). R = 1 % du capital risqué par trade. Filtre choisi sur la 1re moitié, jugé sur la 2e. « Hasard » = 500 filtres qui refusent la même part de cassures au hasard.

## GOLD (203 cassures avec un vote, 2018-11-01 -> 2026-11-27)

| Filtre | Cassures refusées | 1re moitié (choix) | 2e moitié (jugée) | Tout | Hasard (même part refusée) : R médian tout | Mieux que le hasard |
|---|---|---|---|---|---|---|
| sans filtre (bot actuel) | 0/203 | -5.3 R · 108 trades · 36 % · pire -14.5 R | +40.1 R · 98 trades · 46 % · pire -7.8 R | +34.8 R · 206 trades · 41 % · pire -14.5 R | — | — |
| accord | 12/203 | -1.9 R · 102 trades · 37 % · pire -12.4 R | +42.5 R · 92 trades · 47 % · pire -8.0 R | +40.6 R · 194 trades · 42 % · pire -12.4 R | +33.8 R | 90 % des hasards |
| accord_sur | 58/203 | -3.0 R · 71 trades · 35 % · pire -10.0 R | +33.7 R · 77 trades · 44 % · pire -6.8 R | +30.7 R · 148 trades · 40 % · pire -10.0 R | +24.5 R | 66 % des hasards |
| pas_contre_fort | 2/203 | -5.3 R · 108 trades · 36 % · pire -14.5 R | +40.5 R · 96 trades · 46 % · pire -7.8 R | +35.2 R · 204 trades · 41 % · pire -14.5 R | +34.8 R | 56 % des hasards |

## SILVER (202 cassures avec un vote, 2018-11-01 -> 2026-11-27)

| Filtre | Cassures refusées | 1re moitié (choix) | 2e moitié (jugée) | Tout | Hasard (même part refusée) : R médian tout | Mieux que le hasard |
|---|---|---|---|---|---|---|
| sans filtre (bot actuel) | 0/202 | +13.3 R · 99 trades · 43 % · pire -6.2 R | +14.7 R · 106 trades · 41 % · pire -7.9 R | +28.0 R · 205 trades · 42 % · pire -7.9 R | — | — |
| accord | 18/202 | +13.3 R · 91 trades · 44 % · pire -5.2 R | +15.7 R · 96 trades · 41 % · pire -6.5 R | +29.0 R · 187 trades · 42 % · pire -6.5 R | +26.9 R | 67 % des hasards |
| accord_sur | 63/202 | +1.6 R · 66 trades · 41 % · pire -6.4 R | +9.6 R · 76 trades · 40 % · pire -8.1 R | +11.2 R · 142 trades · 40 % · pire -8.1 R | +20.6 R | 17 % des hasards |
| pas_contre_fort | 0/202 | +13.3 R · 99 trades · 43 % · pire -6.2 R | +14.7 R · 106 trades · 41 % · pire -7.9 R | +28.0 R · 205 trades · 42 % · pire -7.9 R | — | — |

## Panier or + argent

| Filtre | 1re moitié | 2e moitié | Tout | pire baisse (pire des 2) |
|---|---|---|---|---|
| sans filtre (bot actuel) | +8.0 R | +54.8 R | +62.8 R | -14.5 R |
| accord | +11.4 R | +58.1 R | +69.5 R | -12.4 R |
| accord_sur | -1.4 R | +43.3 R | +41.9 R | -10.0 R |
| pas_contre_fort | +8.0 R | +55.2 R | +63.2 R | -14.5 R |

En euros : 1 R = 1 % du capital au risque du bot (Cassure : 3 %/trade en direct -> 1 R x 3). Sur 100 €, +10 R à 1 % = +10 € ; à 3 % = +30 €.

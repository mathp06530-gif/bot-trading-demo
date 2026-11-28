# Amplitude : ne parier que si le mouvement prévu dépasse le spread

Question : prévoir la taille du prochain mouvement, et ne jouer que lorsque ce mouvement, du bon côté,
dépasse le spread et les frais de nuit.

Deux règles, figées avant de lire la période jugée (après le 28/11/2025) :
- **pessimiste** : on achète seulement si le quartile bas (25 %) du mouvement prévu est déjà au-dessus du coût,
  on vend seulement si le quartile haut (75 %) est déjà en dessous de moins le coût. Aucun seuil à régler.
- **médiane** : on suit le signe du mouvement médian prévu, seulement s'il dépasse k fois le coût.
  k est choisi dans {1 ; 1,5 ; 2 ; 3} sur le passé du mois. S'il n'y a aucun k gagnant dans le passé, on s'abstient.

À 60 min et à 4 h, la règle du tableau détaillé est celle qui a le meilleur gain sur la période de choix,
à condition que les prix mélangés y restent ≤ 53 %. À 15 min l'historique est trop court pour choisir :
on publie la règle pessimiste.

## Verdict

- **15 min : rejetée.** La règle pessimiste ne trouve aucun moment où le mauvais cas du
  mouvement prévu dépasse le spread. La médiane, elle, parie et perd -0,0203 % par trade (48,5 % de bonnes réponses, 0/5 marchés, prix mélangés 53,8 %).
- **60min : rejetée** (règle médiane). Hors échantillon : 52,1 % de bonnes réponses, -0,0228 % par trade, 58 trades/mois, 2/8 marchés gagnants, sens majoritaire 51,2 %, prix mélangés 52,0 %.
- **4h : rejetée** (règle médiane). Hors échantillon : 50,2 % de bonnes réponses, -0,0454 % par trade, 35 trades/mois, 0/7 marchés gagnants, sens majoritaire 52,4 %, prix mélangés 49,6 %.

En une phrase : prévoir l'amplitude ne suffit pas à passer le spread. À 15 min le modèle prudent
se tait, et le modèle qui parle perd à peu près le spread. À 60 min et à 4 h, c'est la même chose
sur un an jamais utilisé pour choisir la règle.

## Comment c'est mesuré

Entraînement sur le passé seulement, un trou d'au moins une bougie (le résultat de la dernière bougie
d'entraînement est déjà connu). Période de choix : avant le 28/11/2025. Période jugée : après.
Une position à la fois : on entre à la clôture et on sort à la clôture suivante, donc chaque trade est
un instant distinct (pas le même mouvement compté plusieurs fois). Le total « instants » additionne
les marchés : la même heure sur l'or et sur l'euro compte deux instants.

Les bougies Capital.com sont dans le cache GitHub Actions, pas dans le dépôt. Les prix utilisés ici
viennent de Yahoo Finance (euro et livre au comptant ; or, argent, pétrole, Nasdaq et S&P en futures ;
DAX au comptant), du 29/11/2024 au 27/11/2026 en 1 h, et ~60 jours seulement en 15 min.
Le spread facturé est le spread **médian** mesuré chez Capital.com dans `ia/resultats.json`.
GBPUSD (0,010 %) et DE40 (0,007 %) viennent de `ia/FRAIS_COURTIERS.md`. Ce n'est pas le spread de
chaque minute : aux heures où Capital.com l'élargit, le coût réel serait un peu plus haut.
Les frais de nuit sont la moyenne achat/vente publiée, payée des deux côtés, à chaque passage de 22 h UTC
(même calcul que `ia/predire.py`).

Contrôle des prix mélangés : on permute les rendements, on garde le même spread, on refait toute la
chaîne. La réussite doit rester autour de 50 %. Au-dessus de 53 %, la règle est rejetée.
Le sens majoritaire est la part du sens le plus fréquent sur les trades jugés. « Majorité passée »
parie, sur les mêmes instants, le sens qui gagnait le plus souvent avant la période. « Sens seul »
suit la médiane prévue à chaque bougie, sans filtre d'amplitude.

Le vieux filtre « amplitude ≥ 3 × spread » du labo multi-cerveaux demandait seulement « est-ce que ça
va beaucoup bouger », puis devinait le sens. Il est déjà perdu. Ici le mouvement **du côté parié**
doit dépasser le coût.

## 15min — rejetée

Règle publiée : **pessimiste** (aucun seuil). Elle ne parie sur aucun marché.
Le détail marché ci-dessous est donc la **médiane** (non retenue, et perdante).

| Période | Réussite | Gain après spread et frais | Trades (instants) | Trades/mois | Sens majoritaire | Gain du sens majoritaire passé | Sens seul (gain) | Marchés gagnants | Mois positifs | Prix mélangés |
|---|---|---|---|---|---|---|---|---|---|---|
| Choix (avant le 28/11/2025) | ne parie pas | — | 0 | 0 | — | — | — | — | — | — |
| Jugé (après le 28/11/2025) | ne parie pas | — | 0 | 0 | — | — | — | — | — | — |

Les deux règles sur la période jugée. Celle qui n'a pas été retenue sur le choix ne confirme rien.

| Règle | Réussite | Gain | Trades/mois | Marchés gagnants | Prix mélangés |
|---|---|---|---|---|---|
| pessimiste | trop peu de trades (0) | — | — | — | — |
| médiane | 48,5 % | -0,0203 % | 464 | 0/5 | 53,8 % |

Détail par marché, règle **mediane**, période jugée.

| Marché | Réussite | Gain | Trades | Trades/mois | Sens majoritaire | Gain majorité passée | Instants | Mois + | Prix mélangés | Coût moyen |
|---|---|---|---|---|---|---|---|---|---|---|
| GOLD | trop peu de trades (0) | — | 0 | — | — | — | 0 | — | — | 0.0094 % |
| SILVER | trop peu de trades (0) | — | 0 | — | — | — | 0 | — | — | 0.0793 % |
| OIL_CRUDE | 45,9 % | -0,0751 % | 403 | 491 | 55,3 % | — | 403 | 0/1 | — | 0.0474 % |
| US100 | 50,3 % | -0,0048 % | 579 | 705 | 51,1 % | — | 579 | 0/1 | 52,2 % | 0.0072 % |
| US500 | 50,6 % | -0,0053 % | 180 | 219 | 52,2 % | — | 180 | 0/1 | 51,6 % | 0.0078 % |
| DE40 | 46,8 % | -0,0088 % | 376 | 458 | 56,1 % | — | 376 | 0/1 | 52,7 % | 0.0070 % |
| EURUSD | 49,0 % | -0,0073 % | 367 | 447 | 52,0 % | — | 367 | 0/1 | — | 0.0059 % |
| GBPUSD | trop peu de trades (0) | — | 0 | — | — | — | 0 | — | — | 0.0100 % |
Prix mélangés au-dessus de 53 % (ces lignes ne comptent pas comme un signal) : GOLD (58,6 %).

## 60min — rejetée

Règle retenue sur la période de choix : **mediane** (gain de choix -0,0177 %).

| Période | Réussite | Gain après spread et frais | Trades (instants) | Trades/mois | Sens majoritaire | Gain du sens majoritaire passé | Sens seul (gain) | Marchés gagnants | Mois positifs | Prix mélangés |
|---|---|---|---|---|---|---|---|---|---|---|
| Choix (avant le 28/11/2025) | 49,8 % | -0,0177 % | 2778 (2778) | 58 | 54,7 % | -0,0212 % | -0,0237 % | 1/7 | 5/17 | 49,3 %, gain -0,0165 % |
| Jugé (après le 28/11/2025) | 52,1 % | -0,0228 % | 5051 (5051) | 58 | 51,2 % | -0,0264 % | -0,0176 % | 2/8 | 33/61 | 52,0 %, gain +0,0167 % |

Les deux règles sur la période jugée. Celle qui n'a pas été retenue sur le choix ne confirme rien.

| Règle | Réussite | Gain | Trades/mois | Marchés gagnants | Prix mélangés |
|---|---|---|---|---|---|
| pessimiste | trop peu de trades (0) | — | — | — | — |
| médiane | 52,1 % | -0,0228 % | 58 | 2/8 | 52,0 % |

Détail par marché, règle **mediane**, période jugée.

| Marché | Réussite | Gain | Trades | Trades/mois | Sens majoritaire | Gain majorité passée | Instants | Mois + | Prix mélangés | Coût moyen |
|---|---|---|---|---|---|---|---|---|---|---|
| GOLD | 49,3 % | -0,0205 % | 477 | 40 | 50,9 % | -0,0187 % | 477 | 4/7 | 51,4 % | 0.0112 % |
| SILVER | 49,5 % | -0,0679 % | 204 | 23 | 50,5 % | -0,0679 % | 204 | 0/4 | trop peu (16) | 0.0800 % |
| OIL_CRUDE | 50,4 % | -0,0959 % | 450 | 38 | 50,4 % | -0,0990 % | 450 | 3/5 | 59,7 % | 0.0454 % |
| US100 | 51,2 % | +0,0042 % | 1239 | 127 | 50,6 % | -0,0065 % | 1239 | 6/9 | 51,1 % | 0.0083 % |
| US500 | 52,2 % | +0,0078 % | 876 | 81 | 53,4 % | +0,0036 % | 876 | 7/11 | 50,9 % | 0.0082 % |
| DE40 | 50,1 % | -0,0084 % | 814 | 69 | 50,9 % | -0,0068 % | 814 | 3/8 | 50,6 % | 0.0070 % |
| EURUSD | 54,7 % | -0,0001 % | 907 | 76 | 50,7 % | -0,0056 % | 907 | 7/12 | 53,0 % | 0.0057 % |
| GBPUSD | 59,5 % | -0,0019 % | 84 | 11 | 52,4 % | -0,0106 % | 84 | 3/5 | trop peu (9) | 0.0101 % |

Gain positif sur la période jugée : US100 (+0,0042 %), US500 (+0,0078 %).
Prix mélangés au-dessus de 53 % (ces lignes ne comptent pas comme un signal) : OIL_CRUDE (59,7 %), EURUSD (53,0 %).

## 4h — rejetée

Règle retenue sur la période de choix : **mediane** (gain de choix -0,0578 %).
DE40 en 4 h : 452 bougies utilisables (le DAX ne cote pas la nuit), sous le minimum de 500
pour entraîner. Ce marché n'entre pas dans ce tableau.

| Période | Réussite | Gain après spread et frais | Trades (instants) | Trades/mois | Sens majoritaire | Gain du sens majoritaire passé | Sens seul (gain) | Marchés gagnants | Mois positifs | Prix mélangés |
|---|---|---|---|---|---|---|---|---|---|---|
| Choix (avant le 28/11/2025) | 47,8 % | -0,0578 % | 1233 (1233) | 36 | 53,2 % | -0,0194 % | -0,0347 % | 0/6 | 5/19 | 50,8 %, gain -0,0287 % |
| Jugé (après le 28/11/2025) | 50,2 % | -0,0454 % | 2545 (2545) | 35 | 52,4 % | -0,0353 % | -0,0379 % | 0/7 | 20/46 | 49,6 %, gain -0,0146 % |

Les deux règles sur la période jugée. Celle qui n'a pas été retenue sur le choix ne confirme rien.

| Règle | Réussite | Gain | Trades/mois | Marchés gagnants | Prix mélangés |
|---|---|---|---|---|---|
| pessimiste | trop peu de trades (1) | — | — | — | — |
| médiane | 50,2 % | -0,0454 % | 35 | 0/7 | 49,6 % |

Détail par marché, règle **mediane**, période jugée.

| Marché | Réussite | Gain | Trades | Trades/mois | Sens majoritaire | Gain majorité passée | Instants | Mois + | Prix mélangés | Coût moyen |
|---|---|---|---|---|---|---|---|---|---|---|
| GOLD | 47,3 % | -0,0066 % | 351 | 36 | 51,8 % | -0,0139 % | 351 | 3/5 | 48,0 % | 0.0157 % |
| SILVER | 52,0 % | -0,1485 % | 148 | 15 | 52,0 % | -0,1485 % | 148 | 0/2 | 47,6 % | 0.1010 % |
| OIL_CRUDE | 51,3 % | -0,1229 % | 232 | 34 | 50,9 % | -0,0723 % | 232 | 1/4 | 53,2 % | 0.0506 % |
| US100 | 49,6 % | -0,0127 % | 718 | 67 | 52,1 % | +0,0016 % | 718 | 5/10 | 50,9 % | 0.0140 % |
| US500 | 51,1 % | -0,0039 % | 472 | 40 | 53,0 % | +0,0180 % | 472 | 5/11 | 48,0 % | 0.0174 % |
| EURUSD | 49,6 % | -0,0030 % | 508 | 43 | 53,3 % | -0,0086 % | 508 | 4/9 | 53,9 % | 0.0061 % |
| GBPUSD | 50,9 % | -0,0202 % | 116 | 10 | 53,4 % | -0,0233 % | 116 | 2/5 | 45,4 % | 0.0106 % |
Prix mélangés au-dessus de 53 % (ces lignes ne comptent pas comme un signal) : OIL_CRUDE (53,2 %), EURUSD (53,9 %).

## Lecture

Confirmée : gain jugé positif, au moins 6 marchés sur 8, réussite au-dessus du sens majoritaire,
assez de trades, prix mélangés ≤ 53 %, et la période de choix était déjà positive.
Prometteuse : gain jugé positif, avec un contrôle qui manque.
Rejetée : gain négatif ou nul, ou presque aucun trade, ou prix mélangés au-dessus de 53 %.

À 60 min, le sens seul perd -0,0176 % par trade et la règle retenue perd -0,0228 % : le filtre d'amplitude retire des trades, la perte reste.
À 4 h la réussite jugée (50,2 %) se compare au sens majoritaire (52,4 %).
Sur les prix mélangés à 60 min, le gain est +0,0167 % parce que la permutation
garde la hausse de fond de l'or et des indices, et la réussite est 52,0 %. Le contrôle de réussite reste sous 53 %, et le gain réel est négatif.

## Prochaine variante (pas lancée, aucun ordre)

Le vote 4 h déjà confirmé (5 % les plus sûrs, +0,013 à +0,023 % par trade) reste la piste qui tient.
La règle pessimiste de cette étude se tait presque tout le temps : l'ajouter telle quelle sur ce vote
couperait aussi les bons signaux. La variante à tester ensuite : garder le sens du vote 4 h, et
s'abstenir seulement quand le mouvement médian prévu est plus petit que le spread. On filtre un
signal qui a déjà une petite avance, avec le seuil le plus simple (k = 1), hors échantillon,
prix mélangés à côté. Rien n'est branché sur `ia/pistes_direct.py`.


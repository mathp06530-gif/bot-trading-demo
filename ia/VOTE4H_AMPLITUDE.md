# Vote 4 h filtré par l'amplitude

On garde le sens du vote 4 h (14 cerveaux, seulement ses 5 % les plus sûrs).
On retire un trade seulement quand le mouvement médian prévu est plus petit que le spread et les frais de nuit.
**k = 1** est figé. La période jugée commence le 2024-11-27, et n'a servi à choisir aucun seuil.

## Verdict : rejetée

Sur la période jugée, le vote seul fait +0,0076 % par trade (54,0 % de bonnes réponses, sens majoritaire 55,5 %, 6/8 marchés, 7 trades/mois, 971 instants distincts).
Le filtre fait -0,0096 % par trade (53,8 %, 6/8 marchés, 4 trades/mois, 626 instants). Il bat 15 % des filtres au hasard.
Le filtre est rejeté : sur la période jugée il gagne moins que le vote seul, et moins que des retraits au hasard.

Lecture : gain = moyenne des marchés, après spread et frais de nuit, en % du prix. Instants = horaires distincts (la même bougie sur deux marchés compte une fois dans le total, et une fois par marché dans la somme). « Mieux que le hasard » = part de 500 filtres qui retirent le même nombre de trades et font un gain moyen plus bas.

| | Réussite | Gain / trade | Trades (instants) | Trades/mois | Marchés + | Mois + | Sens majoritaire |
|---|---|---|---|---|---|---|---|
| (a) vote seul, choix | 54,8 % | -0,0081 % | 1592 (1273) | 6 | 3/8 | 134/264 | 54,2 % |
| (b) vote + amplitude, choix | 54,2 % | -0,0108 % | 1024 (858) | 4 | 4/8 | 125/246 | 54,4 % |
| (a) vote seul, jugé | 54,0 % | +0,0076 % | 1312 (971) | 7 | 6/8 | 91/185 | 55,5 % |
| (b) vote + amplitude, jugé | 53,8 % | -0,0096 % | 802 (626) | 4 | 6/8 | 82/172 | 55,6 % |

Choix : le filtre bat 86 % des hasards (tous les trades réunis : gain +0,0026 %, médiane du hasard -0,0078 %, 1024 trades gardés sur 1592).
Jugé : le filtre bat 15 % des hasards (tous les trades réunis : gain -0,0035 %, médiane du hasard +0,0113 %, 802 trades gardés sur 1312).

Prix mélangés, période jugée : vote seul 51,4 % (gain -0,0547 %), vote + amplitude 51,5 % (gain -0,0253 %, marchés avec au moins 30 trades mélangés).

Sur un marché isolé, les prix mélangés dépassent 53 % pour : US500 (57,3 %, 82 trades), GBPUSD (61,2 %, 49 trades).
La réussite filtrée de ces marchés-là ne compte pas comme un signal.

k choisi sur le choix seulement : **1** (gain de choix -0,0108 %). Sur la période jugée il fait -0,0096 % (53,8 %, 6/8 marchés). Ce n'est pas le test principal.

## Par marché, période jugée, k = 1

| Marché | (a) réussite | (a) gain | (a) trades | (b) réussite | (b) gain | (b) trades | (b) sens majoritaire | (b) mois + | (b) prix mélangés | Mieux que le hasard |
|---|---|---|---|---|---|---|---|---|---|---|
| GOLD | 58,1 % | +0,0440 % | 229 | 55,1 % | +0,0059 % | 138 | 56,5 % | 11/24 | 46,2 % | 9 % |
| SILVER | 54,4 % | +0,0896 % | 180 | 47,7 % | +0,0310 % | 44 | 54,5 % | 5/14 | — | 32 % |
| OIL_CRUDE | 45,1 % | -0,1265 % | 153 | 45,5 % | -0,2214 % | 77 | 57,1 % | 7/23 | 52,3 % | 8 % |
| US100 | 57,5 % | +0,0490 % | 141 | 58,2 % | +0,0513 % | 122 | 58,2 % | 13/23 | 50,0 % | 55 % |
| US500 | 53,2 % | -0,0443 % | 154 | 52,5 % | -0,0463 % | 118 | 52,5 % | 8/22 | 57,3 % | 45 % |
| DE40 | 57,2 % | +0,0348 % | 173 | 59,9 % | +0,0484 % | 142 | 59,2 % | 12/23 | 49,5 % | 90 % |
| EURUSD | 48,5 % | +0,0034 % | 130 | 46,2 % | +0,0209 % | 78 | 52,6 % | 14/23 | 44,3 % | 88 % |
| GBPUSD | 57,9 % | +0,0111 % | 152 | 65,1 % | +0,0333 % | 83 | 54,2 % | 12/20 | 61,2 % | 92 % |

## D'où viennent les prix

Dukascopy, bougies horaires bid, regroupées en 4 h (au moins 3 heures), de 2016 à novembre 2026.
Le spread collé autour du prix est le spread médian des bougies 4 h Capital.com (`ia/resultats.json`).
GBPUSD 0,010 % et DE40 0,007 % viennent de `ia/FRAIS_COURTIERS.md`. Les frais de nuit sont la moyenne
achat/vente publiée, ajoutée quand la bougie passe 22 h UTC. Ce n'est pas le spread de chaque minute
Capital.com : aux heures où il s'élargit, le coût réel serait un peu plus haut.

Le vote est celui du labo (`ia/multi_labo.py`) : 3 IA réentraînées chaque mois sur le passé et 11 règles,
trou de 10 h, seuil des 5 % le plus sûr calculé sur les bougies précédentes seulement.
Le quantile médian est le même type de modèle que `ia/amplitude.py` (LightGBM, 80 arbres), entraîné
chaque mois avec un trou de 4 h. Il ne choisit pas le sens : le sens reste celui du vote.

## Lecture du verdict

Confirmée : sur la période jugée, (b) gagne de l'argent, bat (a), bat au moins 95 % des filtres au hasard,
a une réussite au-dessus du sens majoritaire, au moins 5 marchés sur 8 sont positifs, les prix mélangés restent
≤ 53 %, et (b) battait déjà (a) sur la période de choix.
Les prix ne sont pas les bougies Capital.com du vote confirmé (55 à 56 %, +0,013 à +0,023 % par trade).
Ici on compare (a) et (b) sur les mêmes bougies Dukascopy. Le vote seul, sur cette série, ne dépasse pas
le sens majoritaire : son petit gain vient surtout de la hausse de fond, pas d'un taux de réussite supérieur.
Prometteuse : (b) est devant (a) et gagne de l'argent, mais un de ces contrôles manque.
Rejetée : (b) perd, ou ne bat pas (a), ou les prix mélangés dépassent 53 %.

## Suite

Le vote 4 h seul reste la piste en test direct (`ia/pistes_direct.py`). Ce filtre n'y est pas ajouté.


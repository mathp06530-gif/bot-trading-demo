# IA unique multi-cerveaux : labo sur l'historique (12 derniers mois jamais vus)

Chaque ligne : moyenne sur les marchés. Gain = gain moyen par prédiction APRÈS le vrai spread (en % du prix).
« Prix mélangés » = la même chaîne complète refaite sur des prix sans aucune structure (doit donner ~50 %).

## MINUTE_15

| Méta-cerveau | Réussite | Gain après spread | Si sûr : réussite / couverture / gain | Marchés gagnants (si sûr) | Mois positifs (si sûr) | Prix mélangés (réussite, si sûr) |
|---|---|---|---|---|---|---|
| Vote simple | 49.91 % | -0.0148 % | 50.11 % / 1 % / -0.0073 % | 0/3 | 2/14 | 49.91 % |
| Champion du mois | 51.13 % | -0.0149 % | 53.66 % / 1 % / +0.0003 % | 2/3 | 4/11 | 50.16 % |
| Fixed Share global | 50.00 % | -0.0161 % | 49.50 % / 0 % / -0.0221 % | 0/2 | 0/4 | 50.06 % |
| Fixed Share par régime | 49.89 % | -0.0154 % | 53.84 % / 0 % / -0.0117 % | 0/2 | 0/3 | 50.51 % |
| Aiguilleur (mixture of experts) | 50.88 % | -0.0152 % | 51.14 % / 1 % / -0.0103 % | 0/3 | 5/21 | 49.64 % |
| CHEF (IA unique) | 50.76 % | -0.0152 % | 54.82 % / 1 % / -0.0119 % | 0/3 | 3/12 | 51.67 % |
| Élève (distillation) | 50.98 % | -0.0150 % | 51.18 % / 1 % / -0.0181 % | 0/4 | 5/17 | 49.81 % |

## MINUTE_5

| Méta-cerveau | Réussite | Gain après spread | Si sûr : réussite / couverture / gain | Marchés gagnants (si sûr) | Mois positifs (si sûr) | Prix mélangés (réussite, si sûr) |
|---|---|---|---|---|---|---|
| Vote simple | 49.71 % | -0.0146 % | 44.79 % / 0 % / -0.0024 % | 0/1 | 0/1 | 51.35 % |
| Champion du mois | 50.80 % | -0.0139 % | ne parie jamais | — | — | 49.77 % |
| Fixed Share global | 50.28 % | -0.0145 % | 48.70 % / 0 % / -0.0068 % | 0/1 | 0/3 | 50.00 % |
| Fixed Share par régime | 50.26 % | -0.0143 % | 52.35 % / 0 % / -0.0017 % | 0/1 | 0/2 | 49.95 % |
| Aiguilleur (mixture of experts) | 50.92 % | -0.0139 % | 48.34 % / 0 % / -0.0059 % | 0/2 | 1/3 | 51.14 % |
| CHEF (IA unique) | 50.67 % | -0.0143 % | 51.67 % / 0 % / -0.0134 % | 0/1 | 0/1 | 49.55 % |
| Élève (distillation) | 50.85 % | -0.0139 % | 53.94 % / 0 % / -0.0134 % | 0/2 | 0/5 | 49.22 % |

Essais comptés (méta-cerveau x marché x version) : 196.

# IA unique « multi-cerveaux » : recherche et construction (27/11/2026)

Demande de Mathis : une seule IA qui contient toutes les IA, sans mélanger leurs avis à l'aveugle ; un méta-cerveau
qui choisit qui écouter selon le régime du marché (tendance ou retournement). Variante « élève » (distillation).
Règles : gratuit, aucun lookahead, jugé après le vrai spread, contrôle sur prix mélangés (jeter au-delà de ~53 %).

## Ce que dit la recherche (sources lues le 27/11)

| Source | Ce qu'on en retient |
|---|---|
| Fixed Share (Herbster & Warmuth ; notes W. Koolen, CWI) | Suivre le meilleur expert quand il CHANGE : à chaque pas on redistribue une petite part des poids (alpha). Le regret ne croît qu'en log(nombre d'experts) : 30-60 cerveaux ne coûtent presque rien. C'est exactement le problème du 27/11 (IA collées à l'ancienne tendance). |
| Shalizi et al., « growing expert ensembles » (arXiv 1103.0949) | On peut ajouter des experts en cours de route ; le poids de départ d'un nouveau venu est un point délicat. |
| Numerai, apprentissage en ligne et changements de régime (arXiv 2301.00790) | Choisir dynamiquement entre variantes sur leurs résultats récents améliore le Sharpe (1,18 -> 1,43) ; la meilleure variante « après coup » n'était pas repérable à l'avance. |
| MoE-F, ICLR 2025 (filtrage en ligne des experts) | Un filtre par expert estime la probabilité qu'il soit le meilleur à partir de ses pertes seulement, sans routeur appris : F1 0,52 contre 0,35 pour le meilleur expert seul (direction SPY, journalier). |
| Mixture of experts « volatilité » (arXiv 2508.02686), RAVEN (arXiv 2606.24062) | Aiguiller selon un régime de volatilité ou d'échelle aide sur du journalier ; résultats non vérifiables indépendamment. |
| FFORMA / FFORMPP (M4, arXiv 1908.11500) | Choisir ou pondérer les modèles à partir de caractéristiques de la série (tendance, entropie, Hurst) : « comparable » aux autres méthodes, gain modeste. |
| Trading via selective classification (arXiv 2110.14914) | Abstention : ne trader que quand la confiance dépasse un seuil choisi avec une garantie de risque, sur des futures métaux en 30 min. |
| Numin (arXiv 2412.03167) | Vote pondéré par l'utilité de trading en intraday 5 min : gain sur 5 jours seulement, sans frais : à ne pas croire tel quel. |
| MNQ intraday (arXiv 2605.04004) | 14 familles de signaux 5 min testées honnêtement : aucune ne passe tous les tests après frais ; un décalage d'une bougie suffit à inverser un résultat. |
| BSIC, régimes ML sur ES (2026) | Aiguillage par régime : surtout moins de volatilité, pas de vrai surplus (Reality Check p = 0,55) ; pièges : fuite d'étiquettes, réglages vus sur le test. |
| TIPS, distillation d'ensemble (arXiv 2603.16985) | Un élève peut garder l'essentiel de l'ensemble (Sharpe 1,45 contre 1,34) pour 7 fois moins de calcul ; gain inégal selon les marchés. |
| G-Research crypto (Kaggle) | Top 3 = LightGBM ; « le travail sur les variables a fait la différence » ; classement très bousculé pendant la phase en direct. |

Conclusion de la recherche : la piste la plus solide pour « qui écouter quand le régime change » est le Fixed Share
(pondération en ligne qui se rattrape vite), par régime, avec des cerveaux miroirs, plus une abstention réglée sur le
passé. Un routeur appris (mixture of experts LightGBM) demande beaucoup de données. La distillation sert surtout à
aller plus vite, pas à mieux prédire. Personne ne montre de gain sûr après frais en intraday : il faut le mesurer.

## Ce qui est construit

1. `ia/multi_cerveaux.py` (direct, toutes les 20 min, branche `ia-multi`) : sur les prédictions réelles des ~26 IA.
   Cerveaux + miroirs + suiveur/contrarien ; 3 méta-cerveaux (par régime, global, sans miroirs) ; CHEF = Fixed Share
   au-dessus d'eux et du vote. Prédictions en cours affichées sur la page IA. Chiffres « en direct » comptés à partir du
   27/11 20 h UTC.
2. `ia/multi_labo.py` (workflow `multi_labo.yml`) : la même architecture sur 1-2 ans de bougies Capital.com (8 marchés,
   5 min / 15 min / 1 h), 14 cerveaux (3 IA apprises + 11 règles) + miroirs, 7 méta-cerveaux dont l'aiguilleur
   (mixture of experts) et l'élève (distillation), chacun en version « toujours » et « seulement si sûr », tout refait
   sur prix mélangés. Bilan : `ia/MULTI_LABO.md`.
3. Réglages (eta 3, alpha 0,01) choisis sur des PRIX INVENTÉS à régimes, jamais sur les vrais prix testés.

Vérification sur prix inventés (tendance puis retournement par blocs de 1 à 3 jours) : chaque cerveau seul fait
50,0-50,7 % (le signal est caché), le Fixed Share global 51,5 %, par régime 51,7 % ; prix mélangés 49-50 %.
Le moteur trouve donc bien un signal qui change de sens, et ne fabrique rien sur du hasard.

# Recherche « gagner beaucoup en peu de temps » (26/11/2026)

Backtest : `backtest/asymetrie.py` (workflow `asymetrie.yml`), bilan dans `resultats_asymetrie.json` / `.txt`.
Réglages choisis sur 2017-2021, jugés sur 01/2022-06/2024 et 07/2024-2026 (jamais vus), frais réels, contrôle sur prix au hasard.

## Ce qui a été testé chez Capital.com
| Piste | Résultat (R : 2017-21 / 2022-mi24 / mi24-2026) | Verdict |
|---|---|---|
| Avant la Fed, US100 (achat veille 14 h NY, sortie avant l'annonce, stop 1 ATR) | +7,5 / +4,4 / +3,2 (80 trades) | **Ajoutée en démo à 1 %** (bot/fed.py). Preuve faible à moyenne, 8 trades/an |
| Avant la Fed, US500 / US30 / DE40 | positif aux 3 périodes, plus petit | même effet (pas ajoutés : même pari, risque doublé) |
| Avant la Fed, or / EUR/USD | négatif à l'entraînement | rejeté |
| Achat de nuit (indices, clôture -> ouverture) | 2017-21 positif, 2022-mi24 négatif partout | rejeté (frais de nuit) |
| Cassure de volatilité Larry Williams (14 marchés, jour) | aucun marché gagnant en 2017-21 | rejeté |
| Prix au hasard (contrôle) | Fed : +0,9 à +7,5 R ; nuit : toujours négatif ; Williams : 0 | le hasard explique une partie de la Fed |

## Taille des positions (Kelly, ruine) : vrais trades Cassure or+argent, tirés au hasard sur 1 an
Sur les trades 2022-2026 (période favorable, hausse de l'or) :
| Risque/trade | Capital médian après 1 an | Chance x2 | Chance x10 | Chance de passer par -50 % |
|---|---|---|---|---|
| 1 % | x1,12 | 0,4 % | 0 % | 0 % |
| 3 % (actuel) | x1,35 | 21 % | 0,1 % | 0,5 % |
| 5 % | x1,54 | 35 % | 1 % | 12 % |
| 8 % | x1,69 | 43 % | 5,5 % | 49 % |
| 12 % | x1,65 | 45 % | 11,5 % | 86 % |
| 20 % | x0,99 | 38 % | 15 % | 99,7 % (23 % perdent 90 %) |
Sur les trades 2017-2021 (période plate), même 3 % ne gagne rien en médiane et 8 % fait perdre (x0,79).
Kelly (taille qui fait grossir le plus vite) : 1,8 % sur 2017-21, 9,5 % sur 2022-26 → instable ; la moitié de Kelly
du pire cas ≈ 1-3 %. Conclusion : augmenter le risque augmente surtout la chance de tout perdre.

## Challenge prop firm (+10 % avant -10 %, sans intérêts composés), Cassure or+argent, trades 2022-2026
1 % : 85 % de réussite (~26 trades, ~6 mois) ; 2 % : 68 % ; 3 % : 61 %. ATTENTION : basé sur la meilleure période de
l'or ; les chiffres publics des prop firms sont ~14 % de réussite et ~7 % de paiements. 18 ans minimum, payant.

## Hors Capital.com (recherche)
- Options très hors de la monnaie, Polymarket : pas accessibles (âge, interdit/limité en France, pas chez Capital.com).
- Concours démo gratuits avec prix (Deriv, LiteFinance, TradingView « The Leap ») : gratuits, mais en général 18 ans
  et pièce d'identité pour toucher le prix ; gagnés par les plus gros paris (loterie).
- Études sur les particuliers : Brésil, 97 % des day traders qui persistent perdent (Chague et al. 2019) ;
  Taïwan, moins de 1 % gagnent de façon régulière (Barber et al.). Championnats (Larry Williams +11 376 % en 1987)
  = survivants d'un grand nombre de joueurs.

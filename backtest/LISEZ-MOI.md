# Le labo de backtest

Ce dossier ne passe aucun ordre. Il sert à tester une idée sur l'historique Capital.com avant de la mettre en démo.

| Fichier | Rôle |
|---|---|
| `moteur.py` | simule les trades (spread, frais de nuit, stop garanti, stop suiveur) ; utilisé aussi par l'auto-amélioration |
| `telecharger.py` | télécharge l'historique des prix Capital.com |
| `serrage.py`, `sortie_rapide.py` | outils communs (frais de nuit, sorties de la Rapide) |
| `strategies.py`, `lancer.py` | premières stratégies de référence (la cassure du bot est vérifiée contre elles par un test) |
| `usine.py`, `usine_regles.py` | l'usine à stratégies (millions de combinaisons, contrôle sur des années jamais vues) |

## Ce qui a déjà été testé et rejeté (avant le 26/11/2026)

Pour ne pas refaire les mêmes essais. Les scripts et résultats détaillés sont dans la branche `sauvegarde-26-11`.

- TP serrés, stops serrés dès l'entrée, entrée sur mouvement brutal, indice peur/avidité, cassure ouverture New York, RSI.
- Cassure sur tous les marchés (seuls l'or et l'argent tiennent), cassure sur dollar, devises et indices.
- Filtres « gros acteurs » (volume, VWAP, COT CFTC), filtre ADX plus fort, confirmation avant entrée, prise de gain partielle.
- Filtres de régime, taille selon la volatilité, corrélation, chandeliers : 0 sur 16 idées solides.
- FVG + Fibonacci (or 15 min) : 0 solide sur 10 ans.
- Fouille « tout le web » (2 181 couples idée × marché) : 0 solide.
- Usine : 3,66 millions de stratégies sur 41 marchés : 0 solide.
- Élan des gros acteurs, Supertrend Ethereum, MACD gaz naturel et Tesla, Avant la Fed : mis en démo à 1 % en
  expérience, retirés au nettoyage du 26/11/2026 (preuves trop faibles).

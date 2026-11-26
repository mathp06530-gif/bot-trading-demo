# Grande fouille du web (26/11/2026, « retourne tout le web »)

Bancs : `backtest/web_large.py` (workflow `web_large.yml`) et `backtest/diversifier.py` (workflow `diversifier.yml`).
Bilans bruts : `resultats_web_large.json/.txt`, `resultats_diversifier.json/.txt`. Dates d'annonces : `dates_annonces.json`.

## Sources
5 recherches en parallèle, **100 pages lues** (≈130 recherches web) : catalogues académiques 16 (Quantpedia, NBER,
AQR, Alpha Architect, CXO…), carry et spreads 25, GitHub/Kaggle/QuantConnect 21, calendrier et banques centrales 18,
forums en plusieurs langues 20 (Reddit, MQL5, smart-lab, J-STAGE/Kobe pour la gotōbi, ProRealCode…).

## Méthode
Réglage choisi sur 2017-2021, jugé sur 01/2022-06/2024 et 07/2024-2026 (jamais vus) ; spread bid/ask réel, frais de
nuit, prime du stop garanti ; frais x 1,5 ; voisins ; prix mélangés (contrôle) ; Bonferroni sur tous les couples.

**23356 réglages, 2181 couples idée × marché** (94 marchés en jour, 41 en 1 h). Seuil Bonferroni : t ≥ 4.08.

Verdicts : ne tient pas avec frais x 1,5 3, passe, mais pourrait être le hasard 46, perd à l'entraînement 786, prometteur 3, réglage isolé (voisins perdants) 66, trop peu de trades 354, échoue sur les années jamais vues 1156

Contrôle prix mélangés (aucun effet possible) : 173 et 147 couples « passent » par hasard, dont 4 et 7 au-dessus de Bonferroni (dérive des cryptos conservée par le mélange). Les vrais prix font MOINS bien que le hasard : **rien ne tient**.

## Tableau idée × meilleur marché (choisi sur 2017-2021) × années jamais vues
| Idée | Meilleur marché 2017-21 | R 2017-21 | R 2022-mi24 | R mi24-26 | t | Marchés testés | Verdict |
|---|---|---|---|---|---|---|---|
| Après la Fed (FOMC) | J225 | 10.0 | 2.1 | 1.2 | 1.37 | 41 | réglage isolé (voisins perdants) |
| Retournement hebdo des indices | ETHUSD | 138.7 | 10.7 | 15.8 | 1.11 | 94 | réglage isolé (voisins perdants) |
| Momentum hebdo crypto | ETHUSD | 264.3 | 6.0 | 7.1 | 0.96 | 94 | passe, mais pourrait être le hasard |
| Rééquilibrage fin de mois | MARA | 50.2 | 3.1 | 0.5 | 0.93 | 94 | réglage isolé (voisins perdants) |
| Avant/après la Banque d'Angleterre | BTCUSD | 11.3 | 0.7 | 3.0 | 0.79 | 41 | réglage isolé (voisins perdants) |
| Momentum intraday US | US30 | 144.7 | 8.7 | -0.7 | 0.66 | 41 | échoue sur les années jamais vues |
| Avant/après la banque d'Australie | OIL_BRENT | 13.2 | 1.2 | -0.6 | 0.12 | 41 | échoue sur les années jamais vues |
| Paires (retour à la moyenne de l'écart) | US100/NVDA | 10.7 | -0.7 | 1.2 | 0.11 | 14 | échoue sur les années jamais vues |
| Veille BoE (indice anglais) | ETHUSD | 43.0 | 0.4 | -0.1 | 0.08 | 94 | échoue sur les années jamais vues |
| Expiration des options | ETHUSD | 79.5 | -16.3 | 16.4 | 0.01 | 94 | échoue sur les années jamais vues |
| Sell in May (Halloween) | ETHUSD | 288.2 | 15.5 | -15.2 | 0.01 | 94 | échoue sur les années jamais vues |
| Avant/après l'inflation US (CPI) | BTCUSD | 15.0 | -0.7 | 0.1 | -0.1 | 41 | échoue sur les années jamais vues |
| Avant/après la Banque du Japon | USDCHF | 9.4 | -3.4 | 2.9 | -0.1 | 41 | échoue sur les années jamais vues |
| Fixing de fin de mois (dollar) | J225 | 10.7 | 0.4 | -0.6 | -0.13 | 41 | échoue sur les années jamais vues |
| Veille de jour férié | ETHUSD | 58.2 | 2.2 | -4.4 | -0.47 | 94 | échoue sur les années jamais vues |
| Automne de l'or | RIOT | 43.6 | -4.8 | 1.1 | -0.55 | 94 | trop peu de trades |
| Momentum entre marchés (portefeuille 41 marchés) | portefeuille | 315.8 | 4.8 | -21.7 | -0.63 | 1 | échoue sur les années jamais vues |
| Veille RBA (indice australien) | ETHUSD | 98.3 | -1.0 | -2.0 | -0.67 | 94 | échoue sur les années jamais vues |
| Séances de l'or | US30 | 126.1 | -0.9 | -8.1 | -0.67 | 41 | échoue sur les années jamais vues |
| V du dollar autour des fixings | US30 | 111.4 | 2.6 | -11.4 | -0.89 | 41 | échoue sur les années jamais vues |
| Calendrier composite (Quantpedia) | ETHUSD | 96.3 | -8.7 | -2.7 | -1.13 | 94 | échoue sur les années jamais vues |
| Avant/après la BCE | USDCHF | 8.9 | 1.1 | -7.3 | -1.18 | 41 | échoue sur les années jamais vues |
| Avant/après l'emploi US (NFP) | J225 | 17.1 | -3.1 | -2.4 | -1.26 | 41 | échoue sur les années jamais vues |
| Saisonnalité même mois | TSLA | 37.9 | -13.2 | -6.0 | -1.45 | 94 | échoue sur les années jamais vues |
| Veille BCE (indices zone euro) | MARA | 45.6 | -0.6 | -3.0 | -1.54 | 94 | échoue sur les années jamais vues |
| Crypto du 25 au 3 | ETHUSD | 83.7 | 5.9 | -18.2 | -1.58 | 94 | échoue sur les années jamais vues |
| Début/fin de mois | XRPUSD | 72.4 | -11.5 | -3.6 | -1.65 | 94 | échoue sur les années jamais vues |
| Veille BoJ (Nikkei) | MARA | 41.9 | -1.0 | -2.6 | -1.69 | 94 | échoue sur les années jamais vues |
| BTC meneur de l'ETH | US30 | 1306.2 | -19.4 | -33.3 | -1.91 | 40 | échoue sur les années jamais vues |
| IBS (clôture près du bas) | ETHUSD | 244.2 | -15.3 | -4.9 | -2.02 | 94 | échoue sur les années jamais vues |
| Baisses d'affilée | MARA | 176.1 | -7.3 | -8.2 | -2.2 | 94 | échoue sur les années jamais vues |
| Fin de séance US -> ouverture Asie | HK50 | 27.8 | -10.8 | -22.3 | -2.89 | 40 | échoue sur les années jamais vues |
| Inversion de fin de mois | XRPUSD | 58.3 | -12.1 | -21.3 | -3.01 | 94 | échoue sur les années jamais vues |
| Jour de la semaine | MARA | 240.1 | -9.1 | -13.0 | -3.08 | 94 | échoue sur les années jamais vues |
| Gotobi (USD/JPY) | BTCUSD | 74.6 | -28.9 | -9.5 | -5.12 | 41 | échoue sur les années jamais vues |
| Heures du Bitcoin | BTCUSD | 148.7 | -58.5 | -21.9 | -9.83 | 41 | échoue sur les années jamais vues |

ATTENTION : les très gros R 2017-21 (crypto, US30 en 1 h) viennent surtout de vieilles données (spread manquant complété, volatilité 2017-18) ; ils s'effondrent tous ensuite.

Les 3 « prometteurs » (t 1,6 à 2,6, sous le seuil 4,1) : veille BCE sur l'or, veille RBA sur USD/JPY, momentum hebdo sur l'or — sans logique économique (idées faites pour d'autres marchés) et le hasard en produit 65-72 de ce niveau. Non ajoutés.

## Petits marchés
| Catégorie | Marchés trouvés | Spread médian | Verdicts |
|---|---|---|---|
| matières premières secondaires | 14 | USCOCOA 0.17 %, COFFEEARABICA 0.228 %, UKSUGAR 0.158 %, USCOTTON 0.246 %, OATS 0 %, WHEAT 0 %, CORN 0 %, SOYBEAN 0 %, LUMBER 0.682 %, LIVECATTLE 0 %, LEANHOGS 0 %, RR 0.204 %, HEATINGOIL 0 %, GASOLINE 0 % | ne tient pas avec frais x 1,5 1, passe, mais pourrait être le hasard 6, échoue sur les années jamais vues 130, perd à l'entraînement 49, réglage isolé (voisins perdants) 6, trop peu de trades 74 |
| devises exotiques | 10 | USDTRY 0.521 %, USDZAR 0.108 %, USDMXN 0.029 %, USDPLN 0.126 %, USDHUF 0.284 %, USDSEK 0.225 %, USDNOK 0.067 %, USDSGD 0.031 %, EURTRY 0.511 %, USDCZK 0.178 % | échoue sur les années jamais vues 71, réglage isolé (voisins perdants) 3, trop peu de trades 13, perd à l'entraînement 103 |
| petites cryptos | 11 | ADAUSD 0.673 %, DOTUSD 1.123 %, LINKUSD 1.392 %, AVAXUSD 1.88 %, ATOMUSD 1.009 %, BCHUSD 0.705 %, XLMUSD 1.001 %, UNIUSD 1.125 %, TRXUSD 2.012 %, ALGOUSD 2.402 %, ETCUSD 2.362 % | échoue sur les années jamais vues 84, réglage isolé (voisins perdants) 1, trop peu de trades 75, perd à l'entraînement 49 |
| petits indices | 7 | NL25 0.037 %, SP35 0.07 %, IT40 0.053 %, SW20 0.026 %, CN50 0.07 %, SG25 0.081 %, GOLD 0.016 % | ne tient pas avec frais x 1,5 1, trop peu de trades 10, passe, mais pourrait être le hasard 7, échoue sur les années jamais vues 98, perd à l'entraînement 24, réglage isolé (voisins perdants) 6, prometteur 2 |
| petites actions | 12 | PLUG 0 %, RIOT 0 %, MARA 0.432 %, SOFI 0.519 %, GME 0.816 %, AMC 1.163 %, LCID 0.608 %, RIVN 0.491 %, NIO 0 %, SNAP 0.647 %, PLTR 0.321 %, COIN 0.312 % | passe, mais pourrait être le hasard 1, échoue sur les années jamais vues 88, perd à l'entraînement 37, réglage isolé (voisins perdants) 5, trop peu de trades 97 |

Spread 0 % = Capital.com n'a donné que le prix vendeur : frais sous-estimés (test optimiste), rien ne tient quand même. La recherche « Singapore » a renvoyé l'or (ligne GOLD dans petits indices, à ignorer).

Cassure / Supertrend 4 h (réglages actuels) sur les petits marchés : devises exotiques : aucun sur 20; matières premières secondaires : aucun sur 20; petites actions : ['Cassure 4 h COIN'] sur 22; petites cryptos : aucun sur 22; petits indices : ['Supertrend 4 h GOLD'] sur 14. COIN (Coinbase) : +2,5 R / +2,5 R, cotée depuis 2021, trop peu pour conclure ; l'ajouter baisse le total du portefeuille à risque égal (43,3 -> 30,7 R).

## Diversifier (dollar, devises, indices)
Cassure et Supertrend 4 h sur 28 grands marchés hors or/argent : aucun ne gagne sur les 3 périodes (indice dollar : -94 R et -75 R). Supertrend or/argent tient mais suit les mêmes mois que la Cassure (corrélation 0,53) : même pari, non ajouté.

## Verdict
Aucune stratégie ajoutée. Rien ne change dans le bot.

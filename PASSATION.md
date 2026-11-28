# Dossier de passation : projet « bot de trading de A à Z »

> Rédigé le 28/11/2026 pour qu'une autre IA (Grok ou autre) reprenne le projet. Version publique : technique seulement (le profil personnel est donné à part).
> Aucun secret ici : les clés Capital.com et GitHub restent dans les « secrets » du dépôt GitHub.
> Dépôt public : https://github.com/mathp06530-gif/bot-trading-demo (branche `main`).

---

## 1. À lire en premier : règles à respecter avec Mathis

1. **Compte démo uniquement.** Argent fictif, chez Capital.com. Pas de trading en argent réel, ni sur un compte au nom de quelqu'un d'autre (interdit par les courtiers).
2. **100 % gratuit et H24.** Tout tourne sur GitHub Actions (gratuit car le dépôt est public).
3. **Ne jamais lui dire « c'est impossible ».** Quand les chiffres ne vont pas dans le bon sens, ne pas se braquer : chercher une autre piste, la tester, l'améliorer.
4. **Mais rester honnête sur les chiffres mesurés.** Pas de promesse de rendement. Toujours dire ce qui a vraiment été mesuré.
5. **Séparer gain réalisé et gain latent.** Il s'inquiète vite quand le compte baisse. Dans `docs/data.json`, `compte.solde` INCLUT déjà le latent : argent encaissé = `solde - resultat_latent`. Ne jamais additionner solde + latent.
6. **Ton : direct ET encourageant**, en français simple, réponses courtes. Lui rappeler son objectif. Étapes courtes, résultats visibles vite, dates précises. L'attente le démotive.
7. **Tout automatique.** Il veut que les modifications soient faites et mises en ligne sans qu'il ait à coder.
8. **Anti-triche stricte dans les tests** (sa demande) : voir section 4.
9. Jamais de clé ou de mot de passe dans le chat.

## 2. Architecture technique

| Pièce | Rôle |
|---|---|
| **Capital.com démo** (API REST) | Le courtier. Ordres réels sur compte démo. Le compte EXIGE un **stop garanti** sur chaque ordre (géré dans `bot/capital.py`). |
| **GitHub Actions** | Le « moteur ». `moteur.yml` boucle ~5 h 45 et fait un tour **toutes les minutes** (`scripts/tour.sh` : fetch, reset, tour, push, 3 essais), puis se relance seul. Le cron GitHub seul ne se déclenchait jamais, d'où cette boucle. |
| **Appli PWA** (`docs/`) | https://mathp06530-gif.github.io/bot-trading-demo/docs/ (attention : les liens contiennent `docs/`). Pages : `index.html` (Centre de contrôle), `ia.html` (IA), `elan.html` (Élan crypto), `mur.html` (mur des IA, un graphique par IA). Style v3 noir/vert terminal, `theme.css` + `nav.js` communs, service worker `sw.js` (monter sa version à chaque changement). |
| **docs/data.json** | État du compte, positions (avec stop/objectif), ordres, journal, courbe. Écrit par le bot à chaque tour. |
| **reglages.env** (racine) | Tous les réglages, relus à chaque tour. Jamais de clé dedans. |
| **Commandes de l'appli** | `bot.yml` (workflow_dispatch, input `action` = analyser / pause / reprendre / fermer). L'appli utilise une clé GitHub fine-grained stockée dans le navigateur de chaque appareil. |
| **Secrets GitHub** | `CAPITAL_API_KEY`, `CAPITAL_IDENTIFIER`, `CAPITAL_PASSWORD` (noms seulement, jamais les valeurs). |

Dossiers du dépôt : `bot/` (bot principal), `elan_crypto/` (bot à part), `ia/` (système IA à part, n'envoie aucun ordre), `backtest/` (labo manuel, `backtest/LISEZ-MOI.md` résume les rejets), `tests/`, `.github/workflows/` (22 workflows).

Branches importantes : `sauvegarde-26-11` (sauvegarde complète avant nettoyage, **ne jamais supprimer**), `ia-archives`, `ia-multi`, `ia-pistes`, `ia-boost`, `ia-sentiment` (données des IA).

Pour ajouter une stratégie : créer `bot/<nom>.py`, ajouter une ligne dans `STRATEGIES` (`bot/main.py`), ses réglages dans `reglages.env`, et un test dans `tests/`.

## 3. Ce qui tourne aujourd'hui (bot principal, après le nettoyage du 26/11)

| Stratégie | Marché | Unité | Risque/trade | Règles clés |
|---|---|---|---|---|
| **Cassure 4 h** | Or, argent | bougies 4 h | 3 % | Entrée quand la clôture sort du canal des 20 dernières bougies, sortie sur l'autre bord du canal 20. Dès +1,5 R, le stop garde 50 % du meilleur gain. Pas de ré-entrée en cours de tendance. Jusqu'à 3 positions empilées (une de plus seulement après +1 R). |
| **Rapide 5 min** | Or | bougies 5 min | 1 % | ADX > 20, bandes de Bollinger qui s'élargissent, stop suiveur 1 %, sortie au prix d'entrée si un gain de +0,5 R disparaît, sortie sur croisement inverse confirmé 3 bougies, garde 60 % du gain dès +1,5 R. 2 positions max. |

**Garde-fous** : coupe-tout à -50 % depuis le plus haut ; plus de nouvel ordre à -15 % dans la journée ; 14 positions max ; risque total 35 % max ; pause 30 min avant / 60 min après les grandes annonces US ; pause 24 h sur un marché après 3 stops perdants d'affilée.

**Auto-amélioration** (`bot/amelioration.py`, dimanche 19 h Paris, appliquée dès le 29/11) : teste un cran sur un seul réglage par stratégie, l'adopte seulement s'il gagne sur les deux moitiés de l'historique, l'annule s'il fait moins bien la semaine suivante. Ne touche jamais au risque ni aux garde-fous.

**Bot à part « Élan crypto »** (`elan_crypto/`, toutes les 30 min) : ETH/LTC/SOL (Élan 50) et XRP (Élan 200), bougies 4 h, sens donné par la moyenne 200, stop 1,5 ATR, 1 % de risque. Coupe-circuit à part : -3 %/jour, -10 % au total. Se couper avec `ELAN_CRYPTO="non"`. À juger fin janvier 2027.

**Chiffres réels** : départ officiel le 20/11/2026 à 98,21 €. Pic ≈ 106,5 € le 25/11. Chute à ~93 € les 25-26/11 = 2 stops Cassure or + argent (-5,32 €), pas un bug ; backtest 10 ans relancé, réglages gardés. **Au 28/11 midi : 92,79 €, aucune position ouverte.** Le test démarre à peine : ne pas juger avant ~3 mois ou ~100 trades.

## 4. Le système IA (dossier `ia/`, aucun ordre réel)

But de Mathis : prédire la direction du marché en temps réel avec « toutes les IA gratuites du monde », puis les « booster ».

- **IA en direct** : LightGBM, forêt, logistique, réseaux, LSTM, CatBoost, transformers, TimesFM, Sundial, FlowState, BiTCN, DLinear, NLinear, GRU, KAN, etc. Retirées le 27/11 (mauvaises) : Chronos-T5, TTM, Time-MoE, Lag-Llama.
- **8 marchés à petits frais** : GOLD, SILVER, OIL_CRUDE, US100, US500, DE40, EURUSD, GBPUSD. **Horizons 5 / 15 / 30 / 60 min** (Mathis juge le 15 min le meilleur ; 1, 2, 3 min et 40 s abandonnés).
- **Super IA** (`ia/super_ia.py`) puis **IA unique multi-cerveaux** (`ia/multi_cerveaux.py`, depuis le 27/11 soir) : chaque IA + son miroir → méta-cerveaux « Fixed Share » par régime → un CHEF + un vote, avec abstention quand ce n'est pas sûr.
- **Boosts en test** (`ia/boost/`, toutes les heures) : correcteur LightGBM par-dessus les IA figées, filtre, champion. N'influencent pas le direct.

**Règles anti-triche (validées par Mathis, à garder absolument)** :
entraîner sur le passé seulement ; tester sur des périodes jamais vues ; purge/embargo ≥ horizon ; **contrôle sur prix mélangés** (doit donner ~50 % : rejeter toute IA ou boost nettement au-dessus de ~53 %) ; comparer au « sens majoritaire » et compter les instants distincts (à 60 min, peu d'instants = chiffres trompeurs) ; toujours compter le **vrai spread** et les frais de nuit ; afficher ces contrôles à côté de chaque chiffre.

**Ce qu'on a mesuré (honnêtement)** :
- À 15 min : ~51 % de bonnes réponses, environ -0,02 % par trade après spread, même sur les 5 % de moments les plus sûrs. Le spread mange l'avance.
- **Première piste confirmée : vote simple à 4 h, 5 % des moments les plus sûrs.** 2024-26 : 56,2 %, +0,013 %/trade ; 2021-24 jamais vu, réglages fixés avant : 54,9 %, +0,023 %/trade, 6/8 marchés, 59 % de mois positifs ; prix mélangés 50,8 %. Avance réelle mais petite (~50 trades/mois, ~1 €/mois sur 100 €). Elle ne marche que sur les 8 marchés à petits frais (20 autres marchés : perdants).
- **Retournement en fin de séance US100/US500** (30 dernières minutes) : 54-56 % confirmé sur période jamais vue, mais ~0 après spread.
- Ces deux pistes tournent **en test direct sans ordres** (`ia/pistes_direct.py`, carte sur la page IA, branche `ia-pistes`).
- **Filtre « vote 4 h » sur la Cassure** : +62,8 → +69,5 R sur 10 ans et baisse un peu moins forte, mais mieux que seulement 67 % des filtres au hasard : **non significatif**, pas branché.
- Stratégie « journée » intraday maison (28/11) : échec après frais (-0,023 %/trade jugé).
- Rapports détaillés dans `ia/*.md` : `MULTI_LABO.md`, `CONFIRMATION_4H.md`, `FIN_SEANCE.md`, `LABO_GAINS.md`, `JOURNEE.md`, `FILTRE_CASSURE.md`, `PISTES_BOOST.md`, `FRAIS_COURTIERS.md`.

**Prochaines pistes prévues** : prédire l'amplitude du mouvement (pas seulement le sens) ; correcteur + calibrage par IA sur les archives ; cibles « au-delà du spread » + abstention ; sentiment Capital.com (enregistré depuis le 27/11) ; apprentissage en ligne. Toujours hors échantillon.

## 5. Déjà testé et rejeté (ne pas refaire)

Sur le bot classique : EMA 9/21 en 15 min (-36 %), tout en 1 minute (le spread dépasse le mouvement), day trading 5 min sur 11 marchés, TP serrés et stops serrés dès l'entrée, entrée après un mouvement brutal, décider chaque minute, indice peur/avidité, RSI et RSI(2), filtres RSI/ATR, filtre ADX plus fort, confirmation avant entrée, cassure de l'ouverture de New York, cassure sur tous les marchés, tendance 1 mois sur 35 marchés, pari « x5 » sur l'or, prise de gain partielle, Rapide sur l'argent, Rapide sans empilement, filtres « gros acteurs » (volume, VWAP, COT CFTC), FVG + Fibonacci sur l'or 15 min, filtres de régime, taille selon la volatilité, corrélation, chandeliers, « Avant la Fed ».

Recherches massives : usine à stratégies (3,66 M essais sur 41 marchés), recherche « 2 mois » (8,6 M essais), fouille de 2 181 idées x marchés trouvées sur le web : **0 stratégie solide** de plus. Les gagnantes récentes ne tiennent pas sur d'autres périodes.

Retirées au nettoyage du 26/11 (récupérables dans `sauvegarde-26-11`) : Tendance 4 h Bitcoin, « deux cerveaux », Élan (version bot principal), Supertrend ETH, MACD gaz/Tesla, Avant la Fed, veille d'actus, simulateur, actions/ETF.

Outils et courtiers écartés : TradingView (pas d'ordres par API, sert à regarder), Alpaca (refusé par Mathis), MoonX (pas de démo ni d'API), Cubrik.ai (crédits gratuits épuisés, payant 19-399 €/mois). Courtiers moins chers : IC Markets EU Raw seulement ~0-30 % de frais en moins, et le 15 min reste perdant même à zéro frais → rester chez Capital.com, viser le 4 h.

Leçons : plus de risque = surtout plus de risque de ruine (Kelly, Monte Carlo) ; l'empilement donne plus de gain mais des baisses énormes ; Capital.com n'a les bougies 15 min que depuis 01/2024 ; prop firms : ~7 % touchent un jour de l'argent, 18 ans minimum.

## 6. Calendrier

| Date | Étape |
|---|---|
| 29/11/2026 | Premier dimanche d'auto-amélioration appliquée automatiquement |
| 30/11/2026 | Premiers chiffres IA fiables + début des boosts (priorité 15 min) |
| 4/12/2026 18 h | Point d'étape du bot (pas un verdict) |
| ~11/12/2026 | Bilan IA sur 2 semaines |
| Fin janvier 2027 | Verdict IA et Élan crypto |
| ~Fin février 2027 | Vrai verdict du bot (~3 mois ou ~100 trades) |

## 7. Ce que la nouvelle IA doit savoir faire pour reprendre

- Lire le dépôt public (tout le code et les rapports `ia/*.md` y sont).
- Le bot tourne seul sur GitHub : **il ne s'arrête pas** si on change d'IA. Rien n'est lié à Claude.
- Pour modifier le code, il faut soit une IA qui peut pousser sur GitHub, soit que Mathis copie-colle les fichiers. Toujours `git pull --rebase` avant de pousser (le bot pousse `docs/data.json` chaque minute).
- Chaque modification : test dans `tests/`, backtest hors échantillon avec les règles anti-triche, puis bilan clair à Mathis (réalisé / latent, chiffres mesurés).
- Le profil complet de Mathis et l'historique privé ne sont PAS dans ce dépôt public : il les donne à part (fichier passation privé).

### Message à coller pour démarrer

> Tu reprends mon projet de bot de trading en démo. Lis d'abord le fichier PASSATION.md de mon dépôt public github.com/mathp06530-gif/bot-trading-demo et respecte ses règles (démo uniquement, honnêteté sur les chiffres, anti-triche, ne jamais me dire que c'est impossible, ton direct et encourageant). Résume-moi en 5 lignes où en est le projet, puis propose la prochaine étape.

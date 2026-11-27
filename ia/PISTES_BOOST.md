# Nouvelles pistes pour booster les IA (recherche du 27/11/2026)

Objectif : faire monter la réussite **réelle, après spread**, des prédictions de direction à 5 / 15 / 30 / 60 min
sur nos 8 marchés à petits frais (GOLD, SILVER, OIL_CRUDE, US100, US500, DE40, EURUSD, GBPUSD).

Ce rapport s'ajoute aux pistes déjà en cours dans « IA unique multi-cerveaux » (Fixed Share par régime, IA élève,
abstention, marchés croisés, amplitude, heures à faible spread). Il ne les répète pas : il en apporte de **nouvelles**.

Règle de lecture : chaque piste a une **preuve réelle** (papier, compétition), un **gain réaliste** (pas le chiffre du
papier), sa **faisabilité gratuite avec nos données**, et une **priorité**. Toute piste passe la règle anti-triche :
entraînement sur le passé, test hors échantillon, prix mélangés ≤ ~53 %, gain compté après le vrai spread,
comparé au « sens majoritaire » et compté en instants distincts.

---

## Le constat qui guide tout

Les gains les plus solides de la littérature à l'échelle de 5-60 min ne viennent **pas** d'une IA plus grosse.
Ils viennent de **flux structurels** : l'horloge (ouvertures, fixings, fins de séance), les annonces économiques,
le positionnement des clients, les ordres posés sur les chiffres ronds. Ce sont des effets qui ont une **cause**
(des gens obligés d'acheter ou de vendre à une heure précise), donc ils ont plus de chances de durer qu'un motif
trouvé par hasard. Nos IA ont déjà l'heure en sin/cos et le jour, mais **pas** la minute dans l'heure, pas la distance
aux fixings, pas le calendrier, pas le sentiment. C'est là que se trouve la marge la moins exploitée.

---

## Priorité 1 : à tester dès ce week-end (données déjà dans le cache, gratuit)

### 1. Horloge fine : minute dans l'heure, fixings, ouvertures, « même minute hier »

**Idée.** Ajouter aux IA :
- la minute dans l'heure et la position dans le quart d'heure (0-14) ;
- les minutes avant/après : ouverture Londres (8 h), fixing BCE (14 h 15 Paris), ouverture actions US
  (15 h 30 Paris), fixing WM/Reuters (17 h Paris = 16 h Londres), fixings or LBMA (10 h 30 et 15 h Londres),
  fixing Tokyo (9 h 55 heure de Tokyo), clôture US (22 h Paris), clôture Xetra (17 h 30 Paris) ;
- la **périodicité** : rendement moyen du même créneau de 15 min sur les 5, 10, 20 derniers jours (passé seulement).

**Preuves.**
- Heston, Korajczyk & Sadka (2010) puis Haendler, Heston, Korajczyk & Sadka (SSRN 5749704, nov. 2025) : le rendement
  d'un créneau horaire se répète les jours suivants à la même heure, et l'effet **persiste hors échantillon** 15 ans après
  la publication (rare). Il s'explique par des traders qui exécutent toujours à la même heure (VWAP, fonds indiciels).
- Krohn, Mueller & Whelan (WU Vienne, 1999-2019, devises G9) : le dollar monte avant les fixings Tokyo, BCE et Londres puis
  se retourne après. Retournement Tokyo : +4,1 points de base/jour, t = 14,5, positif 59 % des jours. **Mais** :
  avant frais, et la version « on prend la liquidité » devient négative après frais. Effet plus petit depuis 2014.
- Kim & Hansen (arXiv 2607.09426, 2026) : en crypto, bursts d'activité aux quarts d'heure pile (+26 % de trades,
  +26 % d'amplitude), retours d'ouverture prévisibles hors échantillon. Montre que les algos ont une horloge.

**Gain réaliste.** Faible en moyenne (0 à +1 point), mais il peut être **fort sur quelques créneaux précis**
(autour des fixings sur EURUSD/GBPUSD, autour de l'ouverture US sur US100/US500). Utilisé surtout pour savoir
**quand jouer** et **quand s'abstenir**.

**Faisable gratuit.** Oui, 100 % calculable depuis la date des bougies déjà en cache (ia-donnees-v1).

**Test proposé.** LightGBM « avec » contre « sans » ces colonnes, mêmes jours de test ; plus une règle seule
« sens moyen du même créneau sur 10 jours » comme cerveau à part. Attention : comparer au sens majoritaire du créneau.

### 2. Momentum de fin de séance sur les indices (horizon 30 min)

**Idée.** Sur US100 / US500 (et DE40 avec la clôture Xetra) : le rendement de l'ouverture jusqu'à 30 min avant la
clôture prédit le sens des 30 dernières minutes. Une prédiction par jour et par indice, à 21 h 30 Paris pour les US.

**Preuves.**
- Gao, Han, Li & Zhou (JFE 2018) : la première demi-heure prédit la dernière demi-heure (SPY).
- Baltussen, Da, Lammers & Martens (JFE 2021) : **60 contrats à terme, 1974-2020**, actions, obligations, matières
  premières, devises. R² hors échantillon 2,88 % sur les indices actions, t = 7,3, Sharpe annuel ~1,7 sur actions
  (avant frais ; les auteurs vérifient que ça tient à 1 tick de coût sur le S&P). Cause identifiée : la couverture
  gamma des vendeurs d'options, qui doivent acheter quand ça monte et vendre quand ça baisse en fin de journée.
  Plus faible sur les devises (Sharpe 0,87).

**Gain réaliste.** C'est la piste la mieux prouvée de ce rapport, mais elle ne donne **qu'un trade par jour par indice**.
Sur nos indices à petit spread, l'effet moyen (quelques points de base) peut passer le spread les jours agités.
Il faut ~60 jours de test pour juger. Les 10 ans d'historique 1 h / 15 min de Capital.com permettent un vrai test.

**Faisable gratuit.** Oui (bougies US100/US500/DE40 déjà en cache ; 15 min depuis 01/2024, 1 h sur plus long).

**Test proposé.** Règle seule (signe du rendement ouverture → 21 h 30) puis comme colonne pour les IA 30 min.
Contrôle : même règle à une heure au hasard de la journée (doit donner ~50 %).

### 3. Calendrier économique : s'abstenir (ou prévoir l'amplitude) autour des annonces

**Idée.** Colonne « minutes avant/après la prochaine annonce importante » (NFP, CPI, Fed, BCE, PMI, stocks pétrole
EIA le mercredi 16 h 30 Paris) et « importance de l'annonce ». Utilisation : couper les prédictions de direction de
5 min avant à 15 min après (le spread explose et le sens est un pile ou face), et donner cette info à l'IA d'amplitude.

**Preuves.**
- Kurov, Sancetta, Strasser & Wolfe (JFQA, E-mini S&P et T-note 2008-2014) : 30 min avant 9 annonces sur 20, le prix
  dérive déjà dans le bon sens (environ 40 % du mouvement total). **Non exploitable directement** (le sens n'est connu
  qu'après) mais ça prouve que ces créneaux sont « spéciaux » et ne doivent pas être mélangés au reste.
- Notre propre expérience : la stratégie « Avant la Fed » a été retirée ; l'intérêt ici est le **filtre**, pas un pari.

**Gain réaliste.** Pas de hausse de la réussite en soi, mais **moins de pertes** : on retire les instants où le spread
mange tout et où le passé ne dit rien. Souvent +0,5 à +1 point sur les prédictions gardées.

**Faisable gratuit.** Oui. Flux JSON hebdomadaire public du calendrier ForexFactory (`ff_calendar_thisweek.json`,
domaine faireconomy) à enregistrer chaque semaine ; pour le passé, les dates des grandes annonces US (NFP 1er vendredi,
CPI, FOMC) sont publiques et peuvent être codées à la main. À vérifier : disponibilité et limites du flux.

---

## Priorité 2 : à commencer à enregistrer tout de suite (pas d'historique)

### 4. Sentiment des clients Capital.com (en contrarien) + intensité des cotations

**Idée.** L'API Capital.com a un point d'accès gratuit « Client Sentiment » (Markets Info : % de clients acheteurs /
vendeurs par marché). Les particuliers perdent en moyenne : un positionnement extrême est souvent un signal **inverse**.
Le flux WebSocket donne aussi `bidQty` / `ofrQty` (quantités au meilleur prix) et chaque mise à jour de cotation :
compter les mises à jour par minute = activité réelle, que nos bougies ne donnent qu'en partie (`lastTradedVolume`).

**Preuves.**
- Nolte & Nolte (Lancaster, OANDA EUR/USD 2003-2004) : le flux d'ordres des particuliers, par type d'ordre, améliore
  les prévisions à 1-20 min hors échantillon. Amélioration **petite** (erreur 1,0656 contre 1,0713 à 20 min, p = 0,004),
  sans test de trading. Données vieilles, une seule paire.
- IG publie que son « IG Client Sentiment » s'utilise en contrarien : c'est du **marketing**, aucun chiffre vérifiable.

**Gain réaliste.** Inconnu, probablement faible à 15 min, plus utile à 60 min. Mais c'est une donnée **que personne
d'autre n'a gratuitement** pour Capital.com, et elle coûte une requête par minute (limite API : 10 requêtes/s).

**Faisable gratuit.** Oui, mais il faut **d'abord l'enregistrer** (pas d'historique) : ajouter une ligne au tour de
1 min qui sauvegarde le sentiment des 8 marchés dans les archives. Test possible vers mi-décembre (2-3 semaines).
WebSocket : le tour GitHub Actions peut l'écouter ~45 s par minute (max 40 marchés).

### 5. Apprentissage en ligne + cibles multiples (méthode des gagnants Jane Street)

**Idée.** Les gagnants de la compétition Kaggle Jane Street 2024-2025 (prévision en temps réel, données anonymes)
attribuent leur plus gros gain à **l'apprentissage en ligne** (le modèle se met à jour chaque jour avec les nouvelles
réponses), devant le travail sur les colonnes, puis les **cibles auxiliaires** (apprendre en même temps 5, 15, 30, 60 min
et l'amplitude), puis l'ensemble. Ordre rapporté : en ligne +0,008, colonnes +0,003, cibles auxiliaires +0,002,
ensemble +0,0007 (score de la compétition). Source secondaire, à vérifier sur les écrits Kaggle d'origine.

**Gain réaliste.** Surtout de la **stabilité** quand le marché change de régime (c'est notre problème : les gagnantes
récentes ne tiennent pas). Score Kaggle ≠ argent après frais.

**Faisable gratuit.** Oui. LightGBM `init_model` chaque nuit (déjà prévu dans le rapport « réentraîner sans oubli »),
ou la bibliothèque `river` (forêt adaptative). Cibles multiples : un réseau simple avec 5 sorties.

### 6. Niveaux ronds (ordres stop et objectifs groupés)

**Idée.** Colonne « distance au chiffre rond le plus proche » (EURUSD 1,0500 / 1,0550 ; or 2 650 / 2 700 ; US100 par
100 points), en multiples d'ATR, et côté (au-dessus / au-dessous).

**Preuves.** Osler (Journal of Finance 2003, ordres réels d'une grande banque, FX) : les objectifs de gain sont
regroupés pile sur les chiffres ronds (le prix **rebondit** dessus), les stops juste au-delà (le prix **accélère**
quand il les franchit). Effet causal (vrais carnets d'ordres), mais ancien et mesuré en FX seulement.

**Gain réaliste.** Faible, localisé aux moments où le prix est à moins d'1 ATR d'un chiffre rond.
**Faisable gratuit.** Oui, trivial.

---

## Priorité 3 : intéressant, mais preuves faibles ou coût élevé

### 7. Méta-étiquetage « triple barrière » avec le spread dedans
Le principe de López de Prado (un 2e modèle décide si on suit le 1er) est déjà en cours sous la forme « abstention ».
Ce qui manque : des étiquettes **triple barrière** (objectif = k × ATR, stop = k × ATR, limite de temps = horizon),
spread inclus, au lieu de « monte / baisse à H ». Preuve publiée faible : Singh & Joubert (Hudson Thames, E-mini S&P
2011-2019, un an de test) : précision 0,48 → 0,54 sur la tendance, **sans frais**, un seul marché. À tester mais sans
attendre de miracle.

### 8. Débruitage (auto-encodeur supervisé)
Utilisé par plusieurs gagnants Jane Street 2021 (arXiv 2404.01866 le reprend). Gain faible et risque de triche si
l'auto-encodeur voit les jours de test. Seulement après les pistes 1-6.

### 9. VIX et rendements obligataires comme colonnes pour les indices
Si Capital.com cote VIX / taux US en CFD, les ajouter aux marchés croisés (en cours dans l'autre fil). Pas de preuve
forte à 15 min.

### 10. Affiner (fine-tuning) les géantes
Preuves **négatives** récentes : Cheung (arXiv 2607.12248, 2026) : TimesFM affiné avec LoRA sur NASDAQ-100/S&P 500
n'a **aucune** compétence au-delà du taux « toujours hausse » (80 % affiché = artefact, taux de base 70 %).
Rahimikia 2025 et Upadhyay 2026 vont dans le même sens. On garde le plan déjà décidé : géantes figées + correcteur.

---

## Écarté (et pourquoi)

| Piste | Raison |
|---|---|
| Google Trends / Wikipedia | Données jour/semaine, trop lentes pour 5-60 min (utiles seulement en journalier). |
| Déséquilibre du carnet d'ordres (OFI) | Capital.com ne donne pas de carnet, seulement le meilleur prix. Les papiers OFI (Cont et al.) travaillent à la seconde sur de vrais carnets. Le remplaçant gratuit = piste 4 (`bidQty`/`ofrQty` + intensité). |
| Décomposition ondelettes / EMD | Nombreux papiers à 70-90 % sont de la **triche** : la décomposition est calculée sur toute la série, donc elle voit le futur (arXiv 2405.06986, AF-190900). |
| LLM qui lisent les news en direct | Risque de « fuite » : le LLM a vu l'histoire pendant son entraînement (arXiv 2512.23847). Payant à l'échelle de la minute. |
| Dérive avant annonce comme pari | Le sens n'est connu qu'après l'annonce ; garder comme filtre (piste 3). |

---

## Pièges à vérifier sur chaque chiffre (vus dans les papiers lus)

1. **Taux de base** : 80 % de réussite peut être 70 % de « toujours hausse ». Toujours afficher le sens majoritaire.
2. **Score ≠ argent** : précision, R², score Kaggle ne disent rien du gain après spread.
3. **Un an, un marché** : la plupart des preuves (méta-étiquetage, sentiment) tiennent sur un seul marché et une seule
   période ; on exige les 8 marchés et des jours jamais vus.
4. **Effets qui s'usent** : les fixings FX ont faibli après 2014 ; tester par année.
5. **Décompositions et normalisations calculées sur toute la série** = triche invisible.

---

## Ordre de test proposé

1. Ce week-end (cache existant) : pistes 1, 2, 6 dans le labo multi-cerveaux, chacune « avec / sans », prix mélangés.
2. Dès maintenant : enregistrer sentiment Capital.com + calendrier (pistes 3, 4) dans les archives.
3. Semaine du 30/11 : filtre calendrier (piste 3) + apprentissage en ligne et cibles multiples (piste 5).
4. Vers le 11/12 (bilan 2 semaines) : premier test du sentiment ; méta-étiquetage triple barrière (piste 7).

Ce qui est honnête d'attendre : aucune de ces pistes ne promet 60 % partout. Ce qu'elles peuvent donner, c'est
**quelques créneaux et quelques marchés** où la réussite après spread devient nettement positive, et un tri plus
fin des moments où il vaut mieux ne rien faire. C'est exactement le chemin vers des trades moins nombreux mais
meilleurs.

## Sources

- Haendler, Heston, Korajczyk, Sadka, « The Intra-Day Stock Return Periodicity Puzzle », SSRN 5749704 (2025) : https://papers.ssrn.com/ab_id=5749704
- Heston, Korajczyk, Sadka, « Intraday Patterns in the Cross-section of Stock Returns » : https://arxiv.org/pdf/1005.3535.pdf
- Krohn, Mueller, Whelan, « Foreign Exchange Fixings and Returns Around the Clock » : https://www.wu.ac.at/fileadmin/wu/d/ri/isk/VSFX_2022/Paper/Session_III_1a_Krohn__foreign_Exchange_Fixings_Returns_Around_The_Clock_0712.pdf
- Kim, Hansen, « The Quarter-Hour Effect » : https://arxiv.org/html/2607.09426v2
- Gao, Han, Li, Zhou, « Market Intraday Momentum », JFE 2018 : https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414
- Baltussen, Da, Lammers, Martens, « Hedging Demand and Market Intraday Momentum », JFE 2021 : https://www3.nd.edu/~zda/intramom.pdf
- Kurov, Sancetta, Strasser, Wolfe, « Price Drift Before U.S. Macroeconomic News » : https://www.skidmore.edu/economics/documents/KSSW2017-PriceDriftBeforeUSMacroeconomicNews.pdf
- Nolte & Nolte, retail order flow OANDA : https://eprints.lancs.ac.uk/71649/1/_paper.pdf
- API Capital.com (Client Sentiment, WebSocket, limites) : https://open-api.capital.com/
- IG Client Sentiment (marketing) : https://www.ig.com/en/trading-strategies/_how-to-trade-using-ig-client-sentiment-240912
- Synthèse Jane Street Kaggle (source secondaire) : https://vankyle00.github.io/trading-models/docs/concepts/02-jane-street-key-concepts.html
- Osler, « Currency Orders and Exchange Rate Dynamics », J. of Finance 2003 : https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr125.pdf
- Singh & Joubert, méta-étiquetage (Hudson Thames) : https://hudsonthames.org/does-meta-labeling-add-to-signal-efficacy/
- Chalkidis & Savani, « Trading via Selective Classification » (métaux CME 30 min) : https://arxiv.org/abs/2110.14914
- Cheung, LoRA TimesFM sans compétence au-delà du taux de base : https://arxiv.org/abs/2607.12248
- Rahimikia et al., TSFM en finance : https://arxiv.org/html/2511.18578v1
- Fu et al., TimesFM affiné finance : https://arxiv.org/html/2412.09880v1
- Auto-encodeur supervisé : https://arxiv.org/html/2404.01866v1
- Biais EMD : https://journals.sagepub.com/doi/10.3233/AF-190900 ; https://arxiv.org/pdf/2405.06986v1.pdf
- Biais d'anticipation des LLM : https://arxiv.org/pdf/2512.23847
- Or : qui mène la découverte des prix (spot, futures, ETF) : https://ideas.repec.org/a/wly/jfutmk/v41y2021i7p1092-1123.html

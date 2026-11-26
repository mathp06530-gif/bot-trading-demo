# Bot de trading démo (Capital.com)

Ce bot trade **avec de l'argent fictif uniquement**, sur un compte démo Capital.com.
Il tourne tout seul, 24 h/24, gratuitement grâce à GitHub, et tu le suis sur ton PC, ton téléphone et ta tablette.

## Ce qui tourne (depuis le nettoyage du 26/11/2026)

| Stratégie | Marchés | Risque par trade | Code |
|---|---|---|---|
| **Cassure 4 h** : achète quand le prix casse le plus haut des 20 dernières bougies de 4 h (vend sous le plus bas), dans le sens de l'EMA 200 | or, argent | 3 % | `bot/cassure.py` |
| **Rapide 5 min** : EMA 9/50 en 5 min, seulement dans le sens des tendances 1 h et 4 h | or | 1 % | `bot/rapide.py` |

Avec les **garde-fous** (`bot/garde_fous.py`) : coupe-circuit à -50 % depuis le plus haut, plus d'ordre après -15 % dans la
journée, positions et risque total plafonnés, pause autour des grandes annonces américaines, pause de 24 h après 3 stops
d'affilée. Et l'**auto-amélioration** chaque dimanche (voir plus bas).

Tout ce qui a été retiré le 26/11/2026 (Tendance Bitcoin, Élan, Supertrend Ethereum, usine MACD gaz/Tesla,
Avant la Fed, veille d'actus, simulateur, deux cerveaux, études de backtest) est intact dans la branche
**`sauvegarde-26-11`** : on peut tout remettre.

| Élément | Rôle |
|---|---|
| `bot/main.py` | un tour du bot : chaque stratégie de la liste `STRATEGIES`, puis mise à jour de `docs/data.json` |
| `reglages.env` | tous les réglages, relus à chaque tour |
| `.github/workflows/moteur.yml` | fait tourner le bot toutes les minutes, sans arrêt |
| `docs/` | l'application (accueil, graphique en direct, stratégies, ordres, journal, réglages) |
| `backtest/` | le labo : moteur de backtest, téléchargement des prix, usine à stratégies |

### Ajouter une stratégie

1. Écrire `bot/<nom>.py` sur le modèle de `bot/cassure.py` (signaux sur bougies terminées, stop garanti,
   passage par `garde.autoriser(...)` avant chaque ordre).
2. Ajouter une ligne dans `STRATEGIES` en haut de `bot/main.py` et ses réglages dans `reglages.env`.
3. Ajouter un test dans `tests/`.

## Installation pas à pas

### 1. Capital.com : compte démo et clé pour le bot

1. Installe l'appli Capital.com ([iPhone/iPad](https://apps.apple.com/fr/app/id1230088754), [Android](https://play.google.com/store/apps/details?id=com.capital.trading&hl=fr), ou sur PC dans le navigateur : [capital.com/trading/platform](https://capital.com/trading/platform/)).
2. Crée ton compte et passe en mode **Démo**.
3. Sur PC, dans la plateforme web : **Paramètres → Sécurité**, active la **double authentification (2FA)**. C'est obligatoire pour créer une clé.
4. **Paramètres → API integrations → Generate new key** :
   - nom : `bot-demo`
   - choisis un **mot de passe propre à la clé** (pas celui de ton compte !)
   - entre ton code 2FA
5. Copie la **clé API** affichée. Elle n'est montrée qu'une seule fois.

Tu as maintenant 3 informations, à ne **jamais** envoyer dans un chat :
- la clé API
- ton e-mail Capital.com
- le mot de passe de la clé

### 2. GitHub : le dépôt qui fait tourner le bot

1. Crée un compte sur [github.com](https://github.com) si besoin, puis un **nouveau dépôt public** nommé `bot-trading-demo`.
   *Public* = gratuit et illimité pour faire tourner le bot. Tes clés restent cachées (voir étape 3) ;
   seuls le code et les résultats du compte démo sont visibles.
2. Mets-y les fichiers de ce dossier (Claude peut le faire pour toi).

### 3. Ranger les clés en sécurité dans GitHub

Dans le dépôt : **Settings → Secrets and variables → Actions → New repository secret**, crée ces 3 secrets :

| Nom du secret | Valeur |
|---|---|
| `CAPITAL_API_KEY` | la clé API |
| `CAPITAL_IDENTIFIER` | ton e-mail Capital.com |
| `CAPITAL_PASSWORD` | le mot de passe de la clé |

### 4. Allumer le bot

1. Onglet **Actions** du dépôt → accepte d'activer les workflows si GitHub le demande.
2. Clique sur **Bot de trading démo** → **Run workflow** pour un premier tour tout de suite.
3. Ensuite le workflow **Moteur du bot** le fait tourner toutes les minutes, sans arrêt.

### 5. Le tableau de bord sur tous tes appareils

1. Dans le dépôt : **Settings → Pages** → *Source* : **Deploy from a branch**, branche **main**, dossier **/docs** → *Save*.
2. Après 1 ou 2 minutes, ton tableau de bord est à l'adresse :
   `https://TON-PSEUDO-GITHUB.github.io/bot-trading-demo/`
3. Sur téléphone et tablette : ouvre ce lien, puis **Partager → Sur l'écran d'accueil** (iPhone/iPad)
   ou **⋮ → Ajouter à l'écran d'accueil** (Android). Tu auras une icône comme une appli.

---

### 6. L'application (PC, téléphone, tablette) et les commandes

1. Ouvre `https://mathp06530-gif.github.io/bot-trading-demo/`.
2. **Installer** : sur PC (Chrome/Edge), clique sur **⬇ Installer** en haut ou sur l'icône d'installation dans la barre d'adresse.
   Un raccourci « Bot de trading démo » est créé sur le bureau. Sur iPhone/iPad : Partager → *Sur l'écran d'accueil*. Sur Android : ⋮ → *Installer l'application*.
3. **Commander le bot** (Pause, Reprendre, Analyser maintenant, Fermer la position) : crée une clé GitHub *fine-grained*
   ([lien](https://github.com/settings/personal-access-tokens/new)) limitée au dépôt `bot-trading-demo`, avec
   *Actions : Read and write* et *Contents : Read-only*, puis colle-la dans l'onglet **Réglages** de l'application, sur chaque appareil.

## Réglages

Tout est dans `reglages.env` (relu à chaque tour, une modification s'applique à la minute suivante).

## Auto-amélioration chaque semaine

Chaque dimanche à 19 h (Paris), le workflow « Auto-amélioration (chaque semaine) » :
1. fait le bilan des vrais trades de la semaine, stratégie par stratégie, comparé à la semaine d'avant ;
2. vérifie le changement adopté la semaine d'avant sur les prix de la semaine écoulée, et **l'annule tout seul** s'il a fait moins bien ;
3. teste de petites variantes des réglages (un seul réglage, d'un seul cran) sur l'historique récent (1 an en 4 h, 8 semaines en 5 min) et n'en garde **qu'une par stratégie**, seulement si elle fait mieux sur les deux moitiés de la période.

Il ne touche jamais au risque par trade ni aux garde-fous. Tout est écrit dans le Journal (filtre « Améliorations ») et dans l'onglet Stratégies. Le mode se règle dans `reglages.env` (`AUTO_AMELIORATION` : `auto`, `suggestions` ou `non`). Détails : `bot/amelioration.py`.

## Usine à stratégies (labo)

`backtest/usine.py` fabrique et teste des millions de stratégies sur ~40 marchés Capital.com, et ne garde que
celles qui gagnent aussi sur des années jamais vues. Lancement à la main seulement (onglet Actions >
« Usine à stratégies »). Elle ne passe aucun ordre. 1re fouille (26/11/2026) : 3,66 millions d'essais, 0 solide.

## Si quelque chose ne va pas

- **Le tableau de bord affiche « Problème »** : regarde la dernière ligne rouge du journal, elle explique l'erreur.
- **« Connexion refusée »** : vérifie les 3 secrets GitHub (la clé, l'e-mail, le mot de passe *de la clé*).
- **Rien ne bouge** : onglet **Actions** du dépôt, vérifie que le workflow est activé.

## Tester le code sans connexion

```bash
pip install requests pytest
python -m pytest -q
```

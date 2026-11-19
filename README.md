# Bot de trading démo (Capital.com + TradingView)

Ce bot trade **avec de l'argent fictif uniquement**, sur un compte démo Capital.com.
Il tourne tout seul, 24 h/24, gratuitement grâce à GitHub, et tu le suis sur ton PC, ton téléphone et ta tablette.

## Comment ça marche

| Élément | Rôle | Où le voir |
|---|---|---|
| Script TradingView (`tradingview/strategie_demo.pine`) | Affiche les signaux ACHAT / VENTE sur ton graphique | Appli et site TradingView |
| Bot (`bot/`) | Toutes les 5 minutes, il analyse le Bitcoin et passe les ordres sur ton compte démo | Appli Capital.com (mode Démo) |
| Tableau de bord (`docs/index.html`) | 6 onglets : Accueil (valeur, gains 24 h / 7 j / 30 j / 1 an, courbe), Ordres, Marché, Stats, Journal, Réglages | Un lien web, sur tous tes appareils |

La stratégie de démonstration est un **croisement de moyennes mobiles (EMA 9 / EMA 21)** en bougies de 15 minutes :
quand la moyenne rapide passe au-dessus de la lente, le bot achète ; quand elle passe en dessous, il vend.
C'est la même règle dans le script TradingView et dans le bot. Pour changer de stratégie plus tard,
on remplacera `bot/strategie.py` et le script Pine.

> ⚠️ TradingView ne permet pas à un programme de passer des ordres sur ton compte TradingView.
> Le bot passe donc ses ordres sur Capital.com, qui est un courtier partenaire de TradingView.

---

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
3. Ensuite il se lance seul toutes les 5 minutes (GitHub a parfois quelques minutes de retard).

### 5. Le tableau de bord sur tous tes appareils

1. Dans le dépôt : **Settings → Pages** → *Source* : **Deploy from a branch**, branche **main**, dossier **/docs** → *Save*.
2. Après 1 ou 2 minutes, ton tableau de bord est à l'adresse :
   `https://TON-PSEUDO-GITHUB.github.io/bot-trading-demo/`
3. Sur téléphone et tablette : ouvre ce lien, puis **Partager → Sur l'écran d'accueil** (iPhone/iPad)
   ou **⋮ → Ajouter à l'écran d'accueil** (Android). Tu auras une icône comme une appli.

### 6. Le script sur ton graphique TradingView

1. Sur [tradingview.com](https://www.tradingview.com) (sur PC), ouvre un graphique **CAPITALCOM:BTCUSD** en **15 minutes**.
2. En bas, ouvre **Éditeur Pine**, efface tout, colle le contenu de `tradingview/strategie_demo.pine`, puis **Enregistrer** et **Ajouter au graphique**.
3. Les flèches ACHAT / VENTE apparaissent, et l'onglet **Testeur de stratégie** montre les résultats passés.
   Le script est enregistré sur ton compte : tu le retrouves aussi dans l'appli TradingView sur téléphone et tablette.
4. (Facultatif) Panneau **Trading** en bas du graphique → **Capital.com** pour relier ton compte.

---

### 7. L'application (PC, téléphone, tablette) et les commandes

1. Ouvre `https://mathp06530-gif.github.io/bot-trading-demo/`.
2. **Installer** : sur PC (Chrome/Edge), clique sur **⬇ Installer** en haut ou sur l'icône d'installation dans la barre d'adresse.
   Un raccourci « Bot de trading démo » est créé sur le bureau. Sur iPhone/iPad : Partager → *Sur l'écran d'accueil*. Sur Android : ⋮ → *Installer l'application*.
3. **Commander le bot** (Pause, Reprendre, Analyser maintenant, Fermer la position) : crée une clé GitHub *fine-grained*
   ([lien](https://github.com/settings/personal-access-tokens/new)) limitée au dépôt `bot-trading-demo`, avec
   *Actions : Read and write* et *Contents : Read-only*, puis colle-la dans l'onglet **Réglages** de l'application, sur chaque appareil.

## Réglages

Dans `.github/workflows/bot.yml` :

| Réglage | Par défaut | Signification |
|---|---|---|
| `MARCHES` | `BTCUSD` | marchés à trader, séparés par des virgules (ex. `BTCUSD,GOLD`) |
| `TAILLE` | `0.01` | taille de chaque position |
| `UNITE` | `MINUTE_15` | durée d'une bougie |
| `STOP_PCT` | `3` | stop de sécurité en % du prix |

## Si quelque chose ne va pas

- **Le tableau de bord affiche « Problème »** : regarde la dernière ligne rouge du journal, elle explique l'erreur.
- **« Connexion refusée »** : vérifie les 3 secrets GitHub (la clé, l'e-mail, le mot de passe *de la clé*).
- **Rien ne bouge** : onglet **Actions** du dépôt, vérifie que le workflow est activé.

## Tester le code sans connexion

```bash
pip install requests pytest
python -m pytest -q
```

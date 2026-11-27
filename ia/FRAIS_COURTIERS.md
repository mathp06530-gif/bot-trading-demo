# Changer de courtier pour payer moins de frais ? (27/11/2026)

Question de Mathis : « et si on passait à un autre fournisseur dont les frais ne sont pas trop élevés ? »
Règles gardées : tout gratuit, compte DÉMO seulement, rien de changé dans le bot ni dans les IA en direct.

## 1. Les courtiers regardés (sources officielles, lues le 27/11/2026)

| Courtier (entité pour la France) | Frais | Démo gratuite + API pour un bot | Verdict frais |
|---|---|---|---|
| **Capital.com** (actuel, CySEC) | spread seul, pas de commission | oui, API REST démo (déjà utilisée) | référence |
| **IC Markets EU** (IC Markets (EU) Ltd, CySEC 362/18) | compte Raw : spread brut + commission **3 $ par 100 000 $ par côté** (cTrader) ou 3,25 €/lot/côté (MT5), **seulement sur devises et métaux** ; indices et pétrole sans commission | oui : démo gratuite, **cTrader Open API** (gratuite) ou MT5 | le moins cher trouvé, mais à peine |
| **Pepperstone EU** (Pepperstone EU Ltd, CySEC 388/20) | compte Razor : 3,50 $/lot/côté sur devises ; 0 commission sur indices et matières premières ; or « dès 0,05 pt » | oui : démo gratuite, cTrader Open API / MT5 / TradingView | proche d'IC Markets (tableau par marché non publié en clair) |
| **OANDA Europe** (OANDA TMS Brokers, Pologne) | spread seul : EUR/USD dès 0,8 pip, or dès 0,25 $, DE30 dès 1 pt | oui : démo 50 000 € virtuels, API développeur | **plus cher** que Capital.com (EUR/USD 0,8 pip contre ~0,7) |
| **Interactive Brokers** (IBKR Ireland, Banque centrale d'Irlande) | CFD au spread de la Bourse **+ commission** : US500 0,005 %, US Tech 100 0,010 %, DE40 0,005 % (min 1 $/1 € par ordre), or 0,015 %, argent 0,03 % (min 2 $), devises 0,2 pb (min 2 $), pétrole 0,015 % | compte papier + API TWS | **plus cher** à notre échelle : commission payée à l'entrée ET à la sortie, et **minimum 1-2 $ par ordre** (énorme sur un compte de ~100 €) |

Spreads moyens officiels d'IC Markets Raw (page ic.com ; la page EU ne donne que « dès 0,0 ») :
or 0,09 $, argent 0,03 $, pétrole WTI 0,034 $, US500 0,49 pt, US Tech 100 1,81 pt, DE40 1,34 pt, EUR/USD ~0,1 pip, GBP/USD ~0,1-0,2 pip.

Important : le prix du marché lui-même a un écart acheteur/vendeur. Même le meilleur courtier ECN ne le supprime pas ;
il remplace une partie du spread par une commission.

## 2. Coût aller-retour par marché (en % du prix)

Capital.com = spread réellement payé dans l'historique (moyenne sur 12-24 mois, bougies 15 min).
IC Markets = spread moyen officiel + commission, calculé au prix de chaque bougie (sortie du labo, `ia/frais/ic.md`).

| Marché | Capital.com | IC Markets Raw | Différence |
|---|---|---|---|
| Or | 0,0094 % | 0,0084 % | -11 % |
| Argent | 0,079 % | 0,069 % | -13 % |
| Pétrole WTI | 0,047 % | 0,048 % | pareil |
| US500 | 0,0078 % | 0,0074 % | -5 % |
| US100 | 0,0072 % | 0,0074 % | pareil |
| DE40 | ~0,007 % | 0,0056 % | ~-20 % |
| EUR/USD | 0,0058 % | 0,0069 % | **+19 % (plus cher)** |
| GBP/USD | ~0,010 % | 0,0075 % | ~-25 % |

Dans le labo, le coût moyen par trade passe de **~0,024 % (Capital.com) à ~0,017 % (IC Markets)**, soit environ -30 %.
Attention : ce -30 % est flatteur pour IC Markets. Pour Capital.com, le labo paie le vrai spread de chaque instant,
y compris la nuit, les ouvertures et les annonces où il s'élargit. Pour IC Markets, on ne connaît qu'une moyenne
publiée, qui s'élargit aussi à ces moments-là. Aux heures calmes, marché par marché, l'écart réel est plutôt de 0 à 20 %.

## 3. Les mêmes tests des IA refaits avec ces frais

Mêmes IA, mêmes 12 mois jamais vus, mêmes règles anti-triche. Gain moyen par trade après frais (en % du prix) :

**Toutes les prédictions** (le cas moyen) :

| Horizon | Capital.com | IC Markets | Frais ÷ 2 | Zéro frais |
|---|---|---|---|---|
| 15 min (Aiguilleur) | -0,023 % | -0,016 % | -0,011 % | **+0,001 %** |
| 1 h (Vote simple) | -0,024 % | -0,017 % | -0,012 % | +0,000 % |
| 4 h (Vote simple) | -0,020 % | -0,012 % | -0,008 % | +0,005 % |

**Les 5 % de moments les plus sûrs** :

| Horizon | Réussite | Capital.com | IC Markets | Frais ÷ 2 | Zéro frais | Marchés gagnants (IC) | Mois positifs (IC) |
|---|---|---|---|---|---|---|---|
| 15 min (Aiguilleur) | 53,8 % | -0,022 % | -0,013 % | -0,009 % | **+0,003 %** | 0/8 | — |
| 1 h (Vote simple) | 52,2 % | -0,002 % | **+0,005 %** | +0,010 % | +0,022 % | 5/8 | 51/102 |
| 4 h (Vote simple) | 52,9 % | **+0,036 %** | **+0,043 %** | +0,047 % | +0,059 % | 8/8 | 53/99 |

Ce que ça veut dire :
- **15 min : aucun courtier ne peut le sauver.** Même avec zéro frais, les moments les plus sûrs ne rapportent que
  +0,003 % par trade, soit à peine un tiers du spread de l'or. Les 53-54 % de réussite portent sur de tout petits mouvements.
- **1 h : IC Markets fait passer le Vote simple (5 % les plus sûrs) de -0,002 % à +0,005 %.** C'est positif, mais
  minuscule : un mois sur deux seulement est positif. Pas solide.
- **4 h : c'est déjà positif chez Capital.com** dans le dernier labo (+0,036 %, 8 marchés sur 8). IC Markets ajoute
  ~+0,007 %. Prudence : sur les prix mélangés sans frais, le même réglage donne déjà +0,023 % (effet de la tendance de
  fond de l'or et des indices), donc le vrai avantage des IA est plutôt ~+0,035 % par trade avant frais.

## 4. Conclusion

- **Meilleur candidat : IC Markets EU, compte Raw cTrader** (CySEC, démo gratuite, cTrader Open API gratuite).
  Pepperstone EU Razor est très proche. OANDA (spreads plus larges) et Interactive Brokers (commission à l'entrée et à
  la sortie, minimum 1-2 $ par ordre) sont **plus chers** que Capital.com pour nous.
- **Gain de frais : environ -30 % sur le papier, plutôt 0 à 20 % en vrai selon le marché**, et EUR/USD est plus cher.
  Capital.com est déjà un courtier bon marché sur nos 8 marchés : on ne trouvera pas de frais « nettement » plus bas.
- **Est-ce que ça rend les IA rentables sur le passé ?** Non à 15 min (même à zéro frais). À peine à 1 h (positif mais
  pas régulier). À 4 h c'est déjà positif chez Capital.com, avec ou sans changement.
- **Conseil : ne pas changer de courtier maintenant.** Le levier qui marche, c'est l'horizon plus long (4 h), pas le
  courtier. Changer demanderait de réécrire toute la partie API du bot (Capital.com → cTrader) pour ~0,007 % par trade.
- Piste gratuite pour plus tard, si Mathis le veut : ouvrir une démo IC Markets (ça prend 5 min, à son nom, gratuit)
  pour mesurer leurs vrais spreads minute par minute, nuit comprise, avant toute décision.

---
Comment c'est calculé : workflow `frais_courtiers.yml` (PR 88). Il rejoue exactement le labo multi-cerveaux
(12 derniers mois jamais vus, mêmes IA, même anti-triche « prix mélangés ») en remplaçant seulement les frais.
Scénarios : `ic` (IC Markets Raw cTrader), `moitie` (frais Capital.com ÷ 2, hypothèse que personne n'offre),
`zero` (aucun frais : le plafond). Détails : `ia/frais/ic.md`, `ia/frais/moitie.md`, `ia/frais/zero.md`.

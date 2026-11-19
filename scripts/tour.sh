#!/usr/bin/env bash
# Un tour du bot, toujours à partir de la toute dernière version du dépôt.
# Si quelqu'un d'autre a enregistré entre-temps (commande depuis l'appli, autre tour),
# on repart de sa version et on refait le tour : aucun résultat n'est perdu.
set -u
git config user.name "bot-trading-demo"
git config user.email "bot-trading-demo@users.noreply.github.com"
for essai in 1 2 3; do
  git fetch -q origin main && git reset -q --hard origin/main
  python -m bot.main || echo "Le tour a signalé une erreur (voir le journal de l'appli)."
  git add docs/data.json
  git diff --cached --quiet && exit 0
  git commit -qm "Tour du bot $(date -u +%Y-%m-%dT%H:%MZ)"
  git push -q origin HEAD:main && exit 0
  echo "Enregistrement en même temps qu'un autre tour : on recommence ($essai/3)."
  sleep $((RANDOM % 5 + 2))
done
exit 1

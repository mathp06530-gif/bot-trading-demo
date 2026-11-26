#!/usr/bin/env bash
# Crée un environnement Python par famille d'IA géante (torch CPU). Une famille qui échoue est simplement sautée.
set -u
cd "$(dirname "$0")/../.."
pip install -q uv
mkdir -p .venvs ia/vendor
FAMS=$(python -c "from ia.geantes.familles import FAMILLES; print(' '.join(FAMILLES))")
for f in ${IA_FAMILLES:-$FAMS}; do
  (
    set -e
    PIP=$(python -c "from ia.geantes.familles import FAMILLES; print(' '.join(FAMILLES['$f']['pip']))")
    GIT=$(python -c "from ia.geantes.familles import FAMILLES; print(FAMILLES['$f'].get('git',''))")
    uv venv -q --python 3.12 .venvs/$f
    uv pip install -q --python .venvs/$f/bin/python --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match torch numpy pandas $PIP
    if [ -n "$GIT" ]; then
      [ -d ia/vendor/$f ] || git clone -q --depth 1 "$GIT" ia/vendor/$f
      [ -f ia/vendor/$f/requirements.txt ] && uv pip install -q --python .venvs/$f/bin/python \
        --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
        --index-strategy unsafe-best-match -r ia/vendor/$f/requirements.txt || true
    fi
    echo "famille $f : installée"
  ) || { echo "famille $f : ÉCHEC d'installation (mise de côté)"; rm -rf .venvs/$f; }
done

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
    PY=$(python -c "from ia.geantes.familles import FAMILLES; print(FAMILLES['$f'].get('py','3.12'))")
    SANSREQ=$(python -c "from ia.geantes.familles import FAMILLES; print(1 if FAMILLES['$f'].get('sans_requirements') else '')")
    uv venv -q --python $PY .venvs/$f
    uv pip install -q --python .venvs/$f/bin/python --index-url https://download.pytorch.org/whl/cpu \
      --extra-index-url https://pypi.org/simple --index-strategy unsafe-best-match torch numpy pandas $PIP
    if [ -n "$GIT" ]; then
      [ -d ia/vendor/$f ] || git clone -q --depth 1 "$GIT" ia/vendor/$f
      [ -z "$SANSREQ" ] && [ -f ia/vendor/$f/requirements.txt ] && uv pip install -q --python .venvs/$f/bin/python \
        --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
        --index-strategy unsafe-best-match -r ia/vendor/$f/requirements.txt || true
    fi
    echo "famille $f : installée"
  ) || { echo "famille $f : ÉCHEC d'installation (mise de côté)"; rm -rf .venvs/$f; }
done

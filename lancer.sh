#!/usr/bin/env bash
# Lance SmEcoFarm depuis n'importe où (double-clic, démarrage automatique...).
# Les options sont transmises à main.py, par exemple : ./lancer.sh --simulation incendie
cd "$(dirname "$(readlink -f "$0")")" || exit 1
if [ -f .venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source .venv/bin/activate
fi
exec python3 main.py "$@"

#!/usr/bin/env bash
# Installation de SmEcoFarm sur Raspberry Pi (ou PC Linux).
# Usage, depuis le dossier du projet :   bash install.sh
#
# Le script :
#   1. affiche le système détecté (32 ou 64 bits, version de Python) ;
#   2. installe les paquets système utiles (OpenCV, YAML, GPIO, outils webcam) ;
#   3. crée l'environnement Python .venv et installe les dépendances ;
#   4. installe le moteur d'IA TFLite adapté (ai-edge-litert, sinon tflite-runtime) ;
#   5. lance les tests.

set -u
cd "$(dirname "$0")"

vert()  { printf '\033[32m%s\033[0m\n' "$*"; }
rouge() { printf '\033[31m%s\033[0m\n' "$*"; }
titre() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }

titre "1. Système détecté"
BITS=$(python3 -c 'import struct; print(struct.calcsize("P") * 8)')
PYVER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "Noyau          : $(uname -m)"
echo "Python         : $PYVER ($BITS bits)"
[ -f /etc/os-release ] && echo "Système        : $(. /etc/os-release; echo "$PRETTY_NAME")"
if [ "$BITS" != "64" ]; then
    rouge "Attention : Python est en 32 bits. Le moteur d'IA recommandé (ai-edge-litert)"
    rouge "n'existe qu'en 64 bits. Le script va essayer tflite-runtime à la place."
fi

if [ "${1:-}" != "--sans-apt" ]; then
    titre "2. Paquets système (mot de passe demandé si nécessaire)"
    sudo apt-get update
    # Installés un par un : certains n'existent pas sur toutes les versions du système
    for paquet in python3-venv python3-pip python3-opencv python3-yaml python3-lgpio \
                  python3-gpiozero libgpiod2 v4l-utils; do
        if sudo apt-get install -y "$paquet" >/dev/null 2>&1; then
            echo "  ok      $paquet"
        else
            echo "  ignoré  $paquet (non disponible sur ce système)"
        fi
    done
fi

titre "3. Environnement Python .venv"
if [ ! -x .venv/bin/python ]; then
    rm -rf .venv
    python3 -m venv --system-site-packages .venv || { rouge "Échec de création du venv"; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt || { rouge "Échec de l'installation des dépendances (voir le message ci-dessus)"; exit 1; }

titre "4. Moteur d'IA TFLite"
if python -c "import ai_edge_litert" 2>/dev/null || python -c "import tflite_runtime" 2>/dev/null; then
    vert "Déjà installé."
elif pip install ai-edge-litert; then
    vert "ai-edge-litert installé."
elif pip install tflite-runtime; then
    vert "tflite-runtime installé."
else
    rouge "Aucun moteur TFLite n'est disponible pour ce système (Python $PYVER, $BITS bits)."
    rouge "Solution : réinstaller « Raspberry Pi OS (64-bit) » avec Raspberry Pi Imager,"
    rouge "puis relancer : bash install.sh"
    exit 1
fi

titre "5. Tests"
if python -m pytest -q tests/; then
    vert "Installation terminée."
    echo
    echo "Pour lancer le programme :"
    echo "  source .venv/bin/activate"
    echo "  python main.py --simulation incendie --duree 90   # sans matériel"
    echo "  python main.py                                    # avec le matériel"
else
    rouge "Des tests échouent : copiez le message ci-dessus pour le diagnostic."
    exit 1
fi

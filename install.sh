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
echo "Noyau          : $(uname -m)   (Python voit : $(python3 -c 'import platform; print(platform.machine())'))"
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
                  python3-gpiozero python3-rpi.gpio libgpiod2 libopenblas0 libopenblas-dev \
                  libatlas-base-dev v4l-utils; do
        if sudo apt-get install -y "$paquet" >/dev/null 2>&1; then
            echo "  ok      $paquet"
        else
            echo "  ignoré  $paquet (non disponible sur ce système)"
        fi
    done
    # Lecteur RFID : le bus SPI doit être activé
    if [ ! -e /dev/spidev0.0 ] && command -v raspi-config >/dev/null; then
        echo "  Activation du bus SPI (lecteur RFID)..."
        sudo raspi-config nonint do_spi 0 && echo "  ok      SPI activé (redémarrez le Pi si le lecteur ne répond pas)"
    fi
    # numpy (piwheels) a besoin de libopenblas.so.0 : on vérifie qu'elle est bien là
    if ! ldconfig -p | grep -q "libopenblas.so.0"; then
        rouge "libopenblas.so.0 introuvable : tentative d'installation avec affichage des erreurs"
        sudo apt-get install -y libopenblas0 || sudo apt-get install -y libopenblas-base
        if ! ldconfig -p | grep -q "libopenblas.so.0"; then
            rouge "libopenblas.so.0 toujours absente : copiez les messages ci-dessus pour le diagnostic."
        fi
    fi
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
# Sur Raspberry Pi : numpy 1.x obligatoire (OpenCV et le moteur TFLite sont compilés pour numpy 1.x)
case "$(python -c 'import platform; print(platform.machine())')" in
    x86_64|AMD64) ;;
    *) pip install "numpy<2" ;;
esac

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

# Le moteur d'IA ne doit pas avoir remis numpy 2 : on revérifie
case "$(python -c 'import platform; print(platform.machine())')" in
    x86_64|AMD64) ;;
    *) pip install -q "numpy<2" ;;
esac

titre "5. Vérification des modules"
python - <<'PYEOF'
import importlib
modules = [("numpy", "calculs"), ("PIL", "images"), ("yaml", "configuration"),
           ("cv2", "webcams (sudo apt install python3-opencv)"),
           ("gpiozero", "GPIO : ventilateur, buzzer, MQ-135"),
           ("adafruit_dht", "capteur DHT11"), ("RPi.GPIO", "GPIO : porte (servo), lecteur RFID"),
           ("mfrc522", "lecteur RFID"), ("spidev", "bus SPI du lecteur RFID")]
for name, role in modules:
    try:
        module = importlib.import_module(name)
        print(f"  ok      {name:14s} {getattr(module, '__version__', '')}")
    except Exception as exc:
        print(f"  ÉCHEC   {name:14s} {role} : {exc}")
try:
    import Adafruit_DHT  # noqa: F401
    print("  ok      Adafruit_DHT   (ancienne bibliothèque DHT, utilisée en priorité)")
except Exception:
    pass
import os
print("  ok      bus SPI" if os.path.exists("/dev/spidev0.0")
      else "  ÉCHEC   bus SPI : sudo raspi-config > Interface Options > SPI, puis redémarrer")
for name in ("ai_edge_litert", "tflite_runtime"):
    try:
        importlib.import_module(name)
        print(f"  ok      {name:14s} moteur d'IA")
        break
    except Exception as exc:
        last = exc
else:
    print(f"  ÉCHEC   moteur d'IA : {last}")
PYEOF

titre "6. Tests"
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

"""Lancer SmEcoFarm depuis un IDE Python (Thonny, VS Code...) avec le bouton Run.

Modifiez les réglages ci-dessous, enregistrez, puis cliquez sur Run (ou F5).
Le bouton Stop arrête proprement le programme (ventilateur, buzzer et LED coupés, porte fermée).
"""

# ============ RÉGLAGES ============

# None = vrai matériel (prototype)
# "normal", "chaleur" ou "incendie" = simulation sans capteurs
SIMULATION = None

# "tout", ou une seule station : "champ", "entrepot", "acces"
STATION = "tout"

# Durée en secondes (None = sans fin, jusqu'au bouton Stop)
DUREE = None

# ==================================

import sys
from pathlib import Path

PROJET = Path(__file__).resolve().parent
VENV_PYTHON = PROJET / ".venv" / "bin" / "python"


def verifier_interpreteur():
    """Vérifie que l'IDE utilise l'environnement Python du projet (.venv)."""
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        import yaml  # noqa: F401
        try:
            import ai_edge_litert  # noqa: F401
        except ImportError:
            import tflite_runtime  # noqa: F401
        return True
    except ImportError as exc:
        print("=" * 70)
        print(f"Module manquant : {exc.name} (ou moteur d'IA ai_edge_litert / tflite_runtime)")
        print("L'IDE n'utilise pas l'environnement Python du projet.")
        print()
        print("Dans Thonny : Outils > Options > Interpréteur")
        print("  choisir « Interpréteur Python 3 alternatif ou environnement virtuel »")
        print(f"  puis indiquer : {VENV_PYTHON}")
        print("  puis OK et relancer avec Run.")
        print()
        print(f"Interpréteur actuel : {sys.executable}")
        print("=" * 70)
        return False


if __name__ == "__main__":
    if verifier_interpreteur():
        sys.path.insert(0, str(PROJET))
        sys.argv = [str(PROJET / "main.py"), "--station", STATION]
        if SIMULATION:
            sys.argv += ["--simulation", SIMULATION]
        if DUREE:
            sys.argv += ["--duree", str(DUREE)]
        import main
        main.main()

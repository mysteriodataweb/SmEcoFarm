"""Chargement du moteur d'inférence TFLite et utilitaires d'image communs."""

from pathlib import Path

import numpy as np
from PIL import Image

# Dossier racine du projet (contient models/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"


def load_interpreter(model_path, num_threads=4):
    """Crée un interpréteur TFLite avec le premier runtime disponible.

    Ordre d'essai :
      1. ai-edge-litert  (nouveau nom de tflite-runtime, recommandé sur le Pi)
      2. tflite-runtime  (ancien paquet)
      3. tensorflow      (plus lourd, pratique sur PC)
    """
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            try:
                from tensorflow.lite import Interpreter
            except ImportError as exc:
                raise ImportError(
                    "Aucun runtime TFLite trouvé. Installez-en un : pip install ai-edge-litert"
                ) from exc

    interpreter = Interpreter(model_path=str(model_path), num_threads=num_threads)
    interpreter.allocate_tensors()
    return interpreter


def to_rgb_array(image):
    """Convertit l'entrée en tableau numpy RGB uint8 (H, W, 3).

    Accepte : un chemin de fichier, une image PIL ou un tableau numpy RGB.
    Attention : OpenCV fournit des images en BGR, il faut les convertir avant
    (cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).
    """
    if isinstance(image, (str, Path)):
        image = Image.open(image)
    if isinstance(image, Image.Image):
        return np.asarray(image.convert("RGB"), dtype=np.uint8)
    array = np.asarray(image)
    if array.ndim != 3 or array.shape[2] < 3:
        raise ValueError(f"Image RGB attendue (H, W, 3), reçu {array.shape}")
    return array[:, :, :3].astype(np.uint8, copy=False)


def resize(rgb_array, size):
    """Redimensionne une image RGB vers (largeur, hauteur) = size."""
    return np.asarray(Image.fromarray(rgb_array).resize(size, Image.BILINEAR), dtype=np.uint8)


def load_labels(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

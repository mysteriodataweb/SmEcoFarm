"""Classification des maladies des feuilles avec MobileNetV2 pré-entraîné sur PlantVillage.

Le modèle connaît 38 classes (14 plantes). Comme on sait quelle plante est
filmée, on peut restreindre la prédiction aux classes de cette plante
(par défaut : tomate, 10 classes) et recalculer les probabilités entre elles.
Aucun entraînement n'est nécessaire.
"""

from dataclasses import dataclass, field

import numpy as np

from .runtime import MODELS_DIR, load_interpreter, load_labels, resize, to_rgb_array

DEFAULT_MODEL = MODELS_DIR / "disease" / "plant_disease_model.tflite"
DEFAULT_LABELS = MODELS_DIR / "disease" / "plant_labels.txt"

# Noms en français pour l'affichage (dashboard Blynk, rapport)
FRENCH_NAMES = {
    "tomato_bacterial_spot": "Tomate - tache bactérienne",
    "tomato_early_blight": "Tomate - alternariose",
    "tomato_late_blight": "Tomate - mildiou",
    "tomato_leaf_mold": "Tomate - moisissure des feuilles (cladosporiose)",
    "tomato_septoria_leaf_spot": "Tomate - septoriose",
    "tomato_spider_mites_two_spotted_spider_mite": "Tomate - acariens (tétranyque)",
    "tomato_target_spot": "Tomate - tache cible",
    "tomato_tomato_yellow_leaf_curl_virus": "Tomate - virus de l'enroulement jaune (TYLCV)",
    "tomato_tomato_mosaic_virus": "Tomate - virus de la mosaïque",
    "tomato_healthy": "Tomate - saine",
}


@dataclass
class Prediction:
    key: str            # identifiant, ex. "tomato_late_blight"
    name: str           # nom lisible en français si disponible
    confidence: float   # 0 à 1
    uncertain: bool     # True si confidence < seuil
    healthy: bool
    top: list = field(default_factory=list)  # [(key, confiance), ...] meilleures classes


class DiseaseClassifier:
    def __init__(self, model_path=DEFAULT_MODEL, labels_path=DEFAULT_LABELS,
                 crop="tomato", confidence_threshold=0.6, num_threads=4):
        """
        crop                 : plante filmée ("tomato", "potato", ...) ; None pour
                               garder les 38 classes.
        confidence_threshold : en dessous, le résultat est marqué « incertain ».
        """
        self.confidence_threshold = confidence_threshold
        self.keys = [label.replace(" ", "_") for label in load_labels(labels_path)]
        self.interpreter = load_interpreter(model_path, num_threads)

        input_details = self.interpreter.get_input_details()[0]
        self._input_index = input_details["index"]
        _, height, width, _ = input_details["shape"]
        self.input_size = (int(width), int(height))  # (224, 224)
        self._output_index = self.interpreter.get_output_details()[0]["index"]

        if crop:
            self.class_ids = [i for i, k in enumerate(self.keys) if k.startswith(crop + "_")]
            if not self.class_ids:
                raise ValueError(f"Aucune classe pour la plante '{crop}' dans le modèle")
        else:
            self.class_ids = list(range(len(self.keys)))

    def predict(self, image, top_k=3):
        """Retourne une Prediction pour l'image d'une feuille.

        image : chemin, image PIL ou tableau numpy RGB (H, W, 3).
        Pour de bons résultats : une feuille en gros plan, bien éclairée.
        """
        rgb = to_rgb_array(image)

        # Prétraitement identique à l'entraînement : RGB, 224x224, pixels / 255.
        model_input = resize(rgb, self.input_size).astype(np.float32) / 255.0
        self.interpreter.set_tensor(self._input_index, model_input[np.newaxis, ...])
        self.interpreter.invoke()
        probabilities = self.interpreter.get_tensor(self._output_index)[0]

        # Restriction à la plante choisie, puis renormalisation (somme = 1)
        crop_probs = probabilities[self.class_ids]
        crop_probs = crop_probs / max(float(crop_probs.sum()), 1e-9)

        order = np.argsort(crop_probs)[::-1]
        top = [(self.keys[self.class_ids[i]], float(crop_probs[i])) for i in order[:top_k]]
        best_key, confidence = top[0]

        return Prediction(
            key=best_key,
            name=FRENCH_NAMES.get(best_key, best_key.replace("_", " ")),
            confidence=confidence,
            uncertain=confidence < self.confidence_threshold,
            healthy=best_key.endswith("_healthy"),
            top=top,
        )

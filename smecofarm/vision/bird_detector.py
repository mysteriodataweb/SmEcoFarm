"""Détection d'oiseaux avec EfficientDet-Lite0 pré-entraîné sur COCO.

Le modèle détecte les 90 classes COCO ; on ne garde que « bird ».
Aucun entraînement n'est nécessaire.
"""

from dataclasses import dataclass

import numpy as np

from .runtime import MODELS_DIR, load_interpreter, load_labels, resize, to_rgb_array

DEFAULT_MODEL = MODELS_DIR / "bird" / "efficientdet_lite0.tflite"
DEFAULT_LABELS = MODELS_DIR / "bird" / "labelmap.txt"


@dataclass
class Detection:
    label: str
    score: float
    # Boîte en pixels de l'image d'origine : (x_min, y_min, x_max, y_max)
    box: tuple


class BirdDetector:
    def __init__(self, model_path=DEFAULT_MODEL, labels_path=DEFAULT_LABELS,
                 score_threshold=0.5, target_labels=("bird",), num_threads=4):
        """
        score_threshold : confiance minimale pour garder une détection (0 à 1).
        target_labels   : classes COCO à garder ; None pour toutes les garder
                          (utile pour vérifier que le modèle fonctionne).
        """
        self.score_threshold = score_threshold
        self.target_labels = set(target_labels) if target_labels else None
        self.labels = load_labels(labels_path)
        self.interpreter = load_interpreter(model_path, num_threads)

        input_details = self.interpreter.get_input_details()[0]
        self._input_index = input_details["index"]
        _, height, width, _ = input_details["shape"]
        self.input_size = (int(width), int(height))  # (320, 320)

        # Sorties du post-traitement TFLite (même ordre que l'exemple officiel
        # Raspberry Pi de TensorFlow) : boîtes, classes, scores, nombre.
        outputs = {d["name"]: d["index"] for d in self.interpreter.get_output_details()}
        self._boxes = outputs["StatefulPartitionedCall:3"]
        self._classes = outputs["StatefulPartitionedCall:2"]
        self._scores = outputs["StatefulPartitionedCall:1"]
        self._count = outputs["StatefulPartitionedCall:0"]

    def detect(self, image):
        """Retourne la liste des détections (Detection), triées par score décroissant.

        image : chemin, image PIL ou tableau numpy RGB (H, W, 3).
        """
        rgb = to_rgb_array(image)
        img_h, img_w = rgb.shape[:2]

        # Le modèle attend des pixels uint8 de 0 à 255, sans normalisation.
        model_input = resize(rgb, self.input_size)[np.newaxis, ...]
        self.interpreter.set_tensor(self._input_index, model_input)
        self.interpreter.invoke()

        boxes = self.interpreter.get_tensor(self._boxes)[0]
        classes = self.interpreter.get_tensor(self._classes)[0]
        scores = self.interpreter.get_tensor(self._scores)[0]
        count = int(self.interpreter.get_tensor(self._count)[0])

        detections = []
        for i in range(count):
            score = float(scores[i])
            if score < self.score_threshold:
                continue
            label = self.labels[int(classes[i])]
            if self.target_labels is not None and label not in self.target_labels:
                continue
            # Boîtes normalisées (0 à 1) au format [y_min, x_min, y_max, x_max]
            y_min, x_min, y_max, x_max = np.clip(boxes[i], 0.0, 1.0)
            box = (int(x_min * img_w), int(y_min * img_h), int(x_max * img_w), int(y_max * img_h))
            detections.append(Detection(label, score, box))

        detections.sort(key=lambda d: d.score, reverse=True)
        return detections

    def has_bird(self, image):
        """Raccourci : True si au moins un oiseau est détecté."""
        return any(d.label == "bird" for d in self.detect(image))

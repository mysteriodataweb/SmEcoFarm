"""SmEcoFarm : surveillance du champ (oiseaux, maladies) et de l'entrepôt
(conservation des tomates, incendie) sur un Raspberry Pi 4."""

from .vision import BirdDetector, Detection, DiseaseClassifier, FireDetector, FireResult, Prediction

__all__ = ["BirdDetector", "Detection", "DiseaseClassifier", "Prediction", "FireDetector", "FireResult"]

"""SmEcoFarm : détection d'oiseaux et de maladies des plantes sur Raspberry Pi."""

from .bird_detector import BirdDetector, Detection
from .disease_classifier import DiseaseClassifier, Prediction

__all__ = ["BirdDetector", "Detection", "DiseaseClassifier", "Prediction"]

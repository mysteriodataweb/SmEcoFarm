"""Vision : détection d'oiseaux, de maladies et de flammes."""

from .bird_detector import BirdDetector, Detection
from .disease_classifier import DiseaseClassifier, Prediction
from .fire_detector import FireDetector, FireResult

__all__ = ["BirdDetector", "Detection", "DiseaseClassifier", "Prediction", "FireDetector", "FireResult"]

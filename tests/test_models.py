"""Tests rapides des deux modèles : python -m pytest tests/"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from smecofarm import BirdDetector, DiseaseClassifier  # noqa: E402

BIRDS = ROOT / "test_images" / "birds"
TOMATO = ROOT / "test_images" / "tomato"


@pytest.fixture(scope="module")
def bird_detector():
    return BirdDetector()


@pytest.fixture(scope="module")
def disease_classifier():
    return DiseaseClassifier()


def test_bird_detected(bird_detector):
    detections = bird_detector.detect(BIRDS / "eagle.jpg")
    assert detections and detections[0].label == "bird"
    x1, y1, x2, y2 = detections[0].box
    assert 0 <= x1 < x2 and 0 <= y1 < y2


@pytest.mark.parametrize("name", ["dog.jpg", "horses.jpg", "person.jpg", "giraffe.jpg", "kite.jpg", "scream.jpg"])
def test_no_bird(bird_detector, name):
    assert not bird_detector.has_bird(BIRDS / name)


def test_bird_accepts_numpy_array(bird_detector):
    from PIL import Image
    array = np.asarray(Image.open(BIRDS / "eagle.jpg").convert("RGB"))
    assert bird_detector.has_bird(array)


def test_disease_only_tomato_classes(disease_classifier):
    p = disease_classifier.predict(next((TOMATO / "tomato_late_blight").iterdir()))
    assert p.key.startswith("tomato_")
    assert all(k.startswith("tomato_") for k, _ in p.top)
    assert 0.0 <= p.confidence <= 1.0


def test_disease_accuracy(disease_classifier):
    total = correct = 0
    for class_dir in TOMATO.iterdir():
        for path in class_dir.iterdir():
            total += 1
            correct += disease_classifier.predict(path).key == class_dir.name
    assert total == 100
    assert correct / total >= 0.8

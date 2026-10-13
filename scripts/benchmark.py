"""Mesurer la vitesse des modèles (à lancer sur le Raspberry Pi).

    python scripts/benchmark.py
    python scripts/benchmark.py --runs 50 --threads 4
"""

import argparse
import platform
import statistics
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smecofarm import BirdDetector, DiseaseClassifier  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def measure(fn, image, runs):
    fn(image)  # premier appel (préparation), non compté
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn(image)
        times.append((time.perf_counter() - t0) * 1000)
    return statistics.mean(times), min(times), max(times)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    print(f"Machine : {platform.machine()}  Python {platform.python_version()}  threads={args.threads}")
    bird_image = Image.open(ROOT / "test_images" / "birds" / "eagle.jpg").convert("RGB")
    leaf_image = Image.open(next((ROOT / "test_images" / "tomato" / "tomato_healthy").iterdir())).convert("RGB")

    for name, model, image in [
        ("Oiseaux  (EfficientDet-Lite0)", BirdDetector(num_threads=args.threads).detect, bird_image),
        ("Maladies (MobileNetV2)       ", DiseaseClassifier(num_threads=args.threads).predict, leaf_image),
    ]:
        mean, low, high = measure(model, image, args.runs)
        print(f"{name}  moyenne {mean:6.1f} ms  (min {low:.1f}, max {high:.1f})  ~{1000 / mean:.1f} images/s")


if __name__ == "__main__":
    main()

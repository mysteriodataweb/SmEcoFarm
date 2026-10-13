"""Mesurer la précision du classifieur de maladies sur un dossier d'images étiquetées.

Structure attendue : un sous-dossier par classe, nommé avec la clé du modèle
(ex. tomato_late_blight/, tomato_healthy/). Voir test_images/tomato/.

    python scripts/evaluate_disease.py                       # test_images/tomato
    python scripts/evaluate_disease.py --dir mes_photos --crop all
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smecofarm import DiseaseClassifier  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=str(ROOT / "test_images" / "tomato"))
    parser.add_argument("--crop", default="tomato", help="plante (tomato, ...) ou 'all' pour les 38 classes")
    args = parser.parse_args()

    classifier = DiseaseClassifier(crop=None if args.crop == "all" else args.crop)
    total = correct = uncertain = 0
    print(f"{'classe attendue':45s} {'correct':>8s}   erreurs fréquentes")
    for class_dir in sorted(p for p in Path(args.dir).iterdir() if p.is_dir()):
        expected = class_dir.name
        images = [p for p in sorted(class_dir.iterdir()) if p.suffix.lower() in IMAGE_EXTENSIONS]
        ok = 0
        mistakes = Counter()
        for path in images:
            p = classifier.predict(path)
            uncertain += p.uncertain
            if p.key == expected:
                ok += 1
            else:
                mistakes[p.key] += 1
        total += len(images)
        correct += ok
        errors = ", ".join(f"{k} x{n}" for k, n in mistakes.most_common(2))
        print(f"{expected:45s} {ok:3d}/{len(images):<4d}   {errors}")

    if total:
        print(f"\nPrécision : {correct}/{total} = {correct / total:.0%}"
              f"   (prédictions sous le seuil de confiance : {uncertain})")


if __name__ == "__main__":
    main()

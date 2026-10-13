"""Tester les modèles sur une image, un dossier d'images ou la caméra.

Exemples (depuis la racine du projet) :
    python scripts/test_models.py --image test_images/birds/eagle.jpg
    python scripts/test_models.py --dir test_images/birds --model bird
    python scripts/test_models.py --dir test_images/tomato/tomato_late_blight --model disease
    python scripts/test_models.py --camera            # webcam USB ou caméra Pi (nécessite OpenCV)

Les images annotées (boîtes des oiseaux) sont enregistrées dans le dossier output/.
"""

import argparse
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smecofarm import BirdDetector, DiseaseClassifier  # noqa: E402

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}


def annotate(image, detections):
    image = image.copy()
    draw = ImageDraw.Draw(image)
    for d in detections:
        draw.rectangle(d.box, outline=(255, 0, 0), width=3)
        draw.text((d.box[0] + 4, d.box[1] + 4), f"{d.label} {d.score:.0%}", fill=(255, 0, 0))
    return image


def analyse(image, name, bird_detector, disease_classifier, output_dir):
    """Analyse une image PIL RGB et affiche les résultats."""
    print(f"\n=== {name}")
    if bird_detector:
        t0 = time.perf_counter()
        detections = bird_detector.detect(image)
        ms = (time.perf_counter() - t0) * 1000
        if detections:
            for d in detections:
                print(f"  [oiseaux]  {d.label:10s} {d.score:5.0%}  boîte={d.box}")
        else:
            print("  [oiseaux]  aucun oiseau détecté")
        print(f"             ({ms:.0f} ms)")
        if output_dir and detections:
            output_dir.mkdir(parents=True, exist_ok=True)
            annotate(image, detections).save(output_dir / f"{Path(name).stem}_detections.jpg")

    if disease_classifier:
        t0 = time.perf_counter()
        p = disease_classifier.predict(image)
        ms = (time.perf_counter() - t0) * 1000
        status = "INCERTAIN" if p.uncertain else ("saine" if p.healthy else "MALADIE")
        print(f"  [maladies] {p.name}  {p.confidence:.0%}  -> {status}")
        others = ", ".join(f"{k} {c:.0%}" for k, c in p.top[1:])
        print(f"             autres : {others}   ({ms:.0f} ms)")


def iter_images(args):
    if args.image:
        yield Path(args.image)
    elif args.dir:
        for path in sorted(Path(args.dir).rglob("*")):
            if path.suffix.lower() in IMAGE_EXTENSIONS:
                yield path


def run_camera(args, bird_detector, disease_classifier):
    import cv2  # pip install opencv-python (ou sudo apt install python3-opencv)

    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        sys.exit("Impossible d'ouvrir la caméra")
    print("Appuyez sur Ctrl+C pour arrêter.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Image caméra non lue, nouvel essai...")
                time.sleep(0.5)
                continue
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))  # OpenCV = BGR
            analyse(image, time.strftime("camera_%H%M%S"), bird_detector, disease_classifier,
                    Path(args.output))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", help="chemin d'une image")
    source.add_argument("--dir", help="dossier d'images (parcouru récursivement)")
    source.add_argument("--camera", action="store_true", help="utiliser la caméra")
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--interval", type=float, default=1.0, help="secondes entre deux analyses caméra")
    parser.add_argument("--model", choices=["bird", "disease", "both"], default="both")
    parser.add_argument("--bird-threshold", type=float, default=0.5)
    parser.add_argument("--all-classes", action="store_true",
                        help="afficher toutes les classes COCO, pas seulement les oiseaux")
    parser.add_argument("--crop", default="tomato", help="plante filmée (tomato, potato, ...) ou 'all'")
    parser.add_argument("--output", default="output", help="dossier des images annotées")
    args = parser.parse_args()

    bird_detector = disease_classifier = None
    if args.model in ("bird", "both"):
        bird_detector = BirdDetector(score_threshold=args.bird_threshold,
                                     target_labels=None if args.all_classes else ("bird",))
    if args.model in ("disease", "both"):
        disease_classifier = DiseaseClassifier(crop=None if args.crop == "all" else args.crop)

    if args.camera:
        run_camera(args, bird_detector, disease_classifier)
        return

    paths = list(iter_images(args))
    if not paths:
        sys.exit("Aucune image trouvée")
    for path in paths:
        image = Image.open(path).convert("RGB")
        analyse(image, str(path), bird_detector, disease_classifier, Path(args.output))


if __name__ == "__main__":
    main()

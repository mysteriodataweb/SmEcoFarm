"""Enregistrement de l'historique dans des fichiers CSV (un par jour).

Ces fichiers s'ouvrent dans Excel / LibreOffice et servent à tracer les
courbes du rapport. Les photos d'événements sont enregistrées à côté.
"""

import csv
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

COLUMNS = [
    "date_heure", "temperature_c", "humidite_pct", "air_anormal", "ventilateur",
    "niveau_incendie", "oiseaux_detectes", "maladie", "confiance_maladie",
]


class DataLogger:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.photos = self.folder / "photos"
        self.photos.mkdir(parents=True, exist_ok=True)

    def log(self, row):
        path = self.folder / f"{datetime.now():%Y-%m-%d}.csv"
        new_file = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore", delimiter=";")
            if new_file:
                writer.writeheader()
            writer.writerow({"date_heure": datetime.now().isoformat(timespec="seconds"), **row})

    def save_photo(self, image, label):
        """Enregistre une image RGB numpy et retourne son chemin."""
        path = self.photos / f"{time.strftime('%Y%m%d_%H%M%S')}_{label}.jpg"
        Image.fromarray(image).save(path, quality=85)
        return path

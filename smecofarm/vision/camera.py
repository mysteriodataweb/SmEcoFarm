"""Lecture des webcams USB (OpenCV) et caméra simulée pour les tests."""

import itertools
import logging
import time
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


class UsbCamera:
    """Webcam USB lue avec OpenCV. Renvoie des images RGB (numpy)."""

    def __init__(self, source=0, width=640, height=480, name="caméra"):
        """
        source : index (0, 1, 2...) ou chemin stable, par exemple
                 /dev/v4l/by-id/usb-...-video-index0 (conseillé avec 2 webcams,
                 car les index peuvent changer au redémarrage).
        """
        import cv2  # sudo apt install python3-opencv
        self._cv2 = cv2
        self.source = source
        self.width = width
        self.height = height
        self.name = name
        self._cap = None
        self._open()

    def _open(self):
        cv2 = self._cv2
        if self._cap is not None:
            self._cap.release()
        self._cap = cv2.VideoCapture(self.source)
        # MJPG : réduit le débit USB, nécessaire pour 2 webcams sur le même Pi
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self._cap.isOpened():
            log.error("%s : impossible d'ouvrir la webcam %s", self.name, self.source)

    def read(self):
        """Retourne la dernière image RGB, ou None si la lecture échoue."""
        cv2 = self._cv2
        # On lit plusieurs fois pour vider le tampon et obtenir une image récente
        for _ in range(2):
            self._cap.grab()
        ok, frame = self._cap.retrieve()
        if not ok or frame is None:
            log.warning("%s : lecture impossible, réouverture de la webcam", self.name)
            time.sleep(0.5)
            self._open()
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # OpenCV fournit du BGR

    def close(self):
        if self._cap is not None:
            self._cap.release()


class ImageFolderCamera:
    """Caméra simulée : renvoie tour à tour les images d'un dossier."""

    def __init__(self, folder, name="caméra simulée"):
        paths = sorted(p for p in Path(folder).rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
        if not paths:
            raise FileNotFoundError(f"Aucune image dans {folder}")
        self.name = name
        self._paths = itertools.cycle(paths)
        self.current_path = None

    def read(self):
        self.current_path = next(self._paths)
        return np.asarray(Image.open(self.current_path).convert("RGB"))

    def close(self):
        pass


class SyntheticFireCamera:
    """Caméra simulée pour l'entrepôt : une pièce grise, avec une flamme
    qui scintille quand fire_active() renvoie True."""

    def __init__(self, fire_active, size=(320, 240), seed=0):
        self.name = "caméra entrepôt simulée"
        self._fire_active = fire_active
        self._width, self._height = size
        self._rng = np.random.default_rng(seed)

    def read(self):
        h, w = self._height, self._width
        frame = np.full((h, w, 3), 90, dtype=np.uint8)
        frame[int(h * 0.6):, :] = (70, 60, 50)  # sol
        frame[int(h * 0.45):int(h * 0.6), int(w * 0.1):int(w * 0.4)] = (150, 40, 30)  # caisse de tomates
        if self._fire_active():
            # Flamme : ellipse jaune-orange dont la taille et la position varient
            cx = w * 0.7 + self._rng.uniform(-4, 4)
            cy = h * 0.6
            rx = w * 0.06 * self._rng.uniform(0.7, 1.3)
            ry = h * 0.18 * self._rng.uniform(0.6, 1.4)
            yy, xx = np.mgrid[0:h, 0:w]
            inside = ((xx - cx) / rx) ** 2 + ((yy - (cy - ry)) / ry) ** 2 <= 1
            frame[inside] = (255, int(self._rng.uniform(140, 210)), 40)
        return frame

    def close(self):
        pass

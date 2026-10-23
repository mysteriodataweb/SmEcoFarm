"""Détection de flammes par la couleur et le scintillement (sans modèle d'IA).

Principe :
  1. couleur : on repère les pixels rouge-orangé lumineux. Méthode par défaut
     « hsv » = les plages de couleurs du code d'origine du projet (rouge et
     orange en HSV, avec nettoyage du masque) ; méthode « rgb » = règle
     classique R > 180, R >= G > B ;
  2. scintillement : une vraie flamme bouge. On mesure la part de l'image dont
     la couleur « flamme » change d'une image à l'autre. Des objets rouges
     immobiles, comme des TOMATES MÛRES (même couleur qu'une flamme !),
     ne changent pas et ne déclenchent donc rien ;
  3. confirmation : il faut plusieurs images consécutives.

Limites : une personne en vêtement rouge qui bouge, une lampe orange qui
clignote peuvent tromper la caméra. C'est pour cela que l'alerte incendie
croise la caméra avec les capteurs (voir regles/incendie.py).
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .runtime import to_rgb_array

# Taille de travail : petite pour être rapide sur le Raspberry Pi
WORK_SIZE = (160, 120)

# Plages HSV du code d'origine (échelle OpenCV : H 0–179, S et V 0–255)
HSV_RANGES = [
    ((5, 100, 150), (35, 255, 255)),    # orange
    ((0, 120, 150), (5, 255, 255)),     # rouge (début du cercle des teintes)
    ((170, 120, 150), (179, 255, 255)),  # rouge (fin du cercle des teintes)
]


@dataclass
class FireResult:
    flame: bool        # flamme vue sur cette image
    confirmed: bool    # flamme vue sur assez d'images consécutives
    ratio: float       # part de l'image ayant une couleur de flamme
    flicker: float     # part de l'image dont la couleur « flamme » a changé
    box: tuple = None  # zone colorée en pixels de l'image d'origine


def _shift_and(mask):
    """Érosion 3x3 : un pixel reste vrai si ses 8 voisins le sont aussi."""
    padded = np.pad(mask, 1, constant_values=False)
    out = np.ones_like(mask)
    h, w = mask.shape
    for dy in range(3):
        for dx in range(3):
            out &= padded[dy:dy + h, dx:dx + w]
    return out


def _shift_or(mask):
    """Dilatation 3x3 : un pixel devient vrai si l'un de ses voisins l'est."""
    padded = np.pad(mask, 1, constant_values=False)
    out = np.zeros_like(mask)
    h, w = mask.shape
    for dy in range(3):
        for dx in range(3):
            out |= padded[dy:dy + h, dx:dx + w]
    return out


class FireDetector:
    def __init__(self, method="hsv", min_ratio=0.02, consecutive_frames=3, require_flicker=True,
                 min_flicker=0.003):
        """
        method             : "hsv" (plages du code d'origine) ou "rgb".
        min_ratio          : part minimale de l'image de couleur flamme (2 %, comme le code d'origine).
        consecutive_frames : nombre d'images de suite avant de confirmer.
        require_flicker    : exiger que la zone colorée bouge.
        min_flicker        : part minimale de l'image qui doit changer (0,3 %).
        """
        if method not in ("hsv", "rgb"):
            raise ValueError("method doit valoir 'hsv' ou 'rgb'")
        self.method = method
        self.min_ratio = min_ratio
        self.consecutive_frames = consecutive_frames
        self.require_flicker = require_flicker
        self.min_flicker = min_flicker
        self._previous_mask = None
        self._count = 0

    def flame_mask(self, rgb_small):
        if self.method == "rgb":
            rgb = rgb_small.astype(np.int16)
            r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
            saturation = (rgb.max(axis=2) - rgb.min(axis=2)) / np.maximum(rgb.max(axis=2), 1)
            return (r > 180) & (r >= g) & (g > b) & (saturation > 0.25)

        hsv = np.asarray(Image.fromarray(rgb_small).convert("HSV")).astype(np.int16)
        hue = hsv[..., 0] * 180 // 256  # PIL : 0–255 -> OpenCV : 0–179
        sat, val = hsv[..., 1], hsv[..., 2]
        mask = np.zeros(hue.shape, dtype=bool)
        for (h1, s1, v1), (h2, s2, v2) in HSV_RANGES:
            mask |= (hue >= h1) & (hue <= h2) & (sat >= s1) & (sat <= s2) & (val >= v1) & (val <= v2)
        # Nettoyage (ouverture morphologique 3x3, comme cv2.MORPH_OPEN) : enlève les pixels isolés
        return _shift_or(_shift_and(mask))

    def analyse(self, image):
        rgb = to_rgb_array(image)
        height, width = rgb.shape[:2]
        small = np.asarray(Image.fromarray(rgb).resize(WORK_SIZE, Image.BILINEAR))
        mask = self.flame_mask(small)
        ratio = float(mask.mean())

        flicker = 0.0
        if self._previous_mask is not None:
            flicker = float((mask ^ self._previous_mask).mean())
        self._previous_mask = mask

        flame = ratio >= self.min_ratio and (not self.require_flicker or flicker >= self.min_flicker)
        self._count = self._count + 1 if flame else 0

        box = None
        if ratio >= self.min_ratio:
            ys, xs = np.nonzero(mask)
            sx, sy = width / WORK_SIZE[0], height / WORK_SIZE[1]
            box = (int(xs.min() * sx), int(ys.min() * sy), int((xs.max() + 1) * sx), int((ys.max() + 1) * sy))

        return FireResult(flame, self._count >= self.consecutive_frames, ratio, flicker, box)

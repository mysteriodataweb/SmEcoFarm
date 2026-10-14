"""Détection de flammes par la couleur et le scintillement (sans modèle d'IA).

Principe (règle classique de détection de feu dans l'espace RGB) :
  1. un pixel « flamme » est rouge-orangé et lumineux : R > seuil, R >= G > B,
     et suffisamment saturé ;
  2. une vraie flamme bouge : la zone détectée change d'une image à l'autre
     (scintillement), contrairement à un objet orange immobile ;
  3. la flamme doit être vue sur plusieurs images consécutives pour être confirmée.

Limites : le soleil, une lampe orange ou un vêtement rouge qui bouge peuvent
tromper le détecteur. C'est pour cela que l'alerte incendie croise la caméra
avec les capteurs (voir regles/incendie.py).
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image

from .runtime import to_rgb_array

# Taille de travail : petite pour être rapide sur le Raspberry Pi
WORK_SIZE = (160, 120)


@dataclass
class FireResult:
    flame: bool        # flamme vue sur cette image
    confirmed: bool    # flamme vue sur assez d'images consécutives
    ratio: float       # part de l'image couverte par la zone « flamme »
    flicker: float     # part de la zone qui a changé depuis l'image précédente
    box: tuple = None  # zone de la flamme en pixels de l'image d'origine


class FireDetector:
    def __init__(self, min_ratio=0.005, consecutive_frames=3, require_flicker=True,
                 min_flicker=0.15, red_threshold=180, saturation_threshold=0.25):
        """
        min_ratio          : part minimale de l'image couverte par la flamme (0,5 %).
        consecutive_frames : nombre d'images de suite avant de confirmer.
        require_flicker    : exiger que la zone bouge (évite les objets orange fixes).
        min_flicker        : part minimale de la zone qui doit changer entre 2 images.
        """
        self.min_ratio = min_ratio
        self.consecutive_frames = consecutive_frames
        self.require_flicker = require_flicker
        self.min_flicker = min_flicker
        self.red_threshold = red_threshold
        self.saturation_threshold = saturation_threshold
        self._previous_mask = None
        self._count = 0

    def flame_mask(self, rgb_small):
        rgb = rgb_small.astype(np.int16)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        max_c = rgb.max(axis=2)
        min_c = rgb.min(axis=2)
        saturation = (max_c - min_c) / np.maximum(max_c, 1)
        return (r > self.red_threshold) & (r >= g) & (g > b) & (saturation > self.saturation_threshold)

    def analyse(self, image):
        rgb = to_rgb_array(image)
        height, width = rgb.shape[:2]
        small = np.asarray(Image.fromarray(rgb).resize(WORK_SIZE, Image.BILINEAR))
        mask = self.flame_mask(small)
        ratio = float(mask.mean())

        flicker = 0.0
        if self._previous_mask is not None:
            union = mask | self._previous_mask
            if union.any():
                flicker = float((mask ^ self._previous_mask).sum() / union.sum())
        self._previous_mask = mask

        flame = ratio >= self.min_ratio and (not self.require_flicker or flicker >= self.min_flicker)
        self._count = self._count + 1 if flame else 0

        box = None
        if ratio >= self.min_ratio:
            ys, xs = np.nonzero(mask)
            sx, sy = width / WORK_SIZE[0], height / WORK_SIZE[1]
            box = (int(xs.min() * sx), int(ys.min() * sy), int((xs.max() + 1) * sx), int((ys.max() + 1) * sy))

        return FireResult(flame, self._count >= self.consecutive_frames, ratio, flicker, box)

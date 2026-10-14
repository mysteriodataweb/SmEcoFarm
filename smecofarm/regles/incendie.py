"""Détection du risque d'incendie par croisement de plusieurs indices.

Indices surveillés :
  - flamme      : la caméra voit une flamme confirmée
  - temperature : montée rapide (ex. +5 °C en 60 s, comme un détecteur
                  thermovélocimétrique) ou température très élevée
  - fumee       : le MQ-135 signale un air anormal

Niveaux :
  0 NORMAL     aucun indice
  1 VIGILANCE  un seul indice (peut être une fausse alerte)
  2 ALERTE     au moins deux indices -> e-mail, sirène, ventilateur coupé

L'alerte est mémorisée (verrouillée) jusqu'à un réarmement manuel, comme
sur une vraie centrale incendie.
"""

from collections import deque
from dataclasses import dataclass, field

NORMAL, VIGILANCE, ALERTE = 0, 1, 2
LEVEL_NAMES = {NORMAL: "Normal", VIGILANCE: "Vigilance", ALERTE: "ALERTE INCENDIE"}

DEFAULTS = {
    "hausse_temp_c": 5.0,
    "fenetre_hausse_s": 60.0,
    "temp_max_c": 45.0,
}


@dataclass
class FireStatus:
    level: int
    indicators: list = field(default_factory=list)
    new_alarm: bool = False  # True uniquement au moment où l'alerte se déclenche

    @property
    def name(self):
        return LEVEL_NAMES[self.level]


class FireRules:
    def __init__(self, config=None):
        self.cfg = {**DEFAULTS, **(config or {})}
        self._history = deque()  # (instant, température)
        self.latched = False
        self.latched_indicators = []

    def _temperature_indicator(self, now, temperature):
        if temperature is None:
            return False
        window = self.cfg["fenetre_hausse_s"]
        self._history.append((now, temperature))
        while self._history and now - self._history[0][0] > window:
            self._history.popleft()
        lowest = min(t for _, t in self._history)
        return temperature >= self.cfg["temp_max_c"] or temperature - lowest >= self.cfg["hausse_temp_c"]

    def update(self, now, temperature, air_bad, flame_confirmed):
        """now : instant en secondes (time.monotonic())."""
        indicators = []
        if flame_confirmed:
            indicators.append("flamme")
        if self._temperature_indicator(now, temperature):
            indicators.append("temperature")
        if air_bad:
            indicators.append("fumee")

        new_alarm = False
        if len(indicators) >= 2 and not self.latched:
            self.latched = True
            self.latched_indicators = list(indicators)
            new_alarm = True

        if self.latched:
            merged = list(dict.fromkeys(self.latched_indicators + indicators))
            return FireStatus(ALERTE, merged, new_alarm)
        return FireStatus(VIGILANCE if indicators else NORMAL, indicators)

    def reset(self):
        """Réarmement manuel (bouton Blynk)."""
        self.latched = False
        self.latched_indicators = []
        self._history.clear()

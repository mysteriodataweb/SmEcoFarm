"""Capteurs simulés : permettent de faire tourner le programme sur PC
(ou sur le Pi sans capteur branché) avec un scénario choisi.

Scénarios :
  normal   : entrepôt à 20–21 °C, air normal
  chaleur  : la température monte jusqu'à 32 °C en 2 minutes (le ventilateur doit démarrer)
  incendie : normal pendant 30 s, puis flamme, montée de 8 °C/min et fumée
"""

import math

from .dht11 import ClimateReading

SCENARIOS = ("normal", "chaleur", "incendie")
FIRE_START_S = 30


class Scenario:
    def __init__(self, name, clock):
        if name not in SCENARIOS:
            raise ValueError(f"Scénario inconnu : {name} (choix : {', '.join(SCENARIOS)})")
        self.name = name
        self._clock = clock
        self._start = clock()

    @property
    def elapsed(self):
        return self._clock() - self._start

    def fire_active(self):
        return self.name == "incendie" and self.elapsed >= FIRE_START_S

    def temperature(self):
        t = self.elapsed
        base = 20.5 + 0.5 * math.sin(t / 20)
        if self.name == "chaleur":
            return base + min(t / 120, 1.0) * 11.5
        if self.fire_active():
            return min(base + (t - FIRE_START_S) / 60 * 8, 50)
        return base

    def humidity(self):
        return 70 - 0.3 * max(self.temperature() - 21, 0)


class SimulatedDht11:
    def __init__(self, scenario):
        self._scenario = scenario

    def read(self):
        # Le DHT11 donne des valeurs entières
        return ClimateReading(float(round(self._scenario.temperature())),
                              float(round(self._scenario.humidity())), True)

    def close(self):
        pass


class SimulatedMq135:
    warming_up = False

    def __init__(self, scenario):
        self._scenario = scenario

    def air_bad(self):
        # La fumée atteint le capteur 10 s après le début du feu
        return self._scenario.fire_active() and self._scenario.elapsed >= 40

    def close(self):
        pass

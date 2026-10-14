"""Capteur de température et d'humidité DHT11.

Caractéristiques du DHT11 : 0–50 °C (±2 °C), 20–80 % d'humidité (±5 %),
une mesure toutes les 2 secondes au maximum. Les lectures échouent souvent
(c'est normal avec ce capteur) : on garde la dernière bonne valeur et on ne
signale une panne que si aucune lecture n'a réussi depuis un moment.
"""

import logging
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ClimateReading:
    temperature: float = None  # °C
    humidity: float = None     # %
    ok: bool = False           # False si le capteur ne répond plus


class Dht11Sensor:
    def __init__(self, gpio=4, max_age_s=60):
        """gpio : numéro BCM de la broche DATA (GPIO4 = broche physique 7)."""
        import adafruit_dht  # pip install adafruit-circuitpython-dht
        import board
        self._device = adafruit_dht.DHT11(getattr(board, f"D{gpio}"), use_pulseio=False)
        self.max_age_s = max_age_s
        self._last = ClimateReading()
        self._last_ok_time = None

    def read(self):
        try:
            temperature = self._device.temperature
            humidity = self._device.humidity
            if temperature is not None and humidity is not None:
                self._last = ClimateReading(float(temperature), float(humidity), True)
                self._last_ok_time = time.monotonic()
        except RuntimeError as exc:
            # Erreur de lecture fréquente sur les DHT : on réessaiera au prochain tour
            log.debug("DHT11 : lecture ratée (%s)", exc)
        except Exception:
            log.exception("DHT11 : erreur inattendue")

        if self._last_ok_time is None or time.monotonic() - self._last_ok_time > self.max_age_s:
            return ClimateReading(self._last.temperature, self._last.humidity, False)
        return self._last

    def close(self):
        self._device.exit()

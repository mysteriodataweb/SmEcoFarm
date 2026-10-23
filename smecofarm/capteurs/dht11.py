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
    """Lit le DHT11 avec la bibliothèque disponible :

      - Adafruit_DHT (ancienne bibliothèque, celle du code d'origine) ;
      - adafruit_dht (bibliothèque CircuitPython, plus récente).
    """

    def __init__(self, gpio=17, max_age_s=60):
        """gpio : numéro BCM de la broche DATA (GPIO17 = broche physique 11)."""
        self.max_age_s = max_age_s
        self._last = ClimateReading()
        self._last_ok_time = None
        self._legacy = None
        self._device = None
        try:
            import Adafruit_DHT
            self._legacy = Adafruit_DHT
            self._gpio = gpio
            log.info("DHT11 : bibliothèque Adafruit_DHT, GPIO%d", gpio)
        except ImportError:
            import adafruit_dht  # pip install adafruit-circuitpython-dht
            import board
            self._device = adafruit_dht.DHT11(getattr(board, f"D{gpio}"), use_pulseio=False)
            log.info("DHT11 : bibliothèque adafruit_dht, GPIO%d", gpio)

    def _read_raw(self):
        if self._legacy is not None:
            # read() et non read_retry() : read_retry peut bloquer jusqu'à 30 s
            humidity, temperature = self._legacy.read(self._legacy.DHT11, self._gpio)
            return temperature, humidity
        return self._device.temperature, self._device.humidity

    def read(self):
        try:
            temperature, humidity = self._read_raw()
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
        if self._device is not None:
            self._device.exit()

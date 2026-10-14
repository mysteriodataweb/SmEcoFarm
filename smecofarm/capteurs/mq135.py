"""Capteur de gaz MQ-135, lu par sa sortie numérique DO.

Sans convertisseur analogique (ADS1115), le Raspberry Pi ne peut lire que la
sortie DO du module : elle bascule quand la concentration de gaz (fumée, CO₂,
alcool, ammoniac...) dépasse un seuil réglé avec le potentiomètre bleu du module.
On obtient donc une information « air normal / air anormal », pas une valeur en ppm.

⚠️ Le module est alimenté en 5 V et sa sortie DO peut monter à 5 V : il faut un
pont diviseur (voir docs/CABLAGE.md) avant l'entrée GPIO du Pi (3,3 V maximum).

Le capteur chauffe : ses mesures ne sont pas fiables pendant les premières
minutes (et pendant 24 h lors de la toute première utilisation).
"""

import time


class Mq135Digital:
    def __init__(self, gpio=17, active_low=True, preheat_s=180):
        """
        active_low : True si la sortie DO passe à 0 quand du gaz est détecté
                     (cas des modules courants : la LED « DO » s'allume alors).
        preheat_s  : durée de préchauffage pendant laquelle on ignore le capteur.
        """
        from gpiozero import DigitalInputDevice
        self._input = DigitalInputDevice(gpio, pull_up=None, active_state=not active_low)
        self._start = time.monotonic()
        self.preheat_s = preheat_s

    @property
    def warming_up(self):
        return time.monotonic() - self._start < self.preheat_s

    def air_bad(self):
        """True si air anormal, False si normal, None pendant le préchauffage."""
        if self.warming_up:
            return None
        return bool(self._input.is_active)

    def close(self):
        self._input.close()

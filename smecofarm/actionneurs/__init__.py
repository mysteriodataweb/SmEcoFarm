"""Actionneurs : ventilateur (via module relais) et buzzer actif.

Chaque actionneur existe en version réelle (gpiozero) et simulée (affichage).
"""

import logging
import random

log = logging.getLogger(__name__)


class Fan:
    """Mini ventilateur 5 V commandé par un module relais."""

    def __init__(self, gpio=27, active_low=True, simulated=False):
        """active_low : True pour les modules relais qui collent quand IN = 0 (le plus courant)."""
        self.is_on = False
        self._relay = None
        if not simulated:
            from gpiozero import DigitalOutputDevice
            self._relay = DigitalOutputDevice(gpio, active_high=not active_low, initial_value=False)

    def set(self, on):
        on = bool(on)
        if on == self.is_on:
            return
        self.is_on = on
        if self._relay is not None:
            self._relay.value = on
        log.info("Ventilateur %s", "EN MARCHE" if on else "ARRÊTÉ")

    def close(self):
        self.set(False)
        if self._relay is not None:
            self._relay.close()


class Buzzer:
    """Buzzer actif partagé : chasse aux oiseaux et sirène incendie.

    La sirène incendie est prioritaire : tant qu'elle sonne, les bips
    « oiseau » sont ignorés.
    """

    def __init__(self, gpio=22, simulated=False):
        self.siren_on = False
        self._buzzer = None
        if not simulated:
            from gpiozero import Buzzer as GpioBuzzer
            self._buzzer = GpioBuzzer(gpio)

    def bird_alert(self):
        """Série de bips au rythme aléatoire, pour limiter l'accoutumance des oiseaux."""
        if self.siren_on:
            return
        on_time = random.uniform(0.08, 0.4)
        off_time = random.uniform(0.05, 0.3)
        count = random.randint(4, 10)
        log.info("Buzzer : chasse oiseaux (%d bips)", count)
        if self._buzzer is not None:
            self._buzzer.beep(on_time=on_time, off_time=off_time, n=count, background=True)

    def siren(self, on):
        """Sirène incendie continue (bips de 0,5 s) jusqu'à l'arrêt."""
        if on == self.siren_on:
            return
        self.siren_on = on
        log.warning("Buzzer : sirène incendie %s", "ACTIVÉE" if on else "arrêtée")
        if self._buzzer is not None:
            if on:
                self._buzzer.beep(on_time=0.5, off_time=0.5, n=None, background=True)
            else:
                self._buzzer.off()

    def close(self):
        if self._buzzer is not None:
            self._buzzer.off()
            self._buzzer.close()

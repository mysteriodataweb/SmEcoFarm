"""Actionneurs : ventilateur (relais), buzzer actif, LED et porte (servo).

Chaque actionneur existe en version réelle et simulée (affichage seulement).
"""

import logging
import random
import threading
import time

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
    """Buzzer actif partagé, avec des sons différents et un ordre de priorité :

      1. sirène incendie (bips de 0,5 s jusqu'au réarmement) ;
      2. carte RFID refusée (son continu de 2 s) ;
      3. chasse aux oiseaux (bips au rythme aléatoire).
    """

    def __init__(self, gpio=23, simulated=False, clock=time.monotonic):
        self.siren_on = False
        self._buzzer = None
        self._clock = clock
        self._refused_until = 0.0
        if not simulated:
            from gpiozero import Buzzer as GpioBuzzer
            self._buzzer = GpioBuzzer(gpio)

    def refused_alert(self, duration_s=2.0):
        """Son continu (comme dans le code d'origine) quand une carte est refusée."""
        if self.siren_on:
            return
        self._refused_until = self._clock() + duration_s
        log.info("Buzzer : carte refusée (%.0f s)", duration_s)
        if self._buzzer is not None:
            self._buzzer.beep(on_time=duration_s, off_time=0.1, n=1, background=True)

    def bird_alert(self):
        """Série de bips au rythme aléatoire, pour limiter l'accoutumance des oiseaux."""
        if self.siren_on or self._clock() < self._refused_until:
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


class Led:
    """LED témoin (allumée si température haute ou porte ouverte)."""

    def __init__(self, gpio=22, simulated=False):
        self.is_on = False
        self._led = None
        if not simulated:
            from gpiozero import LED
            self._led = LED(gpio)

    def set(self, on):
        on = bool(on)
        if on == self.is_on:
            return
        self.is_on = on
        if self._led is not None:
            self._led.value = on
        log.info("LED %s", "allumée" if on else "éteinte")

    def close(self):
        if self._led is not None:
            self._led.off()
            self._led.close()


class Door:
    """Porte motorisée par un servo (même commande que le code d'origine :
    signal 50 Hz, rapport cyclique = 2,5 + angle / 18, puis signal coupé
    pour éviter que le servo tremble).

    Le mouvement prend 0,5 s : il est fait en arrière-plan pour ne pas
    bloquer le reste du programme.
    """

    def __init__(self, gpio=26, closed_angle=0, open_angle=90, simulated=False):
        self.closed_angle = closed_angle
        self.open_angle = open_angle
        self.is_open = False
        self._pwm = None
        self._lock = threading.Lock()
        if not simulated:
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(gpio, GPIO.OUT)
            self._pwm = GPIO.PWM(gpio, 50)
            self._pwm.start(0)
        self._move(closed_angle, background=False)

    def _turn(self, angle):
        with self._lock:
            if self._pwm is None:
                return
            self._pwm.ChangeDutyCycle(2.5 + angle / 18.0)
            time.sleep(0.5)
            self._pwm.ChangeDutyCycle(0)

    def _move(self, angle, background=True):
        if background:
            threading.Thread(target=self._turn, args=(angle,), name="servo", daemon=True).start()
        else:
            self._turn(angle)

    def open(self):
        if self.is_open:
            return
        self.is_open = True
        log.info("Ouverture de la porte")
        self._move(self.open_angle)

    def close_door(self):
        if not self.is_open:
            return
        self.is_open = False
        log.info("Fermeture de la porte")
        self._move(self.closed_angle)

    def close(self):
        """Arrêt du programme : on referme la porte et on libère le GPIO."""
        if self.is_open:
            self.is_open = False
            self._move(self.closed_angle, background=False)
        if self._pwm is not None:
            self._pwm.stop()

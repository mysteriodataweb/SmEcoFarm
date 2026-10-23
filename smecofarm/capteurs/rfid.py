"""Lecteur de badges RFID RC522 (bus SPI) et lecteur simulé.

La lecture d'un badge bloque le programme jusqu'à ce qu'une carte soit
présentée : elle se fait donc dans un fil d'exécution séparé, qui dépose
les cartes lues dans une file d'attente. Le programme principal vient
ensuite les chercher avec poll().
"""

import logging
import queue
import threading
import time

log = logging.getLogger(__name__)


class RfidReader:
    def __init__(self, debounce_s=3.0):
        """
        debounce_s : une même carte n'est traitée qu'une fois pendant ce délai
                     (une carte posée sur le lecteur est lue en boucle).
        """
        import RPi.GPIO as GPIO
        from mfrc522 import SimpleMFRC522  # pip install mfrc522 (SPI à activer)

        # Comme dans le code d'origine : mode BCM choisi avant de créer le lecteur
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        self._reader = SimpleMFRC522()
        self.debounce_s = debounce_s
        self._cards = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="rfid", daemon=True)
        self._thread.start()
        log.info("Lecteur RFID prêt : approchez une carte")

    def _run(self):
        last_card, last_time = None, 0.0
        while not self._stop.is_set():
            try:
                card_id = self._reader.read_id()
                now = time.monotonic()
                if card_id == last_card and now - last_time < self.debounce_s:
                    time.sleep(0.2)
                    continue
                last_card, last_time = card_id, now
                self._cards.put(int(card_id))
            except Exception as exc:
                log.warning("Erreur RFID : %r", exc)
                time.sleep(2)

    def poll(self):
        """Retourne la prochaine carte lue (numéro), ou None."""
        try:
            return self._cards.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self._stop.set()


class SimulatedRfid:
    """Lecteur simulé : présente des cartes à des instants donnés.

    events : liste de (secondes après le démarrage, numéro de carte).
    """

    def __init__(self, events, clock):
        self._events = sorted(events)
        self._clock = clock
        self._start = clock()

    def poll(self):
        if self._events and self._clock() - self._start >= self._events[0][0]:
            return self._events.pop(0)[1]
        return None

    def close(self):
        pass

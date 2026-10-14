"""Communication avec Blynk IoT via son API HTTP.

Pourquoi l'API HTTP ? Elle est officielle, simple et ne demande aucune
bibliothèque : de simples requêtes web suffisent.

Les échanges se font dans un fil d'exécution séparé (thread) pour que le
programme principal ne soit jamais bloqué par un problème de réseau.
Seules les valeurs qui ont changé sont envoyées (le plan gratuit limite
le nombre de messages).
"""

import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)


class BlynkClient:
    def __init__(self, token, server="blynk.cloud", interval_s=5.0, control_pins=(), resend_every_s=300):
        """
        token        : « Auth Token » du device Blynk (dans .env : BLYNK_TOKEN).
        server       : serveur de votre compte (ex. blynk.cloud, fra1.blynk.cloud, ny3.blynk.cloud).
        control_pins : pins virtuelles lues depuis l'application (boutons, interrupteurs).
        """
        self.base_url = f"https://{server}/external/api"
        self.token = token
        self.interval_s = interval_s
        self.control_pins = list(control_pins)
        self.resend_every_s = resend_every_s
        self.controls = {}       # dernières valeurs lues : {"V4": "1", ...}
        self.connected = False
        self._state = {}
        self._sent = {}
        self._last_full_send = 0.0
        self._events = queue.Queue()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="blynk", daemon=True)
        self._thread.start()

    # --- appelé par le programme principal -------------------------------
    def publish(self, values):
        """Met à jour les valeurs à afficher : {"V5": 23.0, "V2": "Tomate - saine"}."""
        with self._lock:
            self._state.update(values)

    def event(self, code, description):
        """Déclenche un événement Blynk (notification sur le téléphone).

        L'événement doit exister dans le template Blynk avec ce code.
        """
        self._events.put((code, description[:300]))

    def control(self, pin, default=None):
        return self.controls.get(pin, default)

    def write_now(self, pin, value):
        """Écrit une valeur tout de suite (ex. remettre un bouton à 0)."""
        with self._lock:
            self._state[pin] = value
            self._sent.pop(pin, None)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=10)

    # --- fil d'exécution réseau ------------------------------------------
    def _request(self, endpoint, params):
        query = urllib.parse.urlencode([("token", self.token)] + params, safe="")
        url = f"{self.base_url}/{endpoint}?{query}"
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read().decode("utf-8")

    def _sync(self):
        now = time.monotonic()
        with self._lock:
            full = now - self._last_full_send > self.resend_every_s
            changed = {pin: value for pin, value in self._state.items() if full or self._sent.get(pin) != value}
        if changed:
            try:
                self._request("batch/update", [(pin, _format(value)) for pin, value in changed.items()])
            except urllib.error.HTTPError as exc:
                # Une valeur refusée (ex. texte envoyé vers un datastream numérique)
                # fait échouer tout l'envoi groupé : on envoie alors pin par pin.
                log.debug("Blynk : envoi groupé refusé (%s), envoi pin par pin", exc)
                for pin, value in list(changed.items()):
                    try:
                        self._request("update", [(pin, _format(value))])
                    except urllib.error.HTTPError as pin_exc:
                        log.warning("Blynk refuse %s=%r (%s) : vérifiez le type du datastream", pin, value, pin_exc)
            with self._lock:
                self._sent.update(changed)
            if full:
                self._last_full_send = now

        while not self._events.empty():
            code, description = self._events.get_nowait()
            self._request("logEvent", [("code", code), ("description", description)])
            log.info("Blynk : événement '%s' envoyé", code)

        if self.control_pins:
            # GET /get?token=...&V4&V9 -> {"V4": 1, "V9": 0} (ou une seule valeur)
            query = urllib.parse.urlencode([("token", self.token)])
            url = f"{self.base_url}/get?{query}&" + "&".join(self.control_pins)
            with urllib.request.urlopen(url, timeout=5) as response:
                text = response.read().decode("utf-8")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = text
            if isinstance(data, dict):
                self.controls.update({k: str(v) for k, v in data.items()})
            elif len(self.control_pins) == 1:
                self.controls[self.control_pins[0]] = str(data)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._sync()
                if not self.connected:
                    log.info("Blynk : connecté")
                self.connected = True
            except Exception as exc:
                if self.connected:
                    log.warning("Blynk : connexion perdue (%s)", exc)
                else:
                    log.debug("Blynk : échec (%s)", exc)
                self.connected = False
            self._stop.wait(self.interval_s)


def _format(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


class NullBlynk:
    """Remplace Blynk quand il n'est pas configuré : n'envoie rien."""

    connected = False
    controls = {}

    def publish(self, values):
        pass

    def event(self, code, description):
        log.info("[Blynk désactivé] événement %s : %s", code, description)

    def control(self, pin, default=None):
        return default

    def write_now(self, pin, value):
        pass

    def close(self):
        pass

"""Station Accès : contrôle de la porte de l'entrepôt par badge RFID.

- carte autorisée : porte ouverte pendant quelques secondes ;
- carte refusée   : buzzer pendant 2 s et notification Blynk ;
- bouton Blynk    : ouverture à distance ;
- incendie        : porte ouverte et maintenue ouverte pour l'évacuation,
                    jusqu'au réarmement de l'alarme.
Chaque passage est enregistré dans le journal des accès (CSV).
"""

import logging

log = logging.getLogger(__name__)

DEFAULTS = {
    "cartes_autorisees": {},
    "duree_ouverture_s": 4.0,
    "duree_alarme_refus_s": 2.0,
    "duree_message_s": 10.0,
}


class AccessStation:
    def __init__(self, config, reader, door, buzzer, blynk, logger, pins):
        cfg = {**DEFAULTS, **(config or {})}
        self.cfg = cfg
        # Numéros de carte autorisés -> nom (les clés peuvent être écrites en texte dans config.yaml)
        self.authorized = {int(uid): (name or "") for uid, name in (cfg["cartes_autorisees"] or {}).items()}
        self.reader = reader
        self.door = door
        self.buzzer = buzzer
        self.blynk = blynk
        self.logger = logger
        self.pins = pins
        self.evacuation = False
        self.last_card = None
        self.message = None
        self._message_until = 0.0
        self._close_at = None
        self._last_remote_value = None

    def tick(self, now):
        card = self.reader.poll()
        if card is not None:
            self._handle_card(now, card)

        self._handle_remote_open(now)

        if self._close_at is not None and now >= self._close_at and not self.evacuation:
            self._close_at = None
            self.door.close_door()

        if self.message and now >= self._message_until:
            self.message = None

    def _set_message(self, now, text):
        self.message = text
        self._message_until = now + self.cfg["duree_message_s"]

    def _open_for(self, now, seconds):
        self.door.open()
        self._close_at = now + seconds

    def _handle_card(self, now, card):
        self.last_card = card
        if card in self.authorized:
            name = self.authorized[card]
            log.info("Carte autorisée : %s%s", card, f" ({name})" if name else "")
            self._set_message(now, "Accès autorisé" + (f" : {name}" if name else ""))
            self._open_for(now, self.cfg["duree_ouverture_s"])
            self.logger.log_access(card, True, name)
        else:
            log.warning("Carte refusée : %s", card)
            self._set_message(now, "Carte non reconnue")
            self.buzzer.refused_alert(self.cfg["duree_alarme_refus_s"])
            self.blynk.event("acces_refuse", f"Carte non reconnue : {card}")
            self.logger.log_access(card, False, "")

    def _handle_remote_open(self, now):
        """Bouton Blynk « ouvrir la porte » : agit seulement quand il passe à 1."""
        pin = self.pins.get("ouvrir_porte")
        value = self.blynk.control(pin, "0")
        if value == "1" and self._last_remote_value != "1":
            log.info("Ouverture de la porte depuis Blynk")
            self._set_message(now, "Porte ouverte à distance (Blynk)")
            self._open_for(now, self.cfg["duree_ouverture_s"])
            self.logger.log_access("blynk", True, "ouverture à distance")
            self.blynk.write_now(pin, 0)
        self._last_remote_value = value

    def set_evacuation(self, now, active):
        """Incendie : ouvre la porte et la garde ouverte tant que l'alerte dure."""
        if active == self.evacuation:
            return
        self.evacuation = active
        if active:
            log.warning("Incendie : porte ouverte pour l'évacuation")
            self.door.open()
            self._set_message(now, "Porte ouverte : évacuation")
        else:
            log.info("Fin de l'évacuation : fermeture de la porte")
            self._close_at = now

    def state(self):
        values = {"porte_ouverte": int(self.door.is_open)}
        if self.last_card is not None:
            values["derniere_carte"] = str(self.last_card)
        return values

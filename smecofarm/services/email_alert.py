"""Envoi d'e-mails d'alerte avec photo via Gmail.

Gmail n'accepte plus le mot de passe normal pour les programmes : il faut
activer la validation en deux étapes puis créer un « mot de passe d'application »
(voir README). Ce mot de passe se met dans le fichier .env, jamais dans le code.

L'envoi se fait en arrière-plan (il peut prendre quelques secondes) et un délai
minimum entre deux e-mails évite d'inonder la boîte de réception.
"""

import io
import logging
import smtplib
import threading
import time
from email.message import EmailMessage

from PIL import Image

log = logging.getLogger(__name__)


class GmailNotifier:
    def __init__(self, user, app_password, recipients, cooldown_s=600):
        self.user = user
        self.app_password = app_password.replace(" ", "")
        self.recipients = [r.strip() for r in recipients.split(",") if r.strip()]
        self.cooldown_s = cooldown_s
        self._last_sent = None

    def send_alert(self, subject, body, image=None):
        """Envoie l'alerte (avec la photo RGB numpy si fournie).

        Retourne False si l'e-mail est ignoré à cause du délai minimum.
        """
        now = time.monotonic()
        if self._last_sent is not None and now - self._last_sent < self.cooldown_s:
            log.info("E-mail non envoyé (délai minimum de %d min)", self.cooldown_s // 60)
            return False
        self._last_sent = now
        message = self._build(subject, body, image)
        threading.Thread(target=self._send, args=(message,), name="email", daemon=True).start()
        return True

    def _build(self, subject, body, image):
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.user
        message["To"] = ", ".join(self.recipients)
        message.set_content(body)
        if image is not None:
            buffer = io.BytesIO()
            Image.fromarray(image).save(buffer, format="JPEG", quality=85)
            name = time.strftime("smecofarm_%Y%m%d_%H%M%S.jpg")
            message.add_attachment(buffer.getvalue(), maintype="image", subtype="jpeg", filename=name)
        return message

    def _send(self, message):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
                smtp.login(self.user, self.app_password)
                smtp.send_message(message)
            log.info("E-mail envoyé à %s", message["To"])
        except Exception:
            log.exception("Échec de l'envoi de l'e-mail (vérifiez GMAIL_USER / GMAIL_APP_PASSWORD)")


class NullNotifier:
    """Remplace l'e-mail quand il n'est pas configuré : affiche seulement le message."""

    def send_alert(self, subject, body, image=None):
        log.warning("[E-mail désactivé] %s\n%s", subject, body)
        return True

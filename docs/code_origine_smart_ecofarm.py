# Code d'origine du projet Smart EcoFarm (avant l'intégration dans smecofarm/).
# Conservé comme référence pour le rapport ; il n'est plus utilisé par main.py.
# Seule modification : BLYNK_AUTH_TOKEN était vide (ligne invalide), remplacé par "".
#
# Ce que la nouvelle version reprend : câblage (GPIO), servo de la porte, badge RFID,
# LED, buzzer, plages de couleurs HSV de la caméra, pins Blynk V0 et V3 à V7.

import BlynkLib
from BlynkTimer import BlynkTimer
import RPi.GPIO as GPIO
import Adafruit_DHT
from mfrc522 import SimpleMFRC522
import threading
import time
import cv2
import numpy as np

# =====================================
# 1. INITIALISATION
# =====================================

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.cleanup()

BLYNK_AUTH_TOKEN = ""

blynk = BlynkLib.Blynk(BLYNK_AUTH_TOKEN)
timer = BlynkTimer()

stop_event = threading.Event()

# Verrous et état des alarmes
etat_lock = threading.Lock()
rfid_lock = threading.Lock()
porte_lock = threading.Lock()
alarme_lock = threading.Lock()

fire_detected = False
badge_alarm_until = 0

# =====================================
# 2. CAPTEUR DHT11
# =====================================

DHT_SENSOR = Adafruit_DHT.DHT11
DHT_PIN = 17
TEMP_THRESHOLD = 30.0

temperature_haute = False
badge_autorise = False

# =====================================
# 3. CAPTEUR MQ-135
# =====================================

MQ135_PIN = 16
MQ135_ACTIVE_LOW = True

GPIO.setup(MQ135_PIN, GPIO.IN)

# =====================================
# 4. LED
# =====================================

LED_PIN = 22

GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)

# =====================================
# 5. SERVO : PORTE SUR GPIO26
# =====================================

SERVO_PIN = 26

GPIO.setup(SERVO_PIN, GPIO.OUT)

servo_pwm = GPIO.PWM(SERVO_PIN, 50)
servo_pwm.start(0)

ANGLE_FERME = 0
ANGLE_OUVERT = 90


def tourner_servo(angle):
    duty = 2.5 + angle / 18.0
    servo_pwm.ChangeDutyCycle(duty)
    time.sleep(0.5)
    servo_pwm.ChangeDutyCycle(0)


def ouvrir_porte():
    print("Ouverture de la porte...")
    tourner_servo(ANGLE_OUVERT)


def fermer_porte():
    print("Fermeture de la porte...")
    tourner_servo(ANGLE_FERME)

# =====================================
# 6. BUZZER SUR GPIO23
# =====================================


BUZZER_PIN = 23

GPIO.setup(BUZZER_PIN, GPIO.OUT)
GPIO.output(BUZZER_PIN, GPIO.LOW)


def buzzer_worker():
    """Le buzzer sonne si une carte est refusée
    ou si la caméra détecte un feu."""

    while not stop_event.is_set():
        with alarme_lock:
            alarme_feu = fire_detected
            alarme_badge = time.time() < badge_alarm_until

        GPIO.output(
            BUZZER_PIN,
            GPIO.HIGH if (alarme_feu or alarme_badge)
            else GPIO.LOW
        )

        time.sleep(0.05)


def alerter_carte_refusee():
    global badge_alarm_until

    with alarme_lock:
        badge_alarm_until = time.time() + 2

# =====================================
# 7. LECTEUR RFID
# =====================================


reader = SimpleMFRC522()

# Une seule carte autorisée
CARTES_AUTORISEES = {
    1046817149299
}

# =====================================
# 8. GESTION DE LA LED
# =====================================


def actualiser_led():
    with etat_lock:
        etat_led = temperature_haute or badge_autorise

    GPIO.output(
        LED_PIN,
        GPIO.HIGH if etat_led else GPIO.LOW
    )

    blynk.virtual_write(0, int(etat_led))

# =====================================
# 9. LECTURE DES CAPTEURS
# =====================================


def myData():
    global temperature_haute

    humidity, temperature = Adafruit_DHT.read_retry(
        DHT_SENSOR,
        DHT_PIN
    )

    if temperature is not None and humidity is not None:
        print(
            f"Température : {temperature:.1f} °C | "
            f"Humidité : {humidity:.1f} %"
        )

        blynk.virtual_write(3, temperature)
        blynk.virtual_write(4, humidity)

        with etat_lock:
            temperature_haute = temperature > TEMP_THRESHOLD

        actualiser_led()
    else:
        print("Erreur de lecture du DHT11.")

    mq135_raw = GPIO.input(MQ135_PIN)

    air_pollue = (
        mq135_raw == 0
        if MQ135_ACTIVE_LOW
        else mq135_raw == 1
    )

    print(
        "MQ-135 :",
        "SEUIL DEPASSE" if air_pollue
        else "SEUIL NON DEPASSE"
    )

    blynk.virtual_write(5, int(air_pollue))

# =====================================
# 10. CAMERA : DETECTION DE FLAMMES
# =====================================


def camera_worker():
    global fire_detected

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():
        print("ERREUR : caméra inaccessible.")
        print("Vérifiez la connexion et l'index de la caméra.")
        return

    print("Caméra démarrée : surveillance du feu.")

    frames_feu = 0

    try:
        while not stop_event.is_set():
            success, frame = camera.read()

            if not success:
                print("Impossible de lire l'image caméra.")
                time.sleep(1)
                continue

            # Réduction de l'image pour accélérer l'analyse
            frame = cv2.resize(frame, (320, 240))

            # Conversion en HSV
            hsv = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2HSV
            )

            # Couleurs rouges et orange pouvant correspondre
            # à une flamme. Cette méthode reste approximative.
            masque_orange = cv2.inRange(
                hsv,
                np.array([5, 100, 150]),
                np.array([35, 255, 255])
            )

            masque_rouge_1 = cv2.inRange(
                hsv,
                np.array([0, 120, 150]),
                np.array([5, 255, 255])
            )

            masque_rouge_2 = cv2.inRange(
                hsv,
                np.array([170, 120, 150]),
                np.array([179, 255, 255])
            )

            masque = cv2.bitwise_or(
                masque_orange,
                masque_rouge_1
            )

            masque = cv2.bitwise_or(
                masque,
                masque_rouge_2
            )

            # Nettoyage du masque
            noyau = np.ones((3, 3), np.uint8)

            masque = cv2.morphologyEx(
                masque,
                cv2.MORPH_OPEN,
                noyau
            )

            # Surface occupée par les couleurs ciblées
            ratio = cv2.countNonZero(masque) / (
                masque.shape[0] * masque.shape[1]
            )

            # Détection approximative : seuil à calibrer
            couleur_suspecte = ratio > 0.02

            if couleur_suspecte:
                frames_feu += 1
            else:
                frames_feu = 0

            # Demander plusieurs images successives
            # pour limiter les déclenchements isolés
            nouveau_statut = frames_feu >= 3

            with alarme_lock:
                ancien_statut = fire_detected
                fire_detected = nouveau_statut

            if nouveau_statut and not ancien_statut:
                print("!!! ALERTE : FEU POTENTIEL DETECTE !!!")
                blynk.virtual_write(7, "ALERTE : feu potentiel")

            elif ancien_statut and not nouveau_statut:
                print("Alerte feu terminée.")

                blynk.virtual_write(7, "Aucune flamme détectée")

            time.sleep(0.05)

    finally:
        camera.release()
        print("Caméra arrêtée.")

# =====================================
# 11. RFID : CONTROLE DE LA PORTE
# =====================================


def rfid_worker():
    global badge_autorise

    print("Lecteur RFID prêt.")
    print("Approchez une carte...")

    derniere_carte = None
    dernier_temps = 0

    while not stop_event.is_set():
        try:
            with rfid_lock:
                card_id, text = reader.read()

            maintenant = time.time()

            # Éviter de traiter plusieurs fois la même carte
            if (
                card_id == derniere_carte
                and maintenant - dernier_temps < 3
            ):
                continue

            derniere_carte = card_id
            dernier_temps = maintenant

            print(f"Carte détectée : UID {card_id}")

            if card_id in CARTES_AUTORISEES:
                print("CARTE AUTORISEE.")

                with porte_lock:
                    with etat_lock:
                        badge_autorise = True

                    actualiser_led()

                    blynk.virtual_write(6, str(card_id))
                    blynk.virtual_write(7, "Accès autorisé")

                    ouvrir_porte()

                    # Porte ouverte pendant 4 secondes
                    time.sleep(4)

                    fermer_porte()

                    with etat_lock:
                        badge_autorise = False

                    actualiser_led()

                print("Porte fermée.")

            else:
                print("CARTE REFUSEE.")

                blynk.virtual_write(6, str(card_id))
                blynk.virtual_write(7, "Carte non reconnue")

                # Sonnerie pendant 2 secondes
                alerter_carte_refusee()

            time.sleep(1)

        except Exception as e:
            print("Erreur RFID :", repr(e))
            time.sleep(2)

# =====================================
# 12. CONNEXION BLYNK
# =====================================


@blynk.on("connected")
def blynk_connected():
    print("Raspberry Pi connecté à Blynk.")


timer.set_interval(2, myData)

# =====================================
# 13. LANCEMENT DU SYSTEME
# =====================================

threads = [
    threading.Thread(target=rfid_worker, daemon=True),
    threading.Thread(target=camera_worker, daemon=True),
    threading.Thread(target=buzzer_worker, daemon=True)
]

try:
    fermer_porte()

    for thread in threads:
        thread.start()

    print("Smart EcoFarm démarré.")
    print("RFID + Servo + Buzzer + Caméra + Capteurs")

    while True:
        blynk.run()
        timer.run()
        time.sleep(0.01)

except KeyboardInterrupt:
    print("\nArrêt du système.")

finally:
    stop_event.set()

    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

    servo_pwm.stop()
    GPIO.cleanup()

"""
Smart EcoFarm - système complet + IA (vision par ordinateur embarquée)

Ce fichier reprend le système existant (RFID, servo, buzzer, caméra feu,
DHT11, ventilateur, FC-28, pompe, Blynk) et y ajoute la partie IA, marquée
[IA] dans le code :

  - Détection d'oiseaux : modèle EfficientDet-Lite0 pré-entraîné (COCO).
    Un oiseau devant la caméra -> bips du buzzer pour le chasser.
  - Maladies des feuilles de tomate : modèle MobileNetV2 pré-entraîné
    (PlantVillage), 9 maladies + « saine ».

Les deux modèles tournent sur le Raspberry Pi lui-même (Edge AI), sans
Internet. Ils utilisent la même webcam que la détection de feu.

Fichiers nécessaires : le dossier models/ du projet SmEcoFarm, placé à côté
de ce fichier (c'est déjà le cas dans le dépôt Git).

Installation sans environnement virtuel (une seule fois, dans un terminal) :
    sudo apt-get install -y libopenblas0 python3-opencv python3-numpy
    pip3 install tflite-runtime
Si le moteur d'IA est absent, le reste du système fonctionne quand même
(un message l'indique au démarrage).
"""

import BlynkLib
from BlynkTimer import BlynkTimer
import RPi.GPIO as GPIO
import Adafruit_DHT
from mfrc522 import SimpleMFRC522
import threading
import time
import os
import random
import cv2
import numpy as np

# =====================================
# 1. INITIALISATION
# =====================================

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.cleanup()

BLYNK_AUTH_TOKEN = 'COLLER_VOTRE_TOKEN_BLYNK_ICI'

blynk = BlynkLib.Blynk(BLYNK_AUTH_TOKEN)
timer = BlynkTimer()

stop_event = threading.Event()

etat_lock = threading.Lock()
rfid_lock = threading.Lock()
porte_lock = threading.Lock()
alarme_lock = threading.Lock()

fire_detected = False
badge_alarm_until = 0

# [IA] Buzzer « chasse aux oiseaux » : bips jusqu'à cet instant
bird_alarm_until = 0
bird_bip_periode = 0.15

# =====================================
# 2. CAPTEUR DHT11
# =====================================

DHT_SENSOR = Adafruit_DHT.DHT11
DHT_PIN = 17

TEMP_THRESHOLD = 30.0
temperature_haute = False

# =====================================
# 3. LED
# =====================================

LED_PIN = 22

GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(LED_PIN, GPIO.LOW)

# =====================================
# 4. VENTILATEUR GPIO6
# =====================================

FAN_PIN = 6

FAN_TEMP_THRESHOLD = 10.0
FAN_HUM_THRESHOLD = 70.0

GPIO.setup(FAN_PIN, GPIO.OUT)
GPIO.output(FAN_PIN, GPIO.LOW)

# =====================================
# 5. CAPTEUR D'HUMIDITE DU SOL FC-28
# =====================================

SOL_PIN = 16

# True : sortie HIGH = sol sec
# False : sortie LOW = sol sec
SOL_SEC_SI_HIGH = True

GPIO.setup(SOL_PIN, GPIO.IN)

# =====================================
# 6. POMPE D'IRRIGATION GPIO5
# =====================================

POMPE_PIN = 5
POMPE_ACTIVE_HIGH = True

DUREE_ARROSAGE = 5
DUREE_MANUELLE_MAX = 60

SOL_SEC_AVANT_ARROSAGE = 30
PAUSE_ENTRE_ARROSAGES = 600

GPIO.setup(
    POMPE_PIN,
    GPIO.OUT,
    initial=GPIO.LOW if POMPE_ACTIVE_HIGH else GPIO.HIGH
)

pompe_on = False
pompe_manuelle = False
mode_auto = True

fin_arrosage = 0
prochain_arrosage_permis = 0
compteur_sol_sec = 0


def ecrire_pompe(allumer):

    niveau_on = GPIO.HIGH if POMPE_ACTIVE_HIGH else GPIO.LOW
    niveau_off = GPIO.LOW if POMPE_ACTIVE_HIGH else GPIO.HIGH

    GPIO.output(
        POMPE_PIN,
        niveau_on if allumer else niveau_off
    )


def piloter_pompe(allumer):

    global pompe_on

    pompe_on = allumer
    ecrire_pompe(allumer)

    blynk.virtual_write(10, int(allumer))

    print("POMPE :", "ON" if allumer else "OFF")


def sol_est_sec():

    niveau_haut = GPIO.input(SOL_PIN) == GPIO.HIGH

    return niveau_haut if SOL_SEC_SI_HIGH else not niveau_haut


# Pompe obligatoirement éteinte au démarrage
ecrire_pompe(False)


# =====================================
# 7. LECTURE HUMIDITE DU SOL
# =====================================

def actualiser_humidite_sol():

    sol_sec = sol_est_sec()

    if sol_sec:
        statut = "SOL SEC"
        valeur = 1
    else:
        statut = "SOL HUMIDE"
        valeur = 0

    print(f"Capteur FC-28 : {statut}")

    # Blynk V1
    # 0 = sol humide
    # 1 = sol sec
    blynk.virtual_write(1, valeur)


# =====================================
# 8. BOUTON MANUEL BLYNK V8
# =====================================

@blynk.on("V8")
def v8_pompe_manuelle(value):

    global pompe_manuelle
    global fin_arrosage

    pompe_manuelle = value[0] == "1"

    if pompe_manuelle:

        fin_arrosage = time.time() + DUREE_MANUELLE_MAX
        piloter_pompe(True)

        print("Arrosage manuel activé.")

    else:

        piloter_pompe(False)
        print("Arrosage manuel désactivé.")


# =====================================
# 9. MODE AUTOMATIQUE BLYNK V9
# =====================================

@blynk.on("V9")
def v9_mode_auto(value):

    global mode_auto
    global compteur_sol_sec

    mode_auto = value[0] == "1"

    compteur_sol_sec = 0

    print(
        "Mode automatique :",
        "ACTIVÉ" if mode_auto else "DÉSACTIVÉ"
    )

    if not mode_auto and not pompe_manuelle and pompe_on:
        piloter_pompe(False)


# =====================================
# 10. CONTROLE AUTOMATIQUE DE LA POMPE
# =====================================

def controler_pompe():

    global compteur_sol_sec
    global fin_arrosage
    global prochain_arrosage_permis
    global pompe_manuelle

    maintenant = time.time()

    # 1. Arrêt après la durée programmée

    if pompe_on and maintenant >= fin_arrosage:

        if pompe_manuelle:

            pompe_manuelle = False
            blynk.virtual_write(8, 0)

            print("Fin de l'arrosage manuel.")

        piloter_pompe(False)

        prochain_arrosage_permis = (
            maintenant + PAUSE_ENTRE_ARROSAGES
        )

        print("Arrosage terminé.")

        return

    # 2. Vérifier les conditions du mode automatique

    if pompe_on or pompe_manuelle or not mode_auto:
        return

    # 3. Respecter la pause entre deux arrosages

    if maintenant < prochain_arrosage_permis:
        return

    # 4. Vérifier si le sol est sec

    if sol_est_sec():

        compteur_sol_sec += 1

        print(
            f"Sol sec depuis {compteur_sol_sec} "
            f"/ {SOL_SEC_AVANT_ARROSAGE} secondes"
        )

    else:

        compteur_sol_sec = 0

    # 5. Déclencher l'arrosage

    if compteur_sol_sec >= SOL_SEC_AVANT_ARROSAGE:

        compteur_sol_sec = 0

        fin_arrosage = maintenant + DUREE_ARROSAGE

        print("SOL SEC : ARROSAGE AUTOMATIQUE ACTIVÉ")

        piloter_pompe(True)


# =====================================
# 11. SERVO : PORTE GPIO26
# =====================================

SERVO_PIN = 26

GPIO.setup(SERVO_PIN, GPIO.OUT)

servo_pwm = GPIO.PWM(SERVO_PIN, 50)
servo_pwm.start(0)

ANGLE_FERME = 45
ANGLE_OUVERT = 180


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
# 12. BUZZER GPIO23
# =====================================

BUZZER_PIN = 23

GPIO.setup(BUZZER_PIN, GPIO.OUT)
GPIO.output(BUZZER_PIN, GPIO.LOW)


def buzzer_worker():

    while not stop_event.is_set():

        with alarme_lock:

            alarme_feu = fire_detected
            alarme_badge = time.time() < badge_alarm_until
            alarme_oiseau = time.time() < bird_alarm_until  # [IA]
            periode = bird_bip_periode

        if alarme_feu or alarme_badge:

            # Feu et carte refusée : son continu (prioritaires)
            GPIO.output(BUZZER_PIN, GPIO.HIGH)

        elif alarme_oiseau:

            # [IA] Oiseau : bips (le rythme change à chaque alerte,
            # pour que les oiseaux s'y habituent moins vite)
            bip_on = int(time.time() / periode) % 2 == 0
            GPIO.output(BUZZER_PIN, GPIO.HIGH if bip_on else GPIO.LOW)

        else:

            GPIO.output(BUZZER_PIN, GPIO.LOW)

        time.sleep(0.02)


def alerter_carte_refusee():

    global badge_alarm_until

    with alarme_lock:

        badge_alarm_until = time.time() + 2


# =====================================
# 13. LECTEUR RFID
# =====================================

reader = SimpleMFRC522()

CARTE_BLANCHE = 1046817149299
CARTE_BLEUE = 221099462090

CARTES_AUTORISEES = {
    CARTE_BLANCHE
}


# =====================================
# 14. GESTION DE LA LED
# =====================================

def actualiser_led():

    with etat_lock:

        etat_led = temperature_haute

    GPIO.output(
        LED_PIN,
        GPIO.HIGH if etat_led else GPIO.LOW
    )

    blynk.virtual_write(0, int(etat_led))


# =====================================
# 15. LECTURE DHT11 + VENTILATEUR
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

        ventilateur_on = (
            temperature > FAN_TEMP_THRESHOLD
            or humidity > FAN_HUM_THRESHOLD
        )

        GPIO.output(
            FAN_PIN,
            GPIO.HIGH if ventilateur_on else GPIO.LOW
        )

        print(
            "Ventilateur :",
            "ON" if ventilateur_on else "OFF"
        )

    else:

        print("Erreur de lecture du DHT11.")


# =====================================
# 16. CAMERA : DETECTION DE FLAMMES
# =====================================

# [IA] Dernière image de la webcam, partagée avec l'IA (une seule caméra
# ne peut pas être ouverte par deux programmes en même temps)
image_lock = threading.Lock()
derniere_image = None


def camera_worker():

    global fire_detected
    global derniere_image

    camera = cv2.VideoCapture(0)

    if not camera.isOpened():

        print("ERREUR : caméra inaccessible.")
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

            # [IA] Image en pleine résolution transmise à l'IA
            with image_lock:
                derniere_image = frame

            frame = cv2.resize(frame, (320, 240))

            hsv = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2HSV
            )

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

            noyau = np.ones((3, 3), np.uint8)

            masque = cv2.morphologyEx(
                masque,
                cv2.MORPH_OPEN,
                noyau
            )

            ratio = cv2.countNonZero(masque) / (
                masque.shape[0] * masque.shape[1]
            )

            couleur_suspecte = ratio > 0.02

            if couleur_suspecte:
                frames_feu += 1
            else:
                frames_feu = 0

            nouveau_statut = frames_feu >= 3

            with alarme_lock:

                ancien_statut = fire_detected
                fire_detected = nouveau_statut

            if nouveau_statut and not ancien_statut:

                print("!!! ALERTE : FEU POTENTIEL DETECTE !!!")

                blynk.virtual_write(
                    7,
                    "ALERTE : feu potentiel"
                )

            elif ancien_statut and not nouveau_statut:

                print("Alerte feu terminée.")

                blynk.virtual_write(
                    7,
                    "Aucune flamme détectée"
                )

            time.sleep(0.05)

    finally:

        camera.release()
        print("Caméra arrêtée.")


# =====================================
# 16 bis. [IA] VISION PAR ORDINATEUR
# =====================================
# Deux modèles pré-entraînés, sans entraînement supplémentaire :
#   - oiseaux  : EfficientDet-Lite0 (90 objets COCO, on garde « bird »)
#   - maladies : MobileNetV2 entraîné sur PlantVillage (38 classes, on garde
#                les 10 classes de la tomate)

DOSSIER_MODELES = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "models"
)

MODELE_OISEAUX = os.path.join(DOSSIER_MODELES, "bird", "efficientdet_lite0.tflite")
LABELS_OISEAUX = os.path.join(DOSSIER_MODELES, "bird", "labelmap.txt")
MODELE_MALADIES = os.path.join(DOSSIER_MODELES, "disease", "plant_disease_model.tflite")
LABELS_MALADIES = os.path.join(DOSSIER_MODELES, "disease", "plant_labels.txt")

SEUIL_OISEAU = 0.5            # confiance minimale (0 à 1)
INTERVALLE_OISEAUX = 1.0      # une analyse « oiseaux » par seconde
DUREE_BIPS_OISEAU = 3         # durée des bips quand un oiseau est vu
PAUSE_BUZZER_OISEAU = 30      # délai minimum entre deux chasses

PLANTE = "tomato"             # classes PlantVillage gardées
SEUIL_MALADIE = 0.6           # en dessous : résultat « incertain »
INTERVALLE_MALADIES = 60      # secondes ; 1800 (30 min) en usage réel

# Pins Blynk de l'IA (V0, V1, V3, V4, V6 à V10 sont déjà utilisées)
VPIN_OISEAU = 11              # 0/1 : oiseau devant la caméra
VPIN_COMPTEUR_OISEAUX = 12    # nombre d'oiseaux détectés
VPIN_MALADIE = 13             # texte : maladie détectée
VPIN_CONFIANCE_MALADIE = 14   # % de confiance

NOMS_MALADIES = {
    "tomato bacterial spot": "Tomate - tache bactérienne",
    "tomato early blight": "Tomate - alternariose",
    "tomato late blight": "Tomate - mildiou",
    "tomato leaf mold": "Tomate - moisissure des feuilles",
    "tomato septoria leaf spot": "Tomate - septoriose",
    "tomato spider mites two spotted spider mite": "Tomate - acariens",
    "tomato target spot": "Tomate - tache cible",
    "tomato tomato yellow leaf curl virus": "Tomate - virus de l'enroulement jaune",
    "tomato tomato mosaic virus": "Tomate - virus de la mosaïque",
    "tomato healthy": "Tomate - saine",
}

oiseaux_compteur = 0

# [IA] Résultats affichés sur l'image de la fenêtre caméra
derniers_oiseaux = []
dernier_resultat_maladie = ""

# Fenêtre vidéo en direct (nécessite l'écran du Pi, pas une connexion SSH)
AFFICHER_CAMERA = True


def charger_modele(chemin):
    """Charge un modèle TFLite avec le moteur installé sur le Pi."""
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        try:
            from ai_edge_litert.interpreter import Interpreter
        except ImportError:
            from tensorflow.lite import Interpreter

    modele = Interpreter(model_path=chemin, num_threads=2)
    modele.allocate_tensors()
    return modele


def lire_labels(chemin):
    with open(chemin, encoding="utf-8") as f:
        return [ligne.strip() for ligne in f if ligne.strip()]


class DetecteurOiseaux:

    def __init__(self):

        self.modele = charger_modele(MODELE_OISEAUX)
        self.labels = lire_labels(LABELS_OISEAUX)

        entree = self.modele.get_input_details()[0]
        self.index_entree = entree["index"]
        self.taille = (int(entree["shape"][2]), int(entree["shape"][1]))  # 320 x 320

        # Sorties : boîtes, classes, scores, nombre d'objets
        sorties = {s["name"]: s["index"] for s in self.modele.get_output_details()}
        self.i_boites = sorties["StatefulPartitionedCall:3"]
        self.i_classes = sorties["StatefulPartitionedCall:2"]
        self.i_scores = sorties["StatefulPartitionedCall:1"]
        self.i_nombre = sorties["StatefulPartitionedCall:0"]

    def detecter(self, image_bgr):
        """Retourne la liste des oiseaux : [(score, (x1, y1, x2, y2)), ...]."""

        hauteur, largeur = image_bgr.shape[:2]

        # Le modèle attend une image RGB 320x320, pixels de 0 à 255
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        entree = cv2.resize(rgb, self.taille).astype(np.uint8)

        self.modele.set_tensor(self.index_entree, np.expand_dims(entree, 0))
        self.modele.invoke()

        boites = self.modele.get_tensor(self.i_boites)[0]
        classes = self.modele.get_tensor(self.i_classes)[0]
        scores = self.modele.get_tensor(self.i_scores)[0]
        nombre = int(self.modele.get_tensor(self.i_nombre)[0])

        oiseaux = []

        for i in range(nombre):

            if scores[i] < SEUIL_OISEAU:
                continue

            if self.labels[int(classes[i])] != "bird":
                continue

            y1, x1, y2, x2 = np.clip(boites[i], 0, 1)
            oiseaux.append((
                float(scores[i]),
                (int(x1 * largeur), int(y1 * hauteur), int(x2 * largeur), int(y2 * hauteur))
            ))

        return sorted(oiseaux, reverse=True)


class ClassifieurMaladies:

    def __init__(self):

        self.modele = charger_modele(MODELE_MALADIES)
        self.labels = lire_labels(LABELS_MALADIES)

        entree = self.modele.get_input_details()[0]
        self.index_entree = entree["index"]
        self.taille = (int(entree["shape"][2]), int(entree["shape"][1]))  # 224 x 224
        self.index_sortie = self.modele.get_output_details()[0]["index"]

        # On sait que la plante est une tomate : on ne garde que ses 10 classes
        self.classes_plante = [
            i for i, label in enumerate(self.labels)
            if label.startswith(PLANTE + " ")
        ]

    def analyser(self, image_bgr):
        """Retourne (nom de la maladie, confiance de 0 à 1, plante saine ?)."""

        # Même prétraitement qu'à l'entraînement : RGB, 224x224, pixels / 255
        rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        entree = cv2.resize(rgb, self.taille).astype(np.float32) / 255.0

        self.modele.set_tensor(self.index_entree, np.expand_dims(entree, 0))
        self.modele.invoke()
        probas = self.modele.get_tensor(self.index_sortie)[0]

        # Probabilités recalculées entre les seules classes de la tomate
        probas_plante = probas[self.classes_plante]
        probas_plante = probas_plante / max(float(probas_plante.sum()), 1e-9)

        meilleure = int(np.argmax(probas_plante))
        label = self.labels[self.classes_plante[meilleure]]

        return (
            NOMS_MALADIES.get(label, label),
            float(probas_plante[meilleure]),
            label.endswith("healthy")
        )


def ia_worker():

    global bird_alarm_until
    global bird_bip_periode
    global oiseaux_compteur
    global derniers_oiseaux
    global dernier_resultat_maladie

    try:

        detecteur = DetecteurOiseaux()
        classifieur = ClassifieurMaladies()

    except Exception as e:

        print("IA DÉSACTIVÉE :", repr(e))
        print("Vérifiez le dossier models/ et le moteur d'IA :")
        print("  pip3 install tflite-runtime")
        return

    print("IA prête : détection d'oiseaux + analyse des maladies.")

    oiseau_present = False
    dernier_buzzer_oiseau = 0
    prochaine_analyse_maladie = time.time() + 5
    attente_affichee = False

    while not stop_event.is_set():

        debut = time.time()

        with image_lock:
            image = derniere_image

        if image is None:

            if not attente_affichee:
                print("IA : en attente d'une image de la caméra...")
                attente_affichee = True

            time.sleep(1)
            continue

        try:

            # ---------- Détection d'oiseaux ----------

            oiseaux = detecteur.detecter(image)
            derniers_oiseaux = oiseaux
            present = len(oiseaux) > 0

            if present and not oiseau_present:

                oiseaux_compteur += 1

                print(
                    f"IA : OISEAU DÉTECTÉ ({oiseaux[0][0]:.0%}) "
                    f"- total : {oiseaux_compteur}"
                )

                blynk.virtual_write(VPIN_COMPTEUR_OISEAUX, oiseaux_compteur)
                blynk.virtual_write(7, "Oiseau détecté")

            if present != oiseau_present:
                blynk.virtual_write(VPIN_OISEAU, int(present))

            oiseau_present = present

            maintenant = time.time()

            if present and maintenant - dernier_buzzer_oiseau >= PAUSE_BUZZER_OISEAU:

                dernier_buzzer_oiseau = maintenant

                with alarme_lock:
                    bird_alarm_until = maintenant + DUREE_BIPS_OISEAU
                    bird_bip_periode = random.uniform(0.08, 0.3)

                print("Buzzer : chasse des oiseaux.")

            # ---------- Analyse des maladies ----------

            if maintenant >= prochaine_analyse_maladie:

                prochaine_analyse_maladie = maintenant + INTERVALLE_MALADIES

                nom, confiance, saine = classifieur.analyser(image)
                incertain = confiance < SEUIL_MALADIE

                texte = nom + (" (incertain)" if incertain else "")
                dernier_resultat_maladie = f"{texte} {confiance:.0%}"

                print(f"IA : analyse de la feuille : {texte} - {confiance:.0%}")

                blynk.virtual_write(VPIN_MALADIE, texte)
                blynk.virtual_write(VPIN_CONFIANCE_MALADIE, round(confiance * 100))

                if not saine and not incertain:
                    blynk.virtual_write(7, "Maladie : " + nom)

        except Exception as e:

            print("Erreur IA :", repr(e))
            time.sleep(2)

        time.sleep(max(0.0, INTERVALLE_OISEAUX - (time.time() - debut)))


def afficher_camera():
    """[IA] Affiche l'image de la webcam avec les résultats (appelée par la boucle principale)."""

    with image_lock:
        image = derniere_image

    if image is None:
        return True

    vue = image.copy()

    for score, (x1, y1, x2, y2) in derniers_oiseaux:
        cv2.rectangle(vue, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(vue, f"Oiseau {score:.0%}", (x1 + 5, y1 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    lignes = [
        "FEU POTENTIEL !" if fire_detected else "Feu : rien",
        f"Oiseaux detectes : {oiseaux_compteur}",
        "Feuille : " + (dernier_resultat_maladie or "en attente"),
    ]
    for i, ligne in enumerate(lignes):
        couleur = (0, 0, 255) if (i == 0 and fire_detected) else (0, 255, 0)
        # Accents retirés : OpenCV ne sait pas les dessiner
        ligne = ligne.encode("ascii", "ignore").decode()
        cv2.putText(vue, ligne, (10, 25 + 25 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, couleur, 2)

    cv2.imshow("Smart EcoFarm - camera (touche q pour fermer)", vue)

    # Touche q : ferme seulement la fenêtre, le système continue
    return (cv2.waitKey(1) & 0xFF) != ord("q")


# =====================================
# 17. RFID : CONTROLE DE LA PORTE
# =====================================

def rfid_worker():

    print("Lecteur RFID prêt.")
    print("Approchez une carte...")

    derniere_carte = None
    absences = 0

    while not stop_event.is_set():

        try:

            with rfid_lock:

                card_id, text = reader.read_no_block()

            if card_id is None:

                absences = min(absences + 1, 5)

                if absences >= 5:
                    derniere_carte = None

                time.sleep(0.1)
                continue

            absences = 0

            if card_id == derniere_carte:

                time.sleep(0.1)
                continue

            derniere_carte = card_id

            print(f"Carte détectée : UID {card_id}")

            # CARTE BLANCHE

            if card_id == CARTE_BLANCHE:

                print("CARTE BLANCHE : ACCÈS AUTORISÉ.")

                blynk.virtual_write(6, str(card_id))

                blynk.virtual_write(
                    7,
                    "Accès autorisé - Carte blanche"
                )

                with porte_lock:

                    ouvrir_porte()

                    print("Porte ouverte pendant 4 secondes.")

                    time.sleep(4)

                    fermer_porte()

                print("Porte fermée.")

            # CARTE BLEUE

            elif card_id == CARTE_BLEUE:

                print("CARTE BLEUE : ACCÈS REFUSÉ.")

                blynk.virtual_write(6, str(card_id))

                blynk.virtual_write(
                    7,
                    "Accès refusé - Carte bleue"
                )

                alerter_carte_refusee()

                print("Buzzer activé pendant 2 secondes.")

            # CARTE INCONNUE

            else:

                print("CARTE INCONNUE : ACCÈS REFUSÉ.")

                blynk.virtual_write(6, str(card_id))

                blynk.virtual_write(
                    7,
                    "Carte inconnue"
                )

                alerter_carte_refusee()

                print("Buzzer activé pendant 2 secondes.")

        except Exception as e:

            print("Erreur RFID :", repr(e))
            time.sleep(2)


# =====================================
# 18. CONNEXION BLYNK
# =====================================

@blynk.on("connected")
def blynk_connected():

    print("Raspberry Pi connecté à Blynk.")

    blynk.virtual_write(9, int(mode_auto))

    # Envoyer immédiatement l'état du sol
    actualiser_humidite_sol()

    blynk.virtual_write(10, int(pompe_on))

    # [IA] Compteur d'oiseaux
    blynk.virtual_write(VPIN_COMPTEUR_OISEAUX, oiseaux_compteur)


# =====================================
# 19. TIMERS
# =====================================

# DHT11 toutes les 2 secondes
timer.set_interval(2, myData)

# Humidité du sol toutes les secondes
timer.set_interval(1, actualiser_humidite_sol)

# Contrôle de la pompe toutes les secondes
timer.set_interval(1, controler_pompe)


# =====================================
# 20. LANCEMENT DU SYSTEME
# =====================================

threads = [

    threading.Thread(
        target=rfid_worker,
        daemon=True
    ),

    threading.Thread(
        target=camera_worker,
        daemon=True
    ),

    threading.Thread(
        target=buzzer_worker,
        daemon=True
    ),

    # [IA]
    threading.Thread(
        target=ia_worker,
        daemon=True
    )

]

try:

    fermer_porte()

    for thread in threads:
        thread.start()

    print("Smart EcoFarm démarré.")

    print(
        "RFID + Servo + Buzzer + Caméra + "
        "DHT11 + Ventilateur + FC-28 + Pompe + IA"
    )

    fenetre_ouverte = AFFICHER_CAMERA

    while True:

        blynk.run()
        timer.run()

        # [IA] Vidéo en direct
        if fenetre_ouverte:
            try:
                fenetre_ouverte = afficher_camera()
                if not fenetre_ouverte:
                    cv2.destroyAllWindows()
            except cv2.error as e:
                print("Fenêtre caméra impossible (pas d'écran ?) :", e)
                fenetre_ouverte = False

        time.sleep(0.01)

except KeyboardInterrupt:

    print("\nArrêt du système.")

finally:

    stop_event.set()

    GPIO.output(LED_PIN, GPIO.LOW)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    GPIO.output(FAN_PIN, GPIO.LOW)

    ecrire_pompe(False)

    servo_pwm.stop()

    try:
        cv2.destroyAllWindows()
    except cv2.error:
        pass

    GPIO.cleanup()

    print("Système arrêté proprement.")

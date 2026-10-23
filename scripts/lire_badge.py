"""Afficher le numéro d'une carte RFID, pour l'ajouter dans config.yaml.

    python scripts/lire_badge.py

Approchez la carte du lecteur ; Ctrl+C pour quitter.
Ensuite, dans config.yaml, section acces > cartes_autorisees, ajoutez :
    123456789012: Nom de la personne
(Arrêtez d'abord le service s'il tourne : sudo systemctl stop smecofarm)
"""

import RPi.GPIO as GPIO
from mfrc522 import SimpleMFRC522

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
reader = SimpleMFRC522()
print("Approchez une carte du lecteur (Ctrl+C pour quitter)...")
try:
    while True:
        card_id = reader.read_id()
        print(f"Carte détectée : {card_id}")
        input("Appuyez sur Entrée pour lire une autre carte...")
except KeyboardInterrupt:
    print()
finally:
    GPIO.cleanup()

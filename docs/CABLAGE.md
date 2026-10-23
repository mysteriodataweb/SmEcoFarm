# Câblage sur le Raspberry Pi 4

Ce câblage reprend celui du **code d'origine du projet** (`docs/code_origine_smart_ecofarm.py`),
auquel s'ajoute le relais du ventilateur.

Le Pi n'a que deux broches 5 V (2 et 4) et deux broches 3,3 V (1 et 17) : utilisez les rails « + » et « − »
d'une breadboard pour brancher plusieurs éléments sur la même alimentation.

Numéros GPIO = numérotation **BCM** (celle de `config.yaml`). Broche physique = position sur le connecteur 40 broches.

| Élément | Broche du module | Raspberry Pi | Broche physique |
|---|---|---|---|
| **DHT11** | VCC (+) | 3,3 V | 1 |
| | DATA (out) | GPIO17 | 11 |
| | GND (−) | GND | 9 |
| **MQ-135** | VCC | **5 V** (le chauffage a besoin de 5 V) | 2 (ou rail 5 V) |
| | GND | GND | 6 |
| | DO | GPIO16 **via pont diviseur** (voir ci-dessous) | 36 |
| | AO | non branché (il faudrait un ADS1115) | — |
| **Lecteur RFID RC522** | 3.3V | 3,3 V (**jamais 5 V**) | 17 |
| | RST | comme dans votre montage actuel (habituellement GPIO25) | 22 |
| | GND | GND | 20 |
| | MISO | GPIO9 (SPI MISO) | 21 |
| | MOSI | GPIO10 (SPI MOSI) | 19 |
| | SCK | GPIO11 (SPI SCLK) | 23 |
| | SDA (SS) | GPIO8 (SPI CE0) | 24 |
| | IRQ | non branché | — |
| **Servo de la porte** | signal (orange / jaune) | GPIO26 | 37 |
| | + (rouge) | 5 V (rail 5 V) | 4 |
| | − (marron / noir) | GND | 39 |
| **LED** | + (patte longue), avec une résistance de 220 Ω | GPIO22 | 15 |
| | − | GND | 14 |
| **Buzzer actif** | + (patte longue) | GPIO23 | 16 |
| | − | GND | 25 |
| **Module relais** (ventilateur) | VCC | 5 V (rail 5 V) | — |
| | GND | GND | 30 |
| | IN | GPIO27 | 13 |
| **Ventilateur 5 V** | + | borne **NO** du relais (la borne **COM** va au rail 5 V) | — |
| | − | GND | 34 |
| **Webcams USB** | | ports USB | — |

## Bus SPI pour le lecteur RFID

Le lecteur RC522 utilise le bus SPI, désactivé par défaut. `install.sh` l'active ; sinon :
`sudo raspi-config` > *Interface Options* > *SPI* > *Yes*, puis `sudo reboot`.
Vérification : `ls /dev/spidev0.0` doit afficher le fichier.

Pour connaître le numéro d'une nouvelle carte : `python scripts/lire_badge.py`, puis l'ajouter dans
`config.yaml` (section `acces` > `cartes_autorisees`).

## Servo

Un servo consomme beaucoup au démarrage du mouvement. S'il tremble ou si le Pi redémarre quand la porte
bouge, alimentez le servo avec une alimentation 5 V séparée (en reliant son GND au GND du Pi).

## ⚠️ Pont diviseur pour la sortie DO du MQ-135

Le module MQ-135 est alimenté en 5 V : sa sortie DO peut donc monter à 5 V.
Les broches GPIO du Pi acceptent **3,3 V maximum** : sans protection, on risque d'abîmer le Pi.

```
MQ-135 DO ──── 10 kΩ ────┬──── GPIO16 (broche 36)
                         │
                       20 kΩ
                         │
                        GND
```

5 V × 20 / (10 + 20) = 3,3 V. On peut aussi utiliser 1 kΩ + 2 kΩ, ou 2 résistances de 10 kΩ en série pour faire 20 kΩ.

## Réglage du MQ-135

1. Première utilisation : laisser le module alimenté **24 h** (rodage du capteur).
2. À chaque démarrage, il faut environ **3 minutes** de chauffe. Pendant ce temps, le programme ignore le capteur.
3. Dans un air propre, tourner le **potentiomètre bleu** jusqu'à ce que la LED « DO » s'éteigne, puis tourner un peu plus.
4. Test : approcher une allumette qu'on vient d'éteindre (fumée), ou un coton imbibé d'alcool : la LED doit s'allumer.

## Module relais

- La plupart des modules collent quand IN = 0 (« actif bas ») : c'est le réglage par défaut (`relais_actif_bas: true`).
  Si le ventilateur fait l'inverse de ce qui est affiché, mettre `false`.
- Un mini ventilateur 5 V consomme peu et peut être alimenté par le 5 V du Pi. Utilisez l'alimentation officielle **5 V 3 A** du Pi 4 (webcams, servo, ventilateur).

## Buzzer actif

Un buzzer actif sonne dès qu'il est alimenté. S'il s'agit d'un **module** (petite carte avec 3 broches VCC / I/O / GND),
brancher VCC sur 3,3 V, I/O sur GPIO23 et GND sur GND. Si c'est un **buzzer seul** qui sonne faiblement,
ajouter un transistor (2N2222 + résistance de 1 kΩ sur la base) : une broche GPIO ne fournit que quelques mA.

## Deux webcams USB

Chaque webcam crée souvent **deux** périphériques (`/dev/video0` et `/dev/video1` pour la première, `/dev/video2` et `/dev/video3` pour la seconde).
Pour les identifier :

```bash
v4l2-ctl --list-devices        # sudo apt install v4l-utils
ls -l /dev/v4l/by-id/
```

Dans `config.yaml`, mettre de préférence le chemin `/dev/v4l/by-id/...-video-index0` : il ne change pas au redémarrage, contrairement aux numéros.

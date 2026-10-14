# Câblage sur le Raspberry Pi 4

Le Pi n'a que deux broches 5 V (2 et 4) : reliez la broche 2 au rail « + » d'une breadboard et une broche GND au rail « − », puis branchez dessus tout ce qui demande du 5 V ou une masse.

Numéros GPIO = numérotation **BCM** (celle de `config.yaml`). Broche physique = position sur le connecteur 40 broches.

| Élément | Broche du module | Raspberry Pi | Broche physique |
|---|---|---|---|
| **DHT11** | VCC (+) | 3,3 V | 1 |
| | DATA (out) | GPIO4 | 7 |
| | GND (−) | GND | 9 |
| **MQ-135** | VCC | **5 V** (le chauffage a besoin de 5 V) | 2 (ou rail 5 V) |
| | GND | GND | 6 |
| | DO | GPIO17 **via pont diviseur** (voir ci-dessous) | 11 |
| | AO | non branché (il faudrait un ADS1115) | — |
| **Module relais** | VCC | 5 V | 4 (ou rail 5 V) |
| | GND | GND | 14 |
| | IN | GPIO27 | 13 |
| **Ventilateur 5 V** | + | borne **NO** du relais (la borne **COM** va au rail 5 V) | — |
| | − | GND | 20 |
| **Buzzer actif** | + (patte longue) | GPIO22 | 15 |
| | − | GND | 25 |
| **Webcams USB** | | ports USB (de préférence les ports USB 2 noirs pour l'une et USB 3 bleus pour l'autre) | — |

## ⚠️ Pont diviseur pour la sortie DO du MQ-135

Le module MQ-135 est alimenté en 5 V : sa sortie DO peut donc monter à 5 V.
Les broches GPIO du Pi acceptent **3,3 V maximum** : sans protection, on risque d'abîmer le Pi.

```
MQ-135 DO ──── 10 kΩ ────┬──── GPIO17 (broche 11)
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
- Un mini ventilateur 5 V consomme peu et peut être alimenté par le 5 V du Pi. Utilisez l'alimentation officielle **5 V 3 A** du Pi 4 (deux webcams + ventilateur).

## Buzzer actif

Un buzzer actif sonne dès qu'il est alimenté. S'il s'agit d'un **module** (petite carte avec 3 broches VCC / I/O / GND),
brancher VCC sur 3,3 V, I/O sur GPIO22 et GND sur GND. Si c'est un **buzzer seul** qui sonne faiblement,
ajouter un transistor (2N2222 + résistance de 1 kΩ sur la base) : une broche GPIO ne fournit que quelques mA.

## Deux webcams USB

Chaque webcam crée souvent **deux** périphériques (`/dev/video0` et `/dev/video1` pour la première, `/dev/video2` et `/dev/video3` pour la seconde).
Pour les identifier :

```bash
v4l2-ctl --list-devices        # sudo apt install v4l-utils
ls -l /dev/v4l/by-id/
```

Dans `config.yaml`, mettre de préférence le chemin `/dev/v4l/by-id/...-video-index0` : il ne change pas au redémarrage, contrairement aux numéros.

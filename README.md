# SmEcoFarm : vision par ordinateur embarquée (Edge AI)

Prototype scolaire : une caméra filme les cultures, le **Raspberry Pi 4** exécute
localement deux modèles d'IA **pré-entraînés, sans entraînement supplémentaire**,
puis envoie les résultats au dashboard **Blynk** (étape suivante).

| Objectif | Modèle | Ce qu'il fait |
|---|---|---|
| Détection d'oiseaux | EfficientDet-Lite0 (COCO) | Dit s'il y a un oiseau et où il se trouve (boîte) |
| Détection de maladies | MobileNetV2 (PlantVillage) | Classe une feuille de tomate : saine ou l'une de 9 maladies |

> État actuel : **étape 1, les modèles**. La caméra, le buzzer et Blynk viendront ensuite.

## Organisation

```
models/
  bird/      efficientdet_lite0.tflite, labelmap.txt   (4,6 Mo)
  disease/   plant_disease_model.tflite, plant_labels.txt  (11,6 Mo)
smecofarm/
  bird_detector.py       classe BirdDetector
  disease_classifier.py  classe DiseaseClassifier
  runtime.py             chargement TFLite + utilitaires image
scripts/
  test_models.py         tester sur une image, un dossier ou la caméra
  evaluate_disease.py    mesurer la précision sur des images étiquetées
  benchmark.py           mesurer la vitesse (à lancer sur le Pi)
tests/test_models.py     tests automatiques (pytest)
test_images/
  birds/                 1 photo d'oiseau + 6 photos sans oiseau
  tomato/<classe>/       10 feuilles de tomate par classe (100 images)
```

## Installation

Sur le Raspberry Pi 4 : **Raspberry Pi OS 64 bits (Bookworm)**. Même chose sur PC.

```bash
git clone <url-du-depot> SmEcoFarm && cd SmEcoFarm
python3 -m venv --system-site-packages .venv   # --system-site-packages : réutilise picamera2/opencv installés par apt
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

```bash
# Tests automatiques (10 tests)
python -m pytest tests/

# Oiseaux sur toutes les photos de test (images annotées dans output/)
python scripts/test_models.py --dir test_images/birds --model bird

# Voir toutes les classes COCO détectées (pour vérifier que le modèle « voit » bien)
python scripts/test_models.py --image test_images/birds/dog.jpg --model bird --all-classes

# Maladie sur une feuille
python scripts/test_models.py --image test_images/tomato/tomato_late_blight/tomato_late_blight_01.jpg --model disease

# Précision sur les 100 feuilles de test
python scripts/evaluate_disease.py

# Vitesse sur le Pi
python scripts/benchmark.py

# Caméra (webcam USB, nécessite OpenCV), une analyse par seconde
python scripts/test_models.py --camera
```

Dans votre propre code :

```python
from smecofarm import BirdDetector, DiseaseClassifier

birds = BirdDetector(score_threshold=0.5)
for d in birds.detect("photo.jpg"):          # chemin, image PIL ou tableau numpy RGB
    print(d.label, d.score, d.box)           # box = (x_min, y_min, x_max, y_max) en pixels

disease = DiseaseClassifier(crop="tomato", confidence_threshold=0.6)
p = disease.predict("feuille.jpg")
print(p.name, p.confidence, p.uncertain, p.healthy)
# ex. "Tomate - mildiou" 0.95 False False
```

⚠️ OpenCV fournit les images en **BGR** : convertir avec `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)` avant d'appeler les modèles.

## Les modèles

### Oiseaux : EfficientDet-Lite0

- Source : exemple officiel TensorFlow Lite pour Raspberry Pi (Google),
  `lite-model_efficientdet_lite0_detection_metadata_1.tflite`.
- Entraîné sur COCO (90 classes, dont `bird`) ; quantifié int8.
- Entrée : image RGB 320×320, pixels 0–255 (uint8). Sortie : jusqu'à 25 détections
  (boîte, classe, score), post-traitement inclus dans le modèle.
- On ne garde que la classe `bird`, avec un seuil de **0,5**.

### Maladies : MobileNetV2 + PlantVillage

- Source : projet [obeshor/Plant-Diseases-Detector](https://github.com/obeshor/Plant-Diseases-Detector)
  (Yannick Serge Obam, licence Apache 2.0), fichier `plant_disease_model.tflite`.
- MobileNetV2 (pré-entraîné ImageNet) + couches finales entraînées sur PlantVillage par l'auteur ;
  précision de validation annoncée dans son notebook : environ 94 %.
- Entrée : image RGB 224×224, pixels divisés par 255 (float32). Sortie : 38 probabilités.
- **Restriction à la tomate** : on garde les 10 classes de la tomate et on renormalise les
  probabilités. Le modèle ne peut donc plus répondre « pomme » ou « raisin » sur une feuille de tomate.
- En dessous de **60 %** de confiance, le résultat est marqué « incertain ».
- Le chou et le persil **ne sont pas dans PlantVillage** : il faudrait un entraînement
  pour les ajouter (amélioration future).

## Résultats (sur PC, images de test du dépôt)

**Oiseaux** : l'aigle est détecté (84 %). Aucune fausse détection « bird » sur les
6 photos sans oiseau (chien, chevaux, personne, girafe, cerf-volant, tableau).

**Maladies** : `python scripts/evaluate_disease.py`

| Classe | Correct |
|---|---|
| Tache bactérienne | 10/10 |
| Alternariose (early blight) | 9/10 |
| Saine | 7/10 |
| Mildiou (late blight) | 9/10 |
| Moisissure des feuilles | 10/10 |
| Septoriose | 9/10 |
| Acariens | 8/10 |
| Tache cible | 5/10 |
| Virus de la mosaïque | 10/10 |
| Virus de l'enroulement jaune | 10/10 |
| **Total** | **87/100** |

**Limites à indiquer dans le rapport :**
- Ce chiffre est **optimiste** : les images PlantVillage ont été prises en laboratoire
  (feuille seule, fond uni), et une partie a probablement servi à entraîner le modèle.
  Sur des photos prises au jardin, la précision sera nettement plus faible.
- 10 images par classe, c'est peu : le résultat varie de quelques points selon les images choisies.
- Le détecteur d'oiseaux repère mal les oiseaux très petits ou lointains dans l'image.

**Vitesse** : sur PC, environ 17 ms (oiseaux) et 4 ms (maladies) par image.
À mesurer sur le Pi 4 avec `scripts/benchmark.py` ; on peut s'attendre à
environ 10 fois plus, ce qui reste suffisant (1 à 2 analyses par seconde suffisent).

## Conseils pour la démo

- **Oiseaux** : montrer à la caméra une **photo réaliste** d'oiseau (imprimée ou sur un
  téléphone, luminosité au maximum), oiseau entier, occupant au moins 10–20 % de l'image.
  Montrer aussi une image sans oiseau pour prouver qu'il n'y a pas de fausse alerte.
- **Maladies** : montrer une feuille en **gros plan**, bien éclairée, sur fond uni.
  Les images de `test_images/tomato/` (imprimées ou sur écran) fonctionnent bien.

## Provenance des images de test

- `test_images/birds/` : images d'exemple du projet Darknet/YOLO (pjreddie/darknet, dossier `data/`).
- `test_images/tomato/` : échantillon du jeu PlantVillage (spMohanty/PlantVillage-Dataset,
  `raw/color`), 10 images par classe tirées au hasard. Voir les dépôts d'origine pour leurs licences.

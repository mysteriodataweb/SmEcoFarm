# SmEcoFarm : ferme intelligente sur Raspberry Pi (Edge AI)

Prototype scolaire. **Un seul Raspberry Pi 4** surveille :

| Station | Matériel | Fonctions |
|---|---|---|
| **Champ** | webcam USB n° 1, buzzer actif | Détection d'oiseaux (IA) → buzzer pour les chasser ; analyse des maladies des feuilles de tomate (IA) |
| **Entrepôt** | webcam USB n° 2, DHT11, MQ-135, relais + mini ventilateur 5 V, buzzer (partagé) | Conservation des tomates (température, humidité, air) → ventilateur ; sécurité incendie → e-mail Gmail avec photo + sirène |

Tout est affiché sur **Blynk**. Les modèles d'IA sont **pré-entraînés** et tournent **sur le Pi**, sans Internet.

## Organisation du code

```
main.py                    programme principal
config.yaml                seuils, broches GPIO, webcams, pins Blynk
.env                       secrets (token Blynk, Gmail) - à créer depuis .env.example
smecofarm/
  vision/                  oiseaux (EfficientDet-Lite0), maladies (MobileNetV2), flammes (couleur), webcams
  capteurs/                DHT11, MQ-135, capteurs simulés
  actionneurs/             ventilateur (relais), buzzer
  regles/                  logique conservation et incendie (testable sans matériel)
  services/                Blynk (API HTTP), e-mail Gmail, journal CSV, configuration
  stations/                champ.py, entrepot.py
  app.py                   assemblage et boucle principale
models/                    modèles TFLite (oiseaux, maladies)
docs/CABLAGE.md            câblage des capteurs ⚠️ à lire avant de brancher
docs/BLYNK.md              configuration du dashboard Blynk
deploy/smecofarm.service   démarrage automatique au boot
scripts/                   tests des modèles d'IA (image, dossier, webcam), précision, vitesse
tests/                     tests automatiques (27 tests)
```

## Fonctionnement

### Station Champ
- Une image par seconde → **détection d'oiseaux**. Si un oiseau est vu : photo enregistrée,
  compteur, **buzzer** avec un rythme aléatoire (pour limiter l'accoutumance), puis 30 s de pause.
- Toutes les 30 minutes → **analyse de maladie** sur la même image (10 classes de la tomate).
  Une maladie détectée avec assez de confiance déclenche une notification Blynk.

### Station Entrepôt : conservation (tomates mûres)

| Règle | Seuil (modifiable dans `config.yaml`) |
|---|---|
| Ventilateur en marche | température > **24 °C**, ou air anormal (MQ-135) |
| Ventilateur à l'arrêt | température < **22 °C** et air normal (hystérésis : évite les marche/arrêt incessants) |
| Alerte « dégradation rapide » | ≥ **30 °C** |
| Alerte « dommage par le froid » | ≤ **7 °C** |
| Alerte « air trop sec » | humidité ≤ **60 %** |

- **Pourquoi pas de règle « humidité trop haute » ?** Le DHT11 ne mesure qu'entre 20 et 80 % (±5 %),
  alors que l'idéal pour la tomate est 85–95 %. La règle existe mais est désactivée ; il suffit de
  l'activer avec un DHT22.
- **Limite du ventilateur :** il ne fabrique pas de froid. Il remplace l'air intérieur par l'air extérieur,
  évacue la chaleur produite par les fruits et les gaz (dont l'éthylène qui accélère le mûrissement).
  Au Maroc en été, il ne pourra pas descendre sous la température extérieure.
- Depuis Blynk, le ventilateur peut être mis en **auto / marche forcée / arrêt forcé**.

### Station Entrepôt : incendie

Trois indices sont surveillés :

1. **Flamme** vue par la webcam (couleur rouge-orangé + scintillement, sur 3 images de suite) ;
2. **Température** : montée de 5 °C en 1 minute, ou plus de 45 °C ;
3. **Fumée / gaz** : sortie DO du MQ-135.

| Niveau | Condition | Actions |
|---|---|---|
| 0 Normal | aucun indice | — |
| 1 Vigilance | 1 indice (peut être une fausse alerte) | affiché sur Blynk, photo enregistrée |
| 2 **Alerte** | ≥ 2 indices | **e-mail Gmail avec photo**, notification Blynk, **sirène**, **ventilateur coupé** (il attiserait le feu) |

L'alerte reste active jusqu'au **réarmement** par le bouton Blynk (V11). Un seul e-mail toutes les 10 minutes au maximum.

### MQ-135 sans ADS1115

Le Raspberry Pi n'a pas d'entrée analogique : il ne sait lire que 0 ou 1. La sortie AO du MQ-135
donne une tension variable, illisible directement ; il faudrait un petit convertisseur **ADS1115**
(environ 3 €) pour obtenir une vraie mesure. On utilise donc la sortie **DO**, qui passe à 1 quand
le gaz dépasse un seuil réglé avec le potentiomètre du module : on sait si l'air est **normal ou
anormal**, sans valeur précise. C'est suffisant pour le prototype ; l'ADS1115 est une amélioration future.

## Installation sur le Raspberry Pi 4

Câbler d'abord selon [docs/CABLAGE.md](docs/CABLAGE.md). Puis, dans un terminal du Pi :

```bash
git clone https://github.com/mysteriodataweb/SmEcoFarm.git
cd SmEcoFarm
bash install.sh
cp .env.example .env
nano .env
```

`install.sh` détecte le système (32 ou 64 bits), installe les paquets nécessaires, crée l'environnement
Python `.venv`, choisit le moteur d'IA adapté (`ai-edge-litert` en 64 bits, `tflite-runtime` sinon)
et lance les tests. Si aucun moteur n'est disponible, il l'indique : il faut alors installer
**Raspberry Pi OS (64-bit)** avec Raspberry Pi Imager.

Dans `config.yaml`, vérifier les numéros des webcams (`champ.camera`, `entrepot.camera`) :
`v4l2-ctl --list-devices` les affiche.

### Gmail : mot de passe d'application

1. Sur le compte Google qui envoie les alertes : activer la **validation en deux étapes**.
2. Aller sur <https://myaccount.google.com/apppasswords>, créer un mot de passe nommé « SmEcoFarm ».
3. Copier les 16 lettres dans `.env` :

```
GMAIL_USER=adresse.envoi@gmail.com
GMAIL_APP_PASSWORD=abcdefghijklmnop
EMAIL_TO=destinataire@gmail.com
```

### Blynk

Voir [docs/BLYNK.md](docs/BLYNK.md) : datastreams V0 à V12, événements `incendie`, `conservation`,
`maladie`, widgets conseillés.

## Lancement

```bash
source .venv/bin/activate

# Tests automatiques (sans matériel)
python -m pytest tests/

# Simulation sans capteurs (fonctionne aussi sur PC) : normal | chaleur | incendie
python main.py --simulation incendie --duree 90
python main.py --simulation chaleur --duree 180

# Avec le vrai matériel
python main.py                      # champ + entrepôt
python main.py --station entrepot   # une seule station

# Démarrage automatique au boot
sudo cp deploy/smecofarm.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now smecofarm
journalctl -u smecofarm -f          # voir les messages
```

En simulation, si `.env` est rempli, Blynk et l'e-mail fonctionnent vraiment : pratique pour
tester le dashboard et la réception de l'e-mail avant de câbler les capteurs.

Les données sont enregistrées dans `data/` : un fichier CSV par jour (une ligne par minute,
s'ouvre dans Excel), les photos d'événements dans `data/photos/` et le journal `smecofarm.log`.

## Démonstration sans danger

| Test | Comment |
|---|---|
| Oiseau | Photo réaliste d'oiseau (imprimée ou sur téléphone) devant la webcam du champ |
| Maladie | Image de `test_images/tomato/` devant la webcam (gros plan, bien éclairée) |
| Chaleur | Souffler de l'air chaud (sèche-cheveux à distance) sur le DHT11 → ventilateur |
| Air anormal | Allumette qu'on vient d'éteindre près du MQ-135 → ventilateur |
| Incendie | **Vidéo de flammes** sur un téléphone devant la webcam de l'entrepôt **+** fumée d'allumette sur le MQ-135 → alerte, e-mail, sirène |

⚠️ Ne pas faire de vrai feu près du montage.

## Les modèles d'IA

### Oiseaux : EfficientDet-Lite0
- Exemple officiel TensorFlow Lite pour Raspberry Pi (Google), entraîné sur COCO (90 classes dont `bird`), quantifié int8, 4,6 Mo.
- Entrée 320×320 RGB. On garde la classe `bird` avec un seuil de 0,5.
- Test : l'aigle est détecté à 84 %, aucune fausse détection sur 6 photos sans oiseau.

### Maladies : MobileNetV2 + PlantVillage
- Projet [obeshor/Plant-Diseases-Detector](https://github.com/obeshor/Plant-Diseases-Detector) (licence Apache 2.0), 38 classes, 11,6 Mo.
- Entrée 224×224 RGB, pixels / 255. Restreint aux **10 classes de la tomate**, probabilités renormalisées ;
  sous 60 % de confiance, le résultat est « incertain ».
- Test : **87/100** feuilles de tomate PlantVillage bien classées (`python scripts/evaluate_disease.py`).
  Chiffre optimiste : images de laboratoire, probablement vues à l'entraînement. Sur de vraies photos de jardin,
  la précision sera plus faible. Le chou et le persil ne sont pas couverts (il faudrait un entraînement).

### Flammes : règle de couleur (sans IA)
- Pixels rouge-orangé lumineux et saturés (R > 180, R ≥ G > B), zone qui **scintille** d'une image à l'autre,
  confirmée sur 3 images de suite. Un objet orange immobile n'est pas pris pour une flamme.
- Des reflets ou une lampe orange qui bouge peuvent tromper la caméra : c'est pourquoi l'alerte demande **2 indices**.

### Tester les modèles seuls

```bash
python scripts/test_models.py --dir test_images/birds --model bird
python scripts/test_models.py --image test_images/tomato/tomato_late_blight/tomato_late_blight_01.jpg --model disease
python scripts/test_models.py --camera --camera-index 0
python scripts/evaluate_disease.py
python scripts/benchmark.py        # vitesse sur le Pi
```

## Améliorations futures

- **DHT22** (5 €) à la place du DHT11 : mesure jusqu'à 100 % d'humidité → activer la règle « humidité > 95 % ».
- **ADS1115** pour lire la valeur analogique du MQ-135 (vraie courbe, détection de montée rapide).
- **2ᵉ capteur de température à l'extérieur** : ne ventiler que si l'air extérieur est plus frais.
- **Capteur de flamme infrarouge** (2 €) : 4ᵉ indice incendie, très fiable de près.
- Modèle d'IA dédié feu/fumée, entraînement sur le chou et le persil.

## Provenance des images de test

- `test_images/birds/` : images d'exemple du projet Darknet/YOLO (pjreddie/darknet, dossier `data/`).
- `test_images/tomato/` : échantillon du jeu PlantVillage (spMohanty/PlantVillage-Dataset, `raw/color`),
  10 images par classe tirées au hasard. Voir les dépôts d'origine pour leurs licences.

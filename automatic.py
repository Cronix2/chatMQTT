import paho.mqtt.client as mqtt
import threading
import time
from datetime import datetime, timedelta

# Configuration
BROKER = "20.107.241.46"  # IP de la VM Azure
TOPIC = "iot/healthcheck"  # Topic unique pour l'échange
TIMEOUT = 90  # Temps max d'attente d'un message avant alerte

last_received_time = None

# Déterminer si l'on est IoT ou VM
role = input("Entrez votre rôle (iot/vm) : ").strip().lower()
if role not in ["iot", "vm"]:
    print("Rôle invalide. Utilisez 'iot' ou 'vm'.")
    exit()

def on_connect(client, userdata, flags, rc, properties=None):
    """Gère la connexion au broker MQTT."""
    if rc == 0:
        print(f"✅ [{role.upper()}] Connecté au broker MQTT !")
        client.subscribe(TOPIC)
    else:
        print(f"⚠️ [{role.upper()}] Erreur de connexion, code {rc}")

def on_message(client, userdata, msg):
    """Gère la réception des messages."""
    global last_received_time

    received_msg = msg.payload.decode()
    print(f"\n📩 {received_msg}")

    # Mise à jour du dernier message reçu
    last_received_time = time.time()

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, 1883, 60)

# Lancer le listener MQTT en arrière-plan
threading.Thread(target=client.loop_forever, daemon=True).start()

# Boucle principale pour envoyer un message à la bonne minute
while True:
    now = datetime.now()
    minute = now.minute

    if (role == "iot" and minute % 2 == 1) or (role == "vm" and minute % 2 == 0):  
        # Création du message avec identifiant
        if role == "iot":
            msg = f"[from: iot] [{now.strftime('%d/%m/%Y %H:%M')}]"
        else:  # VM
            next_minute = (now + timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M')
            msg = f"[from: vm] [{now.strftime('%d/%m/%Y %H:%M')}] : OK / [{next_minute}]"

        # Envoi du message
        client.publish(TOPIC, msg)
        print(f"📤 {msg}")

    # Vérification si un message est manquant
    if last_received_time:
        elapsed_time = time.time() - last_received_time
        if elapsed_time > TIMEOUT:
            print(f"🚨 [{role.upper()}] Problème détecté à {now.strftime('%d/%m/%Y %H:%M')} ! Communication arrêtée.")
            break

    # Attendre 10 secondes avant de revérifier
    time.sleep(10)

import paho.mqtt.client as mqtt
import threading
import time
from datetime import datetime

BROKER = "20.107.241.46"  # IP de la VM Azure
TOPIC = "iot/healthcheck"  # Topic unique pour l'échange
TIMEOUT = 70  # Temps max d'attente d'un message (secondes)

last_received_time = None
waiting_for_response = False

# Déterminer si l'on est l'IoT ou la VM
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
    """Réception et réponse automatique aux messages."""
    global last_received_time, waiting_for_response

    received_msg = msg.payload.decode()
    print(f"\n📩 [{role.upper()}] Message reçu : {received_msg}")

    # Mise à jour du temps de dernier message reçu
    last_received_time = time.time()
    
    if role == "vm":  # La VM répond à l'IoT
        response = f"{received_msg} : OK / [{datetime.now().strftime('%d/%m/%Y %H:%M')}]"
        client.publish(TOPIC, response)
        print(f"📤 [{role.upper()}] Réponse envoyée : {response}")

    elif role == "iot":  # L'IoT répond à la VM
        if "OK" in received_msg:  # Vérifie que la VM a bien répondu
            time.sleep(60)  # Attendre 1 minute
            response = f"[{datetime.now().strftime('%d/%m/%Y %H:%M')}]"
            client.publish(TOPIC, response)
            print(f"📤 [{role.upper()}] Nouveau check envoyé : {response}")
            waiting_for_response = True

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, 1883, 60)

# Lancer le listener MQTT en arrière-plan
threading.Thread(target=client.loop_forever, daemon=True).start()

# Si c'est l'IoT, il doit initier le premier message
if role == "iot":
    time.sleep(5)  # Petite pause avant d'envoyer le premier message
    initial_msg = f"[{datetime.now().strftime('%d/%m/%Y %H:%M')}]"
    client.publish(TOPIC, initial_msg)
    print(f"📤 [{role.upper()}] Premier message envoyé : {initial_msg}")
    waiting_for_response = True

# Vérification continue de l’état des échanges
while True:
    if waiting_for_response and last_received_time:
        elapsed_time = time.time() - last_received_time
        if elapsed_time > TIMEOUT:
            print(f"🚨 [{role.upper()}] Problème détecté à {datetime.now().strftime('%d/%m/%Y %H:%M')} ! Communication arrêtée.")
            break
    time.sleep(5)  # Vérification toutes les 5 secondes

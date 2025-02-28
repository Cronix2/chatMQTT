import paho.mqtt.client as mqtt
import threading
import time
from datetime import datetime, timedelta, timezone

# Configuration
BROKER = "20.107.241.46"  # IP de la VM Azure
TOPIC = "iot/healthcheck"
TIMEOUT = 90  # Temps max avant alerte
last_received_time = None
last_received_message = None
last_sent_minute = None  # Pour éviter les envois multiples

# Déterminer si on est IoT ou VM
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
    global last_received_time, last_received_message

    received_msg = msg.payload.decode()

    # Ignorer les messages envoyés par soi-même
    if f"[from: {role}]" in received_msg:
        return

    last_received_time = time.time()
    last_received_message = received_msg

    print(f"\n📩 {received_msg}")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, 1883, 60)

# Lancer le listener MQTT en arrière-plan
threading.Thread(target=client.loop_forever, daemon=True).start()

# Boucle principale
while True:
    now = datetime.now(timezone.utc)  # Utiliser un datetime UTC valide
    minute = now.minute

    # Vérifier si on a déjà envoyé un message cette minute
    if last_sent_minute == minute:
        time.sleep(10)
        continue

    # Vérifier qu'on a bien reçu un message de l'autre machine avant d'envoyer le sien
    expected_sender = "iot" if role == "vm" else "vm"
    if last_received_message and expected_sender not in last_received_message:
        print(f"🚨 [{role.upper()}] Problème détecté : Dernier message reçu non conforme.")
        break

    # IoT envoie aux minutes impaires, VM aux minutes paires
    if (role == "iot" and minute % 2 == 1) or (role == "vm" and minute % 2 == 0):
        if role == "iot":
            msg = f"[from: iot] [{now.strftime('%d/%m/%Y %H:%M')}]"
        else:  # VM
            next_minute = (now + timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M')
            msg = f"[from: vm] [{now.strftime('%d/%m/%Y %H:%M')}] : OK / [{next_minute}]"

        client.publish(TOPIC, msg)
        print(f"📤 {msg}")
        last_sent_minute = minute  # Mémoriser la dernière minute d'envoi

    # Vérification si un message est manquant
    if last_received_time:
        elapsed_time = time.time() - last_received_time
        if elapsed_time > TIMEOUT:
            print(f"🚨 [{role.upper()}] Problème détecté à {now.strftime('%d/%m/%Y %H:%M')} ! Communication arrêtée.")
            break

    # Attente de 10 secondes avant de vérifier à nouveau
    time.sleep(10)

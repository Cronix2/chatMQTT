import paho.mqtt.client as mqtt
import threading
import time
from datetime import datetime, timedelta, timezone
import os
import requests
from dotenv import load_dotenv

# Configuration
BROKER = "20.107.241.46"  # IP de la VM Azure
TOPIC = "iot/healthcheck"
received_messages = []
last_received_time = None
last_received_message = None
last_sent_minute = None  # Pour éviter les envois multiples
load_dotenv()
DiscordWebhook = os.getenv("WEBHOOK")
PORT = os.getenv("PORT")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
CERT_PATH = os.getenv("CERT_PATH")


# Déterminer si on est IoT ou VM
role = input("Entrez votre rôle (iot/vm) : ").strip().lower()
if role not in ["iot", "vm"]:
    print("Rôle invalide. Utilisez 'iot' ou 'vm'.")
    exit()

def send_discord_alert(message):
    """Envoie une alerte sur un canal Discord via un webhook."""
    if not DiscordWebhook:
        print("⚠️ Erreur : Webhook Discord non défini dans le fichier .env")
        return

    data = {"content": message, "username": "MQTT Healthchecker"}

    response = requests.post(DiscordWebhook, json=data)

    if response.status_code == 204:
        print("✅ Alerte envoyée sur Discord avec succès !")
    else:
        print(f"⚠️ Erreur lors de l'envoi sur Discord : {response.status_code} - {response.text}")

def log_message(message):
    with open("mqtt_healthcheck.log", "a") as log_file:
        log_file.write(f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} - {message}\n")

def on_connect(client, userdata, flags, rc, properties=None):
    """Gère la connexion au broker MQTT."""
    if rc == 0:
        print(f"✅ [{role.upper()}] Connecté au broker MQTT !\n\n")
        client.subscribe(TOPIC)
    else:
        print(f"⚠️ [{role.upper()}] Erreur de connexion, code {rc}")

def obtain_sender(msg):
    """Obtenir l'expéditeur du message."""
    return "iot" if "[from: iot]" in msg else "vm"


def on_message(client, userdata, msg):
    """Gère la réception des messages."""
    global last_received_time, last_received_message

    received_msg = msg.payload.decode()

    # Ignorer les messages envoyés par soi-même
    if f"[from: {role}]" in received_msg:
        return

    last_received_time = time.time()
    last_received_message = received_msg
    received_messages.append(obtain_sender(received_msg))

    print(f"📩 {received_msg}")
    log_message(f"RECEIVED: {received_msg}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(USERNAME, PASSWORD)
client.tls_set(CERT_PATH)
client.on_connect = on_connect
client.on_message = on_message

client.connect(BROKER, PORT, 60)

# Lancer le listener MQTT en arrière-plan
threading.Thread(target=client.loop_forever, daemon=True).start()

print(f"🚀 [{role.upper()}] Démarrage du script...")
if role == "iot":
    print("🔵 IoT envoie aux minutes impaires.")
else:
    print("🔴 VM envoie aux minutes paires.")

if role == "iot" and datetime.now().minute % 2 == 0:
    print("⚠️ [IoT] Minute actuelle paire, attendez la prochaine minute impaire pour envoyer.")
    while datetime.now().minute % 2 == 0:
        time.sleep(1)
elif role == "iot" and datetime.now().minute % 2 == 1:
    print("⚠️ [IoT] Minute actuelle impaire, attendez la prochaine minute impaire pour envoyer.")
    time.sleep(60)
    while datetime.now().minute % 2 == 0:
        time.sleep(1)
elif role == "vm":
    # Attendre le premier message de l'IoT
    while not last_received_message:
        time.sleep(1)

boucle = 0

# Boucle principale
while True:
    now = datetime.now(timezone.utc)
    minute = now.minute

    # Vérifier si on a déjà envoyé un message cette minute
    if last_sent_minute == minute:
        time.sleep(1)
        continue

    if role == "iot" and minute % 2 == 1 and boucle == 0:
        msg = f"[from: iot] [{now.strftime('%d/%m/%Y %H:%M')}]"
        client.publish(TOPIC, msg)

    # Vérifier qu'on a bien reçu le message de l'autre machine avant d'envoyer
    expected_sender = "iot" if role == "vm" else "vm"
    if last_received_message:
        if expected_sender not in last_received_message:
            print(f"\n🚨 [{role.upper()}] Problème détecté : Dernier message reçu non conforme.")
            break

    # IoT envoie aux minutes impaires, VM aux minutes paires
    if (role == "iot" and minute % 2 == 1) or (role == "vm" and minute % 2 == 0):
        if last_received_time:
            elapsed_time = time.time() - last_received_time
            if elapsed_time < 30:  # S'assurer d'avoir bien reçu le message avant d'envoyer le sien
                print(f"⏳ [{role.upper()}] En attente de confirmation de l'autre machine...")
                time.sleep(1)
                continue

        if role == "iot":
            prev_minute = (now - timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M')
            msg = f"[from: iot] [{prev_minute}] : OK / [{now.strftime('%d/%m/%Y %H:%M')}]"
        else:  # VM
            prev_minute = (now - timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M')
            msg = f"[from: vm] [{prev_minute}] : OK / [{now.strftime('%d/%m/%Y %H:%M')}]"

        client.publish(TOPIC, msg)
        print(f"📤 {msg}")
        log_message(f"SENT: {msg}")
        received_messages.append(obtain_sender(msg))
        last_sent_minute = minute  # Mémoriser la dernière minute d'envoi

    # Vérification si un message est manquant
    # si on envoie deux messages consécutifs sans réponse de l'autre machine
    if len(received_messages) > 2 and received_messages[-1] == received_messages[-2]:
        alert_message = f"🚨 **[{role.upper()}] Problème détecté !**\n📅 {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S UTC')}\n❌ Message non reçu."
        print(alert_message)
        send_discord_alert(alert_message)
        log_message(f"ERROR: Message manquant.")
        break

    if len(received_messages)>5:
        # Si on a reçu plus de 5 messages, on supprime les plus anciens
        received_messages.pop(0)

    # Attente de 1 seconde avant de vérifier à nouveau
    boucle += 1
    time.sleep(1)

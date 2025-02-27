import paho.mqtt.client as mqtt
import threading

# Configuration
BROKER = "20.107.241.46"  # IP de la VM Azure
TOPIC_SEND = "iot/chat"  # Topic unique pour tout le monde
TOPIC_RECEIVE = "iot/chat"  # On écoute et envoie sur le même topic

# Demander un pseudo pour identifier les messages
username = input("Entrez votre pseudo : ")

def on_connect(client, userdata, flags, rc, properties=None):
    """Gère la connexion au broker MQTT."""
    if rc == 0:
        print("✅ Connecté au broker MQTT !")
        client.subscribe(TOPIC_RECEIVE)  # S'abonner au topic général
    else:
        print(f"⚠️ Erreur de connexion, code {rc}")

def on_message(client, userdata, msg):
    """Affiche les messages reçus, sauf ceux envoyés par soi-même."""
    decoded_msg = msg.payload.decode()
    if not decoded_msg.startswith(f"[{username}]"):  # Éviter de réafficher ses propres messages
        print(f"\n📩 {decoded_msg}\n> ", end="")

# Configuration du client MQTT
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)  # Correction de l’alerte de version
client.on_connect = on_connect
client.on_message = on_message

# Connexion au broker
client.connect(BROKER, 1883, 60)

# Lancer la réception des messages en parallèle
threading.Thread(target=client.loop_forever, daemon=True).start()

# Boucle principale pour envoyer des messages
while True:
    message = input("> ")
    if message.strip():  # Éviter d'envoyer des messages vides
        full_message = f"[{username}] {message}"
        client.publish(TOPIC_SEND, full_message)

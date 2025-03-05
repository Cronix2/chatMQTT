import subprocess
import threading
import time
import os
import requests
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from aiocoap import Context, resource, Message
import logging

# Configurer les variables globales
global error
error = 0

# Configurer les logs
logging.basicConfig(level=logging.INFO)

# Charger les variables d'environnement
load_dotenv()
DiscordWebhook = os.getenv("WEBHOOK")

# Configuration
COAP_SERVER = "coap://20.107.241.46:5683"  # Adresse du serveur CoAP
RESOURCE = "healthcheck"
received_messages = []
last_received_time = None
last_received_message = None
last_sent_minute = None  # Éviter les envois multiples
error = 0

# Déterminer si on est IoT ou VM
role = input("Entrez votre rôle (iot/vm) : ").strip().lower()
if role not in ["iot", "vm"]:
    print("Rôle invalide. Utilisez 'iot' ou 'vm'.")
    exit()

class HealthCheckResource(resource.Resource):
    """Ressource CoAP pour gérer les requêtes GET et POST sur /healthcheck"""
    
    def __init__(self):
        super().__init__()
        self.latest_message = "Aucun message reçu"

    async def render_get(self, request):
        """Gérer les requêtes GET"""
        print(f"📥 [GET] Reçu - Dernier message stocké : {self.latest_message}")
        return Message(payload=self.latest_message.encode('utf-8'))

    async def render_post(self, request):
        """Gérer les requêtes POST"""
        self.latest_message = request.payload.decode('utf-8')
        print(f"📩 [POST] Nouveau message reçu et enregistré : {self.latest_message}")
        return Message(payload=b"Message enregistré")

async def run_coap_server():
    """Lancer le serveur CoAP"""
    root = resource.Site()
    root.add_resource([RESOURCE], HealthCheckResource())
    await Context.create_server_context(root, bind=('::', 5683))
    print("✅ Serveur CoAP en écoute sur le port 5683...")
    await asyncio.get_running_loop().create_future()

def start_coap_server():
    """Démarrer le serveur CoAP en arrière-plan si le rôle est 'vm'"""
    if role == "vm":
        print("🟢 [VM] Démarrage du serveur CoAP...")
        threading.Thread(target=lambda: asyncio.run(run_coap_server()), daemon=True).start()

if role == "vm":
    start_coap_server()

def send_discord_alert(message):
    """Envoie une alerte sur un canal Discord via un webhook."""
    if not DiscordWebhook:
        print("⚠️ Webhook Discord non défini dans le fichier .env")
        return
    

    data = {"content": message, "username": "CoAP Healthchecker"}
    response = requests.post(DiscordWebhook, json=data)
    
    if response.status_code == 204:
        print("✅ Alerte envoyée sur Discord avec succès !")
    else:
        print(f"⚠️ Erreur lors de l'envoi sur Discord : {response.status_code} - {response.text}")

def coap_get():
    """Effectue une requête GET sur le serveur CoAP."""
    global error
    try:
        cmd = ["coap-client", "-m", "get", f"{COAP_SERVER}/{RESOURCE}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            response = result.stdout.strip()
            print(f"🔹 [DEBUG] Réponse GET reçue : {response}")  # <-- Ajout pour voir la réponse
            return response
        else:
            print(f"⚠️ Erreur GET : {result.stderr}")
            return None
    except Exception as e:
        print(f"⚠️ Exception GET : {e}")
        if error > 10:
            print("🚨 Trop d'erreurs GET, arrêt du script.")
            send_discord_alert("🚨 **Trop d'erreurs GET, arrêt du script.**")
            if role == "vm":
                print("🔴 [VM] Arrêt du serveur CoAP...")
                subprocess.run(["pkill", "coap-server"])
            exit()
        error += 1
        return None

def coap_post(payload):
    """Envoie une requête POST sur le serveur CoAP."""
    try:
        cmd = ["coap-client", "-m", "post", "-e", payload, f"{COAP_SERVER}/{RESOURCE}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"⚠️ Erreur POST : {result.stderr}")
            return None
    except Exception as e:
        print(f"⚠️ Exception POST : {e}")
        return None

# Lancement du script
print(f"🚀 [{role.upper()}] Démarrage du script...")

if role == "iot":
    print("🔵 IoT envoie aux minutes impaires.")
else:
    print("🔴 VM envoie aux minutes paires.")

# Vérification du timing initial
if role == "iot" and datetime.now().minute % 2 == 0:
    print("⚠️ [IoT] Minute actuelle paire, attente prochaine minute impaire.")
    while datetime.now().minute % 2 == 0:
        time.sleep(1)
elif role == "iot" and datetime.now().minute % 2 == 1:
    print("⚠️ [IoT] Minute actuelle impaire, attente prochaine minute impaire.")
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
    
    if role == "iot" and minute % 2 == 1:
        msg = f"[from: iot] [{now.strftime('%d/%m/%Y %H:%M')}]"
        coap_post(msg)
    
    last_received_message = coap_get()
        expected_sender = "iot" if role == "vm" else "vm"
    print(f"🔹 [DEBUG] Message attendu contenant : '{expected_sender}', Message reçu : '{last_received_message}'")
    if last_received_message and expected_sender not in last_received_message:
        print(f"\n🚨 [{role.upper()}] Problème détecté : Dernier message reçu non conforme.")
        send_discord_alert(f"🚨 **[{role.upper()}] Problème détecté !**\n📅 {now.strftime('%d/%m/%Y %H:%M:%S UTC')}\n❌ Message non reçu.")
        break
    
    if (role == "iot" and minute % 2 == 1) or (role == "vm" and minute % 2 == 0):
        prev_minute = (now - timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M')
        msg = f"[from: {role}] [{prev_minute}] : OK / [{now.strftime('%d/%m/%Y %H:%M')}]"
        coap_post(msg)
        print(f"📤 {msg}")
        error = 0
        last_sent_minute = minute
    
    time.sleep(1)

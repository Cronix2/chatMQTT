import subprocess
import threading
import time
import os
import requests
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from aiocoap import Context, Message
from aiocoap.resource import Resource, Site
import logging

# Configurer les logs
logging.basicConfig(level=logging.INFO)

# Charger les variables globales
global error
error = 0

# Charger les variables d'environnement
load_dotenv()
DiscordWebhook = os.getenv("WEBHOOK")

# Configuration
COAP_SERVER = "coap://20.107.241.46:5683"  # Adresse du serveur CoAP
RESOURCE = "healthcheck"
received_messages = []
last_received_time = None
last_received_message = None
last_sent_minute = None

# Déterminer si on est IoT ou VM
role = input("Entrez votre rôle (iot/vm) : ").strip().lower()
if role not in ["iot", "vm"]:
    print("Rôle invalide. Utilisez 'iot' ou 'vm'.")
    exit()

class HealthCheckResource(Resource):
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
        global last_received_message
        self.latest_message = "vm : " + request.payload.decode('utf-8')
        last_received_message = self.latest_message
        print(f"📩 [POST] Nouveau message reçu et enregistré : {self.latest_message}")
        return Message(payload=b"Message enregistre")

async def run_coap_server():
    """Lancer le serveur CoAP"""
    root = Site()
    root.add_resource([RESOURCE], HealthCheckResource())
    await Context.create_server_context(root, bind=('::', 5683))
    print("✅ Serveur CoAP en écoute sur le port 5683...")
    await asyncio.get_running_loop().create_future()

def start_coap_server():
    """Démarrer le serveur CoAP en arrière-plan si le rôle est 'vm'"""
    if role == "vm":
        print("🟢 [VM] Démarrage du serveur CoAP...")
        loop = asyncio.new_event_loop()
        threading.Thread(target=lambda: loop.run_until_complete(run_coap_server()), daemon=True).start()

if role == "vm":
    start_coap_server()

def coap_get():
    """Effectue une requête GET sur le serveur CoAP."""
    global error
    try:
        cmd = ["coap-client", "-m", "get", f"{COAP_SERVER}/{RESOURCE}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            response = result.stdout.strip()
            print(f"🔹 [DEBUG] Réponse GET reçue : {response}")
            return response
        else:
            print(f"⚠️ Erreur GET : {result.stderr}")
            return None
    except Exception as e:
        print(f"⚠️ Exception GET : {e}")
        error += 1
        if error > 10:
            print("🚨 Trop d'erreurs GET, arrêt du script.")
            exit()
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

print(f"🚀 [{role.upper()}] Démarrage du script...")
if role == "iot":
    print("🔵 IoT envoie aux minutes impaires.")
else:
    print("🔴 VM envoie aux minutes paires.")

# Boucle principale
while True:
    now = datetime.now(timezone.utc)
    minute = now.minute

    if role == "vm":
        last_received_message = coap_get()
        if last_received_message and "iot" in last_received_message:
            msg = f"[from: vm] [{now.strftime('%d/%m/%Y %H:%M')}]"
            coap_post(msg)
            print(f"📤 [VM] Réponse envoyée : {msg}")

    expected_sender = "iot" if role == "vm" else "vm"
    print(f"🔹 [DEBUG] Message attendu : '{expected_sender}', Message reçu : '{last_received_message}'")

    time.sleep(1)

import subprocess
import threading
import time
import os
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

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

# Déterminer si on est IoT ou VM
role = input("Entrez votre rôle (iot/vm) : ").strip().lower()
if role not in ["iot", "vm"]:
    print("Rôle invalide. Utilisez 'iot' ou 'vm'.")
    exit()

def start_coap_server():
    """Démarre le serveur CoAP en arrière-plan si le rôle est 'vm'."""
    try:
        print("🟢 [VM] Démarrage du serveur CoAP...")
        server_process = subprocess.Popen(["coap-server", "-v", "7"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for line in server_process.stdout:
            print(f"🔹 {line.decode().strip()}")
    except Exception as e:
        print(f"⚠️ Erreur lors du lancement du serveur CoAP : {e}")

if role == "vm":
    # Lancer le serveur CoAP dans un thread séparé
    threading.Thread(target=start_coap_server, daemon=True).start()

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

def log_message(message):
    """Enregistre les logs."""
    with open("coap_healthcheck.log", "a") as log_file:
        log_file.write(f"{datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M:%S')} - {message}\n")

def coap_get():
    """Effectue une requête GET sur le serveur CoAP."""
    error = 0
    try:
        cmd = ["coap-client", "-m", "get", f"{COAP_SERVER}/{RESOURCE}"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
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

    # IoT envoie aux minutes impaires
    if role == "iot" and minute % 2 == 1 and boucle == 0:
        msg = f"[from: iot] [{now.strftime('%d/%m/%Y %H:%M')}]"
        coap_post(msg)

    # Vérifier qu'on a bien reçu le message de l'autre machine avant d'envoyer
    expected_sender = "iot" if role == "vm" else "vm"
    last_received_message = coap_get()
    if last_received_message and expected_sender not in last_received_message:
        print(f"\n🚨 [{role.upper()}] Problème détecté : Dernier message reçu non conforme.")
        send_discord_alert(f"🚨 **[{role.upper()}] Problème détecté !**\n📅 {now.strftime('%d/%m/%Y %H:%M:%S UTC')}\n❌ Message non reçu.")
        break

    # IoT envoie aux minutes impaires, VM aux minutes paires
    if (role == "iot" and minute % 2 == 1) or (role == "vm" and minute % 2 == 0):
        if last_received_time:
            elapsed_time = time.time() - last_received_time
            if elapsed_time < 30:
                print(f"⏳ [{role.upper()}] En attente de confirmation de l'autre machine...")
                time.sleep(1)
                continue

        if role == "iot":
            prev_minute = (now - timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M')
            msg = f"[from: iot] [{prev_minute}] : OK / [{now.strftime('%d/%m/%Y %H:%M')}]"
        else:
            prev_minute = (now - timedelta(minutes=1)).strftime('%d/%m/%Y %H:%M')
            msg = f"[from: vm] [{prev_minute}] : OK / [{now.strftime('%d/%m/%Y %H:%M')}]"

        coap_post(msg)
        print(f"📤 {msg}")
        log_message(f"SENT: {msg}")
        received_messages.append(msg)
        last_sent_minute = minute

    # Vérification de l'absence de réponse
    if len(received_messages) > 2 and received_messages[-1] == received_messages[-2]:
        alert_message = f"🚨 **[{role.upper()}] Problème détecté !**\n📅 {now.strftime('%d/%m/%Y %H:%M:%S UTC')}\n❌ Message non reçu."
        print(alert_message)
        send_discord_alert(alert_message)
        log_message(f"ERROR: Message manquant.")
        break

    # Limitation des logs
    if len(received_messages) > 5:
        received_messages.pop(0)

    # Pause avant la prochaine itération
    boucle += 1
    time.sleep(1)

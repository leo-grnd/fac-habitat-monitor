#!/bin/bash

# Cron n'hérite pas des variables d'environnement Docker,
# donc on les écrit dans un fichier .env que run.sh sourcera
env | grep -E "^(SMTP_|EMAIL_)" > /app/.env

echo "[$(date)] Moniteur Fac-Habitat démarré. Cron toutes les 2h."
echo "[$(date)] Premier check immédiat..."

# Premier run au démarrage du conteneur
/app/run.sh

echo "[$(date)] Cron actif. Logs :"
# Lancer cron en foreground + tail les logs
cron
tail -f /app/data/cron.log /app/data/monitor.log 2>/dev/null

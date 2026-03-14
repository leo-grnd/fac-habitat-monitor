FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py .

# Cron toutes les 2h
RUN apt-get update && apt-get install -y --no-install-recommends cron && \
    rm -rf /var/lib/apt/lists/*

# Le script cron qui injecte les variables d'env
RUN echo '#!/bin/bash\n\
set -a\n\
source /app/.env\n\
set +a\n\
cd /app\n\
mkdir -p /app/data\n\
python3 /app/monitor.py >> /app/data/cron.log 2>&1' > /app/run.sh && \
    chmod +x /app/run.sh

# Crontab : toutes les 2h
RUN echo "0 */2 * * * /app/run.sh" > /etc/cron.d/monitor && \
    chmod 0644 /etc/cron.d/monitor && \
    crontab /etc/cron.d/monitor

# Entrypoint : écrit le .env depuis les variables Docker, lance cron en foreground
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

CMD ["/app/entrypoint.sh"]

#!/usr/bin/env python3
"""
Moniteur de disponibilité — Résidence Saint-Jérôme (Fac-Habitat)
Vérifie toutes les 2h si le statut change et envoie un mail d'alerte.

Déploiement : cron job sur un serveur Linux (ex: Hostinger KVM).
"""

import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# ─── Configuration ───────────────────────────────────────────────
URL = "https://www.fac-habitat.com/fr/residences-etudiantes/id-127-saint-jerome"
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / ".last_status"

# Email (Gmail SMTP) — utiliser un "Mot de passe d'application" Google
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")       # ton.email@gmail.com
SMTP_PASS = os.environ.get("SMTP_PASS", "")       # mot de passe d'application
EMAIL_TO   = os.environ.get("EMAIL_TO", "")        # adresse de destination

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# ─── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "monitor.log"),
    ],
)
log = logging.getLogger(__name__)


def fetch_availability() -> dict:
    """
    Scrape la page et retourne un dict par type de logement :
    { "T1": { "loyer": "...", "surface": "...", "meuble": True/False, "statut": "..." } }
    """
    resp = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    # Le tableau de réservation contient les infos de dispo
    # On cherche toutes les lignes <tr> dans le tableau principal
    results = {}

    # Chercher le tableau qui contient "Déposer un dossier"
    tables = soup.find_all("table")
    target_table = None
    for table in tables:
        if "poser un dossier" in table.get_text():
            target_table = table
            break

    if not target_table:
        # Fallback : chercher directement le texte de disponibilité
        page_text = soup.get_text()
        if "Aucune disponibilité" in page_text:
            results["general"] = {"statut": "Aucune disponibilité"}
        elif "Réserver" in page_text:
            results["general"] = {"statut": "Disponible"}
        else:
            results["general"] = {"statut": "Inconnu"}
        return results

    rows = target_table.find_all("tr")[1:]  # skip header
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 5:
            continue

        type_log = cells[0].get_text(strip=True)
        loyer = cells[1].get_text(strip=True)
        surface = cells[2].get_text(strip=True)
        meuble = bool(cells[3].find("img") or "✓" in cells[3].get_text())
        statut_cell = cells[4]

        # Le statut peut être "Aucune disponibilité" ou un lien "Réserver"
        link = statut_cell.find("a")
        if link:
            statut = "Disponible — " + link.get_text(strip=True)
        else:
            statut = statut_cell.get_text(strip=True)

        results[type_log] = {
            "loyer": loyer,
            "surface": surface,
            "meuble": meuble,
            "statut": statut,
        }

    return results


def load_previous_status() -> str | None:
    """Charge le dernier statut sauvegardé."""
    if STATE_FILE.exists():
        return STATE_FILE.read_text(encoding="utf-8").strip()
    return None


def save_status(status_str: str):
    """Sauvegarde le statut actuel."""
    STATE_FILE.write_text(status_str, encoding="utf-8")


def format_status(results: dict) -> str:
    """Transforme le dict en string lisible pour comparaison et affichage."""
    lines = []
    for type_log, info in sorted(results.items()):
        lines.append(f"{type_log}: {info['statut']}")
    return "\n".join(lines)


def send_email(subject: str, body: str):
    """Envoie un email via SMTP."""
    if not all([SMTP_USER, SMTP_PASS, EMAIL_TO]):
        log.error("Variables SMTP non configurées. Email non envoyé.")
        log.info(f"Contenu de l'alerte :\n{body}")
        return

    msg = MIMEMultipart()
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #2ecc71;">🏠 Changement de disponibilité détecté !</h2>
        <p><strong>Résidence :</strong> Saint-Jérôme — 47 rue Saint-Jérôme, 69007 Lyon</p>
        <hr>
        <pre style="background: #f4f4f4; padding: 15px; border-radius: 8px;">{body}</pre>
        <hr>
        <p>
            <a href="{URL}" style="background: #2ecc71; color: white; padding: 12px 24px;
               text-decoration: none; border-radius: 6px; font-weight: bold;">
                Voir sur Fac-Habitat
            </a>
        </p>
        <p style="color: #888; font-size: 12px;">
            Vérifié le {datetime.now().strftime('%d/%m/%Y à %H:%M')}
        </p>
    </body>
    </html>
    """

    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        log.info(f"Email envoyé à {EMAIL_TO}")
    except Exception as e:
        log.error(f"Erreur envoi email : {e}")


def main():
    log.info("Vérification de la disponibilité...")

    try:
        results = fetch_availability()
    except Exception as e:
        log.error(f"Erreur lors du scraping : {e}")
        sys.exit(1)

    current_status = format_status(results)
    previous_status = load_previous_status()

    log.info(f"Statut actuel :\n{current_status}")

    if previous_status is None:
        log.info("Premier lancement — sauvegarde du statut initial.")
        save_status(current_status)
        return

    if current_status != previous_status:
        log.info("CHANGEMENT DÉTECTÉ !")
        body = (
            f"Ancien statut :\n{previous_status}\n\n"
            f"Nouveau statut :\n{current_status}"
        )
        send_email(
            subject="🏠 Fac-Habitat Saint-Jérôme — Disponibilité changée !",
            body=body,
        )
        save_status(current_status)
    else:
        log.info("Aucun changement.")


if __name__ == "__main__":
    main()

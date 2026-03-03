"""
╔══════════════════════════════════════════════════════╗
║        🎓 Stage Finder - Scraper d'offres de stage   ║
╚══════════════════════════════════════════════════════╝

Scrape Indeed, HelloWork, Welcome to the Jungle et LinkedIn
puis envoie un récap par email.

Usage :
  python job_scraper.py
  (ou planifier via cron : 0 8 * * * python /chemin/job_scraper.py)
"""

import os
import requests
from bs4 import BeautifulSoup
import smtplib
import json
import os
import time
import random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Optional
import logging
from dotenv import load_dotenv
import cloudscraper
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

load_dotenv()

# ─────────────────────────────────────────────
#  CONFIGURATION — À MODIFIER AVANT DE LANCER
# ─────────────────────────────────────────────
CONFIG = {
    # ── Critères de recherche ──────────────────
    "keywords": ["stage informatique", "stage développeur", "stage software engineer", "stage data analyst", "stage web", "stage programmation"],  # mots-clés à rechercher
    "location": "Pau",          # ou "Paris", "Remote", etc.
    "contract_type": "internship",   # stage | alternance | cdi | cdd
    "radius_km": 50,            # rayon autour de la localisation

    # ── Filtres optionnels ─────────────────────
    "max_age_days": 20,          # offres publiées il y a moins de N jours
    "exclude_keywords": ["senior", "lead", "manager", "6 mois", "sénior", "CDI", "CDD", "5 ans", "3 ans"], # ex. ["senior", "10 ans d'expérience"]

    # ── Email ──────────────────────────────────
    "email": {
        "sender": os.getenv("GMAIL_SENDER"),
        "password": os.getenv("GMAIL_PASSWORD"),  # mot de passe d'application Gmail
        "receiver": os.getenv("GMAIL_RECEIVER"),
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
    },

    # ── Fichier cache (évite les doublons) ─────
    "cache_file": "seen_jobs.json",

    # ── Sites actifs ───────────────────────────
    "sites": {
        "indeed": True,
        "hellowork": True,
        "welcometothejungle": True,
        "linkedin": True,
    },
}

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ─────────────────────────────────────────────
#  DATA MODEL
# ─────────────────────────────────────────────
@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    date: str = ""
    description: str = ""
    salary: str = ""

    @property
    def uid(self) -> str:
        return f"{self.source}|{self.url}"


# ─────────────────────────────────────────────
#  CACHE (pour ne pas re-notifier les mêmes offres)
# ─────────────────────────────────────────────
def load_cache(path: str) -> set:
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_cache(path: str, seen: set):
    with open(path, "w") as f:
        json.dump(list(seen), f, indent=2)


# ─────────────────────────────────────────────
#  SCRAPERS
# ─────────────────────────────────────────────

scraper = cloudscraper.create_scraper()


def _get(url: str, **kwargs) -> Optional[BeautifulSoup]:
    try:
        time.sleep(random.uniform(1.5, 3.5))
        r = scraper.get(url, headers=HEADERS, timeout=15, **kwargs)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log.warning(f"GET {url} → {e}")
        return None


def get_driver():
    options = Options()
    options.add_argument("--headless")  # mode sans interface graphique
    options.add_argument("--no-sandbox")    
    options.add_argument("--disable-dev-shm-usage") 
    options.add_argument(f"user-agent={HEADERS['User-Agent']}") 
    options.add_argument("--disable-blink-features=AutomationControlled") 
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_argument("--log-level=3")           # ← désactive les logs Chrome
    options.add_experimental_option("excludeSwitches", ["enable-logging"])  # ← Windows surtout

    # Silencer webdriver-manager
    os.environ["WDM_LOG"] = "0"

    service = Service(ChromeDriverManager().install())
    service.log_path = os.devnull  # ← redirige les logs du driver vers /dev/null

    driver = webdriver.Chrome(service=service, options=options)
    return driver

def scrape_indeed(keyword: str, location: str, pages: int = 3) -> List[Job]:
    jobs = []
    driver = get_driver()

    try:
        for page in range(pages):
            url = (
                f"https://fr.indeed.com/jobs"
                f"?q={requests.utils.quote(keyword)}"
                f"&l={requests.utils.quote(location)}"
                f"&jt={CONFIG['contract_type']}"
                f"&radius={CONFIG['radius_km']}"
                f"&fromage={CONFIG['max_age_days']}"
                f"&start={page * 10}"
            )
            driver.get(url)
            time.sleep(random.uniform(2, 4))  # laisser la page charger

            soup = BeautifulSoup(driver.page_source, "html.parser")

            for card in soup.select("div.job_seen_beacon"):
                try:
                    title_el = card.select_one("h2.jobTitle span")
                    company_el = card.select_one("span.companyName, [data-testid='company-name']")
                    loc_el = card.select_one("div.companyLocation, [data-testid='text-location']")
                    link_el = card.select_one("h2.jobTitle a")
                    date_el = card.select_one("span.date, [data-testid='myJobsStateDate']")

                    if not title_el or not link_el:
                        continue

                    href = link_el.get("href", "")
                    if href.startswith("/"):
                        href = "https://fr.indeed.com" + href

                    jobs.append(Job(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "N/A",
                        location=loc_el.get_text(strip=True) if loc_el else location,
                        url=href,
                        source="Indeed",
                        date=date_el.get_text(strip=True) if date_el else "",
                    ))
                except Exception:
                    continue

    finally:
        driver.quit()

    log.info(f"  Indeed        → {len(jobs)} offres pour « {keyword} »")
    return jobs

def scrape_hellowork(keyword: str, location: str, pages: int = 3) -> List[Job]:
    jobs = []
    for page in range(1, pages + 1):
        url = (
            f"https://www.hellowork.com/fr-fr/emploi/recherche.html"
            f"?k={requests.utils.quote(keyword)}"
            f"&l={requests.utils.quote(location)}"
            f"&p={page}"
        )
        soup = _get(url)
        if not soup:
            continue

        for card in soup.select("li[data-id], article.job-item"):
            try:
                title_el = card.select_one("h2, h3, [class*='title']")
                company_el = card.select_one("[class*='company'], [class*='entreprise']")
                loc_el = card.select_one("[class*='location'], [class*='localisation']")
                link_el = card.select_one("a[href]")
                date_el = card.select_one("[class*='date'], time")

                if not title_el or not link_el:
                    continue

                href = link_el.get("href", "")
                if href.startswith("/"):
                    href = "https://www.hellowork.com" + href

                jobs.append(Job(
                    title=title_el.get_text(strip=True),
                    company=company_el.get_text(strip=True) if company_el else "N/A",
                    location=loc_el.get_text(strip=True) if loc_el else location,
                    url=href,
                    source="HelloWork",
                    date=date_el.get_text(strip=True) if date_el else "",
                ))
            except Exception:
                continue

    log.info(f"  HelloWork     → {len(jobs)} offres pour « {keyword} »")
    return jobs


def scrape_wttj(keyword: str, location: str) -> List[Job]:
    """Welcome to the Jungle via leur API publique."""
    jobs = []
    try:
        api_url = (
            "https://api.welcometothejungle.com/api/v1/jobs"
            f"?query={requests.utils.quote(keyword)}"
            f"&page=1&per_page=30"
            f"&contract_type_keys%5B%5D={CONFIG['contract_type']}"
        )
        r = requests.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        data = r.json()

        for item in data.get("jobs", []):
            org = item.get("organization", {})
            office = item.get("office", {})
            jobs.append(Job(
                title=item.get("name", ""),
                company=org.get("name", "N/A"),
                location=office.get("city", location),
                url=f"https://www.welcometothejungle.com/fr/companies/{org.get('slug','')}/jobs/{item.get('slug','')}",
                source="WTTJ",
                date=item.get("published_at", "")[:10],
            ))
    except Exception as e:
        log.warning(f"  WTTJ API → {e}")

    log.info(f"  WTTJ          → {len(jobs)} offres pour « {keyword} »")
    return jobs


def scrape_linkedin(keyword: str, location: str, pages: int = 2) -> List[Job]:
    jobs = []
    for page in range(pages):
        url = (
            f"https://www.linkedin.com/jobs/search/"
            f"?keywords={requests.utils.quote(keyword)}"
            f"&location={requests.utils.quote(location)}"
            f"&f_TPR=r{CONFIG['max_age_days'] * 86400}"
            f"&start={page * 25}"
        )
        soup = _get(url)
        if not soup:
            continue

        for card in soup.select("div.base-card, li.jobs-search-results__list-item"):
            try:
                title_el = card.select_one("h3.base-search-card__title, h3")
                company_el = card.select_one("h4.base-search-card__subtitle, h4")
                loc_el = card.select_one("span.job-search-card__location")
                link_el = card.select_one("a.base-card__full-link, a")
                date_el = card.select_one("time")

                if not title_el or not link_el:
                    continue

                jobs.append(Job(
                    title=title_el.get_text(strip=True),
                    company=company_el.get_text(strip=True) if company_el else "N/A",
                    location=loc_el.get_text(strip=True) if loc_el else location,
                    url=link_el.get("href", ""),
                    source="LinkedIn",
                    date=date_el.get("datetime", "") if date_el else "",
                ))
            except Exception:
                continue

    log.info(f"  LinkedIn      → {len(jobs)} offres pour « {keyword} »")
    return jobs


# ─────────────────────────────────────────────
#  FILTRAGE
# ─────────────────────────────────────────────

def filter_jobs(jobs: List[Job]) -> List[Job]:
    filtered = []
    for job in jobs:
        text = (job.title + " " + job.description).lower()

        # Exclure les mots-clés indésirables
        if any(kw.lower() in text for kw in CONFIG["exclude_keywords"]):
            continue

        filtered.append(job)

    # Dédoublonnage par URL
    seen_urls = set()
    unique = []
    for job in filtered:
        if job.url not in seen_urls:
            seen_urls.add(job.url)
            unique.append(job)

    return unique


# ─────────────────────────────────────────────
#  EMAIL HTML
# ─────────────────────────────────────────────

def build_email_html(jobs: List[Job]) -> str:
    now = datetime.now().strftime("%d/%m/%Y à %Hh%M")
    no_jobs_msg = "<p style=\"color:#888; text-align:center;\">Aucune nouvelle offre aujourd'hui.</p>"

    # Grouper par source
    by_source: dict[str, List[Job]] = {}
    for job in jobs:
        by_source.setdefault(job.source, []).append(job)

    source_colors = {
        "Indeed": "#003A9B",
        "HelloWork": "#FF6B35",
        "WTTJ": "#3D1152",
        "LinkedIn": "#0A66C2",
    }

    cards_html = ""
    for source, src_jobs in by_source.items():
        color = source_colors.get(source, "#555")
        cards_html += f"""
        <div style="margin-bottom:30px;">
          <h2 style="border-left:5px solid {color}; padding-left:12px; color:{color}; margin-bottom:15px;">
            {source} <span style="font-size:14px; color:#888;">({len(src_jobs)} offres)</span>
          </h2>
        """
        for job in src_jobs:
            cards_html += f"""
          <div style="background:#fff; border:1px solid #e5e7eb; border-radius:10px;
                      padding:16px 20px; margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,.06);">
            <a href="{job.url}" style="font-size:17px; font-weight:700; color:#111; text-decoration:none;">
              {job.title}
            </a>
            <div style="margin-top:6px; color:#555; font-size:14px;">
              🏢 <strong>{job.company}</strong> &nbsp;·&nbsp;
              📍 {job.location}
              {"&nbsp;·&nbsp; 📅 " + job.date if job.date else ""}
            </div>
            <a href="{job.url}" style="display:inline-block; margin-top:10px; padding:6px 14px;
               background:{color}; color:#fff; border-radius:6px; font-size:13px;
               text-decoration:none;">Voir l'offre →</a>
          </div>
        """
        cards_html += "</div>"

    return f"""<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><title>Offres de stage</title></head>
<body style="font-family:Arial,sans-serif; background:#f3f4f6; margin:0; padding:0;">
  <div style="max-width:680px; margin:30px auto; background:#f3f4f6;">

    <!-- Header -->
    <div style="background:linear-gradient(135deg,#1e40af,#7c3aed); border-radius:14px 14px 0 0;
                padding:30px 30px 20px; color:#fff; text-align:center;">
      <div style="font-size:36px;">🎓</div>
      <h1 style="margin:10px 0 5px; font-size:24px;">Stage Finder</h1>
      <p style="margin:0; opacity:.85; font-size:14px;">Rapport du {now}</p>
    </div>

    <!-- Summary -->
    <div style="background:#fff; padding:20px 30px; border-bottom:1px solid #e5e7eb;">
      <p style="margin:0; font-size:15px; color:#374151;">
        🔍 Recherche : <strong>{', '.join(CONFIG['keywords'])}</strong><br>
        📍 Localisation : <strong>{CONFIG['location']}</strong> (rayon {CONFIG['radius_km']} km)<br>
        📬 <strong>{len(jobs)} nouvelle(s) offre(s)</strong> trouvées
      </p>
    </div>

    <!-- Jobs -->
    <div style="padding:25px 30px;">
      {cards_html if jobs else no_jobs_msg}
    </div>

    <!-- Footer -->
    <div style="background:#e5e7eb; border-radius:0 0 14px 14px; padding:15px 30px;
                text-align:center; font-size:12px; color:#6b7280;">
      Généré automatiquement par Stage Finder · Modifie tes critères dans <code>job_scraper.py</code>
    </div>
  </div>
</body>
</html>"""


def send_email(subject: str, html: str):
    cfg = CONFIG["email"]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["sender"]
    msg["To"] = cfg["receiver"]
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(cfg["sender"], cfg["password"])
        server.sendmail(cfg["sender"], cfg["receiver"], msg.as_string())

    log.info(f"✅  Email envoyé à {cfg['receiver']}")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    log.info("═" * 55)
    log.info("  🎓  Stage Finder  —  démarrage")
    log.info("═" * 55)

    cache = load_cache(CONFIG["cache_file"])
    all_jobs: List[Job] = []

    for keyword in CONFIG["keywords"]:
        log.info(f"\n🔍  Mot-clé : « {keyword} »")

        if CONFIG["sites"]["indeed"]:
            all_jobs += scrape_indeed(keyword, CONFIG["location"])
        if CONFIG["sites"]["hellowork"]:
            all_jobs += scrape_hellowork(keyword, CONFIG["location"])
        if CONFIG["sites"]["welcometothejungle"]:
            all_jobs += scrape_wttj(keyword, CONFIG["location"])
        if CONFIG["sites"]["linkedin"]:
            all_jobs += scrape_linkedin(keyword, CONFIG["location"])

    # Filtrer
    all_jobs = filter_jobs(all_jobs)
    log.info(f"\n📊  Total après dédoublonnage : {len(all_jobs)} offres")

    # Nouvelles offres seulement
    new_jobs = [j for j in all_jobs if j.uid not in cache]
    log.info(f"🆕  Nouvelles offres (non vues) : {len(new_jobs)}")

    # Mettre à jour le cache
    for job in new_jobs:
        cache.add(job.uid)
    save_cache(CONFIG["cache_file"], cache)

    # Envoyer l'email
    subject = f"[Stage Finder] {len(new_jobs)} nouvelle(s) offre(s) — {datetime.now().strftime('%d/%m/%Y')}"
    html = build_email_html(new_jobs)

    if new_jobs:
        try:
            send_email(subject, html)
        except Exception as e:
            log.error(f"❌  Envoi email échoué : {e}")
            log.info("💾  HTML sauvegardé dans 'rapport_offres.html' pour débogage")
            with open("rapport_offres.html", "w", encoding="utf-8") as f:
                f.write(html)
    else:
        log.info("📭  Aucune nouvelle offre, email non envoyé.")

    log.info("\n✅  Terminé !")


if __name__ == "__main__":
    main()
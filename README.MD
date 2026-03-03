# 🎓 Stage Finder

Scraper d'offres de stage qui parcourt **Indeed, HelloWork, Welcome to the Jungle et LinkedIn**, dédoublonne les résultats et t'envoie un **email HTML** avec les nouvelles offres chaque jour.

---

## ⚡ Installation (2 minutes)

```bash
pip install requests beautifulsoup4 python-dotenv cloudscraper selenium webdriver-manager
```

---

## ⚙️ Configuration

### 1. Fichier `.env`

Crée un fichier `.env` à la racine du projet avec tes identifiants Gmail :

```env
GMAIL_SENDER=ton.email@gmail.com
GMAIL_PASSWORD=xxxx xxxx xxxx xxxx
GMAIL_RECEIVER=destinataire@gmail.com
```

### 2. Bloc `CONFIG` dans `main.py`

Ouvre `main.py` et modifie le bloc `CONFIG` en haut du fichier :

```python
CONFIG = {
    # Mots-clés de recherche (tu peux en mettre plusieurs)
    "keywords": ["stage informatique", "stage développeur", "stage software engineer", "stage data analyst", "stage web", "stage programmation"],

    "location": "Pau",         # Ta ville
    "contract_type": "internship",
    "radius_km": 50,
    "max_age_days": 20,         # Offres des 20 derniers jours

    # Mots à exclure (ex. pour éviter les offres "senior")
    "exclude_keywords": ["senior", "lead", "manager", "6 mois", "sénior", "CDI", "CDD", "5 ans", "3 ans"],

    "email": {
        "sender": os.getenv("GMAIL_SENDER"),
        "password": os.getenv("GMAIL_PASSWORD"),  # ← lire depuis .env
        "receiver": os.getenv("GMAIL_RECEIVER"),
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
    },

    # Activer/désactiver des sites
    "sites": {
        "indeed": True,
        "hellowork": True,
        "welcometothejungle": True,
        "linkedin": True,
    },
}
```

### 🔑 Mot de passe Gmail (Application Password)

Gmail bloque les connexions SMTP avec ton vrai mot de passe. Tu dois créer un **mot de passe d'application** :

1. Compte Google → **Sécurité** → **Validation en deux étapes** (active si pas déjà fait)
2. **Sécurité** → **Mots de passe des applications**
3. Sélectionne "Autre" → nomme-le "Stage Finder" → **Générer**
4. Copie le code `xxxx xxxx xxxx xxxx` dans `GMAIL_PASSWORD` dans ton `.env`

---

## 🚀 Lancement manuel

```bash
python main.py
```

---

## ⏰ Automatisation quotidienne

### Sur Linux/Mac (cron)

```bash
crontab -e
```

Ajoute cette ligne pour lancer chaque matin à 8h :

```
0 8 * * * /usr/bin/python3 /chemin/vers/main.py >> /tmp/stage_finder.log 2>&1
```

### Sur Windows (Planificateur de tâches)

1. Ouvre le **Planificateur de tâches**
2. Créer une tâche de base → déclencheur quotidien à 8h00
3. Action : démarrer un programme → `python.exe` avec l'argument `C:\chemin\main.py`

---

## 📬 Format de l'email reçu

L'email HTML contient pour chaque offre :
- Le titre du poste (cliquable)
- L'entreprise, la localisation, la date de publication
- Un bouton **"Voir l'offre"** qui mène directement à l'annonce
- Les offres sont groupées par site source (Indeed, HelloWork, WTTJ, LinkedIn)

---

## 📁 Fichier `seen_jobs.json`

Le script garde en mémoire les offres déjà envoyées pour ne pas te re-notifier. Ce fichier se crée automatiquement au premier lancement. Tu peux le supprimer pour re-recevoir toutes les offres.

---

## ⚠️ Notes importantes

- Les scrapers peuvent se casser si les sites changent leur HTML (ça arrive). La solution WTTJ utilise l'API publique et est donc plus stable.
- Indeed utilise Selenium (Chrome headless) pour contourner la protection anti-bot.
- Évite de lancer le script trop souvent (max 1-2 fois/jour) pour ne pas te faire bannir.
- LinkedIn est parfois strict sur le scraping, résultats peuvent varier.

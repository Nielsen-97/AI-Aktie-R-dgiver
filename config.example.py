"""
Konfiguration for den AI-drevne YouTube-pipeline.

DETTE ER EN SKABELON. Kopiér denne fil til "config.py" og udfyld
din egen API-nøgle der. config.py bliver IKKE lagt på GitHub
(se .gitignore), så din nøgle forbliver privat.

Alt kører 100% lokalt og gratis via Ollama - ingen cloud-tjenester,
ingen regning, nogensinde.
"""

# --- Ollama / lokal LLM (skriver indhold på engelsk, oversætter selv til dansk) ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

# --- Kanal-niche & stil ---
NICHE = "IT, teknologi, gaming-nyheder og leaks (spil, hardware, software)"
SPROG = "dansk"
TONE = "kort, punchy, letforståeligt sprog, lidt humor, faktabaseret"
VIDEO_LAENGDE_SEKUNDER = 180
ORD_PER_MINUT = 130

# --- Nyheder ---
FRISKHED_DAGE = 3
USD_TIL_DKK_KURS = 6.9

# --- Trends (YouTube Data API - gratis nøgle fra console.cloud.google.com) ---
YOUTUBE_API_KEY = "SÆT-DIN-YOUTUBE-NØGLE-HER"
TRENDS_LAND = "DK"
ANTAL_TRENDS = 15

# --- Output ---
OUTPUT_MAPPE = "output"

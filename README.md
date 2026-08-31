# YouTube AI-pipeline – Fase 1

Trend-research → videoidéer → manuskript → metadata, 100% gratis
via din lokale Llama 3 (Ollama).

## Opsætning (én gang)

1. **Ollama skal køre lokalt.** Du har allerede llama3 installeret fra
   dit aktie-projekt. Sørg for at Ollama-appen er startet (eller kør
   `ollama serve` i en terminal), og at modellen er hentet:
   ```
   ollama pull llama3
   ```

2. **Installer Python-pakker:**
   ```
   cd sti/til/youtube_ai
   pip install -r requirements.txt
   ```

3. **Opret din config.py:**
   ```
   copy config.example.py config.py
   ```
   (på Mac/Linux: `cp config.example.py config.py`)

   `config.py` er den fil, der indeholder din rigtige API-nøgle, og den
   ligger IKKE på GitHub (se `.gitignore`) — så din nøgle forbliver privat,
   selv hvis repoet er offentligt.

4. **Opret en gratis YouTube Data API-nøgle** (til at hente rigtige trends):
   1. Gå til [console.cloud.google.com](https://console.cloud.google.com)
   2. Opret et nyt projekt (gratis)
   3. Søg efter "YouTube Data API v3" og aktivér den
   4. Gå til "Credentials" → "Create Credentials" → "API key"
   5. Kopiér nøglen ind i din `config.py` som `YOUTUBE_API_KEY = "din-nøgle"`

   Uden en nøgle kører scriptet stadig, men springer trend-hentning over,
   og Llama 3 bruger så kun sin egen (ikke altid opdaterede) viden.

## Kør pipelinen

```
python main.py
```

Scriptet vil:
1. Hente dagens trends (gratis, via Google Trends)
2. Bede Llama 3 foreslå 5 videoidéer
3. Bede dig vælge/beskrive hvilken idé du vil bruge
4. Lade Llama 3 skrive et fuldt manuskript
5. Generere titel, beskrivelse og tags
6. Gemme alt i `output/video_ÅÅÅÅ-MM-DD_TT-MM.txt`

## Justér til din kanal

Åbn `config.py` og ret:
- `NICHE` – hvad kanalen handler om
- `TONE` – hvordan manuskripterne skal lyde
- `VIDEO_LAENGDE_SEKUNDER` – hvor lange videoerne skal være
- `OLLAMA_MODEL` – hvis du bruger en anden model end llama3

## Arkitektur: Engelsk → dansk (100% lokalt)

Indhold (idéer, manuskript, metadata) skrives på **engelsk** af den
lokale model (Ollama), fordi lokale modeller generelt er stærkere på
engelsk end dansk. Det færdige resultat **oversættes derefter til
dansk af samme lokale model**, i et separat kald - oversættelse er en
nemmere opgave for modellen end fri dansk generering, så kvaliteten
plejer at blive bedre.

Alt kører 100% lokalt og gratis - ingen cloud-tjenester, ingen
API-nøgler ud over YouTube-trend-nøglen, ingen regning nogensinde.
Samme princip som i aktie-analyse-projektet.

## Hvad kommer i Fase 2

Næste skridt er at tage det færdige manuskript og automatisk:
- Generere voiceover (gratis TTS)
- Finde matchende stock-klip (gratis Pexels/Pixabay)
- Samle det hele til en færdig video med FFmpeg

Sig til, når du har testet Fase 1 og er klar til at gå videre.

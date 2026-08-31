"""
Kommunikation med den lokale LLM (llama3/Qwen2.5) via Ollama.

ARKITEKTUR: Alt indhold genereres først på ENGELSK lokalt (hvor modellen
er markant stærkere), og oversættes derefter til dansk - OGSÅ lokalt,
af samme model, i et separat kald. Dette er 100% gratis og kører helt
uden internetforbindelse eller cloud-tjenester (samme princip som
aktie-analyse-projektet) - ingen API-nøgler, ingen regning, nogensinde.

Kræver at Ollama kører og at modellen er hentet (fx `ollama pull llama3`).
"""

import re
import requests
import config


def spoerg_llm(prompt: str, temperature: float = 0.8) -> str:
    """
    Sender en prompt til den lokale LLM og returnerer svaret som tekst.
    """
    try:
        response = requests.post(
            config.OLLAMA_URL,
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=600,
        )
        response.raise_for_status()
        svar = response.json().get("response", "").strip()
        return _fjern_preamble(svar)
    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Kunne ikke forbinde til Ollama. Sørg for at Ollama kører "
            "(åbn Ollama-appen, eller kør 'ollama serve' i en terminal)."
        )


def _fjern_preamble(tekst: str) -> str:
    """Fjerner indledende sætninger som "Here is..." før selve indholdet."""
    linjer = tekst.split("\n")
    while linjer and re.match(r"^(here|i'll|i will|sure|okay|note:)\b", linjer[0].strip().lower()):
        linjer.pop(0)
        while linjer and linjer[0].strip() == "":
            linjer.pop(0)
    return "\n".join(linjer).strip()


def _oversaet_til_dansk(engelsk_tekst: str, kontekst: str = "") -> str:
    """
    Oversætter en engelsk tekst til naturligt dansk - lokalt, gratis,
    via samme Ollama-model. Oversættelse er typisk en nemmere opgave
    for modellen end fri dansk generering, så kvaliteten bliver ofte
    bedre end at bede den skrive dansk fra bunden.
    """
    prompt = f"""You are a professional English-to-Danish translator. Translate the
following text into natural, fluent, everyday Danish - the way a native
Danish YouTuber would actually phrase it, NOT a word-for-word translation.

Rules:
- Keep official product and company names unchanged (e.g. "Apple Maps",
  "PlayStation", "Nintendo Switch", "GTA 6") - do not translate them
- Never combine or connect different topics that weren't connected in
  the source text
- Never invent new facts, numbers or details not in the source text
- Output ONLY the Danish translation, nothing else - no preamble, no
  explanation, no "Here is the translation:"

{kontekst}

Text to translate:
---
{engelsk_tekst}
---

Danish translation:"""

    print("🌍 Oversætter til dansk (lokalt) ...")
    return spoerg_llm(prompt, temperature=0.3)


def foreslaa_video_idéer(trending_emner: list[str], nyheds_artikler: list[dict] = None) -> str:
    """
    Beder den lokale LLM foreslå 5 videoidéer PÅ ENGELSK ud fra dagens
    trends + rigtige nyhedsoverskrifter + kanalens niche, og oversætter
    derefter listen til dansk (lokalt).
    """
    emne_liste = "\n".join(f"- {e}" for e in trending_emner) or "(no specific trends found today)"

    if nyheds_artikler:
        nyheds_liste = "\n".join(
            f"- {a['titel']} (source: {a['kilde']}) — {a['resume'][:150]}"
            for a in nyheds_artikler
        )
    else:
        nyheds_liste = "(no news articles found)"

    prompt = f"""You are a content strategist for a YouTube channel about: {config.NICHE}.

Here are topics currently trending on YouTube:
{emne_liste}

Here are ACTUAL, current news headlines from the last few days:
{nyheds_liste}

Suggest 5 concrete video ideas, based on the real news above wherever
possible. IMPORTANT: Each video idea must be based on ONE single news
story from the list above. NEVER combine two different, unrelated news
stories into one idea - that creates false connections that aren't
true. If in doubt whether two stories are related, assume they are NOT.

For each idea, give:
1. A catchy title referencing a concrete news story (use real names/numbers/products)
2. A short reason why it will perform well right now
3. A concrete hook sentence for the first 5 seconds - based on a specific
   number, quote or fact from the source, NOT a rhetorical question

Do not repeat the same hook structure across the 5 ideas. Be specific
and concrete, not vague or generic. Write in English."""

    print("🧠 Spørger AI-modellen om videoidéer (på engelsk) ...")
    engelsk = spoerg_llm(prompt, temperature=0.9)
    return _oversaet_til_dansk(
        engelsk,
        kontekst="This is a list of 5 YouTube video idea suggestions, each with a title, reasoning and hook.",
    )


def skriv_manuskript(valgt_idé: str, fakta: str = "") -> dict:
    """
    Skriver et fuldt manuskript PÅ ENGELSK til en valgt videoidé, og
    oversætter det til dansk (lokalt).

    Returnerer en dict: {"engelsk": ..., "dansk": ...} - den engelske
    version bruges bagefter til at generere metadata med bedre kontekst.
    """
    antal_ord = int((config.VIDEO_LAENGDE_SEKUNDER / 60) * config.ORD_PER_MINUT)
    antal_ord_engelsk = int(antal_ord * 0.9)  # engelsk er typisk lidt mere kompakt end dansk

    if fakta.strip():
        fakta_afsnit = f"""
Here is the factual information the script MUST be based on (use ONLY
these facts, do not invent extra details, names, dates or numbers not
stated here). Use AT LEAST 3 concrete details/numbers/names from this:
---
{fakta}
---
"""
    else:
        fakta_afsnit = """
You have not been given concrete source facts for this topic. Do NOT
write invented details, numbers, quotes or "reveals" as if they were
confirmed. Stick to general, correct knowledge, and be clear if
something is a rumor/unofficial.
"""

    prompt = f"""You are a scriptwriter for a faceless YouTube channel about: {config.NICHE}.

Write a full script for this video idea:
{valgt_idé}
{fakta_afsnit}
Structure the script internally like this (do not write the headers
themselves in the output, just let the content flow naturally):
1. HOOK: 1-2 sentences with a concrete, surprising detail - no clichés,
   no rhetorical questions like "Have you ever..." or "Did you know..."
2. CONTEXT: briefly what happened
3. CORE: at least 3 concrete facts/numbers/names from the source
4. PERSPECTIVE: a short, sharp take on what it means
5. CTA: a short call to like/follow

Requirements:
- Length: about {antal_ord_engelsk} words
- Tone: {config.TONE}
- Write ONLY the text that should be read aloud by the voiceover - no
  stage directions, no [scene descriptions], no section headers

Write the script now, in English:"""

    print("✍️  Skriver manuskript (på engelsk) ...")
    engelsk = spoerg_llm(prompt, temperature=0.7)

    dansk = _oversaet_til_dansk(
        engelsk,
        kontekst=(
            "This is a script for a Danish YouTube video, meant to sound completely "
            "natural when read aloud by a voiceover."
        ),
    )

    return {"engelsk": engelsk, "dansk": dansk}


def generer_metadata(manuskript_engelsk: str) -> str:
    """
    Genererer titel, beskrivelse og tags PÅ ENGELSK ud fra det engelske
    manuskript, og oversætter til dansk (lokalt).
    """
    prompt = f"""Here is the script for a YouTube video:

{manuskript_engelsk}

Generate for this video:
1. TITLE: a catchy, CTR-optimized title (max 60 characters), with a
   concrete number or name if possible - not a generic phrasing
2. DESCRIPTION: 2-3 sentences for the video description
3. TAGS: 10 relevant search tags, comma-separated

Answer in English, in exactly this format with the three headers."""

    print("🏷️  Genererer metadata (på engelsk) ...")
    engelsk = spoerg_llm(prompt, temperature=0.6)
    return _oversaet_til_dansk(
        engelsk,
        kontekst="This is metadata (title, description, tags) for a Danish YouTube video.",
    )

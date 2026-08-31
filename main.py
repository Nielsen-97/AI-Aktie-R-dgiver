"""
FASE 1: Trend-research + idegenerering + manuskript + metadata.

NY ARKITEKTUR: Indhold skrives på engelsk lokalt (gratis, ingen
tokengrænse), og oversættes til naturligt dansk via Groq (gratis,
generøs daglig kvote). Se llm.py og cloud.py for detaljer.

Kør: python main.py
"""

import os
from datetime import datetime

import config
import trends
import news
import llm


def main():
    os.makedirs(config.OUTPUT_MAPPE, exist_ok=True)

    # 1. Hent trends (YouTube) + rigtige nyhedsartikler (RSS)
    trending_emner = trends.hent_trending_emner()
    alle_nyheder = news.hent_nyheder()

    # 2. Bed LLM foreslå videoidéer (engelsk lokalt -> dansk via Groq)
    idéer = llm.foreslaa_video_idéer(trending_emner, alle_nyheder)
    print("\n" + "=" * 60)
    print("VIDEOIDÉER")
    print("=" * 60)
    print(idéer)

    # 3. Lad brugeren vælge
    print("\n" + "-" * 60)
    valgt = input(
        "\nIndsæt/beskriv hvilken idé du vil gå videre med "
        "(eller kopiér en af titlerne ovenfor):\n> "
    )

    # 4. Find automatisk relevante nyhedsartikler til den valgte idé
    relevante = news.find_relevante_artikler(valgt, alle_nyheder)
    if relevante:
        print(f"\n📎 Fandt {len(relevante)} relevante kilde(r) automatisk:")
        for a in relevante:
            print(f"   - [{a['kilde']}] {a['titel']}")
        fakta = news.formater_som_fakta(relevante)
    else:
        print("\n📎 Ingen matchende kilder fundet automatisk — manuskriptet skrives uden opdigtede detaljer.")
        fakta = ""

    # 5. Skriv manuskript (engelsk lokalt -> dansk via Groq)
    resultat = llm.skriv_manuskript(valgt, fakta)
    manuskript_engelsk = resultat["engelsk"]
    manuskript = resultat["dansk"]
    print("\n" + "=" * 60)
    print("MANUSKRIPT")
    print("=" * 60)
    print(manuskript)

    # 6. Generér metadata (ud fra det engelske manuskript -> dansk via Groq)
    metadata = llm.generer_metadata(manuskript_engelsk)
    print("\n" + "=" * 60)
    print("METADATA")
    print("=" * 60)
    print(metadata)

    # 7. Gem alt til en fil
    tidsstempel = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filnavn = os.path.join(config.OUTPUT_MAPPE, f"video_{tidsstempel}.txt")

    with open(filnavn, "w", encoding="utf-8") as f:
        f.write("TRENDING EMNER DEN DAG\n")
        f.write("\n".join(trending_emner) or "(ingen)")
        f.write("\n\n" + "=" * 60 + "\nFORESLÅEDE IDÉER\n" + "=" * 60 + "\n")
        f.write(idéer)
        f.write("\n\n" + "=" * 60 + "\nVALGT IDÉ\n" + "=" * 60 + "\n")
        f.write(valgt)
        f.write("\n\n" + "=" * 60 + "\nAUTOMATISK FUNDNE KILDER\n" + "=" * 60 + "\n")
        f.write(fakta or "(ingen fundet)")
        f.write("\n\n" + "=" * 60 + "\nMANUSKRIPT (DANSK)\n" + "=" * 60 + "\n")
        f.write(manuskript)
        f.write("\n\n" + "=" * 60 + "\nMANUSKRIPT (ENGELSK ORIGINAL)\n" + "=" * 60 + "\n")
        f.write(manuskript_engelsk)
        f.write("\n\n" + "=" * 60 + "\nMETADATA\n" + "=" * 60 + "\n")
        f.write(metadata)

    print(f"\n✅ Alt er gemt i: {filnavn}")
    print("   Klar til Fase 2 (voiceover + visuals) næste gang.")


if __name__ == "__main__":
    main()

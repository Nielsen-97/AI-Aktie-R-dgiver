#!/usr/bin/env python3
"""
Læser 'købt X'-svar i Discord-signalkanalen og registrerer handlerne i
aktive_handler.json / portfolio.json via engine.py.

Dette er IKKE en persistent bot — GitHub Actions kan ikke holde en Discord
gateway-forbindelse åben. I stedet henter scriptet de seneste beskeder i
kanalen via Discord REST API'et (bot-token) hver gang det køres, og
behandler dem der matcher 'købt 1' / 'købt 2' / 'købt 3' (evt. + pris).
Kørt fra .github/workflows/check_discord_replies.yml hver time på hverdage.
"""
import os
import re
import json
import requests

import engine

DISCORD_BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")
PROCESSED_FILE = os.path.join(engine.DATA_DIR, "discord_svar_behandlet.json")

KOEBT_MOENSTER = re.compile(
    r"^\s*købt\s+([123])(?:\s+(\d+(?:[.,]\d+)?))?\s*[.!]?\s*$", re.IGNORECASE
)


def hent_behandlede():
    try:
        with open(PROCESSED_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def gem_behandlede(ids):
    # Behold kun de seneste 500 — filen skal ikke vokse uendeligt
    trimmet = sorted(ids)[-500:]
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmet, f)


def hent_nye_beskeder():
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    r = requests.get(url, headers=headers, params={"limit": 50}, timeout=15)
    r.raise_for_status()
    return r.json()


def send_besked(tekst):
    url = f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        r = requests.post(url, headers=headers, json={"content": tekst}, timeout=15)
        r.raise_for_status()
    except Exception as e:
        engine.log(f"Discord-svar: kunne ikke sende bekræftelse — {e}")


def main():
    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
        print("DISCORD_BOT_TOKEN eller DISCORD_CHANNEL_ID mangler — springer over")
        return

    behandlede = hent_behandlede()
    try:
        beskeder = hent_nye_beskeder()
    except Exception as e:
        print(f"Kunne ikke hente Discord-beskeder: {e}")
        return

    nye = 0
    # Discord returnerer nyeste først — behandl ældste først så rækkefølgen
    # af flere svar i samme kørsel bliver den brugeren faktisk skrev dem i.
    for msg in reversed(beskeder):
        msg_id = msg.get("id")
        if not msg_id or msg_id in behandlede:
            continue
        behandlede.add(msg_id)

        if msg.get("author", {}).get("bot"):
            continue  # ignorer botens egne beskeder (bekræftelser osv.)

        tekst = msg.get("content", "")
        match = KOEBT_MOENSTER.match(tekst)
        if not match:
            continue

        index = int(match.group(1))
        pris_raw = match.group(2)
        pris = float(pris_raw.replace(",", ".")) if pris_raw else None

        forfatter = msg.get("author", {}).get("username", "ukendt")
        engine.log(f"Discord-svar: {forfatter} skrev '{tekst}' — forsøger at registrere signal #{index}")

        resultat = engine.registrer_koeb_fra_discord_signal(index, pris_override=pris)
        nye += 1

        if resultat["ok"]:
            send_besked(
                f"✅ Registreret: **{resultat['ticker']}** {resultat['antal']} stk à "
                f"{resultat['koebspris']} {resultat['valuta']} via {resultat['platform']} "
                f"(gebyr ~{resultat['gebyr_dkk']:.0f} DKK) — Stop: {resultat['stop_loss']} · Mål: {resultat['target']}"
            )
        else:
            send_besked(f"❌ Kunne ikke registrere 'købt {index}': {resultat['fejl']}")

    gem_behandlede(behandlede)
    print(f"Discord-svar tjekket: {nye} nye 'købt X'-beskeder behandlet")


if __name__ == "__main__":
    main()

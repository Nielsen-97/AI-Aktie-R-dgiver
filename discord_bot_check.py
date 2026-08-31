#!/usr/bin/env python3
"""
Læser 'købt X'-svar i Discord-signalkanalen og registrerer handlerne.

IKKE en persistent bot — GitHub Actions kan ikke holde en Discord gateway-
forbindelse åben. I stedet henter scriptet de seneste beskeder i kanalen
via Discord REST API'et (bot-token) hver gang det køres, og behandler dem
der matcher 'købt 1' / 'købt 2' / 'købt 3' (evt. + pris) eller 'ja'/'nej'.
Kørt fra .github/workflows/check_discord_replies.yml hver 5. minut på
hverdage (nødvendigt for at 15-minutters bekræftelsesvinduet nedenfor giver
mening — sat højere end selve cron-intervallet fordi GitHub Actions'
schedule-trigger ikke i praksis rammer hvert 5. minut pålideligt).

To slags handel:
  - Nordnet/Endavu: ingen API-integration findes, så handlen registreres
    med det samme i aktive_handler.json (som hidtil) — det er ren
    bogføring af noget brugeren selv udfører manuelt, ingen rigtige penge
    flytter sig via dette script.
  - eToro: der ER en API-integration (se etoro_client.py), så en 'købt X'
    her ville udføre en RIGTIG ordre. Derfor kræver eToro-handler et
    eksplicit bekræftelsesflow: botten foreslår handlen, og udfører den
    KUN hvis brugeren svarer 'ja' inden for 15 minutter. Svares der 'nej',
    eller udløber tiden, annulleres forslaget uden at noget udføres.
"""
import os
import re
import json
import requests
from datetime import datetime, timedelta, timezone

import engine

DISCORD_BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "")
PROCESSED_FILE = os.path.join(engine.DATA_DIR, "discord_svar_behandlet.json")
PENDING_FILE   = os.path.join(engine.DATA_DIR, "etoro_pending_ordre.json")

PENDING_TIMEOUT = timedelta(minutes=15)

KOEBT_MOENSTER = re.compile(
    r"^\s*købt\s+([123])(?:\s+(\d+(?:[.,]\d+)?))?\s*[.!]?\s*$", re.IGNORECASE
)
JA_MOENSTER  = re.compile(r"^\s*ja\s*[.!]?\s*$", re.IGNORECASE)
NEJ_MOENSTER = re.compile(r"^\s*nej\s*[.!]?\s*$", re.IGNORECASE)


def hent_behandlede():
    try:
        with open(PROCESSED_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def gem_behandlede(ids):
    trimmet = sorted(ids)[-500:]  # behold kun de seneste 500 — filen skal ikke vokse uendeligt
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmet, f)


def hent_pending():
    try:
        with open(PENDING_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data if data else None
    except Exception:
        return None


def gem_pending(pending):
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False)


def er_udloebet(pending, nu):
    try:
        oprettet = datetime.fromisoformat(pending["oprettet_utc"])
    except Exception:
        return True
    return (nu - oprettet) > PENDING_TIMEOUT


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
        engine.log(f"Discord-svar: kunne ikke sende besked — {e}")


def demo_taenkning():
    if not engine.ETORO_KLIENT_TILGAENGELIG:
        return ""
    return "🧪 DEMO" if engine.etoro_client.ETORO_DEMO_MODE else "💰 LIVE"


def haandter_ja(pending):
    forslag = pending
    resultat = engine.udfoer_etoro_koeb(forslag)
    if resultat["ok"]:
        sl_note = ""
        if forslag.get("stop_loss") or forslag.get("target"):
            sl_note = f" — Stop: {forslag.get('stop_loss')} · Mål: {forslag.get('target')}"
            if not resultat["sl_tp_bekraeftet"]:
                sl_note += "\n⚠️ Kunne IKKE bekræfte at stop-loss/take-profit reelt blev sat på eToro — tjek og sæt det manuelt i appen NU."
        send_besked(
            f"✅ **{resultat['ticker']}** købt: {resultat['antal']} stk à ${resultat['fill_pris']:.2f} (fill-pris) "
            f"via eToro.{sl_note}"
        )
    else:
        send_besked(f"❌ Ordren fejlede på eToro for {forslag['ticker']}: {resultat['fejl']}")


def haandter_nej():
    send_besked("❌ Køb annulleret.")


def haandter_timeout(pending):
    send_besked(f"❌ Køb annulleret — timeout ({pending['ticker']}, ingen bekræftelse inden for 15 minutter).")


def byg_bekraeft_besked(forslag):
    tag = demo_taenkning()
    tag_del = f" ({tag})" if tag else ""
    note = ""
    try:
        eksisterende = [
            p for p in engine.hent_etoro_positioner()
            if str(p.get("symbol") or p.get("instrumentDisplayName") or "").upper() == forslag["ticker"].upper()
        ]
        if eksisterende:
            note = f"\nℹ️ Du har allerede en åben position i {forslag['ticker']} på eToro."
    except Exception:
        pass
    return (
        f"⚠️ Bekræft køb{tag_del}: **{forslag['ticker']}** {forslag['antal']} stk à ${forslag['pris_estimat']:.2f} "
        f"via eToro (${forslag['beloeb_usd']:.2f}).{note}\n"
        f"Svar `ja` inden for 15 minutter for at bekræfte, eller `nej` for at annullere."
    )


def main():
    if not DISCORD_BOT_TOKEN or not DISCORD_CHANNEL_ID:
        print("DISCORD_BOT_TOKEN eller DISCORD_CHANNEL_ID mangler — springer over")
        return

    nu = datetime.now(timezone.utc)
    behandlede = hent_behandlede()
    pending = hent_pending()

    if pending and er_udloebet(pending, nu):
        haandter_timeout(pending)
        pending = None

    try:
        beskeder = hent_nye_beskeder()
    except Exception as e:
        print(f"Kunne ikke hente Discord-beskeder: {e}")
        gem_pending(pending)
        return

    nye = 0
    for msg in reversed(beskeder):  # ældste først, så rækkefølgen af svar bliver den brugeren skrev dem i
        msg_id = msg.get("id")
        if not msg_id or msg_id in behandlede:
            continue
        behandlede.add(msg_id)

        if msg.get("author", {}).get("bot"):
            continue

        tekst = msg.get("content", "")

        if pending and not er_udloebet(pending, nu):
            if NEJ_MOENSTER.match(tekst):
                haandter_nej()
                pending = None
                nye += 1
                continue
            if JA_MOENSTER.match(tekst):
                haandter_ja(pending)
                pending = None
                nye += 1
                continue
            if KOEBT_MOENSTER.match(tekst):
                send_besked(
                    f"⚠️ Der venter allerede en bekræftelse på {pending['ticker']} — "
                    f"svar `ja` eller `nej` først."
                )
                nye += 1
            continue

        if pending and er_udloebet(pending, nu):
            haandter_timeout(pending)
            pending = None
            # falder igennem herunder så denne besked stadig kan behandles som en ny kommando

        match = KOEBT_MOENSTER.match(tekst)
        if not match:
            continue

        index = int(match.group(1))
        pris_raw = match.group(2)
        pris = float(pris_raw.replace(",", ".")) if pris_raw else None

        forfatter = msg.get("author", {}).get("username", "ukendt")
        engine.log(f"Discord-svar: {forfatter} skrev '{tekst}' — forsøger at registrere signal #{index}")

        forslag = engine.byg_ordre_forslag(index, pris_override=pris)
        nye += 1

        if not forslag["ok"]:
            send_besked(f"❌ Kunne ikke registrere 'købt {index}': {forslag['fejl']}")
            continue

        if not forslag["auto_udfoerbar"]:
            resultat = engine.registrer_koeb_fra_discord_signal(index, pris_override=pris)
            if resultat["ok"]:
                send_besked(
                    f"✅ Registreret (manuel {resultat['platform']}): **{resultat['ticker']}** "
                    f"{resultat['antal']} stk à {resultat['koebspris']} {resultat['valuta']} "
                    f"(gebyr ~{resultat['gebyr_dkk']:.0f} DKK) — husk selv at lægge ordren "
                    f"hos {resultat['platform']}."
                )
            else:
                send_besked(f"❌ Kunne ikke registrere 'købt {index}': {resultat['fejl']}")
            continue

        # eToro-signal — foreslå, udfør IKKE endnu
        pending = {**forslag, "oprettet_utc": nu.isoformat(), "forfatter": forfatter}
        send_besked(byg_bekraeft_besked(pending))

    if pending and er_udloebet(pending, nu):
        haandter_timeout(pending)
        pending = None

    gem_behandlede(behandlede)
    gem_pending(pending)
    print(f"Discord-svar tjekket: {nye} nye beskeder behandlet, pending={'ja' if pending else 'nej'}")


if __name__ == "__main__":
    main()

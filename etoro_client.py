#!/usr/bin/env python3
"""
eToro API v2 klient.

Opdateret ud fra uddrag af den officielle dokumentation som brugeren har
indsat direkte i samtalen (Authentication, "Open and close market orders",
"Get Agent Portfolios"). Det er en FORBEDRING i forhold til den første
version af denne fil, som var bygget på søgemaskine-uddrag — men der er
STADIG huller, listet herunder, fordi builders.etoro.com/api-portal.etoro.com
er blokeret af netværksproxyen i det miljø hvor filen skrives, så jeg kan
ikke selv slå det op.

BEKRÆFTET af brugerens indsatte dokumentation:
  - Auth-headers: x-api-key, x-user-key, x-request-id (UUID).
  - Instrument-søgning: GET /api/v1/market-data/search?internalSymbolFull=<ticker>
    — svar-wrapper er "items", felter "instrumentId" og "internalSymbolFull".
  - Ordreåbning: POST /api/v2/trading/execution/orders (live) eller
    POST /api/v2/trading/execution/demo/orders (demo) — samme værtsnavn,
    demo er et sti-segment, IKKE et separat subdomæne. Krop bekræftet
    ordret: {"action","transaction","symbol","instrumentId","orderType",
    "leverage","amount","orderCurrency"}.
  - Lukning af position (ikke implementeret her — ikke efterspurgt, kun
    køb sker via 'købt X'): POST /api/v1/trading/execution/market-close-orders/positions/{positionId},
    krop {"InstrumentId":..., "UnitsToDeduct": null eller antal for delvis luk}.
  - Anbefalet at tjekke live kurs via GET /api/v1/market-data/instruments/rates
    før en ordre lægges, for prisnøjagtighed.
  - Kontantsaldo: GET /api/v1/trading/info/{demo|real}/pnl. Tilgængelig
    cash beregnes som credit - sum(ordersForOpen[].amount hvor mirrorID==0)
    - sum(orders[].amount) — bekræftet formel og endpoint.
  - "Get Agent Portfolios" (/api/v1/agent-portfolios) er IKKE saldo/positioner
    — det er eToro's bot/API-nøgle-administration (Builders-platformen),
    hvert objekt har en eksplicit VIRTUEL budget-ramme og scopede
    userTokens, intet reelt saldo- eller positionsfelt. Bruges ikke.

STADIG UBEKRÆFTET / UÅBNET:
  1. Åbne positioner (til hent_etoro_positioner()/"tjek eksisterende
     beholdning") — pnl-endpointet ovenfor leverer credit/ordersForOpen/
     orders til saldoberegningen, men det er IKKE bekræftet om det også
     indeholder en liste over aktuelt åbne positioner (med indgangspris,
     antal osv.), eller om det kræver et separat endpoint. hent_positioner()
     rejser derfor stadig bevidst EtoroFejl indtil dette er afklaret.
  2. Feltnavne for stop-loss/take-profit i ordre-kroppen (gætter stadig på
     "stopLossRate"/"takeProfitRate") og i ordre-SVARET (position_id,
     fill-pris) — dokumentationen viste intet eksempel-svar for
     POST .../orders. placer_markedsordre() forsøger at bekræfte SL/TP ved
     at slå positionen op igen bagefter via hent_positioner() — det opslag
     fejler indtil videre altid (punkt 1 ovenfor), så sl_tp_bekraeftet er
     ALTID False. Det er en bevidst konservativ standard (advar altid frem
     for at antage det virkede), ikke en fejl i sig selv.
  3. Query-parameter-navnet til at filtrere /market-data/instruments/rates
     til ét instrument (gætter "instrumentIds") — hent_live_rate() fejler
     blødt (returnerer None) hvis det ikke virker, så resten af flowet
     fortsætter med det eksisterende prisestimat.

FØR ETORO_DEMO nogensinde sættes til "false":
  1. Kør en fuld tur i DEMO og tjek at ordrer, stop-loss/take-profit og
     saldo/positioner rent faktisk matcher det eToro-appens demo-konto viser.
  2. Ret felt-gæt ovenfor hvis noget logges som uventet i data/koersel_log.txt.

ETORO_DEMO fejler LUKKET: alt andet end den præcise streng "false"
(case-insensitive) holder klienten i demo-miljøet.
"""
import os
import uuid

import requests

ETORO_API_KEY  = os.getenv("ETORO_API_KEY", "")
ETORO_USER_KEY = os.getenv("ETORO_USER_KEY", "")

ETORO_DEMO_MODE = os.getenv("ETORO_DEMO", "true").strip().lower() != "false"

# Ét fælles værtsnavn — demo vs. live er et sti-segment på
# ordre-udførelses-endpointet, ikke et separat subdomæne (bekræftet).
BASE_URL = "https://public-api.etoro.com"
_ORDER_STI = "/api/v2/trading/execution/demo/orders" if ETORO_DEMO_MODE else "/api/v2/trading/execution/orders"


class EtoroFejl(Exception):
    """Rejses ved enhver fejl i kommunikationen med eToro API'et."""
    pass


def _headers():
    if not ETORO_API_KEY or not ETORO_USER_KEY:
        raise EtoroFejl("ETORO_API_KEY eller ETORO_USER_KEY mangler i miljøvariabler")
    return {
        "x-api-key": ETORO_API_KEY,
        "x-user-key": ETORO_USER_KEY,
        "x-request-id": str(uuid.uuid4()),
        "Content-Type": "application/json",
    }


def _kald(method, sti, **kwargs):
    url = f"{BASE_URL}{sti}"
    try:
        r = requests.request(method, url, headers=_headers(), timeout=20, **kwargs)
    except requests.RequestException as e:
        raise EtoroFejl(f"Netværksfejl mod eToro ({url}): {e}")
    if r.status_code >= 400:
        raise EtoroFejl(f"eToro API-fejl {r.status_code} ({url}): {r.text[:500]}")
    try:
        return r.json()
    except ValueError:
        return {}


def _foerste_match(d, kandidat_navne):
    """Prøver flere mulige feltnavne (eToro's casing er ikke konsistent på tværs af endpoints)."""
    for navn in kandidat_navne:
        if isinstance(d, dict) and d.get(navn) is not None:
            return d[navn]
    return None


def find_instrument_id(ticker):
    """
    Slår et ticker-symbol (fx 'AAPL') op til eToro's numeriske instrumentId
    via GET /api/v1/market-data/search?internalSymbolFull=<ticker>.
    Svar-form bekræftet: {"items": [{"instrumentId": ..., "internalSymbolFull": ...}, ...]}.
    Kræver et præcist match på internalSymbolFull — rejser EtoroFejl (i
    stedet for at gætte på det første resultat) hvis søgningen giver
    resultater, men ingen af dem matcher tickeren præcist, da et forkert
    instrumentId ville handle et helt andet aktiv.
    """
    data = _kald("GET", "/api/v1/market-data/search", params={"internalSymbolFull": ticker})
    items = data.get("items", []) if isinstance(data, dict) else []

    if not items:
        raise EtoroFejl(f"Fandt ikke et eToro instrumentId for '{ticker}' — rå svar: {str(data)[:300]}")

    for item in items:
        if str(item.get("internalSymbolFull", "")).upper() == ticker.upper():
            return item["instrumentId"]

    raise EtoroFejl(
        f"Intet PRÆCIST symbol-match for '{ticker}' blandt {len(items)} søgeresultat(er) "
        f"({[i.get('internalSymbolFull') for i in items]}) — afviser for ikke at risikere at "
        f"handle det forkerte instrument."
    )


def hent_live_rate(instrument_id):
    """
    Henter en frisk kurs for instrumentet via GET /api/v1/market-data/instruments/rates
    (dokumentationen anbefaler at tjekke dette for prisnøjagtighed inden en
    ordre lægges). Query-parameternavnet er IKKE bekræftet — fejler blødt
    (returnerer None) frem for at afbryde hele købsflowet hvis det ikke virker.
    """
    try:
        data = _kald("GET", "/api/v1/market-data/instruments/rates", params={"instrumentIds": instrument_id})
    except EtoroFejl:
        return None

    emner = data.get("rates") or data.get("instruments") or data if isinstance(data, list) else []
    if isinstance(data, dict) and not emner:
        emner = [data]

    for emne in emner:
        if str(_foerste_match(emne, ["instrumentId", "InstrumentID", "InstrumentId"]) or instrument_id) != str(instrument_id):
            continue
        rate = _foerste_match(emne, ["rate", "ask", "bid", "price", "Rate", "Ask"])
        if rate is not None:
            return float(rate)
    return None


def hent_konto():
    """
    Henter tilgængelig kontantsaldo via GET /api/v1/trading/info/{demo|real}/pnl
    (bekræftet endpoint og formel):

        tilgængelig cash = credit
                            - sum(ordersForOpen[].amount hvor mirrorID == 0)
                            - sum(orders[].amount)

    (Det tidligere forsøg med /api/v1/agent-portfolios er droppet — det
    endpoint er eToro's bot/API-nøgle-administration, ikke kontosaldo, se
    modul-docstring.)
    """
    miljo = "demo" if ETORO_DEMO_MODE else "real"
    data = _kald("GET", f"/api/v1/trading/info/{miljo}/pnl")

    credit = data.get("credit")
    if credit is None:
        raise EtoroFejl(f"pnl-svar havde intet 'credit'-felt — rå svar: {str(data)[:300]}")

    ordrer_til_aabning = data.get("ordersForOpen") or []
    egne_ordrer_sum = sum(
        float(o.get("amount", 0)) for o in ordrer_til_aabning if o.get("mirrorID") == 0
    )
    ordrer = data.get("orders") or []
    ordrer_sum = sum(float(o.get("amount", 0)) for o in ordrer)

    saldo = float(credit) - egne_ordrer_sum - ordrer_sum
    return {"saldo_usd": saldo, "raw": data}


def hent_positioner():
    """
    INGEN VERIFICERET POSITIONS-ENDPOINT FUNDET ENDNU.

    /api/v1/trading/info/{demo|real}/pnl (bruges af hent_konto() til
    saldoen) er ikke bekræftet til også at indeholde en liste over åbne
    positioner — kun credit/ordersForOpen/orders er bekræftet af brugerens
    dokumentation. Rejser derfor bevidst EtoroFejl i stedet for at gætte;
    kaldende kode (engine.hent_etoro_positioner) fanger den og returnerer []
    i stedet for at foregive at kende brugerens beholdning.
    """
    raise EtoroFejl(
        "Intet verificeret positions-endpoint — pnl-svaret er kun bekræftet til "
        "credit/ordersForOpen/orders (saldo), ikke en positionsliste. Se docstring i hent_positioner()."
    )


def placer_markedsordre(ticker, beloeb_usd, stop_loss_pris=None, take_profit_pris=None):
    """
    Åbner en market-buy-position på eToro via POST /api/v2/trading/execution/orders
    (eller .../demo/orders — sti bekræftet af brugerens dokumentation, som
    også bekræfter at request-kroppen skal indeholde både "symbol" og
    "instrumentId" samt "leverage"). Stop-loss/take-profit-feltnavnene
    (stopLossRate/takeProfitRate) er STADIG et gæt — dokumentationen nævner
    kun at det er muligt, ikke de præcise feltnavne.

    Efter ordren er lagt, slår funktionen den nyoprettede position op igen
    og tjekker om SL/TP faktisk blev sat — hvis feltnavnene er forkerte,
    opdager vi det HER i stedet for at antage det virkede, og kaldende kode
    kan advare brugeren om at sætte det manuelt.

    Returnerer dict med position_id, fill_pris og sl_tp_bekraeftet.
    Rejser EtoroFejl hvis selve ordren fejler.
    """
    instrument_id = find_instrument_id(ticker)

    krop = {
        "action": "open",
        "transaction": "buy",
        "symbol": ticker,
        "instrumentId": instrument_id,
        "orderType": "mkt",
        "leverage": 1,
        "amount": round(beloeb_usd, 2),
        "orderCurrency": "usd",
    }
    if stop_loss_pris:
        krop["stopLossRate"] = stop_loss_pris
    if take_profit_pris:
        krop["takeProfitRate"] = take_profit_pris

    svar = _kald("POST", _ORDER_STI, json=krop)

    position_id = _foerste_match(svar, ["positionId", "PositionId", "orderId", "OrderId", "id", "Id"])
    fill_pris   = _foerste_match(svar, ["executionRate", "openRate", "price", "ExecutionRate", "OpenRate", "Price"])

    sl_tp_bekraeftet = not (stop_loss_pris or take_profit_pris)  # intet at bekræfte hvis ingen blev bedt om
    if position_id and (stop_loss_pris or take_profit_pris):
        try:
            for p in hent_positioner():
                p_id = _foerste_match(p, ["positionId", "PositionId", "id", "Id"])
                if str(p_id) == str(position_id):
                    p_sl = _foerste_match(p, ["stopLossRate", "StopLossRate"])
                    p_tp = _foerste_match(p, ["takeProfitRate", "TakeProfitRate"])
                    har_sl = (not stop_loss_pris) or p_sl
                    har_tp = (not take_profit_pris) or p_tp
                    sl_tp_bekraeftet = bool(har_sl and har_tp)
                    break
        except EtoroFejl:
            sl_tp_bekraeftet = False  # kunne ikke bekræfte — kaldende kode bør advare brugeren

    return {
        "position_id": position_id,
        "fill_pris": float(fill_pris) if fill_pris is not None else None,
        "sl_tp_bekraeftet": sl_tp_bekraeftet,
        "raw": svar,
    }

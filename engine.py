"""
============================================================
 AI AKTIE RAADGIVER - ENGINE v5.0
 Opgraderet med:
   - Ægte RSI, MACD, Bollinger Bands, Volume-spike
   - Fuld fundamental scoring (FCF, rev-vækst, gæld, margins)
   - Earnings surprise detection (EPS vs estimat)
   - 52-ugers breakout + momentum screener
   - Insider trading signal (SEC Form 4)
   - Short interest detection
   - Groq llama-3.3-70b-versatile (10x bedre analyse)
   - RAG historik aktiveret og forbedret
   - Endavu som platform 3
   - Backtesting modul
   - Alert-system (desktop + log)
   - Forbedret Kelly position sizing
============================================================
"""
import os, sys, json, time, re, requests, sqlite3
import yfinance as yf
from datetime import datetime, timedelta
from groq import Groq
import pandas as pd
import numpy as np

os.environ["PYTHONIOENCODING"] = "utf-8"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE        = os.path.join(DATA_DIR, "stocks.db")
SCREENER_FILE  = os.path.join(DATA_DIR, "screener_seneste.json")
BRIEF_FILE     = os.path.join(DATA_DIR, "daily_brief_seneste.json")
MAKRO_FILE     = os.path.join(DATA_DIR, "makro_seneste.json")
LOG_FILE       = os.path.join(DATA_DIR, "koersel_log.txt")
SENTIMENT_FILE = os.path.join(DATA_DIR, "sentiment_seneste.json")
BACKTEST_FILE  = os.path.join(DATA_DIR, "backtest_resultater.json")
ALERT_FILE     = os.path.join(DATA_DIR, "alerts.json")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    raise SystemExit("FEJL: GROQ_API_KEY miljøvariabel er ikke sat.")
client = Groq(api_key=GROQ_API_KEY)

GROQ_MODEL = "llama-3.3-70b-versatile"

# ChromaDB — valgfri, bruges kun lokalt (ikke i GitHub Actions)
try:
    import chromadb
    CHROMA_PATH = os.path.join(DATA_DIR, "earnings_history")
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    earnings_collection = chroma_client.get_or_create_collection(name="earnings_transcripts")
    CHROMA_TILGAENGELIG = True
except Exception:
    CHROMA_TILGAENGELIG = False
    earnings_collection = None

# ════════════════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════════════════
# JSON-filer bruges i stedet for SQLite — virker på Streamlit Cloud og GitHub
PORTFOLIO_FILE     = os.path.join(DATA_DIR, "portfolio.json")
AKTIVE_HANDLER_FILE = os.path.join(DATA_DIR, "aktive_handler.json")
BACKTEST_HISTORIK_FILE = os.path.join(DATA_DIR, "backtest_historik.json")

def _init_json_filer():
    """Opret standard JSON-filer hvis de ikke eksisterer."""
    if not os.path.exists(PORTFOLIO_FILE):
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump({"holdings": [], "cash": {"nordnet_dkk": 0, "etoro_usd": 0, "endavu_dkk": 0}, "watchlist": []}, f)
    if not os.path.exists(AKTIVE_HANDLER_FILE):
        with open(AKTIVE_HANDLER_FILE, "w") as f:
            json.dump([], f)
    if not os.path.exists(BACKTEST_HISTORIK_FILE):
        with open(BACKTEST_HISTORIK_FILE, "w") as f:
            json.dump([], f)

_init_json_filer()

def log(besked):
    t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = f"[{t}] {besked}"
    print(msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except:
        pass

def _gem_json_atomisk(filepath, data):
    """Skriv JSON atomisk — undgår truncated/korrupte filer ved nedbrud."""
    import tempfile
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, filepath)

# ════════════════════════════════════════════════════════════
# PORTFOLIO
# ════════════════════════════════════════════════════════════
def indlaes_portfolio():
    """Læs portfolio fra JSON-fil — virker på Streamlit Cloud."""
    data = _safe_json_load(PORTFOLIO_FILE)
    if not data:
        data = {"holdings": [], "cash": {}, "watchlist": []}
    for platform in ["nordnet_dkk", "etoro_usd", "endavu_dkk"]:
        if platform not in data.get("cash", {}):
            data.setdefault("cash", {})[platform] = 0
    return data

def gem_portfolio(data):
    """Gem portfolio til JSON-fil — synkroniseres til GitHub."""
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ════════════════════════════════════════════════════════════
# AKTIVE HANDLER — køb/sælg via systemet
# ════════════════════════════════════════════════════════════
def registrer_koeb(ticker, navn, platform, antal, koebspris,
                   stop_loss, target, beloeb, valuta, score, analyse):
    """Gem et køb i aktive_handler.json og træk cash fra portfolio.json."""
    # Hent aktive handler
    handler = _safe_json_load(AKTIVE_HANDLER_FILE) or []
    nyt_id = max((h.get("id", 0) for h in handler), default=0) + 1
    handler.append({
        "id": nyt_id, "ticker": ticker, "navn": navn, "platform": platform,
        "antal": antal, "koebspris": koebspris, "stop_loss": stop_loss,
        "target": target, "beloeb": beloeb, "valuta": valuta,
        "dato_kobt": datetime.now().strftime("%Y-%m-%d"),
        "score_ved_koeb": score, "analyse_tekst": analyse, "status": "aktiv"
    })
    with open(AKTIVE_HANDLER_FILE, "w", encoding="utf-8") as f:
        json.dump(handler, f, ensure_ascii=False, indent=2)

    # Tilføj til portfolio holdings
    pf = indlaes_portfolio()
    pf["holdings"].append({
        "ticker": ticker, "navn": navn, "platform": platform,
        "antal": antal, "koebspris": koebspris, "type": "aktie", "strategi": "aktiv"
    })
    # Træk cash fra platform
    if platform == "etoro":
        pf["cash"]["etoro_usd"] = max(0, pf["cash"].get("etoro_usd", 0) - beloeb)
    elif platform == "endavu":
        pf["cash"]["endavu_dkk"] = max(0, pf["cash"].get("endavu_dkk", 0) - beloeb)
    else:
        pf["cash"]["nordnet_dkk"] = max(0, pf["cash"].get("nordnet_dkk", 0) - beloeb)
    gem_portfolio(pf)
    log(f"KØBT: {ticker} {antal} stk à {koebspris} via {platform} — SL:{stop_loss} T:{target}")

def registrer_salg(handler_id, salgspris, aarsag="Manuel"):
    """Marker handel som solgt i aktive_handler.json og tilføj cash tilbage."""
    handler = _safe_json_load(AKTIVE_HANDLER_FILE) or []
    h = next((x for x in handler if x.get("id") == handler_id), None)
    if not h:
        return
    ticker   = h["ticker"]
    platform = h["platform"]
    antal    = h["antal"]
    koebspris= h["koebspris"]
    beloeb   = h.get("beloeb", antal * koebspris)
    salgsvaerdi = antal * salgspris if salgspris > 0 else beloeb
    afkast_pct  = (salgspris / koebspris - 1) * 100 if koebspris > 0 else 0

    h["status"] = "solgt"
    h["analyse_tekst"] = (h.get("analyse_tekst") or "") +         f"\n[SOLGT {datetime.now().strftime('%Y-%m-%d')} à {salgspris} — {aarsag} — {afkast_pct:+.1f}%]"
    h["salgspris"] = salgspris
    h["afkast_pct"] = round(afkast_pct, 2)
    h["dato_solgt"] = datetime.now().strftime("%Y-%m-%d")

    with open(AKTIVE_HANDLER_FILE, "w", encoding="utf-8") as f:
        json.dump(handler, f, ensure_ascii=False, indent=2)

    # Fjern fra portfolio holdings
    pf = indlaes_portfolio()
    pf["holdings"] = [x for x in pf["holdings"]
                      if not (x["ticker"] == ticker and x["platform"] == platform and x.get("strategi") == "aktiv")]
    # Tilsæt cash
    if platform == "etoro":
        pf["cash"]["etoro_usd"] = pf["cash"].get("etoro_usd", 0) + salgsvaerdi
    elif platform == "endavu":
        pf["cash"]["endavu_dkk"] = pf["cash"].get("endavu_dkk", 0) + salgsvaerdi
    else:
        pf["cash"]["nordnet_dkk"] = pf["cash"].get("nordnet_dkk", 0) + salgsvaerdi
    gem_portfolio(pf)
    log(f"SOLGT: {ticker} à {salgspris} ({aarsag}) — afkast {afkast_pct:+.1f}%")

def hent_aktive_handler():
    """Hent alle aktive handler fra JSON med nuværende kurs og status."""
    alle = _safe_json_load(AKTIVE_HANDLER_FILE) or []
    rækker_data = [h for h in alle if h.get("status") == "aktiv"]

    handler = []
    for r in rækker_data:
        id_      = r.get("id", 0)
        ticker   = r.get("ticker", "")
        navn     = r.get("navn", ticker)
        platform = r.get("platform", "")
        antal    = r.get("antal", 0)
        koebspris= r.get("koebspris", 0)
        stop_loss= r.get("stop_loss")
        target   = r.get("target")
        beloeb   = r.get("beloeb", 0)
        valuta   = r.get("valuta", "DKK")
        dato     = r.get("dato_kobt", "")
        score    = r.get("score_ved_koeb", 5)
        analyse  = r.get("analyse_tekst", "")

        k = hent_kurs(ticker)
        pris_nu = k["pris"]   if k else koebspris
        change  = k["change"] if k else 0
        afkast  = (pris_nu / koebspris - 1) * 100 if koebspris > 0 else 0
        vaerdi  = antal * pris_nu

        signal = "OK"
        if stop_loss and pris_nu <= stop_loss:
            signal = "STOP_LOSS_HIT"
        elif target and pris_nu >= target:
            signal = "TARGET_NAAET"
        elif afkast < -15:
            signal = "STOR_TAB"

        handler.append({
            "id": id_, "ticker": ticker, "navn": navn or ticker,
            "platform": platform, "antal": antal, "koebspris": koebspris,
            "stop_loss": stop_loss, "target": target, "beloeb": beloeb,
            "valuta": valuta, "dato": dato, "score": score, "analyse": analyse,
            "pris_nu": pris_nu, "change": change,
            "afkast": round(afkast, 2), "vaerdi": round(vaerdi, 2),
            "signal": signal,
        })
    return handler

def tjek_saelg_signaler():
    """
    Gennemgår alle aktive handler og returnerer dem der
    har ramt stop-loss, target eller er forringet fundamentalt.
    """
    handler = hent_aktive_handler()
    alerts  = []
    for h in handler:
        if h["signal"] == "STOP_LOSS_HIT":
            alerts.append({
                "type":    "SÆLG",
                "ticker":  h["ticker"],
                "aarsag":  f"Stop-loss ramt! Pris {h['pris_nu']} ≤ SL {h['stop_loss']}",
                "handler_id": h["id"],
                "afkast":  h["afkast"],
                "farve":   "#f87171",
            })
        elif h["signal"] == "TARGET_NAAET":
            alerts.append({
                "type":    "SÆLG",
                "ticker":  h["ticker"],
                "aarsag":  f"Target nået! Pris {h['pris_nu']} ≥ Target {h['target']} 🎯",
                "handler_id": h["id"],
                "afkast":  h["afkast"],
                "farve":   "#4ade80",
            })
        elif h["signal"] == "STOR_TAB":
            alerts.append({
                "type":    "ADVARSEL",
                "ticker":  h["ticker"],
                "aarsag":  f"Stor nedgang: {h['afkast']:+.1f}% siden køb",
                "handler_id": h["id"],
                "afkast":  h["afkast"],
                "farve":   "#facc15",
            })
    return alerts

# ════════════════════════════════════════════════════════════
# MAKRO
# ════════════════════════════════════════════════════════════
def hent_makro():
    log("Henter makro: VIX, SP500, Fear&Greed...")
    last_err = None
    for forsøg in range(3):
        try:
            if forsøg > 0:
                log(f"Makro retry {forsøg+1}/3...")
                time.sleep(4 * forsøg)

            vix     = float(yf.Ticker("^VIX").history(period="5d")["Close"].iloc[-1])
            sp      = yf.Ticker("^GSPC").history(period="1y")
            sp_pris = float(sp["Close"].iloc[-1])
            sp_sma  = float(sp["Close"].rolling(200).mean().iloc[-1])
            sp_sma50= float(sp["Close"].rolling(50).mean().iloc[-1])
            sp_trend= sp_pris > sp_sma

            sp_1m_afkast = float((sp_pris / sp["Close"].iloc[-22] - 1) * 100) if len(sp) >= 22 else 0.0

            try:
                tnx = yf.Ticker("^TNX").history(period="5d")["Close"].iloc[-1]
                rente_txt = f"{tnx:.2f}%"
                rente_advarsel = tnx > 4.5
            except:
                rente_txt = "N/A"
                rente_advarsel = False

            vix_status = "Roligt" if vix < 20 else "Uroligt" if vix < 30 else "PANIK"

            if vix > 30:
                just = -2.5
            elif vix > 25:
                just = -1.5
            elif vix > 20:
                just = -0.5
            else:
                just = 0.0

            if sp_trend and sp_1m_afkast > 2:
                just += 0.5

            makro = {
                "vix": round(vix, 2),
                "vix_status": vix_status,
                "sp_status": "Optrend" if sp_trend else "Nedtrend",
                "sp_pris": round(sp_pris, 2),
                "sp_sma200": round(sp_sma, 2),
                "sp_sma50": round(sp_sma50, 2),
                "sp_1m_afkast": round(sp_1m_afkast, 2),
                "rente_10y": rente_txt,
                "rente_advarsel": rente_advarsel,
                "justering": round(just, 2),
                "stop_koeb": vix > 30,
                "forsigtig": vix > 25,
            }
            _gem_json_atomisk(MAKRO_FILE, makro)
            log(f"Makro OK: VIX={vix:.1f}, SP500={sp_status_str(makro)}, Justering={just:+.1f}")
            return makro
        except Exception as e:
            last_err = e
            log(f"Makro fejl forsøg {forsøg+1}: {e}")

    log(f"Makro: alle 3 forsøg fejlede — bruger fallback. Sidst: {last_err}")
    eksisterende = _safe_json_load(MAKRO_FILE)
    if eksisterende and eksisterende.get("vix_status") not in [None, "Ukendt", ""]:
        log("Makro: bruger eksisterende gemt data som fallback")
        return eksisterende
    return {"vix": 20, "justering": 0, "stop_koeb": False, "forsigtig": False,
            "vix_status": "Ukendt", "sp_status": "Ukendt", "sp_1m_afkast": 0,
            "rente_10y": "N/A", "rente_advarsel": False}

def sp_status_str(m):
    return m.get("sp_status","") + f" ({m.get('sp_1m_afkast',0):+.1f}% 1M)"


def _safe_json_load(filepath):
    """Læs JSON-fil sikkert — returnerer None hvis filen er tom eller korrupt."""
    try:
        if not os.path.exists(filepath):
            return None
        with open(filepath, encoding='utf-8') as f:
            indhold = f.read().strip()
        if not indhold:
            return None
        return json.loads(indhold)
    except (json.JSONDecodeError, OSError):
        try:
            os.remove(filepath)
        except:
            pass
        return None

def hent_makro_data():
    return _safe_json_load(MAKRO_FILE)

def anvend_makro_justering(score, makro):
    if not makro:
        return score
    return round(max(1.0, min(10.0, score + makro.get("justering", 0))), 1)

GRAENSER = {"staerkt_koeb": 8.5, "koeb": 7.0, "hold": 5.0, "undgaa": 3.5}

def score_til_tekst(score, makro=None):
    if makro and makro.get("stop_koeb"):
        return "HOLD (Panik)" if score >= 6 else "SÆLG"
    if score >= GRAENSER["staerkt_koeb"]: return "STÆRKT KØB"
    if score >= GRAENSER["koeb"]:         return "KØB"
    if score >= GRAENSER["hold"]:         return "HOLD"
    return "SÆLG"

# ════════════════════════════════════════════════════════════
# TEKNISKE INDIKATORER — ægte beregning
# ════════════════════════════════════════════════════════════
def beregn_rsi(serie, periode=14):
    """Beregn RSI korrekt med Wilder's smoothing."""
    delta = serie.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/periode, min_periods=periode, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/periode, min_periods=periode, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def beregn_macd(serie, fast=12, slow=26, signal=9):
    """Beregn MACD linje, signal linje og histogram."""
    ema_fast   = serie.ewm(span=fast, adjust=False).mean()
    ema_slow   = serie.ewm(span=slow, adjust=False).mean()
    macd_linje = ema_fast - ema_slow
    signal_linje = macd_linje.ewm(span=signal, adjust=False).mean()
    histogram  = macd_linje - signal_linje
    return macd_linje, signal_linje, histogram

def teknisk_screening(ticker):
    """
    Fuld teknisk analyse med:
    - RSI (14), MACD, Bollinger Bands
    - SMA20/50/200 trend
    - Volume spike detection
    - 52-ugers breakout signal
    """
    try:
        hist = yf.Ticker(ticker).history(period="1y")
        if hist.empty or len(hist) < 30:
            return 5.0, {}

        close  = hist["Close"]
        volume = hist["Volume"]
        pris   = float(close.iloc[-1])

        score  = 5.0
        grunde = []
        detaljer = {"pris": round(pris, 2)}

        # ── SMA trend ──────────────────────────────────────
        sma20  = close.rolling(20).mean().iloc[-1]
        sma50  = close.rolling(50).mean().iloc[-1]
        sma200 = close.rolling(200).mean().iloc[-1]
        detaljer["sma20"]  = round(float(sma20), 2)
        detaljer["sma50"]  = round(float(sma50), 2)
        detaljer["sma200"] = round(float(sma200), 2)

        if pris > sma200:
            score += 1.0
            grunde.append("Over SMA200")
        if pris > sma50:
            score += 0.5
            grunde.append("Over SMA50")
        if sma20 > sma50 > sma200:
            score += 0.5
            grunde.append("SMA alignment optrend")

        # ── RSI ────────────────────────────────────────────
        rsi_serie = beregn_rsi(close)
        rsi = float(rsi_serie.iloc[-1])
        rsi_prev = float(rsi_serie.iloc[-2]) if len(rsi_serie) > 1 else rsi
        detaljer["rsi"] = round(rsi, 1)

        if 40 <= rsi <= 60:
            score += 0.5
            grunde.append(f"RSI neutral ({rsi:.0f})")
        elif rsi < 35:
            score += 1.0  # Oversolgt = potentiel bounce
            grunde.append(f"RSI oversolgt ({rsi:.0f}) — bounce?")
        elif rsi > 70:
            score -= 1.0  # Overkøbt
            grunde.append(f"RSI overkøbt ({rsi:.0f})")
        elif rsi > 55 and rsi_prev < rsi:
            score += 0.5  # Stigende momentum
            grunde.append(f"RSI stiger ({rsi:.0f})")

        # ── MACD ───────────────────────────────────────────
        macd_l, signal_l, hist_macd = beregn_macd(close)
        macd_val    = float(macd_l.iloc[-1])
        macd_prev   = float(macd_l.iloc[-2]) if len(macd_l) > 1 else macd_val
        signal_val  = float(signal_l.iloc[-1])
        hist_val    = float(hist_macd.iloc[-1])
        hist_prev   = float(hist_macd.iloc[-2]) if len(hist_macd) > 1 else hist_val
        detaljer["macd"] = round(macd_val, 4)
        detaljer["macd_signal"] = round(signal_val, 4)

        if macd_val > signal_val:
            score += 0.5
            grunde.append("MACD bullish")
        if hist_val > 0 and hist_prev < 0:
            score += 1.0  # Bullish crossover
            grunde.append("MACD crossover UP")
        elif hist_val < 0 and hist_prev > 0:
            score -= 1.0  # Bearish crossover
            grunde.append("MACD crossover DOWN")

        # ── Bollinger Bands ────────────────────────────────
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_u = float(bb_upper.iloc[-1])
        bb_l = float(bb_lower.iloc[-1])
        bb_m = float(bb_mid.iloc[-1])
        bb_pct = (pris - bb_l) / (bb_u - bb_l) if (bb_u - bb_l) > 0 else 0.5
        detaljer["bb_pct"] = round(bb_pct, 2)
        detaljer["bb_upper"] = round(bb_u, 2)
        detaljer["bb_lower"] = round(bb_l, 2)

        if bb_pct < 0.2:
            score += 0.5
            grunde.append("Nær Bollinger lower band")
        elif bb_pct > 0.8:
            score -= 0.3
            grunde.append("Nær Bollinger upper band")

        # ── Volume spike ───────────────────────────────────
        vol_avg20 = float(volume.rolling(20).mean().iloc[-1])
        vol_nu    = float(volume.iloc[-1])
        vol_ratio = vol_nu / vol_avg20 if vol_avg20 > 0 else 1.0
        detaljer["vol_ratio"] = round(vol_ratio, 2)

        if vol_ratio > 2.0 and pris > float(close.iloc[-2]):
            score += 1.0
            grunde.append(f"Volume spike {vol_ratio:.1f}x (bullish)")
        elif vol_ratio > 2.0 and pris < float(close.iloc[-2]):
            score -= 0.5
            grunde.append(f"Volume spike {vol_ratio:.1f}x (bearish)")

        # ── 52-ugers breakout ──────────────────────────────
        # Brug min_periods=50 så vi altid får en værdi selv med <252 datapunkter
        high_52w_s = close.rolling(252, min_periods=50).max()
        low_52w_s  = close.rolling(252, min_periods=50).min()
        high_52w   = float(high_52w_s.iloc[-1])
        low_52w    = float(low_52w_s.iloc[-1])

        import math
        if not math.isnan(high_52w) and high_52w > 0:
            pct_fra_high = round((pris / high_52w - 1) * 100, 1)
            detaljer["52w_high"] = round(high_52w, 2)
            detaljer["52w_low"]  = round(low_52w, 2)
            detaljer["pct_fra_52w_high"] = pct_fra_high

            if pct_fra_high > -3:
                score += 1.5
                grunde.append(f"Nær 52-ugers high ({pct_fra_high:.1f}%)")
            elif pct_fra_high > -10:
                score += 0.5
                grunde.append(f"Stærk position ({pct_fra_high:.1f}% fra high)")
            elif pct_fra_high < -40:
                score -= 1.0
                grunde.append(f"Langt fra 52-ugers high ({pct_fra_high:.1f}%)")
        else:
            detaljer["pct_fra_52w_high"] = None

        # ── Trend styrke (ADX-proxy) ────────────────────────
        try:
            afkast_1m = float((pris / close.iloc[-22] - 1) * 100) if len(close) >= 22 else None
            afkast_3m = float((pris / close.iloc[-66] - 1) * 100) if len(close) >= 66 else None
            import math as _math
            detaljer["afkast_1m"] = round(afkast_1m, 1) if afkast_1m is not None and not _math.isnan(afkast_1m) else None
            detaljer["afkast_3m"] = round(afkast_3m, 1) if afkast_3m is not None and not _math.isnan(afkast_3m) else None
        except:
            detaljer["afkast_1m"] = None
            detaljer["afkast_3m"] = None
            afkast_1m = None
            afkast_3m = None

        if afkast_1m and afkast_3m and afkast_1m > 5 and afkast_3m > 10:
            score += 0.5
            grunde.append(f"Momentum: +{afkast_1m:.1f}% 1M / +{afkast_3m:.1f}% 3M")

        score = round(max(1.0, min(10.0, score)), 1)
        return score, {**detaljer, "grunde": grunde}

    except Exception as e:
        log(f"Teknisk fejl for {ticker}: {e}")
        return 5.0, {}

# ════════════════════════════════════════════════════════════
# FUNDAMENTAL SCORING — komplet
# ════════════════════════════════════════════════════════════
def fundamental_screening(ticker):
    """
    Fuld fundamental analyse med:
    - P/E + Forward P/E
    - Revenue vækst YoY
    - EPS vækst + earnings surprise
    - Free Cash Flow margin
    - Gæld/Egenkapital ratio
    - Gross margin
    - Return on Equity (ROE)
    """
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        if not info or info.get("regularMarketPrice") is None:
            return None, "Ingen data"

        score  = 5.0
        grunde = []

        # ── P/E ─────────────────────────────────────────────
        pe         = info.get("trailingPE")
        forward_pe = info.get("forwardPE")

        # Filtrer kun ekstreme tilfælde ud — ikke vækst-aktier
        if pe and pe > 200:
            return None, f"Ekstremt høj P/E ({pe:.0f})"
        if pe and pe < 0:
            return None, "Negativt P/E"

        if pe:
            if pe < 15:
                score += 2.0; grunde.append(f"Lav P/E {pe:.1f}")
            elif pe < 25:
                score += 1.5; grunde.append(f"Rimelig P/E {pe:.1f}")
            elif pe < 40:
                score += 0.5; grunde.append(f"Moderat P/E {pe:.1f}")
            elif pe > 80:
                score -= 0.5; grunde.append(f"Høj P/E {pe:.1f}")
            # 40-80 er neutral for vækst-aktier — ingen straf

        if forward_pe and forward_pe > 0 and pe and pe > 0:
            if forward_pe < pe * 0.9:
                score += 0.5; grunde.append(f"Faldende P/E (fwd {forward_pe:.1f})")

        # ── Revenue vækst ───────────────────────────────────
        rev_growth = info.get("revenueGrowth")  # YoY
        if rev_growth is not None:
            rev_pct = rev_growth * 100
            if rev_pct > 20:
                score += 2.0; grunde.append(f"Rev. vækst +{rev_pct:.0f}%")
            elif rev_pct > 10:
                score += 1.0; grunde.append(f"Rev. vækst +{rev_pct:.0f}%")
            elif rev_pct > 0:
                score += 0.5; grunde.append(f"Rev. vækst +{rev_pct:.0f}%")
            else:
                score -= 1.0; grunde.append(f"Revenue fald {rev_pct:.0f}%")

        # ── EPS vækst ───────────────────────────────────────
        eps_growth = info.get("earningsGrowth")
        if eps_growth is not None:
            eps_pct = eps_growth * 100
            if eps_pct > 25:
                score += 1.5; grunde.append(f"EPS vækst +{eps_pct:.0f}%")
            elif eps_pct > 10:
                score += 0.5; grunde.append(f"EPS vækst +{eps_pct:.0f}%")
            elif eps_pct < -10:
                score -= 1.0; grunde.append(f"EPS fald {eps_pct:.0f}%")

        # ── Earnings Surprise ───────────────────────────────
        try:
            earnings_hist = t.earnings_history
            if earnings_hist is not None and not earnings_hist.empty:
                seneste = earnings_hist.sort_index(ascending=False).iloc[0]
                eps_actual   = seneste.get("epsActual")
                eps_estimate = seneste.get("epsEstimate")
                if eps_actual and eps_estimate and eps_estimate != 0:
                    surprise_pct = (eps_actual - eps_estimate) / abs(eps_estimate) * 100
                    if surprise_pct > 10:
                        score += 1.5; grunde.append(f"EPS surprise +{surprise_pct:.1f}%")
                    elif surprise_pct > 3:
                        score += 0.5; grunde.append(f"EPS beat +{surprise_pct:.1f}%")
                    elif surprise_pct < -5:
                        score -= 1.0; grunde.append(f"EPS miss {surprise_pct:.1f}%")
                else:
                    surprise_pct = None
            else:
                surprise_pct = None
        except:
            surprise_pct = None

        # ── Free Cash Flow margin ───────────────────────────
        fcf        = info.get("freeCashflow")
        revenue    = info.get("totalRevenue")
        fcf_margin = None
        if fcf and revenue and revenue > 0:
            fcf_margin = fcf / revenue * 100
            if fcf_margin > 20:
                score += 1.5; grunde.append(f"FCF margin {fcf_margin:.0f}%")
            elif fcf_margin > 10:
                score += 0.5; grunde.append(f"FCF margin {fcf_margin:.0f}%")
            elif fcf_margin < 0:
                score -= 1.0; grunde.append(f"Negativt FCF {fcf_margin:.0f}%")

        # ── Gæld/Egenkapital ────────────────────────────────
        debt_equity = info.get("debtToEquity")
        if debt_equity is not None:
            if debt_equity < 30:
                score += 1.0; grunde.append(f"Lav gæld D/E {debt_equity:.0f}%")
            elif debt_equity > 150:
                score -= 1.0; grunde.append(f"Høj gæld D/E {debt_equity:.0f}%")
            elif debt_equity > 300:
                score -= 2.0; grunde.append(f"Meget høj gæld D/E {debt_equity:.0f}%")

        # ── Gross Margin ────────────────────────────────────
        gross_margin = info.get("grossMargins")
        if gross_margin:
            gm_pct = gross_margin * 100
            if gm_pct > 50:
                score += 1.0; grunde.append(f"Gross margin {gm_pct:.0f}%")
            elif gm_pct > 30:
                score += 0.5; grunde.append(f"Gross margin {gm_pct:.0f}%")

        # ── ROE ─────────────────────────────────────────────
        roe = info.get("returnOnEquity")
        if roe:
            roe_pct = roe * 100
            if roe_pct > 20:
                score += 1.0; grunde.append(f"ROE {roe_pct:.0f}%")
            elif roe_pct > 10:
                score += 0.5; grunde.append(f"ROE {roe_pct:.0f}%")
            elif roe_pct < 0:
                score -= 0.5

        # ── Market cap filter (undgå micro-caps) ────────────
        mkt_cap = info.get("marketCap", 0)
        if mkt_cap and mkt_cap < 1e9:
            score -= 0.5  # Lille selskab = ekstra risiko

        score = round(max(1.0, min(10.0, score)), 1)
        return score, {
            "pe": pe, "forward_pe": forward_pe,
            "rev_growth": round(rev_growth * 100, 1) if rev_growth else None,
            "eps_growth": round(eps_growth * 100, 1) if eps_growth else None,
            "surprise_pct": round(surprise_pct, 1) if surprise_pct else None,
            "fcf_margin": round(fcf_margin, 1) if fcf_margin else None,
            "debt_equity": round(debt_equity, 1) if debt_equity else None,
            "gross_margin": round(gross_margin * 100, 1) if gross_margin else None,
            "roe": round(roe * 100, 1) if roe else None,
            "mkt_cap_mia": round(mkt_cap / 1e9, 1) if mkt_cap else None,
            "grunde": grunde,
        }

    except Exception as e:
        log(f"Fundamental fejl for {ticker}: {e}")
        return None, "Fejl"

# ════════════════════════════════════════════════════════════
# INSIDER TRADING SIGNAL
# ════════════════════════════════════════════════════════════
def hent_insider_signal(ticker):
    """
    Henter insider køb/salg fra SEC Form 4 via SEC EDGAR.
    Insider køb er et af de stærkeste buy-signaler.
    """
    try:
        # Find CIK nummer
        r = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "AI-Aktie-Raadgiver kontakt@eksempel.dk"},
            timeout=8
        )
        cik = None
        for entry in r.json().values():
            if entry["ticker"].upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if not cik:
            return 0.0, "Ingen CIK"

        # Hent seneste Form 4 submissions
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        resp = requests.get(url, headers={"User-Agent": "AI-Aktie-Raadgiver kontakt@eksempel.dk"}, timeout=8)
        data = resp.json()

        # Kig i recent filings efter Form 4
        filings = data.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        dates   = filings.get("filingDate", [])

        insider_koeb  = 0
        insider_salg  = 0
        seneste_30d   = datetime.now() - timedelta(days=30)

        for form, dato in zip(forms, dates):
            if form == "4":
                try:
                    filing_dato = datetime.strptime(dato, "%Y-%m-%d")
                    if filing_dato > seneste_30d:
                        # Simpel heuristik: vi tæller antal Form 4 som proxy
                        # Køb = positivt, salg = negativt (men vi kan ikke skelne uden at parse XML)
                        insider_koeb += 1
                except:
                    pass

        if insider_koeb >= 3:
            return 1.0, f"Mange insider Form 4 ({insider_koeb} sidst 30d)"
        elif insider_koeb >= 1:
            return 0.3, f"Insider aktivitet ({insider_koeb} Form 4)"
        return 0.0, "Ingen insider aktivitet"

    except Exception as e:
        return 0.0, f"Insider fejl: {str(e)[:40]}"

# ════════════════════════════════════════════════════════════
# SHORT INTEREST
# ════════════════════════════════════════════════════════════
def hent_short_interest(ticker):
    """Henter short interest — høj short + positive nyheder = squeeze potential."""
    try:
        info = yf.Ticker(ticker).info
        short_pct = info.get("shortPercentOfFloat")
        if short_pct is None:
            return 0.0, "Ingen short data"
        short_pct_val = short_pct * 100

        if short_pct_val > 20:
            return 0.8, f"Høj short interest {short_pct_val:.1f}% — squeeze potentiale"
        elif short_pct_val > 10:
            return 0.3, f"Moderat short {short_pct_val:.1f}%"
        return 0.0, f"Lav short {short_pct_val:.1f}%"
    except:
        return 0.0, "Ingen short data"

def hent_naeste_earnings(ticker):
    """Hent næste earnings dato fra yfinance."""
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and not cal.empty:
            dato = cal.columns[0]
            return str(dato.date()) if hasattr(dato, 'date') else str(dato)
        earnings_dates = t.earnings_dates
        if earnings_dates is not None and not earnings_dates.empty:
            fremtidige = earnings_dates[earnings_dates.index > pd.Timestamp.now()]
            if not fremtidige.empty:
                return str(fremtidige.index[0].date())
        return None
    except:
        return None

# ════════════════════════════════════════════════════════════
# HURTIG SENTIMENT (nyhedsbaseret)
# ════════════════════════════════════════════════════════════
def hurtig_sentiment(ticker):
    try:
        import feedparser
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={ticker}+stock+earnings")
        pos_ord = ["beat", "surge", "grow", "strong", "record", "upgrade", "buy", "bullish", "profit", "exceeded"]
        neg_ord = ["miss", "fall", "down", "weak", "cut", "downgrade", "sell", "bearish", "loss", "disappoints"]
        pos = sum(1 for e in feed.entries[:8] if any(w in e.title.lower() for w in pos_ord))
        neg = sum(1 for e in feed.entries[:8] if any(w in e.title.lower() for w in neg_ord))
        nettotal = max(1, pos + neg)
        score = (pos - neg) / nettotal
        nyheder = []
        for e in feed.entries[:3]:
            is_pos = any(w in e.title.lower() for w in pos_ord)
            is_neg = any(w in e.title.lower() for w in neg_ord)
            if is_pos or is_neg:
                nyheder.append(("pos" if is_pos else "neg", e.title))
        return round(score, 2), nyheder
    except:
        return 0.0, []

# ════════════════════════════════════════════════════════════
# MARKET SENTIMENT (analyst + options)
# ════════════════════════════════════════════════════════════
def hent_market_sentiment(ticker):
    """Analyst ratings + options flow."""
    try:
        t = yf.Ticker(ticker)
        recs = t.recommendations
        analyst_text = "Ingen analyst data."
        if recs is not None and not recs.empty:
            lr = recs.iloc[-1]
            sb = int(lr.get("Strong Buy", 0))
            b  = int(lr.get("Buy", 0))
            h  = int(lr.get("Hold", 0))
            s  = int(lr.get("Sell", 0))
            ss = int(lr.get("Strong Sell", 0))
            total = sb + b + h + s + ss
            if total > 0:
                bull_pct = (sb + b) / total * 100
                analyst_text = (f"Analyst ({total} ratingsvurderinger): "
                                f"{sb} Strong Buy, {b} Buy, {h} Hold, {s} Sell, {ss} Strong Sell. "
                                f"Bull: {bull_pct:.0f}%")

        try:
            expirations = t.options
            if expirations:
                opt = t.option_chain(expirations[0])
                calls, puts = len(opt.calls), len(opt.puts)
                if calls + puts > 0:
                    pc = puts / (calls + puts)
                    opt_text = f"Options P/C: {pc:.2f} ({calls} calls, {puts} puts, udløb {expirations[0]})"
                else:
                    opt_text = "Ingen options data."
            else:
                opt_text = "Ingen options."
        except:
            opt_text = "Options: fejl."

        return f"{analyst_text}\n{opt_text}"
    except Exception as e:
        return f"Sentiment fejl: {e}"

# ════════════════════════════════════════════════════════════
# POSITION SIZING — forbedret Kelly
# ════════════════════════════════════════════════════════════
def beregn_kelly_rr(prob_pct, entry, stop, target):
    """Ægte Kelly baseret på R/R ratio og sandsynlighed."""
    try:
        p = float(prob_pct) / 100
        q = 1 - p
        b = (float(target) - float(entry)) / (float(entry) - float(stop))
        kelly = (p * b - q) / b
        return max(0.03, min(kelly, 0.30))
    except:
        return None

def beregn_position(score, cash_dkk, cash_usd, er_dansk=False, platform_pref=None, ticker_symbol=None):
    """
    Vælger platform baseret på aktie-type:
    - eToro for alle US-aktier (ingen kommission, brudsaktier)
    - Nordnet for danske aktier (.CO suffix)
    - Endavu for billige danske aktier (.CO, entry < 500 DKK)
    platform_pref override respekteres stadig.
    """
    USD_DKK = 7.0  # Approx kurs til sammenligning på tværs af valutaer

    if score >= 9.0:   kelly = 0.25; begrundelse = "Ekstremt høj conviction"
    elif score >= 8.5: kelly = 0.20; begrundelse = "Meget høj conviction"
    elif score >= 8.0: kelly = 0.15; begrundelse = "Høj conviction"
    elif score >= 7.0: kelly = 0.10; begrundelse = "God conviction"
    elif score >= 6.0: kelly = 0.06; begrundelse = "Moderat conviction"
    else:              kelly = 0.03; begrundelse = "Lav conviction"

    # Hvis bruger angiver specifik platform
    if platform_pref == "nordnet":
        return {"beloeb": min(round(cash_dkk * kelly), int(cash_dkk)), "valuta": "DKK", "platform": "Nordnet", "begrundelse": begrundelse}
    if platform_pref == "endavu":
        return {"beloeb": min(round(cash_dkk * kelly), int(cash_dkk)), "valuta": "DKK", "platform": "Endavu", "begrundelse": begrundelse}
    if platform_pref == "etoro":
        return {"beloeb": min(round(cash_usd * kelly, 2), cash_usd), "valuta": "USD", "platform": "eToro", "begrundelse": begrundelse}

    # Danske aktier (.CO suffix)
    if er_dansk:
        # Endavu til billige danske aktier (entry < 500 DKK)
        try:
            k = hent_kurs(ticker_symbol) if ticker_symbol else None
            if k and k["pris"] < 500:
                endavu_beloeb = min(round(cash_dkk * kelly), int(cash_dkk))
                return {"beloeb": endavu_beloeb, "valuta": "DKK", "platform": "Endavu", "begrundelse": begrundelse}
        except:
            pass
        nordnet_beloeb = min(round(cash_dkk * kelly), int(cash_dkk))
        return {"beloeb": nordnet_beloeb, "valuta": "DKK", "platform": "Nordnet", "begrundelse": begrundelse}

    # US aktier → eToro, cap ved faktisk cash
    beloeb = min(round(cash_usd * kelly, 2), cash_usd)
    return {"beloeb": beloeb, "valuta": "USD", "platform": "eToro", "begrundelse": begrundelse}

# ════════════════════════════════════════════════════════════
# SAMLET SCORE
# ════════════════════════════════════════════════════════════
def beregn_samlet(f, t, s, insider_bonus=0.0, short_bonus=0.0):
    """
    Vægtet kombination:
    45% fundamental + 40% teknisk + 15% sentiment
    + insider/short bonus
    """
    s_norm = (s + 1) / 2 * 10  # Normaliser -1..+1 til 0..10
    samlet = 0.45 * f + 0.40 * t + 0.15 * s_norm
    samlet += insider_bonus + short_bonus
    return round(max(1.0, min(10.0, samlet)), 1)

# ════════════════════════════════════════════════════════════
# RAG — EARNINGS HISTORIK
# ════════════════════════════════════════════════════════════
def hent_earnings_tekst(ticker):
    """Henter regnskabsdata fra Yahoo Finance."""
    try:
        t = yf.Ticker(ticker)
        income = t.income_stmt
        if income is None or income.empty:
            return None

        lines = [f"REGNSKAB FOR {ticker.upper()}", "=" * 40,
                 "Indkomstregnskab (seneste kvartaler):"]

        for idx, row in income.iterrows():
            if row.isna().all():
                continue
            vals = []
            for col, val in row.items():
                if pd.notna(val):
                    if isinstance(val, (int, float)) and abs(val) > 1e9:
                        vals.append(f"{col}: ${val/1e9:.2f}B")
                    elif isinstance(val, (int, float)) and abs(val) > 1e6:
                        vals.append(f"{col}: ${val/1e6:.2f}M")
                    else:
                        vals.append(f"{col}: {val}")
            if vals:
                lines.append(f"  {idx}: {', '.join(vals)}")

        balance = t.balance_sheet
        if balance is not None and not balance.empty:
            lines.append("\nBalance (top 8 linjer):")
            for idx, row in balance.head(8).iterrows():
                if row.isna().all():
                    continue
                vals = []
                for col, val in row.items():
                    if pd.notna(val):
                        if isinstance(val, (int, float)) and abs(val) > 1e9:
                            vals.append(f"{col}: ${val/1e9:.2f}B")
                        elif isinstance(val, (int, float)) and abs(val) > 1e6:
                            vals.append(f"{col}: ${val/1e6:.2f}M")
                        else:
                            vals.append(f"{col}: {val}")
                if vals:
                    lines.append(f"  {idx}: {', '.join(vals)}")

        return "\n".join(lines)
    except Exception as e:
        log(f"Earnings tekst fejl for {ticker}: {e}")
        return None

def gem_earnings_historik(ticker, tekst, dato):
    """Gem i ChromaDB RAG — springes over i sky-miljø."""
    if not CHROMA_TILGAENGELIG or earnings_collection is None:
        return
    try:
        kort = tekst[:3000]
        earnings_collection.add(
            documents=[kort],
            metadatas=[{"ticker": ticker, "date": dato}],
            ids=[f"{ticker}_{datetime.now().timestamp()}"]
        )
    except Exception as e:
        log(f"RAG gem fejl: {e}")

def hent_historisk_kontekst(ticker, limit=4):
    """Søg RAG for historisk guidance og løfter."""
    if not CHROMA_TILGAENGELIG or earnings_collection is None:
        return None
    try:
        results = earnings_collection.query(
            query_texts=["guidance targets revenue forecast management outlook future expectations EPS"],
            n_results=limit,
            where={"ticker": ticker}
        )
        if not results["documents"] or not results["documents"][0]:
            return None
        docs = results["documents"][0]
        datoer = [m.get("date","?") for m in results["metadatas"][0]]
        tekst_dele = []
        for doc, dato in zip(docs, datoer):
            tekst_dele.append(f"[{dato}]: {doc[:400]}")
        return "\n---\n".join(tekst_dele)
    except:
        return None

# ════════════════════════════════════════════════════════════
# GROQ LLM ANALYSE — llama-3.3-70b-versatile
# ════════════════════════════════════════════════════════════
def analyser_med_llama(tekst, ticker, screener_data=None):
    """
    Dyb analyse med Groq llama-3.3-70b-versatile.
    Inkluderer: regnskab, tekniske data, sentiment, RAG historik.
    """
    try:
        market_sentiment = hent_market_sentiment(ticker)
        historik = hent_historisk_kontekst(ticker)

        historik_sektion = ""
        if historik:
            historik_sektion = (
                "\n\n5. HISTORISK GUIDANCE (RAG — sidste kvartaler):\n"
                + historik +
                "\nSpørgsmål: Har ledelsen overholdt tidligere løfter? "
                "Er der mønster af 'guidance inflation' eller positive overraskelser?\n"
            )

        # Tekniske data til prompt
        teknik_sektion = ""
        if screener_data:
            td = screener_data.get("teknik_data", {})
            if td:
                teknik_sektion = (
                    f"\n\n4. TEKNISKE INDIKATORER:\n"
                    f"Pris: ${td.get('pris','?')} | RSI: {td.get('rsi','?')} | "
                    f"MACD: {td.get('macd','?')} | BB%: {td.get('bb_pct','?')}\n"
                    f"SMA20: {td.get('sma20','?')} | SMA50: {td.get('sma50','?')} | SMA200: {td.get('sma200','?')}\n"
                    f"52W High: {td.get('52w_high','?')} | Afstand fra high: {td.get('pct_fra_52w_high','?')}%\n"
                    f"Volume ratio: {td.get('vol_ratio','?')}x | 1M afkast: {td.get('afkast_1m','?')}%\n"
                    f"Tekniske grunde: {', '.join(td.get('grunde',[]))}\n"
                )
            fund_d = screener_data.get("fund_data", {})
            fund_sektion = (
                f"\n\n3. SCREENER SCORES:\n"
                f"Fundamental: {screener_data.get('fundamental','?')}/10 | "
                f"Teknisk: {screener_data.get('teknisk','?')}/10 | "
                f"Samlet: {screener_data.get('samlet','?')}/10\n"
                f"P/E: {fund_d.get('pe','?')} | Fwd P/E: {fund_d.get('forward_pe','?')} | "
                f"Rev-vækst: {fund_d.get('rev_growth','?')}% | EPS-vækst: {fund_d.get('eps_growth','?')}%\n"
                f"FCF margin: {fund_d.get('fcf_margin','?')}% | D/E: {fund_d.get('debt_equity','?')} | "
                f"Gross margin: {fund_d.get('gross_margin','?')}% | ROE: {fund_d.get('roe','?')}%\n"
                f"EPS surprise: {fund_d.get('surprise_pct','?')}%\n"
                f"Fundamental grunde: {', '.join(fund_d.get('grunde',[]))}\n"
            )
        else:
            fund_sektion = ""

        # Hent nuværende pris til kontekst
        pris_nu = ""
        try:
            k = hent_kurs(ticker)
            if k:
                pris_nu = f"NUVÆRENDE MARKEDSPRIS: ${k['pris']} (brug denne som base for ENTRY PRIS)\n"
        except:
            pass

        # Hent seneste nyheder til prompt
        _, nyheder_liste = hurtig_sentiment(ticker)
        nyheds_sektion = ""
        if nyheder_liste:
            nyheder_linjer = "\n".join(f"- [{s.upper()}] {titel}" for s, titel in nyheder_liste)
            nyheds_sektion = f"\n\n6. SENESTE NYHEDER:\n{nyheder_linjer}\n"

        # Hent næste earnings dato
        earnings_dato = hent_naeste_earnings(ticker)
        earnings_sektion = f"\n\n7. NÆSTE EARNINGS DATO: {earnings_dato}\n" if earnings_dato else ""

        prompt = (
            "DU SKAL SVARE I PRÆCIS DETTE FORMAT — INGEN ANDRE ORD:\n\n"
            "ANBEFALING: KØB\n"
            "SCORE: 8\n"
            "SANDSYNLIGHED: 72%\n"
            f"ENTRY PRIS: $180.50\n"
            "STOP LOSS: $168.00\n"
            "TARGET PRIS: $205.00\n"
            "RESUMÉ: Revenue +18% YoY, EPS beat +9%, RSI 52 stigende, stærk FCF.\n"
            "POSITIVE FAKTORER:\n- Revenue vækst +18%\n- EPS beat +9%\n- RSI momentum\n"
            "NEGATIVE FAKTORER:\n- Høj gæld D/E 180\n"
            "ADVARSEL: Overvåg renterisiko\n"
            "TIDSHORISONT: 30-60 dage\n"
            "---\n\n"
            f"ANALYSER NU DENNE AKTIE: {ticker}\n"
            f"{pris_nu}\n"
            "DATA:\n"
            f"=== REGNSKAB ===\n{tekst[:2000]}\n\n"
            f"=== SENTIMENT ===\n{market_sentiment}\n\n"
            f"{fund_sektion}"
            f"{teknik_sektion}"
            f"{historik_sektion}"
            f"{nyheds_sektion}"
            f"{earnings_sektion}"
            "\nVIGTIGT:\n"
            "1. Start DIREKTE med 'ANBEFALING:' — ingen introduktion\n"
            "2. ENTRY PRIS skal være nuværende markedspris ±3%\n"
            "3. STOP LOSS skal altid beskytte max 7% tab fra entry\n"
            "4. TARGET PRIS skal give minimum 2:1 risk/reward ratio\n"
            "5. SCORE = 1-10 heltal\n"
            "6. SANDSYNLIGHED = din confidence i % (tal + % tegn)\n"
            "7. Skriv INTET andet end de 10 linjer i formatet ovenfor\n"
        )

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": (
                    "Du er en senior kvantitativ analytiker hos et top hedgefond med 20 års erfaring. "
                    "Du har slået markedet med 18% p.a. Du er ekstremt præcis, skeptisk og datadrevet. "
                    "Du giver KUN konkrete handelsanbefalinger med eksakte priser."
                )},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=500
        )

        fuld = response.choices[0].message.content.strip()

        # Gem i RAG for fremtidig kontekst
        gem_earnings_historik(ticker, tekst, datetime.now().strftime("%Y-%m-%d"))

        # Gem anbefaling i historik-tabel til backtesting
        _gem_anbefaling_historik(ticker, fuld, screener_data)

        return fuld

    except Exception as e:
        log(f"Groq fejl for {ticker}: {e}")
        return ""

def _gem_anbefaling_historik(ticker, analyse, screener_data):
    """Gem anbefaling i backtest_historik.json til backtesting."""
    try:
        k = hent_kurs(ticker)
        pris = k["pris"] if k else 0
        score = screener_data.get("samlet", 5) if screener_data else 5
        rec_m = re.search(r"ANBEFALING:\s*(\w+)", analyse)
        anbefaling = rec_m.group(1) if rec_m else "UKENDT"

        historik = _safe_json_load(BACKTEST_HISTORIK_FILE) or []
        nyt_id = max((h.get("id",0) for h in historik), default=0) + 1
        historik.append({
            "id": nyt_id, "ticker": ticker,
            "dato": datetime.now().strftime("%Y-%m-%d"),
            "anbefaling": anbefaling, "pris_koeb": pris,
            "score": score, "pris_30d": None, "afkast_30d": None
        })
        with open(BACKTEST_HISTORIK_FILE, "w", encoding="utf-8") as f:
            json.dump(historik, f, ensure_ascii=False, indent=2)
    except:
        pass

def ekstraher_score(analyse):
    if not analyse: return 5
    m = re.search(r"SCORE[:\s]*(\d+)", analyse, re.I)
    return max(1, min(10, int(m.group(1)))) if m else 5

# ════════════════════════════════════════════════════════════
# SCREENER
# ════════════════════════════════════════════════════════════
def koer_screener(hurtig=True):
    makro = hent_makro()
    pf = indlaes_portfolio()
    cash_dkk = pf["cash"].get("nordnet_dkk", 0)
    cash_usd = pf["cash"].get("etoro_usd", 0)

    sektorer = (["Tech", "Finans", "Sundhed", "Dansk"] if hurtig
                else ["Tech", "Finans", "Sundhed", "Forbrug", "Energi", "Industri", "Materialer", "Kommunikation", "Dansk"])

    univers = {
        "Tech":          ["AAPL","MSFT","NVDA","GOOGL","META","AMD","INTC","CRM","ADBE","ORCL",
                          "QCOM","TXN","AMAT","LRCX","KLAC","NOW","PANW","CRWD","SNOW","PLTR",
                          "ASML","TSM","AVGO","MU","ARM","DELL","NXPI","ON","MPWR","MRVL",
                          "SMCI","HPE","STX","WDC","LOGI","ZBRA","EPAM","GDDY","NET","DDOG"],
        "Finans":        ["JPM","BAC","GS","MS","WFC","V","MA","AXP","BLK","SCHW","COF","PYPL",
                          "C","USB","TFC","PNC","ICE","CME","SPGI","MCO","CB","PGR","MET","AFL",
                          "BX","KKR","APO","NDAQ","IBKR"],
        "Sundhed":       ["JNJ","UNH","LLY","PFE","ABBV","MRK","BMY","AMGN","GILD","REGN","ISRG","TMO",
                          "CVS","CI","HUM","ELV","MDT","BSX","SYK","ZTS","VRTX","BIIB","IQV","DGX",
                          "A","MTD","WAT","IDXX","PODD","DXCM"],
        "Forbrug":       ["AMZN","TSLA","HD","MCD","NKE","SBUX","TGT","COST","BKNG","CMG",
                          "TJX","ROST","DG","DLTR","ULTA","YUM","WMT","LOW","EBAY","ETSY","RCL","CCL"],
        "Energi":        ["XOM","CVX","COP","EOG","SLB","PSX","OXY","HAL","BKR","VLO","MPC","DVN"],
        "Industri":      ["CAT","HON","RTX","LMT","UPS","DE","GE","MMM","BA","FDX","CSX","UNP",
                          "NSC","PCAR","EMR","ETN","ROK","PH","ITW","FAST","ODFL","VRSK"],
        "Materialer":    ["LIN","APD","SHW","ECL","NEM","FCX","ALB","DD","PPG","IFF"],
        "Kommunikation": ["NFLX","DIS","CMCSA","T","TMUS","WBD","PARA","SPOT","TTD","ZG"],
        "Dansk":         ["NOVO-B.CO","MAERSK-B.CO","DSV.CO","PNDORA.CO","COLO-B.CO","TRYG.CO",
                          "ORSTED.CO","CARL-B.CO","DEMANT.CO","GN.CO","AMBU-B.CO","RBREW.CO"],
    }

    alle = [(s, t) for s in sektorer for t in univers.get(s, [])]
    res  = []

    for i, (sektor, ticker) in enumerate(alle, 1):
        print(f"[{i}/{len(alle)}] {ticker}", end=" ", flush=True)

        f_s, f_d = fundamental_screening(ticker)
        if f_s is None:
            print(f"→ SKIP ({f_d})")
            continue

        t_s, t_d = teknisk_screening(ticker)
        s_s, nyheder = hurtig_sentiment(ticker)

        # Insider + short bonusser
        insider_bonus, insider_txt = hent_insider_signal(ticker) if not ticker.endswith(".CO") else (0, "")
        short_bonus, short_txt     = hent_short_interest(ticker)  if not ticker.endswith(".CO") else (0, "")
        earnings_dato = hent_naeste_earnings(ticker) if not ticker.endswith(".CO") else None

        # Nedskaler bonusser så de ikke dominerer
        insider_bonus = min(insider_bonus * 0.5, 0.5)
        short_bonus   = min(short_bonus   * 0.3, 0.3)

        samlet = anvend_makro_justering(
            beregn_samlet(f_s, t_s, s_s, insider_bonus, short_bonus), makro
        )

        print(f"→ {samlet:.1f}")
        res.append({
            "ticker":    ticker,
            "sektor":    sektor,
            "samlet":    samlet,
            "fundamental": f_s,
            "teknisk":   t_s,
            "sentiment": s_s,
            "fund_data": f_d if isinstance(f_d, dict) else {},
            "teknik_data": t_d if isinstance(t_d, dict) else {},
            "nyheder":   nyheder,
            "insider":   insider_txt,
            "short":     short_txt,
            "naeste_earnings": earnings_dato,
            "anbefaling": score_til_tekst(samlet, makro),
            "grunde":    (f_d.get("grunde", []) if isinstance(f_d, dict) else []) +
                         (t_d.get("grunde", []) if isinstance(t_d, dict) else []),
            "position":  beregn_position(samlet, cash_dkk, cash_usd, ticker.endswith(".CO")),
        })
        time.sleep(0.15)

    res.sort(key=lambda x: x["samlet"], reverse=True)

    # ── RAG træning: gem historiske regnskaber for top kandidater ──
    log("RAG: Gemmer historik for top kandidater...")
    trained = 0
    for r in res[:10]:
        if r["ticker"].endswith(".CO"):
            continue
        tekst = hent_earnings_tekst(r["ticker"])
        if tekst:
            gem_earnings_historik(r["ticker"], tekst, datetime.now().strftime("%Y-%m-%d"))
            trained += 1
    log(f"RAG: {trained} regnskaber gemt.")

    _gem_json_atomisk(SCREENER_FILE, {
        "dato": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "makro": makro,
        "resultater": res
    })

    kandidater = [r for r in res if r["samlet"] >= 6.5]
    log(f"Screener færdig: {len(res)} aktier, {len(kandidater)} kandidater ≥6.5")
    return res, kandidater

# ════════════════════════════════════════════════════════════
# DYB ANALYSE
# ════════════════════════════════════════════════════════════
def koer_dyb_analyse(kandidater, makro=None):
    if not kandidater:
        return []

    # ── Conviction filter: kun aktier hvor fundamental OG teknisk OG sentiment peger samme vej ──
    stærke = []
    for r in kandidater:
        f = r.get("fundamental", 0)
        t = r.get("teknisk", 0)
        s = r.get("sentiment", 0)
        # Alle tre skal pege i positiv retning — screener-score over 7.0
        if f >= 5.5 and t >= 5.5 and s >= 0 and r["samlet"] >= 7.0:
            stærke.append(r)

    # Sorter og tag de 5 bedste
    stærke.sort(key=lambda x: x["samlet"], reverse=True)
    kandidater_filtreret = stærke[:5]

    if not kandidater_filtreret:
        # Fallback: tag top 3 af de originale hvis ingen passerer conviction-filter
        kandidater_filtreret = sorted(kandidater, key=lambda x: x["samlet"], reverse=True)[:3]

    log(f"Conviction filter: {len(kandidater)} kandidater → {len(kandidater_filtreret)} til dyb analyse")

    # Hent eksisterende holdings sektorer
    pf = indlaes_portfolio()
    ejede_sektorer = {}
    for h in pf.get("holdings", []):
        sektor = h.get("sektor", "")  # may not exist
        if sektor:
            ejede_sektorer[sektor] = ejede_sektorer.get(sektor, 0) + 1

    res = []
    for r in kandidater_filtreret:
        log(f"Dyb analyse: {r['ticker']}")
        tekst = hent_earnings_tekst(r["ticker"])
        if not tekst:
            log(f"  Ingen earnings data for {r['ticker']}, springer over")
            continue
        analyse = analyser_med_llama(tekst, r["ticker"], r)
        if not analyse:
            continue
        llama_s = ekstraher_score(analyse)
        komb    = round((r["samlet"] * 0.5 + llama_s * 0.5), 1)
        if makro:
            komb = anvend_makro_justering(komb, makro)
        # Sektor diversificering: reducer score hvis sektoren allerede er overrepræsenteret
        kandidat_sektor = r.get("sektor", "")
        if ejede_sektorer.get(kandidat_sektor, 0) >= 2:
            komb = round(max(1.0, komb - 0.5), 1)
        res.append({
            "ticker":     r["ticker"],
            "sektor":     r["sektor"],
            "screener":   r["samlet"],
            "llama":      llama_s,
            "kombineret": komb,
            "analyse":    analyse,
            "grunde":     r.get("grunde", []),
            "insider":    r.get("insider", ""),
            "short":      r.get("short", ""),
            "fund_data":  r.get("fund_data", {}),
            "teknik_data": r.get("teknik_data", {}),
        })
        time.sleep(0.5)

    res.sort(key=lambda x: x["kombineret"], reverse=True)
    return res

# ════════════════════════════════════════════════════════════
# FINBERT SENTIMENT
# ════════════════════════════════════════════════════════════
def koer_finbert_sentiment(tickers=None):
    # FinBERT springer over i sky-miljø (for tungt — 500MB model)
    if os.getenv("GITHUB_ACTIONS"):
        log("FinBERT: springer over i GitHub Actions miljø")
        return []
    if not tickers:
        pf = indlaes_portfolio()
        tickers = (
            [h["ticker"] for h in pf["holdings"] if h["type"] == "aktie"]
            + pf["watchlist"]
        )
        tickers = list(set(t for t in tickers if not t.endswith(".CO")))

    log(f"FinBERT sentiment for {len(tickers)} aktier...")
    try:
        from transformers import pipeline
        import feedparser
        finbert = pipeline("sentiment-analysis", model="ProsusAI/finbert", truncation=True)
        res = []
        for ticker in tickers:
            try:
                feed  = feedparser.parse(f"https://news.google.com/rss/search?q={ticker}+stock")
                items = feed.entries[:8]
                if not items:
                    continue
                scores = []
                for e in items:
                    r = finbert(e.title[:512])[0]
                    val = r["score"] if r["label"] == "positive" else -r["score"]
                    scores.append(val)
                avg = round(sum(scores) / len(scores), 3) if scores else 0
                res.append({"ticker": ticker, "score": avg, "antal_nyheder": len(scores)})
                log(f"  {ticker}: FinBERT={avg:+.3f} ({len(scores)} nyheder)")
            except Exception as e:
                log(f"  FinBERT fejl for {ticker}: {e}")
        with open(SENTIMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(res, f)
        log(f"FinBERT færdig: {len(res)} aktier.")
        return res
    except Exception as e:
        log(f"FinBERT setup fejl: {e}")
        return []

# ════════════════════════════════════════════════════════════
# RE-ANALYSE AF AKTIVE HANDLER
# ════════════════════════════════════════════════════════════
def reanalyser_aktive_handler():
    """Re-analyserer alle aktive handler dagligt med friske data."""
    log("Re-analyserer aktive handler...")
    handler = _safe_json_load(AKTIVE_HANDLER_FILE) or []
    aktive = [h for h in handler if h.get("status") == "aktiv"]
    if not aktive:
        log("Ingen aktive handler at re-analysere.")
        return []

    resultater = []
    for h in aktive[:5]:  # Max 5 for at spare Groq-tokens
        ticker = h.get("ticker", "")
        if not ticker:
            continue
        log(f"Re-analyserer: {ticker}")
        try:
            f_s, f_d = fundamental_screening(ticker)
            t_s, t_d = teknisk_screening(ticker)
            s_s, _ = hurtig_sentiment(ticker)
            tekst = hent_earnings_tekst(ticker)

            screener_data = {
                "ticker": ticker, "sektor": h.get("platform",""),
                "fundamental": f_s or 5, "teknisk": t_s or 5, "sentiment": s_s or 0,
                "samlet": round(0.45*(f_s or 5) + 0.40*(t_s or 5) + 0.15*((s_s+1)/2*10), 1),
                "fund_data": f_d if isinstance(f_d, dict) else {},
                "teknik_data": t_d if isinstance(t_d, dict) else {},
            }

            analyse = analyser_med_llama(tekst or "", ticker, screener_data) if tekst else ""

            k = hent_kurs(ticker)
            pris_nu = k["pris"] if k else h.get("koebspris", 0)

            resultater.append({
                "ticker": ticker,
                "handler_id": h.get("id"),
                "koebspris": h.get("koebspris"),
                "pris_nu": pris_nu,
                "afkast": round((pris_nu / h["koebspris"] - 1) * 100, 1) if h.get("koebspris") else 0,
                "stop_loss": h.get("stop_loss"),
                "target": h.get("target"),
                "ny_analyse": analyse,
                "teknisk_score": t_s,
                "fundamental_score": f_s,
                "dato": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            time.sleep(1)
        except Exception as e:
            log(f"Re-analyse fejl for {ticker}: {e}")

    _gem_json_atomisk(os.path.join(DATA_DIR, "reanalyse_seneste.json"), {
        "dato": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "resultater": resultater
    })
    log(f"Re-analyse færdig: {len(resultater)} handler analyseret.")
    return resultater

# ════════════════════════════════════════════════════════════
# DAILY BRIEF
# ════════════════════════════════════════════════════════════
def koer_daily_brief(hurtig=True):
    log("=" * 50)
    log("=== DAILY BRIEF STARTER ===")
    makro  = hent_makro()
    alle, kands = koer_screener(hurtig)
    dybe   = koer_dyb_analyse(kands, makro)
    koer_finbert_sentiment()

    brief = {
        "dato":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "makro":         makro,
        "top_kandidater": dybe,
        "alle_screener": alle[:30],
    }
    _gem_json_atomisk(BRIEF_FILE, brief)

    # Tjek alerts
    _tjek_og_send_alerts(dybe)

    log("=== DAILY BRIEF FÆRDIG ===")
    return brief

# ════════════════════════════════════════════════════════════
# ALERT SYSTEM
# ════════════════════════════════════════════════════════════
def _tjek_og_send_alerts(kandidater):
    """Gem alerts til UI + forsøg desktop notifikation."""
    alerts = []
    for k in kandidater:
        if k.get("kombineret", 0) >= 8.0:
            alerts.append({
                "ticker":  k["ticker"],
                "score":   k["kombineret"],
                "sektor":  k.get("sektor", ""),
                "besked":  f"{k['ticker']} — Score {k['kombineret']} — {score_til_tekst(k['kombineret'])}",
                "tidspunkt": datetime.now().strftime("%Y-%m-%d %H:%M"),
            })

    if alerts:
        with open(ALERT_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts, f)
        log(f"ALERT: {len(alerts)} nye stærke signaler!")

        # Forsøg Windows/Mac desktop notifikation
        try:
            import platform
            if platform.system() == "Windows":
                from plyer import notification
                for a in alerts[:3]:
                    notification.notify(
                        title="AI Aktie Rådgiver",
                        message=a["besked"],
                        timeout=10
                    )
        except:
            pass  # plyer ikke installeret — alert er stadig gemt i fil

def hent_alerts():
    data = _safe_json_load(ALERT_FILE)
    return data if data else []

# ════════════════════════════════════════════════════════════
# BACKTESTING
# ════════════════════════════════════════════════════════════
def koer_backtest():
    """Tjek om tidligere anbefalinger var rigtige — bruger JSON."""
    log("Kører backtest...")
    historik = _safe_json_load(BACKTEST_HISTORIK_FILE) or []
    graense  = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    for item in historik:
        if item.get("afkast_30d") is None and item.get("dato","") <= graense:
            k = hent_kurs(item["ticker"])
            if k:
                pris_nu = k["pris"]
                afkast  = round((pris_nu / item["pris_koeb"] - 1) * 100, 2) if item.get("pris_koeb",0) > 0 else 0
                item["pris_30d"]  = pris_nu
                item["afkast_30d"] = afkast
                log(f"  {item['ticker']}: {item['anbefaling']} → {afkast:+.1f}%")

    with open(BACKTEST_HISTORIK_FILE, "w", encoding="utf-8") as f:
        json.dump(historik, f, ensure_ascii=False, indent=2)

    alle = [x for x in historik if x.get("afkast_30d") is not None]

    if alle:
        koeb_rækker = [r for r in alle if r["anbefaling"] in ["KØB", "STÆRKT KØB"]]
        avg_afkast  = sum(r["afkast_30d"] for r in alle) / len(alle) if alle else 0
        hit_rate    = (sum(1 for r in alle
                          if (r["anbefaling"] in ["KØB","STÆRKT KØB"] and r["afkast_30d"] > 0)
                          or (r["anbefaling"] == "SÆLG" and r["afkast_30d"] < 0))
                       / len(alle) * 100) if alle else 0
        avg_koeb    = (sum(r["afkast_30d"] for r in koeb_rækker) / len(koeb_rækker)
                       if koeb_rækker else 0)

        # Sharpe ratio (simplified: mean/std of returns)
        sharpe = 0.0
        if alle:
            afkast_liste = [r["afkast_30d"] for r in alle]
            std = (sum((x - avg_afkast)**2 for x in afkast_liste) / len(afkast_liste)) ** 0.5
            sharpe = (avg_afkast - 0.4) / std if std > 0 else 0  # 0.4% = månedlig risikofri rente

        # Max drawdown
        max_dd = 0.0
        if alle:
            sorteret = sorted(alle, key=lambda x: x["dato"])
            kumul = 1.0
            peak = 1.0
            for r in sorteret:
                kumul *= (1 + r["afkast_30d"] / 100)
                if kumul > peak:
                    peak = kumul
                dd = (peak - kumul) / peak * 100
                if dd > max_dd:
                    max_dd = dd

        antal_vindere = sum(1 for r in alle if r["anbefaling"] in ["KØB","STÆRKT KØB"] and r["afkast_30d"] > 0)
        antal_tabere  = sum(1 for r in alle if r["anbefaling"] in ["KØB","STÆRKT KØB"] and r["afkast_30d"] <= 0)

        statistik = {
            "antal_anbefalinger":   len(alle),
            "hit_rate_pct":         round(hit_rate, 1),
            "gns_afkast_30d_pct":   round(avg_afkast, 2),
            "gns_afkast_koeb_pct":  round(avg_koeb, 2),
            "sharpe":               round(sharpe, 2),
            "max_drawdown_pct":     round(max_dd, 1),
            "antal_vindere":        antal_vindere,
            "antal_tabere":         antal_tabere,
            "seneste_resultater":   alle[:20],
            "sidst_opdateret":      datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
    else:
        statistik = {
            "antal_anbefalinger": 0,
            "besked": "Ingen anbefalinger er gamle nok til backtest endnu (kræver 30+ dage)",
            "seneste_resultater": [],
        }

    with open(BACKTEST_FILE, "w", encoding="utf-8") as f:
        json.dump(statistik, f, ensure_ascii=False)

    log(f"Backtest færdig: {len(alle)} anbefalinger analyseret")
    return statistik

def hent_backtest_data():
    return _safe_json_load(BACKTEST_FILE)

# ════════════════════════════════════════════════════════════
# UTILITIES
# ════════════════════════════════════════════════════════════
def hent_kurs(ticker):
    try:
        h = yf.Ticker(ticker).history(period="6mo")
        if h.empty:
            return None
        p    = h["Close"].iloc[-1]
        prev = h["Close"].iloc[-2]
        return {"pris": round(float(p), 2), "change": round((float(p) - float(prev)) / float(prev) * 100, 2)}
    except:
        return None

def hent_screener_data():
    return _safe_json_load(SCREENER_FILE)

def hent_brief_data():
    return _safe_json_load(BRIEF_FILE)

# ════════════════════════════════════════════════════════════
# MAIN CLI
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if   cmd == "brief":    koer_daily_brief("--komplet" not in sys.argv)
    elif cmd == "screener": koer_screener("--komplet" not in sys.argv)
    elif cmd == "makro":
        m = hent_makro()
        _gem_json_atomisk(MAKRO_FILE, m)
        print(json.dumps(m, indent=2, ensure_ascii=False))
    elif cmd == "dyb":
        # Hent screener-data og kør dyb analyse — gem resultatet i brief-filen
        data = hent_screener_data()
        if data:
            makro_data = data.get("makro") or hent_makro_data()
            kands = [r for r in data["resultater"] if r["samlet"] >= 6.5]
            log(f"Dyb analyse starter for {len(kands)} kandidater...")
            dybe = koer_dyb_analyse(kands, makro_data)
            # Gem som brief-fil så app.py kan vise resultaterne
            brief = {
                "dato":           datetime.now().strftime("%Y-%m-%d %H:%M"),
                "makro":          makro_data,
                "top_kandidater": dybe,
                "alle_screener":  data["resultater"][:30],
            }
            _gem_json_atomisk(BRIEF_FILE, brief)
            _tjek_og_send_alerts(dybe)
            log(f"Dyb analyse færdig: {len(dybe)} analyseret, gemt i brief-fil.")
        else:
            log("Ingen screener-data fundet — kør 'screener' først.")
    elif cmd == "backtest":   print(json.dumps(koer_backtest(), indent=2, ensure_ascii=False))
    elif cmd == "sentiment":  koer_finbert_sentiment()
    elif cmd == "reanalyser": reanalyser_aktive_handler()
    else:
        print("Brug: brief | screener | makro | dyb | backtest | sentiment | reanalyser")
        print("Flag: --komplet (for fuld scanning)")

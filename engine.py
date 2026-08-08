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
import os, sys, json, time, re, requests, sqlite3, subprocess
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
REANALYSE_FILE     = os.path.join(DATA_DIR, "reanalyse_seneste.json")
ML_TRAINING_FILE   = os.path.join(DATA_DIR, "ml_training_data.json")
ML_MODEL_FILE      = os.path.join(DATA_DIR, "ml_model.pkl")

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
    if not os.path.exists(ML_TRAINING_FILE):
        with open(ML_TRAINING_FILE, "w") as f:
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
        json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)

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
        json.dump(handler, f, ensure_ascii=False, indent=2, default=_json_default)

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
    h["salgs_aarsag"] = aarsag

    with open(AKTIVE_HANDLER_FILE, "w", encoding="utf-8") as f:
        json.dump(handler, f, ensure_ascii=False, indent=2, default=_json_default)

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

    # ── Hent VIX ────────────────────────────────────────────
    vix = None
    for ticker_vix in ["^VIX", "VIX"]:
        try:
            hist = yf.Ticker(ticker_vix).history(period="5d", auto_adjust=False)
            if not hist.empty:
                vix = float(hist["Close"].dropna().iloc[-1])
                if vix > 0:
                    break
        except:
            pass

    if not vix or vix <= 0:
        # Fallback: hent fra Yahoo Finance direkte via requests
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            )
            data = r.json()
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            vix = float([x for x in closes if x is not None][-1])
        except:
            vix = 18.0  # Fornuftig default
            log("VIX fallback til 18.0")

    # ── Hent SP500 ──────────────────────────────────────────
    sp_pris = None
    sp_hist = None
    for ticker_sp in ["^GSPC", "SPY"]:
        try:
            sp_data = yf.Ticker(ticker_sp).history(period="1y", auto_adjust=False)
            if not sp_data.empty and len(sp_data) >= 22:
                sp_hist = sp_data
                sp_pris = float(sp_data["Close"].dropna().iloc[-1])
                break
        except:
            pass

    if sp_pris is None or sp_hist is None:
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=1y",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            )
            data = r.json()
            closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes_clean = [x for x in closes if x is not None]
            sp_pris = float(closes_clean[-1])
            import pandas as pd
            sp_hist = pd.DataFrame({"Close": closes_clean})
        except Exception as e:
            log(f"SP500 fejl: {e}")
            sp_pris = 5500.0
            sp_hist = None

    try:
        sp_sma200 = float(sp_hist["Close"].rolling(200, min_periods=50).mean().iloc[-1]) if sp_hist is not None else sp_pris * 0.95
        sp_sma50  = float(sp_hist["Close"].rolling(50,  min_periods=20).mean().iloc[-1]) if sp_hist is not None else sp_pris * 0.98
        sp_1m     = float((sp_pris / sp_hist["Close"].dropna().iloc[-22] - 1) * 100) if sp_hist is not None and len(sp_hist) >= 22 else 0.0
        sp_trend  = sp_pris > sp_sma200
    except:
        sp_sma200 = sp_pris * 0.95
        sp_sma50  = sp_pris * 0.98
        sp_1m     = 0.0
        sp_trend  = True

    # ── Hent 10-årig rente ──────────────────────────────────
    try:
        tnx = yf.Ticker("^TNX").history(period="5d", auto_adjust=False)
        rente_val = float(tnx["Close"].dropna().iloc[-1]) if not tnx.empty else 4.3
        rente_txt = f"{rente_val:.2f}%"
        rente_advarsel = rente_val > 4.5
    except:
        rente_txt = "4.30%"
        rente_advarsel = False

    # ── Beregn score-justering ──────────────────────────────
    vix_status = "Roligt" if vix < 20 else "Uroligt" if vix < 30 else "PANIK"

    if vix > 30:
        just = -2.5
    elif vix > 25:
        just = -1.5
    elif vix > 20:
        just = -0.5
    else:
        just = 0.0

    if sp_trend and sp_1m > 2:
        just += 0.5

    makro = {
        "vix":           round(vix, 2),
        "vix_status":    vix_status,
        "sp_status":     "Optrend" if sp_trend else "Nedtrend",
        "sp_pris":       round(sp_pris, 2),
        "sp_sma200":     round(sp_sma200, 2),
        "sp_sma50":      round(sp_sma50, 2),
        "sp_1m_afkast":  round(sp_1m, 2),
        "rente_10y":     rente_txt,
        "rente_advarsel": rente_advarsel,
        "justering":     round(just, 2),
        "stop_koeb":     vix > 30,
        "forsigtig":     vix > 25,
    }

    with open(MAKRO_FILE, "w", encoding="utf-8") as f:
        json.dump(makro, f, ensure_ascii=False, default=_json_default)

    log(f"Makro OK: VIX={vix:.1f} ({vix_status}), SP500={'Optrend' if sp_trend else 'Nedtrend'} ({sp_1m:+.1f}% 1M), Rente={rente_txt}, Justering={just:+.1f}")
    return makro

def sp_status_str(m):
    return m.get("sp_status","") + f" ({m.get('sp_1m_afkast',0):+.1f}% 1M)"


def _json_default(o):
    """
    Fallback for json.dump: konverterer numpy/pandas-skalarer (numpy.bool_,
    numpy.integer, numpy.floating) til native Python-typer.

    Uden denne kan et enkelt numpy.bool_ der sniger sig ind i et resultat
    (fx fra en sammenligning mellem en Python-float og en ukonverteret
    pandas/numpy-skalar) vælte HELE screener-kørslen efter flere minutters
    arbejde, fordi json.dump fejler på selve skrive-trinnet til sidst.
    """
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

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

# Simpel in-memory cache for SPY-serien — genbruges på tværs af alle tickers
# i én screener-kørsel, så vi ikke henter SPY 100+ gange.
_spy_cache = {}
def _hent_spy_serie():
    if "close" not in _spy_cache:
        try:
            h = yf.Ticker("SPY").history(period="1y")
            _spy_cache["close"] = h["Close"] if not h.empty else None
        except Exception:
            _spy_cache["close"] = None
    return _spy_cache["close"]

def teknisk_screening(ticker):
    """
    Fuld teknisk analyse med:
    - RSI (14), MACD, Bollinger Bands
    - SMA20/50/200 trend
    - Volume spike detection
    - 52-ugers breakout signal
    """
    try:
        yft  = yf.Ticker(ticker)
        hist = yft.history(period="1y")
        if hist.empty or len(hist) < 30:
            return 5.0, {}

        close  = hist["Close"]
        volume = hist["Volume"]
        pris   = float(close.iloc[-1])

        score  = 5.0
        grunde = []
        detaljer = {"pris": round(pris, 2)}

        # ── SMA trend ──────────────────────────────────────
        # float() her er vigtigt: numpy-skalarer sammenlignet med Python-floats
        # kan give numpy.bool_ i stedet for bool, som json.dump ikke kan serialisere.
        sma20  = float(close.rolling(20).mean().iloc[-1])
        sma50  = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        detaljer["sma20"]  = round(float(sma20), 2)
        detaljer["sma50"]  = round(float(sma50), 2)
        detaljer["sma200"] = round(float(sma200), 2)

        if pris > sma200:
            score += 1.0
            grunde.append("Over SMA200")
        else:
            score -= 1.0
            grunde.append("Under SMA200 (nedtrend)")
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

            # Volume confirmation: en breakout uden volumen over gennemsnit er svag
            volumen_bekraeftet = bool(vol_ratio >= 1.0)
            if pct_fra_high > -3:
                if volumen_bekraeftet:
                    score += 1.5
                    grunde.append(f"Nær 52-ugers high ({pct_fra_high:.1f}%), bekræftet af volumen {vol_ratio:.1f}x")
                else:
                    score += 0.3
                    grunde.append(f"Nær 52-ugers high ({pct_fra_high:.1f}%) men svagt volumen ({vol_ratio:.1f}x) — usikker breakout")
            elif pct_fra_high > -10:
                score += 0.5 if volumen_bekraeftet else 0.2
                grunde.append(f"Stærk position ({pct_fra_high:.1f}% fra high)")
            elif pct_fra_high < -40:
                score -= 1.0
                grunde.append(f"Langt fra 52-ugers high ({pct_fra_high:.1f}%)")
        else:
            detaljer["pct_fra_52w_high"] = None

        # ── Trend styrke (ADX-proxy) ────────────────────────
        afkast_1m = float((pris / close.iloc[-22] - 1) * 100) if len(close) >= 22 else 0
        afkast_3m = float((pris / close.iloc[-66] - 1) * 100) if len(close) >= 66 else 0
        afkast_5d = float((pris / close.iloc[-6] - 1) * 100) if len(close) >= 6 else 0
        detaljer["afkast_1m"] = round(afkast_1m, 1)
        detaljer["afkast_3m"] = round(afkast_3m, 1)
        detaljer["afkast_5d"] = round(afkast_5d, 1)

        if afkast_1m > 5 and afkast_3m > 10:
            score += 0.5
            grunde.append(f"Momentum: +{afkast_1m:.1f}% 1M / +{afkast_3m:.1f}% 3M")

        # ── Relativ styrke mod SP500 ─────────────────────────
        # Det vigtigste enkelt-signal: klarer aktien sig bedre end markedet?
        rs_vs_sp500 = None
        try:
            spy_close = _hent_spy_serie()
            if spy_close is not None and len(spy_close) >= 66 and len(close) >= 66:
                spy_pris = float(spy_close.iloc[-1])
                spy_3m   = float((spy_pris / spy_close.iloc[-66] - 1) * 100)
                rs_vs_sp500 = round(afkast_3m - spy_3m, 1)
        except Exception:
            pass
        detaljer["rs_vs_sp500"] = rs_vs_sp500
        if rs_vs_sp500 is not None:
            if rs_vs_sp500 > 10:
                score += 1.5
                grunde.append(f"Meget stærkere end SP500 ({rs_vs_sp500:+.1f}pp over 3M)")
            elif rs_vs_sp500 > 3:
                score += 0.75
                grunde.append(f"Stærkere end SP500 ({rs_vs_sp500:+.1f}pp over 3M)")
            elif rs_vs_sp500 < -10:
                score -= 1.5
                grunde.append(f"Meget svagere end SP500 ({rs_vs_sp500:+.1f}pp under 3M)")
            elif rs_vs_sp500 < -3:
                score -= 0.75
                grunde.append(f"Svagere end SP500 ({rs_vs_sp500:+.1f}pp under 3M)")

        # ── Earnings-kalender: undgå at købe inden regnskab ─────
        # Professionel regel: undgå 3 uger FØR earnings (høj usikkerhed)
        earnings_ok = True
        dage_til_earnings = None
        try:
            edates = yft.get_earnings_dates(limit=8)
            if edates is not None and not edates.empty:
                now_ts = pd.Timestamp.now(tz=edates.index.tz)
                fremtidige = edates.index[edates.index >= now_ts]
                if len(fremtidige) > 0:
                    dage_til_earnings = (fremtidige.min() - now_ts).days
                    if dage_til_earnings <= 21:
                        earnings_ok = False
        except Exception:
            pass
        detaljer["dage_til_earnings"] = dage_til_earnings
        detaljer["earnings_ok"] = earnings_ok
        if not earnings_ok:
            grunde.append(f"Regnskab om {dage_til_earnings} dag(e) — undgå køb 3 uger før")

        # ── YTD afkast (år-til-dato) ─────────────────────────
        ytd_rows = close[close.index.year == datetime.now().year]
        ytd_afkast = None
        if len(ytd_rows) > 0:
            ytd_start = float(ytd_rows.iloc[0])
            if ytd_start > 0:
                ytd_afkast = round((pris / ytd_start - 1) * 100, 1)
        detaljer["ytd_afkast"] = ytd_afkast

        # ── Hård trend-filter: undgå aktier i nedtrend ───────
        # (fx BMY -15% YTD der blev anbefalt flere dage i træk)
        trend_ok = bool((pris > sma200) and (ytd_afkast is None or ytd_afkast > 0))
        detaljer["trend_ok"] = trend_ok
        if not trend_ok:
            grunde.append(f"NEDTREND — diskvalificeret (under SMA200 og/eller YTD {ytd_afkast}%)")

        # ── Momentum-krav: positivt 1M afkast OG positiv 5-dages trend ──
        momentum_ok = bool((afkast_1m > 0) and (afkast_5d > 0))
        detaljer["momentum_ok"] = momentum_ok
        if not momentum_ok:
            grunde.append(f"Svagt momentum — 1M {afkast_1m:+.1f}% / 5D {afkast_5d:+.1f}%")

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
def hent_circuit_breaker_faktor():
    """
    Reducerer positionsstørrelser hvis systemets seneste lukkede handler har
    tabt penge. Beskytter mod at blive ved med at satse fuldt ud gennem en
    tabsstime — uanset hvor overbevist scoringen ser ud på papiret.
    """
    handler = _safe_json_load(AKTIVE_HANDLER_FILE) or []
    solgte  = [h for h in handler if h.get("status") == "solgt" and h.get("afkast_pct") is not None]
    seneste = sorted(solgte, key=lambda h: h.get("dato_solgt", ""), reverse=True)[:10]

    if len(seneste) < 5:
        return 1.0, "Ikke nok lukkede handler endnu til cirkelbryderen (kræver 5+)"

    hit_rate = sum(1 for h in seneste if h["afkast_pct"] > 0) / len(seneste)
    gns      = sum(h["afkast_pct"] for h in seneste) / len(seneste)

    if hit_rate < 0.30 and gns < -5:
        return 0.25, f"CIRKELBRYDER AKTIV: {hit_rate*100:.0f}% hit-rate, {gns:+.1f}% snit på seneste {len(seneste)} handler — positioner skåret til 25%"
    elif hit_rate < 0.40 or gns < -2:
        return 0.50, f"Forsigtig: {hit_rate*100:.0f}% hit-rate, {gns:+.1f}% snit på seneste {len(seneste)} handler — positioner skåret til 50%"
    return 1.0, f"Normal: {hit_rate*100:.0f}% hit-rate på seneste {len(seneste)} handler"

def beregn_position(score, cash_dkk, cash_usd, er_dansk=False, platform_pref=None, circuit_faktor=1.0):
    """
    Forbedret Kelly-lignende position sizing.
    Tre platforme: Nordnet (DKK), eToro (USD), Endavu (DKK).

    Kelly-lofterne er bevidst holdt lave (max 10%) — et system uden lang
    dokumenteret track record bør aldrig satse store andele af kapitalen på
    én enkelt aktie, uanset hvor høj scoren ser ud.
    """
    # Kelly fraktioner baseret på conviction — konservative lofter
    if score >= 9.0:
        kelly = 0.10; begrundelse = "Ekstremt høj conviction"
    elif score >= 8.5:
        kelly = 0.08; begrundelse = "Meget høj conviction"
    elif score >= 8.0:
        kelly = 0.06; begrundelse = "Høj conviction"
    elif score >= 7.0:
        kelly = 0.04; begrundelse = "God conviction"
    elif score >= 6.0:
        kelly = 0.02; begrundelse = "Moderat conviction"
    else:
        kelly = 0.01; begrundelse = "Lav conviction"

    kelly *= circuit_faktor
    if circuit_faktor < 1.0:
        begrundelse += f" (cirkelbryder × {circuit_faktor:.2f})"

    if er_dansk or platform_pref == "nordnet":
        beloeb = round(cash_dkk * kelly)
        return {"beloeb": beloeb, "valuta": "DKK", "platform": "Nordnet", "begrundelse": begrundelse}

    if platform_pref == "endavu":
        endavu_dkk = cash_dkk  # Endavu bruger DKK
        beloeb = round(endavu_dkk * kelly)
        return {"beloeb": beloeb, "valuta": "DKK", "platform": "Endavu", "begrundelse": begrundelse}

    # Standard: eToro hvis der er USD, ellers Nordnet
    if cash_usd >= 50:
        return {"beloeb": round(cash_usd * kelly, 2), "valuta": "USD",
                "platform": "eToro", "begrundelse": begrundelse}
    else:
        return {"beloeb": round(cash_dkk * kelly), "valuta": "DKK",
                "platform": "Nordnet", "begrundelse": begrundelse}

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

        # Anti-repetitions advarsel til LLM'en
        gange_anbefalet = screener_data.get("gange_anbefalet_5d", 0) if screener_data else 0
        repetitions_sektion = ""
        if gange_anbefalet > 0:
            repetitions_sektion = (
                f"\n\nADVARSEL — REPETITION: {ticker} er allerede anbefalt {gange_anbefalet} "
                f"gang(e) de seneste 5 dage. Anbefal KUN igen hvis der er en KONKRET NY katalysator "
                f"siden sidst (nyt regnskab, opdateret guidance, nyt teknisk signal). "
                f"Er der ingen ny katalysator, sæt ANBEFALING til HOLD og sænk SCORE.\n"
            )

        # Hent nuværende pris til kontekst
        pris_nu = ""
        try:
            k = hent_kurs(ticker)
            if k:
                pris_nu = f"NUVÆRENDE MARKEDSPRIS: ${k['pris']} (brug denne som base for ENTRY PRIS)\n"
        except:
            pass

        prompt = (
            "DU SKAL SVARE I PRÆCIS DETTE FORMAT — INGEN ANDRE ORD:\n\n"
            "ANBEFALING: KØB\n"
            "SCORE: 7.3\n"
            "SANDSYNLIGHED: 62%\n"
            f"ENTRY PRIS: $180.50\n"
            "STOP LOSS: $165.00\n"
            "TARGET PRIS: $205.00\n"
            "RESUMÉ: Revenue +18% YoY men EPS-vækst aftager. RSI 52 neutral. FCF stærk.\n"
            "POSITIVE FAKTORER:\n- Revenue vækst +18%\n- EPS beat +9%\n"
            "NEGATIVE FAKTORER:\n- Høj gæld D/E 180\n- RSI ikke overbevisende\n"
            "ADVARSEL: Høj gæld — sælg hvis renten stiger\n"
            "TIDSHORISONT: 30-60 dage\n"
            "---\n\n"
            f"ANALYSER NU DENNE AKTIE: {ticker}\n"
            f"{pris_nu}\n"
            "DATA:\n"
            f"=== REGNSKAB ===\n{tekst[:2000]}\n\n"
            f"=== SENTIMENT + ANALYST ===\n{market_sentiment}\n\n"
            f"{fund_sektion}"
            f"{teknik_sektion}"
            f"{historik_sektion}"
            f"{repetitions_sektion}"
            "\nKRITISKE REGLER — læs disse nøje:\n"
            "1. Start DIREKTE med 'ANBEFALING:' — ingen introduktion overhovedet\n"
            "2. SCORE skal ALTID have ÉN decimal (fx 6.3, 7.8, 8.2) — ALDRIG hele tal som '7' eller '8'. "
            "Brug hele skalaen 1.0-10.0. Score 9.0-10.0 kun hvis ALT peger op. "
            "Score 7.0-8.9 for gode aktier. Score 5.0-6.9 for neutrale. Score under 5.0 for problematiske. "
            "To forskellige aktier må IKKE få samme score medmindre deres data er identiske — "
            "differentiér på baggrund af de konkrete tal i data (P/E, RSI, momentum, vækst osv.).\n"
            "3. SANDSYNLIGHED skal afspejle din usikkerhed: "
            "Markedet er uforudsigeligt. Brug 55-70% for normale tilfælde. "
            "Over 80% kun ved ekstraordinære setup. Aldrig 85% på alt.\n"
            "4. ENTRY PRIS = nuværende markedspris ±2%\n"
            "5. STOP LOSS = 7-10% under entry (sæt det præcist ved teknisk støtte)\n"
            "6. TARGET PRIS = realistisk kursmål baseret på fundamental fair value\n"
            "7. Vær KRITISK — det er bedre at sige HOLD end at give falsk KØB-signal\n"
            "8. Skriv INTET andet end de 10 linjer i formatet\n"
        )

        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": (
                    "Du er en trading-algoritme. Du returnerer KUN strukturerede handelsanbefalinger "
                    "i det præcise format du får vist. Aldrig fri tekst. Aldrig introduktioner. "
                    "Din første linje er altid 'ANBEFALING:' efterfulgt af KØB, SÆLG eller HOLD."
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
            json.dump(historik, f, ensure_ascii=False, indent=2, default=_json_default)
    except:
        pass

def ekstraher_score(analyse):
    if not analyse: return 5.0
    m = re.search(r"SCORE[:\s]*(\d+(?:[.,]\d+)?)", analyse, re.I)
    if not m:
        return 5.0
    val = float(m.group(1).replace(",", "."))
    return round(max(1.0, min(10.0, val)), 1)

# ════════════════════════════════════════════════════════════
# ML-MODEL — trænet model der erstatter/supplerer den håndtunede formel
# ════════════════════════════════════════════════════════════
# Data logges hver dag for ALLE screenede tickers (ikke kun de anbefalede),
# så vi får langt flere trænings-eksempler. koer_backtest() udfylder senere
# "afkast_30d" og "label" når 30 dage er gået. Modellen trænes først når der
# er nok labelled data til at det giver statistisk mening.
ML_MIN_TRAENINGS_EKSEMPLER = 50  # under denne grænse bruges kun heuristikken
_ML_MODEL_CACHE = {"model": None, "forsoegt": False}

ML_FEATURE_NAVNE = [
    "fundamental", "teknisk", "sentiment",
    "pe", "forward_pe", "rev_growth", "eps_growth", "fcf_margin",
    "debt_equity", "gross_margin", "roe", "surprise_pct",
    "rsi", "macd", "bb_pct", "vol_ratio", "pct_fra_52w_high",
    "afkast_1m", "afkast_3m", "afkast_5d", "ytd_afkast", "rs_vs_sp500",
    "vix", "sp_1m_afkast",
]

def _byg_ml_features(f_s, t_s, s_s, f_d, t_d, makro):
    """Flad numerisk feature-vektor til ML-modellen. Manglende data → 0.0."""
    def g(d, k, default=0.0):
        v = (d or {}).get(k, default)
        return float(v) if isinstance(v, (int, float)) and not _er_nan(v) else default

    def _er_nan(v):
        try:
            return v != v  # NaN != NaN
        except Exception:
            return False

    return {
        "fundamental":     float(f_s or 0),
        "teknisk":         float(t_s or 0),
        "sentiment":       float(s_s or 0),
        "pe":              g(f_d, "pe"),
        "forward_pe":      g(f_d, "forward_pe"),
        "rev_growth":      g(f_d, "rev_growth"),
        "eps_growth":      g(f_d, "eps_growth"),
        "fcf_margin":      g(f_d, "fcf_margin"),
        "debt_equity":     g(f_d, "debt_equity"),
        "gross_margin":    g(f_d, "gross_margin"),
        "roe":             g(f_d, "roe"),
        "surprise_pct":    g(f_d, "surprise_pct"),
        "rsi":             g(t_d, "rsi", 50.0),
        "macd":            g(t_d, "macd"),
        "bb_pct":          g(t_d, "bb_pct", 0.5),
        "vol_ratio":       g(t_d, "vol_ratio", 1.0),
        "pct_fra_52w_high": g(t_d, "pct_fra_52w_high", -20.0),
        "afkast_1m":       g(t_d, "afkast_1m"),
        "afkast_3m":       g(t_d, "afkast_3m"),
        "afkast_5d":       g(t_d, "afkast_5d"),
        "ytd_afkast":      g(t_d, "ytd_afkast"),
        "rs_vs_sp500":     g(t_d, "rs_vs_sp500"),
        "vix":             float((makro or {}).get("vix", 0) or 0),
        "sp_1m_afkast":    float((makro or {}).get("sp_1m_afkast", 0) or 0),
    }

def backfill_ml_training_fra_git_historik():
    """
    Miner tidligere data/screener_seneste.json-snapshots fra git-historikken
    for at genskabe trænings-eksempler RETROAKTIVT, i stedet for at vente 30
    dage fra i dag på hvert eneste eksempel. Hver daglig scanning er allerede
    committet til repoet siden systemet startede — den historik indeholder
    fuld fundamental/teknisk data og kan bruges med det samme, fordi mange af
    de gamle dage allerede er 30+ dage gamle og derfor har et kendt outcome.

    Kør denne ÉN GANG efter deploy for at give ML-modellen et hovedspring i
    stedet for at starte fra nul.
    """
    try:
        ud = subprocess.run(
            ["git", "log", "--follow", "--format=%H|%ad", "--date=format:%Y-%m-%d",
             "--", "data/screener_seneste.json"],
            cwd=BASE_DIR, capture_output=True, text=True, timeout=60,
        )
    except Exception as e:
        log(f"Backfill: kunne ikke læse git-historik: {e}")
        return 0

    linjer = [l for l in ud.stdout.strip().split("\n") if l]
    if not linjer:
        log("Backfill: ingen git-historik fundet for screener_seneste.json")
        return 0

    eksisterende = _safe_json_load(ML_TRAINING_FILE) or []
    kendte_noegler = {(r["ticker"], r["dato"]) for r in eksisterende}

    nye = []
    for linje in linjer:
        sha, commit_dato = linje.split("|", 1)
        try:
            r = subprocess.run(["git", "show", f"{sha}:data/screener_seneste.json"],
                                cwd=BASE_DIR, capture_output=True, text=True, timeout=30)
            data = json.loads(r.stdout)
        except Exception:
            continue

        makro = data.get("makro", {})
        dato  = (data.get("dato") or commit_dato)[:10] or commit_dato

        for res in data.get("resultater", []):
            ticker = res.get("ticker")
            if not ticker or (ticker, dato) in kendte_noegler:
                continue
            f_d = res.get("fund_data", {}) or {}
            t_d = res.get("teknik_data", {}) or {}
            features = _byg_ml_features(res.get("fundamental"), res.get("teknisk"),
                                         res.get("sentiment"), f_d, t_d, makro)
            nye.append({
                "ticker": ticker, "dato": dato, "pris_ved_log": t_d.get("pris", 0),
                "features": features, "afkast_30d": None, "label": None,
            })
            kendte_noegler.add((ticker, dato))

    alle = eksisterende + nye
    with open(ML_TRAINING_FILE, "w", encoding="utf-8") as f:
        json.dump(alle, f, ensure_ascii=False, default=_json_default)
    log(f"Backfill: {len(nye)} historiske trænings-eksempler tilføjet fra {len(linjer)} git-snapshots "
        f"(i alt {len(alle)} eksempler i ML_TRAINING_FILE)")
    return len(nye)

def gem_ml_traeningseksempel(ticker, dato, pris, features):
    """Logger dagens feature-vektor. Label/afkast udfyldes senere af koer_backtest()."""
    try:
        data = _safe_json_load(ML_TRAINING_FILE) or []
        data.append({
            "ticker": ticker, "dato": dato, "pris_ved_log": pris,
            "features": features, "afkast_30d": None, "label": None,
        })
        # Undgå ubegrænset vækst — behold seneste ~2 års daglige logs
        if len(data) > 100_000:
            data = data[-100_000:]
        with open(ML_TRAINING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=_json_default)
    except Exception as e:
        log(f"ML-log fejl for {ticker}: {e}")

def _opdater_ml_labels():
    """Udfylder afkast_30d/label for trænings-eksempler der er ≥30 dage gamle."""
    data = _safe_json_load(ML_TRAINING_FILE) or []
    graense = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    opdateret = 0
    for row in data:
        if row.get("afkast_30d") is None and row.get("dato", "") <= graense:
            k = hent_kurs(row["ticker"])
            if k and row.get("pris_ved_log", 0) > 0:
                afkast = round((k["pris"] / row["pris_ved_log"] - 1) * 100, 2)
                row["afkast_30d"] = afkast
                row["label"] = 1 if afkast > 0 else 0
                opdateret += 1
    if opdateret:
        with open(ML_TRAINING_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=_json_default)
    log(f"ML-labels opdateret: {opdateret} nye eksempler fik outcome")
    return data

def train_ml_model():
    """
    Træner en logistisk regressionsmodel på historiske feature/outcome-par.
    Kører kun hvis vi har nok labelled data (ML_MIN_TRAENINGS_EKSEMPLER) —
    ellers beholder vi den håndtunede formel, som er langt mere robust
    når data er sparsom.
    """
    data = _opdater_ml_labels()
    labelled = [r for r in data if r.get("label") is not None]

    if len(labelled) < ML_MIN_TRAENINGS_EKSEMPLER:
        log(f"ML-træning sprunget over: kun {len(labelled)}/{ML_MIN_TRAENINGS_EKSEMPLER} labelled eksempler endnu")
        return None

    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import cross_val_score
    except ImportError:
        log("ML-træning sprunget over: scikit-learn ikke installeret")
        return None

    X = np.array([[r["features"].get(k, 0.0) for k in ML_FEATURE_NAVNE] for r in labelled])
    y = np.array([r["label"] for r in labelled])

    pipeline = Pipeline([
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])

    try:
        cv_scores = cross_val_score(pipeline, X, y, cv=min(5, len(labelled) // 10 or 2))
        log(f"ML-model cross-val accuracy: {cv_scores.mean():.2f} (±{cv_scores.std():.2f}) på {len(labelled)} eksempler")
    except Exception as e:
        log(f"ML cross-val fejl (træner alligevel): {e}")

    pipeline.fit(X, y)

    import pickle
    with open(ML_MODEL_FILE, "wb") as f:
        pickle.dump({"pipeline": pipeline, "feature_navne": ML_FEATURE_NAVNE,
                     "traenet_dato": datetime.now().strftime("%Y-%m-%d"),
                     "antal_eksempler": len(labelled)}, f)
    log(f"ML-model trænet og gemt: {len(labelled)} eksempler")
    return pipeline

def hent_ml_score(features):
    """Returnerer ML-modellens sandsynlighed for positivt 30-dages afkast (0-1), eller None."""
    if not _ML_MODEL_CACHE["forsoegt"]:
        _ML_MODEL_CACHE["forsoegt"] = True
        if os.path.exists(ML_MODEL_FILE):
            try:
                import pickle
                with open(ML_MODEL_FILE, "rb") as f:
                    pakke = pickle.load(f)
                _ML_MODEL_CACHE["model"] = pakke
            except Exception as e:
                log(f"Kunne ikke indlæse ML-model: {e}")

    pakke = _ML_MODEL_CACHE["model"]
    if not pakke:
        return None
    try:
        x = np.array([[features.get(k, 0.0) for k in pakke["feature_navne"]]])
        return float(pakke["pipeline"].predict_proba(x)[0][1])
    except Exception as e:
        log(f"ML-score fejl: {e}")
        return None

# ════════════════════════════════════════════════════════════
# STOP-LOSS COOLDOWN
# ════════════════════════════════════════════════════════════
def hent_stop_loss_cooldown(dage=30):
    """
    Tickers der ramte stop-loss inden for de seneste `dage` dage.
    Disse skal ikke genanbefales før cooldown-perioden er ovre.
    """
    handler = _safe_json_load(AKTIVE_HANDLER_FILE) or []
    graense = (datetime.now() - timedelta(days=dage)).strftime("%Y-%m-%d")
    cooldown = set()
    for h in handler:
        if (h.get("status") == "solgt"
                and str(h.get("salgs_aarsag", "")).lower().startswith("stop-loss")
                and h.get("dato_solgt", "") >= graense):
            cooldown.add(h["ticker"])
    return cooldown

# ════════════════════════════════════════════════════════════
# SEKTOR-ROTATION
# ════════════════════════════════════════════════════════════
SEKTOR_ETF = {
    "Tech": "XLK", "Finans": "XLF", "Sundhed": "XLV", "Forbrug": "XLY",
    "Energi": "XLE", "Industri": "XLI", "Kommunikation": "XLC",
}

def hent_sektor_rotation():
    """
    Rangerer sektorer efter 1-måneds performance via sektor-ETFer.
    De stærkeste sektorer får en bonus, de svageste en straf —
    så vi prioriterer aktier i sektorer der klarer sig godt lige nu.
    """
    afkast = {}
    for sektor, etf in SEKTOR_ETF.items():
        try:
            h = yf.Ticker(etf).history(period="2mo")
            if len(h) >= 22:
                pris    = float(h["Close"].iloc[-1])
                pris_1m = float(h["Close"].iloc[-22])
                afkast[sektor] = round((pris / pris_1m - 1) * 100, 1)
        except Exception:
            continue

    if not afkast:
        return {"afkast": {}, "bonus": {}}

    sorteret = sorted(afkast.items(), key=lambda x: x[1], reverse=True)
    n = len(sorteret)
    top_bund = max(1, n // 3)
    bonus = {}
    for i, (sektor, _) in enumerate(sorteret):
        if i < top_bund:
            bonus[sektor] = 0.5
        elif i >= n - top_bund:
            bonus[sektor] = -0.5
        else:
            bonus[sektor] = 0.0

    log(f"Sektor-rotation (1M afkast): {sorteret}")
    return {"afkast": afkast, "bonus": bonus}

# ════════════════════════════════════════════════════════════
# SCREENER
# ════════════════════════════════════════════════════════════
def koer_screener(hurtig=True):
    makro = hent_makro()
    pf = indlaes_portfolio()
    cash_dkk = pf["cash"].get("nordnet_dkk", 0)
    cash_usd = pf["cash"].get("etoro_usd", 0)

    sektor_rot = hent_sektor_rotation()
    stop_loss_cooldown = hent_stop_loss_cooldown()
    if stop_loss_cooldown:
        log(f"Stop-loss cooldown: {len(stop_loss_cooldown)} tickers udelukket i 30 dage: {sorted(stop_loss_cooldown)}")

    circuit_faktor, circuit_besked = hent_circuit_breaker_faktor()
    log(f"Cirkelbryder: {circuit_besked}")

    sektorer = (["Tech", "Finans", "Sundhed", "Dansk"] if hurtig
                else ["Tech", "Finans", "Sundhed", "Forbrug", "Energi", "Industri", "Kommunikation", "Dansk"])

    univers = {
        "Tech":          ["AAPL","MSFT","NVDA","GOOGL","META","AMD","INTC","CRM","ADBE","ORCL",
                          "QCOM","TXN","AMAT","LRCX","KLAC","NOW","PANW","CRWD","SNOW","PLTR"],
        "Finans":        ["JPM","BAC","GS","MS","WFC","V","MA","AXP","BLK","SCHW","COF","PYPL"],
        "Sundhed":       ["JNJ","UNH","LLY","PFE","ABBV","MRK","BMY","AMGN","GILD","REGN","ISRG","TMO"],
        "Forbrug":       ["AMZN","TSLA","HD","MCD","NKE","SBUX","TGT","COST","BKNG","CMG"],
        "Energi":        ["XOM","CVX","COP","EOG","SLB","PSX"],
        "Industri":      ["CAT","HON","RTX","LMT","UPS","DE","GE","MMM"],
        "Kommunikation": ["NFLX","DIS","CMCSA","T","TMUS","GOOGL","META"],
        "Dansk":         ["NOVO-B.CO","MAERSK-B.CO","DSV.CO","PNDORA.CO","COLO-B.CO","TRYG.CO"],
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

        # Nedskaler bonusser så de ikke dominerer
        insider_bonus = min(insider_bonus * 0.5, 0.5)
        short_bonus   = min(short_bonus   * 0.3, 0.3)

        samlet = anvend_makro_justering(
            beregn_samlet(f_s, t_s, s_s, insider_bonus, short_bonus), makro
        )

        # ── Momentum bonus: aktier med stærkt positivt momentum ──────
        td = t_d if isinstance(t_d, dict) else {}
        afkast_1m = td.get("afkast_1m", 0) or 0
        afkast_3m = td.get("afkast_3m", 0) or 0
        pct_fra_high = td.get("pct_fra_52w_high", -50) or -50
        import math as _math
        if not _math.isnan(float(afkast_1m if afkast_1m else 0)):
            if afkast_1m > 10 and afkast_3m > 15:
                samlet = min(10.0, samlet + 0.3)  # Stærkt momentum
            elif afkast_1m < -15:
                samlet = max(1.0, samlet - 0.5)  # Dårlig momentum

        # ── Sektor-rotation: bonus/straf ud fra hvor sektoren ligger ──
        samlet = round(max(1.0, min(10.0, samlet + sektor_rot.get("bonus", {}).get(sektor, 0.0))), 1)

        # ── ML-model: log features til fremtidig træning + bland score ind
        # hvis en trænet model allerede findes (kræver ML_MIN_TRAENINGS_EKSEMPLER) ──
        ml_features = _byg_ml_features(f_s, t_s, s_s, f_d, t_d, makro)
        ml_prob = hent_ml_score(ml_features)
        if ml_prob is not None:
            samlet = round(max(1.0, min(10.0, samlet * 0.70 + (ml_prob * 10) * 0.30)), 1)
        gem_ml_traeningseksempel(ticker, datetime.now().strftime("%Y-%m-%d"), td.get("pris", 0), ml_features)

        i_cooldown = ticker in stop_loss_cooldown

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
            "anbefaling": score_til_tekst(samlet, makro),
            "grunde":    (f_d.get("grunde", []) if isinstance(f_d, dict) else []) +
                         (t_d.get("grunde", []) if isinstance(t_d, dict) else []) +
                         (["Stop-loss cooldown (30 dage)"] if i_cooldown else []),
            "position":  beregn_position(samlet, cash_dkk, cash_usd, ticker.endswith(".CO"), circuit_faktor=circuit_faktor),
            "stop_loss_cooldown": i_cooldown,
            "ml_score":  round(ml_prob, 2) if ml_prob is not None else None,
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

    with open(SCREENER_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "dato": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "makro": makro,
            "resultater": res
        }, f, ensure_ascii=False, default=_json_default)

    kandidater = [
        r for r in res
        if r["samlet"] >= 6.5
        and r["teknik_data"].get("trend_ok", True)
        and r["teknik_data"].get("momentum_ok", True)
        and r["teknik_data"].get("earnings_ok", True)
        and not r.get("stop_loss_cooldown", False)
    ]
    frasorteret = len([r for r in res if r["samlet"] >= 6.5]) - len(kandidater)
    log(f"Screener færdig: {len(res)} aktier, {len(kandidater)} kandidater ≥6.5 "
        f"({frasorteret} frasorteret pga. nedtrend/svagt momentum/regnskab-snart/stop-loss-cooldown)")
    return res, kandidater

# ════════════════════════════════════════════════════════════
# DYB ANALYSE
# ════════════════════════════════════════════════════════════
def koer_dyb_analyse(kandidater, makro=None):
    if not kandidater:
        return []

    # ── Anti-repetitions filter: hent hvad vi anbefalte de sidste 5 dage ──
    historik = _safe_json_load(BACKTEST_HISTORIK_FILE) or []
    graense_dato = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    nylige_anbefalinger = {
        h["ticker"] for h in historik
        if h.get("dato", "") >= graense_dato
        and h.get("anbefaling") in ["KØB", "STÆRKT", "KØB"]
    }
    # Tæl hvor mange gange hver ticker er anbefalet de seneste 5 dage
    antal_anbefalinger = {}
    for h in historik:
        if h.get("dato", "") >= graense_dato:
            t = h["ticker"]
            antal_anbefalinger[t] = antal_anbefalinger.get(t, 0) + 1

    log(f"Anti-repetition: {len(nylige_anbefalinger)} aktier anbefalet de seneste 5 dage")

    # ── Relativ styrke: sorter inden for sektorer ──────────────────────
    sektorer_scores = {}
    for r in kandidater:
        s = r.get("sektor", "")
        if s not in sektorer_scores:
            sektorer_scores[s] = []
        sektorer_scores[s].append(r["samlet"])

    def relativ_styrke(r):
        """Beregn om aktien er stærkere end sektorgennemsnittet."""
        s = r.get("sektor", "")
        scores = sektorer_scores.get(s, [r["samlet"]])
        gns = sum(scores) / len(scores)
        return r["samlet"] - gns  # Positiv = stærkere end sektor

    # ── Conviction filter: strammere krav ──────────────────────────────
    stærke = []
    for r in kandidater:
        f = r.get("fundamental", 0)
        t = r.get("teknisk", 0)
        s = r.get("sentiment", 0)
        ticker = r["ticker"]
        gange_anbefalet = antal_anbefalinger.get(ticker, 0)

        # Strammere krav end før
        if f < 6.5 or t < 6.0 or r["samlet"] < 7.5:
            continue

        # Hård trend-/momentum-/earnings-/cooldown-diskvalifikation (defensivt —
        # filtreres normalt allerede fra i koer_screener, men tjekkes igen her)
        td = r.get("teknik_data", {})
        if (not td.get("trend_ok", True) or not td.get("momentum_ok", True)
                or not td.get("earnings_ok", True) or r.get("stop_loss_cooldown", False)):
            continue

        # Strafafelt for aktier anbefalet mange gange
        repetitions_straf = gange_anbefalet * 1.0
        justeret_score = r["samlet"] - repetitions_straf

        # Kræv minimum relativ styrke i sektoren
        rel_styrke = relativ_styrke(r)

        stærke.append({
            **r,
            "justeret_score": round(justeret_score, 1),
            "rel_styrke": round(rel_styrke, 2),
            "gange_anbefalet_5d": gange_anbefalet,
        })

    # Sorter efter justeret score (straffer repetition)
    stærke.sort(key=lambda x: x["justeret_score"], reverse=True)

    # Maksimalt 5 — og max 2 fra samme sektor
    kandidater_filtreret = []
    sektor_count = {}
    for r in stærke:
        sektor = r.get("sektor", "")
        if sektor_count.get(sektor, 0) >= 2:
            continue  # Max 2 per sektor
        kandidater_filtreret.append(r)
        sektor_count[sektor] = sektor_count.get(sektor, 0) + 1
        if len(kandidater_filtreret) >= 5:
            break

    if not kandidater_filtreret:
        # Fallback: top 3 med mindst repetition
        fallback = sorted(kandidater, key=lambda x: (
            -x["samlet"] + antal_anbefalinger.get(x["ticker"], 0) * 1.0
        ))[:3]
        kandidater_filtreret = fallback
        log("Conviction fallback: bruger top 3 med lavest repetition")

    log(f"Conviction filter: {len(kandidater)} → {len(stærke)} → {len(kandidater_filtreret)} til dyb analyse")
    for r in kandidater_filtreret:
        gange = r.get("gange_anbefalet_5d", 0)
        log(f"  {r['ticker']}: score {r['samlet']} → justeret {r.get('justeret_score', r['samlet'])} (anbefalet {gange}x de seneste 5d)")

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
        # Groq får 60% vægt, screener 40% — Groq er mere nuanceret
        komb = round((r["samlet"] * 0.40 + llama_s * 0.60), 1)
        if makro:
            komb = anvend_makro_justering(komb, makro)
        # Straf aktier der er anbefalet mange gange de seneste 5 dage
        gange = r.get("gange_anbefalet_5d", 0)
        komb = round(max(1.0, komb - gange * 1.0), 1)

        log(f"  {r['ticker']}: screener={r['samlet']} Groq={llama_s} kombineret={komb} (anbefalet {gange}x)")
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
            json.dump(res, f, default=_json_default)
        log(f"FinBERT færdig: {len(res)} aktier.")
        return res
    except Exception as e:
        log(f"FinBERT setup fejl: {e}")
        return []

# ════════════════════════════════════════════════════════════
# RE-ANALYSE AF AKTIVE POSITIONER — exit-logik
# ════════════════════════════════════════════════════════════
TRAILING_STOP_PCT  = 0.08   # stop følger 8% under nuværende pris, hæves aldrig sænkes
TIDS_STOP_DAGE     = 25     # "død kapital" hvis ingen bevægelse efter så mange dage
SCORE_FALD_GRAENSE = 2.0    # fald i screener-score siden køb der udløser advarsel

def koer_reanalyse_aktive():
    """
    Daglig re-analyse af alle aktive positioner. Dette er "sælg-siden" af
    systemet — det eneste sted der løbende overvåger positioner du allerede
    ejer og fortæller dig hvornår du bør handle:

    - Trailing stop-loss: stop hæves når kursen stiger, sænkes aldrig.
    - Tids-stop: flager positioner der ikke har bevæget sig i ~25 dage
      (død kapital — pengene kunne arbejde bedre andetsteds).
    - Score-forringelse: sammenligner frisk fundamental+teknisk score med
      scoren ved køb; stort fald betyder tesen er svækket.
    - Frisk Groq-analyse i samme format som de daglige anbefalinger.

    Gemmer til data/reanalyse_seneste.json (læses af app.py's "Daglig
    Re-analyse"-sektion) og opdaterer alerts.json via tjek_saelg_signaler().
    """
    handler = _safe_json_load(AKTIVE_HANDLER_FILE) or []
    aktive  = [h for h in handler if h.get("status") == "aktiv"]

    if not aktive:
        log("Reanalyse: ingen aktive positioner")
        with open(REANALYSE_FILE, "w", encoding="utf-8") as f:
            json.dump({"dato": datetime.now().strftime("%Y-%m-%d %H:%M"), "resultater": []}, f, ensure_ascii=False, default=_json_default)
        return []

    res = []
    aendret = False

    for h in aktive:
        ticker    = h["ticker"]
        koebspris = h.get("koebspris", 0)
        stop_loss = h.get("stop_loss")
        target    = h.get("target")
        score_ved_koeb = h.get("score_ved_koeb", 5)
        dato_kobt = h.get("dato_kobt", "")

        k = hent_kurs(ticker)
        pris_nu = k["pris"] if k else koebspris
        afkast  = round((pris_nu / koebspris - 1) * 100, 2) if koebspris > 0 else 0

        try:
            dage_holdt = (datetime.now() - datetime.strptime(dato_kobt, "%Y-%m-%d")).days
        except Exception:
            dage_holdt = 0

        flag = []

        # ── Trailing stop-loss: hæv aldrig sænk ──────────────
        if stop_loss and koebspris > 0 and pris_nu > koebspris:
            ny_stop = round(pris_nu * (1 - TRAILING_STOP_PCT), 2)
            if ny_stop > stop_loss:
                log(f"Trailing stop {ticker}: {stop_loss} → {ny_stop}")
                h["stop_loss"] = ny_stop
                stop_loss = ny_stop
                aendret = True
                flag.append(f"Trailing stop hævet til ${ny_stop} (låser gevinst)")

        # ── Tids-stop: død kapital ────────────────────────────
        if dage_holdt >= TIDS_STOP_DAGE and abs(afkast) < 3:
            flag.append(f"TIDS-STOP: {dage_holdt} dage uden bevægelse ({afkast:+.1f}%) — overvej salg")

        # ── Delvis profit-taking ved target ───────────────────
        if target and pris_nu >= target:
            flag.append(f"TARGET NÅET (${target}) — overvej at sælge halvdelen og lade resten køre med trailing stop")

        # ── Frisk scoring vs. score ved køb ───────────────────
        f_s, f_d = fundamental_screening(ticker)
        t_s, t_d = teknisk_screening(ticker)
        s_s, _   = hurtig_sentiment(ticker)
        ny_score = beregn_samlet(f_s, t_s, s_s) if f_s is not None else None

        if ny_score is not None and (score_ved_koeb - ny_score) >= SCORE_FALD_GRAENSE:
            flag.append(f"SCORE FALDET: {score_ved_koeb} → {ny_score} siden køb — fundamentals/teknik er forringet")

        # ── Frisk Groq re-analyse (samme format som daglig brief) ──
        screener_data = {
            "fundamental": f_s if f_s is not None else score_ved_koeb,
            "teknisk":     t_s,
            "sentiment":   s_s,
            "samlet":      ny_score if ny_score is not None else score_ved_koeb,
            "fund_data":   f_d if isinstance(f_d, dict) else {},
            "teknik_data": t_d if isinstance(t_d, dict) else {},
            "gange_anbefalet_5d": 0,
        }
        tekst = hent_earnings_tekst(ticker)
        ny_analyse = analyser_med_llama(tekst, ticker, screener_data) if tekst else ""
        if not ny_analyse:
            ny_analyse = (f"ANBEFALING: HOLD\nSCORE: {score_ved_koeb}\n"
                          f"RESUMÉ: Kunne ikke hente frisk analysedata i dag — behold indtil videre.\n")
        if flag:
            ny_analyse += "\n\nSYSTEM-FLAG:\n" + "\n".join(f"- {x}" for x in flag)

        res.append({
            "ticker":     ticker,
            "dato":       datetime.now().strftime("%Y-%m-%d"),
            "ny_analyse": ny_analyse,
            "afkast":     afkast,
            "dage_holdt": dage_holdt,
            "stop_loss":  stop_loss,
            "target":     target,
            "flag":       flag,
        })
        time.sleep(0.5)

    if aendret:
        with open(AKTIVE_HANDLER_FILE, "w", encoding="utf-8") as f:
            json.dump(handler, f, ensure_ascii=False, indent=2, default=_json_default)

    with open(REANALYSE_FILE, "w", encoding="utf-8") as f:
        json.dump({"dato": datetime.now().strftime("%Y-%m-%d %H:%M"), "resultater": res}, f, ensure_ascii=False, default=_json_default)

    # Genbrug det eksisterende sælg-signal-tjek med de evt. opdaterede stops
    alerts = tjek_saelg_signaler()
    if alerts:
        with open(ALERT_FILE, "w", encoding="utf-8") as f:
            json.dump(alerts, f, ensure_ascii=False, default=_json_default)

    log(f"Reanalyse færdig: {len(res)} aktive positioner gennemgået, {sum(1 for r in res if r['flag'])} med flag")
    return res

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
    koer_reanalyse_aktive()

    brief = {
        "dato":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        "makro":         makro,
        "top_kandidater": dybe,
        "alle_screener": alle[:30],
    }
    with open(BRIEF_FILE, "w", encoding="utf-8") as f:
        json.dump(brief, f, ensure_ascii=False, default=_json_default)

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
            json.dump(alerts, f, default=_json_default)
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
        json.dump(historik, f, ensure_ascii=False, indent=2, default=_json_default)

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

        statistik = {
            "antal_anbefalinger":   len(alle),
            "hit_rate_pct":         round(hit_rate, 1),
            "gns_afkast_30d_pct":   round(avg_afkast, 2),
            "gns_afkast_koeb_pct":  round(avg_koeb, 2),
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
        json.dump(statistik, f, ensure_ascii=False, default=_json_default)

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
    elif cmd == "makro":    print(json.dumps(hent_makro(), indent=2, ensure_ascii=False))
    elif cmd == "dyb":
        # Hent screener-data og kør dyb analyse — gem resultatet i brief-filen
        data = hent_screener_data()
        if data:
            makro_data = data.get("makro") or hent_makro_data()
            kands = [
                r for r in data["resultater"]
                if r["samlet"] >= 6.5
                and r.get("teknik_data", {}).get("trend_ok", True)
                and r.get("teknik_data", {}).get("momentum_ok", True)
                and r.get("teknik_data", {}).get("earnings_ok", True)
                and not r.get("stop_loss_cooldown", False)
            ]
            log(f"Dyb analyse starter for {len(kands)} kandidater...")
            dybe = koer_dyb_analyse(kands, makro_data)
            # Gem som brief-fil så app.py kan vise resultaterne
            brief = {
                "dato":           datetime.now().strftime("%Y-%m-%d %H:%M"),
                "makro":          makro_data,
                "top_kandidater": dybe,
                "alle_screener":  data["resultater"][:30],
            }
            with open(BRIEF_FILE, "w", encoding="utf-8") as f:
                json.dump(brief, f, ensure_ascii=False, default=_json_default)
            _tjek_og_send_alerts(dybe)
            log(f"Dyb analyse færdig: {len(dybe)} analyseret, gemt i brief-fil.")
        else:
            log("Ingen screener-data fundet — kør 'screener' først.")
    elif cmd == "backtest":  print(json.dumps(koer_backtest(), indent=2, ensure_ascii=False))
    elif cmd == "sentiment": koer_finbert_sentiment()
    elif cmd == "train":    train_ml_model()
    elif cmd == "reanalyser": koer_reanalyse_aktive()
    elif cmd == "backfill": backfill_ml_training_fra_git_historik()
    else:
        print("Brug: brief | screener | makro | dyb | backtest | sentiment | train | reanalyser | backfill")
        print("Flag: --komplet (for fuld scanning)")

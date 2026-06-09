"""
============================================================
 AI AKTIE RAADGIVER - Dashboard v7.0
 4 tabs: OVERSIGT · PORTEFØLJE · SIGNALER · BACKTEST
 Nyt: Køb-flow med stop-loss, sælg-signaler, maks 5 signaler
============================================================
"""
import streamlit as st
import os, sys, json, re, math, html as html_mod, requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine

st.set_page_config(page_title="AI Aktie Rådgiver", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;700;800&display=swap');
*{box-sizing:border-box}
html,body,[data-testid="stAppViewContainer"]{background:#0a0a0f!important;color:#e8e8f0!important;font-family:'Syne',sans-serif!important}
[data-testid="stAppViewContainer"]{background:radial-gradient(ellipse at 20% 0%,#0d1528 0%,#0a0a0f 60%)!important}
#MainMenu,footer,header,[data-testid="stToolbar"],[data-testid="stSidebar"]{display:none!important}
.block-container{padding:2rem 3rem!important;max-width:1500px!important}
.main-header{display:flex;align-items:flex-end;justify-content:space-between;padding:2rem 0 2rem;border-bottom:1px solid rgba(255,255,255,.06);margin-bottom:2rem}
.main-title{font-size:2.4rem;font-weight:800;letter-spacing:-.03em;background:linear-gradient(135deg,#fff 0%,#a0a8ff 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.main-subtitle{font-family:'Space Mono',monospace;font-size:.7rem;color:#4a4a6a;margin-top:.3rem;letter-spacing:.08em;text-transform:uppercase}
.header-date{font-family:'Space Mono',monospace;font-size:.7rem;color:#4a4a6a;text-align:right}
[data-testid="stTabs"]>div:first-child{border-bottom:1px solid rgba(255,255,255,.06)!important}
button[data-baseweb="tab"]{font-family:'Space Mono',monospace!important;font-size:.72rem!important;letter-spacing:.1em!important;text-transform:uppercase!important;color:#4a4a6a!important;padding:.8rem 1.5rem!important;border:none!important;background:transparent!important;border-bottom:2px solid transparent!important}
button[data-baseweb="tab"]:hover{color:#a0a8ff!important}
button[data-baseweb="tab"][aria-selected="true"]{color:#fff!important;border-bottom:2px solid #a0a8ff!important}
[data-testid="stTabPanel"]{padding-top:1.5rem!important}
.metric-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:1.2rem 1.4rem;margin-bottom:.8rem}
.metric-label{font-family:'Space Mono',monospace;font-size:.62rem;letter-spacing:.12em;text-transform:uppercase;color:#4a4a6a;margin-bottom:.5rem}
.metric-value{font-size:1.5rem;font-weight:700;color:#fff}
.metric-sub{font-family:'Space Mono',monospace;font-size:.68rem;color:#6a6a8a;margin-top:.25rem}
.up{color:#4ade80!important}.down{color:#f87171!important}.neu{color:#facc15!important}
.sct{font-size:.65rem;font-family:'Space Mono',monospace;letter-spacing:.15em;text-transform:uppercase;color:#4a4a6a;margin:2rem 0 1rem;padding-bottom:.5rem;border-bottom:1px solid rgba(255,255,255,.04)}
.badge{display:inline-flex;align-items:center;padding:.2rem .6rem;border-radius:20px;font-family:'Space Mono',monospace;font-size:.65rem;font-weight:700}
.b-strong{background:rgba(74,222,128,.2);color:#22c55e;border:1px solid rgba(74,222,128,.4)}
.b-buy{background:rgba(74,222,128,.12);color:#4ade80;border:1px solid rgba(74,222,128,.25)}
.b-hold{background:rgba(250,204,21,.1);color:#facc15;border:1px solid rgba(250,204,21,.25)}
.b-sell{background:rgba(248,113,113,.1);color:#f87171;border:1px solid rgba(248,113,113,.25)}
/* Sælg-banner */
.saelg-banner{border-radius:10px;padding:1rem 1.4rem;margin-bottom:.8rem;display:flex;justify-content:space-between;align-items:center}
.saelg-stop{background:rgba(248,113,113,.1);border:1px solid rgba(248,113,113,.35)}
.saelg-target{background:rgba(74,222,128,.1);border:1px solid rgba(74,222,128,.35)}
.saelg-adv{background:rgba(250,204,21,.08);border:1px solid rgba(250,204,21,.25)}
/* Aktiv handel kort */
.handel-kort{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:1.1rem 1.3rem;margin-bottom:.6rem}
.handel-kort:hover{border-color:rgba(255,255,255,.12)}
.handel-header{display:flex;justify-content:space-between;align-items:flex-start}
/* Signal kort */
.sig-kort{border-radius:14px;padding:1.4rem;background:rgba(255,255,255,.02);margin-bottom:1rem}
.sig-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:.8rem}
.sig-titel{font-size:1.4rem;font-weight:800}
.sig-meta{font-family:'Space Mono',monospace;font-size:.7rem;color:#6a6a8a;margin-top:.2rem}
.sig-right{text-align:right}
.sig-prob{font-size:1.1rem;font-weight:700}
/* Pris-grid */
.pris-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:.4rem;background:rgba(0,0,0,.2);padding:.7rem;border-radius:8px;margin:.7rem 0}
.pris-cell{text-align:center}
.pris-lbl{font-size:.6rem;color:#6a6a8a;text-transform:uppercase;letter-spacing:.04em}
.pris-val{font-size:.95rem;font-weight:700;margin-top:.15rem}
/* Tek grid */
.tek-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:.3rem;background:rgba(0,0,0,.2);padding:.5rem .7rem;border-radius:7px;margin:.5rem 0}
.tek-cell{text-align:center}
.tek-lbl{font-family:'Space Mono',monospace;font-size:.56rem;color:#4a4a6a;text-transform:uppercase}
.tek-val{font-family:'Space Mono',monospace;font-size:.72rem;font-weight:700}
/* Makro */
.makro-strip{padding:.65rem 1.2rem;border-radius:8px;margin-bottom:1.2rem;font-family:'Space Mono',monospace;font-size:.68rem;font-weight:700;border:1px solid}
.mok{background:rgba(74,222,128,.06);border-color:rgba(74,222,128,.2)}
.mwarn{background:rgba(250,204,21,.06);border-color:rgba(250,204,21,.2)}
.mdanger{background:rgba(248,113,113,.08);border-color:rgba(248,113,113,.25)}
/* Info */
.info-box{background:rgba(160,168,255,.06);border:1px solid rgba(160,168,255,.15);border-radius:10px;padding:1rem 1.4rem;margin-bottom:1.2rem;font-size:.85rem;color:#8a8aaa}
.opd-kort{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.06);border-radius:10px;padding:.9rem 1.1rem;margin-bottom:.4rem}
.opd-kort:hover{border-color:rgba(160,168,255,.2)}
/* Holding row */
.h-row{display:flex;justify-content:space-between;align-items:center;padding:.9rem 1.1rem;background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.05);border-radius:10px;margin-bottom:.5rem}
.h-row:hover{background:rgba(160,168,255,.04);border-color:rgba(160,168,255,.12)}
/* BT */
.bt-row{display:flex;justify-content:space-between;align-items:center;padding:.6rem 1rem;border-bottom:1px solid rgba(255,255,255,.04);font-size:.8rem}
/* Knapper */
.stButton>button{background:rgba(160,168,255,.08)!important;color:#a0a8ff!important;border:1px solid rgba(160,168,255,.25)!important;border-radius:8px!important;font-family:'Space Mono',monospace!important;font-size:.7rem!important;letter-spacing:.06em!important}
.stButton>button:hover{background:rgba(160,168,255,.2)!important;border-color:rgba(160,168,255,.5)!important;color:#fff!important}
[data-testid="stTextInput"]>div>div>input,[data-testid="stNumberInput"]>div>div>input{background:rgba(255,255,255,.04)!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:8px!important;color:#e8e8f0!important}
[data-testid="stSelectbox"]>div>div{background:rgba(255,255,255,.04)!important;border:1px solid rgba(255,255,255,.1)!important;border-radius:8px!important}
label{color:#6a6a8a!important;font-size:.78rem!important}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
def badge(score):
    if   score >= 8.5: return f'<span class="badge b-strong">STÆRKT KØB {score}</span>'
    elif score >= 7.0: return f'<span class="badge b-buy">KØB {score}</span>'
    elif score >= 5.0: return f'<span class="badge b-hold">HOLD {score}</span>'
    else:              return f'<span class="badge b-sell">SÆLG {score}</span>'

def sec(tekst, m=""):
    st.markdown(f'<div class="sct" style="{m}">{tekst}</div>', unsafe_allow_html=True)

@st.cache_data(ttl=300)
def kurs(ticker):
    return engine.hent_kurs(ticker)

def trigger_github_scanning(scanning_type="komplet"):
    token = st.secrets.get("GITHUB_TOKEN", "")
    repo  = st.secrets.get("GITHUB_REPO", "Nielsen-97/AI-Aktie-R-dgiver")
    if not token:
        return False, "GITHUB_TOKEN mangler i Streamlit Secrets"
    url = f"https://api.github.com/repos/{repo}/actions/workflows/daily_brief.yml/dispatches"
    r = requests.post(url,
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        json={"ref": "main", "inputs": {"scanning_type": scanning_type}},
        timeout=15)
    if r.status_code == 204:
        return True, ""
    return False, f"GitHub API fejl {r.status_code}: {r.text[:200]}"

def makro_strip(m):
    if not m: return
    vix = m.get("vix", 20)
    cls = "mok" if vix < 20 else "mwarn" if vix < 27 else "mdanger"
    st.markdown(
        f'<div class="makro-strip {cls}">'
        f'VIX {vix:.1f} ({m.get("vix_status","")}) &nbsp;·&nbsp; '
        f'SP500 {m.get("sp_status","")} {m.get("sp_1m_afkast",0):+.1f}% 1M &nbsp;·&nbsp; '
        f'10Y {m.get("rente_10y","N/A")} &nbsp;·&nbsp; Justering {m.get("justering",0):+.1f}'
        f'</div>', unsafe_allow_html=True)

def parse_analyse(tekst):
    if not tekst:
        return {"anbefaling":"VENT","score":"–","prob":"–","entry":"-",
                "stop":"-","target":"-","resume":"–","tidshorisont":"30-90 dage"}
    def s(patterns, default="-"):
        for p in (patterns if isinstance(patterns,list) else [patterns]):
            m = re.search(p, tekst, re.I)
            if m: return m.group(1).strip().rstrip(".,")
        return default
    anb = s([r"ANBEFALING[:\s]+([A-ZÆØÅ]+(?:\s+[A-ZÆØÅ]+)?)",
             r"KONKLUSION[:\s]+([A-ZÆØÅ]+(?:\s+[A-ZÆØÅ]+)?)",
             r"\b(STÆRKT KØB|KØB|SÆLG|HOLD)\b"], "VENT")
    anb = {"BUY":"KØB","STRONG BUY":"STÆRKT KØB","SELL":"SÆLG"}.get(anb.upper(), anb.upper())
    resume = s([r"RESUMÉ[:\s]+(.{15,150})", r"KONKLUSION[:\s]+(.{15,150})"], "–")
    if resume == "–":
        for l in tekst.splitlines():
            l = l.strip("- *:#")
            if len(l) > 25 and not any(x in l.upper() for x in
               ["ANBEFALING","SCORE","ENTRY","STOP","TARGET","FAKTORER","SANDSYNLIGHED"]):
                resume = l[:140]; break
    return {
        "anbefaling":   anb,
        "score":        s(r"SCORE[:\s]+(\d+(?:\.\d+)?)", "–"),
        "prob":         s([r"SANDSYNLIGHED[:\s]+(\d+)%?", r"(\d+)%\s*sandsynlighed"], "–"),
        "entry":        s([r"ENTRY PRIS[:\s]+\$?([\d]+[.,]\d+)", r"ENTRY[:\s]+\$?([\d]+[.,]\d+)"], "-"),
        "stop":         s([r"STOP LOSS[:\s]+\$?([\d]+[.,]\d+)", r"STOP[:\s]+\$?([\d]+[.,]\d+)"], "-"),
        "target":       s([r"TARGET PRIS[:\s]+\$?([\d]+[.,]\d+)", r"TARGET[:\s]+\$?([\d]+[.,]\d+)"], "-"),
        "resume":       resume,
        "tidshorisont": s([r"TIDSHORISONT[:\s]+(.{5,40})", r"(\d+-\d+\s*dage)"], "30-90 dage"),
    }

def ok_tal(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))

def fmt(v, suf="", pre=False):
    if not ok_tal(v): return "–"
    px = "+" if pre and isinstance(v,(int,float)) and v>0 else ""
    return f"{px}{v}{suf}"

def tek_grid(td):
    if not td: return ""
    def cell(lbl, v, cls=""):
        return (f'<div class="tek-cell"><div class="tek-lbl">{lbl}</div>'
                f'<div class="tek-val {cls}">{v}</div></div>')
    rsi = td.get("rsi"); vol = td.get("vol_ratio")
    ret = td.get("afkast_1m"); h52 = td.get("pct_fra_52w_high"); bb = td.get("bb_pct")
    rsi_c = "up" if ok_tal(rsi) and rsi<40 else "down" if ok_tal(rsi) and rsi>70 else ""
    vol_c = "up" if ok_tal(vol) and vol>1.5 else ""
    ret_c = "up" if ok_tal(ret) and ret>0 else "down" if ok_tal(ret) and ret<0 else ""
    h52_c = "up" if ok_tal(h52) and h52>-5 else ""
    rsi_s = f"{rsi:.1f}" if ok_tal(rsi) else "–"
    vol_s = f"{vol:.2f}" if ok_tal(vol) else "–"
    ret_s = (f"+{ret:.1f}%" if ok_tal(ret) and ret>0 else f"{ret:.1f}%" if ok_tal(ret) else "–")
    h52_s = f"{h52:.1f}%" if ok_tal(h52) else "–"
    bb_s  = f"{bb:.2f}" if ok_tal(bb) else "–"
    return ('<div class="tek-grid">'
            + cell("RSI",rsi_s,rsi_c) + cell("Vol×",vol_s,vol_c)
            + cell("1M",ret_s,ret_c) + cell("52W",h52_s,h52_c)
            + cell("BB%",bb_s) + '</div>')

def esc(t):
    clean = re.sub(r'<[^>]+>', '', str(t))
    return html_mod.escape(clean)


# ════════════════════════════════════════════════════════════
# KØB DIALOG — vises i en expander
# ════════════════════════════════════════════════════════════
def vis_koeb_dialog(r, p, pf, cash_dkk, cash_usd, cash_end):
    """Inline købs-form under signal-kortet."""
    ticker  = r["ticker"]
    score   = r.get("kombineret", r.get("samlet", 5))

    # Forsøg at parse priser som float
    def til_float(s, fallback=0.0):
        try: return float(str(s).replace(",", ".").replace("$", ""))
        except: return fallback

    entry_f  = til_float(p["entry"])
    stop_f   = til_float(p["stop"])
    target_f = til_float(p["target"])

    k = kurs(ticker)
    pris_nu = k["pris"] if k else entry_f or 100.0

    with st.expander(f"🟢 Køb {ticker} — udfyld detaljer", expanded=True):
        st.markdown(
            f'<div style="font-size:.8rem;color:#8a8aaa;margin-bottom:1rem">'
            f'Groq anbefaler: Entry ~${entry_f:.2f} · Stop Loss ${stop_f:.2f} · Target ${target_f:.2f}'
            f'</div>', unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            platform = st.selectbox("Platform", ["nordnet","etoro","endavu"],
                                    key=f"plat_{ticker}")
        with col2:
            antal = st.number_input("Antal aktier", min_value=0.01,
                                    value=1.0, step=0.5, key=f"antal_{ticker}")
        with col3:
            koebspris = st.number_input("Købspris ($)",
                                        min_value=0.01,
                                        value=float(round(pris_nu, 2)) if pris_nu > 0 else 1.0,
                                        step=0.5, key=f"kpris_{ticker}")

        col4, col5 = st.columns(2)
        with col4:
            stop_input = st.number_input("Stop Loss ($)",
                                         min_value=0.01,
                                         value=float(round(stop_f, 2)) if stop_f > 0 else float(round(koebspris * 0.92, 2)),
                                         step=0.5, key=f"stop_{ticker}")
        with col5:
            target_input = st.number_input("Target ($)",
                                           min_value=0.01,
                                           value=float(round(target_f, 2)) if target_f > 0 else float(round(koebspris * 1.15, 2)),
                                           step=0.5, key=f"target_{ticker}")

        # Beregn beløb baseret på platform
        if platform == "etoro":
            max_beloeb = cash_usd
            valuta     = "USD"
            beloeb_std = round(engine.beregn_position(score, cash_dkk, cash_usd, False)["beloeb"], 2)
        elif platform == "endavu":
            max_beloeb = cash_end
            valuta     = "DKK"
            beloeb_std = round(engine.beregn_position(score, cash_end, 0, True)["beloeb"])
        else:
            max_beloeb = cash_dkk
            valuta     = "DKK"
            beloeb_std = round(engine.beregn_position(score, cash_dkk, cash_usd, False)["beloeb"])

        beloeb = st.number_input(
            f"Investeret beløb ({valuta}) — max {max_beloeb:,.0f}",
            min_value=1.0,
            value=float(min(beloeb_std, max_beloeb)) if beloeb_std > 0 and max_beloeb > 0 else 100.0,
            step=100.0 if valuta=="DKK" else 10.0,
            key=f"bel_{ticker}"
        )

        navn = st.text_input("Navn (valgfri)", value=ticker, key=f"navn_{ticker}")

        # Risk/reward preview
        if koebspris > 0 and stop_input > 0 and target_input > 0:
            risk    = (koebspris - stop_input) / koebspris * 100
            reward  = (target_input - koebspris) / koebspris * 100
            rr      = reward / risk if risk > 0 else 0
            rr_c    = "#4ade80" if rr >= 2 else "#facc15" if rr >= 1 else "#f87171"
            st.markdown(
                f'<div style="font-family:Space Mono,monospace;font-size:.72rem;'
                f'background:rgba(0,0,0,.2);padding:.6rem .8rem;border-radius:6px;margin:.5rem 0">'
                f'Risiko: <span class="down">-{risk:.1f}%</span> &nbsp;·&nbsp; '
                f'Potentiale: <span class="up">+{reward:.1f}%</span> &nbsp;·&nbsp; '
                f'R/R: <span style="color:{rr_c};font-weight:700">{rr:.1f}x</span>'
                f'</div>', unsafe_allow_html=True)

        col_ok, col_nej = st.columns([2, 1])
        with col_ok:
            if st.button(f"✅ Bekræft køb af {ticker}", key=f"bekraeft_{ticker}",
                         use_container_width=True):
                engine.registrer_koeb(
                    ticker=ticker, navn=navn, platform=platform,
                    antal=antal, koebspris=koebspris,
                    stop_loss=stop_input, target=target_input,
                    beloeb=beloeb, valuta=valuta,
                    score=score, analyse=r.get("analyse","")
                )
                st.success(f"✅ {ticker} købt og tilføjet til portefølje! Stop-loss sat til ${stop_input:.2f}")
                st.cache_data.clear()
                st.rerun()
        with col_nej:
            if st.button("Annuller", key=f"cancel_{ticker}", use_container_width=True):
                st.session_state.pop(f"koeb_{ticker}", None)
                st.rerun()


# ════════════════════════════════════════════════════════════
# SIGNAL KORT
# ════════════════════════════════════════════════════════════
def vis_signal_kort(r, cash_dkk, cash_usd, cash_end, pf, vis_koeb=True):
    score   = r.get("kombineret", r.get("samlet", 5))
    analyse = r.get("analyse", "")
    analyse_ren = esc(analyse)
    p   = parse_analyse(analyse)
    rec = p["anbefaling"].upper().strip()

    if rec in ["KØB","STÆRKT KØB"]:
        border_c = "#4ade80"; rec_c = "#4ade80"
    elif rec == "SÆLG":
        border_c = "#f87171"; rec_c = "#f87171"
    else:
        border_c = "#facc15"; rec_c = "#facc15"

    pos = engine.beregn_position(score, cash_dkk, cash_usd, r["ticker"].endswith(".CO"))
    td  = r.get("teknik_data", {})
    fd  = r.get("fund_data",   {})

    # Fund linje
    bits = []
    if fd.get("pe"):           bits.append(f"P/E {fd['pe']:.0f}")
    if fd.get("rev_growth"):   bits.append(f"Rev {fd['rev_growth']:+.0f}%")
    if fd.get("fcf_margin"):   bits.append(f"FCF {fd['fcf_margin']:.0f}%")
    if fd.get("surprise_pct"): bits.append(f"EPS beat {fd['surprise_pct']:+.1f}%")
    fund_linje = " · ".join(bits)

    plat_c = "#a0ff8a" if pos["platform"]=="Endavu" else "#a0a8ff"

    # Pris grid
    def til_float(s):
        try: return float(str(s).replace(",",".").replace("$",""))
        except: return 0.0
    entry_f = til_float(p["entry"]); stop_f = til_float(p["stop"]); target_f = til_float(p["target"])
    priser_html = ""
    if entry_f > 0:
        priser_html = (
            '<div class="pris-grid">'
            f'<div class="pris-cell"><div class="pris-lbl">Entry</div><div class="pris-val" style="color:#e8e8f0">${p["entry"]}</div></div>'
            f'<div class="pris-cell"><div class="pris-lbl">Stop Loss</div><div class="pris-val" style="color:#f87171">${p["stop"]}</div></div>'
            f'<div class="pris-cell"><div class="pris-lbl">Target</div><div class="pris-val" style="color:#4ade80">${p["target"]}</div></div>'
            f'<div class="pris-cell"><div class="pris-lbl">Anbefalet pos.</div><div class="pris-val" style="color:{plat_c}">{pos["beloeb"]} {pos["valuta"]}</div></div>'
            '</div>'
        )
        if entry_f > 0 and stop_f > 0 and target_f > 0:
            risk = (entry_f - stop_f)/entry_f*100
            rew  = (target_f - entry_f)/entry_f*100
            rr   = rew/risk if risk>0 else 0
            rr_c = "#4ade80" if rr>=2 else "#facc15" if rr>=1 else "#f87171"
            priser_html += (
                f'<div style="font-family:Space Mono,monospace;font-size:.65rem;'
                f'color:#6a6a8a;margin-bottom:.4rem">'
                f'Risiko <span class="down">-{risk:.1f}%</span> &nbsp;·&nbsp; '
                f'Potentiale <span class="up">+{rew:.1f}%</span> &nbsp;·&nbsp; '
                f'R/R <span style="color:{rr_c};font-weight:700">{rr:.1f}x</span></div>'
            )

    # Faktorer
    fakt_html = ""
    pos_blok = re.search(r"POSITIVE FAKTORER[:\s]*(.*?)(?:NEGATIVE|ADVARSEL|TIDSHORISONT|$)", analyse, re.I|re.S)
    neg_blok = re.search(r"NEGATIVE FAKTORER[:\s]*(.*?)(?:ADVARSEL|TIDSHORISONT|KONKLUSION|$)", analyse, re.I|re.S)
    if pos_blok:
        ls = [l.strip("- •*").strip() for l in pos_blok.group(1).strip().splitlines() if l.strip("- •*").strip()]
        fakt_html += "".join(f'<span class="up">+ {esc(l)}</span><br>' for l in ls[:3])
    if neg_blok:
        ls = [l.strip("- •*").strip() for l in neg_blok.group(1).strip().splitlines() if l.strip("- •*").strip()]
        fakt_html += "".join(f'<span class="down">− {esc(l)}</span><br>' for l in ls[:2])

    extra = ""
    if r.get("insider") and "Ingen" not in r.get("insider",""):
        extra += '<span style="background:rgba(74,222,128,.1);border:1px solid rgba(74,222,128,.2);border-radius:4px;padding:.1rem .35rem;font-family:Space Mono,monospace;font-size:.6rem;color:#4ade80;margin-right:.3rem">INSIDER ↑</span>'
    if r.get("short") and "Lav" not in r.get("short","") and "Ingen" not in r.get("short",""):
        extra += '<span style="background:rgba(250,204,21,.1);border:1px solid rgba(250,204,21,.2);border-radius:4px;padding:.1rem .35rem;font-family:Space Mono,monospace;font-size:.6rem;color:#facc15;margin-right:.3rem">SHORT ⚡</span>'

    st.markdown(
        f'<div class="sig-kort" style="border:1px solid {border_c}33;border-left:3px solid {border_c}">'
        f'<div class="sig-header">'
        f'<div><div class="sig-titel" style="color:{rec_c}">{rec}</div>'
        f'<div class="sig-meta">{r["ticker"]} · {r.get("sektor","")} · Score {score}/10</div>'
        f'<div style="font-family:Space Mono,monospace;font-size:.6rem;color:#4a4a6a;margin-top:.2rem">{fund_linje}</div>'
        + (f'<div style="margin-top:.35rem">{extra}</div>' if extra else '') +
        f'</div>'
        f'<div class="sig-right">'
        f'<div class="sig-prob">{p["prob"]}% sandsynlighed</div>'
        f'<div style="font-family:Space Mono,monospace;font-size:.62rem;color:#6a6a8a">Groq 70b · {p["tidshorisont"]}</div>'
        f'<div style="font-family:Space Mono,monospace;font-size:.62rem;color:{plat_c};margin-top:.2rem">📍 {pos["platform"]}</div>'
        f'</div></div>'
        + tek_grid(td) + priser_html +
        f'<div style="font-size:.82rem;color:#ccc;margin:.5rem 0 .3rem"><b>Resumé:</b> {esc(p["resume"])}</div>'
        f'<div style="font-size:.7rem;color:#6a6a8a;line-height:1.9">{fakt_html}</div>'
        f'<details style="margin-top:.7rem">'
        f'<summary style="cursor:pointer;color:#a0a8ff;font-family:Space Mono,monospace;font-size:.68rem">▸ Vis fuld Groq analyse</summary>'
        f'<div style="margin-top:.5rem;font-family:Space Mono,monospace;font-size:.68rem;white-space:pre-wrap;color:#8a8aaa;border-top:1px solid rgba(255,255,255,.06);padding-top:.5rem">{analyse_ren}</div>'
        f'</details></div>',
        unsafe_allow_html=True
    )

    # Knapper under kortet
    if vis_koeb:
        ejede = [h["ticker"] for h in pf.get("holdings",[])]
        allerede_købt = r["ticker"] in ejede
        k1, k2 = st.columns([2, 2])
        with k1:
            if allerede_købt:
                st.markdown(
                    f'<div style="font-family:Space Mono,monospace;font-size:.68rem;color:#4ade80;padding:.4rem 0">'
                    f'✓ Allerede i portefølje</div>', unsafe_allow_html=True)
            else:
                if st.button(f"🟢 Køb {r['ticker']}", key=f"sig_koeb_{r['ticker']}", use_container_width=True):
                    st.session_state[f"vis_koeb_{r['ticker']}"] = True
        with k2:
            wl = pf.get("watchlist",[])
            if r["ticker"] not in wl and not allerede_købt:
                if st.button(f"+ Watchlist", key=f"sig_wl_{r['ticker']}", use_container_width=True):
                    wl.append(r["ticker"]); pf["watchlist"]=wl
                    engine.gem_portfolio(pf); st.rerun()

    # Vis købs-dialog hvis knap er trykket
    if st.session_state.get(f"vis_koeb_{r['ticker']}"):
        vis_koeb_dialog(r, p, pf, cash_dkk, cash_usd, cash_end)


# ════════════════════════════════════════════════════════════
# HEADER
# ════════════════════════════════════════════════════════════
saelg_alerts = engine.tjek_saelg_signaler()
koeb_alerts  = engine.hent_alerts()

st.markdown(
    '<div class="main-header">'
    '<div><div class="main-title">AI Aktie Rådgiver</div>'
    '<div class="main-subtitle">Groq 70B · RSI/MACD · Insider · Stop-loss · Endavu</div></div>'
    f'<div class="header-date">{datetime.now().strftime("%A %d %B %Y").upper()}'
    '<br><span style="color:#6a6a8a">v7.0</span></div></div>',
    unsafe_allow_html=True)

# Sælg-alerts øverst — vigtigst
for a in saelg_alerts:
    cls = "saelg-stop" if a["farve"]=="#f87171" else "saelg-target" if a["farve"]=="#4ade80" else "saelg-adv"
    st.markdown(
        f'<div class="saelg-banner {cls}">'
        f'<span style="font-family:Space Mono,monospace;font-size:.72rem;font-weight:700;color:{a["farve"]}">'
        f'{"🔴 SÆLG" if a["type"]=="SÆLG" else "⚠️ ADVARSEL"}: {a["ticker"]} — {a["aarsag"]} &nbsp;·&nbsp; {a["afkast"]:+.1f}%'
        f'</span><span style="font-family:Space Mono,monospace;font-size:.62rem;color:#6a6a8a">→ Se Mine Handler</span></div>',
        unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "  OVERSIGT  ", "  PORTEFØLJE  ", "  SIGNALER  ",
    "  MINE HANDLER  ", "  BACKTEST  "
])


# ════════════════════════════════════════════════════════════
# TAB 1: OVERSIGT
# ════════════════════════════════════════════════════════════
with tab1:
    pf       = engine.indlaes_portfolio()
    cash_dkk = pf["cash"].get("nordnet_dkk", 0)
    cash_usd = pf["cash"].get("etoro_usd",   0)
    cash_end = pf["cash"].get("endavu_dkk",  0)
    makro    = engine.hent_makro_data()
    brief    = engine.hent_brief_data()
    handler  = engine.hent_aktive_handler()

    makro_strip(makro)

    # Sælg-signaler preview
    if saelg_alerts:
        sec("⚠️ Kræver Din Opmærksomhed")
        for a in saelg_alerts[:3]:
            cls = "saelg-stop" if a["farve"]=="#f87171" else "saelg-target" if a["farve"]=="#4ade80" else "saelg-adv"
            st.markdown(
                f'<div class="saelg-banner {cls}" style="margin-bottom:.5rem">'
                f'<span style="font-family:Space Mono,monospace;font-size:.72rem;font-weight:700;color:{a["farve"]}">'
                f'{a["ticker"]} — {a["aarsag"]}</span>'
                f'<span style="font-family:Space Mono,monospace;font-size:.65rem;color:#6a6a8a">{a["afkast"]:+.1f}%</span>'
                f'</div>', unsafe_allow_html=True)

    total_handler = sum(h["vaerdi"] for h in handler)
    total_fond = sum(
        (kurs(h["ticker"])["pris"] if kurs(h["ticker"]) else 0) * h["antal"]
        for h in pf.get("holdings",[]) if h["type"] in ["fond","obligation"])

    c1,c2,c3,c4,c5 = st.columns(5)
    for col,lbl,val,sub in [
        (c1,"Fonde · Nordnet",  f"{total_fond:,.0f} DKK", "Fonde + obligationer"),
        (c2,"Mine Handler",     f"{total_handler:,.0f} DKK","Aktive positioner"),
        (c3,"Cash · Nordnet",   f"{cash_dkk:,.0f} DKK",   "Ledig"),
        (c4,"Cash · eToro",     f"${cash_usd:,.2f}",       "USD ledig"),
        (c5,"Cash · Endavu",    f"{cash_end:,.0f} DKK",    "Billig handel"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="metric-label">{lbl}</div>'
                f'<div class="metric-value">{val}</div>'
                f'<div class="metric-sub">{sub}</div></div>', unsafe_allow_html=True)

    # Makro
    if makro:
        sec("Markedsstatus")
        m1,m2,m3 = st.columns(3)
        vix = makro.get("vix",20)
        with m1:
            vc = "#4ade80" if vix<20 else "#facc15" if vix<30 else "#f87171"
            st.markdown(f'<div class="metric-card"><div class="metric-label">VIX</div>'
                        f'<div class="metric-value" style="color:{vc}">{vix:.1f}</div>'
                        f'<div class="metric-sub">{makro.get("vix_status","")}</div></div>', unsafe_allow_html=True)
        with m2:
            sc = "#4ade80" if "Optrend" in makro.get("sp_status","") else "#f87171"
            st.markdown(f'<div class="metric-card"><div class="metric-label">SP500</div>'
                        f'<div class="metric-value" style="color:{sc}">{makro.get("sp_status","–")}</div>'
                        f'<div class="metric-sub">{makro.get("sp_1m_afkast",0):+.1f}% 1M</div></div>', unsafe_allow_html=True)
        with m3:
            rc = "#f87171" if makro.get("rente_advarsel") else "#e8e8f0"
            st.markdown(f'<div class="metric-card"><div class="metric-label">10Y Rente</div>'
                        f'<div class="metric-value" style="color:{rc}">{makro.get("rente_10y","N/A")}</div>'
                        f'<div class="metric-sub">{"⚠ Høj" if makro.get("rente_advarsel") else "Normal"}</div></div>', unsafe_allow_html=True)

    # Top signaler preview
    if brief and brief.get("top_kandidater"):
        sec(f"Dagens Signaler · {brief.get('dato','')}")
        kands = brief["top_kandidater"][:3]
        cols = st.columns(min(3,len(kands)))
        for i, r in enumerate(kands):
            p2 = parse_analyse(r.get("analyse",""))
            rec = p2["anbefaling"].upper()
            rc = "#4ade80" if rec in ["KØB","STÆRKT KØB"] else "#f87171" if rec=="SÆLG" else "#facc15"
            score = r.get("kombineret",5)
            with cols[i%3]:
                st.markdown(
                    f'<div class="opd-kort" style="border-left:2px solid {rc}">'
                    f'<div style="font-family:Space Mono,monospace;font-weight:700">{r["ticker"]}</div>'
                    f'<div style="font-size:.7rem;color:#6a6a8a">{r.get("sektor","")}</div>'
                    f'<div style="font-size:1.3rem;font-weight:800;color:{rc};margin:.2rem 0">{rec}</div>'
                    + badge(score) +
                    f'<div style="font-family:Space Mono,monospace;font-size:.62rem;color:#4a4a6a;margin-top:.3rem">'
                    f'Entry ${p2["entry"]} → Target ${p2["target"]}</div>'
                    f'</div>', unsafe_allow_html=True)

    # Fonde
    sec("Dine Fonde og Obligationer")
    fonde = [h for h in pf.get("holdings",[]) if h["type"] in ["fond","obligation"]]
    if not fonde:
        st.markdown('<p style="color:#4a4a6a;font-size:.82rem">Ingen fonde tilføjet.</p>', unsafe_allow_html=True)
    for h in fonde:
        k2 = kurs(h["ticker"])
        pris = k2["pris"] if k2 else 0; ch = k2["change"] if k2 else 0
        afk = (pris - h["koebspris"])/h["koebspris"]*100 if h["koebspris"] else 0
        pc = "#a0ff8a" if h["platform"]=="endavu" else "#a0a8ff"
        st.markdown(
            f'<div class="h-row">'
            f'<div><div style="font-weight:600">{h["navn"]}</div>'
            f'<div style="font-family:Space Mono,monospace;font-size:.68rem;color:#6a6a8a">'
            f'{h["ticker"]} · <span style="color:{pc}">{h["platform"].upper()}</span> · {h["antal"]} stk</div></div>'
            f'<div style="text-align:right">'
            f'<div style="font-weight:700">{pris*h["antal"]:,.0f} DKK</div>'
            f'<div style="font-family:Space Mono,monospace;font-size:.68rem">'
            f'<span class="{"up" if afk>=0 else "down"}">{afk:+.1f}%</span>'
            f' · <span class="{"up" if ch>=0 else "down"}">{ch:+.2f}% i dag</span></div>'
            f'</div></div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# TAB 2: PORTEFØLJE
# ════════════════════════════════════════════════════════════
with tab2:
    pf = engine.indlaes_portfolio()
    cl, _, cr = st.columns([2,.1,2])
    with cl:
        sec("Tilføj Position (fonde/obligationer)")
        with st.form("add_pos"):
            ti = st.text_input("Ticker", placeholder="SPIDJB.CO, NOVO-B.CO...")
            ni = st.text_input("Navn",   placeholder="Sparindex Global")
            ca,cb = st.columns(2)
            with ca: plat  = st.selectbox("Platform", ["nordnet","etoro","endavu"])
            with cb: type_ = st.selectbox("Type",     ["fond","obligation","aktie"])
            cc,cd = st.columns(2)
            with cc: antal = st.number_input("Antal",    min_value=0.01, value=1.0)
            with cd: kpris = st.number_input("Købspris", min_value=0.01, value=100.0)
            if st.form_submit_button("Tilføj", use_container_width=True):
                if ti and ni:
                    pf["holdings"].append({
                        "ticker":ti.upper(),"navn":ni,"platform":plat,
                        "antal":antal,"koebspris":kpris,"type":type_,"strategi":"hold_forever"})
                    engine.gem_portfolio(pf); st.success(f"{ti.upper()} tilføjet!"); st.rerun()

        sec("Opdater Cash", "margin-top:1.5rem")
        with st.form("cash"):
            ce,cf,cg = st.columns(3)
            with ce: nn = st.number_input("Nordnet DKK", value=float(pf["cash"].get("nordnet_dkk",0)), step=100.0)
            with cf: et = st.number_input("eToro USD",   value=float(pf["cash"].get("etoro_usd",0)),   step=10.0)
            with cg: en = st.number_input("Endavu DKK",  value=float(pf["cash"].get("endavu_dkk",0)),  step=100.0)
            if st.form_submit_button("Opdater", use_container_width=True):
                pf["cash"]["nordnet_dkk"]=nn; pf["cash"]["etoro_usd"]=et; pf["cash"]["endavu_dkk"]=en
                engine.gem_portfolio(pf); st.success("Opdateret!"); st.rerun()

        sec("Watchlist", "margin-top:1.5rem")
        wa,wb = st.columns([3,1])
        with wa:
            ny = st.text_input("Ticker", placeholder="NVDA", label_visibility="collapsed", key="wl_inp")
        with wb:
            if st.button("Tilføj", key="wl_btn", use_container_width=True):
                if ny and ny.upper() not in pf.get("watchlist",[]):
                    pf["watchlist"].append(ny.upper()); engine.gem_portfolio(pf); st.rerun()
        for w in pf.get("watchlist",[]):
            wx,wy = st.columns([5,1])
            with wx:
                k2 = kurs(w); ps = f"${k2['pris']}" if k2 else "–"; cg2 = f"{k2['change']:+.2f}%" if k2 else ""
                cc2 = "up" if k2 and k2["change"]>=0 else "down"
                st.markdown(f'<div style="padding:.4rem 0;font-family:Space Mono,monospace;font-size:.72rem">'
                            f'<b>{w}</b> {ps} <span class="{cc2}">{cg2}</span></div>', unsafe_allow_html=True)
            with wy:
                if st.button("✕", key=f"rm_{w}"):
                    pf["watchlist"].remove(w); engine.gem_portfolio(pf); st.rerun()

    with cr:
        sec("Alle Positioner")
        if not pf.get("holdings"):
            st.markdown('<p style="color:#4a4a6a">Ingen positioner.</p>', unsafe_allow_html=True)
        for i,h in enumerate(pf.get("holdings",[])):
            k2 = kurs(h["ticker"]); pris = k2["pris"] if k2 else h["koebspris"]
            afk = (pris-h["koebspris"])/h["koebspris"]*100 if h["koebspris"] else 0
            pc = "#a0ff8a" if h["platform"]=="endavu" else "#a0a8ff"
            r1,r2 = st.columns([5,1])
            with r1:
                st.markdown(
                    f'<div style="padding:.55rem 0;border-bottom:1px solid rgba(255,255,255,.04)">'
                    f'<span style="font-weight:600">{h["navn"]}</span>'
                    f'<span style="font-family:Space Mono,monospace;font-size:.68rem;color:#6a6a8a"> {h["ticker"]}</span><br>'
                    f'<span style="font-family:Space Mono,monospace;font-size:.65rem">'
                    f'<span style="color:{pc}">{h["platform"].upper()}</span> · {h["antal"]} stk · {h["type"]}'
                    f' · <span class="{"up" if afk>=0 else "down"}">{afk:+.1f}%</span>'
                    f'</span></div>', unsafe_allow_html=True)
            with r2:
                if st.button("Slet", key=f"del_{i}"):
                    pf["holdings"].pop(i); engine.gem_portfolio(pf); st.rerun()


# ════════════════════════════════════════════════════════════
# TAB 3: SIGNALER
# ════════════════════════════════════════════════════════════
with tab3:
    pf       = engine.indlaes_portfolio()
    cash_dkk = pf["cash"].get("nordnet_dkk", 0)
    cash_usd = pf["cash"].get("etoro_usd",   0)
    cash_end = pf["cash"].get("endavu_dkk",  0)
    makro    = engine.hent_makro_data()
    brief    = engine.hent_brief_data()
    screener = engine.hent_screener_data()

    makro_strip(makro)

    # ── Data-status banner ────────────────────────────────────
    brief_dato  = brief.get("dato", "")  if brief  else ""
    screen_dato = screener.get("dato","") if screener else ""
    sidst_dato  = brief_dato or screen_dato or "Ingen data"
    st.markdown(
        f'<div style="font-family:Space Mono,monospace;font-size:.65rem;color:#4a4a6a;'
        f'background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.05);border-radius:6px;'
        f'padding:.5rem 1rem;margin-bottom:.8rem">'
        f'Data sidst opdateret: <b style="color:#a0a8ff">{sidst_dato}</b> &nbsp;·&nbsp; '
        f'Scanning kører automatisk man–fre kl 07:00 &nbsp;·&nbsp; '
        f'Genindlæs siden efter scanning for at se ny data'
        f'</div>', unsafe_allow_html=True)

    st.markdown(
        '<div class="info-box">Systemet finder de <b>1-5 bedste signaler</b> hvor fundamental, teknisk '
        'og sentiment alle peger samme vej. Klik <b>🟢 Køb</b> for at registrere en handel — '
        'appen tracker stop-loss og target automatisk.</div>', unsafe_allow_html=True)

    ka,kb = st.columns([1,1])
    with ka:
        if st.button("▶ Hurtig Scanning (~15 min)", use_container_width=True,
                     help="Starter scanning via GitHub Actions"):
            ok, err = trigger_github_scanning("hurtig")
            if ok:
                st.success("✅ Scanning startet på GitHub Actions! Vent ~15 min og genindlæs siden.")
            else:
                st.error(f"Fejl: {err}")
    with kb:
        if st.button("▶ Komplet Scanning (~30 min)", use_container_width=True,
                     help="Starter komplet scanning via GitHub Actions"):
            ok, err = trigger_github_scanning("komplet")
            if ok:
                st.success("✅ Komplet scanning startet! Vent ~30 min og genindlæs siden.")
            else:
                st.error(f"Fejl: {err}")

    if not brief and not screener:
        st.markdown(
            '<div style="text-align:center;padding:4rem;color:#4a4a6a">'
            '<div style="font-family:Space Mono,monospace;font-size:1.1rem">INGEN DATA</div>'
            '<div style="font-size:.82rem;margin-top:.5rem">Kør en scanning ovenfor</div>'
            '</div>', unsafe_allow_html=True)
    else:
        # ── Groq-analyserede signaler ──────────────────────
        if brief and brief.get("top_kandidater"):
            kands = brief["top_kandidater"]
            koeb  = [r for r in kands if parse_analyse(r.get("analyse",""))["anbefaling"].upper() in ["KØB","STÆRKT KØB"]]
            saelg = [r for r in kands if parse_analyse(r.get("analyse",""))["anbefaling"].upper() == "SÆLG"]
            hold  = [r for r in kands if parse_analyse(r.get("analyse",""))["anbefaling"].upper() in ["HOLD","VENT"]]

            sec(f"Handelsanbefalinger · Groq 70b · {brief.get('dato','')}")

            if koeb:
                st.markdown('<p style="font-family:Space Mono,monospace;font-size:.68rem;color:#4ade80;margin-bottom:.8rem">▸ KØB SIGNALER</p>', unsafe_allow_html=True)
                for r in koeb:
                    vis_signal_kort(r, cash_dkk, cash_usd, cash_end, pf)

            if saelg:
                st.markdown('<p style="font-family:Space Mono,monospace;font-size:.68rem;color:#f87171;margin:1.2rem 0 .8rem">▸ SÆLG SIGNALER</p>', unsafe_allow_html=True)
                for r in saelg:
                    vis_signal_kort(r, cash_dkk, cash_usd, cash_end, pf, vis_koeb=False)

            if hold and not koeb and not saelg:
                st.markdown('<p style="font-family:Space Mono,monospace;font-size:.68rem;color:#facc15;margin-bottom:.8rem">▸ HOLD / VENT</p>', unsafe_allow_html=True)
                for r in hold:
                    vis_signal_kort(r, cash_dkk, cash_usd, cash_end, pf, vis_koeb=False)

        # ── Interessante opdagelser ────────────────────────
        if screener and screener.get("resultater"):
            alle = screener["resultater"]
            brief_tickers = {r["ticker"] for r in (brief or {}).get("top_kandidater",[])}
            opd = [r for r in alle if r["samlet"]>=7.0 and r["ticker"] not in brief_tickers][:6]
            momentum = [r for r in alle
                        if ok_tal(r.get("teknik_data",{}).get("pct_fra_52w_high"))
                        and r.get("teknik_data",{}).get("pct_fra_52w_high",-100) > -5
                        and r["ticker"] not in brief_tickers and r not in opd][:3]

            if opd or momentum:
                sec(f"Interessante Opdagelser · {screener.get('dato','')}", "margin-top:2rem")
                st.markdown(
                    '<p style="font-size:.78rem;color:#8a8aaa;margin-bottom:1rem">'
                    'God screener-score men ikke Groq-analyseret endnu. '
                    'Kør komplet scanning for dyb analyse.</p>', unsafe_allow_html=True)
                if opd:
                    cols = st.columns(min(3,len(opd)))
                    for i,r in enumerate(opd):
                        s2 = r["samlet"]; tc = "#4ade80" if s2>=8.5 else "#facc15" if s2>=7 else "#f87171"
                        td = r.get("teknik_data",{}); fd = r.get("fund_data",{})
                        bits2 = []
                        if fd.get("rev_growth"): bits2.append(f"Rev {fd['rev_growth']:+.0f}%")
                        if fd.get("pe"):         bits2.append(f"P/E {fd['pe']:.0f}")
                        if ok_tal(td.get("rsi")): bits2.append(f"RSI {td['rsi']:.0f}")
                        pos3 = engine.beregn_position(s2, cash_dkk, cash_usd, r["ticker"].endswith(".CO"))
                        with cols[i%3]:
                            st.markdown(
                                f'<div class="opd-kort">'
                                f'<div style="font-family:Space Mono,monospace;font-weight:700">{r["ticker"]}</div>'
                                f'<div style="font-size:.68rem;color:#6a6a8a">{r.get("sektor","")}</div>'
                                f'<div style="font-size:1.4rem;font-weight:800;color:{tc};margin:.2rem 0">{s2}</div>'
                                + badge(s2) + tek_grid(td) +
                                f'<div style="font-family:Space Mono,monospace;font-size:.6rem;color:#4a4a6a;margin-top:.3rem">{" · ".join(bits2)}</div>'
                                + (f'<div style="font-family:Space Mono,monospace;font-size:.6rem;color:#a0a8ff;margin-top:.3rem">'
                                   f'{pos3["platform"]}: max {pos3["beloeb"]} {pos3["valuta"]}</div>'
                                   if pos3["beloeb"]>0 else '') +
                                f'</div>', unsafe_allow_html=True)
                            wl2 = pf.get("watchlist",[])
                            ejede2 = [h["ticker"] for h in pf.get("holdings",[])]
                            allerede_kobt2 = r["ticker"] in ejede2
                            if allerede_kobt2:
                                st.markdown(
                                    '<div style="font-family:Space Mono,monospace;font-size:.65rem;'
                                    'color:#4ade80;padding:.3rem 0">✓ I portefølje</div>',
                                    unsafe_allow_html=True)
                            else:
                                b1o, b2o = st.columns(2)
                                with b1o:
                                    if st.button(f"🟢 Køb", key=f"koeb_opd_{i}_{r['ticker']}", use_container_width=True):
                                        st.session_state[f"vis_koeb_{r['ticker']}"] = True
                                with b2o:
                                    if r["ticker"] not in wl2:
                                        if st.button("+ WL", key=f"wl_opd2_{i}_{r['ticker']}", use_container_width=True):
                                            wl2.append(r["ticker"]); pf["watchlist"]=wl2
                                            engine.gem_portfolio(pf); st.rerun()
                            # Vis købs-dialog for screener-opdagelse
                            if st.session_state.get(f"vis_koeb_{r['ticker']}"):
                                p_dummy = {"entry": str(round(kurs(r["ticker"])["pris"],2)) if kurs(r["ticker"]) else "-",
                                           "stop": "-", "target": "-"}
                                vis_koeb_dialog(r, p_dummy, pf, cash_dkk, cash_usd, cash_end)

        # Fuld tabel
        if screener:
            with st.expander("Vis alle screenede aktier"):
                tabel = []
                for r in screener.get("resultater",[]):
                    td2=r.get("teknik_data",{}); fd2=r.get("fund_data",{})
                    tabel.append({
                        "Ticker":r["ticker"],"Sektor":r["sektor"],"Score":r["samlet"],
                        "Fund":r["fundamental"],"Tek":r["teknisk"],
                        "RSI":f'{td2.get("rsi","–"):.1f}' if ok_tal(td2.get("rsi")) else "–",
                        "1M%":f'{td2.get("afkast_1m","–"):+.1f}%' if ok_tal(td2.get("afkast_1m")) else "–",
                        "Rev%":f'{fd2.get("rev_growth","–"):+.0f}%' if fd2.get("rev_growth") else "–",
                        "Anbefaling":r.get("anbefaling",""),
                    })
                st.dataframe(tabel, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════
# TAB 4: MINE HANDLER
# ════════════════════════════════════════════════════════════
with tab4:
    handler = engine.hent_aktive_handler()
    pf2     = engine.indlaes_portfolio()

    sec("Mine Aktive Handler · Købt via systemet")

    if saelg_alerts:
        st.markdown(f'<div style="font-family:Space Mono,monospace;font-size:.7rem;color:#f87171;'
                    f'background:rgba(248,113,113,.08);border:1px solid rgba(248,113,113,.2);'
                    f'border-radius:8px;padding:.7rem 1rem;margin-bottom:1rem">'
                    f'⚠️ {len(saelg_alerts)} aktiv(e) sælg-signal(er) — se nedenfor</div>',
                    unsafe_allow_html=True)

    if not handler:
        st.markdown(
            '<div class="info-box">Ingen aktive handler endnu. '
            'Gå til <b>Signaler</b> og klik <b>Køb</b> på et signal for at registrere et køb.</div>',
            unsafe_allow_html=True)
    else:
        for h in handler:
            # Bestem rammefarve
            if h["signal"] == "STOP_LOSS_HIT":
                brd = "#f87171"; signal_txt = "🔴 SÆLG — Stop-loss ramt!"
            elif h["signal"] == "TARGET_NAAET":
                brd = "#4ade80"; signal_txt = "🟢 SÆLG — Target nået!"
            elif h["signal"] == "STOR_TAB":
                brd = "#facc15"; signal_txt = "⚠️ Stor nedgang"
            else:
                brd = "rgba(255,255,255,.1)"; signal_txt = ""

            afk_c = "up" if h["afkast"]>=0 else "down"
            plat_c = "#a0ff8a" if h["platform"]=="endavu" else "#a0a8ff"

            # Stop-loss progress bar
            sl_pct = 0
            if h["stop_loss"] and h["target"] and h["koebspris"]:
                range_total = h["target"] - h["stop_loss"]
                if range_total > 0:
                    sl_pct = max(0, min(100, (h["pris_nu"] - h["stop_loss"]) / range_total * 100))

            st.markdown(
                f'<div class="handel-kort" style="border-left:3px solid {brd}">'
                f'<div class="handel-header">'
                f'<div>'
                f'<div style="font-family:Space Mono,monospace;font-size:1rem;font-weight:700">{h["ticker"]}</div>'
                f'<div style="font-size:.72rem;color:#6a6a8a">{h["navn"]} · <span style="color:{plat_c}">{h["platform"].upper()}</span> · købt {h["dato"]}</div>'
                + (f'<div style="font-family:Space Mono,monospace;font-size:.68rem;color:{brd};font-weight:700;margin-top:.3rem">{signal_txt}</div>' if signal_txt else '') +
                f'</div>'
                f'<div style="text-align:right">'
                f'<div style="font-size:1.3rem;font-weight:800;class="{afk_c}" style="color:{"#4ade80" if h["afkast"]>=0 else "#f87171"}">{h["afkast"]:+.1f}%</div>'
                f'<div style="font-family:Space Mono,monospace;font-size:.68rem;color:#6a6a8a">${h["pris_nu"]:.2f} nu · ${h["koebspris"]:.2f} købt</div>'
                f'<div style="font-family:Space Mono,monospace;font-size:.65rem;color:#4a4a6a">{h["antal"]} stk · {h["vaerdi"]:.0f} {h["valuta"]}</div>'
                f'</div></div>'
                f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:.4rem;'
                f'background:rgba(0,0,0,.15);padding:.5rem .7rem;border-radius:6px;margin:.7rem 0;'
                f'font-family:Space Mono,monospace;font-size:.65rem">'
                f'<div><span style="color:#4a4a6a">STOP LOSS</span><br>'
                f'<span style="color:#f87171;font-weight:700">${h["stop_loss"]:.2f}</span></div>'
                f'<div><span style="color:#4a4a6a">TARGET</span><br>'
                f'<span style="color:#4ade80;font-weight:700">${h["target"]:.2f}</span></div>'
                f'<div><span style="color:#4a4a6a">SCORE VED KØB</span><br>'
                f'<span style="font-weight:700">{h["score"]}</span></div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True)

            # Sælg-knap
            sc1, sc2, sc3 = st.columns([2,2,2])
            with sc1:
                salgs_pris = st.number_input(
                    "Salgspris ($)",
                    min_value=0.01,
                    value=float(round(h["pris_nu"],2)),
                    step=0.5,
                    key=f"sp_{h['id']}"
                )
            with sc2:
                if st.button(f"🔴 Registrer salg {h['ticker']}", key=f"saelg_{h['id']}", use_container_width=True):
                    engine.registrer_salg(h["id"], salgs_pris, "Manuel")
                    st.success(f"{h['ticker']} solgt til ${salgs_pris:.2f}!")
                    st.cache_data.clear(); st.rerun()
            with sc3:
                if signal_txt and st.button(f"Sælg til markedspris", key=f"saelg_mkt_{h['id']}", use_container_width=True):
                    engine.registrer_salg(h["id"], h["pris_nu"],
                                          "Stop-loss" if h["signal"]=="STOP_LOSS_HIT" else "Target")
                    st.success(f"{h['ticker']} solgt til ${h['pris_nu']:.2f}!")
                    st.cache_data.clear(); st.rerun()

    # Historik fra JSON
    sec("Afsluttede Handler", "margin-top:2rem")
    alle_handler = engine._safe_json_load(engine.AKTIVE_HANDLER_FILE) or []
    solgte = [h for h in alle_handler if h.get("status") == "solgt"]
    if not solgte:
        st.markdown('<p style="color:#4a4a6a;font-size:.82rem">Ingen afsluttede handler endnu.</p>', unsafe_allow_html=True)
    for h in solgte:
        afk2 = h.get("afkast_pct", 0) or 0
        afk_c2 = "up" if afk2 >= 0 else "down"
        kp2 = h.get("koebspris", 0)
        sp2 = h.get("salgspris", 0)
        st.markdown(
            f'<div class="bt-row">'
            f'<span style="font-weight:600;min-width:60px">{h.get("ticker","")}</span>'
            f'<span style="color:#6a6a8a;min-width:80px">{h.get("dato_solgt","")}</span>'
            f'<span style="color:#6a6a8a">{h.get("antal",0)} stk</span>'
            f'<span style="color:#6a6a8a">${kp2:.2f} → ${sp2:.2f}</span>'
            f'<span class="{afk_c2}" style="font-weight:700">{afk2:+.1f}%</span>'
            f'</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# TAB 5: BACKTEST
# ════════════════════════════════════════════════════════════
with tab5:
    sec("Backtest · Virker Modellen?")
    st.markdown(
        '<div class="info-box">Systemet tracker alle Groq-anbefalinger. '
        'Efter 30 dage beregner det om retningen var rigtig. '
        'Kræver 30+ dages historik.</div>', unsafe_allow_html=True)

    if st.button("Opdater Backtest", use_container_width=False):
        with st.spinner("Beregner..."): statistik = engine.koer_backtest()
        st.success("Opdateret!"); st.rerun()

    data_bt = engine.hent_backtest_data()
    if not data_bt or data_bt.get("antal_anbefalinger",0)==0:
        st.markdown(
            f'<div class="info-box" style="color:#6a6a8a">'
            f'{data_bt.get("besked","Ingen data endnu.") if data_bt else "Klik Opdater Backtest."}'
            f'</div>', unsafe_allow_html=True)
    else:
        b1,b2,b3,b4 = st.columns(4)
        for col,lbl,val,sub,clr in [
            (b1,"Anbefalinger",str(data_bt["antal_anbefalinger"]),"total","#e8e8f0"),
            (b2,"Hit Rate",f'{data_bt["hit_rate_pct"]:.1f}%',"korrekt retning",
             "#4ade80" if data_bt["hit_rate_pct"]>55 else "#facc15" if data_bt["hit_rate_pct"]>45 else "#f87171"),
            (b3,"Gns afkast 30d",f'{data_bt["gns_afkast_30d_pct"]:+.1f}%',"alle",
             "#4ade80" if data_bt["gns_afkast_30d_pct"]>0 else "#f87171"),
            (b4,"Gns KØB afkast",f'{data_bt["gns_afkast_koeb_pct"]:+.1f}%',"kun køb",
             "#4ade80" if data_bt["gns_afkast_koeb_pct"]>0 else "#f87171"),
        ]:
            with col:
                st.markdown(f'<div class="metric-card"><div class="metric-label">{lbl}</div>'
                            f'<div class="metric-value" style="color:{clr}">{val}</div>'
                            f'<div class="metric-sub">{sub}</div></div>', unsafe_allow_html=True)
        sec("Seneste 20 Anbefalinger")
        for r in data_bt.get("seneste_resultater",[]):
            afl=r.get("afkast_30d",0) or 0; anb=r.get("anbefaling","")
            ok=(anb in ["KØB","STÆRKT KØB"] and afl>0) or (anb=="SÆLG" and afl<0)
            st.markdown(
                f'<div class="bt-row">'
                f'<span style="color:{"#4ade80" if ok else "#f87171"};font-weight:700">{"✓" if ok else "✗"}</span>'
                f'<span style="font-weight:600;min-width:60px">{r.get("ticker","")}</span>'
                f'<span style="color:#6a6a8a;min-width:85px">{r.get("dato","")}</span>'
                f'<span style="min-width:100px">{anb}</span>'
                f'<span style="color:#6a6a8a">{r.get("pris_koeb",0):.2f}→{r.get("pris_30d",0):.2f}</span>'
                f'<span style="color:{"#4ade80" if afl>0 else "#f87171"};font-weight:700">{afl:+.1f}%</span>'
                f'</div>', unsafe_allow_html=True)


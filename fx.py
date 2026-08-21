"""داشبورد RTM — همیشه عدد ورود، حد ضرر و تارگت را نشان می‌دهد."""

import os
import sys
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
import yfinance as yf

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.data_fetcher import DataFetcher
from src.rtm import RTMStrategy


st.set_page_config(page_title="RTM یورو دلار", page_icon="📉", layout="wide")
st.markdown(
    """
<style>
  .main { direction: rtl; text-align: right; }
  .banner { padding: 18px 22px; border-radius: 16px; font-size: 22px; font-weight: 800; margin: 8px 0 18px; }
  .wait { background:#3b2a05; color:#fde68a; border:1px solid #f59e0b; }
  .buy { background:#052e16; color:#bbf7d0; border:1px solid #22c55e; }
  .sell { background:#450a0a; color:#fecaca; border:1px solid #ef4444; }
  .num { background:#0f172a; border-radius:16px; padding:18px 10px; text-align:center; border:2px solid #334155; }
  .num .lbl { font-size:15px; color:#94a3b8; }
  .num .val { font-size:34px; font-weight:900; letter-spacing:0.5px; color:#fff; font-family: ui-monospace, monospace; }
  .num .sub { font-size:13px; color:#cbd5e1; margin-top:4px; }
</style>
""",
    unsafe_allow_html=True,
)


def _strip_tz(series):
    ts = pd.to_datetime(series)
    try:
        return ts.dt.tz_localize(None)
    except TypeError:
        try:
            return ts.dt.tz_convert(None)
        except Exception:
            return ts


@st.cache_data(ttl=180)
def fetch_data(period, interval):
    fetcher = DataFetcher()
    if interval == "1m" and period not in ("1d", "5d"):
        period = "5d"
    try:
        df = yf.Ticker("EURUSD=X").history(period=period, interval=interval)
        if df is not None and not df.empty:
            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            if "datetime" in df.columns:
                df["timestamps"] = _strip_tz(df["datetime"])
            elif "date" in df.columns:
                df["timestamps"] = _strip_tz(df["date"])
            return df
    except Exception:
        pass
    return fetcher._generate_sample_data()


def get_live_price():
    try:
        res = requests.post(
            "https://scanner.tradingview.com/forex/scan",
            json={"symbols": {"tickers": ["FX_IDC:EURUSD"]}, "columns": ["close", "bid", "ask"]},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=3,
        )
        if res.status_code == 200 and res.json().get("data"):
            v = res.json()["data"][0]["d"]
            price = float(v[0])
            bid = float(v[1]) if v[1] else round(price - 0.00006, 5)
            ask = float(v[2]) if v[2] else round(price + 0.00006, 5)
            return price, bid, ask
    except Exception:
        pass
    try:
        data = yf.Ticker("EURUSD=X").history(period="1d", interval="1m")
        if not data.empty:
            price = float(data["Close"].iloc[-1])
            return price, round(price - 0.00006, 5), round(price + 0.00006, 5)
    except Exception:
        pass
    return None, None, None


def analyze(period, interval, config):
    df = fetch_data(period, interval)
    live, bid, ask = get_live_price()
    if live is not None and df is not None and not df.empty:
        df.loc[df.index[-1], "close"] = live
    strategy = RTMStrategy(config=config)
    ctx, plan = strategy.analyze(df)
    return {
        "df": df,
        "ctx": ctx,
        "plan": plan,
        "live": live,
        "bid": bid,
        "ask": ask,
        "updated": datetime.now().strftime("%H:%M:%S"),
    }


def card(title, value, sub, color):
    shown = f"{value:.5f}" if value else "—"
    return f"""
    <div class="num" style="border-color:{color}">
      <div class="lbl">{title}</div>
      <div class="val" style="color:{color}">{shown}</div>
      <div class="sub">{sub}</div>
    </div>
    """


with st.sidebar:
    st.header("تنظیمات RTM")
    period = st.selectbox("بازه", ["5d", "1mo", "3mo"], index=1)
    interval = st.selectbox("تایم‌فریم", ["1m", "5m", "15m", "30m", "1h"], index=0)
    if interval == "1m":
        st.caption("تایم ۱ دقیقه فقط با بازه ۵ روز کار می‌کند.")
    max_zone = st.slider("حداکثر عرض ناحیه (پیپ)", 12, 35, 28)
    min_rr = st.slider("حداقل سود به ضرر", 1.0, 3.0, 1.2, 0.1)
    analyze_btn = st.button("تحلیل مجدد بازار", type="primary", width="stretch")
    st.caption("ریفرش فقط قیمت را عوض می‌کند. اعداد ورود/حدضرر/تارگت ثابت می‌مانند مگر قیمت به ناحیه برسد.")

config = {"max_zone_pips": max_zone, "min_rr": min_rr}

if "rtm" not in st.session_state or analyze_btn:
    with st.spinner("در حال خواندن نواحی RTM..."):
        st.session_state.rtm = analyze(period, interval, config)

state = st.session_state.rtm
df, ctx, plan = state["df"], state["ctx"], state["plan"]

st.title("نقاط معامله RTM — EUR/USD")
st.caption("نسخه RTM-3 | اگر هنوز EMA و RSI می‌بینید، در Streamlit روی Reboot app بزنید.")

top1, top2, top3 = st.columns([2, 1, 2])
with top2:
    if st.button("ریفرش قیمت", width="stretch"):
        live, bid, ask = get_live_price()
        if live:
            state["live"], state["bid"], state["ask"] = live, bid, ask
            state["updated"] = datetime.now().strftime("%H:%M:%S")
            plan.apply_price(live)
        else:
            st.warning("قیمت زنده نیامد.")

live = state.get("live")
price = live if live else float(df["close"].iloc[-1])
plan.apply_price(price)

with top1:
    prev = float(df["close"].iloc[-2]) if len(df) > 1 else price
    chg = (price - prev) / prev * 100 if prev else 0
    st.metric("قیمت زنده", f"{price:.5f}", f"{chg:+.3f}%")
with top3:
    st.write(f"ساختار: **{ctx.structure_text}**")
    st.write(f"آخرین قیمت: **{state.get('updated', '—')}** | فاصله تا ورود: **{plan.distance_pips:.1f} پیپ**")

if plan.status == "ENTER" and plan.side == "BUY":
    st.markdown(f'<div class="banner buy">{plan.reason}</div>', unsafe_allow_html=True)
elif plan.status == "ENTER" and plan.side == "SELL":
    st.markdown(f'<div class="banner sell">{plan.reason}</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="banner wait">{plan.reason or "صبر کن"}</div>', unsafe_allow_html=True)

side_fa = {"BUY": "خرید", "SELL": "فروش", "NONE": "بدون معامله"}.get(plan.side, plan.side)
st.subheader(f"اعداد معامله — {side_fa} {plan.pattern}")

c1, c2, c3 = st.columns(3)
with c1:
    st.markdown(card("ورود", plan.entry, "لیمیت روی لبه ناحیه", "#fbbf24"), unsafe_allow_html=True)
with c2:
    st.markdown(card("حد ضرر SL", plan.sl, f"{plan.sl_pips} پیپ ریسک", "#ef4444"), unsafe_allow_html=True)
with c3:
    st.markdown(card("تارگت TP", plan.tp, f"{plan.tp_pips} پیپ سود", "#22c55e"), unsafe_allow_html=True)

if plan.entry:
    rr = (plan.tp_pips / plan.sl_pips) if plan.sl_pips else 0
    st.info(
        f"ورود: `{plan.entry:.5f}` &nbsp;|&nbsp; حد ضرر: `{plan.sl:.5f}` &nbsp;|&nbsp; "
        f"تارگت: `{plan.tp:.5f}` &nbsp;|&nbsp; نسبت سود به ضرر: **1:{rr:.1f}**"
    )
else:
    st.warning("الان ستاپ RTM معتبر نیست. صبر کن.")

if ctx.alt_plan and ctx.alt_plan.entry:
    alt = ctx.alt_plan
    st.caption(
        f"پلن مخالف: {alt.side} ورود `{alt.entry:.5f}` | SL `{alt.sl:.5f}` | TP `{alt.tp:.5f}`"
    )

st.markdown("---")
st.subheader("نمودار نواحی")
fig = go.Figure()
chart = df.tail(130)
x = chart["timestamps"] if "timestamps" in chart.columns else chart.index
fig.add_trace(
    go.Candlestick(
        x=x,
        open=chart["open"],
        high=chart["high"],
        low=chart["low"],
        close=chart["close"],
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
        name="قیمت",
    )
)
for zone in ctx.zones[-8:]:
    color = "rgba(34,197,94,0.15)" if zone.kind == "demand" else "rgba(239,68,68,0.15)"
    fig.add_hrect(y0=zone.low, y1=zone.high, fillcolor=color, line_width=0)
if plan.entry:
    fig.add_hline(y=plan.entry, line_dash="dash", line_color="#fbbf24", annotation_text="ورود")
    fig.add_hline(y=plan.sl, line_dash="dot", line_color="#ef4444", annotation_text="SL")
    fig.add_hline(y=plan.tp, line_dash="dot", line_color="#22c55e", annotation_text="TP")
fig.update_layout(
    template="plotly_dark",
    height=480,
    xaxis_rangeslider_visible=False,
    margin=dict(l=8, r=8, t=16, b=8),
    paper_bgcolor="#0b1020",
    plot_bgcolor="#0b1020",
)
st.plotly_chart(fig, width="stretch")

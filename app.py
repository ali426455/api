"""
داشبورد RTM برای اسکالپ EUR/USD
ورود / حد ضرر / خروج — اگر بازار مناسب نبود: صبر کن
"""

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

from src.backtest import BacktestEngine
from src.data_fetcher import DataFetcher
from src.rtm import RTMStrategy
from src.strategy import SignalType


st.set_page_config(
    page_title="ربات RTM یورو/دلار",
    page_icon="📉",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .main { direction: rtl; text-align: right; }
    h1, h2, h3 { color: #7dd3fc; }
    .price-box { background:#111827; border:1px solid #334155; border-radius:14px; padding:16px 18px; }
    .card { background:#111827; border-radius:14px; padding:16px; text-align:center; border:1px solid #334155; }
    .wait-banner { background:#422006; border:1px solid #f59e0b; color:#fde68a; padding:18px 20px; border-radius:14px; font-size:20px; font-weight:700; }
    .buy-banner { background:#052e16; border:1px solid #22c55e; color:#bbf7d0; padding:18px 20px; border-radius:14px; font-size:20px; font-weight:700; }
    .sell-banner { background:#450a0a; border:1px solid #ef4444; color:#fecaca; padding:18px 20px; border-radius:14px; font-size:20px; font-weight:700; }
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
    try:
        ticker = yf.Ticker("EURUSD=X")
        df = ticker.history(period=period, interval=interval)
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
        url = "https://scanner.tradingview.com/forex/scan"
        payload = {"symbols": {"tickers": ["FX_IDC:EURUSD"]}, "columns": ["close", "bid", "ask"]}
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.post(url, json=payload, headers=headers, timeout=3)
        if res.status_code == 200 and res.json().get("data"):
            values = res.json()["data"][0]["d"]
            price = float(values[0])
            bid = float(values[1]) if values[1] else round(price - 0.00006, 5)
            ask = float(values[2]) if values[2] else round(price + 0.00006, 5)
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


def level_card(title, value, sub, color):
    return f"""
    <div class="card" style="border-color:{color};">
        <div style="color:{color}; font-size:13px;">{title}</div>
        <div style="color:#fff; font-size:26px; font-weight:800; letter-spacing:0.5px;">{value}</div>
        <div style="color:#94a3b8; font-size:12px;">{sub}</div>
    </div>
    """


def run_analysis(period, interval, config):
    df = fetch_data(period, interval)
    live, bid, ask = get_live_price()
    if live and df is not None and not df.empty:
        df.loc[df.index[-1], "close"] = live
    strategy = RTMStrategy(config=config)
    ctx, signal = strategy.analyze(df)
    return {
        "df": df,
        "signal": signal,
        "ctx": ctx,
        "live": live,
        "bid": bid,
        "ask": ask,
        "updated": datetime.now().strftime("%H:%M:%S"),
    }


with st.sidebar:
    st.header("تنظیمات RTM")
    period = st.selectbox("بازه داده", ["5d", "1mo", "3mo"], index=1)
    interval = st.selectbox("تایم‌فریم", ["5m", "15m", "30m", "1h"], index=0)
    swing_n = st.slider("حساسیت سوئینگ", 2, 6, 3)
    max_zone = st.slider("حداکثر عرض ناحیه (پیپ)", 10, 35, 22)
    min_rr = st.slider("حداقل نسبت سود به ضرر", 1.0, 3.0, 1.5, 0.1)
    min_conf = st.slider("حداقل اطمینان", 50, 85, 62)
    analyze_btn = st.button("تحلیل مجدد بازار", type="primary", use_container_width=True)
    st.caption("دکمه ریفرش بالا فقط قیمت را عوض می‌کند، تحلیل را تکرار نمی‌کند.")


config = {
    "swing_n": swing_n,
    "max_zone_pips": max_zone,
    "min_rr": min_rr,
    "min_confidence": min_conf,
}

if "analysis" not in st.session_state or analyze_btn:
    with st.spinner("در حال خواندن ساختار بازار و نواحی RTM..."):
        st.session_state.analysis = run_analysis(period, interval, config)

state = st.session_state.analysis
df = state["df"]
signal = state["signal"]
ctx = state["ctx"]

st.title("ربات اسکالپ EUR/USD — استراتژی RTM")
st.caption("ورود فقط روی ناحیه عرضه/تقاضا. اگر ستاپ نباشد، صبر کن.")

price_col, btn_col, meta_col = st.columns([2.2, 1, 2])
with btn_col:
    refresh_price = st.button("ریفرش قیمت", use_container_width=True)

if refresh_price:
    live, bid, ask = get_live_price()
    if live:
        state["live"] = live
        state["bid"] = bid
        state["ask"] = ask
        state["updated"] = datetime.now().strftime("%H:%M:%S")
    else:
        st.warning("قیمت زنده الان در دسترس نبود. همان قیمت قبلی نمایش داده می‌شود.")

live = state.get("live")
price = live if live else float(df["close"].iloc[-1])

with price_col:
    prev = float(df["close"].iloc[-2]) if len(df) > 1 else price
    delta = (price - prev) / prev * 100 if prev else 0
    st.metric("قیمت زنده EUR/USD", f"{price:.5f}", f"{delta:+.3f}%")

with meta_col:
    bid = state.get("bid")
    ask = state.get("ask")
    spread = f"{((ask - bid) / 0.0001):.1f} پیپ" if bid and ask else "—"
    st.write(f"ساختار: **{ctx.structure_text}**")
    st.write(f"اسپرد: **{spread}** | به‌روزرسانی قیمت: **{state.get('updated', '—')}**")

st.markdown("---")

if signal.signal_type == SignalType.BUY:
    st.markdown(f'<div class="buy-banner">خرید — {signal.reason}</div>', unsafe_allow_html=True)
elif signal.signal_type == SignalType.SELL:
    st.markdown(f'<div class="sell-banner">فروش — {signal.reason}</div>', unsafe_allow_html=True)
else:
    st.markdown(f'<div class="wait-banner">{signal.reason}</div>', unsafe_allow_html=True)

st.write("")

if signal.signal_type != SignalType.WAIT:
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            level_card("نقطه ورود", f"{signal.entry_price:.5f}", signal.order_type.value, "#fbbf24"),
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            level_card("حد ضرر", f"{signal.stop_loss:.5f}", f"{signal.sl_pips} پیپ", "#ef4444"),
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            level_card("نقطه خروج", f"{signal.take_profit_1:.5f}", f"{signal.tp1_pips} پیپ", "#22c55e"),
            unsafe_allow_html=True,
        )
    distance = abs(price - signal.entry_price) / 0.0001
    st.info(
        f"اطمینان ستاپ: **{signal.confidence:.0f}٪** | فاصله قیمت فعلی تا ورود: **{distance:.1f} پیپ**"
    )
else:
    st.warning("الان وارد معامله نشو. صبر کن تا قیمت به ناحیه تازه عرضه یا تقاضا برسد.")

st.markdown("---")
st.subheader("نمودار نواحی RTM")

fig = go.Figure()
chart = df.tail(120).copy()
xcol = "timestamps" if "timestamps" in chart.columns else chart.index
fig.add_trace(
    go.Candlestick(
        x=chart[xcol] if "timestamps" in chart.columns else chart.index,
        open=chart["open"],
        high=chart["high"],
        low=chart["low"],
        close=chart["close"],
        name="قیمت",
        increasing_line_color="#22c55e",
        decreasing_line_color="#ef4444",
    )
)

for zone in ctx.zones[-8:]:
    color = "rgba(34,197,94,0.16)" if zone.kind == "demand" else "rgba(239,68,68,0.16)"
    line = "#22c55e" if zone.kind == "demand" else "#ef4444"
    fig.add_hrect(
        y0=zone.low,
        y1=zone.high,
        fillcolor=color,
        line_width=0,
        annotation_text=f"{zone.pattern}{' تازه' if zone.fresh else ''}",
        annotation_position="top left",
    )
    fig.add_hline(y=zone.proximal, line_dash="dot", line_color=line, line_width=1)

if signal.signal_type != SignalType.WAIT:
    fig.add_hline(y=signal.entry_price, line_dash="dash", line_color="#fbbf24", annotation_text="ورود")
    fig.add_hline(y=signal.stop_loss, line_dash="dot", line_color="#ef4444", annotation_text="حد ضرر")
    fig.add_hline(y=signal.take_profit_1, line_dash="dot", line_color="#22c55e", annotation_text="خروج")

fig.update_layout(
    template="plotly_dark",
    height=480,
    xaxis_rangeslider_visible=False,
    margin=dict(l=10, r=10, t=20, b=10),
    paper_bgcolor="#0b1020",
    plot_bgcolor="#0b1020",
)
st.plotly_chart(fig, use_container_width=True)

with st.expander("جزئیات نواحی و بک‌تست"):
    if ctx.zones:
        rows = []
        for z in ctx.zones[-10:]:
            rows.append(
                {
                    "نوع": "تقاضا" if z.kind == "demand" else "عرضه",
                    "الگو": z.pattern,
                    "پایین": f"{z.low:.5f}",
                    "بالا": f"{z.high:.5f}",
                    "عرض": f"{z.width_pips:.1f}",
                    "تازه": "بله" if z.fresh else "خیر",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True)
    if st.button("اجرای بک‌تست RTM"):
        engine = BacktestEngine(strategy=RTMStrategy(config=config), initial_balance=10000, spread_pips=1.2)
        result = engine.run(df, lookback=min(140, max(40, len(df) // 2)))
        if result.total_trades:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("معاملات", result.total_trades)
            m2.metric("وین‌ریت", f"{result.win_rate:.1f}%")
            m3.metric("سود (پیپ)", f"{result.total_pnl_pips:.1f}")
            m4.metric("پرافیت فاکتور", f"{result.profit_factor:.2f}")
        else:
            st.write("در این بازه معامله‌ای ثبت نشد.")

"""
اپلیکیشن وب Streamlit برای ربات معاملاتی EUR/USD
Streamlit Web App for EUR/USD Trading Bot

اجرا در Koyeb:
1. این ریپازیتوری را push کنید
2. در Koyeb یک سرویس جدید بسازید
3. GitHub را انتخاب کنید
4. Port 8501 را تنظیم کنید
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import sys
import os

# اضافه کردن مسیر src
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.strategy import HybridStrategy, SignalType, OrderType
from src.backtest import BacktestEngine
from src.data_fetcher import DataFetcher


# =====================================================
# تنظیمات صفحه
# =====================================================
st.set_page_config(
    page_title="ربات معاملاتی EUR/USD",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS سفارشی برای زبان فارسی
st.markdown("""
<style>
    .main { direction: rtl; text-align: right; }
    .stMetric { direction: rtl; }
    .css-18e3th9 { padding-top: 2rem; }
    h1, h2, h3 { color: #00b4d8; }
    .signal-buy { background: #06d6a0; padding: 10px 20px; border-radius: 10px; color: white; font-weight: bold; }
    .signal-sell { background: #ef476f; padding: 10px 20px; border-radius: 10px; color: white; font-weight: bold; }
    .signal-wait { background: #ffd166; padding: 10px 20px; border-radius: 10px; color: #333; font-weight: bold; }
</style>
""", unsafe_allow_html=True)


# =====================================================
# عنوان
# =====================================================
st.title("🔮 ربات اسکالپ EUR/USD - استراتژی هیبرید")
st.markdown("---")


# =====================================================
# نوار کناری - تنظیمات
# =====================================================
with st.sidebar:
    st.header("⚙️ تنظیمات استراتژی")
    
    # تنظیمات روند
    st.subheader("روند")
    ema_fast = st.slider("EMA سریع", 5, 50, 20)
    ema_slow = st.slider("EMA کند", 20, 200, 50)
    
    # تنظیمات RSI
    st.subheader("RSI")
    rsi_period = st.slider("دوره RSI", 5, 30, 14)
    rsi_oversold = st.slider("اشباع فروش", 10, 40, 30)
    rsi_overbought = st.slider("اشباع خرید", 60, 90, 70)
    
    # مدیریت ریسک
    st.subheader("مدیریت ریسک")
    rr1 = st.slider("R:R تارگت ۱", 0.5, 3.0, 1.0, 0.1)
    rr2 = st.slider("R:R تارگت ۲", 1.0, 5.0, 1.5, 0.1)
    rr3 = st.slider("R:R تارگت ۳", 1.5, 8.0, 2.5, 0.1)
    atr_mult = st.slider("ضریب ATR برای SL", 0.5, 3.0, 1.5, 0.1)
    min_conf = st.slider("حداقل اطمینان", 50, 90, 65)
    
    # تنظیمات داده
    st.subheader("داده‌ها")
    period = st.selectbox("بازه زمانی", ["5d", "1mo", "3mo", "6mo"], index=1)
    interval = st.selectbox("تایم‌فریم", ["1m", "5m", "15m", "30m", "1h"], index=1)
    
    # دکمه اجرا
    run_btn = st.button("🚀 تحلیل و تولید سیگنال", type="primary", use_container_width=True)


# =====================================================
# توابع کمکی
# =====================================================
@st.cache_data(ttl=300)  # کش ۵ دقیقه‌ای
def fetch_data(period, interval):
    """دریافت داده‌های تاریخی"""
    try:
        ticker = yf.Ticker("EURUSD=X")
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return None
        df = df.reset_index()
        df.columns = [c.lower().replace(' ', '_') for c in df.columns]
        if 'datetime' in df.columns:
            df['timestamps'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
        elif 'date' in df.columns:
            df['timestamps'] = pd.to_datetime(df['date']).dt.tz_localize(None)
        return df
    except Exception as e:
        st.error(f"خطا در دریافت داده: {e}")
        return None


def get_live_price():
    """دریافت قیمت زنده"""
    try:
        url = "https://scanner.tradingview.com/forex/scan"
        payload = {"symbols": {"tickers": ["FX_IDC:EURUSD"]}, "columns": ["close", "bid", "ask"]}
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.post(url, json=payload, headers=headers, timeout=3)
        if res.status_code == 200 and res.json().get("data"):
            values = res.json()["data"][0]["d"]
            return float(values[0]), float(values[1]) if values[1] else None, float(values[2]) if values[2] else None
    except:
        pass
    
    try:
        ticker = yf.Ticker("EURUSD=X")
        data = ticker.history(period="1d", interval="1m")
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            return price, round(price - 0.00006, 5), round(price + 0.00006, 5)
    except:
        pass
    
    return None, None, None


def create_strategy_config():
    """ایجاد تنظیمات استراتژی از مقادیر ورودی"""
    return {
        'trend_ema_fast': ema_fast,
        'trend_ema_slow': ema_slow,
        'rsi_period': rsi_period,
        'rsi_oversold': rsi_oversold,
        'rsi_overbought': rsi_overbought,
        'use_ema_cross': True,
        'use_rsi_filter': True,
        'use_kronos_prediction': False,
        'risk_reward_1': rr1,
        'risk_reward_2': rr2,
        'risk_reward_3': rr3,
        'atr_sl_multiplier': atr_mult,
        'max_sl_pips': 30,
        'min_sl_pips': 8,
        'min_confidence': min_conf,
        'high_confidence': 75,
        'trading_hours_start': 8,
        'trading_hours_end': 20,
        'filter_high_impact_news': False,
    }


# =====================================================
# محتوای اصلی
# =====================================================
if run_btn or True:  # همیشه اجرا برای نمایش اولیه
    
    # دریافت داده‌ها
    with st.spinner("📊 دریافت داده‌ها..."):
        df = fetch_data(period, interval)
    
    if df is None or df.empty:
        st.error("❌ خطا در دریافت داده‌ها")
        st.stop()
    
    # دریافت قیمت زنده
    live_price, bid, ask = get_live_price()
    
    if live_price:
        # به‌روزرسانی آخرین کندل
        df.loc[df.index[-1], 'close'] = live_price
    
    # ایجاد استراتژی
    config = create_strategy_config()
    strategy = HybridStrategy(config=config)
    
    # تحلیل روند
    trend = strategy.analyze_trend(df)
    rsi_data = strategy.analyze_rsi(df)
    
    # تولید سیگنال
    signal = strategy.generate_signal(df)
    
    # =====================================================
    # نمایش سیگنال اصلی
    # =====================================================
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if live_price:
            st.metric("قیمت زنده EUR/USD", f"{live_price:.5f}", 
                     delta=f"{((live_price - df['close'].iloc[-2]) / df['close'].iloc[-2] * 100):.3f}%")
        else:
            st.metric("قیمت", f"{df['close'].iloc[-1]:.5f}")
    
    with col2:
        if signal.signal_type == SignalType.BUY:
            st.success(f"🟢 {signal.reason}")
        elif signal.signal_type == SignalType.SELL:
            st.error(f"🔴 {signal.reason}")
        else:
            st.warning(f"⚪ {signal.reason}")
    
    with col3:
        st.metric("اطمینان", f"{signal.confidence:.0f}%")
    
    with col4:
        st.metric("روند", trend['trend_text'])
    
    st.markdown("---")
    
    # =====================================================
    # کارت‌های سطوح معاملاتی
    # =====================================================
    if signal.signal_type != SignalType.WAIT:
        st.subheader("🎯 سطوح معاملاتی")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.markdown(f"""
            <div style="background: #1a1a2e; padding: 15px; border-radius: 10px; border: 2px solid #00b4d8; text-align: center;">
                <span style="color: #00b4d8; font-size: 12px;">ورود</span>
                <div style="color: #FFD700; font-size: 20px; font-weight: bold;">{signal.entry_price:.5f}</div>
                <small style="color: #888;">{signal.order_type.value}</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div style="background: #1a1a2e; padding: 15px; border-radius: 10px; border: 2px solid #ef476f; text-align: center;">
                <span style="color: #ef476f; font-size: 12px;">حد ضرر</span>
                <div style="color: #ef476f; font-size: 20px; font-weight: bold;">{signal.stop_loss:.5f}</div>
                <small style="color: #888;">{signal.sl_pips} پیپ</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div style="background: #1a1a2e; padding: 15px; border-radius: 10px; border: 2px solid #06d6a0; text-align: center;">
                <span style="color: #06d6a0; font-size: 12px;">تارگت ۱</span>
                <div style="color: #06d6a0; font-size: 20px; font-weight: bold;">{signal.take_profit_1:.5f}</div>
                <small style="color: #888;">{signal.tp1_pips} پیپ</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div style="background: #1a1a2e; padding: 15px; border-radius: 10px; border: 2px solid #06d6a0; text-align: center;">
                <span style="color: #06d6a0; font-size: 12px;">تارگت ۲</span>
                <div style="color: #06d6a0; font-size: 20px; font-weight: bold;">{signal.take_profit_2:.5f}</div>
                <small style="color: #888;">{signal.tp2_pips} پیپ</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col5:
            st.markdown(f"""
            <div style="background: #1a1a2e; padding: 15px; border-radius: 10px; border: 2px solid #9b5de5; text-align: center;">
                <span style="color: #9b5de5; font-size: 12px;">تارگت ۳</span>
                <div style="color: #9b5de5; font-size: 20px; font-weight: bold;">{signal.take_profit_3:.5f}</div>
                <small style="color: #888;">{signal.tp3_pips} پیپ</small>
            </div>
            """, unsafe_allow_html=True)
        
        # راهنمای مدیریت ریسک
        st.info(f"💡 **مدیریت ریسک:** در رسیدن به TP1 ({signal.take_profit_1:.5f}) ۵۰٪ سود را ببندید. حد ضرر را به نقطه ورود منتقل کنید (ریسک‌فری).")
    
    st.markdown("---")
    
    # =====================================================
    # نمودار قیمت
    # =====================================================
    st.subheader("📈 نمودار قیمت")
    
    fig = go.Figure()
    
    # کندل‌ها
    df_chart = df.tail(100)
    fig.add_trace(go.Candlestick(
        x=df_chart['timestamps'],
        open=df_chart['open'],
        high=df_chart['high'],
        low=df_chart['low'],
        close=df_chart['close'],
        name="قیمت",
        increasing_line_color='#06d6a0',
        decreasing_line_color='#ef476f'
    ))
    
    # خطوط سیگنال
    if signal.signal_type != SignalType.WAIT:
        fig.add_hline(y=signal.entry_price, line_dash="dash", line_color="#FFD700", annotation_text="Entry")
        fig.add_hline(y=signal.stop_loss, line_dash="dot", line_color="#ef476f", annotation_text="SL")
        fig.add_hline(y=signal.take_profit_1, line_dash="dot", line_color="#06d6a0", annotation_text="TP1")
        fig.add_hline(y=signal.take_profit_2, line_dash="dot", line_color="#00b4d8", annotation_text="TP2")
        fig.add_hline(y=signal.take_profit_3, line_dash="dot", line_color="#9b5de5", annotation_text="TP3")
    
    fig.update_layout(
        template="plotly_dark",
        height=450,
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=30, b=10)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # =====================================================
    # بک‌تست
    # =====================================================
    st.markdown("---")
    st.subheader("🧪 بک‌تست")
    
    with st.spinner("در حال اجرای بک‌تست..."):
        engine = BacktestEngine(strategy=strategy, initial_balance=10000, spread_pips=1.2)
        result = engine.run(df, lookback=min(120, len(df) // 2))
    
    # نمایش نتایج
    if result.total_trades > 0:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("تعداد معاملات", result.total_trades)
        with col2:
            st.metric("Win Rate", f"{result.win_rate:.1f}%")
        with col3:
            st.metric("سود خالص (پیپ)", f"{result.total_pnl_pips:.1f}")
        with col4:
            st.metric("Profit Factor", f"{result.profit_factor:.2f}")
        with col5:
            st.metric("شارپ", f"{result.sharpe_ratio:.2f}")
        
        # نمودار بک‌تست
        fig2 = make_subplots(rows=2, cols=1, subplot_titles=("منحنی سرمایه", "سود/زیان هر معامله"))
        
        if result.equity_curve:
            fig2.add_trace(go.Scatter(y=result.equity_curve, mode='lines', name='سرمایه',
                                     line=dict(color='#00b4d8')), row=1, col=1)
        
        if result.trades:
            pnls = [t.pnl_pips for t in result.trades]
            colors = ['#06d6a0' if p > 0 else '#ef476f' for p in pnls]
            fig2.add_trace(go.Bar(y=pnls, marker_color=colors, name='P/L'), row=2, col=1)
        
        fig2.update_layout(template="plotly_dark", height=400, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
        
    else:
        st.warning("معامله‌ای در بازه زمانی انتخاب شده یافت نشد.")
    
    # =====================================================
    # جدول معاملات اخیر
    # =====================================================
    if result.trades:
        st.subheader("📋 آخرین معاملات")
        
        trades_data = []
        for t in result.trades[-10:]:
            trades_data.append({
                'زمان': str(t.entry_time)[:16],
                'جهت': t.direction.value,
                'ورود': f"{t.entry_price:.5f}",
                'خروج': f"{t.exit_price:.5f}" if t.exit_price else "-",
                'P/L (پیپ)': f"{t.pnl_pips:+.1f}",
                'نتیجه': "✅ سود" if t.result == 'win' else ("❌ زیان" if t.result == 'loss' else "➖ سرریز")
            })
        
        st.dataframe(pd.DataFrame(trades_data), use_container_width=True)
    
    # =====================================================
    # اطلاعات تکمیلی
    # =====================================================
    st.markdown("---")
    with st.expander("📊 اطلاعات تحلیل تکنیکال"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**روند:**")
            st.write(f"- EMA {ema_fast}: {trend['ema_fast']:.5f}")
            st.write(f"- EMA {ema_slow}: {trend['ema_slow']:.5f}")
            st.write(f"- وضعیت: {trend['trend_text']}")
        
        with col2:
            st.write("**RSI:**")
            st.write(f"- مقدار: {rsi_data['rsi']:.1f}")
            st.write(f"- سیگنال: {rsi_data['rsi_signal']}")
    
    # تاریخ آخرین به‌روزرسانی
    st.markdown("---")
    st.caption(f"🕐 آخرین به‌روزرسانی: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

else:
    st.info("👈 از نوار کناری تنظیمات را انتخاب کنید و دکمه **تحلیل و تولید سیگنال** را بزنید.")

"""
ماژول نمایش نتایج و نمودارها
Visualization Module - Charts and Dashboard
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    from IPython.display import display, HTML
    HAS_IPYTHON = True
except ImportError:
    HAS_IPYTHON = False


class TradingVisualizer:
    """نمایش نتایج معاملاتی"""
    
    @staticmethod
    def render_dashboard(data: Dict):
        """نمایش داشبورد HTML"""
        
        price = data['live_price']
        conf_color = '#06d6a0' if data['confidence'] >= 75 else ('#ffd166' if data['confidence'] >= 65 else '#ef476f')
        
        html = f"""
        <div style="background: #0a0e17; padding: 20px; border-radius: 16px; font-family: Tahoma, Arial; direction: rtl; border: 1px solid #2a3a5a; max-width: 900px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                <div>
                    <h2 style="color: #00b4d8; margin: 0;">🔮 مشاور هوشمند فارکس (EUR/USD)</h2>
                    <span style="color: #888; font-size: 12px;">استراتژی هیبرید • تایم‌فریم ۵ دقیقه‌ای</span>
                </div>
                <div style="background: #121a2a; padding: 8px 18px; border-radius: 12px; border: 1px solid #2a3a5a;">
                    <span style="color: #aaa; font-size: 12px;">قیمت زنده: </span>
                    <span style="color: #FFD700; font-size: 20px; font-weight: bold;">${price:.5f}</span>
                </div>
                <div style="background: {data['signal_color']}; padding: 8px 20px; border-radius: 20px; color: white; font-weight: bold;">
                    {data['signal']}
                </div>
            </div>

            <!-- کارت‌های اطلاعاتی -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin: 20px 0;">
                <div style="background: #121a2a; padding: 12px; border-radius: 10px; border: 1px solid #00b4d8;">
                    <span style="color: #00b4d8; font-size: 11px; font-weight:bold;">🎯 ورود ({data['order_type']})</span>
                    <div style="color: #FFD700; font-size: 18px; font-weight: bold; margin-top: 5px;">{data['entry_price']:.5f}</div>
                </div>
                <div style="background: #121a2a; padding: 12px; border-radius: 10px; border: 1px solid #ef476f;">
                    <span style="color: #ef476f; font-size: 11px; font-weight:bold;">🛑 حد ضرر (SL)</span>
                    <div style="color: #ef476f; font-size: 18px; font-weight: bold; margin-top: 5px;">{data['sl_price']:.5f}</div>
                    <small style="color:#888;">{data['sl_pips']} پیپ</small>
                </div>
                <div style="background: #121a2a; padding: 12px; border-radius: 10px; border: 1px solid #06d6a0;">
                    <span style="color: #06d6a0; font-size: 11px; font-weight:bold;">🟢 تارگت ۱ (TP1)</span>
                    <div style="color: #06d6a0; font-size: 18px; font-weight: bold; margin-top: 5px;">{data['tp1_price']:.5f}</div>
                    <small style="color:#888;">{data['tp1_pips']} پیپ</small>
                </div>
                <div style="background: #121a2a; padding: 12px; border-radius: 10px; border: 1px solid #06d6a0;">
                    <span style="color: #06d6a0; font-size: 11px; font-weight:bold;">🎯 تارگت ۲ (TP2)</span>
                    <div style="color: #06d6a0; font-size: 18px; font-weight: bold; margin-top: 5px;">{data['tp2_price']:.5f}</div>
                    <small style="color:#888;">{data['tp2_pips']} پیپ</small>
                </div>
                <div style="background: #121a2a; padding: 12px; border-radius: 10px; border: 1px solid #06d6a0;">
                    <span style="color: #06d6a0; font-size: 11px; font-weight:bold;">🚀 تارگت ۳ (TP3)</span>
                    <div style="color: #06d6a0; font-size: 18px; font-weight: bold; margin-top: 5px;">{data['tp3_price']:.5f}</div>
                    <small style="color:#888;">{data['tp3_pips']} پیپ</small>
                </div>
                <div style="background: #121a2a; padding: 12px; border-radius: 10px; border: 1px solid {conf_color};">
                    <span style="color: #aaa; font-size: 11px;">📊 اطمینان</span>
                    <div style="color: {conf_color}; font-size: 18px; font-weight: bold; margin-top: 5px;">{data['confidence']}%</div>
                    <small style="color:#888;">روند ۱H: {data['trend_1h_text']}</small>
                </div>
            </div>

            <div style="background: #121a2a; padding: 12px; border-radius: 10px; border-right: 4px solid #FFD700; margin-bottom: 15px; font-size: 12px; color: #ddd;">
                💡 <b>مدیریت ریسک:</b> در رسیدن به <b>TP1 ({data['tp1_price']:.5f})</b> ۵۰٪ سود را ببندید. در <b>TP2 ({data['tp2_price']:.5f})</b> حد ضرر را به نقطه ورود منتقل کنید (ریسک‌فری).
            </div>

            <div style="background: #121a2a; padding: 15px; border-radius: 10px; border: 1px solid #2a3a5a;">
                <h4 style="color: #FFD700; margin-top:0;">📝 دلیل سیگنال:</h4>
                <p style="color: #ddd; font-size: 13px; line-height: 1.8;">{data.get('reason', 'تحلیل خودکار')}</p>
            </div>
        </div>
        """
        
        if HAS_IPYTHON:
            display(HTML(html))
        else:
            print(html)
    
    @staticmethod
    def plot_candlestick_with_signals(df: pd.DataFrame, signals: List[Dict] = None,
                                     title: str = "EUR/USD"):
        """رسم نمودار کندل‌ستیک با سیگنال‌ها"""
        
        if not HAS_PLOTLY:
            print("⚠️ plotly نصب نشده. نمایش متنی:")
            print(df.tail(10).to_string())
            return
        
        fig = go.Figure()
        
        # کندل‌ها
        fig.add_trace(go.Candlestick(
            x=df['timestamps'] if 'timestamps' in df.columns else df.index,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name="قیمت",
            increasing_line_color='#06d6a0',
            decreasing_line_color='#ef476f'
        ))
        
        # سیگنال‌ها
        if signals:
            for sig in signals:
                if sig['type'] == 'BUY':
                    fig.add_scatter(
                        x=[sig['time']], y=[sig['price']],
                        mode='markers', marker=dict(symbol='triangle-up', size=15, color='#06d6a0'),
                        name='BUY'
                    )
                elif sig['type'] == 'SELL':
                    fig.add_scatter(
                        x=[sig['time']], y=[sig['price']],
                        mode='markers', marker=dict(symbol='triangle-down', size=15, color='#ef476f'),
                        name='SELL'
                    )
        
        fig.update_layout(
            template="plotly_dark",
            title=title,
            xaxis_rangeslider_visible=False,
            height=500,
            margin=dict(l=10, r=10, t=40, b=10)
        )
        
        fig.show()
    
    @staticmethod
    def plot_backtest_results(result, title: str = "نتایج بک‌تست"):
        """رسم نمودارهای بک‌تست"""
        
        if not HAS_PLOTLY:
            print(result.summary())
            return
        
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=('منحنی سرمایه', 'توزیع سود/زیان', 'معاملات ماهانه'),
            vertical_spacing=0.08
        )
        
        # ۱. منحنی سرمایه
        if result.equity_curve:
            fig.add_trace(
                go.Scatter(y=result.equity_curve, mode='lines', name='سرمایه',
                          line=dict(color='#00b4d8', width=2)),
                row=1, col=1
            )
        
        # ۲. توزیع سود/زیان
        if result.trades:
            pnls = [t.pnl_pips for t in result.trades]
            colors = ['#06d6a0' if p > 0 else '#ef476f' for p in pnls]
            fig.add_trace(
                go.Bar(y=pnls, marker_color=colors, name='P/L (pips)'),
                row=2, col=1
            )
        
        # ۳. بازده ماهانه
        if result.monthly_returns:
            months = list(result.monthly_returns.keys())
            returns = list(result.monthly_returns.values())
            colors = ['#06d6a0' if r > 0 else '#ef476f' for r in returns]
            fig.add_trace(
                go.Bar(x=months, y=returns, marker_color=colors, name='بازده ماهانه'),
                row=3, col=1
            )
        
        fig.update_layout(
            template="plotly_dark",
            title=title,
            height=800,
            showlegend=False,
            margin=dict(l=10, r=10, t=40, b=10)
        )
        
        fig.show()
    
    @staticmethod
    def plot_trade_analysis(trades: List, df: pd.DataFrame = None):
        """تحلیل تفصیلی معاملات"""
        
        if not trades:
            print("معامله‌ای برای نمایش وجود ندارد.")
            return
        
        if not HAS_PLOTLY:
            print(f"تعداد معاملات: {len(trades)}")
            return
        
        # محاسبه آمار
        pnls = [t.pnl_pips for t in trades]
        cumulative = np.cumsum(pnls)
        
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('سود تجمعی', 'توزیع P/L', 'مدت معامله', 'سود/زیان بر اساس جهت')
        )
        
        # سود تجمعی
        fig.add_trace(go.Scatter(y=cumulative, mode='lines', name='سود تجمعی',
                                line=dict(color='#00b4d8')), row=1, col=1)
        
        # توزیع P/L
        fig.add_trace(go.Histogram(x=pnls, nbinsx=30, name='توزیع',
                                  marker_color='#ffd166'), row=1, col=2)
        
        # سود بر اساس جهت
        buy_pnls = [t.pnl_pips for t in trades if t.direction.value == 'BUY']
        sell_pnls = [t.pnl_pips for t in trades if t.direction.value == 'SELL']
        
        fig.add_trace(go.Box(y=buy_pnls, name='BUY', marker_color='#06d6a0'), row=2, col=2)
        fig.add_trace(go.Box(y=sell_pnls, name='SELL', marker_color='#ef476f'), row=2, col=2)
        
        fig.update_layout(template="plotly_dark", height=600, showlegend=True)
        fig.show()

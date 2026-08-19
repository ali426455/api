"""
اجرای سریع بک‌تست از خط فرمان
Quick backtest runner from command line

استفاده:
    python run_backtest.py
    python run_backtest.py --period 3mo --interval 5m
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.strategy import HybridStrategy
from src.backtest import BacktestEngine
from src.data_fetcher import DataFetcher
from src.visualizer import TradingVisualizer


def main():
    parser = argparse.ArgumentParser(description='EUR/USD Hybrid Strategy Backtester')
    parser.add_argument('--period', default='1mo', help='Data period (1d, 5d, 1mo, 3mo, 6mo, 1y)')
    parser.add_argument('--interval', default='5m', help='Timeframe (1m, 5m, 15m, 30m, 1h)')
    parser.add_argument('--balance', type=float, default=10000, help='Initial balance')
    parser.add_argument('--spread', type=float, default=1.2, help='Spread in pips')
    parser.add_argument('--confidence', type=float, default=65, help='Minimum confidence')
    parser.add_argument('--no-charts', action='store_true', help='Disable charts')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("🤖 EUR/USD Hybrid Strategy Backtester")
    print("=" * 60)
    
    # تنظیمات
    config = HybridStrategy.default_config()
    config['min_confidence'] = args.confidence
    
    # دریافت داده‌ها
    print(f"\n📊 دریافت داده‌ها: {args.period} @ {args.interval}")
    fetcher = DataFetcher()
    df = fetcher.get_historical_data(period=args.period, interval=args.interval)
    
    if df.empty:
        print("❌ خطا در دریافت داده‌ها")
        return
    
    # ایجاد استراتژی و موتور بک‌تست
    strategy = HybridStrategy(config=config)
    engine = BacktestEngine(
        strategy=strategy,
        initial_balance=args.balance,
        spread_pips=args.spread
    )
    
    # اجرای بک‌تست
    print("\n⏳ در حال اجرای بک‌تست...")
    result = engine.run(df, lookback=120)
    
    # نمایش نتایج
    print(result.summary())
    
    # نمودارها
    if not args.no_charts:
        try:
            viz = TradingVisualizer()
            viz.plot_backtest_results(result)
        except Exception as e:
            print(f"⚠️ خطا در رسم نمودار: {e}")
    
    # سیگنال زنده
    print("\n📈 سیگنال زنده:")
    live_price, bid, ask = fetcher.get_live_price()
    if live_price:
        print(f"   قیمت: {live_price:.5f}")
        signal = strategy.generate_signal(df)
        print(f"   سیگنال: {signal.signal_type.value}")
        print(f"   اطمینان: {signal.confidence:.0f}%")
        if signal.signal_type.value != 'WAIT':
            print(f"   ورود: {signal.entry_price:.5f}")
            print(f"   SL: {signal.stop_loss:.5f} ({signal.sl_pips} pips)")
            print(f"   TP1: {signal.take_profit_1:.5f} ({signal.tp1_pips} pips)")
            print(f"   TP2: {signal.take_profit_2:.5f} ({signal.tp2_pips} pips)")
            print(f"   TP3: {signal.take_profit_3:.5f} ({signal.tp3_pips} pips)")


if __name__ == '__main__':
    main()

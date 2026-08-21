"""
ماژول دریافت داده‌ها - قیمت زنده و تاریخی
Data Fetcher Module - Live and historical price data
"""

import pandas as pd
import numpy as np
import yfinance as yf
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple
import warnings
warnings.filterwarnings('ignore')


class DataFetcher:
    """دریافت داده‌های قیمتی"""
    
    def __init__(self, finnhub_api_key: str = None):
        self.finnhub_api_key = finnhub_api_key or "d9n0o09r01qlajg2qtr0d9n0o09r01qlajg2qtrg"
    
    def get_historical_data(self, symbol: str = "EURUSD=X", 
                           period: str = "1mo",
                           interval: str = "5m") -> pd.DataFrame:
        """
        دریافت داده‌های تاریخی از Yahoo Finance
        
        Parameters:
        -----------
        symbol : نماد (EURUSD=X برای EUR/USD)
        period : بازه زمانی (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)
        interval : تایم‌فریم (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)
        """
        try:
            if interval == "1m" and period not in ("1d", "5d"):
                period = "5d"
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                print(f"⚠️ داده‌ای برای {symbol} یافت نشد. استفاده از داده‌های نمونه.")
                return self._generate_sample_data()
            
            # استانداردسازی نام ستون‌ها
            df = df.reset_index()
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            
            # تبدیل datetime
            if 'datetime' in df.columns:
                df['timestamps'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
            elif 'date' in df.columns:
                df['timestamps'] = pd.to_datetime(df['date']).dt.tz_localize(None)
            
            # حذف ستون‌های اضافی
            keep_cols = ['open', 'high', 'low', 'close', 'volume', 'timestamps']
            df = df[[c for c in keep_cols if c in df.columns]]
            
            print(f"✅ {len(df)} کندل {interval} برای {symbol} دریافت شد.")
            return df
            
        except Exception as e:
            print(f"⚠️ خطا در دریافت داده: {e}")
            return self._generate_sample_data()
    
    def get_live_price(self) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        دریافت قیمت زنده
        Returns: (price, bid, ask)
        """
        # روش ۱: TradingView Scanner
        try:
            url = "https://scanner.tradingview.com/forex/scan"
            payload = {
                "symbols": {"tickers": ["FX_IDC:EURUSD"]},
                "columns": ["close", "bid", "ask"]
            }
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Origin": "https://www.tradingview.com",
                "Referer": "https://www.tradingview.com/"
            }
            res = requests.post(url, json=payload, headers=headers, timeout=3)
            if res.status_code == 200 and res.json().get("data"):
                values = res.json()["data"][0]["d"]
                price = float(values[0])
                bid = float(values[1]) if values[1] else round(price - 0.00007, 5)
                ask = float(values[2]) if values[2] else round(price + 0.00007, 5)
                return price, bid, ask
        except Exception:
            pass
        
        # روش ۲: Finnhub
        try:
            url = f"https://finnhub.io/api/v1/quote?symbol=OANDA:EUR_USD&token={self.finnhub_api_key}"
            res = requests.get(url, timeout=3).json()
            if 'c' in res and res['c'] > 0:
                price = float(res['c'])
                bid = round(price - 0.00006, 5)
                ask = round(price + 0.00006, 5)
                return price, bid, ask
        except Exception:
            pass
        
        # روش ۳: Yahoo Finance
        try:
            ticker = yf.Ticker("EURUSD=X")
            data = ticker.history(period="1d", interval="1m")
            if not data.empty:
                price = float(data['Close'].iloc[-1])
                bid = round(price - 0.00006, 5)
                ask = round(price + 0.00006, 5)
                return price, bid, ask
        except Exception:
            pass
        
        return None, None, None
    
    def check_high_impact_news(self) -> Tuple[bool, str]:
        """بررسی اخبار با تاثیر بالا"""
        try:
            url = f"https://finnhub.io/api/v1/economic_calendar?token={self.finnhub_api_key}"
            res = requests.get(url, timeout=4)
            if res.status_code == 200:
                events = res.json()
                for event in events:
                    impact = str(event.get('impact', '')).lower()
                    country = str(event.get('country', '')).upper()
                    if impact in ['high', '3', 'high impact'] and country in ['US', 'USA', 'EUR', 'EU']:
                        return True, event.get('event', 'خبر مهم')
        except Exception:
            pass
        return False, ""
    
    def _generate_sample_data(self, n: int = 500) -> pd.DataFrame:
        """تولید داده‌های نمونه برای تست"""
        np.random.seed(42)
        dates = pd.date_range(end=datetime.now(), periods=n, freq='5min')
        
        # شبیه‌سازی حرکت قیمت
        returns = np.random.normal(0, 0.0001, n)
        price = 1.0830
        prices = [price]
        for r in returns:
            price = price * (1 + r)
            prices.append(price)
        prices = prices[1:]
        
        df = pd.DataFrame({
            'timestamps': dates,
            'open': prices,
            'high': [p + abs(np.random.normal(0, 0.0002)) for p in prices],
            'low': [p - abs(np.random.normal(0, 0.0002)) for p in prices],
            'close': [p + np.random.normal(0, 0.0001) for p in prices],
            'volume': np.random.randint(100, 10000, n)
        })
        
        # اطمینان از high >= low
        df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1) + 0.0001
        df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1) - 0.0001
        
        print(f"📊 {n} کندل نمونه تولید شد.")
        return df

"""
استراتژی هیبرید - ترکیب قوانین کاربر و پیش‌بینی Kronos AI
Hybrid Strategy - Combines custom user rules with Kronos AI predictions
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    WAIT = "WAIT"


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    NO_TRADE = "NO TRADE"


@dataclass
class Signal:
    signal_type: SignalType
    order_type: OrderType
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    confidence: float
    reason: str
    sl_pips: float = 0
    tp1_pips: float = 0
    tp2_pips: float = 0
    tp3_pips: float = 0


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    direction: SignalType
    entry_price: float
    exit_price: Optional[float]
    stop_loss: float
    take_profit: float
    result: Optional[str] = None  # 'win', 'loss', 'breakeven'
    pnl_pips: float = 0


class TechnicalIndicators:
    """محاسبه اندیکاتورهای تکنیکال"""
    
    @staticmethod
    def ema(series: pd.Series, span: int) -> pd.Series:
        return series.ewm(span=span, adjust=False).mean()
    
    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        return series.rolling(window=period).mean()
    
    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    @staticmethod
    def bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower
    
    @staticmethod
    def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    @staticmethod
    def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k_period: int = 14, d_period: int = 3):
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        d = k.rolling(window=d_period).mean()
        return k, d


class HybridStrategy:
    """
    استراتژی هیبرید
    ترکیب قوانین سفارشی کاربر با پیش‌بینی‌های Kronos AI
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or self.default_config()
        self.indicators = TechnicalIndicators()
        self.pip_unit = 0.0001  # برای EUR/USD
    
    @staticmethod
    def default_config() -> Dict:
        return {
            # تنظیمات روند
            'trend_ema_fast': 20,
            'trend_ema_slow': 50,
            'trend_timeframe': '1h',
            
            # تنظیمات RSI
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            
            # تنظیمات ورود
            'use_ema_cross': True,
            'use_rsi_filter': True,
            'use_kronos_prediction': True,
            
            # تنظیمات مدیریت ریسک
            'risk_reward_1': 1.0,   # TP1:SL ratio
            'risk_reward_2': 1.5,   # TP2:SL ratio
            'risk_reward_3': 2.5,   # TP3:SL ratio
            'atr_sl_multiplier': 1.5,
            'max_sl_pips': 30,
            'min_sl_pips': 8,
            
            # تنظیمات اطمینان
            'min_confidence': 65,
            'high_confidence': 75,
            
            # فیلتر ساعات معاملاتی
            'trading_hours_start': 8,   # ساعت شروع (UTC)
            'trading_hours_end': 20,    # ساعت پایان (UTC)
            
            # فیلتر اخبار
            'filter_high_impact_news': True,
        }
    
    def analyze_trend(self, df: pd.DataFrame) -> Dict:
        """تحلیل روند بر اساس EMA"""
        ema_fast = self.indicators.ema(df['close'], self.config['trend_ema_fast'])
        ema_slow = self.indicators.ema(df['close'], self.config['trend_ema_slow'])
        
        current_close = df['close'].iloc[-1]
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        
        if current_close > current_ema_fast and current_ema_fast > current_ema_slow:
            trend = "BULLISH"
            trend_text = "صعودی 🟢"
        elif current_close < current_ema_fast and current_ema_fast < current_ema_slow:
            trend = "BEARISH"
            trend_text = "نزولی 🔴"
        else:
            trend = "NEUTRAL"
            trend_text = "خنثی ⚪"
        
        return {
            'trend': trend,
            'trend_text': trend_text,
            'ema_fast': current_ema_fast,
            'ema_slow': current_ema_slow,
            'ema_fast_series': ema_fast,
            'ema_slow_series': ema_slow,
        }
    
    def analyze_rsi(self, df: pd.DataFrame) -> Dict:
        """تحلیل RSI"""
        rsi = self.indicators.rsi(df['close'], self.config['rsi_period'])
        current_rsi = rsi.iloc[-1]
        
        if current_rsi < self.config['rsi_oversold']:
            rsi_signal = "OVERSOLD"
        elif current_rsi > self.config['rsi_overbought']:
            rsi_signal = "OVERBOUGHT"
        else:
            rsi_signal = "NEUTRAL"
        
        return {
            'rsi': current_rsi,
            'rsi_signal': rsi_signal,
            'rsi_series': rsi,
        }
    
    def calculate_confidence(self, signal_type: SignalType, trend: Dict, rsi: Dict, 
                           kronos_direction: str = None) -> float:
        """محاسبه درجه اطمینان"""
        confidence = 50.0
        
        # هماهنگی با روند
        if signal_type.value == trend['trend']:
            confidence += 20
        elif trend['trend'] != "NEUTRAL":
            confidence -= 15
        
        # فیلتر RSI
        if signal_type == SignalType.BUY and rsi['rsi_signal'] == "OVERSOLD":
            confidence += 10
        elif signal_type == SignalType.SELL and rsi['rsi_signal'] == "OVERBOUGHT":
            confidence += 10
        elif signal_type == SignalType.BUY and rsi['rsi_signal'] == "OVERBOUGHT":
            confidence -= 10
        elif signal_type == SignalType.SELL and rsi['rsi_signal'] == "OVERSOLD":
            confidence -= 10
        
        # تأیید Kronos
        if kronos_direction:
            if signal_type.value == kronos_direction:
                confidence += 15
            else:
                confidence -= 20
        
        return max(30, min(95, confidence))
    
    def generate_signal(self, df: pd.DataFrame, kronos_prediction: Dict = None,
                       has_high_news: bool = False) -> Signal:
        """تولید سیگنال معاملاتی"""
        
        curr_close = df['close'].iloc[-1]
        atr = self.indicators.atr(df['high'], df['low'], df['close']).iloc[-1] or 0.0008
        
        # تحلیل روند و RSI
        trend = self.analyze_trend(df)
        rsi = self.analyze_rsi(df)
        
        # تعیین جهت بر اساس Kronos
        kronos_direction = None
        if kronos_prediction and self.config['use_kronos_prediction']:
            if kronos_prediction.get('ret_pct', 0) >= 0.08:
                kronos_direction = "BUY"
            elif kronos_prediction.get('ret_pct', 0) <= -0.08:
                kronos_direction = "SELL"
        
        # فیلتر اخبار
        if has_high_news and self.config['filter_high_impact_news']:
            return Signal(
                signal_type=SignalType.WAIT,
                order_type=OrderType.NO_TRADE,
                entry_price=curr_close,
                stop_loss=curr_close,
                take_profit_1=curr_close,
                take_profit_2=curr_close,
                take_profit_3=curr_close,
                confidence=0,
                reason=f"WAIT - خبر مهم نزدیک است"
            )
        
        # تعیین سیگنال بر اساس قوانین
        raw_signal = SignalType.WAIT
        
        if kronos_direction:
            raw_signal = SignalType.BUY if kronos_direction == "BUY" else SignalType.SELL
        elif self.config['use_ema_cross']:
            if trend['trend'] == "BULLISH":
                raw_signal = SignalType.BUY
            elif trend['trend'] == "BEARISH":
                raw_signal = SignalType.SELL
        
        # محاسبه اطمینان
        confidence = self.calculate_confidence(raw_signal, trend, rsi, kronos_direction)
        
        # بررسی حداقل اطمینان
        if confidence < self.config['min_confidence']:
            return Signal(
                signal_type=SignalType.WAIT,
                order_type=OrderType.NO_TRADE,
                entry_price=curr_close,
                stop_loss=curr_close,
                take_profit_1=curr_close,
                take_profit_2=curr_close,
                take_profit_3=curr_close,
                confidence=confidence,
                reason=f"WAIT - اطمینان پایین ({confidence:.0f}%)"
            )
        
        # محاسبه نقاط ورود و خروج
        if raw_signal == SignalType.BUY:
            return self._calculate_buy_levels(curr_close, atr, trend, confidence, kronos_prediction)
        elif raw_signal == SignalType.SELL:
            return self._calculate_sell_levels(curr_close, atr, trend, confidence, kronos_prediction)
        else:
            return Signal(
                signal_type=SignalType.WAIT,
                order_type=OrderType.NO_TRADE,
                entry_price=curr_close,
                stop_loss=curr_close,
                take_profit_1=curr_close,
                take_profit_2=curr_close,
                take_profit_3=curr_close,
                confidence=confidence,
                reason="WAIT - روند قوی وجود ندارد"
            )
    
    def _calculate_buy_levels(self, curr_close: float, atr: float, trend: Dict,
                             confidence: float, kronos_pred: Dict = None) -> Signal:
        """محاسبه سطوح برای سیگنال خرید"""
        
        ema_fast = trend['ema_fast']
        sl_distance = min(max(atr * self.config['atr_sl_multiplier'], 
                             self.config['min_sl_pips'] * self.pip_unit),
                        self.config['max_sl_pips'] * self.pip_unit)
        
        # نقطه ورود (با اصلاح به EMA)
        if curr_close > ema_fast + self.pip_unit:
            entry_price = round(ema_fast, 5)
            order_type = OrderType.LIMIT
            order_desc = "BUY LIMIT (خرید در اصلاح)"
        else:
            entry_price = round(curr_close, 5)
            order_type = OrderType.MARKET
            order_desc = "BUY MARKET"
        
        # حد ضرر
        sl_price = round(entry_price - sl_distance, 5)
        
        # تارگت‌ها
        tp1 = round(entry_price + (sl_distance * self.config['risk_reward_1']), 5)
        tp2 = round(entry_price + (sl_distance * self.config['risk_reward_2']), 5)
        tp3 = round(entry_price + (sl_distance * self.config['risk_reward_3']), 5)
        
        return Signal(
            signal_type=SignalType.BUY,
            order_type=order_type,
            entry_price=entry_price,
            stop_loss=sl_price,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            confidence=confidence,
            reason=order_desc,
            sl_pips=round((entry_price - sl_price) / self.pip_unit, 1),
            tp1_pips=round((tp1 - entry_price) / self.pip_unit, 1),
            tp2_pips=round((tp2 - entry_price) / self.pip_unit, 1),
            tp3_pips=round((tp3 - entry_price) / self.pip_unit, 1),
        )
    
    def _calculate_sell_levels(self, curr_close: float, atr: float, trend: Dict,
                              confidence: float, kronos_pred: Dict = None) -> Signal:
        """محاسبه سطوح برای سیگنال فروش"""
        
        ema_fast = trend['ema_fast']
        sl_distance = min(max(atr * self.config['atr_sl_multiplier'],
                             self.config['min_sl_pips'] * self.pip_unit),
                        self.config['max_sl_pips'] * self.pip_unit)
        
        # نقطه ورود
        if curr_close < ema_fast - self.pip_unit:
            entry_price = round(ema_fast, 5)
            order_type = OrderType.LIMIT
            order_desc = "SELL LIMIT (فروش در اصلاح)"
        else:
            entry_price = round(curr_close, 5)
            order_type = OrderType.MARKET
            order_desc = "SELL MARKET"
        
        # حد ضرر
        sl_price = round(entry_price + sl_distance, 5)
        
        # تارگت‌ها
        tp1 = round(entry_price - (sl_distance * self.config['risk_reward_1']), 5)
        tp2 = round(entry_price - (sl_distance * self.config['risk_reward_2']), 5)
        tp3 = round(entry_price - (sl_distance * self.config['risk_reward_3']), 5)
        
        return Signal(
            signal_type=SignalType.SELL,
            order_type=order_type,
            entry_price=entry_price,
            stop_loss=sl_price,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            confidence=confidence,
            reason=order_desc,
            sl_pips=round((sl_price - entry_price) / self.pip_unit, 1),
            tp1_pips=round((entry_price - tp1) / self.pip_unit, 1),
            tp2_pips=round((entry_price - tp2) / self.pip_unit, 1),
            tp3_pips=round((entry_price - tp3) / self.pip_unit, 1),
        )

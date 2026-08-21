"""
موتور بک‌تست - شبیه‌سازی معاملات روی داده‌های تاریخی
Backtesting Engine - Simulates trades on historical data
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from src.strategy import HybridStrategy, Signal, SignalType, OrderType, Trade


@dataclass
class BacktestResult:
    """نتایج بک‌تست"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    total_pnl_pips: float = 0.0
    avg_win_pips: float = 0.0
    avg_loss_pips: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pips: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    expectancy: float = 0.0
    avg_holding_bars: float = 0.0
    best_trade_pips: float = 0.0
    worst_trade_pips: float = 0.0
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    equity_curve: List[float] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    monthly_returns: Dict[str, float] = field(default_factory=dict)
    
    def summary(self) -> str:
        return f"""
╔══════════════════════════════════════════════════════════════╗
║                    نتایج بک‌تست | Backtest Results           ║
╠══════════════════════════════════════════════════════════════╣
║  تعداد کل معاملات:          {self.total_trades:>8}                        ║
║  معاملات سودده:            {self.winning_trades:>8}  ({self.win_rate:.1f}%)              ║
║  معاملات زیانده:           {self.losing_trades:>8}                        ║
║  معاملات سرریز:            {self.breakeven_trades:>8}                        ║
╠══════════════════════════════════════════════════════════════╣
║  سود خالص (پیپ):            {self.total_pnl_pips:>8.1f}                        ║
║  میانگین سود:               {self.avg_win_pips:>8.1f} پیپ                     ║
║  میانگین زیان:              {self.avg_loss_pips:>8.1f} پیپ                     ║
║  ضریب سود (Profit Factor):  {self.profit_factor:>8.2f}                        ║
║  بازده انتظاری:             {self.expectancy:>8.2f} پیپ/معامله               ║
╠══════════════════════════════════════════════════════════════╣
║  حداکثر افت سرمایه (پیپ):   {self.max_drawdown_pips:>8.1f}                        ║
║  نسبت شارپ:                 {self.sharpe_ratio:>8.2f}                        ║
║  بهترین معامله:             {self.best_trade_pips:>8.1f} پیپ                     ║
║  بدترین معامله:            {self.worst_trade_pips:>8.1f} پیپ                     ║
║  بیشترین برد متوالی:        {self.consecutive_wins:>8}                        ║
║  بیشترین باخت متوالی:       {self.consecutive_losses:>8}                        ║
╚══════════════════════════════════════════════════════════════╝
"""


class BacktestEngine:
    """
    موتور بک‌تست برای شبیه‌سازی استراتژی روی داده‌های تاریخی
    """
    
    def __init__(self, strategy: HybridStrategy = None, initial_balance: float = 10000,
                 risk_per_trade: float = 0.02, spread_pips: float = 1.2):
        self.strategy = strategy or HybridStrategy()
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.spread_pips = spread_pips
        self.pip_unit = 0.0001
        self.spread_cost = spread_pips * self.pip_unit
    
    def run(self, df: pd.DataFrame, lookback: int = 120, 
            signal_every_n_bars: int = 1) -> BacktestResult:
        """
        اجرای بک‌تست
        
        Parameters:
        -----------
        df : DataFrame with columns: open, high, low, close, timestamps
        lookback : تعداد کندل‌های گذشته برای تحلیل
        signal_every_n_bars : تولید سیگنال هر چند کندل
        """
        result = BacktestResult()
        trades = []
        equity = [self.initial_balance]
        current_balance = self.initial_balance
        
        # اطمینان از وجود ستون timestamps
        if 'timestamps' not in df.columns:
            df['timestamps'] = pd.to_datetime(df.index)
        
        # شبیه‌سازی کندل به کندل
        for i in range(lookback, len(df) - 1, signal_every_n_bars):
            # داده‌های تاریخی تا این نقطه
            historical = df.iloc[:i].copy()
            
            # تولید سیگنال
            signal = self.strategy.generate_signal(historical)
            
            if signal.signal_type == SignalType.WAIT:
                continue
            
            # شبیه‌سازی معامله
            trade = self._simulate_trade(signal, df, i)
            
            if trade:
                trades.append(trade)
                current_balance += trade.pnl_pips * 10  # هر پیپ = 10 دلار (معادل لات استاندارد)
                equity.append(current_balance)
        
        # محاسبه آمار
        result.trades = trades
        result.equity_curve = equity
        self._calculate_metrics(result)
        
        return result
    
    def _simulate_trade(self, signal: Signal, df: pd.DataFrame, 
                       entry_bar: int) -> Optional[Trade]:
        """شبیه‌سازی یک معامله"""
        
        entry_price = signal.entry_price
        sl = signal.stop_loss
        tp1 = signal.take_profit_1
        tp2 = signal.take_profit_2
        tp3 = signal.take_profit_3
        
        # هزینه اسپرد
        if signal.signal_type == SignalType.BUY:
            effective_entry = entry_price + self.spread_cost
        else:
            effective_entry = entry_price - self.spread_cost
        
        # بررسی کندل‌های بعدی
        max_lookahead = 100  # حداکثر 100 کندل برای رسیدن به TP یا SL
        
        for j in range(1, min(max_lookahead, len(df) - entry_bar)):
            bar = df.iloc[entry_bar + j]
            
            if signal.signal_type == SignalType.BUY:
                # رسیدن به حد ضرر
                if bar['low'] <= sl:
                    pnl = (sl - effective_entry) / self.pip_unit
                    return Trade(
                        entry_time=df.iloc[entry_bar].get('timestamps', entry_bar),
                        exit_time=bar.get('timestamps', entry_bar + j),
                        direction=SignalType.BUY,
                        entry_price=effective_entry,
                        exit_price=sl,
                        stop_loss=sl,
                        take_profit=tp1,
                        result='loss',
                        pnl_pips=round(pnl, 1)
                    )
                
                # رسیدن به تارگت 3
                if bar['high'] >= tp3:
                    pnl = (tp3 - effective_entry) / self.pip_unit
                    return Trade(
                        entry_time=df.iloc[entry_bar].get('timestamps', entry_bar),
                        exit_time=bar.get('timestamps', entry_bar + j),
                        direction=SignalType.BUY,
                        entry_price=effective_entry,
                        exit_price=tp3,
                        stop_loss=sl,
                        take_profit=tp3,
                        result='win',
                        pnl_pips=round(pnl, 1)
                    )
                
                # رسیدن به تارگت 2
                if bar['high'] >= tp2:
                    # حرکت SL به نقطه ورود (Breakeakeven)
                    sl = effective_entry
                
                # رسیدن به تارگت 1 - بستن 50% (در اینجا کامل می‌بندیم برای سادگی)
                if bar['high'] >= tp1:
                    pnl = (tp1 - effective_entry) / self.pip_unit
                    return Trade(
                        entry_time=df.iloc[entry_bar].get('timestamps', entry_bar),
                        exit_time=bar.get('timestamps', entry_bar + j),
                        direction=SignalType.BUY,
                        entry_price=effective_entry,
                        exit_price=tp1,
                        stop_loss=sl,
                        take_profit=tp1,
                        result='win',
                        pnl_pips=round(pnl, 1)
                    )
            
            elif signal.signal_type == SignalType.SELL:
                # رسیدن به حد ضرر
                if bar['high'] >= sl:
                    pnl = (effective_entry - sl) / self.pip_unit
                    return Trade(
                        entry_time=df.iloc[entry_bar].get('timestamps', entry_bar),
                        exit_time=bar.get('timestamps', entry_bar + j),
                        direction=SignalType.SELL,
                        entry_price=effective_entry,
                        exit_price=sl,
                        stop_loss=sl,
                        take_profit=tp1,
                        result='loss',
                        pnl_pips=round(pnl, 1)
                    )
                
                # رسیدن به تارگت 3
                if bar['low'] <= tp3:
                    pnl = (effective_entry - tp3) / self.pip_unit
                    return Trade(
                        entry_time=df.iloc[entry_bar].get('timestamps', entry_bar),
                        exit_time=bar.get('timestamps', entry_bar + j),
                        direction=SignalType.SELL,
                        entry_price=effective_entry,
                        exit_price=tp3,
                        stop_loss=sl,
                        take_profit=tp3,
                        result='win',
                        pnl_pips=round(pnl, 1)
                    )
                
                # رسیدن به تارگت 2
                if bar['low'] <= tp2:
                    sl = effective_entry
                
                # رسیدن به تارگت 1
                if bar['low'] <= tp1:
                    pnl = (effective_entry - tp1) / self.pip_unit
                    return Trade(
                        entry_time=df.iloc[entry_bar].get('timestamps', entry_bar),
                        exit_time=bar.get('timestamps', entry_bar + j),
                        direction=SignalType.SELL,
                        entry_price=effective_entry,
                        exit_price=tp1,
                        stop_loss=sl,
                        take_profit=tp1,
                        result='win',
                        pnl_pips=round(pnl, 1)
                    )
        
        # اگر به هیچ حدی نرسید، در آخرین کندل ببند
        last_bar = df.iloc[min(entry_bar + max_lookahead - 1, len(df) - 1)]
        if signal.signal_type == SignalType.BUY:
            pnl = (last_bar['close'] - effective_entry) / self.pip_unit
        else:
            pnl = (effective_entry - last_bar['close']) / self.pip_unit
        
        result_type = 'win' if pnl > 0 else ('loss' if pnl < 0 else 'breakeven')
        
        return Trade(
            entry_time=df.iloc[entry_bar].get('timestamps', entry_bar),
            exit_time=last_bar.get('timestamps', entry_bar + max_lookahead - 1),
            direction=signal.signal_type,
            entry_price=effective_entry,
            exit_price=last_bar['close'],
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit_1,
            result=result_type,
            pnl_pips=round(pnl, 1)
        )
    
    def _calculate_metrics(self, result: BacktestResult):
        """محاسبه معیارهای عملکرد"""
        
        trades = result.trades
        if not trades:
            return
        
        result.total_trades = len(trades)
        result.winning_trades = sum(1 for t in trades if t.result == 'win')
        result.losing_trades = sum(1 for t in trades if t.result == 'loss')
        result.breakeven_trades = sum(1 for t in trades if t.result == 'breakeven')
        
        result.win_rate = (result.winning_trades / result.total_trades) * 100 if result.total_trades > 0 else 0
        
        pnls = [t.pnl_pips for t in trades]
        result.total_pnl_pips = sum(pnls)
        
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        
        result.avg_win_pips = np.mean(wins) if wins else 0
        result.avg_loss_pips = abs(np.mean(losses)) if losses else 0
        
        # Profit Factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Expectancy
        result.expectancy = result.total_pnl_pips / result.total_trades if result.total_trades > 0 else 0
        
        # Best/Worst trade
        result.best_trade_pips = max(pnls) if pnls else 0
        result.worst_trade_pips = min(pnls) if pnls else 0
        
        # Max Drawdown
        equity = result.equity_curve
        peak = equity[0]
        max_dd = 0
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = peak - eq
            if dd > max_dd:
                max_dd = dd
        result.max_drawdown_pips = max_dd / 10  # تبدیل به پیپ
        
        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        current_wins = 0
        current_losses = 0
        
        for t in trades:
            if t.result == 'win':
                current_wins += 1
                current_losses = 0
                max_consec_wins = max(max_consec_wins, current_wins)
            elif t.result == 'loss':
                current_losses += 1
                current_wins = 0
                max_consec_losses = max(max_consec_losses, current_losses)
        
        result.consecutive_wins = max_consec_wins
        result.consecutive_losses = max_consec_losses
        
        # Sharpe Ratio (ساده‌شده)
        if len(pnls) > 1:
            returns = np.array(pnls)
            result.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        # Monthly returns
        for t in trades:
            if hasattr(t.exit_time, 'strftime'):
                month_key = t.exit_time.strftime('%Y-%m')
                result.monthly_returns[month_key] = result.monthly_returns.get(month_key, 0) + t.pnl_pips

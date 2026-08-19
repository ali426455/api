"""
استراتژی RTM (Read The Market)
نواحی عرضه و تقاضا، ساختار بازار، ورود / حد ضرر / خروج
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.strategy import OrderType, Signal, SignalType


PIP = 0.0001


@dataclass
class Zone:
    kind: str  # demand | supply
    pattern: str  # RBR, DBR, DBD, RBD
    low: float
    high: float
    start_idx: int
    end_idx: int
    impulse_pips: float
    fresh: bool = True
    score: float = 0.0

    @property
    def width_pips(self) -> float:
        return (self.high - self.low) / PIP

    @property
    def proximal(self) -> float:
        return self.high if self.kind == "demand" else self.low

    @property
    def distal(self) -> float:
        return self.low if self.kind == "demand" else self.high


@dataclass
class RTMContext:
    structure: str
    structure_text: str
    last_swing_high: Optional[float]
    last_swing_low: Optional[float]
    zones: List[Zone] = field(default_factory=list)
    active_zone: Optional[Zone] = None
    choch: bool = False


class RTMStrategy:
    """استراتژی اسکالپ RTM برای EUR/USD."""

    def __init__(self, config: Dict = None):
        self.config = {**self.default_config(), **(config or {})}
        self.last_context: Optional[RTMContext] = None

    @staticmethod
    def default_config() -> Dict:
        return {
            "swing_n": 3,
            "min_base": 1,
            "max_base": 10,
            "impulse_atr": 0.7,
            "max_zone_pips": 22,
            "min_zone_pips": 1.0,
            "min_impulse_pips": 7,
            "approach_pips": 5,
            "pending_pips": 16,
            "sl_buffer_pips": 2.5,
            "min_rr": 1.5,
            "min_confidence": 60,
            "lookback": 240,
        }

    def generate_signal(self, df: pd.DataFrame, **_kwargs) -> Signal:
        ctx, signal = self.analyze(df)
        self.last_context = ctx
        return signal

    def analyze(self, df: pd.DataFrame) -> tuple[RTMContext, Signal]:
        if df is None or len(df) < 40:
            ctx = RTMContext("UNKNOWN", "نامشخص ⚪", None, None)
            return ctx, self._wait(df, 0, "صبر کن — داده کافی برای تحلیل RTM نیست")

        work = df.tail(int(self.config["lookback"])).reset_index(drop=True)
        price = float(work["close"].iloc[-1])
        atr = self._atr(work)
        ctx = self._build_context(work, price, atr)
        signal = self._signal_from_context(work, price, atr, ctx)
        return ctx, signal

    def _build_context(self, df: pd.DataFrame, price: float, atr: float) -> RTMContext:
        swing_highs, swing_lows = self._swings(df)
        structure, structure_text, choch = self._structure(df, swing_highs, swing_lows, price)
        last_sh = swing_highs[-1][1] if swing_highs else None
        last_sl = swing_lows[-1][1] if swing_lows else None
        zones = self._detect_zones(df, atr)
        zones = self._mark_mitigated(df, zones)
        return RTMContext(
            structure=structure,
            structure_text=structure_text,
            last_swing_high=last_sh,
            last_swing_low=last_sl,
            zones=zones,
            choch=choch,
        )

    def _signal_from_context(
        self, df: pd.DataFrame, price: float, atr: float, ctx: RTMContext
    ) -> Signal:
        fresh_demand = [z for z in ctx.zones if z.kind == "demand" and z.fresh]
        fresh_supply = [z for z in ctx.zones if z.kind == "supply" and z.fresh]

        demand = self._nearest_zone(price, fresh_demand, "demand")
        supply = self._nearest_zone(price, fresh_supply, "supply")

        buy_setup = self._setup(price, demand, supply, ctx, "BUY") if demand else None
        sell_setup = self._setup(price, supply, demand, ctx, "SELL") if supply else None

        candidates = [s for s in (buy_setup, sell_setup) if s]
        if not candidates:
            if not fresh_demand and not fresh_supply:
                reason = "صبر کن — ناحیه عرضه/تقاضای تازه نزدیک قیمت نیست"
            else:
                reason = "صبر کن — قیمت بین نواحی است، الان برای ورود مناسب نیست"
            return self._wait(df, 45, reason)

        best = max(candidates, key=lambda s: s.confidence)
        if best.confidence < self.config["min_confidence"]:
            return self._wait(
                df,
                best.confidence,
                f"صبر کن — ستاپ ضعیف است (اطمینان {best.confidence:.0f}٪)",
            )

        ctx.active_zone = demand if best.signal_type == SignalType.BUY else supply
        return best

    def _setup(
        self,
        price: float,
        zone: Zone,
        opposite: Optional[Zone],
        ctx: RTMContext,
        side: str,
    ) -> Optional[Signal]:
        if zone.width_pips > self.config["max_zone_pips"]:
            return None

        reach = self.config["approach_pips"] * PIP
        pending = self.config["pending_pips"] * PIP
        if side == "BUY":
            near = zone.low - reach <= price <= zone.high + pending
        else:
            near = zone.low - pending <= price <= zone.high + reach
        if not near:
            return None

        buffer = self.config["sl_buffer_pips"] * PIP
        if side == "BUY":
            if ctx.structure == "BEARISH" and not ctx.choch and zone.pattern != "DBR":
                return None
            if zone.low - reach <= price <= zone.high + reach:
                order = OrderType.MARKET
                entry = round(min(max(price, zone.low), zone.high), 5)
                order_txt = "خرید مارکت روی ناحیه تقاضا"
            elif zone.high < price <= zone.high + pending:
                order = OrderType.LIMIT
                entry = round(zone.proximal, 5)
                order_txt = "خرید لیمیت؛ صبر تا برگشت به تقاضا"
            else:
                return None
            sl = round(zone.distal - buffer, 5)
            risk = entry - sl
            if risk <= 0:
                return None
            exit_price = self._target(entry, risk, opposite, ctx, "BUY")
            if (exit_price - entry) / risk < self.config["min_rr"]:
                return None
            tp2 = round(entry + risk * 2.2, 5)
            tp3 = round(entry + risk * 3.0, 5)
            signal_type = SignalType.BUY
            reason = f"{order_txt} — الگوی {zone.pattern}"
        else:
            if ctx.structure == "BULLISH" and not ctx.choch and zone.pattern != "RBD":
                return None
            if price < zone.low - reach:
                return None
            if abs(price - zone.proximal) <= 1.2 * PIP:
                order = OrderType.MARKET
                entry = round(price, 5)
                order_txt = "فروش مارکت روی ناحیه عرضه"
            elif price < zone.proximal:
                return None
            else:
                order = OrderType.LIMIT
                entry = round(zone.proximal, 5)
                order_txt = "فروش لیمیت روی لبه ناحیه عرضه"
            sl = round(zone.distal + buffer, 5)
            risk = sl - entry
            if risk <= 0:
                return None
            exit_price = self._target(entry, risk, opposite, ctx, "SELL")
            if (entry - exit_price) / risk < self.config["min_rr"]:
                return None
            tp2 = round(entry - risk * 2.2, 5)
            tp3 = round(entry - risk * 3.0, 5)
            signal_type = SignalType.SELL
            reason = f"{order_txt} — الگوی {zone.pattern}"

        confidence = self._confidence(zone, ctx, side)
        sl_pips = abs(entry - sl) / PIP
        tp1_pips = abs(exit_price - entry) / PIP
        return Signal(
            signal_type=signal_type,
            order_type=order,
            entry_price=round(entry, 5),
            stop_loss=round(sl, 5),
            take_profit_1=round(exit_price, 5),
            take_profit_2=round(tp2, 5),
            take_profit_3=round(tp3, 5),
            confidence=confidence,
            reason=reason,
            sl_pips=round(sl_pips, 1),
            tp1_pips=round(tp1_pips, 1),
            tp2_pips=round(abs(tp2 - entry) / PIP, 1),
            tp3_pips=round(abs(tp3 - entry) / PIP, 1),
        )

    def _target(
        self,
        entry: float,
        risk: float,
        opposite: Optional[Zone],
        ctx: RTMContext,
        side: str,
    ) -> float:
        min_rr = self.config["min_rr"]
        if side == "BUY":
            options = [entry + risk * min_rr]
            if opposite and opposite.low > entry:
                options.append(opposite.low)
            if ctx.last_swing_high and ctx.last_swing_high > entry:
                options.append(ctx.last_swing_high)
            valid = [x for x in options if (x - entry) / risk >= min_rr]
            return round(min(valid) if valid else entry + risk * min_rr, 5)
        options = [entry - risk * min_rr]
        if opposite and opposite.high < entry:
            options.append(opposite.high)
        if ctx.last_swing_low and ctx.last_swing_low < entry:
            options.append(ctx.last_swing_low)
        valid = [x for x in options if (entry - x) / risk >= min_rr]
        return round(max(valid) if valid else entry - risk * min_rr, 5)

    def _confidence(self, zone: Zone, ctx: RTMContext, side: str) -> float:
        score = 55.0
        if zone.fresh:
            score += 12
        if zone.impulse_pips >= 15:
            score += 8
        if zone.width_pips <= 12:
            score += 8
        aligned = (side == "BUY" and ctx.structure == "BULLISH") or (
            side == "SELL" and ctx.structure == "BEARISH"
        )
        if aligned:
            score += 12
        if ctx.choch and zone.pattern in {"DBR", "RBD"}:
            score += 10
        if ctx.structure == "RANGE":
            score -= 8
        return float(max(35, min(93, score)))

    def _detect_zones(self, df: pd.DataFrame, atr: float) -> List[Zone]:
        labels = self._label_candles(df, atr)
        zones: List[Zone] = []
        i = 1
        n = len(df)
        min_w = self.config["min_zone_pips"]
        max_w = self.config["max_zone_pips"] + 8
        while i < n - 1:
            if labels[i] != 0:
                i += 1
                continue
            start = i
            while i < n and labels[i] == 0:
                i += 1
            end = i - 1
            length = end - start + 1
            if length < self.config["min_base"] or length > self.config["max_base"]:
                continue
            if start == 0 or end >= n - 1:
                continue
            before = labels[start - 1]
            after = labels[end + 1]
            if after == 0 or before == 0:
                continue
            zone = self._zone_from_base(df, start, end, before, after, min_w, max_w)
            if zone:
                zones.append(zone)
        zones.extend(self._swing_zones(df, min_w, max_w))
        return self._dedupe_zones(zones)[-20:]

    def _zone_from_base(
        self,
        df: pd.DataFrame,
        start: int,
        end: int,
        before: int,
        after: int,
        min_w: float,
        max_w: float,
    ) -> Optional[Zone]:
        base = df.iloc[start : end + 1]
        low = float(base["low"].min())
        high = float(base["high"].max())
        width = (high - low) / PIP
        if width < min_w:
            pad = (min_w * PIP - (high - low)) / 2
            low -= pad
            high += pad
            width = (high - low) / PIP
        if width > max_w:
            return None
        n = len(df)
        after_move = abs(float(df["close"].iloc[min(end + 3, n - 1)]) - float(df["close"].iloc[end]))
        impulse_pips = after_move / PIP
        if impulse_pips < self.config["min_impulse_pips"]:
            return None
        if after > 0 and before > 0:
            kind, pattern = "demand", "RBR"
        elif after > 0 and before < 0:
            kind, pattern = "demand", "DBR"
        elif after < 0 and before < 0:
            kind, pattern = "supply", "DBD"
        elif after < 0 and before > 0:
            kind, pattern = "supply", "RBD"
        else:
            return None
        return Zone(
            kind=kind,
            pattern=pattern,
            low=round(low, 5),
            high=round(high, 5),
            start_idx=start,
            end_idx=end,
            impulse_pips=round(impulse_pips, 1),
        )

    def _swing_zones(self, df: pd.DataFrame, min_w: float, max_w: float) -> List[Zone]:
        highs, lows = self._swings(df)
        zones: List[Zone] = []
        close = df["close"].to_numpy()
        n = len(df)
        for idx, level in lows:
            if idx >= n - 4:
                continue
            future = float(close[min(idx + 6, n - 1)]) - level
            if future / PIP < self.config["min_impulse_pips"]:
                continue
            candle = df.iloc[idx]
            low = float(candle["low"])
            high = max(float(candle["open"]), float(candle["close"]))
            if (high - low) / PIP < min_w:
                high = low + min_w * PIP
            if (high - low) / PIP > max_w:
                continue
            zones.append(
                Zone("demand", "DBR", round(low, 5), round(high, 5), idx, idx, round(future / PIP, 1))
            )
        for idx, level in highs:
            if idx >= n - 4:
                continue
            future = level - float(close[min(idx + 6, n - 1)])
            if future / PIP < self.config["min_impulse_pips"]:
                continue
            candle = df.iloc[idx]
            high = float(candle["high"])
            low = min(float(candle["open"]), float(candle["close"]))
            if (high - low) / PIP < min_w:
                low = high - min_w * PIP
            if (high - low) / PIP > max_w:
                continue
            zones.append(
                Zone("supply", "RBD", round(low, 5), round(high, 5), idx, idx, round(future / PIP, 1))
            )
        return zones

    def _dedupe_zones(self, zones: List[Zone]) -> List[Zone]:
        if not zones:
            return []
        zones = sorted(zones, key=lambda z: (z.kind, z.low, z.end_idx))
        kept: List[Zone] = []
        for zone in zones:
            overlap = False
            for prev in kept:
                if prev.kind != zone.kind:
                    continue
                if min(prev.high, zone.high) - max(prev.low, zone.low) > 0:
                    if zone.impulse_pips >= prev.impulse_pips:
                        kept.remove(prev)
                        kept.append(zone)
                    overlap = True
                    break
            if not overlap:
                kept.append(zone)
        return sorted(kept, key=lambda z: z.end_idx)

    def _label_candles(self, df: pd.DataFrame, atr: float) -> np.ndarray:
        body = (df["close"] - df["open"]).abs().to_numpy()
        rng = (df["high"] - df["low"]).to_numpy()
        direction = np.sign((df["close"] - df["open"]).to_numpy())
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat(
            [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
            axis=1,
        ).max(axis=1)
        atr_series = tr.rolling(14, min_periods=5).mean().fillna(atr).to_numpy()
        atr_series = np.where(atr_series <= 0, atr, atr_series)
        impulse = (body >= atr_series * self.config["impulse_atr"]) | (rng >= atr_series * 1.2)
        labels = np.where(impulse, direction, 0)
        return labels.astype(int)

    def _mark_mitigated(self, df: pd.DataFrame, zones: List[Zone]) -> List[Zone]:
        closes = df["close"].to_numpy()
        lows = df["low"].to_numpy()
        highs = df["high"].to_numpy()
        for zone in zones:
            after = slice(zone.end_idx + 1, len(df))
            if zone.kind == "demand":
                zone.fresh = not np.any(closes[after] < zone.low)
                if np.any(lows[after] <= zone.high):
                    zone.score = 8
            else:
                zone.fresh = not np.any(closes[after] > zone.high)
                if np.any(highs[after] >= zone.low):
                    zone.score = 8
        return zones

    def _nearest_zone(self, price: float, zones: List[Zone], kind: str) -> Optional[Zone]:
        if not zones:
            return None
        if kind == "demand":
            candidates = [z for z in zones if z.low <= price + self.config["approach_pips"] * PIP]
        else:
            candidates = [z for z in zones if z.high >= price - self.config["approach_pips"] * PIP]
        if not candidates:
            return None
        return min(candidates, key=lambda z: abs(price - z.proximal))

    def _swings(self, df: pd.DataFrame) -> tuple[List[tuple[int, float]], List[tuple[int, float]]]:
        n = int(self.config["swing_n"])
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        sh, sl = [], []
        for i in range(n, len(df) - n):
            window_h = highs[i - n : i + n + 1]
            window_l = lows[i - n : i + n + 1]
            if highs[i] >= window_h.max() and highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                sh.append((i, float(highs[i])))
            if lows[i] <= window_l.min() and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                sl.append((i, float(lows[i])))
        return sh, sl

    def _structure(
        self,
        df: pd.DataFrame,
        swing_highs: List[tuple[int, float]],
        swing_lows: List[tuple[int, float]],
        price: float,
    ) -> tuple[str, str, bool]:
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return "RANGE", "رنج ⚪", False
        hh = swing_highs[-1][1] > swing_highs[-2][1]
        hl = swing_lows[-1][1] > swing_lows[-2][1]
        lh = swing_highs[-1][1] < swing_highs[-2][1]
        ll = swing_lows[-1][1] < swing_lows[-2][1]
        choch = False
        if hh and hl:
            structure, text = "BULLISH", "صعودی 🟢"
            if price < swing_lows[-1][1]:
                choch = True
                structure, text = "BEARISH", "تغییر ساختار نزولی 🔴"
        elif lh and ll:
            structure, text = "BEARISH", "نزولی 🔴"
            if price > swing_highs[-1][1]:
                choch = True
                structure, text = "BULLISH", "تغییر ساختار صعودی 🟢"
        else:
            structure, text = "RANGE", "رنج ⚪"
            if price > swing_highs[-1][1]:
                choch = True
                structure, text = "BULLISH", "شکست ساختار به بالا 🟢"
            elif price < swing_lows[-1][1]:
                choch = True
                structure, text = "BEARISH", "شکست ساختار به پایین 🔴"
        return structure, text, choch

    def _atr(self, df: pd.DataFrame, period: int = 14) -> float:
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat(
            [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
            axis=1,
        ).max(axis=1)
        val = float(tr.rolling(period).mean().iloc[-1])
        if np.isnan(val) or val <= 0:
            return 0.0008
        return val

    def _wait(self, df: pd.DataFrame, confidence: float, reason: str) -> Signal:
        price = float(df["close"].iloc[-1]) if df is not None and len(df) else 0.0
        return Signal(
            signal_type=SignalType.WAIT,
            order_type=OrderType.NO_TRADE,
            entry_price=round(price, 5),
            stop_loss=round(price, 5),
            take_profit_1=round(price, 5),
            take_profit_2=round(price, 5),
            take_profit_3=round(price, 5),
            confidence=confidence,
            reason=reason,
        )

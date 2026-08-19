"""
استراتژی RTM — Read The Market (IF Myante)

قوانین اجرا شده از منابع RTM:
- ناحیه = بیس قبل از حرکت انفجاری (RBR / DBR / DBD / RBD)
- ورود = لیمیت روی لبه نزدیک ناحیه (proximal) — FTB
- حد ضرر = کمی آن‌طرف لبه دور ناحیه (distal / MPL)
- تارگت = ناحیه مخالف تازه، نه عدد ثابت پیپ
- اگر قیمت وسط دو ناحیه باشد: صبر کن، ولی همان اعداد لیمیت را نشان بده
- کوازیمو (QM): ورود روی QML، حد ضرر پشت MPL
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
    kind: str
    pattern: str
    low: float
    high: float
    start_idx: int
    end_idx: int
    impulse_pips: float
    fresh: bool = True

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
class TradePlan:
    status: str  # ENTER | LIMIT | WAIT
    side: str  # BUY | SELL | NONE
    entry: float
    sl: float
    tp: float
    sl_pips: float
    tp_pips: float
    reason: str
    pattern: str
    confidence: float
    distance_pips: float = 0.0

    def apply_price(self, price: float) -> "TradePlan":
        if self.side == "NONE" or not self.entry:
            return self
        self.distance_pips = round(abs(price - self.entry) / PIP, 1)
        reach = 5 * PIP
        if self.side == "BUY":
            at_zone = self.sl < price <= self.entry + reach
        else:
            at_zone = self.entry - reach <= price < self.sl
        if at_zone:
            self.status = "ENTER"
            if self.side == "BUY":
                self.reason = f"الان بخر — قیمت به ناحیه تقاضا رسید ({self.pattern})"
            else:
                self.reason = f"الان بفروش — قیمت به ناحیه عرضه رسید ({self.pattern})"
        elif self.status != "WAIT":
            self.status = "LIMIT"
            side_fa = "خرید" if self.side == "BUY" else "فروش"
            self.reason = (
                f"صبر کن — لیمیت {side_fa} را روی {self.entry:.5f} بگذار "
                f"(تا ورود {self.distance_pips:.1f} پیپ)"
            )
        return self


@dataclass
class RTMContext:
    structure: str
    structure_text: str
    last_swing_high: Optional[float]
    last_swing_low: Optional[float]
    zones: List[Zone] = field(default_factory=list)
    plan: Optional[TradePlan] = None
    alt_plan: Optional[TradePlan] = None
    choch: bool = False


class RTMStrategy:
    def __init__(self, config: Dict = None):
        self.config = {**self.default_config(), **(config or {})}
        self.last_context: Optional[RTMContext] = None

    @staticmethod
    def default_config() -> Dict:
        return {
            "swing_n": 3,
            "min_base": 1,
            "max_base": 8,
            "impulse_atr": 0.7,
            "max_zone_pips": 28,
            "min_zone_pips": 1.0,
            "min_impulse_pips": 7,
            "sl_buffer_pips": 2.5,
            "min_rr": 1.2,
            "lookback": 260,
        }

    def generate_signal(self, df: pd.DataFrame, **_kwargs) -> Signal:
        ctx, plan = self.analyze(df)
        self.last_context = ctx
        return self._as_signal(plan)

    def analyze(self, df: pd.DataFrame) -> tuple[RTMContext, TradePlan]:
        if df is None or len(df) < 40:
            ctx = RTMContext("UNKNOWN", "نامشخص", None, None)
            plan = TradePlan("WAIT", "NONE", 0, 0, 0, 0, 0, "صبر کن — داده کافی نیست", "", 0)
            ctx.plan = plan
            return ctx, plan

        work = df.tail(int(self.config["lookback"])).reset_index(drop=True)
        price = float(work["close"].iloc[-1])
        atr = self._atr(work)
        ctx = self._context(work, price, atr)
        buy = self._plan_for_side(price, ctx, "BUY")
        sell = self._plan_for_side(price, ctx, "SELL")
        plan, alt = self._pick(buy, sell, price)
        plan.apply_price(price)
        if alt:
            alt.apply_price(price)
        ctx.plan = plan
        ctx.alt_plan = alt
        return ctx, plan

    def _context(self, df: pd.DataFrame, price: float, atr: float) -> RTMContext:
        sh, sl = self._swings(df)
        structure, text, choch = self._structure(sh, sl, price)
        zones = self._mark_mitigated(df, self._detect_zones(df, atr) + self._qm_zones(df, sh, sl))
        return RTMContext(
            structure=structure,
            structure_text=text,
            last_swing_high=sh[-1][1] if sh else None,
            last_swing_low=sl[-1][1] if sl else None,
            zones=zones,
            choch=choch,
        )

    def _plan_for_side(self, price: float, ctx: RTMContext, side: str) -> Optional[TradePlan]:
        kind = "demand" if side == "BUY" else "supply"
        zones = [z for z in ctx.zones if z.kind == kind and z.fresh]
        if not zones:
            zones = [z for z in ctx.zones if z.kind == kind]
        zone = None
        if zones:
            if side == "BUY":
                below = [z for z in zones if z.proximal <= price + 8 * PIP]
                zone = min(below, key=lambda z: abs(price - z.proximal)) if below else None
            else:
                above = [z for z in zones if z.proximal >= price - 8 * PIP]
                zone = min(above, key=lambda z: abs(price - z.proximal)) if above else None
        if zone is None:
            zone = self._structure_zone(ctx, side, price)
        if zone is None:
            return None
        if zone.width_pips > self.config["max_zone_pips"]:
            return None

        buffer = self.config["sl_buffer_pips"] * PIP
        if side == "BUY":
            entry = round(zone.proximal, 5)
            sl = round(zone.distal - buffer, 5)
            risk = entry - sl
        else:
            entry = round(zone.proximal, 5)
            sl = round(zone.distal + buffer, 5)
            risk = sl - entry
        if risk <= 3 * PIP:
            return None

        opposite_kind = "supply" if side == "BUY" else "demand"
        opposite = self._opposite(ctx.zones, opposite_kind, entry, side)
        tp = self._target(entry, risk, opposite, ctx, side)
        rr = abs(tp - entry) / risk
        if rr < self.config["min_rr"]:
            tp = round(entry + risk * self.config["min_rr"], 5) if side == "BUY" else round(
                entry - risk * self.config["min_rr"], 5
            )
            rr = self.config["min_rr"]

        conf = 58
        if zone.fresh:
            conf += 12
        if zone.impulse_pips >= 12:
            conf += 8
        if zone.width_pips <= 12:
            conf += 8
        if zone.pattern == "QM":
            conf += 10
        aligned = (side == "BUY" and ctx.structure == "BULLISH") or (
            side == "SELL" and ctx.structure == "BEARISH"
        )
        if aligned:
            conf += 8
        conf = min(92, conf)

        return TradePlan(
            status="LIMIT",
            side=side,
            entry=entry,
            sl=round(sl, 5),
            tp=round(tp, 5),
            sl_pips=round(abs(entry - sl) / PIP, 1),
            tp_pips=round(abs(tp - entry) / PIP, 1),
            reason="",
            pattern=zone.pattern,
            confidence=float(conf),
        )

    def _pick(
        self, buy: Optional[TradePlan], sell: Optional[TradePlan], price: float
    ) -> tuple[TradePlan, Optional[TradePlan]]:
        scored = []
        for plan in (buy, sell):
            if not plan:
                continue
            dist = abs(price - plan.entry) / PIP
            score = plan.confidence + max(0, 30 - dist)
            scored.append((score, dist, plan))
        if not scored:
            return (
                TradePlan(
                    "WAIT",
                    "NONE",
                    0,
                    0,
                    0,
                    0,
                    0,
                    "صبر کن — ناحیه RTM معتبر پیدا نشد",
                    "",
                    0,
                ),
                None,
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][2]
        alt = scored[1][2] if len(scored) > 1 else None
        return best, alt

    def _structure_zone(self, ctx: RTMContext, side: str, price: float) -> Optional[Zone]:
        if side == "BUY" and ctx.last_swing_low:
            low = ctx.last_swing_low
            high = low + max(8 * PIP, (price - low) * 0.08)
            if high <= price + 20 * PIP:
                return Zone("demand", "SWING", low, high, 0, 0, 10, fresh=True)
        if side == "SELL" and ctx.last_swing_high:
            high = ctx.last_swing_high
            low = high - max(8 * PIP, (high - price) * 0.08)
            if low >= price - 20 * PIP:
                return Zone("supply", "SWING", low, high, 0, 0, 10, fresh=True)
        return None

    def _opposite(self, zones: List[Zone], kind: str, entry: float, side: str) -> Optional[Zone]:
        fresh = [z for z in zones if z.kind == kind and z.fresh]
        if side == "BUY":
            cands = [z for z in fresh if z.low > entry]
            return min(cands, key=lambda z: z.low) if cands else None
        cands = [z for z in fresh if z.high < entry]
        return max(cands, key=lambda z: z.high) if cands else None

    def _target(self, entry: float, risk: float, opposite: Optional[Zone], ctx: RTMContext, side: str) -> float:
        if side == "BUY":
            options = [entry + risk * max(1.5, self.config["min_rr"])]
            if opposite:
                options.append(opposite.low - 2 * PIP)
            if ctx.last_swing_high and ctx.last_swing_high > entry:
                options.append(ctx.last_swing_high)
            valid = [x for x in options if x > entry]
            return round(max(valid) if valid else entry + risk * 1.5, 5)
        options = [entry - risk * max(1.5, self.config["min_rr"])]
        if opposite:
            options.append(opposite.high + 2 * PIP)
        if ctx.last_swing_low and ctx.last_swing_low < entry:
            options.append(ctx.last_swing_low)
        valid = [x for x in options if x < entry]
        return round(min(valid) if valid else entry - risk * 1.5, 5)

    def _qm_zones(
        self,
        df: pd.DataFrame,
        highs: List[tuple[int, float]],
        lows: List[tuple[int, float]],
    ) -> List[Zone]:
        zones: List[Zone] = []
        if len(highs) >= 3 and len(lows) >= 2:
            h1, h2, h3 = highs[-3], highs[-2], highs[-1]
            l1, l2 = lows[-2], lows[-1]
            if h2[1] > h1[1] and l2[1] < l1[1] and h3[1] < h2[1] and h3[1] >= h1[1] - 3 * PIP:
                qml, mpl = h1[1], h2[1]
                if mpl > qml:
                    zones.append(Zone("supply", "QM", round(qml, 5), round(mpl, 5), h1[0], h3[0], (mpl - qml) / PIP))
        if len(lows) >= 3 and len(highs) >= 2:
            l1, l2, l3 = lows[-3], lows[-2], lows[-1]
            h1, h2 = highs[-2], highs[-1]
            if l2[1] < l1[1] and h2[1] > h1[1] and l3[1] > l2[1] and l3[1] <= l1[1] + 3 * PIP:
                qml, mpl = l1[1], l2[1]
                if qml > mpl:
                    zones.append(Zone("demand", "QM", round(mpl, 5), round(qml, 5), l1[0], l3[0], (qml - mpl) / PIP))
        return zones

    def _detect_zones(self, df: pd.DataFrame, atr: float) -> List[Zone]:
        labels = self._label_candles(df, atr)
        zones: List[Zone] = []
        i = 1
        n = len(df)
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
            before, after = labels[start - 1], labels[end + 1]
            if before == 0 or after == 0:
                continue
            base = df.iloc[start : end + 1]
            low, high = float(base["low"].min()), float(base["high"].max())
            width = (high - low) / PIP
            if width < self.config["min_zone_pips"]:
                pad = (self.config["min_zone_pips"] * PIP - (high - low)) / 2
                low -= pad
                high += pad
            if (high - low) / PIP > self.config["max_zone_pips"] + 6:
                continue
            impulse = abs(float(df["close"].iloc[min(end + 3, n - 1)]) - float(df["close"].iloc[end])) / PIP
            if impulse < self.config["min_impulse_pips"]:
                continue
            if after > 0 and before > 0:
                kind, pattern = "demand", "RBR"
            elif after > 0 and before < 0:
                kind, pattern = "demand", "DBR"
            elif after < 0 and before < 0:
                kind, pattern = "supply", "DBD"
            elif after < 0 and before > 0:
                kind, pattern = "supply", "RBD"
            else:
                continue
            zones.append(Zone(kind, pattern, round(low, 5), round(high, 5), start, end, round(impulse, 1)))
        zones.extend(self._swing_zones(df))
        return self._dedupe(zones)[-24:]

    def _swing_zones(self, df: pd.DataFrame) -> List[Zone]:
        highs, lows = self._swings(df)
        close = df["close"].to_numpy()
        n = len(df)
        out: List[Zone] = []
        for idx, level in lows:
            if idx >= n - 4:
                continue
            impulse = (float(close[min(idx + 6, n - 1)]) - level) / PIP
            if impulse < self.config["min_impulse_pips"]:
                continue
            candle = df.iloc[idx]
            low = float(candle["low"])
            high = max(float(candle["open"]), float(candle["close"]), low + PIP)
            if (high - low) / PIP <= self.config["max_zone_pips"]:
                out.append(Zone("demand", "DBR", round(low, 5), round(high, 5), idx, idx, round(impulse, 1)))
        for idx, level in highs:
            if idx >= n - 4:
                continue
            impulse = (level - float(close[min(idx + 6, n - 1)])) / PIP
            if impulse < self.config["min_impulse_pips"]:
                continue
            candle = df.iloc[idx]
            high = float(candle["high"])
            low = min(float(candle["open"]), float(candle["close"]), high - PIP)
            if (high - low) / PIP <= self.config["max_zone_pips"]:
                out.append(Zone("supply", "RBD", round(low, 5), round(high, 5), idx, idx, round(impulse, 1)))
        return out

    def _dedupe(self, zones: List[Zone]) -> List[Zone]:
        kept: List[Zone] = []
        for zone in sorted(zones, key=lambda z: (z.kind, z.low, z.end_idx)):
            hit = None
            for prev in kept:
                if prev.kind == zone.kind and min(prev.high, zone.high) - max(prev.low, zone.low) > 0:
                    hit = prev
                    break
            if hit is None:
                kept.append(zone)
            elif zone.impulse_pips >= hit.impulse_pips:
                kept.remove(hit)
                kept.append(zone)
        return sorted(kept, key=lambda z: z.end_idx)

    def _label_candles(self, df: pd.DataFrame, atr: float) -> np.ndarray:
        body = (df["close"] - df["open"]).abs().to_numpy()
        rng = (df["high"] - df["low"]).to_numpy()
        direction = np.sign((df["close"] - df["open"]).to_numpy())
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        atr_s = tr.rolling(14, min_periods=5).mean().fillna(atr).to_numpy()
        atr_s = np.where(atr_s <= 0, atr, atr_s)
        impulse = (body >= atr_s * self.config["impulse_atr"]) | (rng >= atr_s * 1.2)
        return np.where(impulse, direction, 0).astype(int)

    def _mark_mitigated(self, df: pd.DataFrame, zones: List[Zone]) -> List[Zone]:
        closes = df["close"].to_numpy()
        for zone in zones:
            after = slice(zone.end_idx + 1, len(df))
            if zone.kind == "demand":
                zone.fresh = not np.any(closes[after] < zone.low) if zone.end_idx + 1 < len(df) else True
            else:
                zone.fresh = not np.any(closes[after] > zone.high) if zone.end_idx + 1 < len(df) else True
        return zones

    def _swings(self, df: pd.DataFrame):
        n = int(self.config["swing_n"])
        highs, lows = df["high"].to_numpy(), df["low"].to_numpy()
        sh, sl = [], []
        for i in range(n, len(df) - n):
            if highs[i] >= highs[i - n : i + n + 1].max() and highs[i] > highs[i - 1] and highs[i] > highs[i + 1]:
                sh.append((i, float(highs[i])))
            if lows[i] <= lows[i - n : i + n + 1].min() and lows[i] < lows[i - 1] and lows[i] < lows[i + 1]:
                sl.append((i, float(lows[i])))
        return sh, sl

    def _structure(self, sh, sl, price: float):
        if len(sh) < 2 or len(sl) < 2:
            return "RANGE", "رنج", False
        hh, hl = sh[-1][1] > sh[-2][1], sl[-1][1] > sl[-2][1]
        lh, ll = sh[-1][1] < sh[-2][1], sl[-1][1] < sl[-2][1]
        if hh and hl:
            if price < sl[-1][1]:
                return "BEARISH", "تغییر ساختار نزولی", True
            return "BULLISH", "ساختار صعودی", False
        if lh and ll:
            if price > sh[-1][1]:
                return "BULLISH", "تغییر ساختار صعودی", True
            return "BEARISH", "ساختار نزولی", False
        return "RANGE", "ساختار رنج", False

    def _atr(self, df: pd.DataFrame, period: int = 14) -> float:
        high, low, close = df["high"], df["low"], df["close"]
        tr = pd.concat([high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
        val = float(tr.rolling(period).mean().iloc[-1])
        return 0.0008 if np.isnan(val) or val <= 0 else val

    def _as_signal(self, plan: TradePlan) -> Signal:
        if plan.side == "BUY":
            stype, otype = SignalType.BUY, OrderType.LIMIT if plan.status == "LIMIT" else OrderType.MARKET
        elif plan.side == "SELL":
            stype, otype = SignalType.SELL, OrderType.LIMIT if plan.status == "LIMIT" else OrderType.MARKET
        else:
            stype, otype = SignalType.WAIT, OrderType.NO_TRADE
        return Signal(
            signal_type=stype,
            order_type=otype,
            entry_price=plan.entry,
            stop_loss=plan.sl,
            take_profit_1=plan.tp,
            take_profit_2=plan.tp,
            take_profit_3=plan.tp,
            confidence=plan.confidence,
            reason=plan.reason,
            sl_pips=plan.sl_pips,
            tp1_pips=plan.tp_pips,
        )

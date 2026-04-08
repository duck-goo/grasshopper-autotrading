# backend/strategy/condition.py
import pandas as pd
import numpy as np

def calculate_rsi(prices: list, period: int = 14) -> float:
    """RSI 계산"""
    if len(prices) < period + 1:
        return None

    df = pd.Series(prices)
    delta = df.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)

def calculate_macd(prices: list):
    """MACD 계산"""
    if len(prices) < 26:
        return None, None, None

    df = pd.Series(prices)
    ema12 = df.ewm(span=12, adjust=False).mean()
    ema26 = df.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return round(macd.iloc[-1], 2), round(signal.iloc[-1], 2), round(hist.iloc[-1], 2)

def calculate_ma(prices: list, period: int) -> float:
    """이동평균선 계산"""
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)

def check_condition(condition: dict, prices: list, current_price: float) -> bool:
    """
    조건식 체크
    condition 예시:
    {"type": "RSI", "operator": "<=", "value": 30}
    {"type": "MA_CROSS", "short": 5, "long": 20}
    {"type": "PRICE", "operator": ">=", "value": 80000}
    """
    ctype = condition.get("type")

    if ctype == "RSI":
        rsi = calculate_rsi(prices)
        if rsi is None:
            return False
        return _compare(rsi, condition["operator"], condition["value"])

    elif ctype == "MACD":
        macd, signal, hist = calculate_macd(prices)
        if macd is None:
            return False
        # MACD 골든크로스 (MACD > Signal)
        return macd > signal

    elif ctype == "MA_CROSS":
        short_ma = calculate_ma(prices, condition["short"])
        long_ma = calculate_ma(prices, condition["long"])
        if short_ma is None or long_ma is None:
            return False
        return short_ma > long_ma

    elif ctype == "PRICE":
        return _compare(current_price, condition["operator"], condition["value"])

    return False

def _compare(value, operator: str, target) -> bool:
    """비교 연산자 처리"""
    if operator == ">=":
        return value >= target
    elif operator == "<=":
        return value <= target
    elif operator == ">":
        return value > target
    elif operator == "<":
        return value < target
    elif operator == "==":
        return value == target
    return False

def calculate_bollinger(prices: list, period: int = 20, multiplier: float = 2.0):
    """볼린저밴드 계산"""
    if len(prices) < period:
        return None, None, None
    
    ma = sum(prices[-period:]) / period
    std = (sum((p - ma) ** 2 for p in prices[-period:]) / period) ** 0.5
    upper = ma + (multiplier * std)
    lower = ma - (multiplier * std)
    return round(upper, 2), round(ma, 2), round(lower, 2)

def calculate_stochastic(prices: list, highs: list, lows: list, period: int = 14):
    """스토캐스틱 계산"""
    if len(prices) < period:
        return None, None
    
    highest_high = max(highs[-period:])
    lowest_low = min(lows[-period:])
    
    if highest_high == lowest_low:
        return 50.0, 50.0
    
    k = ((prices[-1] - lowest_low) / (highest_high - lowest_low)) * 100
    d = sum([
        ((prices[-i] - min(lows[-period-i:-i] if len(lows) > period+i else lows)) /
         (max(highs[-period-i:-i] if len(highs) > period+i else highs) -
          min(lows[-period-i:-i] if len(lows) > period+i else lows) or 1)) * 100
        for i in range(1, 4)
    ]) / 3
    
    return round(k, 2), round(d, 2)

def calculate_volume_ratio(volumes: list, period: int = 5) -> float:
    """거래량 비율 계산 (현재 거래량 / 평균 거래량)"""
    if len(volumes) < period + 1:
        return None
    avg_volume = sum(volumes[-period-1:-1]) / period
    if avg_volume == 0:
        return None
    return round(volumes[-1] / avg_volume * 100, 2)

def check_condition_v2(condition: dict, data: list) -> bool:
    """
    확장된 조건식 체크
    data: OHLCV 딕셔너리 리스트
    condition 예시:
    {"type": "RSI", "operator": "<=", "value": 30}
    {"type": "BOLLINGER", "position": "below_lower"}
    {"type": "VOLUME_RATIO", "operator": ">=", "value": 200}
    {"type": "PRICE", "operator": ">=", "value": 10000}
    {"type": "CHANGE_RATE", "operator": ">=", "value": 5.0}
    """
    if not data:
        return False

    closes = [d["close"] for d in data]
    current_price = closes[-1]
    ctype = condition.get("type")

    try:
        if ctype == "RSI":
            rsi = calculate_rsi(closes)
            if rsi is None:
                return False
            return _compare(rsi, condition["operator"], condition["value"])

        elif ctype == "MACD":
            macd, signal, hist = calculate_macd(closes)
            if macd is None:
                return False
            if condition.get("signal") == "golden_cross":
                return macd > signal
            elif condition.get("signal") == "dead_cross":
                return macd < signal
            return macd > signal

        elif ctype == "MA_CROSS":
            short_ma = calculate_ma(closes, condition.get("short", 5))
            long_ma = calculate_ma(closes, condition.get("long", 20))
            if short_ma is None or long_ma is None:
                return False
            if condition.get("signal") == "golden_cross":
                prev_closes = closes[:-1]
                prev_short = calculate_ma(prev_closes, condition.get("short", 5))
                prev_long = calculate_ma(prev_closes, condition.get("long", 20))
                return short_ma > long_ma and prev_short <= prev_long
            return short_ma > long_ma

        elif ctype == "MA":
            period = condition.get("period", 20)
            ma = calculate_ma(closes, period)
            if ma is None:
                return False
            return _compare(current_price, condition["operator"], ma)

        elif ctype == "BOLLINGER":
            upper, mid, lower = calculate_bollinger(closes)
            if upper is None:
                return False
            position = condition.get("position", "below_lower")
            if position == "below_lower":
                return current_price < lower
            elif position == "above_upper":
                return current_price > upper
            elif position == "above_mid":
                return current_price > mid
            elif position == "below_mid":
                return current_price < mid

        elif ctype == "VOLUME_RATIO":
            volumes = [d["volume"] for d in data]
            ratio = calculate_volume_ratio(volumes)
            if ratio is None:
                return False
            return _compare(ratio, condition["operator"], condition["value"])

        elif ctype == "PRICE":
            return _compare(current_price, condition["operator"], condition["value"])

        elif ctype == "CHANGE_RATE":
            # ✅ 1순위: 데이터에 change_rate 필드가 이미 있으면 그대로 사용
            #    (실시간 스캐너 경로에서 KIS API가 직접 등락률을 넘겨줌)
            last = data[-1] if data else {}
            if "change_rate" in last and last["change_rate"] not in (None, "", 0):
                try:
                    change_rate = float(str(last["change_rate"]).replace("%", "").strip())
                    return _compare(change_rate, condition["operator"], condition["value"])
                except (ValueError, TypeError):
                    pass  # 변환 실패하면 아래 종가 기반 계산으로 폴백

            # 2순위: 종가 2개로 계산 (일봉 히스토리 경로)
            if len(closes) < 2:
                return False
            change_rate = ((closes[-1] - closes[-2]) / closes[-2]) * 100
            return _compare(change_rate, condition["operator"], condition["value"])

        elif ctype == "HIGH_52W":
            if len(closes) < 52:
                return False
            high_52w = max(closes[-252:])
            ratio = (current_price / high_52w) * 100
            return _compare(ratio, condition["operator"], condition["value"])

        elif ctype == "LOW_52W":
            if len(closes) < 52:
                return False
            low_52w = min(closes[-252:])
            ratio = (current_price / low_52w) * 100
            return _compare(ratio, condition["operator"], condition["value"])

    except Exception as e:
        print(f"조건식 오류: {e}")
        return False

    return False
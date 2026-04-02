# backend/strategy/backtest.py
from strategy.condition import calculate_rsi, calculate_macd, calculate_ma

def run_backtest(
    data: list,          # 과거 OHLCV 데이터
    condition_type: str, # 매수 조건 (RSI, MACD, MA_CROSS)
    condition_value: float = 30,  # 조건값 (RSI의 경우 기준값)
    take_profit: float = 5.0,     # 익절 %
    stop_loss: float = 3.0,       # 손절 %
    order_amount: int = 100000,   # 1회 주문금액
) -> dict:
    """백테스트 실행"""

    if len(data) < 30:
        return {"error": "데이터가 부족해요 (최소 30일 필요)"}

    trades = []          # 매매 내역
    position = None      # 현재 보유 포지션
    cash = order_amount  # 시작 현금

    prices = [d["close"] for d in data]

    for i in range(20, len(data)):
        current = data[i]
        current_price = current["close"]
        current_date = current["date"]
        window = prices[:i+1]

        # 보유 중일 때 익절/손절 체크
        if position:
            profit_rate = ((current_price - position["buy_price"]) / position["buy_price"]) * 100

            # 익절
            if profit_rate >= take_profit:
                sell_amount = current_price * position["qty"]
                profit = sell_amount - position["buy_amount"]
                trades.append({
                    "type": "sell",
                    "reason": "익절",
                    "date": current_date,
                    "price": current_price,
                    "qty": position["qty"],
                    "profit": profit,
                    "profit_rate": profit_rate,
                    "hold_days": i - position["buy_idx"]
                })
                cash += sell_amount
                position = None
                continue

            # 손절
            if profit_rate <= -stop_loss:
                sell_amount = current_price * position["qty"]
                profit = sell_amount - position["buy_amount"]
                trades.append({
                    "type": "sell",
                    "reason": "손절",
                    "date": current_date,
                    "price": current_price,
                    "qty": position["qty"],
                    "profit": profit,
                    "profit_rate": profit_rate,
                    "hold_days": i - position["buy_idx"]
                })
                cash += sell_amount
                position = None
                continue

        # 포지션 없을 때 매수 조건 체크
        if not position:
            signal = False

            if condition_type == "RSI":
                rsi = calculate_rsi(window)
                if rsi and rsi <= condition_value:
                    signal = True

            elif condition_type == "MACD":
                macd, sig, hist = calculate_macd(window)
                if macd and sig and macd > sig:
                    signal = True

            elif condition_type == "MA_CROSS":
                ma5 = calculate_ma(window, 5)
                ma20 = calculate_ma(window, 20)
                if ma5 and ma20 and ma5 > ma20:
                    # 직전에 데드크로스였는지 확인
                    prev_window = prices[:i]
                    prev_ma5 = calculate_ma(prev_window, 5)
                    prev_ma20 = calculate_ma(prev_window, 20)
                    if prev_ma5 and prev_ma20 and prev_ma5 <= prev_ma20:
                        signal = True

            if signal:
                qty = max(1, int(order_amount / current_price))
                buy_amount = current_price * qty
                position = {
                    "buy_price": current_price,
                    "buy_date": current_date,
                    "buy_amount": buy_amount,
                    "buy_idx": i,
                    "qty": qty
                }
                cash -= buy_amount
                trades.append({
                    "type": "buy",
                    "date": current_date,
                    "price": current_price,
                    "qty": qty,
                    "amount": buy_amount
                })

    # 결과 분석
    sell_trades = [t for t in trades if t["type"] == "sell"]
    win_trades = [t for t in sell_trades if t["profit"] > 0]
    lose_trades = [t for t in sell_trades if t["profit"] <= 0]

    total_profit = sum(t["profit"] for t in sell_trades)
    total_profit_rate = (total_profit / order_amount) * 100 if sell_trades else 0
    win_rate = (len(win_trades) / len(sell_trades) * 100) if sell_trades else 0
    avg_hold_days = sum(t["hold_days"] for t in sell_trades) / len(sell_trades) if sell_trades else 0
    max_loss = min((t["profit_rate"] for t in sell_trades), default=0)

    return {
        "summary": {
            "total_trades": len(sell_trades),
            "win_trades": len(win_trades),
            "lose_trades": len(lose_trades),
            "win_rate": round(win_rate, 1),
            "total_profit": round(total_profit),
            "total_profit_rate": round(total_profit_rate, 2),
            "avg_hold_days": round(avg_hold_days, 1),
            "max_loss_rate": round(max_loss, 2),
        },
        "trades": trades
    }
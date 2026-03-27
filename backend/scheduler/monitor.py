# backend/scheduler/monitor.py
import asyncio
from api.stock import get_stock_price, get_stock_history
from api.watchlist import get_tickers
from strategy.condition import check_condition, calculate_rsi, calculate_macd, calculate_ma
from notification.telegram import send_message
from auth.token_manager import token_manager

# 기본 조건식 설정 (나중에 DB에서 관리할 예정)
DEFAULT_CONDITIONS = [
    {"type": "RSI", "operator": "<=", "value": 30},   # RSI 30 이하 매수
    {"type": "RSI", "operator": ">=", "value": 70},   # RSI 70 이상 매도
    {"type": "MACD"},                                   # MACD 골든크로스
    {"type": "MA_CROSS", "short": 5, "long": 20},     # MA 골든크로스
]

# 중복 알림 방지 (종목+조건 조합 저장)
alerted = set()

async def monitor_loop():
    """관심종목 모니터링 루프"""
    print("🔍 모니터링 시작!")
    while True:
        try:
            token = token_manager.get_token()
            tickers = get_tickers()

            for t in tickers:
                ticker = t["ticker"]
                name = t["name"]

                # 현재가 & 과거 데이터 조회
                price_data = get_stock_price(ticker, token)
                prices = get_stock_history(ticker, token)

                if not prices:
                    continue

                current_price = float(price_data.get("price", 0))
                rsi = calculate_rsi(prices)

                print(f"📊 {name}({ticker}) 현재가: {current_price:,.0f}원 | RSI: {rsi}")

                # 조건식 체크
                for condition in DEFAULT_CONDITIONS:
                    alert_key = f"{ticker}_{condition['type']}"
                    is_triggered = bool(check_condition(condition, prices, current_price))

                    if is_triggered and alert_key not in alerted:
                        # 알림 전송
                        msg = (
                            f"🚨 <b>매매 신호 감지!</b>\n"
                            f"종목: {name} ({ticker})\n"
                            f"현재가: {current_price:,.0f}원\n"
                            f"RSI: {rsi}\n"
                            f"조건: {condition['type']} 충족!"
                        )
                        send_message(msg)
                        alerted.add(alert_key)
                        print(f"🚨 알림 전송: {name} - {condition['type']}")

                    elif not is_triggered and alert_key in alerted:
                        # 조건 해제 시 알림 초기화
                        alerted.discard(alert_key)

        except Exception as e:
            print(f"❌ 모니터링 오류: {e}")

        # 60초마다 반복
        await asyncio.sleep(60)
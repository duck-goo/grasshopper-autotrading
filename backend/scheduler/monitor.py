# backend/scheduler/monitor.py
import asyncio
from api.stock import get_stock_price, get_stock_history
from api.watchlist import get_tickers
from api.order import buy_stock, sell_stock, get_balance
from strategy.condition import check_condition, calculate_rsi, calculate_macd, calculate_ma
from notification.telegram import send_message, send_order_confirm
from notification.popup import send_signal_popup, send_popup
from auth.token_manager import token_manager
from database.logger import log_monitor, log_alert, log_error, get_settings

DEFAULT_CONDITIONS = [
    {"type": "RSI", "operator": "<=", "value": 30},
    {"type": "RSI", "operator": ">=", "value": 70},
    {"type": "MACD"},
    {"type": "MA_CROSS", "short": 5, "long": 20},
]

alerted = set()
balance_cache = {}
balance_last_updated = 0

async def monitor_loop():
    """관심종목 모니터링 루프"""
    global balance_cache, balance_last_updated
    print("🔍 모니터링 시작!")
    while True:
        try:
            settings = get_settings()
            token = token_manager.get_token()
            tickers = get_tickers()

            # 잔고는 5분마다만 조회 (매번 조회 X)
            import time
            if time.time() - balance_last_updated > 300:
                balance_cache = get_balance(token)
                balance_last_updated = time.time()

            for t in tickers:
                ticker = t["ticker"]
                name = t["name"]

                try:
                    price_data = get_stock_price(ticker, token)
                    prices = get_stock_history(ticker, token)

                    if not prices:
                        continue

                    current_price = float(price_data.get("price", 0))
                    if current_price == 0:
                        continue

                    rsi = calculate_rsi(prices)
                    macd, signal, hist = calculate_macd(prices)
                    ma5 = calculate_ma(prices, 5)
                    ma20 = calculate_ma(prices, 20)

                    print(f"📊 {name}({ticker}) 현재가: {current_price:,.0f}원 | RSI: {rsi}")
                    log_monitor(ticker, name, current_price, rsi, macd, ma5, ma20)

                    # 자동 주문 체크
                    if settings.get("auto_order") == "true" and balance_cache:
                        await check_auto_order_from_cache(ticker, name, current_price, settings, token, balance_cache)

                    # 조건식 체크
                    if settings.get("semi_auto_order") == "true" or settings.get("auto_order") == "true":
                        for condition in DEFAULT_CONDITIONS:
                            alert_key = f"{ticker}_{condition['type']}"
                            is_triggered = bool(check_condition(condition, prices, current_price))

                            if is_triggered and alert_key not in alerted:
                                order_amount = int(settings.get("order_amount", 100000))
                                order_qty = max(1, int(order_amount / current_price))

                                msg = (
                                    f"🚨 <b>매수 신호 감지!</b>\n"
                                    f"종목: {name} ({ticker})\n"
                                    f"현재가: {current_price:,.0f}원\n"
                                    f"RSI: {rsi}\n"
                                    f"조건: {condition['type']} 충족!"
                                )

                                if settings.get("semi_auto_order") == "true":
                                    if settings.get("telegram_alert") == "true":
                                        send_order_confirm(ticker, name, current_price, "buy", order_qty)
                                    if settings.get("popup_alert") == "true":
                                        send_signal_popup(name, ticker, current_price, condition['type'])
                                elif settings.get("auto_order") == "true":
                                    result = buy_stock(ticker, order_qty, token)
                                    if result["success"]:
                                        notify_msg = (
                                            f"✅ <b>자동 매수 완료!</b>\n"
                                            f"종목: {name} ({ticker})\n"
                                            f"현재가: {current_price:,.0f}원\n"
                                            f"수량: {order_qty}주"
                                        )
                                        if settings.get("telegram_alert") == "true":
                                            send_message(notify_msg)
                                        if settings.get("popup_alert") == "true":
                                            send_popup(f"✅ 자동 매수!", f"{name} {order_qty}주 매수 완료!")

                                alerted.add(alert_key)
                                log_alert(ticker, name, current_price, condition['type'], msg)

                            elif not is_triggered and alert_key in alerted:
                                alerted.discard(alert_key)

                except Exception as e:
                    error_msg = f"{ticker} 처리 오류: {str(e)}"
                    print(f"❌ {error_msg}")
                    log_error("monitor", error_msg)

        except Exception as e:
            error_msg = f"모니터링 루프 오류: {str(e)}"
            print(f"❌ {error_msg}")
            log_error("monitor_loop", error_msg)

        await asyncio.sleep(60)


async def check_auto_order_from_cache(ticker, name, current_price, settings, token, balance):
    """캐시된 잔고로 익절/손절 체크"""
    try:
        if not balance.get("success"):
            return

        holdings = balance.get("holdings", [])
        holding = next((h for h in holdings if h["ticker"] == ticker), None)

        if not holding:
            return

        avg_price = float(holding["avg_price"])
        qty = int(holding["qty"])
        take_profit = float(settings.get("take_profit", 5.0))
        stop_loss = float(settings.get("stop_loss", 3.0))
        profit_rate = ((current_price - avg_price) / avg_price) * 100

        if profit_rate >= take_profit:
            alert_key = f"{ticker}_take_profit"
            if alert_key not in alerted:
                result = sell_stock(ticker, qty, token)
                if result["success"]:
                    msg = (
                        f"💰 <b>자동 익절 완료!</b>\n"
                        f"종목: {name} ({ticker})\n"
                        f"매수가: {avg_price:,.0f}원\n"
                        f"매도가: {current_price:,.0f}원\n"
                        f"수익률: +{profit_rate:.2f}%"
                    )
                    send_message(msg)
                    send_popup(f"💰 익절 완료! +{profit_rate:.2f}%", f"{name} 자동 익절 완료!")
                    log_alert(ticker, name, current_price, "자동익절", msg)
                    alerted.add(alert_key)

        elif profit_rate <= -stop_loss:
            alert_key = f"{ticker}_stop_loss"
            if alert_key not in alerted:
                result = sell_stock(ticker, qty, token)
                if result["success"]:
                    msg = (
                        f"🛑 <b>자동 손절 완료!</b>\n"
                        f"종목: {name} ({ticker})\n"
                        f"매수가: {avg_price:,.0f}원\n"
                        f"매도가: {current_price:,.0f}원\n"
                        f"손실률: {profit_rate:.2f}%"
                    )
                    send_message(msg)
                    send_popup(f"🛑 손절 완료! {profit_rate:.2f}%", f"{name} 자동 손절 완료!")
                    log_alert(ticker, name, current_price, "자동손절", msg)
                    alerted.add(alert_key)

    except Exception as e:
        log_error("auto_order", f"{ticker} 자동주문 오류: {str(e)}")


async def check_auto_order(ticker: str, name: str, current_price: float, settings: dict, token: str):
    """자동 익절/손절 체크"""
    try:
        balance = get_balance(token)
        if not balance["success"]:
            return

        holdings = balance.get("holdings", [])
        holding = next((h for h in holdings if h["ticker"] == ticker), None)

        if not holding:
            return

        avg_price = float(holding["avg_price"])
        qty = int(holding["qty"])
        take_profit = float(settings.get("take_profit", 5.0))
        stop_loss = float(settings.get("stop_loss", 3.0))

        # 수익률 계산
        profit_rate = ((current_price - avg_price) / avg_price) * 100

        # 익절 체크
        if profit_rate >= take_profit:
            alert_key = f"{ticker}_take_profit"
            if alert_key not in alerted:
                result = sell_stock(ticker, qty, token)
                if result["success"]:
                    msg = (
                        f"💰 <b>자동 익절 완료!</b>\n"
                        f"종목: {name} ({ticker})\n"
                        f"매수가: {avg_price:,.0f}원\n"
                        f"매도가: {current_price:,.0f}원\n"
                        f"수익률: +{profit_rate:.2f}%"
                    )
                    send_message(msg)
                    send_popup(f"💰 익절 완료! +{profit_rate:.2f}%", f"{name} 자동 익절 완료!")
                    log_alert(ticker, name, current_price, "자동익절", msg)
                    alerted.add(alert_key)
                    print(f"💰 자동 익절: {name} +{profit_rate:.2f}%")

        # 손절 체크
        elif profit_rate <= -stop_loss:
            alert_key = f"{ticker}_stop_loss"
            if alert_key not in alerted:
                result = sell_stock(ticker, qty, token)
                if result["success"]:
                    msg = (
                        f"🛑 <b>자동 손절 완료!</b>\n"
                        f"종목: {name} ({ticker})\n"
                        f"매수가: {avg_price:,.0f}원\n"
                        f"매도가: {current_price:,.0f}원\n"
                        f"손실률: {profit_rate:.2f}%"
                    )
                    send_message(msg)
                    send_popup(f"🛑 손절 완료! {profit_rate:.2f}%", f"{name} 자동 손절 완료!")
                    log_alert(ticker, name, current_price, "자동손절", msg)
                    alerted.add(alert_key)
                    print(f"🛑 자동 손절: {name} {profit_rate:.2f}%")

    except Exception as e:
        log_error("auto_order", f"{ticker} 자동주문 오류: {str(e)}")
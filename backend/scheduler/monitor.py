# backend/scheduler/monitor.py
import asyncio
import time
from api.stock import get_stock_price, get_stock_history, get_stock_history_long
from api.watchlist import get_tickers
from api.order import buy_stock, sell_stock, get_balance
from strategy.condition import check_condition_v2, calculate_rsi, calculate_macd, calculate_ma
from notification.telegram import send_message
from notification.popup import send_popup, send_signal_popup
from auth.token_manager import token_manager
from database.logger import log_monitor, log_alert, log_error, get_settings, get_conditions, log_trade
from shared_state import auto_buy_candidates

# 중복 알림 방지
alerted = set()

# 잔고 캐시
balance_cache = {}
balance_last_updated = 0

# 자동매수 후 추적 중인 포지션
# { ticker: { name, avg_price, qty, condition_name, bought_at } }
auto_positions = {}


async def monitor_loop():
    global balance_cache, balance_last_updated
    print("🔍 모니터링 시작!")

    import time as _time
    last_alert_clear = _time.time()

    while True:
        try:
            if _time.time() - last_alert_clear > 3600:
                alerted.clear()
                last_alert_clear = _time.time()
                print("알림기록 초기화")

            settings = get_settings()
            token = token_manager.get_token()

            # 잔고 5분마다 갱신
            if time.time() - balance_last_updated > 180:
                balance_cache = get_balance(token)
                balance_last_updated = time.time()

            # ── 1. 스캐너 후보 자동매수 처리 ──────────────────────
            if settings.get("auto_order") == "true":
                await process_auto_buy(settings, token)

            # ── 2. 보유 포지션 익절/손절 체크 ─────────────────────
            if settings.get("auto_order") == "true":
                await check_exit(settings, token)

            # ── 3. 관심종목 모니터링 (기존 기능 유지) ─────────────
            tickers = get_tickers()
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
                    macd_val, signal_val, _ = calculate_macd(prices)
                    ma5 = calculate_ma(prices, 5)
                    ma20 = calculate_ma(prices, 20)

                    print(f"📊 {name}({ticker}) 현재가: {current_price:,.0f}원 | RSI: {rsi}")
                    log_monitor(ticker, name, current_price, rsi, macd_val, ma5, ma20)

                except Exception as e:
                    log_error("monitor", f"{ticker} 처리 오류: {str(e)}")

        except Exception as e:
            log_error("monitor_loop", f"루프 오류: {str(e)}")
            print(f"❌ 모니터링 루프 오류: {e}")

        await asyncio.sleep(60)


async def process_auto_buy(settings: dict, token: str):
    """스캐너 후보 종목을 조건 재검증 후 자동매수"""
    global balance_cache, balance_last_updated
    if not auto_buy_candidates:
        return

    order_amount = int(settings.get("order_amount", 100000))

    # 현재 보유 종목 조회 (중복 매수 방지)
    balance = get_balance(token)
    holdings_tickers = []
    if balance.get("success"):
        holdings_tickers = [h["ticker"] for h in balance.get("holdings", [])]

    # 순회 중 삭제 방지를 위해 복사본으로 처리
    for candidate in auto_buy_candidates.copy():
        ticker = candidate["ticker"]
        name = candidate["name"]
        condition_id = candidate["condition_id"]
        condition_name = candidate["condition_name"]

        # 이미 보유 중이거나 이미 자동매수 추적 중이면 스킵
        if ticker in holdings_tickers or ticker in auto_positions:
            auto_buy_candidates.remove(candidate)
            print(f"⏭️ {name}({ticker}) 이미 보유 중 - 스킵")
            continue

        try:
            # 현재가 재조회 (스캔 이후 시간이 지났으므로)
            price_data = get_stock_price(ticker, token)
            current_price = float(price_data.get("price", 0))
            if current_price == 0:
                continue

            # 과거 데이터 재조회
            prices = get_stock_history_long(ticker, token)
            if not prices or len(prices) < 20:
                continue

            # 조건식 재검증
            conditions = get_conditions()
            target = next((c for c in conditions if c["id"] == condition_id), None)
            if not target:
                auto_buy_candidates.remove(candidate)
                continue

            check_results = [check_condition_v2(item, prices) for item in target["items"]]
            is_still_valid = (
                all(check_results) if target["logic"] == "AND"
                else any(check_results)
            )

            if is_still_valid:
                # ✅ 매수 실행!
                qty = max(1, int(order_amount / current_price))
                result = buy_stock(ticker, qty, token)

                if result["success"]:
                    auto_positions[ticker] = {
                        "name": name,
                        "avg_price": current_price,
                        "qty": qty,
                        "condition_name": condition_name,
                        "bought_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    msg = (
                        f"✅ <b>자동 매수 완료!</b>\n"
                        f"조건식: {condition_name}\n"
                        f"종목: {name} ({ticker})\n"
                        f"매수가: {current_price:,.0f}원\n"
                        f"수량: {qty}주\n"
                        f"총액: {current_price * qty:,.0f}원"
                    )
                    if settings.get("telegram_alert") == "true":
                        send_message(msg)
                    if settings.get("popup_alert") == "true":
                        send_popup("✅ 자동 매수!", f"{name} {qty}주 매수 완료!")
                    log_alert(ticker, name, current_price, f"자동매수:{condition_name}", msg)
                    print(f"✅ 자동매수: {name}({ticker}) {qty}주 @ {current_price:,.0f}원")
                    log_trade(ticker, name, "buy", current_price, qty,
                            condition_name=condition_name, reason="자동매수")
                    global balance_cache, balance_last_updated
                    balance_cache = get_balance(token)
                    balance_last_updated = time.time()

                else:
                    print(f"❌ 매수 실패: {name}({ticker}) - {result.get('message', '')}")
            else:
                # 조건이 더 이상 충족 안 됨
                print(f"⚠️ 조건 만료: {name}({ticker}) - 매수 취소")

            # 처리 완료 후 후보 목록에서 제거
            auto_buy_candidates.remove(candidate)

        except Exception as e:
            log_error("auto_buy", f"{ticker} 자동매수 오류: {str(e)}")


async def check_exit(settings: dict, token: str):
    """보유 포지션 익절/손절 체크 - 실제 잔고 기반"""
    global balance_cache, balance_last_updated
    take_profit = float(settings.get("take_profit", 5.0))
    stop_loss = float(settings.get("stop_loss", 3.0))

    # ✅ auto_positions 대신 실제 잔고에서 보유종목 조회
    balance = get_balance(token)
    if not balance.get("success"):
        return

    holdings = balance.get("holdings", [])
    if not holdings:
        return

    for holding in holdings:
        ticker = holding["ticker"]
        name = holding["name"]
        qty = int(holding["qty"])
        avg_price = float(holding["avg_price"])

        try:
            price_data = get_stock_price(ticker, token)
            current_price = float(price_data.get("price", 0))
            if current_price == 0:
                continue

            profit_rate = ((current_price - avg_price) / avg_price) * 100

            should_sell = False
            reason = ""
            emoji = ""

            if profit_rate >= take_profit:
                should_sell = True
                reason = f"익절 (+{profit_rate:.2f}%)"
                emoji = "💰"
            elif profit_rate <= -stop_loss:
                should_sell = True
                reason = f"손절 ({profit_rate:.2f}%)"
                emoji = "🛑"

            if should_sell:
                alert_key = f"{ticker}_exit_{round(profit_rate, 1)}"
                if alert_key in alerted:
                    continue

                result = sell_stock(ticker, qty, token)
                if result["success"]:
                    msg = (
                        f"{emoji} <b>자동 {reason}!</b>\n"
                        f"종목: {name} ({ticker})\n"
                        f"매수가: {avg_price:,.0f}원\n"
                        f"매도가: {current_price:,.0f}원\n"
                        f"수익률: {profit_rate:+.2f}%\n"
                        f"수량: {qty}주"
                    )
                    if settings.get("telegram_alert") == "true":
                        send_message(msg)
                    if settings.get("popup_alert") == "true":
                        send_popup(f"{emoji} {reason}!", f"{name} 자동 매도 완료!")
                    log_alert(ticker, name, current_price, f"자동매도:{reason}", msg)
                    log_trade(ticker, name, "sell", current_price, qty,
                              profit_rate=round(profit_rate, 2),
                              reason="익절" if profit_rate > 0 else "손절")
                    print(f"{emoji} 자동매도: {name}({ticker}) {reason}")
                    alerted.add(alert_key)

                    balance_cache = get_balance(token)
                    balance_last_updated = time.time()

                    # auto_positions에서도 제거
                    if ticker in auto_positions:
                        del auto_positions[ticker]

        except Exception as e:
            log_error("auto_exit", f"{ticker} 익절/손절 오류: {str(e)}")
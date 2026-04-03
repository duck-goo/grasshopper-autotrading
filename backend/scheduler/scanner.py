# backend/scheduler/scanner.py
import asyncio
import time
import aiohttp
import os
from database.logger import (
    get_conditions, get_stock_list_from_db,
    is_stock_list_outdated, save_stock_list,
    log_alert, get_settings
)
from strategy.condition import check_condition_v2
from notification.telegram import send_message, send_order_confirm
from notification.popup import send_signal_popup, send_popup
from auth.token_manager import token_manager

# 스캔 결과 저장
scan_results = []
scan_status = {
    "is_running": False,
    "total": 0,
    "scanned": 0,
    "last_scan": None,
    "found": 0
}

# 중복 알림 방지
alerted_scan = set()

# 동시 요청 제한 (KIS API 제한 고려)
CONCURRENT_LIMIT = 5  # 동시에 5개씩 처리

async def fetch_stock_data(session: aiohttp.ClientSession, ticker: str, token: str) -> dict:
    """비동기 현재가 조회"""
    url = "https://openapivts.koreainvestment.com:29443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "FHKST01010100"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker
    }
    # ✅ 수정 - 에러 내용 출력
    try:
        async with session.get(url, headers=headers, params=params) as res:
            data = await res.json()
            output = data.get("output", {})
            price = float(output.get("stck_prpr", 0))
            return {
                "ticker": ticker,
                "price": price,
                "change_rate": output.get("prdy_ctrt", "0"),
                "volume": int(output.get("acml_vol", 0)),
                "success": price > 0
            }
    except Exception as e:
        print(f"❌ fetch_stock_data 오류 ({ticker}): {e}")  # ✅ 에러 내용 출력
        return {"ticker": ticker, "price": 0, "success": False}

async def fetch_history(session: aiohttp.ClientSession, ticker: str, token: str) -> list:
    """비동기 과거 데이터 조회"""
    from datetime import datetime, timedelta
    url = "https://openapivts.koreainvestment.com:29443/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "FHKST03010100"
    }
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=150)).strftime("%Y%m%d")
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_DATE_1": start_date,
        "FID_INPUT_DATE_2": end_date,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0"
    }
    try:
        async with session.get(url, headers=headers, params=params) as res:
            data = await res.json()
            output = data.get("output2", [])
            result = []
            for item in reversed(output):
                if item.get("stck_clpr") and item.get("stck_clpr") != "0":
                    result.append({
                        "date": item.get("stck_bsop_date"),
                        "open": float(item.get("stck_oprc", 0)),
                        "high": float(item.get("stck_hgpr", 0)),
                        "low": float(item.get("stck_lwpr", 0)),
                        "close": float(item.get("stck_clpr", 0)),
                        "volume": int(item.get("acml_vol", 0))
                    })
            return result
    except:
        return []
    
async def fetch_intraday(session: aiohttp.ClientSession, ticker: str, token: str, minutes: str) -> list:
    """분봉 데이터 조회 (1/5/15/30/60분봉)"""
    url = "https://openapivts.koreainvestment.com:29443/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "FHKST03010200"
    }
    params = {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_HOUR_1": minutes,  # "1", "5", "15", "30", "60"
        "FID_PW_DATA_INCU_YN": "Y"
    }
    try:
        async with session.get(url, headers=headers, params=params) as res:
            data = await res.json()
            output = data.get("output2", [])
            result = []
            for item in reversed(output):
                if item.get("stck_clpr") and item.get("stck_clpr") != "0":
                    result.append({
                        "date": item.get("stck_bsop_date", "") + item.get("stck_cntg_hour", ""),
                        "open":   float(item.get("stck_oprc", 0)),
                        "high":   float(item.get("stck_hgpr", 0)),
                        "low":    float(item.get("stck_lwpr", 0)),
                        "close":  float(item.get("stck_clpr", 0)),
                        "volume": int(item.get("cntg_vol", 0))
                    })
            return result
    except Exception as e:
        return []

async def scan_stock(session: aiohttp.ClientSession, stock: dict,
                     conditions: list, token: str, semaphore: asyncio.Semaphore):
    """단일 종목 스캔"""
    global scan_results

    async with semaphore:
        ticker = stock["ticker"]
        name = stock["name"]
        market = stock["market"]

        try:
            price_data = await fetch_stock_data(session, ticker, token)
            current_price = price_data["price"]

            if current_price == 0:
                return

            for condition in conditions:                          # ✅ for condition 루프 시작
                # 시장 필터
                if condition["market"] != "ALL" and condition["market"] != market:
                    continue
                # 가격 필터
                if current_price < condition["min_price"]:
                    continue
                if condition["max_price"] > 0 and current_price > condition["max_price"]:
                    continue

                # ✅ 아래 전부 for condition 루프 안 (들여쓰기 8칸)
                timeframe_cache = {}
                check_results = []

                for item in condition["items"]:                   # ✅ for item 루프 시작
                    timeframe = item.get("timeframe", "D")
                    item_type = item["type"]

                    needs_history = item_type in [
                        "RSI", "MACD", "MA_CROSS", "MA",
                        "BOLLINGER", "VOLUME_RATIO", "HIGH_52W", "LOW_52W"
                    ]

                    if needs_history:
                        if timeframe not in timeframe_cache:
                            if timeframe == "D":
                                tf_data = await fetch_history(session, ticker, token)
                            else:
                                tf_data = await fetch_intraday(session, ticker, token, timeframe)
                            timeframe_cache[timeframe] = tf_data

                        tf_data = timeframe_cache[timeframe]
                        if not tf_data or len(tf_data) < 5:
                            check_results.append(False)
                            continue
                        check_results.append(check_condition_v2(item, tf_data))
                    else:
                        realtime_data = [{
                            "close":       current_price,
                            "volume":      price_data["volume"],
                            "open":        current_price,
                            "high":        current_price,
                            "low":         current_price,
                            "date":        "",
                            "change_rate": price_data.get("change_rate", "0")
                        }]
                        check_results.append(check_condition_v2(item, realtime_data))
                                                                  # ✅ for item 루프 끝

                # ✅ is_match는 for item 루프 밖, for condition 루프 안
                if not check_results:
                    continue
                is_match = all(check_results) if condition["logic"] == "AND" else any(check_results)

                if is_match:
                    alert_key = f"scan_{ticker}_{condition['id']}"
                    scan_results.append({
                        "ticker":         ticker,
                        "name":           name,
                        "market":         market,
                        "price":          current_price,
                        "condition_id":   condition["id"],
                        "condition_name": condition["name"],
                        "change_rate":    price_data.get("change_rate", "0"),
                    })
                    scan_status["found"] += 1

                    # 자동매수 후보 추가
                    from shared_state import auto_buy_candidates
                    settings = get_settings()
                    if settings.get("auto_order") == "true":
                        already_added = any(
                            c["ticker"] == ticker and c["condition_id"] == condition["id"]
                            for c in auto_buy_candidates
                        )
                        if not already_added:
                            auto_buy_candidates.append({
                                "ticker":         ticker,
                                "name":           name,
                                "market":         market,
                                "price":          current_price,
                                "condition_id":   condition["id"],
                                "condition_name": condition["name"],
                                "added_at":       time.strftime("%Y-%m-%d %H:%M:%S"),
                            })
                            print(f"🎯 자동매수 후보 추가: {name}({ticker}) - {condition['name']}")

                    if alert_key not in alerted_scan:
                        settings = get_settings()
                        msg = (
                            f"🔍 <b>조건검색 종목 발견!</b>\n"
                            f"조건식: {condition['name']}\n"
                            f"종목: {name} ({ticker})\n"
                            f"현재가: {current_price:,.0f}원\n"
                            f"등락률: {price_data.get('change_rate', '0')}%"
                        )
                        if settings.get("telegram_alert") == "true":
                            send_message(msg)
                        if settings.get("popup_alert") == "true":
                            send_signal_popup(name, ticker, current_price, condition["name"])
                        log_alert(ticker, name, current_price,
                                  f"조건검색:{condition['name']}", msg)
                        alerted_scan.add(alert_key)
                        print(f"✅ 조건 충족: {name}({ticker}) - {condition['name']}")
                                                                  # ✅ for condition 루프 끝

        except Exception as e:
            print(f"❌ {ticker} 스캔 오류: {e}")

        finally:
            scan_status["scanned"] += 1
            if scan_status["scanned"] % 100 == 0:
                print(f"📊 스캔 진행: {scan_status['scanned']}/{scan_status['total']}")

async def run_scanner():
    """전종목 조건식 스캐너 (비동기 병렬 처리)"""
    global scan_results, scan_status, alerted_scan

    alerted_scan = set()
    conditions = get_conditions()
    if not conditions:
        print("⚠️ 활성화된 조건식이 없어요")
        return

    token = token_manager.get_token()

    if is_stock_list_outdated():
        from api.stock import get_stock_list
        from database.logger import save_stock_list
        kospi = get_stock_list("KOSPI", token)
        kosdaq = get_stock_list("KOSDAQ", token)
        all_stocks = kospi + kosdaq
        save_stock_list(all_stocks)
    else:
        all_stocks = get_stock_list_from_db()

    if not all_stocks:
        print("❌ 종목 리스트 없음")
        return

    scan_status["is_running"] = True
    scan_status["total"] = len(all_stocks)
    scan_status["scanned"] = 0
    scan_status["found"] = 0
    scan_results.clear()

    start_time = time.time()
    print(f"🔍 전종목 스캔 시작: {len(all_stocks)}개 종목 / {len(conditions)}개 조건식")

    # 비동기 세션 + 세마포어로 동시 요청 제한
    CHUNK_SIZE = 100

    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(all_stocks), CHUNK_SIZE):
            chunk = all_stocks[i:i + CHUNK_SIZE]
            tasks = [
                scan_stock(session, stock, conditions, token, semaphore)
                for stock in chunk
            ]
            await asyncio.gather(*tasks)
            await asyncio.sleep(0.1)

    elapsed = time.time() - start_time
    scan_status["is_running"] = False
    scan_status["last_scan"] = time.strftime("%Y-%m-%d %H:%M:%S")

    print(f"✅ 스캔 완료! {scan_status['found']}개 종목 발견 "
          f"(소요시간: {elapsed:.1f}초)")

# ✅ 수정 - 장중/장외 구분해서 주기 다르게
async def scanner_loop():
    """스캐너 주기적 실행"""
    print("🔍 전종목 스캐너 대기 중...")
    while True:
        try:
            from datetime import datetime
            now = datetime.now()
            is_weekday = now.weekday() < 5
            is_market_open = (
                (now.hour == 9 and now.minute >= 0) or
                (9 < now.hour < 15) or
                (now.hour == 15 and now.minute <= 30)
            )

            if is_weekday and is_market_open:
                # ✅ 장중 - 스캔 완료되면 30초 쉬고 바로 재시작 (사실상 연속 스캔)
                print("📈 장중 스캔 시작")
                await run_scanner()
                await asyncio.sleep(30)   # 30초만 쉬고 재시작

            elif is_weekday and not is_market_open:
                # 평일 장외 - 1시간마다 (종가 기준 서치)
                print("🌙 장외 스캔 시작 (종가 기준)")
                await run_scanner()
                await asyncio.sleep(3600)

            else:
                # 주말 - 3시간마다
                print("📅 주말 스캔 시작")
                await run_scanner()
                await asyncio.sleep(10800)

        except Exception as e:
            print(f"❌ 스캐너 루프 오류: {e}")
            await asyncio.sleep(60)
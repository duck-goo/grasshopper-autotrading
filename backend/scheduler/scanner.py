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
from shared_state import auto_buy_candidates
from api.stock import get_volume_rank

# 스캔 결과 저장
scan_results = []
temp_results = []
# 핫 종목 풀
hot_universe = []            # [{ticker, name, market, price}, ...]
hot_universe_updated_at = 0  # 마지막 갱신 시각 (epoch seconds)
# 양보 모드 - 다른 API가 급할 때 스캐너 잠시 멈춤
scanner_pause_until = 0 # 이 시각까지 스캐너 대기
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
CONCURRENT_LIMIT = 3  # 동시에 3개씩 처리
# 비동기 세션 + 세마포어로 동시 요청 제한
CHUNK_SIZE = 100

def request_scanner_pause(seconds: float = 2.0):
    """
    스캐너에게 양보 요청
    지정된 초 동안 새 API 호출을 멈춤
    이미 양보 중이면 더 긴 쪽으로 연장
    """
    global scanner_pause_until
    new_until = time.time() + seconds
    if new_until > scanner_pause_until:
        scanner_pause_until = new_until

def update_hot_universe(min_price: int = None,
                        max_price: int = None,
                        markets: list = None,
                        sort_by: str = None) -> int:
    """
    핫 종목 풀 갱신
    인자가 None이면 settings DB에서 기본값 읽어옴

    Args:
        min_price: 최소 현재가 (None = DB값, 0 = 제한 없음)
        max_price: 최대 현재가 (None = DB값, 0 = 제한 없음)
        markets:   스캔할 시장 리스트 (None = DB값)
        sort_by:   "amount" / "volume" (None = DB값)
    """
    global hot_universe, hot_universe_updated_at

    # ── DB에서 설정 읽기 (인자가 None인 경우만) ─────────
    settings = get_settings()

    if min_price is None:
        try:
            min_price = int(settings.get("hot_min_price", "0") or 0)
        except (ValueError, TypeError):
            min_price = 0

    if max_price is None:
        try:
            max_price = int(settings.get("hot_max_price", "0") or 0)
        except (ValueError, TypeError):
            max_price = 0

    if sort_by is None:
        sort_by = settings.get("hot_sort_by", "amount") or "amount"

    if markets is None:
        market_setting = settings.get("hot_market", "ALL") or "ALL"
        if market_setting == "KOSPI":
            markets = ["KOSPI"]
        elif market_setting == "KOSDAQ":
            markets = ["KOSDAQ"]
        else:
            markets = ["KOSPI", "KOSDAQ"]
    # ──────────────────────────────────────────────────

    token = token_manager.get_token()

    all_stocks = []
    for idx, market in enumerate(markets):
        stocks = get_volume_rank(
            token,
            market=market,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
        )
        all_stocks.extend(stocks)
        if idx < len(markets) - 1:
            time.sleep(0.5)

    # 중복 제거
    seen = set()
    merged = []
    for stock in all_stocks:
        if stock["ticker"] and stock["ticker"] not in seen:
            seen.add(stock["ticker"])
            merged.append(stock)

    hot_universe = merged
    hot_universe_updated_at = time.time()

    print(f"🔥 핫 풀 갱신 완료: {len(hot_universe)}개 종목 "
          f"(시장: {'/'.join(markets)}, 가격: {min_price:,}~{max_price:,}, 정렬: {sort_by})")
    return len(hot_universe)

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
        print(f"❌ {ticker} 시세조회 실패: {e}")
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
    global scan_results, temp_results

    async with semaphore:
        # ✅ 양보 모드 체크 - 다른 API가 처리될 때까지 대기
        while time.time() < scanner_pause_until:
            await asyncio.sleep(0.2)

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
                if condition["max_price"] and current_price > condition["max_price"]:
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
                    temp_results.append({
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

async def run_scanner(use_hot_universe: bool = False):
    """전종목 조건식 스캐너 (비동기 병렬 처리)
    use_hot_universe=True 면 핫 풀만, False 면 전종목 스캔
    """
    global scan_results, scan_status, alerted_scan, temp_results

    if scan_status["is_running"]:
        print("이미 스캔 중이다!")
        return

    alerted_scan = set()
    conditions = get_conditions()
    if not conditions:
        print("⚠️ 활성화된 조건식이 없어요")
        return

    token = token_manager.get_token()
    # 종목 리스트 결정
    if use_hot_universe:
        # 핫 풀이 비어있거나 1시간 이상 됐으면 자동 갱신
        if not hot_universe or (time.time() - hot_universe_updated_at > 3600):
            update_hot_universe(min_price=1000)
        all_stocks = hot_universe
        print(f"🔥 핫 풀 모드: {len(all_stocks)}개 종목 스캔")
    else:
        if is_stock_list_outdated():
            from api.stock import get_stock_list
            from database.logger import save_stock_list
            kospi = get_stock_list("KOSPI", token)
            kosdaq = get_stock_list("KOSDAQ", token)
            all_stocks = kospi + kosdaq
            save_stock_list(all_stocks)
        else:
            all_stocks = get_stock_list_from_db()
        print(f"🌍 전종목 모드: {len(all_stocks)}개 종목 스캔")

    if not all_stocks:
        print("❌ 종목 리스트 없음")
        return

    scan_status["is_running"] = True
    scan_status["total"] = len(all_stocks)
    scan_status["scanned"] = 0
    scan_status["found"] = 0
    scan_results.clear()
    temp_results.clear()

    start_time = time.time()
    print(f"🔍 전종목 스캔 시작: {len(all_stocks)}개 종목 / {len(conditions)}개 조건식")

    # 비동기 세션 + 배치 처리 (다른 API 요청에 숨통 트여주기)
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    BATCH_SIZE = 50  # 50개씩 끊어서 처리

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(all_stocks), BATCH_SIZE):
            batch = all_stocks[i:i + BATCH_SIZE]
            tasks = [
                scan_stock(session, stock, conditions, token, semaphore)
                for stock in batch
            ]
            await asyncio.gather(*tasks)
            # 배치 사이에 잠깐 쉬어서 다른 API 요청이 끼어들 틈을 줌
            await asyncio.sleep(0.5)

    elapsed = time.time() - start_time
    scan_results.extend(temp_results)
    scan_status["is_running"] = False
    scan_status["last_scan"] = time.strftime("%Y-%m-%d %H:%M:%S")

    print(f"✅ 스캔 완료! {scan_status['found']}개 종목 발견 "
          f"(소요시간: {elapsed:.1f}초)")   

# ✅ 수정 - 장중/장외 구분해서 주기 다르게
async def slow_scanner_loop():
    """
    전종목 스캐너 루프 (느린 루프)
    - 장중: 30분마다 1회
    - 장외: 1시간마다 1회
    - 주말: 6시간마다 1회
    """
    print("🌐 전종목 스캐너 루프 시작 (30분 주기)")

    # 서버 시작 직후 1분 대기 (다른 초기화 마무리 시간)
    await asyncio.sleep(60)

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
                print("📈 [전종목] 장중 스캔 시작")
                await run_scanner(use_hot_universe=False)
                sleep_sec = 1800   # 30분
            elif is_weekday and not is_market_open:
                print("🌙 [전종목] 장외 스캔")
                await run_scanner(use_hot_universe=False)
                sleep_sec = 3600   # 1시간
            else:
                print("📅 [전종목] 주말 스캔")
                await run_scanner(use_hot_universe=False)
                sleep_sec = 21600  # 6시간

            await asyncio.sleep(sleep_sec)

        except Exception as e:
            print(f"❌ 전종목 스캐너 루프 오류: {e}")
            await asyncio.sleep(60)


async def fast_scanner_loop():
    """
    핫풀 스캐너 루프 (빠른 루프)
    - 30초마다 1회
    - 핫풀 갱신 → 핫풀 스캔
    - 전종목 스캔이 돌고 있으면 이번 사이클은 건너뜀
    """
    print("🔥 핫풀 스캐너 루프 시작 (30초 주기)")

    # 서버 시작 직후 30초 대기 (전종목 루프와 시작 타이밍 분리)
    await asyncio.sleep(30)

    # 핫풀 갱신 주기: 매 루프마다 안 하고, 일정 주기로만
    HOT_REFRESH_INTERVAL = 600  # 10분마다 핫풀 갱신
    last_hot_refresh = 0

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

            # # 장중이 아니면 쉬기 (장외엔 핫풀 의미 없음)
            # if not (is_weekday and is_market_open):
            #     await asyncio.sleep(60)
            #     continue

            # 다른 스캔이 돌고 있으면 건너뛰기
            if scan_status["is_running"]:
                print("⏭️ [핫풀] 전종목 스캔 중 - 이번 사이클 스킵")
                await asyncio.sleep(30)
                continue

            # 10분마다 핫풀 자동 갱신
            if time.time() - last_hot_refresh > HOT_REFRESH_INTERVAL:
                print("🔄 [핫풀] 자동 갱신 중...")
                try:
                    update_hot_universe()  # DB 설정 사용
                    last_hot_refresh = time.time()
                except Exception as e:
                    print(f"⚠️ [핫풀] 갱신 실패: {e}")

            # 핫풀 스캔 실행
            if hot_universe:
                await run_scanner(use_hot_universe=True)
            else:
                print("⚠️ [핫풀] 비어있음 - 갱신 필요")

            await asyncio.sleep(30)  # 30초 주기

        except Exception as e:
            print(f"❌ 핫풀 스캐너 루프 오류: {e}")
            await asyncio.sleep(30)


# 🔄 기존 scanner_loop는 호환성 위해 두 루프 동시 실행하는 함수로
async def scanner_loop():
    """듀얼 스캐너 - 전종목 + 핫풀 동시 실행"""
    await asyncio.gather(
        slow_scanner_loop(),
        fast_scanner_loop(),
    )
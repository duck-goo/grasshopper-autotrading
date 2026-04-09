# backend/scheduler/scanner.py
import asyncio
import time
import aiohttp
import os
from database.logger import (
    get_conditions, get_stock_list_from_db,
    is_stock_list_outdated, save_stock_list,
    log_alert, get_settings,
    save_prev_close, get_prev_close_cache,
    get_stale_prev_close_tickers, get_prev_close_stats,
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
# 🛑 비상 정지 - 스캐너 완전 OFF (True=작동, False=정지)
scanner_enabled = True
# 🔥 핫풀 초기 갱신 완료 신호 (서버 시작 시 slow_scanner_loop가 이걸 기다림)
hot_pool_ready = asyncio.Event()
# 🔒 핫풀 갱신 중복 방지 플래그
hot_refresh_in_progress = False
# 📦 전일종가 갱신 상태 (UI 표시용)
prev_close_status = {
    "is_running": False,
    "total": 0,
    "done": 0,
    "failed": 0,
    "started_at": None,
    "last_update": None,
}

prev_close_filling = False

scan_status = {
    "is_running": False,
    "total": 0,
    "done": 0,
    "failed": 0,
    "started_at": None,
    "last_update": None,
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

def set_scanner_enabled(enabled: bool):
    """
    스캐너 ON/OFF 제어 (비상 정지용)
    False면 두 스캐너 루프가 다음 사이클부터 작업을 건너뜀
    """
    global scanner_enabled
    scanner_enabled = bool(enabled)
    print(f"{'✅' if enabled else '🛑'} 스캐너 {'활성화' if enabled else '비상정지'}")

def update_hot_universe(min_price: int = None,
                       max_price: int = None,
                       markets: list = None,
                       sort_by: str = None) -> int:
    """
    핫 종목 풀 갱신 (전일종가 캐시 기반 - 즉시 완료)

    이전 방식: 매번 KIS API로 전종목 현재가 조회 (느림, rate limit 문제)
    현재 방식: prev_close_refresh_loop가 백그라운드로 채워둔 캐시에서 필터링만
              → DB 조회만 하므로 즉시 완료
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

    # 캐시에서 필터링 조회 (즉시 완료)
    rows = get_prev_close_cache(
        markets=markets,
        min_price=min_price,
        max_price=max_price
    )

    if not rows:
        stats = get_prev_close_stats()
        print(f"⚠️ [핫풀] 전일종가 캐시가 비어있어요. "
              f"백그라운드 갱신 진행 상황: {stats['cached']}/{stats['total']} "
              f"(오늘 갱신: {stats['fresh']}개)")
        hot_universe = []
        hot_universe_updated_at = time.time()
        return 0

    # 정렬 (거래대금 / 거래량 / 가격순 폴백)
    if sort_by == "amount":
        rows.sort(key=lambda x: x.get("amount", 0) or 0, reverse=True)
    elif sort_by == "volume":
        rows.sort(key=lambda x: x.get("volume", 0) or 0, reverse=True)
    else:
        rows.sort(key=lambda x: x.get("prev_close", 0) or 0, reverse=True)

    hot_universe = [
        {
            "ticker": r["ticker"],
            "name":   r["name"],
            "market": r["market"],
            "price":  r["prev_close"],   # 전일 종가를 가격으로 표시
            "volume": r.get("volume", 0),
            "amount": r.get("amount", 0),
        }
        for r in rows
    ]
    hot_universe_updated_at = time.time()

    print(f"✅ 핫풀 갱신 완료: {len(hot_universe)}개 종목 "
          f"(시장: {'/'.join(markets)}, 가격: {min_price:,}~{max_price:,}, "
          f"정렬: {sort_by}, 출처: 전일종가 캐시)")
    return len(hot_universe)

async def _fetch_prev_close_one(session: aiohttp.ClientSession,
                                stock: dict,
                                token: str) -> dict:
    """
    단일 종목 전일종가 + 거래량 + 거래대금 조회 (디버그 버전)
    실패 시 상세 원인을 반환
    """
    ticker = stock.get("ticker", "")
    url = "https://openapivts.koreainvestment.com:29443/uapi/domestic-stock/v1/quotations/inquire-price"
    headers = {
        "content-type":  "application/json",
        "authorization": f"Bearer {token}",
        "appkey":        os.getenv("MOCK_APP_KEY"),
        "appsecret":     os.getenv("MOCK_APP_SECRET"),
        "tr_id":         "FHKST01010100"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD":         ticker
    }
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(url, headers=headers, params=params, timeout=timeout) as res:
            # HTTP 상태 코드 먼저 확인
            if res.status != 200:
                body_text = await res.text()
                return {
                    "success": False,
                    "error": f"HTTP {res.status}: {body_text[:200]}"
                }

            try:
                data = await res.json()
            except Exception as je:
                body_text = await res.text()
                return {
                    "success": False,
                    "error": f"JSON 파싱 실패: {je} / body: {body_text[:200]}"
                }

            # KIS API 응답 코드 체크
            rt_cd = data.get("rt_cd", "")
            if rt_cd != "0":
                return {
                    "success": False,
                    "error": f"rt_cd={rt_cd}, msg_cd={data.get('msg_cd', '')}, msg={data.get('msg1', '')}"
                }

            output = data.get("output")
            if not output:
                return {
                    "success": False,
                    "error": f"output 없음: keys={list(data.keys())}"
                }

            # 전일 종가 추출 (장중/장외에 따라 필드가 다름)
            # 1순위: stck_prdy_clpr (전일종가)
            # 2순위: stck_sdpr      (기준가 - 장중에 전일종가로 대체)
            # 3순위: stck_prpr      (현재가 - 최후 폴백, 장외이면 종가)
            prev_close = 0
            used_field = ""

            for field in ("stck_prdy_clpr", "stck_sdpr", "stck_prpr"):
                raw = output.get(field, "")
                try:
                    val = int(float(raw or 0))
                except (ValueError, TypeError):
                    val = 0
                if val > 0:
                    prev_close = val
                    used_field = field
                    break

            if prev_close <= 0:
                # 모든 필드가 0이면 디버깅용으로 주요 필드 값 로깅
                debug = {k: output.get(k, "∅") for k in (
                    "stck_prdy_clpr", "stck_sdpr", "stck_prpr", "hts_kor_isnm"
                )}
                return {
                    "success": False,
                    "error": f"all price fields empty: {debug}"
                }

            volume = int(output.get("acml_vol", 0) or 0)
            amount = int(output.get("acml_tr_pbmn", 0) or 0)

            return {
                "success":    True,
                "prev_close": prev_close,
                "volume":     volume,
                "amount":     amount,
            }

    except asyncio.TimeoutError:
        return {"success": False, "error": "timeout (10초 초과)"}
    except aiohttp.ClientError as ce:
        return {"success": False, "error": f"ClientError: {type(ce).__name__}: {ce}"}
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()[:500]}"
        }

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
                     conditions: list, token: str, semaphore: asyncio.Semaphore,
                     settings: dict):
    """단일 종목 스캔"""
    global scan_results, temp_results

    async with semaphore:
        # 🛑 비상정지 상태면 즉시 종료 (진행 중인 스캔도 빠르게 빠져나옴)
        if not scanner_enabled:
            return

        # ✅ 양보 모드 체크 - 다른 API가 처리될 때까지 대기
        while time.time() < scanner_pause_until:
            # 대기 중에도 비상정지 체크
            if not scanner_enabled:
                return
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
            update_hot_universe()  # DB 설정 사용
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

    # ✅ settings는 스캔 시작할 때 1번만 가져옴 (3584번 → 1번)
    settings_snapshot = get_settings()

    # 비동기 세션 + 배치 처리 (다른 API 요청에 숨통 트여주기)
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    BATCH_SIZE = 50  # 50개씩 끊어서 처리

    async with aiohttp.ClientSession() as session:
        for i in range(0, len(all_stocks), BATCH_SIZE):
            # 🛑 비상정지 체크 - 배치 시작 전 확인
            if not scanner_enabled:
                print("🛑 비상정지 감지 - 스캔 중단")
                break

            batch = all_stocks[i:i + BATCH_SIZE]
            tasks = [
                scan_stock(session, stock, conditions, token, semaphore, settings_snapshot)
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
    - 핫풀 초기 갱신 완료를 기다린 후에 시작 (API 대역폭 양보)
    """
    print("🌐 전종목 스캐너 루프 시작 (30분 주기)")

    # ── 🔥 핫풀 초기 갱신이 끝날 때까지 대기 (최대 10분) ──
    print("⏳ [전종목] 핫풀 초기 갱신 완료를 기다리는 중...")
    try:
        await asyncio.wait_for(hot_pool_ready.wait(), timeout=600)
        print("✅ [전종목] 핫풀 준비 완료")
    except asyncio.TimeoutError:
        print("⚠️ [전종목] 핫풀 대기 10분 초과 - 강제로 진행합니다")

    # ── 🔒 전일종가 캐시가 먼저 채워질 시간을 확보 (서버 부팅 직후) ──
    # prev_close_refresh_loop가 10초 지연 후 시작하므로, 여기서는 15초 대기
    # 그 후 prev_close_filling 플래그가 세팅될 때까지 기다림
    print("⏳ [전종목] 전일종가 루프 선점 대기 중 (15초)...")
    await asyncio.sleep(15)

    while True:
        try:
            # 🛑 비상정지 상태면 스킵
            if not scanner_enabled:
                await asyncio.sleep(10)
                continue

            # 🔒 전일종가 캐시가 채워지는 중이면 대기 (API 대역폭 양보)
            if prev_close_filling:
                print("⏸️ [전종목] 전일종가 갱신 중 - 대기")
                while prev_close_filling:
                    await asyncio.sleep(10)
                print("▶️ [전종목] 전일종가 갱신 완료 - 재개")
                # 재개 직후 잠깐 쉬어 rate limit 여유 확보
                await asyncio.sleep(3)

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
    - 서버 시작 시 즉시 핫풀 갱신 (전종목 스캔보다 먼저!)
    - 이후 10분마다 자동 갱신 + 30초마다 핫풀 스캔
    """
    print("🔥 핫풀 스캐너 루프 시작 (30초 주기)")

    # 서버 시작 직후 5초 대기 (초기 로딩 마무리)
    await asyncio.sleep(5)

    # 핫풀 갱신 주기 설정
    HOT_REFRESH_INTERVAL = 600  # 10분마다 핫풀 갱신
    last_hot_refresh = 0

    # ── 🔥 최초 1회 즉시 갱신 (전종목 스캔보다 먼저!) ──
    print("🔄 [핫풀] 초기 갱신 시작 (서버 부팅 직후, 전종목 스캔보다 우선)...")
    try:
        update_hot_universe()
        last_hot_refresh = time.time()
    except Exception as e:
        print(f"⚠️ [핫풀] 초기 갱신 실패: {e}")
    finally:
        # 성공이든 실패든 반드시 신호 발송 (slow_scanner_loop가 무한 대기하지 않게)
        hot_pool_ready.set()
        print("📣 [핫풀] 초기화 완료 신호 발송 → 전종목 루프 해제")

    while True:
        try:
            # 🛑 비상정지 상태면 스킵
            if not scanner_enabled:
                await asyncio.sleep(10)
                continue

            # 🔒 전일종가 캐시가 채워지는 중이면 대기 (API 대역폭 양보)
            if prev_close_filling:
                print("⏸️ [전종목] 전일종가 갱신 중 - 대기")
                while prev_close_filling:
                    await asyncio.sleep(10)
                print("▶️ [전종목] 전일종가 갱신 완료 - 재개")

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

async def prev_close_refresh_loop():
    """
    전일종가 캐시를 백그라운드로 채우는 루프
    - 마지막 마감(15:30) 이후 갱신 안 된 종목만 대상
    - 전종목 스캔이 돌고 있으면 그 배치가 끝날 때까지 대기
    - 호출할 때마다 request_scanner_pause로 다른 스캔에게 양보 요청
    """
    global prev_close_filling

    print("📦 전일종가 캐시 루프 시작")

    # 서버 시작 직후 잠깐 대기 (다른 초기화 마무리)
    await asyncio.sleep(10)

    while True:
        try:
            # 🛑 비상정지 체크
            if not scanner_enabled:
                await asyncio.sleep(10)
                continue

            # 종목 마스터가 비어있으면 잠시 후 재시도
            master = get_stock_list_from_db()
            if not master:
                print("📦 [전일종가] 종목 마스터가 비어있음 - 60초 후 재시도")
                await asyncio.sleep(60)
                continue

            # 갱신 필요한 종목만 조회
            stale = get_stale_prev_close_tickers()

            if not stale:
                stats = get_prev_close_stats()
                print(f"📦 [전일종가] 모두 신선함 ({stats['fresh']}/{stats['total']}) - 1시간 후 재확인")
                prev_close_filling = False
                await asyncio.sleep(3600)
                continue

            # 갱신이 필요한 상태 - 플래그 ON (전종목 스캔에게 대기하라고 알림)
            prev_close_filling = True

            total = len(stale)
            est_min = total * 0.75 / 60
            print(f"📦 [전일종가] 갱신 시작: {total}개 종목 (예상 소요: 약 {est_min:.1f}분)")
            print(f"📦 [전일종가] 갱신 동안 전종목 스캔은 대기합니다")

            # 현재 전종목 스캔이 돌고 있으면 완료까지 대기
            if scan_status["is_running"]:
                print("📦 [전일종가] 전종목 스캔 완료 대기 중...")
                while scan_status["is_running"]:
                    await asyncio.sleep(2)
                print("📦 [전일종가] 전종목 스캔 완료 - 갱신 시작")

            prev_close_status["is_running"] = True
            prev_close_status["total"] = total
            prev_close_status["done"] = 0
            prev_close_status["failed"] = 0
            prev_close_status["started_at"] = time.time()

            token = token_manager.get_token()

            token = token_manager.get_token()

            async def _run_batch(targets: list, label: str) -> list:
                """targets를 순회하며 갱신, 실패한 종목 리스트 반환"""
                failed_list = []
                async with aiohttp.ClientSession() as session:
                    for idx, stock in enumerate(targets):
                        # 🛑 비상정지 체크
                        if not scanner_enabled:
                            print(f"🛑 [전일종가:{label}] 비상정지 - 중단")
                            break

                        # 다른 스캔에 양보 요청
                        request_scanner_pause(1.5)

                        result = await _fetch_prev_close_one(session, stock, token)

                        if result.get("success"):
                            save_prev_close(
                                stock["ticker"],
                                stock.get("name", ""),
                                stock.get("market", ""),
                                result["prev_close"],
                                result.get("volume", 0),
                                result.get("amount", 0),
                            )
                            prev_close_status["done"] += 1
                        else:
                            failed_list.append(stock)
                            prev_close_status["failed"] += 1
                            # 초반 샘플 출력
                            if prev_close_status["failed"] <= 3:
                                err = result.get("error", "unknown")
                                print(f"  ❌ [전일종가:{label}] {stock['ticker']}: {err}")

                        prev_close_status["last_update"] = time.time()

                        # 진행 로그 (50개마다)
                        if (idx + 1) % 50 == 0:
                            elapsed_inner = time.time() - prev_close_status["started_at"]
                            print(f"  [전일종가:{label}] {idx+1}/{len(targets)} 진행 "
                                  f"(누적 성공: {prev_close_status['done']}, "
                                  f"누적 실패: {prev_close_status['failed']}, "
                                  f"경과: {elapsed_inner:.0f}초)")

                        # 안전 페이스
                        await asyncio.sleep(0.75)

                return failed_list

            # ── 1차 실행 ──
            failed_round1 = await _run_batch(stale, "1차")

            # ── 2차 재시도 (1차 실패분만) ──
            if failed_round1 and scanner_enabled:
                # 재시도 전 잠깐 휴식 (API 쿨다운)
                print(f"🔁 [전일종가] 1차 완료, 실패 {len(failed_round1)}개 재시도 전 "
                      f"10초 휴식...")
                await asyncio.sleep(10)
                # 재시도는 실패 카운트 일시 리셋해서 재집계 가능하게
                retry_before_failed = prev_close_status["failed"]
                prev_close_status["failed"] = 0

                failed_round2 = await _run_batch(failed_round1, "2차재시도")

                # 2차 실패는 prev_close_status["failed"]에 이미 집계됨
                # 1차 성공분은 그대로 두고, 2차에서 구제된 개수만큼 총 실패 감소
                rescued = len(failed_round1) - len(failed_round2)
                prev_close_status["failed"] = retry_before_failed - rescued

                print(f"🔁 [전일종가] 재시도 결과: {rescued}개 구제, "
                      f"{len(failed_round2)}개 최종 실패")

                # ── 3차 재시도 (2차도 실패한 종목만, 마지막 기회) ──
                if failed_round2 and scanner_enabled:
                    print(f"🔁 [전일종가] 최종 재시도 전 20초 휴식...")
                    await asyncio.sleep(20)

                    retry_before_failed = prev_close_status["failed"]
                    prev_close_status["failed"] = 0
                    failed_round3 = await _run_batch(failed_round2, "3차최종")
                    rescued3 = len(failed_round2) - len(failed_round3)
                    prev_close_status["failed"] = retry_before_failed - rescued3

                    print(f"🔁 [전일종가] 최종 재시도 결과: {rescued3}개 구제, "
                          f"{len(failed_round3)}개 최종 실패")

            elapsed = time.time() - prev_close_status["started_at"]
            print(f"✅ [전일종가] 갱신 완료: 성공 {prev_close_status['done']}개, "
                  f"실패 {prev_close_status['failed']}개 (소요: {elapsed/60:.1f}분)")

            prev_close_status["is_running"] = False
            prev_close_filling = False

            # 갱신 완료 후 핫풀도 즉시 갱신
            try:
                update_hot_universe()
            except Exception as e:
                print(f"⚠️ [핫풀] 자동 재갱신 실패: {e}")

            # 다음 체크까지 1시간 대기
            await asyncio.sleep(3600)

        except Exception as e:
            print(f"❌ [전일종가] 루프 오류: {e}")
            prev_close_status["is_running"] = False
            prev_close_filling = False
            await asyncio.sleep(60)

# 🔄 기존 scanner_loop는 호환성 위해 두 루프 동시 실행하는 함수로
async def scanner_loop():
    """듀얼 스캐너 + 전일종가 캐시 루프 동시 실행"""
    await asyncio.gather(
        slow_scanner_loop(),
        fast_scanner_loop(),
        prev_close_refresh_loop(),
    )
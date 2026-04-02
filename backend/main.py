# backend/main.py
# 표준 라이브러리
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional

# 서드파티
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 내부 모듈
from auth.token_manager import token_manager
from api.watchlist import init_db, add_ticker, get_tickers, delete_ticker
from api.stock import get_stock_price, get_stock_history, get_stock_history_long, get_stock_list
from api.order import buy_stock, sell_stock, get_balance
from api.realtime import realtime_client
from strategy.backtest import run_backtest
from strategy.ai_predictor import run_ai_prediction
from scheduler.monitor import monitor_loop
from notification.telegram import send_message, start_telegram_bot
from notification.popup import send_popup
from database.logger import (
    init_log_db, get_monitor_logs, get_alert_logs,
    init_settings_db, get_settings, update_setting,
    init_stock_list_db, save_stock_list,
    get_stock_list_from_db, is_stock_list_outdated,
    init_condition_db, save_condition, get_conditions,
    delete_condition, toggle_condition, log_alert
)
from scheduler.scanner import scanner_loop, run_scanner, scan_results, scan_status

# ---- Pydantic 모델 ----
class ConditionItem(BaseModel):
    type: str
    operator: Optional[str] = None
    value: Optional[float] = None
    extra: Optional[str] = None

class ConditionCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    logic: str = "AND"
    min_price: int = 0
    max_price: int = 9999999
    market: str = "ALL"
    items: List[ConditionItem]

# ---- 앱 초기화 ----
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()# 모니터링 백그라운드 실행
    init_log_db() # 로그 DB 초기화
    init_settings_db()
    init_stock_list_db()
    init_condition_db()
    # 모니터링 + 텔레그램 봇 동시 실행
    task1 = asyncio.create_task(monitor_loop())
    task2 = asyncio.create_task(start_telegram_bot())
    task3 = asyncio.create_task(scanner_loop())
    yield
    # 서버 종료 시 모니터링 중지
    task1.cancel()
    task2.cancel()
    task3.cancel()

app = FastAPI(title="Auto Trader API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 연결된 프론트엔드 웹소켓 클라이언트 목록
connected_clients = []

@app.get("/")
def root():
    return {"status": "ok", "message": "Auto Trader 서버 실행 중!"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/auth/token")
def get_token():
    token = token_manager.get_token()
    return {"status": "ok", "token_preview": token[:20] + "..."}

# 관심종목 API
@app.get("/watchlist")
def get_watchlist():
    return {"status": "ok", "data": get_tickers()}

@app.post("/watchlist")
def add_watchlist(ticker: str, name: str, market: str = "KR"):
    add_ticker(ticker, name, market)
    return {"status": "ok", "message": f"{ticker} 추가 완료"}

@app.delete("/watchlist/{ticker_id}")
def delete_watchlist(ticker_id: int):
    delete_ticker(ticker_id)
    return {"status": "ok", "message": f"{ticker_id} 삭제 완료"}

# 현재가 조회 API
@app.get("/stock/{ticker}")
def get_price(ticker: str):
    token = token_manager.get_token()
    result = get_stock_price(ticker, token)
    return {"status": "ok", "data": result}

# 텔레그램 테스트
@app.get("/test/telegram")
def test_telegram():
    result = send_message("✅ Auto Trader 알림 테스트!")
    return {"status": "ok" if result else "fail"}

# 프론트엔드 실시간 연결용 웹소켓
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print(f"✅ 프론트엔드 WebSocket 연결됨 (총 {len(connected_clients)}개)")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print(f"🔌 WebSocket 연결 해제됨 (총 {len(connected_clients)}개)")

# 관심종목 전체 현재가 조회
@app.get("/watchlist/prices")
def get_watchlist_prices():
    token = token_manager.get_token()
    tickers = get_tickers()
    result = []
    for t in tickers:
        price_data = get_stock_price(t["ticker"], token)
        price_data["name"] = t["name"]  # ← 이 줄 추가!
        result.append(price_data)
    return {"status": "ok", "data": result}
    token = token_manager.get_token()
    tickers = get_tickers()
    result = []
    for t in tickers:
        price_data = get_stock_price(t["ticker"], token)
        result.append(price_data)
    return {"status": "ok", "data": result}

from strategy.condition import check_condition, calculate_rsi, calculate_macd, calculate_ma
from api.stock import get_stock_history

@app.get("/strategy/test/{ticker}")
def test_strategy(ticker: str):
    """조건식 테스트 - RSI, MACD, 이동평균 계산"""
    token = token_manager.get_token()
    
    # 과거 30일 가격 데이터 가져오기
    prices = get_stock_history(ticker, token)
    
    if not prices:
        return {"status": "error", "message": "가격 데이터 없음"}
    
    current_price = prices[-1]
    
    # 지표 계산
    rsi = calculate_rsi(prices)
    macd, signal, hist = calculate_macd(prices)
    ma5 = calculate_ma(prices, 5)
    ma20 = calculate_ma(prices, 20)
    
    # 조건식 체크 예시
    rsi_buy = bool(check_condition({"type": "RSI", "operator": "<=", "value": 40}, prices, current_price))
    macd_buy = bool(check_condition({"type": "MACD"}, prices, current_price))
    ma_cross = bool(check_condition({"type": "MA_CROSS", "short": 5, "long": 20}, prices, current_price))

    return {
        "status": "ok",
        "ticker": ticker,
        "current_price": current_price,
        "indicators": {
            "RSI": rsi,
            "MACD": macd,
            "MACD_Signal": signal,
            "MA5": ma5,
            "MA20": ma20,
        },
        "conditions": {
            "RSI_40이하_매수신호": rsi_buy,
            "MACD_골든크로스": macd_buy,
            "MA5_MA20_골든크로스": ma_cross,
        }
    }

# 로그 조회 API
@app.get("/logs/monitor")
def get_monitor_log():
    return {"status": "ok", "data": get_monitor_logs()}

@app.get("/logs/alerts")
def get_alert_log():
    return {"status": "ok", "data": get_alert_logs()}

from notification.popup import send_popup

@app.get("/test/popup")
def test_popup():
    send_popup(
        title="🤖 Auto Trader",
        message="팝업 알림 테스트 성공!"
    )
    return {"status": "ok"}

# 설정 API
@app.get("/settings")
def get_all_settings():
    return {"status": "ok", "data": get_settings()}

@app.post("/settings")
def update_settings(key: str, value: str):
    update_setting(key, value)
    return {"status": "ok", "message": f"{key} 업데이트 완료"}

# 잔고 조회
@app.get("/balance")
def get_account_balance():
    token = token_manager.get_token()
    result = get_balance(token)
    return {"status": "ok", "data": result}

# 매수 주문
@app.post("/order/buy")
def order_buy(ticker: str, name: str, qty: int):
    settings = get_settings()
    token = token_manager.get_token()

    result = buy_stock(ticker, qty, token)

    if result["success"]:
        msg = (
            f"✅ <b>매수 체결 완료!</b>\n"
            f"종목: {name} ({ticker})\n"
            f"수량: {qty}주\n"
            f"주문번호: {result['order_no']}"
        )
        # 텔레그램 알림
        if settings.get("telegram_alert") == "true":
            send_message(msg)

        # 팝업 알림
        if settings.get("popup_alert") == "true":
            send_popup(
                title=f"✅ 매수 체결 완료! - {name}",
                message=f"{name} ({ticker}) {qty}주 매수 완료!"
            )

        log_alert(ticker, name, 0, "매수체결", msg)

    return {"status": "ok" if result["success"] else "error", "data": result}

# 매도 주문
@app.post("/order/sell")
def order_sell(ticker: str, name: str, qty: int):
    settings = get_settings()
    token = token_manager.get_token()

    result = sell_stock(ticker, qty, token)

    if result["success"]:
        msg = (
            f"✅ <b>매도 체결 완료!</b>\n"
            f"종목: {name} ({ticker})\n"
            f"수량: {qty}주\n"
            f"주문번호: {result['order_no']}"
        )
        if settings.get("telegram_alert") == "true":
            send_message(msg)

        if settings.get("popup_alert") == "true":
            send_popup(
                title=f"✅ 매도 체결 완료! - {name}",
                message=f"{name} ({ticker}) {qty}주 매도 완료!"
            )

        log_alert(ticker, name, 0, "매도체결", msg)

    return {"status": "ok" if result["success"] else "error", "data": result}

# 백테스트 API
@app.get("/backtest/{ticker}")
def backtest(
    ticker: str,
    condition_type: str = "RSI",
    condition_value: float = 30,
    take_profit: float = 5.0,
    stop_loss: float = 3.0,
    order_amount: int = 100000
):
    token = token_manager.get_token()
    data = get_stock_history_long(ticker, token)

    if not data:
        return {"status": "error", "message": "데이터 조회 실패"}

    result = run_backtest(
        data=data,
        condition_type=condition_type,
        condition_value=condition_value,
        take_profit=take_profit,
        stop_loss=stop_loss,
        order_amount=order_amount
    )

    return {
        "status": "ok",
        "ticker": ticker,
        "data_period": f"{data[0]['date']} ~ {data[-1]['date']}",
        "total_days": len(data),
        "result": result
    }

# AI 예측 API
@app.get("/ai/predict/{ticker}")
def ai_predict(ticker: str):
    token = token_manager.get_token()
    data = get_stock_history_long(ticker, token)

    if not data:
        return {"status": "error", "message": "데이터 조회 실패"}

    result = run_ai_prediction(data)
    return {
        "status": "ok",
        "ticker": ticker,
        "result": result
    }

# 전종목 리스트 API
@app.get("/stocks/list")
def get_all_stocks(market: str = "ALL"):
    """전종목 리스트 조회 (DB 캐싱)"""
    # DB가 오래됐으면 새로 다운로드
    if is_stock_list_outdated():
        token = token_manager.get_token()
        kospi = get_stock_list("KOSPI", token)
        kosdaq = get_stock_list("KOSDAQ", token)
        all_stocks = kospi + kosdaq
        save_stock_list(all_stocks)
    else:
        all_stocks = get_stock_list_from_db()

    if market == "KOSPI":
        result = [s for s in all_stocks if s["market"] == "KOSPI"]
    elif market == "KOSDAQ":
        result = [s for s in all_stocks if s["market"] == "KOSDAQ"]
    else:
        result = all_stocks

    return {"status": "ok", "count": len(result), "data": result}

# 조건식 API
@app.get("/conditions")
def get_all_conditions():
    return {"status": "ok", "data": get_conditions()}

@app.post("/conditions")
def create_condition(body: ConditionCreate):
    items = [item.dict() for item in body.items]
    condition_id = save_condition(
        body.name, body.description, body.logic,
        body.min_price, body.max_price, body.market, items
    )
    return {"status": "ok", "id": condition_id}

@app.delete("/conditions/{condition_id}")
def remove_condition(condition_id: int):
    delete_condition(condition_id)
    return {"status": "ok"}

@app.post("/conditions/{condition_id}/toggle")
def toggle_condition_api(condition_id: int, is_active: bool):
    toggle_condition(condition_id, is_active)
    return {"status": "ok"}

# 스캐너 API
@app.get("/scanner/status")
def get_scanner_status():
    return {"status": "ok", "data": scan_status}

@app.get("/scanner/results")
def get_scanner_results():
    return {"status": "ok", "data": scan_results}

@app.post("/scanner/run")
async def run_scanner_now():
    """수동으로 즉시 스캔 실행"""
    if scan_status["is_running"]:
        return {"status": "error", "message": "이미 스캔 중이에요!"}
    asyncio.create_task(run_scanner())
    return {"status": "ok", "message": "스캔 시작!"}
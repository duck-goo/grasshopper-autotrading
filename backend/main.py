# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from auth.token_manager import token_manager
from api.watchlist import init_db, add_ticker, get_tickers, delete_ticker
from api.stock import get_stock_price
from api.realtime import realtime_client
from notification.telegram import send_message
from scheduler.monitor import monitor_loop
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 모니터링 백그라운드 실행
    task = asyncio.create_task(monitor_loop())
    yield
    # 서버 종료 시 모니터링 중지
    task.cancel()

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
# backend/api/realtime.py
import websockets
import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "ws://ops.koreainvestment.com:21000"

class RealtimeClient:
    def __init__(self):
        self.app_key = os.getenv("MOCK_APP_KEY")
        self.app_secret = os.getenv("MOCK_APP_SECRET")
        self.websocket = None
        self.is_running = False
        self.subscribers = {}  # ticker: callback 함수

    async def connect(self):
        """웹소켓 연결"""
        try:
            self.websocket = await websockets.connect(BASE_URL)
            self.is_running = True
            print("✅ 실시간 웹소켓 연결 성공")
        except Exception as e:
            print(f"❌ 웹소켓 연결 실패: {e}")

    async def subscribe(self, ticker: str, callback):
        """종목 실시간 시세 구독"""
        if not self.websocket:
            await self.connect()

        # 구독 요청 메시지
        message = {
            "header": {
                "approval_key": await self._get_approval_key(),
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",  # 실시간 체결가
                    "tr_key": ticker
                }
            }
        }

        await self.websocket.send(json.dumps(message))
        self.subscribers[ticker] = callback
        print(f"✅ {ticker} 실시간 구독 시작")

    async def _get_approval_key(self):
        """웹소켓 접속키 발급"""
        import aiohttp
        url = "https://openapivts.koreainvestment.com:29443/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body) as res:
                data = await res.json()
                return data.get("approval_key")

    async def listen(self):
        """실시간 데이터 수신"""
        while self.is_running:
            try:
                data = await self.websocket.recv()
                await self._process(data)
            except Exception as e:
                print(f"❌ 수신 오류: {e}")
                self.is_running = False

    async def _process(self, data: str):
        """수신 데이터 처리"""
        try:
            # PINGPONG 처리
            if data == "PINGPONG":
                await self.websocket.send("PONG")
                return

            # JSON 데이터 처리
            parsed = json.loads(data)
            ticker = parsed.get("body", {}).get("input", {}).get("tr_key")

            if ticker and ticker in self.subscribers:
                await self.subscribers[ticker](parsed)

        except json.JSONDecodeError:
            # 실시간 체결 데이터는 | 구분자 형식
            self._process_raw(data)

    def _process_raw(self, data: str):
        """실시간 체결 데이터 파싱 (| 구분자)"""
        try:
            parts = data.split("|")
            if len(parts) >= 4:
                values = parts[3].split("^")
                ticker = values[0]
                price = values[2]
                print(f"📊 {ticker}: {int(price):,}원")
        except Exception as e:
            print(f"파싱 오류: {e}")

# 전역 클라이언트
realtime_client = RealtimeClient()
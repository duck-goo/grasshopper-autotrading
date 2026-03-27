import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class TokenManager:
    def __init__(self):
        self.app_key = os.getenv("MOCK_APP_KEY")
        self.app_secret = os.getenv("MOCK_APP_SECRET")
        self.base_url = "https://openapivts.koreainvestment.com:29443"
        self.access_token = None
        self.token_expired_at = None

    def is_token_valid(self):
        """토큰이 유효한지 확인"""
        if not self.access_token:
            return False
        if datetime.now() >= self.token_expired_at:
            return False
        return True

    def get_token(self):
        """토큰 반환 (만료 시 자동 재발급)"""
        if not self.is_token_valid():
            self._issue_token()
        return self.access_token

    def _issue_token(self):
        """토큰 발급"""
        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret
        }
        res = requests.post(url, json=body)

        if res.status_code == 200:
            data = res.json()
            self.access_token = data["access_token"]
            # 토큰 만료시간 23시간으로 설정 (실제 24시간이지만 여유있게)
            self.token_expired_at = datetime.now() + timedelta(hours=23)
            print(f"✅ 토큰 발급 성공: {datetime.now()}")
        else:
            print(f"❌ 토큰 발급 실패: {res.status_code}")
            raise Exception("토큰 발급 실패")

# 전역에서 하나만 사용
token_manager = TokenManager()
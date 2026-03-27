import requests
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

APP_KEY = os.getenv("MOCK_APP_KEY")
APP_SECRET = os.getenv("MOCK_APP_SECRET")
ACCOUNT = os.getenv("MOCK_ACCOUNT")

print("=" * 40)
print("🔑 앱키 로드 확인")
print(f"APP_KEY: {APP_KEY[:10]}...")
print(f"ACCOUNT: {ACCOUNT}")
print("=" * 40)

# 모의투자 토큰 발급
url = "https://openapivts.koreainvestment.com:29443/oauth2/tokenP"

body = {
    "grant_type": "client_credentials",
    "appkey": APP_KEY,
    "appsecret": APP_SECRET
}

print("\n📡 토큰 발급 요청 중...")
res = requests.post(url, json=body)

if res.status_code == 200:
    token = res.json()["access_token"]
    print(f"✅ 토큰 발급 성공!")
    print(f"TOKEN: {token[:20]}...")
else:
    print(f"❌ 실패: {res.status_code}")
    print(res.json())
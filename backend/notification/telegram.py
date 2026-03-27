# backend/notification/telegram.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_message(message: str):
    """텔레그램 메시지 전송"""
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ 텔레그램 설정이 없습니다")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }

    res = requests.post(url, json=payload)

    if res.status_code == 200:
        print(f"✅ 텔레그램 전송 성공")
        return True
    else:
        print(f"❌ 텔레그램 전송 실패: {res.text}")
        return False

def send_price_alert(ticker: str, name: str, price: str, change_rate: str):
    """시세 알림 전송"""
    emoji = "📈" if float(change_rate) >= 0 else "📉"
    message = (
        f"{emoji} <b>시세 알림</b>\n"
        f"종목: {name} ({ticker})\n"
        f"현재가: {int(price):,}원\n"
        f"등락률: {change_rate}%"
    )
    return send_message(message)
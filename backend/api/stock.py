# backend/api/stock.py
import requests
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://openapivts.koreainvestment.com:29443"

def get_stock_price(ticker: str, token: str):
    """국내 주식 현재가 조회"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"

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

    res = requests.get(url, headers=headers, params=params)

    if res.status_code == 200:
        data = res.json()
        output = data.get("output", {})
        return {
            "ticker": ticker,
            "name": output.get("hts_kor_isnm", ""),       # 종목명
            "price": output.get("stck_prpr", ""),          # 현재가
            "change": output.get("prdy_vrss", ""),         # 전일대비
            "change_rate": output.get("prdy_ctrt", ""),    # 등락률
            "volume": output.get("acml_vol", ""),          # 거래량
        }
    else:
        return {"error": res.status_code, "message": res.text}
    
def get_stock_history(ticker: str, token: str, period: int = 30) -> list:
    """국내 주식 과거 가격 조회 (종가 기준)"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-price"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "FHKST01010400"
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": "0"
    }

    res = requests.get(url, headers=headers, params=params)
    
    # 응답 전체 출력 (디버깅용)
    print(f"📊 상태코드: {res.status_code}")
    print(f"📊 응답내용: {res.text[:500]}")

    if res.status_code == 200:
        data = res.json()
        output = data.get("output", [])
        prices = [float(item["stck_clpr"]) for item in reversed(output) if item.get("stck_clpr")]
        return prices
    else:
        print(f"❌ 과거 데이터 조회 실패: {res.text}")
        return []

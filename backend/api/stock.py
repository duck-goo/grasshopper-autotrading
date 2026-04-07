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
    
    if res.status_code == 200:
        data = res.json()
        output = data.get("output", [])
        prices = [float(item["stck_clpr"]) for item in reversed(output) if item.get("stck_clpr")]
        return prices
    else:
        print(f"❌ 과거 데이터 조회 실패: {res.text}")
        return []
    
def get_stock_history_long(ticker: str, token: str) -> list:
    """국내 주식 과거 100일 가격 조회"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "FHKST03010100"
    }

    from datetime import datetime, timedelta
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

    res = requests.get(url, headers=headers, params=params)

    if res.status_code == 200:
        data = res.json()
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
    else:
        print(f"❌ 과거 데이터 조회 실패: {res.text}")
        return []

def get_stock_list(market: str, token: str) -> list:
    """코스피/코스닥 전종목 리스트 조회"""
    import zipfile
    import io
    import re

    if market == "KOSPI":
        file_url = "https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip"
    else:
        file_url = "https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip"

    try:
        res = requests.get(file_url, timeout=30)
        if res.status_code != 200:
            print(f"❌ 다운로드 실패: {res.status_code}")
            return []

        z = zipfile.ZipFile(io.BytesIO(res.content))
        data = z.read(z.namelist()[0])

        stocks = []
        try:
            lines = data.decode('euc-kr').split('\n')
        except:
            lines = data.decode('cp949').split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                # 종목코드 6자리 숫자만
                ticker = line[:6]
                if not ticker.isdigit():
                    continue

                rest = line[6:]

                # ISIN 코드(KR...) 이후 종목명 추출
                isin_match = re.search(r'KR\w{10}(.+)', rest)
                if isin_match:
                    name_raw = isin_match.group(1).strip()
                else:
                    name_raw = rest[15:].strip()

                # 한글/영문/숫자만 남기고 정리
                # 2칸 이상 공백 나오면 종목명 끝
                name = re.split(r'\s{2,}', name_raw)[0].strip()

                # 특수문자 및 불필요한 문자 제거
                name = re.sub(r'[^\w\s\(\)\.\-&]', '', name).strip()

                # 너무 짧거나 숫자만 있으면 제외
                if not name or len(name) < 1:
                    continue
                if re.match(r'^[\d\s]+$', name):
                    continue

                stocks.append({
                    "ticker": ticker,
                    "name": name,
                    "market": market
                })
            except:
                continue

        print(f"✅ {market} 종목 수: {len(stocks)}")
        return stocks

    except Exception as e:
        print(f"❌ 종목 리스트 오류: {e}")
        return []
    
def get_volume_rank(token: str,
                    market: str = "KOSPI",
                    min_price: int = 0,
                    max_price: int = 0,
                    sort_by: str = "amount") -> list:
    """
    거래대금/거래량 상위 종목 조회 (KIS 거래량 순위 API)
    한 번 호출에 한 시장에서 최대 30개 반환

    Args:
        token:     KIS 액세스 토큰
        market:    "KOSPI" 또는 "KOSDAQ"
        min_price: 최소 현재가 (원). 0이면 제한 없음
        max_price: 최대 현재가 (원). 0이면 제한 없음
        sort_by:   "amount" = 거래대금 순 (기본)
                   "volume" = 거래량 순
    """
    url = f"{BASE_URL}/uapi/domestic-stock/v1/quotations/volume-rank"

    # 시장 코드
    market_code = "0001" if market == "KOSPI" else "1001"

    # 정렬 기준 코드 (KIS API 문서 기준)
    # 0 = 평균거래량, 1 = 거래증가율, 2 = 평균거래회전율,
    # 3 = 거래금액순, 4 = 평균거래금액회전율
    sort_code = "3" if sort_by == "amount" else "0"

    headers = {
        "content-type":  "application/json",
        "authorization": f"Bearer {token}",
        "appkey":        os.getenv("MOCK_APP_KEY"),
        "appsecret":     os.getenv("MOCK_APP_SECRET"),
        "tr_id":         "FHPST01710000",
    }

    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_COND_SCR_DIV_CODE":  "20171",
        "FID_INPUT_ISCD":         market_code,
        "FID_DIV_CLS_CODE":       "0",            # 0 = 전체
        "FID_BLNG_CLS_CODE":      sort_code,      # ✅ 정렬 기준
        "FID_TRGT_CLS_CODE":      "111111111",
        "FID_TRGT_EXLS_CLS_CODE": "0000000000",
        "FID_INPUT_PRICE_1":      str(min_price) if min_price > 0 else "",
        "FID_INPUT_PRICE_2":      str(max_price) if max_price > 0 else "",
        "FID_VOL_CNT":            "",
        "FID_INPUT_DATE_1":       ""
    }

    try:
        res = requests.get(url, headers=headers, params=params, timeout=10)
        data = res.json()

        if data.get("rt_cd") != "0":
            print(f"❌ {market} 거래량 순위 실패: {data.get('msg1')}")
            return []

        output = data.get("output", [])
        result = []
        for item in output:
            try:
                price = int(item.get("stck_prpr", 0) or 0)

                # ✅ API가 필터를 무시하는 경우를 대비한 이중 안전망
                if min_price > 0 and price < min_price:
                    continue
                if max_price > 0 and price > max_price:
                    continue

                result.append({
                    "ticker": item.get("mksc_shrn_iscd"),
                    "name":   item.get("hts_kor_isnm"),
                    "market": market,
                    "price":  price,
                })
            except (ValueError, TypeError):
                continue

        print(f"✅ {market} {sort_by} 상위 {len(result)}개 "
              f"(가격: {min_price:,}~{max_price:,}원)")
        return result

    except Exception as e:
        print(f"❌ {market} 거래량 순위 예외: {e}")
        return []
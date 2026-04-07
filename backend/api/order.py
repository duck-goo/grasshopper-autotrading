# backend/api/order.py
import requests
import os
import time as time_module
from dotenv import load_dotenv
from database.logger import log_error

load_dotenv()

BASE_URL = "https://openapivts.koreainvestment.com:29443"  # 모의투자

def buy_stock(ticker: str, qty: int, token: str) -> dict:
    """국내 주식 매수 주문"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "VTTC0802U",  # 모의투자 매수
        "custtype": "P"
    }

    body = {
        "CANO": os.getenv("MOCK_ACCOUNT").split("-")[0],       # 계좌번호
        "ACNT_PRDT_CD": os.getenv("MOCK_ACCOUNT").split("-")[1],  # 상품코드
        "PDNO": ticker,           # 종목코드
        "ORD_DVSN": "01",         # 시장가 주문
        "ORD_QTY": str(qty),      # 주문수량
        "ORD_UNPR": "0",          # 시장가는 0
    }

    try:
        res = requests.post(url, headers=headers, json=body)
        data = res.json()

        if data.get("rt_cd") == "0":
            print(f"✅ 매수 주문 성공: {ticker} {qty}주")
            return {
                "success": True,
                "ticker": ticker,
                "qty": qty,
                "order_no": data.get("output", {}).get("ODNO", ""),
                "message": "매수 주문 완료"
            }
        else:
            msg = data.get("msg1", "알 수 없는 오류")
            print(f"❌ 매수 주문 실패: {msg}")
            log_error("order", f"매수 실패 {ticker}: {msg}")
            return {"success": False, "message": msg}

    except Exception as e:
        log_error("order", f"매수 예외 {ticker}: {str(e)}")
        return {"success": False, "message": str(e)}


def sell_stock(ticker: str, qty: int, token: str) -> dict:
    """국내 주식 매도 주문"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "VTTC0801U",  # 모의투자 매도
        "custtype": "P"
    }

    body = {
        "CANO": os.getenv("MOCK_ACCOUNT").split("-")[0],
        "ACNT_PRDT_CD": os.getenv("MOCK_ACCOUNT").split("-")[1],
        "PDNO": ticker,
        "ORD_DVSN": "01",       # 시장가
        "ORD_QTY": str(qty),
        "ORD_UNPR": "0",
    }

    try:
        res = requests.post(url, headers=headers, json=body)
        data = res.json()

        if data.get("rt_cd") == "0":
            print(f"✅ 매도 주문 성공: {ticker} {qty}주")
            return {
                "success": True,
                "ticker": ticker,
                "qty": qty,
                "order_no": data.get("output", {}).get("ODNO", ""),
                "message": "매도 주문 완료"
            }
        else:
            msg = data.get("msg1", "알 수 없는 오류")
            print(f"❌ 매도 주문 실패: {msg}")
            log_error("order", f"매도 실패 {ticker}: {msg}")
            return {"success": False, "message": msg}

    except Exception as e:
        log_error("order", f"매도 예외 {ticker}: {str(e)}")
        return {"success": False, "message": str(e)}


def get_balance(token: str) -> dict:
    """잔고 조회"""
    url = f"{BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"

    headers = {
        "content-type": "application/json",
        "authorization": f"Bearer {token}",
        "appkey": os.getenv("MOCK_APP_KEY"),
        "appsecret": os.getenv("MOCK_APP_SECRET"),
        "tr_id": "VTTC8434R",  # 모의투자 잔고
        "custtype": "P"
    }

    params = {
        "CANO": os.getenv("MOCK_ACCOUNT").split("-")[0],
        "ACNT_PRDT_CD": os.getenv("MOCK_ACCOUNT").split("-")[1],
        "AFHR_FLPR_YN": "N",
        "OFL_YN": "N",
        "INQR_DVSN": "02",
        "UNPR_DVSN": "01",
        "FUND_STTL_ICLD_YN": "N",
        "FNCG_AMT_AUTO_RDPT_YN": "N",
        "PRCS_DVSN": "01",
        "CTX_AREA_FK100": "",
        "CTX_AREA_NK100": ""
    }

    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, params=params)
            data = res.json()

            if data.get("rt_cd") == "0":
                output1 = data.get("output1", [])  # 보유종목
                output2 = data.get("output2", [{}])  # 계좌 요약

                holdings = []
                for item in output1:
                    # 문자열 → 정수 변환 후 비교 (안전)
                    try:
                        qty = int(float(item.get("hldg_qty", "0") or 0))
                    except (ValueError, TypeError):
                        qty = 0

                    if qty <= 0:
                        continue  # 수량 0 이하는 무조건 제외

                    holdings.append({
                        "ticker": item.get("pdno"),
                        "name": item.get("prdt_name"),
                        "qty": str(qty),
                        "avg_price": item.get("pchs_avg_pric"),
                        "current_price": item.get("prpr"),
                        "profit_loss": item.get("evlu_pfls_amt"),
                        "profit_rate": item.get("evlu_pfls_rt"),
                    })

                summary = output2[0] if output2 else {}
                
                def safe_int(val, default=0):
                    if val is None or val == "":
                        return default
                    try:
                        return int(str(val).replace(",","") or default)
                    except (ValueError, TypeError):
                        return default
                dnca = safe_int(summary.get("dnca_tot_amt"))
                thdt_buy = safe_int(summary.get("thdt_buy_amt"))
                available = max(0, dnca - thdt_buy)

                return {
                    "success": True,
                    "holdings": holdings,
                    "total_eval": summary.get("tot_evlu_amt", "0"),
                    "available_cash": str(available),  # ✅ 예수금 - 당일매수금액
                    "profit_loss": summary.get("evlu_pfls_smtl_amt", "0")
                }
            elif "초당 거래건수" in data.get("msg1", ""):
                print(f"⚠️ 잔고 조회 제한 - {attempt+1}번째 재시도...")
                time_module.sleep(1)  # 1초 대기 후 재시도
                continue

            else:
                return {"success": False, "message": data.get("msg1")}

        except Exception as e:
            log_error("balance", str(e))
            return {"success": False, "message": str(e)}

    return {"success": False, "message": "잔고 조회 제한 초과"}

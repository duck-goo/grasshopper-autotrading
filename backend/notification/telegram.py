# backend/notification/telegram.py
import os
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 대기 중인 주문 저장 (버튼 클릭 시 실행)
pending_orders = {}

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
    return res.status_code == 200

def send_order_confirm(ticker: str, name: str, price: float, order_type: str, qty: int):
    """매수/매도 확인 버튼 메시지 전송"""
    if not BOT_TOKEN or not CHAT_ID:
        return False

    emoji = "📈" if order_type == "buy" else "📉"
    action = "매수" if order_type == "buy" else "매도"

    # 대기 주문 저장
    order_key = f"{ticker}_{order_type}"
    pending_orders[order_key] = {
        "ticker": ticker,
        "name": name,
        "qty": qty,
        "order_type": order_type
    }

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": (
            f"{emoji} <b>{action} 신호 감지!</b>\n"
            f"종목: {name} ({ticker})\n"
            f"현재가: {price:,.0f}원\n"
            f"수량: {qty}주\n\n"
            f"{action}하시겠습니까?"
        ),
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": f"✅ 예 ({action})", "callback_data": f"confirm_{order_key}"},
                {"text": "❌ 아니오", "callback_data": f"cancel_{order_key}"}
            ]]
        }
    }
    res = requests.post(url, json=payload)
    return res.status_code == 200

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

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """텔레그램 버튼 클릭 처리"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("confirm_"):
        order_key = data.replace("confirm_", "")
        order = pending_orders.get(order_key)

        if order:
            # 주문 실행
            from auth.token_manager import token_manager
            from api.order import buy_stock, sell_stock
            from notification.popup import send_popup

            token = token_manager.get_token()

            if order["order_type"] == "buy":
                result = buy_stock(order["ticker"], order["qty"], token)
                action = "매수"
            else:
                result = sell_stock(order["ticker"], order["qty"], token)
                action = "매도"

            if result["success"]:
                msg = (
                    f"✅ <b>{action} 체결 완료!</b>\n"
                    f"종목: {order['name']} ({order['ticker']})\n"
                    f"수량: {order['qty']}주"
                )
                send_popup(f"✅ {action} 체결!", f"{order['name']} {order['qty']}주 {action} 완료!")
            else:
                msg = f"❌ {action} 실패: {result['message']}"

            await query.edit_message_text(msg, parse_mode="HTML")
            pending_orders.pop(order_key, None)

    elif data.startswith("cancel_"):
        order_key = data.replace("cancel_", "")
        pending_orders.pop(order_key, None)
        await query.edit_message_text("❌ 주문이 취소되었습니다.")

async def start_telegram_bot():
    """텔레그램 봇 시작"""
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("🦗 쌀파먹는메뚜기 봇 시작! 🦗")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
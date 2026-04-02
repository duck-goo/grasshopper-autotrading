# backend/notification/popup.py
from winotify import Notification, audio

DASHBOARD_URL = "http://localhost:3000"

def send_popup(title: str, message: str):
    """Windows 팝업 알림 전송"""
    try:
        toast = Notification(
            app_id="Auto Trader",
            title=title,
            msg=message,
            duration="short"
        )
        toast.set_audio(audio.Default, loop=False)
        # 클릭 시 대시보드 오픈
        toast.add_actions(
            label="대시보드 열기",
            launch=DASHBOARD_URL
        )
        toast.show()
        print(f"✅ 팝업 알림 전송: {title}")
        return True
    except Exception as e:
        print(f"❌ 팝업 알림 실패: {e}")
        return False

def send_signal_popup(name: str, ticker: str, price: float, condition: str):
    """매매 신호 팝업 알림"""
    send_popup(
        title=f"🚨 매매 신호! - {name}",
        message=f"{name} ({ticker})\n현재가: {price:,.0f}원\n조건: {condition} 충족!\n클릭하면 대시보드로 이동해요"
    )

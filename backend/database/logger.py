# backend/database/logger.py
import sqlite3
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "auto_trader.db")

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_log_db():
    """로그 테이블 초기화"""
    conn = get_db()
    
    # 모니터링 로그
    conn.execute("""
        CREATE TABLE IF NOT EXISTS monitor_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            name TEXT,
            price REAL,
            rsi REAL,
            macd REAL,
            ma5 REAL,
            ma20 REAL,
            created_at TEXT
        )
    """)

    # 알림 로그
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            name TEXT,
            price REAL,
            condition_type TEXT,
            message TEXT,
            created_at TEXT
        )
    """)

    # 오류 로그
    conn.execute("""
        CREATE TABLE IF NOT EXISTS error_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT,
            message TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()
    print("✅ 로그 DB 초기화 완료")

def log_monitor(ticker: str, name: str, price: float, rsi: float, macd: float, ma5: float, ma20: float):
    """모니터링 로그 저장"""
    conn = get_db()
    conn.execute(
        """INSERT INTO monitor_log 
        (ticker, name, price, rsi, macd, ma5, ma20, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, name, price, rsi, macd, ma5, ma20, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def log_alert(ticker: str, name: str, price: float, condition_type: str, message: str):
    """알림 로그 저장"""
    conn = get_db()
    conn.execute(
        """INSERT INTO alert_log 
        (ticker, name, price, condition_type, message, created_at) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (ticker, name, price, condition_type, message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def log_error(module: str, message: str):
    """오류 로그 저장"""
    conn = get_db()
    conn.execute(
        "INSERT INTO error_log (module, message, created_at) VALUES (?, ?, ?)",
        (module, message, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_monitor_logs(limit: int = 50) -> list:
    """모니터링 로그 조회"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM monitor_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_alert_logs(limit: int = 50) -> list:
    """알림 로그 조회"""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM alert_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def init_settings_db():
    """설정 테이블 초기화"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # 기본값 설정
    defaults = [
        ("telegram_alert", "true"),
        ("popup_alert", "true"),
        ("semi_auto_order", "true"),
        ("auto_order", "false"),
        ("order_amount", "100000"),
        ("take_profit", "5.0"),
        ("stop_loss", "3.0"),
        ("hot_min_price", "10000"),
        ("hot_max_price", "0"),
        ("hot_market", "ALL"),
        ("hot_sort_by", "amount"),
    ]
    for key, value in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
    conn.commit()
    conn.close()
    print("✅ 설정 DB 초기화 완료")

def get_settings() -> dict:
    """설정값 전체 조회"""
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}

def update_setting(key: str, value: str):
    """설정값 업데이트"""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()

def init_stock_list_db():
    """전종목 리스트 테이블 초기화"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_list (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            market TEXT,
            updated_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_stock_list(stocks: list):
    """전종목 리스트 저장"""
    conn = get_db()
    conn.execute("DELETE FROM stock_list")
    conn.executemany(
        "INSERT INTO stock_list (ticker, name, market, updated_at) VALUES (?, ?, ?, ?)",
        [(s["ticker"], s["name"], s["market"], datetime.now().isoformat()) for s in stocks]
    )
    conn.commit()
    conn.close()
    print(f"✅ 전종목 리스트 저장 완료: {len(stocks)}개")

def get_stock_list_from_db() -> list:
    """DB에서 전종목 리스트 조회"""
    conn = get_db()
    rows = conn.execute("SELECT ticker, name, market FROM stock_list").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def is_stock_list_outdated() -> bool:
    """종목 리스트 업데이트 필요 여부 (하루 1번)"""
    conn = get_db()
    row = conn.execute(
        "SELECT updated_at FROM stock_list LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return True
    from datetime import datetime
    last_updated = datetime.fromisoformat(row["updated_at"])
    return (datetime.now() - last_updated).days >= 1

def init_condition_db():
    """조건식 테이블 초기화"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conditions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            logic TEXT DEFAULT 'AND',
            min_price INTEGER DEFAULT 0,
            max_price INTEGER DEFAULT 9999999,
            market TEXT DEFAULT 'ALL',
            is_active INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS condition_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            condition_id INTEGER,
            type TEXT,
            operator TEXT,
            value REAL,
            extra TEXT,
            timeframe TEXT DEFAULT 'D',  -- ✅ 추가: D=일봉, 1/5/15/30/60=분봉
            FOREIGN KEY (condition_id) REFERENCES conditions(id)
        )
    """)

    # ✅ 기존 DB에 timeframe 컬럼 없으면 추가 (마이그레이션)
    try:
        conn.execute("ALTER TABLE condition_items ADD COLUMN timeframe TEXT DEFAULT 'D'")
        print("✅ condition_items에 timeframe 컬럼 추가")
    except:
        pass  # 이미 있으면 무시

    conn.commit()
    conn.close()
    print("✅ 조건식 DB 초기화 완료")

def save_condition(name: str, description: str, logic: str,
                   min_price: int, max_price: int,
                   market: str, items: list) -> int:
    """조건식 저장"""
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO conditions
        (name, description, logic, min_price, max_price, market, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
        (name, description, logic, min_price, max_price,
         market, datetime.now().isoformat())
    )
    condition_id = cursor.lastrowid

    for item in items:
        conn.execute(
            """INSERT INTO condition_items
            (condition_id, type, operator, value, extra, timeframe)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (condition_id, item.get("type"), item.get("operator"),
             item.get("value"), str(item.get("extra", "")),
             item.get("timeframe", "D"))  # ✅ timeframe 저장
        )

    conn.commit()
    conn.close()
    return condition_id

def get_conditions(active_only: bool = True) -> list:
    """조건식 전체 조회(active_only=True면 활성만, False면 전체)"""
    conn = get_db()
    if active_only:
        query = "SELECT * FROM conditions WHERE is_active = 1 ORDER BY created_at DESC"
    else:
        query = "SELECT * FROM conditions ORDER BY created_at DESC"
    rows = conn.execute(query).fetchall()
    conditions = []
    for row in rows:
        cond = dict(row)
        items = conn.execute(
            "SELECT * FROM condition_items WHERE condition_id = ?",
            (cond["id"],)
        ).fetchall()
        cond["items"] = [dict(i) for i in items]
        conditions.append(cond)
    conn.close()
    return conditions

def delete_condition(condition_id: int):
    """조건식 삭제"""
    conn = get_db()
    conn.execute("DELETE FROM condition_items WHERE condition_id = ?", (condition_id,))
    conn.execute("DELETE FROM conditions WHERE id = ?", (condition_id,))
    conn.commit()
    conn.close()

def toggle_condition(condition_id: int, is_active: bool):
    """조건식 활성/비활성 토글"""
    conn = get_db()
    conn.execute(
        "UPDATE conditions SET is_active = ? WHERE id = ?",
        (1 if is_active else 0, condition_id)
    )
    conn.commit()
    conn.close()

def init_trade_db():
    """매매 이력 테이블 초기화"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            name TEXT,
            trade_type TEXT,      -- 'buy' / 'sell'
            price REAL,
            qty INTEGER,
            amount REAL,
            condition_name TEXT,
            profit_rate REAL,     -- 매도 시 수익률 (매수는 NULL)
            reason TEXT,          -- '자동매수', '익절', '손절'
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_trade(ticker, name, trade_type, price, qty, condition_name="", profit_rate=None, reason=""):
    conn = get_db()
    conn.execute(
        """INSERT INTO trade_log 
        (ticker, name, trade_type, price, qty, amount, condition_name, profit_rate, reason, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ticker, name, trade_type, price, qty, price*qty,
         condition_name, profit_rate, reason, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_trade_logs(limit=100):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM trade_log ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
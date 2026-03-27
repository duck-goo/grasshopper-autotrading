# backend/api/watchlist.py
import sqlite3
import os
from datetime import datetime

# 현재 파일 기준으로 절대경로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "auto_trader.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """DB 테이블 초기화"""
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            name TEXT,
            market TEXT DEFAULT 'KR',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("✅ DB 초기화 완료")

def add_ticker(ticker: str, name: str, market: str = "KR"):
    """관심종목 추가"""
    conn = get_db()
    conn.execute(
        "INSERT INTO watchlist (ticker, name, market, created_at) VALUES (?, ?, ?, ?)",
        (ticker, name, market, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_tickers():
    """관심종목 전체 조회"""
    conn = get_db()
    rows = conn.execute("SELECT * FROM watchlist").fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_ticker(ticker_id: int):
    """관심종목 삭제"""
    conn = get_db()
    conn.execute("DELETE FROM watchlist WHERE id = ?", (ticker_id,))
    conn.commit()
    conn.close()
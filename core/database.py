"""
core/database.py — SQLite3 주문 통계 데이터베이스
================================================
계획서 3장 데이터베이스 항목 구현.

테이블 구조
  orders   : 판매 통계(요일·시간대별 트렌드 분석용 — 계획서 6장 확장성)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from config import DB_PATH


class KioskDatabase:
    """주문 통계를 관리하는 데이터베이스 클래스(OOP 설계)."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        # 여러 스레드(비전/UI)가 같이 접근하므로 잠금장치(Lock)로 안전하게 보호합니다.
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    # ──────────────────────────────────────────
    # 테이블 생성
    # ──────────────────────────────────────────
    def _create_tables(self) -> None:
        with self._lock:
            cur = self._conn.cursor()
            # 이전 버전에서 만들어진 단골 테이블(얼굴 임베딩 등)이 남아 있으면 제거합니다.
            cur.execute("DROP TABLE IF EXISTS regulars")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    items       TEXT NOT NULL,   -- 주문 내역(JSON)
                    total       INTEGER NOT NULL,
                    weekday     INTEGER,         -- 0=월 ... 6=일
                    hour        INTEGER,         -- 0~23 시
                    created_at  TEXT
                )
                """
            )
            self._conn.commit()

    # ──────────────────────────────────────────
    # 주문 통계(계획서 6장: 빅데이터 마케팅 대시보드)
    # ──────────────────────────────────────────
    def record_order(self, items: list[dict], total: int) -> None:
        """판매가 끝난 주문을 통계용으로 저장합니다(익명)."""
        now = datetime.now()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """INSERT INTO orders (items, total, weekday, hour, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (json.dumps(items, ensure_ascii=False), total,
                 now.weekday(), now.hour, now.isoformat()),
            )
            self._conn.commit()

    def sales_summary(self) -> dict:
        """요일·시간대·메뉴별 판매 트렌드를 요약합니다(점주 대시보드용)."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT items, total, weekday, hour FROM orders")
            rows = cur.fetchall()

        by_weekday: dict[int, int] = {}
        by_hour: dict[int, int] = {}
        by_item: dict[str, int] = {}
        total_revenue = 0
        for r in rows:
            by_weekday[r["weekday"]] = by_weekday.get(r["weekday"], 0) + 1
            by_hour[r["hour"]] = by_hour.get(r["hour"], 0) + 1
            total_revenue += r["total"]
            for it in json.loads(r["items"]):
                name = it.get("name", "?")
                by_item[name] = by_item.get(name, 0) + it.get("qty", 1)

        return {
            "order_count": len(rows),
            "total_revenue": total_revenue,
            "by_weekday": by_weekday,
            "by_hour": by_hour,
            "by_item": dict(sorted(by_item.items(), key=lambda kv: -kv[1])),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

"""
core/database.py — SQLite3 익명 단골 데이터베이스
================================================
계획서 2.2 / 3장 데이터베이스 항목 구현.

개인정보 보호 핵심 원칙(계획서 2.2):
  · 얼굴 "사진(원본 이미지)" 은 절대 저장하지 않습니다.
  · 눈·코·입의 기하학적 랜드마크에서 뽑아낸 "숫자 배열(임베딩 벡터)" 만 저장합니다.
  · 그 숫자마저도 사람이 알아볼 수 없으므로 익명(anonymous)입니다.

테이블 구조
  regulars : 단골 정보(별명, 얼굴 임베딩 벡터, 즐겨찾는 주문)
  orders   : 판매 통계(요일·시간대별 트렌드 분석용 — 계획서 6장 확장성)
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from typing import Optional

import numpy as np

from config import DB_PATH


class KioskDatabase:
    """단골 정보와 주문 통계를 관리하는 데이터베이스 클래스(OOP 설계)."""

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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS regulars (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    nickname    TEXT NOT NULL,
                    embedding   TEXT NOT NULL,   -- 얼굴 임베딩 벡터(JSON 숫자배열)
                    favorite    TEXT,            -- 즐겨찾는 주문(JSON)
                    visit_count INTEGER DEFAULT 1,
                    created_at  TEXT,
                    updated_at  TEXT
                )
                """
            )
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
    # 단골 등록 / 조회
    # ──────────────────────────────────────────
    def add_regular(self, nickname: str, embedding: np.ndarray,
                    favorite: Optional[dict] = None) -> int:
        """새 단골을 등록합니다. 얼굴 임베딩은 JSON 숫자배열로 저장(사진 X)."""
        now = datetime.now().isoformat()
        emb_json = json.dumps([round(float(x), 6) for x in embedding])
        fav_json = json.dumps(favorite, ensure_ascii=False) if favorite else None
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """INSERT INTO regulars
                   (nickname, embedding, favorite, visit_count, created_at, updated_at)
                   VALUES (?, ?, ?, 1, ?, ?)""",
                (nickname, emb_json, fav_json, now, now),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_all_regulars(self) -> list[dict]:
        """모든 단골을 (임베딩 벡터 포함) 불러옵니다."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT * FROM regulars")
            rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "nickname": r["nickname"],
                "embedding": np.array(json.loads(r["embedding"]), dtype=np.float64),
                "favorite": json.loads(r["favorite"]) if r["favorite"] else None,
                "visit_count": r["visit_count"],
            })
        return result

    def update_visit(self, regular_id: int, favorite: Optional[dict] = None) -> None:
        """단골 재방문 시 방문 횟수를 1 늘리고, 필요하면 즐겨찾기를 갱신합니다."""
        now = datetime.now().isoformat()
        with self._lock:
            cur = self._conn.cursor()
            if favorite is not None:
                cur.execute(
                    """UPDATE regulars
                       SET visit_count = visit_count + 1, favorite = ?, updated_at = ?
                       WHERE id = ?""",
                    (json.dumps(favorite, ensure_ascii=False), now, regular_id),
                )
            else:
                cur.execute(
                    """UPDATE regulars
                       SET visit_count = visit_count + 1, updated_at = ?
                       WHERE id = ?""",
                    (now, regular_id),
                )
            self._conn.commit()

    def nickname_exists(self, nickname: str) -> bool:
        """같은 별명이 이미 있는지 확인합니다."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM regulars WHERE nickname = ? LIMIT 1", (nickname,))
            return cur.fetchone() is not None

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

from __future__ import annotations
import json
import os
import sqlite3
import threading
from typing import Optional
from models import GameState

class GameStore:
    def __init__(self, path: str | None = None):
        self.path = path or os.getenv('DB_PATH', './magical_athlete.db')
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as c:
            c.execute('''
                CREATE TABLE IF NOT EXISTS games (
                    chat_id INTEGER PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            c.commit()

    def save(self, game: GameState):
        payload = json.dumps(game.to_dict(), ensure_ascii=False)
        with self._lock, self._connect() as c:
            c.execute('''
                INSERT INTO games(chat_id,payload,updated_at)
                VALUES(?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    payload=excluded.payload,
                    updated_at=CURRENT_TIMESTAMP
            ''', (game.chat_id, payload))
            c.commit()

    def load(self, chat_id: int) -> Optional[GameState]:
        with self._lock, self._connect() as c:
            row = c.execute('SELECT payload FROM games WHERE chat_id=?', (chat_id,)).fetchone()
        if not row:
            return None
        return GameState.from_dict(json.loads(row['payload']))

    def delete(self, chat_id: int):
        with self._lock, self._connect() as c:
            c.execute('DELETE FROM games WHERE chat_id=?', (chat_id,))
            c.commit()

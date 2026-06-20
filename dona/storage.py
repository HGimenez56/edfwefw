"""Camada de armazenamento da Dona (SQLite).

Um único arquivo SQLite guarda tudo: mensagens ingeridas, tarefas e
compromissos extraídos, preferências aprendidas e o perfil do dono. O schema
já nasce cobrindo as fases seguintes para evitar migrações dolorosas — as
fases posteriores apenas passam a *popular* tabelas que já existem.

A API é propositalmente simples (funções + um pequeno `Storage`), sem ORM,
porque o uso é pessoal e o volume é baixo.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional


# --- Schema -----------------------------------------------------------------
# Mantido como uma constante para ser fácil de ler e versionar. Usa
# `CREATE TABLE IF NOT EXISTS` para ser idempotente.
SCHEMA = """
-- Mensagens cruas ingeridas de qualquer fonte (e-mail, whatsapp, telegram).
CREATE TABLE IF NOT EXISTS messages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,           -- 'email' | 'whatsapp' | 'telegram'
    direction    TEXT NOT NULL,           -- 'in' | 'out'
    external_id  TEXT,                    -- id na fonte (para deduplicar)
    sender       TEXT,
    recipient    TEXT,
    subject      TEXT,
    body         TEXT,
    category     TEXT,                    -- 'trabalho' | 'pessoal' | NULL
    received_at  TEXT,                    -- ISO8601 da origem
    ingested_at  TEXT NOT NULL,           -- ISO8601 de quando entrou aqui
    processed    INTEGER NOT NULL DEFAULT 0,
    raw          TEXT,                    -- payload original (JSON), opcional
    UNIQUE(source, external_id)
);

-- Tarefas / pedidos / demandas extraídas pelo cérebro.
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    details      TEXT,
    category     TEXT,                    -- 'trabalho' | 'pessoal'
    priority     INTEGER NOT NULL DEFAULT 3,  -- 1 (alta) .. 5 (baixa)
    status       TEXT NOT NULL DEFAULT 'open', -- 'open'|'done'|'snoozed'|'dismissed'
    due_at       TEXT,                    -- ISO8601, opcional
    source_msg_id INTEGER,               -- FK -> messages.id (opcional)
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY(source_msg_id) REFERENCES messages(id)
);

-- Compromissos / pontas soltas: algo que foi pedido a você, ou que você
-- prometeu, e que precisa de follow-up.
CREATE TABLE IF NOT EXISTS commitments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,           -- 'awaiting_my_reply'|'i_promised'|'awaiting_their_reply'
    who          TEXT,                    -- contraparte (pessoa/cliente)
    summary      TEXT NOT NULL,
    category     TEXT,
    status       TEXT NOT NULL DEFAULT 'open', -- 'open'|'resolved'|'dismissed'
    source_msg_id INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY(source_msg_id) REFERENCES messages(id)
);

-- Preferências aprendidas (ex.: remetente X é alta prioridade, ignorar
-- newsletters). Armazenadas como chave/valor para flexibilidade.
CREATE TABLE IF NOT EXISTS preferences (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scope        TEXT NOT NULL,           -- 'sender'|'topic'|'global'|...
    key          TEXT NOT NULL,
    value        TEXT,                    -- JSON
    weight       REAL NOT NULL DEFAULT 1.0,
    updated_at   TEXT NOT NULL,
    UNIQUE(scope, key)
);

-- Perfil do dono: um documento em texto livre que o cérebro injeta como
-- contexto. É aqui que a "personalidade"/memória de longo prazo vive.
CREATE TABLE IF NOT EXISTS profile (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    content      TEXT NOT NULL DEFAULT '',
    updated_at   TEXT NOT NULL
);

-- Eventos de calendário/reuniões (Fase 2). start_at/end_at em UTC ISO8601.
CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uid          TEXT,                    -- UID do VEVENT (para dedup)
    summary      TEXT,
    location     TEXT,
    organizer    TEXT,
    start_at     TEXT NOT NULL,           -- UTC ISO8601
    end_at       TEXT,                    -- UTC ISO8601
    status       TEXT,                    -- 'confirmed'|'cancelled'|...
    source       TEXT,                    -- 'ics_url'|'email_invite'
    created_at   TEXT NOT NULL,
    UNIQUE(uid, start_at)
);

-- Rascunhos preparados pela Dona aguardando aprovação (Fase 4).
CREATE TABLE IF NOT EXISTS drafts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    kind         TEXT NOT NULL,           -- 'email_reply'|'meeting_invite'
    target       TEXT,                    -- destinatário pretendido
    subject      TEXT,
    body         TEXT NOT NULL,
    payload      TEXT,                    -- JSON extra (ex.: .ics)
    status       TEXT NOT NULL DEFAULT 'pending', -- 'pending'|'approved'|'rejected'|'sent'
    source_msg_id INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    FOREIGN KEY(source_msg_id) REFERENCES messages(id)
);

CREATE INDEX IF NOT EXISTS idx_messages_processed ON messages(processed);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_commitments_status ON commitments(status);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_at);
"""


def _now_iso() -> str:
    """Timestamp atual em ISO8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


class Storage:
    """Acesso fino ao SQLite. Instâncias são baratas; reaproveite uma só."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            # garante a linha única de perfil
            conn.execute(
                "INSERT OR IGNORE INTO profile (id, content, updated_at) "
                "VALUES (1, '', ?)",
                (_now_iso(),),
            )

    # --- Mensagens ---------------------------------------------------------
    def add_message(
        self,
        *,
        source: str,
        direction: str,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        external_id: Optional[str] = None,
        received_at: Optional[str] = None,
        category: Optional[str] = None,
        raw: Optional[dict[str, Any]] = None,
    ) -> Optional[int]:
        """Insere uma mensagem. Retorna o id, ou None se for duplicata."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO messages
                  (source, direction, external_id, sender, recipient, subject,
                   body, category, received_at, ingested_at, raw)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    direction,
                    external_id,
                    sender,
                    recipient,
                    subject,
                    body,
                    category,
                    received_at,
                    _now_iso(),
                    json.dumps(raw) if raw is not None else None,
                ),
            )
            return cur.lastrowid if cur.rowcount else None

    def unprocessed_messages(self, limit: int = 50) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM messages WHERE processed = 0 "
                "ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()

    def mark_processed(self, message_ids: Iterable[int]) -> None:
        ids = list(message_ids)
        if not ids:
            return
        with self._connect() as conn:
            conn.executemany(
                "UPDATE messages SET processed = 1 WHERE id = ?",
                [(i,) for i in ids],
            )

    # --- Tarefas -----------------------------------------------------------
    def add_task(
        self,
        *,
        title: str,
        details: Optional[str] = None,
        category: Optional[str] = None,
        priority: int = 3,
        due_at: Optional[str] = None,
        source_msg_id: Optional[int] = None,
    ) -> int:
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tasks
                  (title, details, category, priority, status, due_at,
                   source_msg_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
                """,
                (title, details, category, priority, due_at,
                 source_msg_id, now, now),
            )
            return int(cur.lastrowid)

    def open_tasks(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM tasks WHERE status = 'open' "
                "ORDER BY priority ASC, COALESCE(due_at, '9999') ASC LIMIT ?",
                (limit,),
            ).fetchall()

    def set_task_status(self, task_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now_iso(), task_id),
            )

    # --- Compromissos ------------------------------------------------------
    def add_commitment(
        self,
        *,
        kind: str,
        summary: str,
        who: Optional[str] = None,
        category: Optional[str] = None,
        source_msg_id: Optional[int] = None,
    ) -> int:
        now = _now_iso()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO commitments
                  (kind, who, summary, category, status, source_msg_id,
                   created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (kind, who, summary, category, source_msg_id, now, now),
            )
            return int(cur.lastrowid)

    def open_commitments(self, limit: int = 100) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM commitments WHERE status = 'open' "
                "ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()

    def set_commitment_status(self, commitment_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE commitments SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now_iso(), commitment_id),
            )

    # --- Eventos (calendário) ---------------------------------------------
    def add_event(
        self,
        *,
        summary: str,
        start_at: str,
        end_at: Optional[str] = None,
        uid: Optional[str] = None,
        location: Optional[str] = None,
        organizer: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Optional[int]:
        """Insere um evento. Retorna o id, ou None se for duplicata."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO events
                  (uid, summary, location, organizer, start_at, end_at,
                   status, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (uid, summary, location, organizer, start_at, end_at,
                 status, source, _now_iso()),
            )
            return cur.lastrowid if cur.rowcount else None

    def events_between(self, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
        """Eventos cujo início cai em [start_iso, end_iso). Tudo em UTC ISO."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM events "
                "WHERE start_at >= ? AND start_at < ? "
                "AND (status IS NULL OR status != 'cancelled') "
                "ORDER BY start_at ASC",
                (start_iso, end_iso),
            ).fetchall()

    # --- Preferências / perfil --------------------------------------------
    def set_preference(
        self, scope: str, key: str, value: Any, weight: float = 1.0
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO preferences (scope, key, value, weight, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(scope, key) DO UPDATE SET
                  value = excluded.value,
                  weight = excluded.weight,
                  updated_at = excluded.updated_at
                """,
                (scope, key, json.dumps(value), weight, _now_iso()),
            )

    def get_preferences(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM preferences ORDER BY scope, key"
            ).fetchall()

    def get_profile(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content FROM profile WHERE id = 1"
            ).fetchone()
            return row["content"] if row else ""

    def set_profile(self, content: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE profile SET content = ?, updated_at = ? WHERE id = 1",
                (content, _now_iso()),
            )

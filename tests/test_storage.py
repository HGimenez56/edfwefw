"""Testes da camada de armazenamento (Fase 0).

Rodam sem nenhuma credencial: exercitam apenas o SQLite, garantindo que o
schema, a deduplicação de mensagens e o CRUD básico funcionam.
"""

from __future__ import annotations

from pathlib import Path

from dona.storage import Storage


def _store(tmp_path: Path) -> Storage:
    return Storage(tmp_path / "test.db")


def test_init_creates_db_and_profile_row(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert (tmp_path / "test.db").exists()
    # perfil começa vazio mas existe
    assert store.get_profile() == ""


def test_add_message_dedup(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = store.add_message(
        source="email", direction="in", external_id="abc", subject="Oi"
    )
    dup = store.add_message(
        source="email", direction="in", external_id="abc", subject="Oi"
    )
    assert isinstance(first, int)
    assert dup is None  # duplicata é ignorada


def test_tasks_lifecycle(tmp_path: Path) -> None:
    store = _store(tmp_path)
    tid = store.add_task(title="Mandar proposta", priority=1)
    assert any(t["id"] == tid for t in store.open_tasks())
    store.set_task_status(tid, "done")
    assert all(t["id"] != tid for t in store.open_tasks())


def test_commitments_and_prefs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    cid = store.add_commitment(
        kind="awaiting_my_reply", summary="Cliente X pediu retorno", who="Cliente X"
    )
    assert any(c["id"] == cid for c in store.open_commitments())

    store.set_preference("sender", "chefe@empresa.com", {"priority": 1}, weight=2.0)
    prefs = store.get_preferences()
    assert any(p["key"] == "chefe@empresa.com" for p in prefs)


def test_profile_update(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.set_profile("Dono trabalha com clientes; prioriza reuniões.")
    assert "clientes" in store.get_profile()


def test_unprocessed_flow(tmp_path: Path) -> None:
    store = _store(tmp_path)
    mid = store.add_message(source="email", direction="in", subject="X")
    assert any(m["id"] == mid for m in store.unprocessed_messages())
    store.mark_processed([mid])
    assert all(m["id"] != mid for m in store.unprocessed_messages())

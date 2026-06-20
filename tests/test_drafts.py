"""Testes do motor de rascunhos (Fase 4). Sem rede/IA: cérebro stub/fake."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dona.skills import drafts


class StubBrain:
    ready = False

    def chat(self, *_a, **_k):  # nunca chamado quando ready=False
        raise AssertionError("não deveria chamar o modelo")


class FakeBrain:
    ready = True

    def chat(self, prompt, temperature=0.3):
        return "Texto gerado pelo modelo."


def test_reply_draft_stub_when_no_brain() -> None:
    text = drafts.generate_reply_draft(StubBrain(), "Pode me enviar o relatório?")
    assert "stub" in text.lower()


def test_reply_draft_uses_brain() -> None:
    text = drafts.generate_reply_draft(FakeBrain(), "Oi, tudo bem?")
    assert text == "Texto gerado pelo modelo."


def test_build_ics_is_valid() -> None:
    start = datetime(2026, 6, 25, 14, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    ics = drafts.build_ics(
        summary="Reunião Cliente X", start=start, end=end,
        organizer="eu@x.com", attendees=["cliente@x.com"], location="Teams",
    )
    assert "BEGIN:VCALENDAR" in ics
    assert "SUMMARY:Reunião Cliente X" in ics
    assert "ATTENDEE:mailto:cliente@x.com" in ics
    # deve ser parseável de volta
    from icalendar import Calendar
    cal = Calendar.from_ical(ics)
    assert len(list(cal.walk("VEVENT"))) == 1


def test_meeting_invite_returns_text_and_ics() -> None:
    start = datetime(2026, 6, 25, 14, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    text, ics = drafts.generate_meeting_invite(
        FakeBrain(), summary="Alinhamento", start=start, end=end,
        attendees=["cliente@x.com"],
    )
    assert text
    assert "BEGIN:VCALENDAR" in ics

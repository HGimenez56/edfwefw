"""Motor de rascunhos (Fase 4).

Gera rascunhos que **sempre** dependem da aprovação do dono — a Donna nunca
envia nada sozinha. Dois tipos:
- resposta a um e-mail/mensagem (texto, no tom do dono);
- convite de reunião (texto + arquivo `.ics` pronto para enviar).

A geração de texto usa o cérebro (`Brain.chat`), que já injeta perfil e
preferências aprendidas — então o tom melhora com o tempo. A construção do
`.ics` é pura (testável sem rede/IA).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from icalendar import Calendar, Event

from ..brain import Brain

_REPLY_PROMPT = """\
Escreva um rascunho de RESPOSTA curto e profissional, no tom do dono (direto,
cordial, português do Brasil), para a mensagem abaixo. Não invente fatos nem
compromissos; se faltar informação, deixe um espaço marcado como [confirmar].
Devolva apenas o texto da resposta, sem assunto e sem assinatura.
"""


def generate_reply_draft(brain: Brain, original_message: str) -> str:
    """Gera o texto de um rascunho de resposta."""
    if not brain.ready:
        return (
            "[rascunho stub — configure a OpenAI]\n\n"
            "Olá, obrigado pela mensagem. [confirmar resposta]."
        )
    return brain.chat(f"{_REPLY_PROMPT}\n\n---\n{original_message}", temperature=0.4)


def build_ics(
    *,
    summary: str,
    start: datetime,
    end: datetime,
    organizer: Optional[str] = None,
    attendees: Optional[list[str]] = None,
    location: str = "",
    description: str = "",
) -> str:
    """Constrói um `.ics` (VCALENDAR com um VEVENT). Datas devem ser aware."""
    cal = Calendar()
    cal.add("prodid", "-//Donna//Assistente//PT")
    cal.add("version", "2.0")
    cal.add("method", "REQUEST")

    event = Event()
    event.add("summary", summary)
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("dtstamp", datetime.now(start.tzinfo))
    if location:
        event.add("location", location)
    if description:
        event.add("description", description)
    if organizer:
        event.add("organizer", f"mailto:{organizer}")
    for att in attendees or []:
        event.add("attendee", f"mailto:{att}")

    cal.add_component(event)
    return cal.to_ical().decode("utf-8")


def generate_meeting_invite(
    brain: Brain,
    *,
    summary: str,
    start: datetime,
    end: datetime,
    attendees: Optional[list[str]] = None,
    location: str = "",
    organizer: Optional[str] = None,
    context: str = "",
) -> tuple[str, str]:
    """Gera (texto do convite, conteúdo .ics) para um convite de reunião."""
    when = start.strftime("%d/%m/%Y às %H:%M")
    if brain.ready:
        prompt = (
            "Escreva um e-mail curto e cordial convidando para uma reunião. "
            f"Assunto: {summary}. Quando: {when}. "
            f"{('Contexto: ' + context) if context else ''} "
            "Confirme o horário e peça retorno. Apenas o corpo do e-mail."
        )
        text = brain.chat(prompt, temperature=0.4)
    else:
        text = (
            f"Olá, proponho nos reunirmos sobre '{summary}' em {when}. "
            "Pode confirmar se funciona para você?"
        )
    ics = build_ics(
        summary=summary, start=start, end=end, attendees=attendees,
        location=location, organizer=organizer, description=context,
    )
    return text, ics

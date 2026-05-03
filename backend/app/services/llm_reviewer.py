"""LLM-powered booking review that runs after document processing.

Instead of hard-coded rules, this uses Claude to autonomously discover
anomalies, missing links, and patterns in the bookings.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_notification import AgentNotification
from app.models.agent_run import AgentRun
from app.models.agent_skill import AgentSkill
from app.models.booking import Booking
from app.models.client import Client
from app.models.document import Document
from app.services.industry_catalog import build_industry_context

logger = logging.getLogger(__name__)

_REVIEW_SYSTEM_PROMPT = """\
Du bist ein erfahrener Buchhalter und Prüfer für deutsche Unternehmen.
Du analysierst Buchungsvorschläge einer KI-Buchhaltung und findest Probleme,
die regelbasierte Systeme nicht erkennen können.

Du bekommst auch die GELERNTEN REGELN des Mandanten — das sind Informationen,
die bereits bekannt sind (z.B. "Dienstwagen wird mit 1%-Regelung versteuert").
Nutze diese Regeln bei der Analyse und wiederhole keine Fragen zu bereits
beantworteten Themen.

Deine Aufgabe: Analysiere die gegebenen Buchungen und finde:
1. **Fehlende Verknüpfungen** — Rechnungsbuchungen ohne zugehörige Bankzahlung
2. **Inkonsistenzen** — Lieferant auf verschiedenen Konten, widersprüchliche USt-Sätze
3. **Anomalien** — Ungewöhnliche Beträge, Duplikate, fehlende Belege
4. **Muster** — Wiederkehrende Probleme, z.B. bestimmte Lieferanten falsch kontiert
5. **Offene Fragen** — Buchungen die Rückfragen an den Mandanten erfordern
6. **Fehlende Informationen** — Steuerlich relevante Sachverhalte, bei denen du
   Informationen brauchst um korrekt zu buchen (z.B. Dienstwagen: 1%-Regelung
   oder Fahrtenbuch? Privatanteil Telefon? Bewirtungsanlass? Home-Office-Pauschale?)

Antworte AUSSCHLIESSLICH mit einem JSON-Array von Issues. Jedes Issue hat:
{
  "severity": "error" | "warning" | "info",
  "title": "Kurztitel max 60 Zeichen",
  "message": "Ausführliche Beschreibung mit Handlungsempfehlung",
  "affected_booking_ids": ["id1", "id2"],
  "category": "missing_bank_link" | "inconsistent_account" | "anomaly" | "duplicate" | "pattern" | "question" | "clarification_needed"
}

Für "clarification_needed" Issues: Formuliere eine klare, konkrete Frage an den
Mandanten. Erkläre WARUM die Information steuerlich relevant ist und welche
Auswirkung die Antwort auf die Buchung hat. Beispiele:
- "Wird der Sixt-Mietwagen als Dienstwagen mit 1%-Regelung, Fahrtenbuch oder
  als einzelne Geschäftsreise abgerechnet? → bestimmt Konto und USt-Behandlung"
- "Netflix/Spotify: Rein privat oder anteilig geschäftlich genutzt (z.B. für
  Kundenempfang)? → bestimmt ob Betriebsausgabe oder Privatentnahme"

Regeln:
- Nur echte Probleme melden, keine trivialen Hinweise
- Immer konkrete Buchungs-IDs referenzieren
- Immer eine Handlungsempfehlung geben
- Prüfe die GELERNTEN REGELN bevor du eine Frage stellst — frag nicht nach
  Informationen die bereits als Regel hinterlegt sind
- Wenn alles in Ordnung ist: leeres Array []
- Maximal 10 Issues pro Analyse
"""


def _format_bookings_for_llm(
    bookings: list[Booking],
    documents: dict[uuid.UUID, Document],
) -> str:
    lines = []
    for b in bookings:
        doc = documents.get(b.document_id)
        doc_name = doc.original_filename if doc else "unbekannt"
        doc_type = ""
        if doc and doc.extraction:
            doc_type = doc.extraction.get("document_type", "")

        lines.append(
            f"ID: {b.id} | Datum: {b.document_date} | "
            f"Konto: {b.account} → Gegenkonto: {b.contra_account} | "
            f"Betrag: {b.amount} EUR | S/H: {b.debit_credit} | "
            f"BU: {b.bu_key or '-'} | "
            f"Text: '{b.booking_text or ''}' | "
            f"Status: {b.status} | Konfidenz: {b.ai_confidence or '-'} | "
            f"Beleg: {doc_name} ({doc_type})"
        )
    return "\n".join(lines)


async def run_llm_review(
    db: AsyncSession,
    client_id: uuid.UUID,
    *,
    trigger: str = "document_processed",
    document_id: uuid.UUID | None = None,
) -> list[dict]:
    """Run an LLM-powered review of a client's bookings.

    Args:
        trigger: What caused this review ("document_processed" or "batch_review")
        document_id: If set, focuses the review around the newly processed document
    """
    client = await db.get(Client, client_id)
    if not client:
        return []

    t0 = time.monotonic()

    result = await db.execute(
        select(Booking)
        .where(
            Booking.client_id == client_id,
            Booking.status.in_(["suggested", "approved"]),
        )
        .order_by(Booking.document_date.desc())
        .limit(100)
    )
    bookings = list(result.scalars().all())

    if not bookings:
        return []

    doc_ids = {b.document_id for b in bookings}
    doc_result = await db.execute(
        select(Document).where(Document.id.in_(doc_ids))
    )
    documents = {d.id: d for d in doc_result.scalars().all()}

    industry_ctx = build_industry_context(client.industry, client.industry_detail)

    skill_result = await db.execute(
        select(AgentSkill)
        .where(
            AgentSkill.client_id == client_id,
            AgentSkill.is_active.is_(True),
        )
        .order_by(AgentSkill.confidence.desc())
        .limit(30)
    )
    skills = list(skill_result.scalars().all())

    skills_ctx = ""
    if skills:
        skill_lines = []
        for s in skills:
            skill_lines.append(f"• [{s.category}] {s.title}: {s.content}")
        skills_ctx = (
            "\n\nGELERNTE REGELN DES MANDANTEN (bereits bekannt — nicht erneut nachfragen):\n"
            + "\n".join(skill_lines)
        )

    focus_note = ""
    if document_id:
        doc = documents.get(document_id)
        if doc:
            new_booking_ids = {str(b.id) for b in bookings if b.document_id == document_id}
            focus_note = (
                f"\n\nFOKUS: Das Dokument '{doc.original_filename}' wurde gerade verarbeitet. "
                f"Die Buchungen mit diesen IDs sind NEU: {', '.join(new_booking_ids)}. "
                f"Prüfe besonders ob diese neuen Buchungen zum Gesamtbild passen."
            )

    booking_text = _format_bookings_for_llm(bookings, documents)

    user_prompt = (
        f"Mandant: {client.company_name}\n"
        f"Kontenrahmen: {client.chart_of_accounts or 'SKR03'}\n"
        f"{industry_ctx}"
        f"{skills_ctx}\n\n"
        f"Buchungen ({len(bookings)} Stück):\n"
        f"{booking_text}"
        f"{focus_note}\n\n"
        f"Analysiere diese Buchungen und gib ausschließlich ein JSON-Array zurück."
    )

    from app.services import llm_service

    try:
        response = await llm_service.completion(
            client_id, db,
            operation="review",
            system=_REVIEW_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=4096,
        )

        raw_text = (response.choices[0].message.content or "").strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3].strip()

        issues = json.loads(raw_text)
        if not isinstance(issues, list):
            issues = []

    except Exception:
        logger.exception("LLM review failed for client %s", client_id)
        return []

    elapsed = int((time.monotonic() - t0) * 1000)

    if issues or trigger == "batch_review":
        run = AgentRun(
            client_id=client_id,
            run_type="llm_review",
            status="completed",
            result_summary=(
                f"LLM-Analyse: {len(issues)} Issue(s) gefunden"
                if issues
                else "LLM-Analyse: Keine Probleme erkannt"
            ),
            items_checked=len(bookings),
            items_flagged=len(issues),
            items_fixed=0,
            completed_at=datetime.now(timezone.utc),
            duration_ms=elapsed,
            strategy=trigger,
            details={
                "issues": issues,
                "bookings_analyzed": len(bookings),
                "trigger": trigger,
                "document_id": str(document_id) if document_id else None,
            },
        )
        db.add(run)
        await db.flush()

        clarifications = [i for i in issues if i.get("category") == "clarification_needed"]
        errors = [i for i in issues if i.get("severity") == "error" and i.get("category") != "clarification_needed"]
        warnings = [i for i in issues if i.get("severity") == "warning" and i.get("category") != "clarification_needed"]
        infos = [i for i in issues if i.get("severity") == "info" and i.get("category") != "clarification_needed"]

        for c in clarifications:
            affected = c.get("affected_booking_ids", [])
            db.add(AgentNotification(
                client_id=client_id,
                agent_run_id=run.id,
                severity="warning",
                category="clarification_needed",
                title=f"Rückfrage: {c['title']}",
                message=(
                    f"{c['message']}\n\n"
                    f"Bitte beantworten Sie diese Frage im Chat oder auf der "
                    f"Prüfer-Seite. Die Antwort wird als Regel gespeichert und "
                    f"bei zukünftigen Buchungen automatisch berücksichtigt."
                ),
                action_required=True,
                action_type="clarification_needed",
                action_data={
                    "affected_booking_ids": affected,
                    "question": c.get("message", ""),
                },
            ))

        if errors:
            summary = "\n".join(
                f"• **{e['title']}**: {e['message']}" for e in errors[:5]
            )
            db.add(AgentNotification(
                client_id=client_id,
                agent_run_id=run.id,
                severity="error",
                category="llm_review",
                title=f"KI-Prüfung: {len(errors)} Problem(e) erkannt",
                message=(
                    f"Die KI-Analyse hat {len(errors)} schwerwiegende "
                    f"Problem(e) in den Buchungen gefunden:\n\n{summary}"
                ),
                action_required=True,
                action_type="review_bookings",
            ))

        if warnings:
            summary = "\n".join(
                f"• **{w['title']}**: {w['message']}" for w in warnings[:5]
            )
            db.add(AgentNotification(
                client_id=client_id,
                agent_run_id=run.id,
                severity="warning",
                category="llm_review",
                title=f"KI-Prüfung: {len(warnings)} Hinweis(e)",
                message=(
                    f"Die KI-Analyse hat {len(warnings)} Hinweis(e):\n\n{summary}"
                ),
            ))

        if infos and not errors and not warnings and not clarifications:
            summary = "\n".join(f"• {i['title']}" for i in infos[:5])
            db.add(AgentNotification(
                client_id=client_id,
                agent_run_id=run.id,
                severity="info",
                category="llm_review",
                title=f"KI-Prüfung: {len(infos)} Info(s)",
                message=f"Informationen aus der KI-Analyse:\n\n{summary}",
            ))

        await db.flush()

    logger.info(
        "LLM review for client %s: %d issues found in %dms (trigger=%s)",
        client_id, len(issues), elapsed, trigger,
    )

    return issues

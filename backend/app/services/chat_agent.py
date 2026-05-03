"""
Conversational bookkeeper agent.

The agent has free access to 8 tools and can chain them in any order.
It streams text token-by-token and emits tool_start/tool_end events so the
frontend can show live progress.
"""
import json
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_skill import AgentSkill
from app.models.audit_log import AuditLog
from app.models.booking import Booking
from app.models.client import Client
from app.models.document import Document
from app.services.code_executor import execute_python
from app.services.skill_manager import (
    VALID_CATEGORIES,
    get_relevant_skills,
    learn_from_chat,
)
from app.services.vat_validation import validate_vat_id
from app.services.web_search import search_accounting

logger = logging.getLogger(__name__)

# ── Tool labels shown in the UI ──────────────────────────────────────────────

TOOL_LABELS: dict[str, str] = {
    "get_client_overview": "Mandantenübersicht wird abgerufen",
    "list_bookings": "Buchungen werden abgerufen",
    "list_documents": "Dokumente werden abgerufen",
    "get_document_details": "Belegdetails werden geladen",
    "approve_booking": "Buchung wird freigegeben",
    "update_booking": "Buchung wird aktualisiert",
    "create_booking": "Buchung wird erstellt",
    "execute_python": "Code wird ausgeführt",
    "web_search": "Recherche läuft",
    "validate_vat_id": "USt-ID wird geprüft",
    "save_skill": "Regel wird gespeichert",
    "list_skills": "Gelernte Regeln werden abgerufen",
    "tax_analysis": "Steuerliche Analyse wird durchgeführt",
}

# ── Tool schemas ─────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "name": "get_client_overview",
        "description": (
            "Gibt Stammdaten und aktuelle Statistiken des Mandanten zurück: "
            "Firmenname, Kontenrahmen, Anzahl Dokumente, offene Reviews, Buchungen nach Status."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "list_bookings",
        "description": (
            "Listet Buchungen des Mandanten. Optional filterbar nach Status "
            "('suggested', 'approved', 'exported', 'all'), Datumsbereich und Limit."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["suggested", "approved", "exported", "all"],
                    "description": "Standard: 'all'",
                },
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
                "account": {"type": "string", "description": "Kontonummer zum Filtern"},
                "limit": {"type": "integer", "description": "Max. Anzahl Ergebnisse, Standard 30"},
            },
            "required": [],
        },
    },
    {
        "name": "list_documents",
        "description": "Listet Dokumente des Mandanten. Filterbar nach Status und Limit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "z.B. 'uploaded', 'booking_suggested', 'approved' oder 'all'",
                },
                "limit": {"type": "integer", "description": "Standard 15"},
            },
            "required": [],
        },
    },
    {
        "name": "get_document_details",
        "description": "Gibt die vollständigen OCR-Extraktionsdaten eines Dokuments zurück (Vendor, Beträge, MwSt, Positionen).",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "UUID des Dokuments"},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "approve_booking",
        "description": "Genehmigt eine Buchung (Status → 'approved'). Schreibt Audit-Log-Eintrag.",
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "UUID der Buchung"},
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "update_booking",
        "description": (
            "Aktualisiert ein oder mehrere Felder einer Buchung. "
            "Nur übergebene Felder werden geändert."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string"},
                "account": {"type": "string"},
                "contra_account": {"type": "string"},
                "bu_key": {"type": "string"},
                "booking_text": {"type": "string", "description": "Max 60 Zeichen"},
                "amount": {"type": "string", "description": "Positiver Dezimalwert"},
                "debit_credit": {"type": "string", "enum": ["S", "H"]},
                "reference_1": {"type": "string"},
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "create_booking",
        "description": "Erstellt eine neue manuelle Buchung für ein vorhandenes Dokument.",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "amount": {"type": "string", "description": "Positiver Dezimalwert"},
                "debit_credit": {"type": "string", "enum": ["S", "H"]},
                "account": {"type": "string"},
                "contra_account": {"type": "string"},
                "document_date": {"type": "string", "description": "YYYY-MM-DD"},
                "bu_key": {"type": "string"},
                "booking_text": {"type": "string", "description": "Max 60 Zeichen"},
                "reference_1": {"type": "string"},
            },
            "required": ["document_id", "amount", "debit_credit", "account", "contra_account", "document_date"],
        },
    },
    {
        "name": "execute_python",
        "description": (
            "Führt Python-Code in einer isolierten Sandbox aus. "
            "Verfügbare Bibliotheken: pandas, numpy, openpyxl, matplotlib, decimal, json, math, datetime, re. "
            "Ideal für Berechnungen, Summen, Pivot-Tabellen, Datenanalysen, Charts, CSV/Excel-Export. "
            "Ergebnisse mit print() ausgeben. "
            "Dateien (CSV, Excel, PNG-Charts) nach OUTPUT_DIR schreiben — sie werden automatisch zurückgegeben. "
            "Wenn du zuvor Buchungsdaten mit list_bookings abgerufen hast, übergib sie als context_data — "
            "sie sind dann als CONTEXT_DATA-Variable im Code verfügbar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Valider Python-Code"},
                "context_data": {
                    "type": "array",
                    "description": (
                        "Optional: Daten die im Code als CONTEXT_DATA verfügbar sein sollen "
                        "(z.B. zuvor abgerufene Buchungen oder Dokumente)"
                    ),
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Recherchiere im Internet nach aktuellen Buchhaltungsregeln, Steuerrecht, "
            "DATEV-Richtlinien, Kontenrahmen-Informationen oder USt-Regelungen. "
            "Nutze es bei Unsicherheit über steuerliche Behandlung, aktuelle Gesetzesänderungen, "
            "oder wenn der Benutzer nach spezifischen Regelungen fragt. "
            "Sucht bevorzugt auf haufe.de, datev.de, bundesfinanzministerium.de und iww.de."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Suchanfrage auf Deutsch, z.B. 'Bewirtungsbeleg Abzugsfähigkeit 2026'",
                },
                "topic": {
                    "type": "string",
                    "enum": ["general", "news", "finance"],
                    "description": "Suchkategorie (Standard: general)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "validate_vat_id",
        "description": (
            "Prüft eine europäische USt-ID (z.B. 'DE123456789') gegen die offizielle VIES-Datenbank "
            "der EU-Kommission. Gibt zurück ob die Nummer gültig ist, sowie Name und Adresse des Unternehmens."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vat_id": {
                    "type": "string",
                    "description": "Europäische USt-ID, z.B. 'DE123456789', 'ATU12345678', 'FR12345678901'",
                },
            },
            "required": ["vat_id"],
        },
    },
    {
        "name": "save_skill",
        "description": (
            "Speichere eine neue Buchungsregel oder ein Muster als wiederverwendbaren Skill. "
            "Nutze dieses Tool PROAKTIV wenn der Benutzer eine Anweisung gibt die für zukünftige "
            "Buchungen relevant ist (z.B. 'Alle Amazon-Rechnungen auf 4930', 'LinkedIn ist Werbung')."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Kurzer Titel der Regel (max 100 Zeichen)",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Markdown-Beschreibung der Regel mit konkreten Konten, BU-Schlüsseln, "
                        "und Anwendungsbedingungen (1-5 Sätze)"
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": sorted(VALID_CATEGORIES),
                    "description": (
                        "vendor_pattern=Lieferantenregel, account_rule=Kontenzuordnung, "
                        "tax_rule=Steuerregel, industry_pattern=Branchenmuster, "
                        "correction_pattern=Korrekturmuster, custom=Sonstiges"
                    ),
                },
            },
            "required": ["title", "content", "category"],
        },
    },
    {
        "name": "list_skills",
        "description": (
            "Listet die gespeicherten Buchungsregeln und Skills des Mandanten auf. "
            "Nutze es um dem Benutzer zu zeigen was das System bereits gelernt hat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": sorted(VALID_CATEGORIES),
                    "description": "Optional: nur Skills dieser Kategorie anzeigen",
                },
                "active_only": {
                    "type": "boolean",
                    "description": "Nur aktive Skills anzeigen (Standard: true)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "tax_analysis",
        "description": (
            "Analysiere die Buchungen des Mandanten auf steuerliche Optimierungspotenziale. "
            "Prüft Absetzbarkeit, fehlende Nachweise, Teilabzüge und gibt Empfehlungen. "
            "Nutze dieses Tool wenn der Benutzer nach Steuersparmöglichkeiten, Absetzbarkeit, "
            "steuerlicher Optimierung oder einem Steuer-Check fragt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Zeitraum: YYYY-MM für einen Monat oder YYYY für ein ganzes Jahr",
                },
                "focus": {
                    "type": "string",
                    "enum": ["all", "deductions", "vat", "depreciation", "year_end"],
                    "description": (
                        "Fokus der Analyse: "
                        "'all' = Gesamtanalyse, "
                        "'deductions' = Absetzbarkeit und Teilabzüge, "
                        "'vat' = Vorsteuer-Probleme, "
                        "'depreciation' = AfA und GWG, "
                        "'year_end' = Jahresende-Optimierung"
                    ),
                },
            },
            "required": [],
        },
    },
]


# ── Tool implementations ─────────────────────────────────────────────────────

async def _tool_get_client_overview(client_id: uuid.UUID, db: AsyncSession) -> dict:
    client = await db.get(Client, client_id)
    if not client:
        return {"error": "Mandant nicht gefunden"}

    bookings_result = await db.execute(select(Booking).where(Booking.client_id == client_id))
    bookings = bookings_result.scalars().all()

    docs_result = await db.execute(select(Document).where(Document.client_id == client_id))
    docs = docs_result.scalars().all()

    status_counts: dict[str, int] = {}
    for b in bookings:
        status_counts[b.status] = status_counts.get(b.status, 0) + 1

    return {
        "company_name": client.company_name,
        "legal_form": client.legal_form,
        "chart_of_accounts": client.chart_of_accounts,
        "tax_number": client.tax_number,
        "vat_id": client.vat_id,
        "datev_consultant_number": client.datev_consultant_number,
        "datev_client_number": client.datev_client_number,
        "documents_total": len(docs),
        "documents_by_status": {
            s: sum(1 for d in docs if d.status == s)
            for s in set(d.status for d in docs)
        },
        "bookings_total": len(bookings),
        "bookings_by_status": status_counts,
    }


async def _tool_list_bookings(client_id: uuid.UUID, inp: dict, db: AsyncSession) -> dict:
    status = inp.get("status", "all")
    date_from_str = inp.get("date_from")
    date_to_str = inp.get("date_to")
    account_filter = inp.get("account")
    limit = min(int(inp.get("limit", 30)), 100)

    query = (
        select(Booking)
        .where(Booking.client_id == client_id)
        .order_by(Booking.document_date.desc())
        .limit(limit)
    )
    if status != "all":
        query = query.where(Booking.status == status)
    if date_from_str:
        query = query.where(Booking.document_date >= date_from_str)
    if date_to_str:
        query = query.where(Booking.document_date <= date_to_str)
    if account_filter:
        query = query.where(Booking.account == account_filter)

    result = await db.execute(query)
    rows = result.scalars().all()

    return {
        "count": len(rows),
        "bookings": [
            {
                "id": str(b.id),
                "document_date": b.document_date.isoformat(),
                "amount": str(b.amount),
                "debit_credit": b.debit_credit,
                "account": b.account,
                "contra_account": b.contra_account,
                "bu_key": b.bu_key,
                "booking_text": b.booking_text,
                "reference_1": b.reference_1,
                "status": b.status,
                "ai_confidence": str(b.ai_confidence) if b.ai_confidence else None,
                "needs_clarification": b.needs_clarification,
                "clarification_category": b.clarification_category,
                "tax_hints": b.tax_hints,
            }
            for b in rows
        ],
    }


async def _tool_list_documents(client_id: uuid.UUID, inp: dict, db: AsyncSession) -> dict:
    status = inp.get("status", "all")
    limit = min(int(inp.get("limit", 15)), 50)

    query = (
        select(Document)
        .where(Document.client_id == client_id)
        .order_by(Document.uploaded_at.desc())
        .limit(limit)
    )
    if status != "all":
        query = query.where(Document.status == status)

    result = await db.execute(query)
    docs = result.scalars().all()

    return {
        "count": len(docs),
        "documents": [
            {
                "id": str(d.id),
                "filename": d.original_filename,
                "status": d.status,
                "ocr_provider": d.ocr_provider,
                "ocr_confidence": str(d.ocr_confidence) if d.ocr_confidence else None,
                "uploaded_at": d.uploaded_at.isoformat(),
            }
            for d in docs
        ],
    }


async def _tool_get_document_details(document_id: str, db: AsyncSession) -> dict:
    try:
        doc = await db.get(Document, uuid.UUID(document_id))
    except ValueError:
        return {"error": "Ungültige Dokument-ID"}
    if not doc:
        return {"error": "Dokument nicht gefunden"}

    bookings_result = await db.execute(
        select(Booking).where(Booking.document_id == doc.id)
    )
    bookings = bookings_result.scalars().all()

    return {
        "id": str(doc.id),
        "filename": doc.original_filename,
        "status": doc.status,
        "ocr_provider": doc.ocr_provider,
        "ocr_confidence": str(doc.ocr_confidence) if doc.ocr_confidence else None,
        "extraction": doc.extraction,
        "bookings": [
            {
                "id": str(b.id),
                "amount": str(b.amount),
                "debit_credit": b.debit_credit,
                "account": b.account,
                "contra_account": b.contra_account,
                "booking_text": b.booking_text,
                "status": b.status,
                "needs_clarification": b.needs_clarification,
                "clarification_question": b.clarification_question,
            }
            for b in bookings
        ],
    }


async def _tool_approve_booking(booking_id: str, db: AsyncSession) -> dict:
    try:
        booking = await db.get(Booking, uuid.UUID(booking_id))
    except ValueError:
        return {"error": "Ungültige Buchungs-ID"}
    if not booking:
        return {"error": "Buchung nicht gefunden"}
    if booking.status == "approved":
        return {"status": "already_approved", "message": "Buchung war bereits freigegeben"}

    prev_status = booking.status
    booking.status = "approved"
    booking.approved_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="approved",
        performed_by="ai_agent",
        previous_state={"status": prev_status},
        new_state={"status": "approved"},
    ))
    await db.flush()

    return {
        "status": "approved",
        "booking_id": booking_id,
        "amount": str(booking.amount),
        "account": booking.account,
        "booking_text": booking.booking_text,
    }


async def _tool_update_booking(inp: dict, db: AsyncSession) -> dict:
    try:
        booking = await db.get(Booking, uuid.UUID(inp["booking_id"]))
    except ValueError:
        return {"error": "Ungültige Buchungs-ID"}
    if not booking:
        return {"error": "Buchung nicht gefunden"}

    prev = {
        "account": booking.account,
        "contra_account": booking.contra_account,
        "bu_key": booking.bu_key,
        "booking_text": booking.booking_text,
        "amount": str(booking.amount),
        "debit_credit": booking.debit_credit,
    }

    if "account" in inp:
        booking.account = inp["account"]
    if "contra_account" in inp:
        booking.contra_account = inp["contra_account"]
    if "bu_key" in inp:
        booking.bu_key = inp["bu_key"] or None
    if "booking_text" in inp:
        booking.booking_text = (inp["booking_text"] or "")[:60] or None
    if "amount" in inp:
        try:
            booking.amount = Decimal(str(inp["amount"]))
        except InvalidOperation:
            return {"error": f"Ungültiger Betrag: {inp['amount']}"}
    if "debit_credit" in inp:
        booking.debit_credit = inp["debit_credit"]
    if "reference_1" in inp:
        booking.reference_1 = (inp["reference_1"] or "")[:36] or None

    booking.status = "corrected" if booking.status == "approved" else booking.status

    db.add(AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="corrected",
        performed_by="ai_agent",
        previous_state=prev,
        new_state={
            "account": booking.account,
            "contra_account": booking.contra_account,
            "bu_key": booking.bu_key,
            "booking_text": booking.booking_text,
            "amount": str(booking.amount),
        },
    ))
    await db.flush()

    return {"status": "updated", "booking_id": inp["booking_id"]}


async def _tool_create_booking(client_id: uuid.UUID, inp: dict, db: AsyncSession) -> dict:
    try:
        amount = Decimal(str(inp["amount"]))
        doc_date = datetime.strptime(inp["document_date"], "%Y-%m-%d").date()
        document_id = uuid.UUID(inp["document_id"])
    except (ValueError, KeyError) as exc:
        return {"error": f"Ungültige Eingabe: {exc}"}

    booking = Booking(
        document_id=document_id,
        client_id=client_id,
        amount=amount,
        debit_credit=inp["debit_credit"],
        account=inp["account"],
        contra_account=inp["contra_account"],
        document_date=doc_date,
        bu_key=inp.get("bu_key"),
        booking_text=(inp.get("booking_text") or "")[:60] or None,
        reference_1=(inp.get("reference_1") or "")[:36] or None,
        suggested_by="ai_agent",
        status="suggested",
    )
    db.add(booking)
    await db.flush()

    db.add(AuditLog(
        entity_type="booking",
        entity_id=booking.id,
        action="created",
        performed_by="ai_agent",
        new_state={
            "amount": str(amount),
            "account": booking.account,
            "contra_account": booking.contra_account,
            "booking_text": booking.booking_text,
        },
    ))
    await db.flush()

    return {"status": "created", "booking_id": str(booking.id)}


async def _tool_save_skill(client_id: uuid.UUID, inp: dict, db: AsyncSession) -> dict:
    title = (inp.get("title") or "").strip()
    content = (inp.get("content") or "").strip()
    category = inp.get("category", "custom")

    if not title or not content:
        return {"error": "Titel und Inhalt sind erforderlich"}

    skill = await learn_from_chat(
        client_id=client_id,
        title=title,
        content=content,
        category=category,
        db=db,
    )
    return {
        "status": "saved",
        "skill_id": str(skill.id),
        "title": skill.title,
        "category": skill.category,
        "message": f"Regel '{skill.title}' wurde gespeichert und wird bei zukünftigen Buchungen berücksichtigt.",
    }


async def _tool_list_skills(client_id: uuid.UUID, inp: dict, db: AsyncSession) -> dict:
    category = inp.get("category")
    active_only = inp.get("active_only", True)

    query = select(AgentSkill).where(AgentSkill.client_id == client_id)
    if active_only:
        query = query.where(AgentSkill.is_active.is_(True))
    if category:
        query = query.where(AgentSkill.category == category)
    query = query.order_by(AgentSkill.confidence.desc(), AgentSkill.updated_at.desc())

    result = await db.execute(query)
    skills = result.scalars().all()

    return {
        "count": len(skills),
        "skills": [
            {
                "id": str(s.id),
                "title": s.title,
                "category": s.category,
                "source": s.source,
                "confidence": str(s.confidence),
                "usage_count": s.usage_count,
                "is_active": s.is_active,
                "content_preview": s.content[:120] + "..." if len(s.content) > 120 else s.content,
                "created_at": s.created_at.isoformat(),
            }
            for s in skills
        ],
    }


_ENTERTAINMENT_ACCOUNTS = {"4650", "4654", "6640", "6644"}
_GIFT_ACCOUNTS = {"4630", "4635", "6610", "6620"}
_GWG_ACCOUNTS = {"0480", "0670"}
_TRAVEL_ACCOUNTS = {"4660", "6650", "4663", "4664", "6660", "6663", "6664"}
_PHONE_ACCOUNTS = {"4806", "4805", "6805"}
_TRAINING_ACCOUNTS = {"4945", "6821", "4946", "6822"}
_DONATION_ACCOUNTS = {"4920", "6860"}
_VEHICLE_ACCOUNTS = {"4500", "4510", "4520", "4530", "6520", "6530", "6540", "6550"}
_DEPRECIATION_ACCOUNTS = {"4822", "4830", "4831", "4832", "6220", "6221", "6222"}

async def _tool_tax_analysis(client_id: uuid.UUID, inp: dict, db: AsyncSession) -> dict:
    period = inp.get("period")
    focus = inp.get("focus", "all")

    query = (
        select(Booking)
        .where(Booking.client_id == client_id)
        .order_by(Booking.document_date.desc())
    )

    if period:
        if len(period) == 7:  # YYYY-MM
            query = query.where(
                Booking.document_date >= date.fromisoformat(f"{period}-01"),
            )
            year, month = int(period[:4]), int(period[5:7])
            if month == 12:
                next_start = date(year + 1, 1, 1)
            else:
                next_start = date(year, month + 1, 1)
            query = query.where(Booking.document_date < next_start)
        elif len(period) == 4:  # YYYY
            query = query.where(
                Booking.document_date >= date(int(period), 1, 1),
                Booking.document_date <= date(int(period), 12, 31),
            )

    result = await db.execute(query)
    bookings = result.scalars().all()

    if not bookings:
        return {
            "status": "no_data",
            "message": "Keine Buchungen im gewählten Zeitraum gefunden.",
        }

    findings: list[dict] = []
    summary_stats = {
        "total_bookings": len(bookings),
        "total_amount": Decimal("0"),
        "with_tax_hints": 0,
        "missing_tax_hints": 0,
        "partial_deductions": 0,
        "action_required_count": 0,
    }

    for b in bookings:
        summary_stats["total_amount"] += b.amount

        if b.tax_hints:
            summary_stats["with_tax_hints"] += 1
            if b.tax_hints.get("action_required"):
                summary_stats["action_required_count"] += 1
            if b.tax_hints.get("deductibility") == "partial":
                summary_stats["partial_deductions"] += 1
        else:
            summary_stats["missing_tax_hints"] += 1

        if focus in ("all", "deductions"):
            if b.account in _ENTERTAINMENT_ACCOUNTS and not b.tax_hints:
                findings.append({
                    "type": "missing_entertainment_proof",
                    "severity": "warning",
                    "booking_id": str(b.id),
                    "amount": str(b.amount),
                    "date": b.document_date.isoformat(),
                    "account": b.account,
                    "text": b.booking_text,
                    "hint": (
                        "Bewirtungsbuchung ohne steuerliche Hinweise. "
                        "70% absetzbar (§ 4 Abs. 5 Nr. 2 EStG). "
                        "Bewirtungsbeleg mit Teilnehmerliste erforderlich."
                    ),
                })

            if b.account in _ENTERTAINMENT_ACCOUNTS and b.amount < Decimal("60"):
                findings.append({
                    "type": "potential_attention",
                    "severity": "info",
                    "booking_id": str(b.id),
                    "amount": str(b.amount),
                    "date": b.document_date.isoformat(),
                    "account": b.account,
                    "text": b.booking_text,
                    "hint": (
                        f"Betrag {b.amount} EUR < 60 EUR: Ggf. als Aufmerksamkeit 100% "
                        "absetzbar statt nur 70% Bewirtung. Prüfen ob Umkontierung sinnvoll."
                    ),
                })

            if b.account in _GIFT_ACCOUNTS:
                findings.append({
                    "type": "gift_check",
                    "severity": "info",
                    "booking_id": str(b.id),
                    "amount": str(b.amount),
                    "date": b.document_date.isoformat(),
                    "account": b.account,
                    "text": b.booking_text,
                    "hint": (
                        f"Geschenk {b.amount} EUR — 50 EUR/Person/Jahr-Grenze beachten "
                        "(§ 4 Abs. 5 Nr. 1 EStG). Empfänger dokumentiert?"
                    ),
                })

            if b.account in _VEHICLE_ACCOUNTS and not b.tax_hints:
                findings.append({
                    "type": "vehicle_private_share",
                    "severity": "warning",
                    "booking_id": str(b.id),
                    "amount": str(b.amount),
                    "date": b.document_date.isoformat(),
                    "account": b.account,
                    "text": b.booking_text,
                    "hint": (
                        "Kfz-Kosten ohne steuerliche Einordnung. "
                        "Privatanteil via 1%-Regelung oder Fahrtenbuch berücksichtigen "
                        "(§ 6 Abs. 1 Nr. 4 EStG)."
                    ),
                })

            if b.account in _PHONE_ACCOUNTS and not b.tax_hints:
                findings.append({
                    "type": "mixed_use_phone",
                    "severity": "info",
                    "booking_id": str(b.id),
                    "amount": str(b.amount),
                    "date": b.document_date.isoformat(),
                    "account": b.account,
                    "text": b.booking_text,
                    "hint": (
                        "Telefon/Internet: Bei gemischter Nutzung nur betrieblicher Anteil "
                        "absetzbar (typisch 20–50%). Aufteilung dokumentieren."
                    ),
                })

        if focus in ("all", "vat"):
            if (
                b.debit_credit == "S"
                and not b.bu_key
                and b.account not in _DONATION_ACCOUNTS
                and b.amount > Decimal("0")
            ):
                findings.append({
                    "type": "missing_vat_key",
                    "severity": "warning",
                    "booking_id": str(b.id),
                    "amount": str(b.amount),
                    "date": b.document_date.isoformat(),
                    "account": b.account,
                    "text": b.booking_text,
                    "hint": (
                        "Aufwandsbuchung ohne BU-Schlüssel. "
                        "Prüfen ob Vorsteuerabzug möglich ist — ggf. BU-Schlüssel ergänzen."
                    ),
                })

        if focus in ("all", "depreciation"):
            net_amount = b.amount / Decimal("1.19")

            if net_amount <= Decimal("800") and net_amount > Decimal("250"):
                if b.account not in _GWG_ACCOUNTS and b.account not in _DEPRECIATION_ACCOUNTS:
                    if b.tax_hints and b.tax_hints.get("deductibility") != "full":
                        findings.append({
                            "type": "potential_gwg",
                            "severity": "info",
                            "booking_id": str(b.id),
                            "amount": str(b.amount),
                            "date": b.document_date.isoformat(),
                            "account": b.account,
                            "text": b.booking_text,
                            "hint": (
                                f"Nettobetrag ca. {net_amount:.2f} EUR liegt im GWG-Bereich "
                                "(250–800 EUR). Sofortabzug nach § 6 Abs. 2 EStG möglich."
                            ),
                        })

    year_end_tips: list[str] = []
    if focus in ("all", "year_end"):
        today = date.today()
        analysis_year = int(period[:4]) if period and len(period) >= 4 else today.year
        if today.month >= 10 and today.year == analysis_year:
            year_end_tips = [
                "IAB bilden: 50% der geplanten Anschaffungskosten vorab als Gewinnminderung (§ 7g Abs. 1 EStG)",
                "GWG-Käufe vorziehen: Sofortabzug bis 800 EUR netto noch im laufenden Jahr",
                "Sonderabschreibung prüfen: 20% im Jahr der Anschaffung zusätzlich zur regulären AfA (§ 7g Abs. 5 EStG)",
                "Spenden-Grenze prüfen: Noch Spielraum bis 20% des Gesamtbetrags der Einkünfte?",
                "Rückstellungen bilden: Erwartete Aufwendungen (Jahresabschluss, Prozesskosten) rückstellen",
                "Vorauszahlungen im Dezember leisten: Versicherungen, Miete → Aufwand im laufenden Jahr",
            ]

    findings.sort(key=lambda f: {"warning": 0, "info": 1}.get(f.get("severity", "info"), 2))

    return {
        "status": "ok",
        "period": period or "gesamter Zeitraum",
        "focus": focus,
        "summary": {
            "total_bookings": summary_stats["total_bookings"],
            "total_amount": str(summary_stats["total_amount"]),
            "bookings_with_tax_hints": summary_stats["with_tax_hints"],
            "bookings_missing_tax_hints": summary_stats["missing_tax_hints"],
            "partial_deductions": summary_stats["partial_deductions"],
            "actions_required": summary_stats["action_required_count"],
        },
        "findings_count": len(findings),
        "findings": findings[:30],
        "year_end_tips": year_end_tips,
    }


async def _dispatch_tool(
    name: str, inp: dict, client_id: uuid.UUID, db: AsyncSession
) -> dict:
    try:
        if name == "get_client_overview":
            return await _tool_get_client_overview(client_id, db)
        if name == "list_bookings":
            return await _tool_list_bookings(client_id, inp, db)
        if name == "list_documents":
            return await _tool_list_documents(client_id, inp, db)
        if name == "get_document_details":
            return await _tool_get_document_details(inp["document_id"], db)
        if name == "approve_booking":
            return await _tool_approve_booking(inp["booking_id"], db)
        if name == "update_booking":
            return await _tool_update_booking(inp, db)
        if name == "create_booking":
            return await _tool_create_booking(client_id, inp, db)
        if name == "execute_python":
            return await execute_python(inp["code"], context_data=inp.get("context_data"))
        if name == "web_search":
            return await search_accounting(inp["query"], topic=inp.get("topic", "general"))
        if name == "validate_vat_id":
            return await validate_vat_id(inp["vat_id"])
        if name == "save_skill":
            return await _tool_save_skill(client_id, inp, db)
        if name == "list_skills":
            return await _tool_list_skills(client_id, inp, db)
        if name == "tax_analysis":
            return await _tool_tax_analysis(client_id, inp, db)
        return {"error": f"Unbekanntes Tool: {name}"}
    except Exception as exc:
        logger.exception("Tool %s failed", name)
        return {"error": str(exc)}


# ── System prompt ─────────────────────────────────────────────────────────────

async def _build_system_prompt(
    client: Client, client_id: uuid.UUID, db: AsyncSession
) -> str:
    today = date.today().strftime("%d.%m.%Y")

    skills_section = ""
    try:
        skills = await get_relevant_skills(client_id, {}, db)
        if skills:
            joined = "\n\n".join(skills)
            skills_section = (
                f"\n\n## Gelernte Regeln für diesen Mandanten\n"
                f"Beachte diese mandantenspezifischen Regeln bei Buchungsvorschlägen:\n\n"
                f"{joined}\n"
            )
    except Exception:
        logger.exception("Failed to load skills for chat system prompt")

    return (
        f"Du bist ein erfahrener Buchhalter-Assistent. "
        f"Du arbeitest für den Mandanten: **{client.company_name}** "
        f"({client.legal_form or 'Rechtsform unbekannt'}, Kontenrahmen {client.chart_of_accounts}).\n"
        f"Heute ist der {today}.\n\n"
        "Du kannst Buchungen einsehen, freigeben und korrigieren, Belege abrufen, "
        "neue Buchungen erstellen und Python-Code ausführen für Berechnungen, Analysen und Auswertungen. "
        "Die Code-Sandbox hat pandas, numpy, matplotlib und openpyxl — nutze sie für "
        "Pivot-Tabellen, Summenanalysen, BWA-Auswertungen, Charts und Excel-Exporte. "
        "Du kannst Buchungsdaten als context_data an execute_python übergeben und im Code als CONTEXT_DATA nutzen. "
        "Dateien nach OUTPUT_DIR schreiben — sie werden automatisch als Download bereitgestellt. "
        "Nutze deine Tools proaktiv — wenn jemand etwas fragt, das Daten erfordert, hol sie dir zuerst. "
        "Bei steuerlichen oder rechtlichen Fragen nutze web_search um aktuelle Informationen zu finden "
        "und nenne die Quelle in deiner Antwort. "
        "Erkläre was du tust, aber halte es knapp. Antworte auf Deutsch. "
        "Bei unklaren Anweisungen frag kurz nach, bevor du handelst.\n\n"
        "**Lernfähigkeit:** Wenn der Benutzer dir eine neue Buchungsregel, Kontenzuordnung oder "
        "ein Muster mitteilt (z.B. 'LinkedIn ist immer Werbung auf 4600'), nutze save_skill um "
        "diese Regel für zukünftige Buchungen zu speichern. Bestätige dem Benutzer kurz, dass "
        "du dir die Regel gemerkt hast.\n\n"
        "**Steueroptimierung:** Wenn der Benutzer nach Steuersparmöglichkeiten, Absetzbarkeit, "
        "steuerlicher Optimierung oder einem Steuer-Check fragt, nutze das tax_analysis Tool. "
        "Präsentiere die Ergebnisse strukturiert: zuerst eine Zusammenfassung, dann die wichtigsten "
        "Findings (Warnungen vor Infos), dann konkrete Handlungsempfehlungen. "
        "Bei Jahresende-Tipps weise besonders auf IAB, vorgezogene Investitionen und Spenden-Grenzen hin."
        f"{skills_section}"
    )


# ── Streaming agent loop ──────────────────────────────────────────────────────

async def run_agent_stream(
    messages: list[dict],
    db: AsyncSession,
    client: Client,
    client_id: uuid.UUID,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that yields SSE-ready dicts:
      {"type": "text",       "delta": "..."}
      {"type": "tool_start", "tool": "...", "label": "..."}
      {"type": "tool_end",   "tool": "..."}
      {"type": "done"}
    """
    from app.services import llm_service

    system = await _build_system_prompt(client, client_id, db)

    litellm_tools = [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}),
            },
        }
        for t in TOOLS
    ]

    for _turn in range(15):
        full_content = ""
        tool_calls_acc: dict[int, dict] = {}

        async for chunk in llm_service.stream_completion(
            client_id, db,
            operation="chat",
            messages=messages,
            system=system,
            max_tokens=8192,
            tools=litellm_tools,
        ):
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            if delta.content:
                full_content += delta.content
                yield {"type": "text", "delta": delta.content}

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["name"] = tc.function.name
                            yield {
                                "type": "tool_start",
                                "tool": tc.function.name,
                                "label": TOOL_LABELS.get(tc.function.name, tc.function.name),
                            }
                        if tc.function.arguments:
                            tool_calls_acc[idx]["arguments"] += tc.function.arguments

        if not tool_calls_acc:
            break

        assistant_msg: dict = {"role": "assistant"}
        if full_content:
            assistant_msg["content"] = full_content
        if tool_calls_acc:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_calls_acc.values()
            ]
        messages.append(assistant_msg)

        for tc_data in tool_calls_acc.values():
            try:
                tool_input = json.loads(tc_data["arguments"])
            except json.JSONDecodeError:
                tool_input = {}

            result = await _dispatch_tool(tc_data["name"], tool_input, client_id, db)
            if tc_data["name"] in ("approve_booking", "update_booking", "create_booking", "save_skill"):
                await db.commit()
            yield {"type": "tool_end", "tool": tc_data["name"]}

            messages.append({
                "role": "tool",
                "tool_call_id": tc_data["id"],
                "content": json.dumps(result, default=str, ensure_ascii=False),
            })

    yield {"type": "done"}

"""Autonomous background supervisor agent.

Runs periodically and performs:
1. OCR self-healing  — retries failed documents with alternative strategies
2. Booking validation — checks all suggested bookings for issues
3. Stale detection     — flags documents stuck in processing
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session
from app.models.agent_notification import AgentNotification
from app.models.agent_run import AgentRun
from app.models.agent_skill import AgentSkill
from app.models.booking import Booking
from app.models.client import Client
from app.models.document import Document
from app.services.booking_validator import ValidationIssue, validate_client_bookings

logger = logging.getLogger(__name__)

_OCR_STRATEGIES = [
    {"name": "mistral_retry", "description": "Erneuter Mistral-OCR-Versuch"},
    {"name": "claude_vision", "description": "Claude Vision als primärer OCR-Provider"},
    {"name": "claude_vision_enhanced", "description": "Claude Vision mit erweitertem Prompt"},
]


class Supervisor:
    """Autonomous agent that monitors and self-heals the accounting pipeline."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if not settings.supervisor_enabled:
            logger.info("Supervisor is disabled via config")
            return
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Supervisor started — interval %ds", settings.supervisor_interval_seconds
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Supervisor stopped")

    async def _loop(self) -> None:
        await asyncio.sleep(10)
        while self._running:
            try:
                await self._run_cycle()
            except Exception:
                logger.exception("Supervisor cycle failed")
            await asyncio.sleep(settings.supervisor_interval_seconds)

    async def _run_cycle(self) -> None:
        async with async_session() as db:
            clients = await self._get_active_clients(db)
            for client in clients:
                try:
                    await self._process_client(db, client)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.exception(
                        "Supervisor failed for client %s", client.id
                    )

    async def _get_active_clients(self, db: AsyncSession) -> list[Client]:
        result = await db.execute(select(Client).order_by(Client.company_name))
        return list(result.scalars().all())

    async def _process_client(self, db: AsyncSession, client: Client) -> None:
        await self._heal_failed_documents(db, client)
        await self._validate_bookings(db, client)
        await self._detect_stale_documents(db, client)
        await self._check_tax_optimization(db, client)
        await self._learn_from_validation_patterns(db, client)
        await self._learn_from_ocr_patterns(db, client)
        await self._prune_stale_skills(db, client)

    # ------------------------------------------------------------------
    # 1. OCR Self-Healing
    # ------------------------------------------------------------------

    async def _heal_failed_documents(
        self, db: AsyncSession, client: Client
    ) -> None:
        result = await db.execute(
            select(Document)
            .where(
                Document.client_id == client.id,
                Document.status.in_(["ocr_failed", "booking_failed"]),
            )
            .order_by(Document.uploaded_at)
        )
        failed_docs = list(result.scalars().all())
        if not failed_docs:
            return

        for doc in failed_docs:
            attempt = await self._count_previous_attempts(db, client.id, doc.id)
            if attempt >= settings.supervisor_max_ocr_retries:
                await self._escalate_to_human(
                    db, client.id, doc,
                    f"Dokument '{doc.original_filename}' konnte nach "
                    f"{attempt} Versuchen nicht verarbeitet werden. "
                    f"Letzter Fehler: {doc.error_details or 'unbekannt'}",
                )
                continue

            strategy = _OCR_STRATEGIES[min(attempt, len(_OCR_STRATEGIES) - 1)]
            await self._retry_document(db, client, doc, strategy, attempt + 1)

    async def _count_previous_attempts(
        self, db: AsyncSession, client_id: uuid.UUID, doc_id: uuid.UUID
    ) -> int:
        result = await db.execute(
            select(func.count(AgentRun.id)).where(
                AgentRun.client_id == client_id,
                AgentRun.target_entity_type == "document",
                AgentRun.target_entity_id == doc_id,
                AgentRun.run_type == "ocr_self_healing",
            )
        )
        return result.scalar_one()

    async def _retry_document(
        self,
        db: AsyncSession,
        client: Client,
        doc: Document,
        strategy: dict,
        attempt: int,
    ) -> None:
        t0 = time.monotonic()
        run = AgentRun(
            client_id=client.id,
            run_type="ocr_self_healing",
            target_entity_type="document",
            target_entity_id=doc.id,
            status="running",
            strategy=strategy["name"],
            attempt_number=attempt,
        )
        db.add(run)
        await db.flush()

        logger.info(
            "Supervisor: retrying document %s with strategy '%s' (attempt %d)",
            doc.id, strategy["name"], attempt,
        )

        try:
            from app.graph.workflow import run_document_workflow

            doc.status = "ocr_processing"
            doc.error_details = None
            await db.flush()

            final_state = await run_document_workflow(doc.id, db)
            elapsed = int((time.monotonic() - t0) * 1000)

            new_status = final_state.get("status", "unknown")
            run.status = "success" if new_status == "booking_suggested" else "failed"
            run.result_summary = f"Status nach Retry: {new_status}"
            run.completed_at = datetime.now(timezone.utc)
            run.duration_ms = elapsed
            run.details = {
                "new_status": new_status,
                "ocr_confidence": final_state.get("ocr_confidence"),
                "booking_count": len(final_state.get("suggested_bookings", [])),
            }

            if new_status == "booking_suggested":
                run.items_fixed = 1
                await self._notify(
                    db, client.id, run.id,
                    severity="success",
                    category="ocr_self_healing",
                    title=f"Dokument erfolgreich wiederhergestellt",
                    message=(
                        f"'{doc.original_filename}' wurde im {attempt}. Versuch "
                        f"erfolgreich verarbeitet (Strategie: {strategy['description']}). "
                        f"{len(final_state.get('suggested_bookings', []))} Buchungsvorschläge erstellt."
                    ),
                    entity_type="document",
                    entity_id=doc.id,
                )
            else:
                run.items_flagged = 1

        except Exception as e:
            elapsed = int((time.monotonic() - t0) * 1000)
            run.status = "failed"
            run.error = str(e)
            run.completed_at = datetime.now(timezone.utc)
            run.duration_ms = elapsed
            logger.exception("Supervisor OCR retry failed for %s", doc.id)

    # ------------------------------------------------------------------
    # 2. Booking Validation
    # ------------------------------------------------------------------

    async def _validate_bookings(
        self, db: AsyncSession, client: Client
    ) -> None:
        t0 = time.monotonic()
        chart = client.chart_of_accounts or "SKR03"

        issues = await validate_client_bookings(
            db, str(client.id), chart, only_status="suggested",
            industry=client.industry,
        )
        if not issues:
            return

        elapsed = int((time.monotonic() - t0) * 1000)
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]

        run = AgentRun(
            client_id=client.id,
            run_type="booking_validation",
            status="completed",
            result_summary=(
                f"{len(errors)} Fehler, {len(warnings)} Warnungen "
                f"bei vorgeschlagenen Buchungen gefunden"
            ),
            items_checked=len(set(i.booking_id for i in issues)),
            items_flagged=len(errors) + len(warnings),
            items_fixed=0,
            completed_at=datetime.now(timezone.utc),
            duration_ms=elapsed,
            details={
                "errors": [
                    {"booking_id": i.booking_id, "rule": i.rule, "message": i.message}
                    for i in errors
                ],
                "warnings": [
                    {"booking_id": i.booking_id, "rule": i.rule, "message": i.message}
                    for i in warnings
                ],
            },
        )
        db.add(run)
        await db.flush()

        if errors:
            error_summary = "\n".join(
                f"• {e.message}" for e in errors[:5]
            )
            if len(errors) > 5:
                error_summary += f"\n… und {len(errors) - 5} weitere Fehler"

            await self._notify(
                db, client.id, run.id,
                severity="error",
                category="booking_validation",
                title=f"{len(errors)} Buchungsfehler gefunden",
                message=(
                    f"Bei der automatischen Prüfung der Buchungsvorschläge "
                    f"wurden {len(errors)} Fehler gefunden:\n\n{error_summary}"
                ),
                action_required=True,
                action_type="review_bookings",
            )

        bank_warnings = [w for w in warnings if w.rule == "missing_bank_payment"]
        other_warnings = [w for w in warnings if w.rule != "missing_bank_payment"]

        if bank_warnings:
            bank_summary = "\n".join(
                f"• {w.message}" for w in bank_warnings[:5]
            )
            if len(bank_warnings) > 5:
                bank_summary += f"\n… und {len(bank_warnings) - 5} weitere"
            await self._notify(
                db, client.id, run.id,
                severity="warning",
                category="missing_bank_link",
                title=f"{len(bank_warnings)} Buchung(en) ohne Bankverknüpfung",
                message=(
                    f"Der Prüfer hat {len(bank_warnings)} Buchung(en) gefunden, "
                    f"die gegen ein Kreditorenkonto gebucht sind, aber keine "
                    f"zugehörige Bankbuchung haben:\n\n{bank_summary}\n\n"
                    f"Bitte prüfen Sie: Fehlt ein Kontoauszug? Wurde bar bezahlt? "
                    f"Oder ist die Rechnung noch offen?"
                ),
                action_required=True,
                action_type="review_bookings",
            )

        if other_warnings and not errors:
            warn_summary = "\n".join(
                f"• {w.message}" for w in other_warnings[:5]
            )
            await self._notify(
                db, client.id, run.id,
                severity="warning",
                category="booking_validation",
                title=f"{len(other_warnings)} Hinweise zu Buchungen",
                message=(
                    f"Bei der Buchungsprüfung wurden {len(other_warnings)} Hinweise gefunden:\n\n"
                    f"{warn_summary}"
                ),
            )

    # ------------------------------------------------------------------
    # 3. Stale Document Detection
    # ------------------------------------------------------------------

    async def _detect_stale_documents(
        self, db: AsyncSession, client: Client
    ) -> None:
        threshold = datetime.now(timezone.utc) - timedelta(minutes=15)
        result = await db.execute(
            select(Document).where(
                Document.client_id == client.id,
                Document.status == "ocr_processing",
                Document.uploaded_at < threshold,
            )
        )
        stale_docs = list(result.scalars().all())
        if not stale_docs:
            return

        for doc in stale_docs:
            doc.status = "ocr_failed"
            doc.error_details = "Timeout: Verarbeitung dauerte länger als 15 Minuten"

            await self._notify(
                db, client.id, None,
                severity="warning",
                category="stale_detection",
                title=f"Dokument hängt fest",
                message=(
                    f"'{doc.original_filename}' ist seit über 15 Minuten "
                    f"im Status 'Verarbeitung'. Der Status wurde auf 'fehlgeschlagen' "
                    f"gesetzt. Der Agent wird einen erneuten Versuch starten."
                ),
                entity_type="document",
                entity_id=doc.id,
            )

    # ------------------------------------------------------------------
    # 4. Tax Optimization Checks
    # ------------------------------------------------------------------

    _ENTERTAINMENT_ACCOUNTS = {"4650", "4654"}
    _GWG_ACCOUNTS = {"0480", "0670"}
    _ASSET_ACCOUNTS_RANGE = range(1, 1000)
    _MIXED_USE_ACCOUNTS = {
        "4920": "Telefon",
        "4921": "Telefon",
        "4930": "Internet/Kommunikation",
        "6805": "Telefon/Internet",
        "4570": "Kfz-Kosten",
        "4580": "Kfz-Versicherung",
        "4510": "Kfz-Steuer",
        "4520": "Kfz-Leasingkosten",
    }
    _VAT_BU_KEYS = {"2", "3", "8", "9"}

    async def _check_tax_optimization(
        self, db: AsyncSession, client: Client
    ) -> None:
        result = await db.execute(
            select(Booking).where(
                Booking.client_id == client.id,
                Booking.status.in_(["suggested", "approved"]),
            )
        )
        bookings = list(result.scalars().all())
        if not bookings:
            return

        t0 = time.monotonic()
        findings: list[dict] = []

        for b in bookings:
            findings.extend(self._tax_check_entertainment(b))
            findings.extend(self._tax_check_gwg_vs_asset(b))
            findings.extend(self._tax_check_missing_vat(b, client))
            findings.extend(self._tax_check_mixed_use(b))

        findings.extend(self._tax_check_year_end(bookings))

        if not findings:
            return

        elapsed = int((time.monotonic() - t0) * 1000)

        run = AgentRun(
            client_id=client.id,
            run_type="tax_optimization",
            status="completed",
            result_summary=f"{len(findings)} steuerliche Optimierungshinweise gefunden",
            items_checked=len(bookings),
            items_flagged=len(findings),
            items_fixed=0,
            completed_at=datetime.now(timezone.utc),
            duration_ms=elapsed,
            details={"findings": findings[:50]},
        )
        db.add(run)
        await db.flush()

        grouped: dict[str, list[dict]] = {}
        for f in findings:
            grouped.setdefault(f["check"], []).append(f)

        for check_type, items in grouped.items():
            title, severity = self._tax_notification_meta(check_type, len(items))
            summary = "\n".join(f"• {i['message']}" for i in items[:5])
            if len(items) > 5:
                summary += f"\n… und {len(items) - 5} weitere"

            await self._notify(
                db, client.id, run.id,
                severity=severity,
                category="tax_optimization",
                title=title,
                message=summary,
                action_required=severity in ("warning", "error"),
                action_type="review_bookings" if severity != "info" else None,
            )

    def _tax_check_entertainment(self, b: Booking) -> list[dict]:
        """Bewirtungskosten auf 4654/4650 ohne Bewirtungsbeleg-Hinweis."""
        if b.account not in self._ENTERTAINMENT_ACCOUNTS:
            return []

        hints = b.tax_hints or {}
        if hints.get("deductibility") == "partial" and hints.get("action_required"):
            return []

        if b.needs_clarification and b.clarification_category == "entertainment_receipt":
            return []

        return [{
            "check": "entertainment_no_receipt",
            "booking_id": str(b.id),
            "message": (
                f"Bewirtung ({b.account}) über {b.amount} EUR "
                f"('{b.booking_text or ''}', {b.document_date}) — "
                f"nur 70% absetzbar (§4 Abs. 5 Nr. 2 EStG). "
                f"Bewirtungsbeleg mit Teilnehmerliste erforderlich."
            ),
        }]

    def _tax_check_gwg_vs_asset(self, b: Booking) -> list[dict]:
        """Beträge 250-800 EUR netto: GWG sofort absetzbar statt Aktivierung."""
        try:
            acct_num = int(b.account)
        except (ValueError, TypeError):
            return []

        is_asset = acct_num in self._ASSET_ACCOUNTS_RANGE
        is_gwg = b.account in self._GWG_ACCOUNTS
        amount = b.amount

        if is_asset and Decimal("250") <= amount <= Decimal("800"):
            return [{
                "check": "gwg_vs_asset",
                "booking_id": str(b.id),
                "message": (
                    f"Anlagenkonto {b.account} mit {amount} EUR netto "
                    f"('{b.booking_text or ''}') — als GWG (Konto 0480/0670) "
                    f"sofort absetzbar statt über Nutzungsdauer abzuschreiben "
                    f"(§6 Abs. 2 EStG, Grenze 800 EUR netto)."
                ),
            }]

        if is_gwg and amount > Decimal("800"):
            return [{
                "check": "gwg_over_limit",
                "booking_id": str(b.id),
                "message": (
                    f"GWG-Konto {b.account} mit {amount} EUR — übersteigt die "
                    f"GWG-Grenze von 800 EUR netto. Muss als Anlage aktiviert "
                    f"und über Nutzungsdauer abgeschrieben werden."
                ),
            }]

        return []

    def _tax_check_missing_vat(self, b: Booking, client: Client) -> list[dict]:
        """Eingangsrechnungen ohne BU-Schlüssel obwohl USt-pflichtig."""
        try:
            contra_num = int(b.contra_account)
        except (ValueError, TypeError):
            return []

        is_creditor = contra_num >= 70000
        if not is_creditor:
            return []

        try:
            acct_num = int(b.account)
        except (ValueError, TypeError):
            return []

        is_expense = 3000 <= acct_num <= 6999

        if not is_expense:
            return []

        if b.bu_key and b.bu_key.strip() in self._VAT_BU_KEYS:
            return []

        hints = b.tax_hints or {}
        if hints.get("deductibility") == "none":
            return []

        if b.amount < Decimal("50"):
            return []

        return [{
            "check": "missing_vat",
            "booking_id": str(b.id),
            "message": (
                f"Eingangsrechnung auf Konto {b.account} gegen Kreditor "
                f"{b.contra_account} ({b.amount} EUR, '{b.booking_text or ''}') "
                f"ohne BU-Schlüssel — Vorsteuerabzug geht verloren. "
                f"Prüfen: BU 9 (19%) oder BU 8 (7%) ergänzen."
            ),
        }]

    def _tax_check_mixed_use(self, b: Booking) -> list[dict]:
        """Bekannte Mischkosten (Telefon, Kfz) ohne Privatanteil-Aufteilung."""
        label = self._MIXED_USE_ACCOUNTS.get(b.account)
        if not label:
            return []

        hints = b.tax_hints or {}
        if hints.get("deductibility") == "partial":
            return []

        text = (b.booking_text or "").lower()
        if "privat" in text or "anteil" in text:
            return []

        return [{
            "check": "mixed_use_no_split",
            "booking_id": str(b.id),
            "message": (
                f"{label} (Konto {b.account}, {b.amount} EUR, "
                f"'{b.booking_text or ''}') — bei gemischter privater/"
                f"geschäftlicher Nutzung muss der Privatanteil ausgebucht "
                f"werden. Typisch: 20-50% bei Telefon/Internet, "
                f"Fahrtenbuch oder 1%-Regel bei Kfz."
            ),
        }]

    def _tax_check_year_end(self, bookings: list[Booking]) -> list[dict]:
        """Jahresende-Optimierungen (Oktober-Dezember)."""
        now = datetime.now(timezone.utc)
        if now.month < 10:
            return []

        current_year = now.year
        year_bookings = [
            b for b in bookings
            if b.document_date and b.document_date.year == current_year
        ]
        if not year_bookings:
            return []

        findings: list[dict] = []

        total_assets = Decimal("0")
        for b in year_bookings:
            try:
                acct_num = int(b.account)
            except (ValueError, TypeError):
                continue
            if acct_num in self._ASSET_ACCOUNTS_RANGE:
                total_assets += b.amount

        if total_assets > Decimal("0"):
            findings.append({
                "check": "year_end_iab",
                "booking_id": "",
                "message": (
                    f"Jahresende-Optimierung: Investitionsabzugsbetrag (IAB) "
                    f"prüfen — bis zu 50% der geplanten Anschaffungskosten "
                    f"für {current_year + 1} können vorab gewinnmindernd "
                    f"berücksichtigt werden (§7g EStG). "
                    f"Bisherige Anlage-Investitionen {current_year}: "
                    f"{total_assets} EUR."
                ),
            })

        gwg_potential = [
            b for b in year_bookings
            if b.account in self._GWG_ACCOUNTS
        ]
        total_gwg = sum((b.amount for b in gwg_potential), Decimal("0"))
        if total_gwg > Decimal("0"):
            findings.append({
                "check": "year_end_depreciation",
                "booking_id": "",
                "message": (
                    f"Sonderabschreibung nach §7g Abs. 5 EStG prüfen: "
                    f"20% zusätzliche Abschreibung im Anschaffungsjahr "
                    f"für GWG und neue Anlagen möglich. "
                    f"GWG-Summe {current_year}: {total_gwg} EUR."
                ),
            })

        total_expenses = Decimal("0")
        for b in year_bookings:
            try:
                acct_num = int(b.account)
            except (ValueError, TypeError):
                continue
            if 4000 <= acct_num <= 6999:
                total_expenses += b.amount

        if total_expenses > Decimal("5000"):
            findings.append({
                "check": "year_end_prepull",
                "booking_id": "",
                "message": (
                    f"Jahresende-Tipp: Geplante Ausgaben für Anfang "
                    f"{current_year + 1} noch in {current_year} tätigen, "
                    f"um den Gewinn zu reduzieren (z.B. Büromaterial, "
                    f"Fachliteratur, Wartungsverträge). "
                    f"Bisherige Betriebsausgaben: {total_expenses} EUR."
                ),
            })

        return findings

    @staticmethod
    def _tax_notification_meta(check_type: str, count: int) -> tuple[str, str]:
        meta: dict[str, tuple[str, str]] = {
            "entertainment_no_receipt": (
                f"{count} Bewirtung(en) ohne Belegnachweis",
                "warning",
            ),
            "gwg_vs_asset": (
                f"{count} mögliche GWG-Sofortabschreibung(en)",
                "info",
            ),
            "gwg_over_limit": (
                f"{count} GWG-Buchung(en) über 800 EUR Grenze",
                "warning",
            ),
            "missing_vat": (
                f"{count} Eingangsrechnung(en) ohne Vorsteuer-Schlüssel",
                "warning",
            ),
            "mixed_use_no_split": (
                f"{count} Mischkosten ohne Privatanteil-Aufteilung",
                "info",
            ),
            "year_end_iab": (
                "Jahresende: Investitionsabzugsbetrag prüfen",
                "info",
            ),
            "year_end_depreciation": (
                "Jahresende: Sonderabschreibung möglich",
                "info",
            ),
            "year_end_prepull": (
                "Jahresende: Ausgaben vorziehen",
                "info",
            ),
        }
        return meta.get(check_type, (f"{count} steuerliche Hinweise", "info"))

    # ------------------------------------------------------------------
    # 5. Learn Skills from Validation Patterns
    # ------------------------------------------------------------------

    async def _learn_from_validation_patterns(
        self, db: AsyncSession, client: Client
    ) -> None:
        """Analyse recent validation runs for recurring issues and create skills."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await db.execute(
            select(AgentRun)
            .where(
                AgentRun.client_id == client.id,
                AgentRun.run_type == "booking_validation",
                AgentRun.started_at > cutoff,
                AgentRun.details.isnot(None),
            )
            .order_by(AgentRun.started_at.desc())
            .limit(20)
        )
        recent_runs = list(result.scalars().all())
        if len(recent_runs) < 3:
            return

        rule_counter: Counter[str] = Counter()
        rule_messages: dict[str, str] = {}
        for run in recent_runs:
            details = run.details or {}
            for issue in [*details.get("errors", []), *details.get("warnings", [])]:
                rule = issue.get("rule", "")
                if rule:
                    rule_counter[rule] += 1
                    rule_messages.setdefault(rule, issue.get("message", ""))

        for rule, count in rule_counter.items():
            if count < 3:
                continue

            skill_key = f"prüfer:validation_pattern:{rule}"
            existing = await db.execute(
                select(AgentSkill).where(
                    AgentSkill.client_id == client.id,
                    AgentSkill.skill_key == skill_key,
                )
            )
            if existing.scalar_one_or_none():
                continue

            msg = rule_messages.get(rule, rule)
            skill = AgentSkill(
                client_id=client.id,
                skill_key=skill_key,
                category="correction_pattern",
                title=f"Häufiges Problem: {rule.replace('_', ' ').title()}",
                content=(
                    f"Der Prüfer hat dieses Problem {count}x in den letzten 24h erkannt:\n"
                    f"{msg}\n\n"
                    f"Berücksichtige diese Information bei zukünftigen Buchungsvorschlägen, "
                    f"um den Fehler zu vermeiden."
                ),
                source="prüfer_validation",
                confidence=Decimal("0.65"),
            )
            db.add(skill)
            logger.info(
                "Prüfer learned validation pattern '%s' (%dx) for client %s",
                rule, count, client.id,
            )

        await db.flush()

    # ------------------------------------------------------------------
    # 6. Learn OCR Patterns
    # ------------------------------------------------------------------

    async def _learn_from_ocr_patterns(
        self, db: AsyncSession, client: Client
    ) -> None:
        """Detect which OCR strategies work best for this client and create skills."""
        result = await db.execute(
            select(AgentRun)
            .where(
                AgentRun.client_id == client.id,
                AgentRun.run_type == "ocr_self_healing",
            )
            .order_by(AgentRun.started_at.desc())
            .limit(50)
        )
        ocr_runs = list(result.scalars().all())
        if len(ocr_runs) < 5:
            return

        strategy_stats: dict[str, dict[str, int]] = {}
        for run in ocr_runs:
            strat = run.strategy or "unknown"
            stats = strategy_stats.setdefault(strat, {"success": 0, "fail": 0})
            if run.status == "success":
                stats["success"] += 1
            else:
                stats["fail"] += 1

        best_strategy = None
        best_rate = 0.0
        for strat, stats in strategy_stats.items():
            total = stats["success"] + stats["fail"]
            if total < 3:
                continue
            rate = stats["success"] / total
            if rate > best_rate:
                best_rate = rate
                best_strategy = strat

        if not best_strategy or best_rate < 0.4:
            return

        skill_key = f"prüfer:ocr_preference:{client.id}"
        existing = await db.execute(
            select(AgentSkill).where(
                AgentSkill.client_id == client.id,
                AgentSkill.skill_key == skill_key,
            )
        )
        skill = existing.scalar_one_or_none()

        content = (
            f"OCR-Analyse: Strategie '{best_strategy}' hat die beste Erfolgsrate "
            f"({best_rate:.0%}) für diesen Mandanten.\n"
            f"Statistiken: {dict(strategy_stats)}\n\n"
            f"Bei OCR-Problemen bevorzugt '{best_strategy}' verwenden."
        )

        if skill:
            skill.content = content
            skill.confidence = min(Decimal(str(round(best_rate, 2))), Decimal("0.95"))
        else:
            db.add(AgentSkill(
                client_id=client.id,
                skill_key=skill_key,
                category="correction_pattern",
                title=f"OCR-Präferenz: {best_strategy}",
                content=content,
                source="prüfer_ocr_analysis",
                confidence=Decimal(str(round(min(best_rate, 0.95), 2))),
            ))
            logger.info(
                "Prüfer learned OCR preference '%s' (%.0f%%) for client %s",
                best_strategy, best_rate * 100, client.id,
            )

        await db.flush()

    # ------------------------------------------------------------------
    # 7. Skill Quality Monitoring
    # ------------------------------------------------------------------

    async def _prune_stale_skills(
        self, db: AsyncSession, client: Client
    ) -> None:
        """Deactivate skills with low confidence that have never been used."""
        result = await db.execute(
            select(AgentSkill).where(
                AgentSkill.client_id == client.id,
                AgentSkill.is_active.is_(True),
            )
        )
        all_skills = list(result.scalars().all())
        if not all_skills:
            return

        now = datetime.now(timezone.utc)
        deactivated = 0

        for skill in all_skills:
            age_days = (now - skill.created_at.replace(tzinfo=timezone.utc)).days

            if (
                skill.usage_count == 0
                and age_days > 14
                and skill.confidence < Decimal("0.50")
            ):
                skill.is_active = False
                deactivated += 1
                logger.info(
                    "Prüfer deactivated unused low-confidence skill '%s' (age %dd, conf %s)",
                    skill.skill_key, age_days, skill.confidence,
                )

            elif (
                skill.usage_count == 0
                and age_days > 30
                and skill.source not in ("industry_starter", "chat_instruction")
            ):
                skill.is_active = False
                deactivated += 1
                logger.info(
                    "Prüfer deactivated never-used skill '%s' (age %dd)",
                    skill.skill_key, age_days,
                )

            elif skill.confidence < Decimal("0.20"):
                skill.is_active = False
                deactivated += 1
                logger.info(
                    "Prüfer deactivated very-low-confidence skill '%s' (conf %s)",
                    skill.skill_key, skill.confidence,
                )

        if deactivated > 0:
            await db.flush()
            await self._notify(
                db, client.id, None,
                severity="info",
                category="skill_maintenance",
                title=f"{deactivated} Skill(s) deaktiviert",
                message=(
                    f"Der Prüfer hat {deactivated} veraltete oder ungenutzte "
                    f"Regeln automatisch deaktiviert. Sie können sie in der "
                    f"Skill-Verwaltung jederzeit wieder aktivieren."
                ),
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _escalate_to_human(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        doc: Document,
        message: str,
    ) -> None:
        existing = await db.execute(
            select(func.count(AgentNotification.id)).where(
                AgentNotification.client_id == client_id,
                AgentNotification.entity_type == "document",
                AgentNotification.entity_id == doc.id,
                AgentNotification.category == "escalation",
                AgentNotification.is_resolved == False,
            )
        )
        if existing.scalar_one() > 0:
            return

        await self._notify(
            db, client_id, None,
            severity="error",
            category="escalation",
            title=f"Menschliche Hilfe benötigt: {doc.original_filename}",
            message=message,
            entity_type="document",
            entity_id=doc.id,
            action_required=True,
            action_type="manual_review",
        )

    async def _notify(
        self,
        db: AsyncSession,
        client_id: uuid.UUID,
        run_id: uuid.UUID | None,
        *,
        severity: str,
        category: str,
        title: str,
        message: str,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        action_required: bool = False,
        action_type: str | None = None,
        action_data: dict | None = None,
    ) -> None:
        notification = AgentNotification(
            client_id=client_id,
            agent_run_id=run_id,
            severity=severity,
            category=category,
            title=title,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            action_required=action_required,
            action_type=action_type,
            action_data=action_data,
        )
        db.add(notification)
        await db.flush()
        logger.info(
            "Supervisor notification [%s/%s]: %s", severity, category, title
        )


supervisor = Supervisor()

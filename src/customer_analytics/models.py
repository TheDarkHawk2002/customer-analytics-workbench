from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math


REQUIRED_COLUMNS = (
    "ticket_id", "account_id", "segment", "region", "topic", "status",
    "opened_at", "first_response_minutes", "resolved_at", "csat", "monthly_value_eur",
)
ALLOWED_STATUSES = {"open", "resolved"}


@dataclass(frozen=True)
class SupportCase:
    ticket_id: str
    account_id: str
    segment: str
    region: str
    topic: str
    status: str
    opened_at: datetime
    first_response_minutes: float | None
    resolved_at: datetime | None
    csat: int | None
    monthly_value_eur: Decimal

    @property
    def resolution_hours(self) -> float | None:
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.opened_at).total_seconds() / 3600


@dataclass(frozen=True)
class Finding:
    row_number: int
    ticket_id: str | None
    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "row_number": self.row_number,
            "ticket_id": self.ticket_id,
            "field": self.field,
            "code": self.code,
            "message": self.message,
        }


def parse_case(raw: dict[str, str], row_number: int) -> tuple[SupportCase | None, list[Finding]]:
    values = {str(key).strip().lower(): str(value or "").strip() for key, value in raw.items() if key}
    ticket_id = values.get("ticket_id", "")
    findings: list[Finding] = []

    def finding(field: str, code: str, message: str) -> None:
        findings.append(Finding(row_number, ticket_id or None, field, code, message))

    for field in ("ticket_id", "account_id", "segment", "region", "topic"):
        if not values.get(field):
            finding(field, "required", f"{field} must not be empty.")

    status = values.get("status", "").lower()
    if status not in ALLOWED_STATUSES:
        finding("status", "invalid_value", "status must be open or resolved.")

    def parse_time(field: str) -> datetime | None:
        value = values.get(field, "")
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            finding(field, "invalid_datetime", f"{field} must be an ISO-8601 timestamp.")
            return None

    opened_at = parse_time("opened_at")
    if opened_at is None and not any(item.field == "opened_at" for item in findings):
        finding("opened_at", "required", "opened_at is required.")
    resolved_at = parse_time("resolved_at")
    if status == "resolved" and resolved_at is None:
        finding("resolved_at", "required_for_status", "Resolved cases need resolved_at.")
    if status == "open" and resolved_at is not None:
        finding("resolved_at", "unexpected_value", "Open cases must not have resolved_at.")
    if opened_at and resolved_at:
        if (opened_at.utcoffset() is None) != (resolved_at.utcoffset() is None):
            finding("resolved_at", "inconsistent_timezone", "Both timestamps must either include a timezone or omit it.")
        elif resolved_at < opened_at:
            finding("resolved_at", "before_opened_at", "resolved_at cannot precede opened_at.")

    try:
        response = float(values.get("first_response_minutes", ""))
        if not math.isfinite(response):
            finding("first_response_minutes", "invalid_number", "first_response_minutes must be a finite non-negative number.")
        elif response < 0:
            finding("first_response_minutes", "negative", "First-response minutes cannot be negative.")
    except ValueError:
        response = None
        finding("first_response_minutes", "invalid_number", "first_response_minutes must be a non-negative number.")

    csat_value = values.get("csat", "")
    try:
        csat = int(csat_value) if csat_value else None
        if csat is not None and not 1 <= csat <= 5:
            finding("csat", "out_of_range", "csat must be an integer from 1 to 5.")
        if status == "resolved" and csat is None:
            finding("csat", "required_for_status", "Resolved cases need a CSAT score.")
    except ValueError:
        csat = None
        finding("csat", "invalid_value", "csat must be an integer from 1 to 5 or empty for open cases.")

    try:
        value = Decimal(values.get("monthly_value_eur", ""))
        if not value.is_finite() or value < 0:
            finding("monthly_value_eur", "invalid_value", "monthly_value_eur must be a finite non-negative number.")
    except InvalidOperation:
        value = Decimal("0")
        finding("monthly_value_eur", "invalid_number", "monthly_value_eur must be a finite non-negative number.")

    if findings:
        return None, findings
    assert opened_at is not None
    return SupportCase(
        ticket_id=ticket_id,
        account_id=values["account_id"],
        segment=values["segment"],
        region=values["region"],
        topic=values["topic"],
        status=status,
        opened_at=opened_at,
        first_response_minutes=response,
        resolved_at=resolved_at,
        csat=csat,
        monthly_value_eur=value,
    ), []

from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .analytics import build_analytics
from .models import REQUIRED_COLUMNS, Finding, SupportCase, parse_case


class InputError(ValueError):
    """Raised when a source file does not follow the documented contract."""


def read_cases(path: Path) -> tuple[list[SupportCase], list[Finding], int]:
    cases: list[SupportCase] = []
    findings: list[Finding] = []
    seen_ids: set[str] = set()
    try:
        handle = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"Cannot open input CSV: {exc}") from exc

    with handle:
        reader = csv.DictReader(handle)
        headers = [str(name or "").strip().lower() for name in (reader.fieldnames or [])]
        missing = [field for field in REQUIRED_COLUMNS if field not in headers]
        if missing:
            raise InputError("Missing columns: " + ", ".join(missing))
        for row_number, raw in enumerate(reader, start=2):
            case, row_findings = parse_case(raw, row_number)
            ticket_id = str(raw.get("ticket_id", "")).strip()
            if ticket_id and ticket_id in seen_ids:
                row_findings.append(Finding(row_number, ticket_id, "ticket_id", "duplicate", "ticket_id has already appeared in this file."))
                case = None
            elif ticket_id:
                seen_ids.add(ticket_id)
            findings.extend(row_findings)
            if case is not None and not row_findings:
                cases.append(case)
    return cases, findings, max(0, reader.line_num - 1)


def _write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _write_database(path: Path, cases: list[SupportCase], accounts: list[dict[str, object]]) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("""CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY, segment TEXT NOT NULL, region TEXT NOT NULL,
            monthly_value_eur NUMERIC NOT NULL, review_signal INTEGER NOT NULL,
            average_csat REAL, ticket_count INTEGER NOT NULL, open_tickets INTEGER NOT NULL
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS support_cases (
            ticket_id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(account_id),
            segment TEXT NOT NULL, region TEXT NOT NULL, topic TEXT NOT NULL, status TEXT NOT NULL,
            opened_at TEXT NOT NULL, first_response_minutes REAL, resolved_at TEXT,
            csat INTEGER, monthly_value_eur NUMERIC NOT NULL
        )""")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM support_cases")
        connection.execute("DELETE FROM accounts")
        connection.executemany(
            """INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(
                str(row["account_id"]), str(row["segment"]), str(row["region"]),
                str(row["monthly_value_eur"]), int(bool(row["review_signal"])),
                row["average_csat"], int(row["ticket_count"]), int(row["open_tickets"]),
            ) for row in accounts],
        )
        connection.executemany(
            """INSERT INTO support_cases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(
                case.ticket_id, case.account_id, case.segment, case.region, case.topic,
                case.status, case.opened_at.isoformat(), case.first_response_minutes,
                case.resolved_at.isoformat() if case.resolved_at else None,
                case.csat, str(case.monthly_value_eur),
            ) for case in cases],
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_cases_segment_topic ON support_cases(segment, topic)")
        connection.commit()


def _report(analytics: dict[str, object], findings: list[Finding], received: int) -> str:
    overview = analytics["overview"]
    assert isinstance(overview, dict)
    lines = [
        "# Customer Support Insights",
        "",
        "## Overview",
        "",
        f"- Valid cases: {overview['accepted_tickets']} of {received}",
        f"- Open cases: {overview['open_tickets']}",
        f"- Average CSAT: {overview['average_csat'] if overview['average_csat'] is not None else 'not available'} / 5",
        f"- Median first response: {overview['median_first_response_minutes'] if overview['median_first_response_minutes'] is not None else 'not available'} minutes",
        f"- Median resolution time: {overview['median_resolution_hours'] if overview['median_resolution_hours'] is not None else 'not available'} hours",
        f"- Accounts flagged for human review: {overview['accounts_flagged_for_review']}",
        f"- Source-quality findings: {len(findings)}",
        "",
        "## Segment summary",
        "",
        "| Segment | Tickets | Accounts | Open | Avg. CSAT | Median response (min) | Median resolution (h) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in analytics["segments"]:
        lines.append(
            f"| {row['segment']} | {row['tickets']} | {row['accounts']} | {row['open_tickets']} | "
            f"{row['average_csat'] if row['average_csat'] is not None else '—'} | "
            f"{row['median_first_response_minutes'] if row['median_first_response_minutes'] is not None else '—'} | "
            f"{row['median_resolution_hours'] if row['median_resolution_hours'] is not None else '—'} |"
        )
    lines.extend(["", "## Topics", "", "| Topic | Tickets | Open | Avg. CSAT |", "| --- | ---: | ---: | ---: |"])
    for row in analytics["topics"]:
        lines.append(f"| {row['topic']} | {row['tickets']} | {row['open_tickets']} | {row['average_csat'] if row['average_csat'] is not None else '—'} |")
    lines.extend(["", "## Accounts for follow-up", ""])
    if analytics["follow_up"]:
        for row in analytics["follow_up"]:
            lines.append(f"- `{row['account_id']}` ({row['segment']}): {'; '.join(row['signal_reasons'])}; monthly value €{row['monthly_value_eur']:.2f}.")
    else:
        lines.append("No accounts crossed the review rules in this sample.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "The review rules identify cases for a person to inspect. They are not churn predictions or a replacement for account context. The data is synthetic and the outputs are descriptive, not a forecast.",
        "",
    ])
    return "\n".join(lines)


def run_pipeline(input_path: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    cases, findings, received = read_cases(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    analytics = build_analytics(cases, datetime.now())
    analytics["source"] = str(input_path.name)
    analytics["received_tickets"] = received
    analytics["quality_findings"] = [finding.to_dict() for finding in findings]
    json_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    issues_path = output_dir / "quality_findings.csv"
    database_path = output_dir / "customer_insights.sqlite"
    json_path.write_text(json.dumps(analytics, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(_report(analytics, findings, received), encoding="utf-8")
    _write_csv(issues_path, [finding.to_dict() for finding in findings], ["row_number", "ticket_id", "field", "code", "message"])
    _write_csv(output_dir / "segment_summary.csv", analytics["segments"], [
        "segment", "tickets", "accounts", "open_tickets", "average_csat",
        "median_first_response_minutes", "median_resolution_hours",
    ])
    _write_csv(output_dir / "account_summary.csv", analytics["accounts"], [
        "account_id", "segment", "region", "ticket_count", "open_tickets",
        "average_csat", "monthly_value_eur", "review_signal", "signal_reasons",
    ])
    _write_database(database_path, cases, analytics["accounts"])
    return report_path, json_path, database_path

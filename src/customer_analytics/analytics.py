from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from statistics import mean, median

from .models import SupportCase


def _rounded(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def build_analytics(cases: list[SupportCase], now: datetime) -> dict[str, object]:
    response_times = [case.first_response_minutes for case in cases if case.first_response_minutes is not None]
    resolution_hours = [case.resolution_hours for case in cases if case.resolution_hours is not None]

    account_cases: dict[str, list[SupportCase]] = defaultdict(list)
    segment_cases: dict[str, list[SupportCase]] = defaultdict(list)
    topic_cases: dict[str, list[SupportCase]] = defaultdict(list)
    for case in cases:
        account_cases[case.account_id].append(case)
        segment_cases[case.segment].append(case)
        topic_cases[case.topic].append(case)

    follow_up: list[dict[str, object]] = []
    customer_summary: list[dict[str, object]] = []
    for account_id, group in sorted(account_cases.items()):
        open_cases = [case for case in group if case.status == "open"]
        low_rated = [case for case in group if case.csat is not None and case.csat <= 2]
        def is_stale(case: SupportCase) -> bool:
            opened = case.opened_at
            if opened.utcoffset() is None:
                reference = now.replace(tzinfo=None) if now.utcoffset() is not None else now
            elif now.utcoffset() is None:
                reference = datetime.now(opened.tzinfo)
            else:
                reference = now.astimezone(opened.tzinfo)
            return (reference - opened).total_seconds() > 48 * 3600

        stale_open = [case for case in open_cases if is_stale(case)]
        risk_cases = stale_open + low_rated
        review = bool(risk_cases)
        customer = {
            "account_id": account_id,
            "segment": group[0].segment,
            "region": group[0].region,
            "ticket_count": len(group),
            "open_tickets": len(open_cases),
            "average_csat": _rounded(mean([case.csat for case in group if case.csat is not None]) if any(case.csat is not None for case in group) else None),
            "monthly_value_eur": float(max(case.monthly_value_eur for case in group)),
            "review_signal": review,
            "signal_reasons": sorted({"open ticket older than 48 hours" for case in stale_open} | {"CSAT 1–2" for case in low_rated}),
        }
        customer_summary.append(customer)
        if review:
            follow_up.append(customer)

    segment_summary = []
    for segment, group in sorted(segment_cases.items()):
        csat_scores = [case.csat for case in group if case.csat is not None]
        responses = [case.first_response_minutes for case in group if case.first_response_minutes is not None]
        durations = [case.resolution_hours for case in group if case.resolution_hours is not None]
        segment_summary.append({
            "segment": segment,
            "tickets": len(group),
            "accounts": len({case.account_id for case in group}),
            "open_tickets": sum(case.status == "open" for case in group),
            "average_csat": _rounded(mean(csat_scores) if csat_scores else None),
            "median_first_response_minutes": _rounded(median(responses) if responses else None),
            "median_resolution_hours": _rounded(median(durations) if durations else None),
        })

    topic_summary = []
    for topic, group in sorted(topic_cases.items(), key=lambda item: (-len(item[1]), item[0])):
        topic_summary.append({
            "topic": topic,
            "tickets": len(group),
            "open_tickets": sum(case.status == "open" for case in group),
            "average_csat": _rounded(mean([case.csat for case in group if case.csat is not None]) if any(case.csat is not None for case in group) else None),
        })

    return {
        "overview": {
            "accepted_tickets": len(cases),
            "accounts": len(account_cases),
            "open_tickets": sum(case.status == "open" for case in cases),
            "resolved_tickets": sum(case.status == "resolved" for case in cases),
            "average_csat": _rounded(mean([case.csat for case in cases if case.csat is not None]) if any(case.csat is not None for case in cases) else None),
            "median_first_response_minutes": _rounded(median(response_times) if response_times else None),
            "median_resolution_hours": _rounded(median(resolution_hours) if resolution_hours else None),
            "accounts_flagged_for_review": len(follow_up),
        },
        "segments": segment_summary,
        "topics": topic_summary,
        "accounts": customer_summary,
        "follow_up": follow_up,
        "method": {
            "review_rules": ["open case older than 48 hours", "resolved case with CSAT 1 or 2"],
            "limitations": "Review signals support human triage; they do not predict churn or replace account review.",
        },
    }

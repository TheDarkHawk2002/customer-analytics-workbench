# Customer Analytics Workbench

Customer Analytics Workbench is a small, reproducible Python pipeline for reviewing customer-support activity and highlighting questions for follow-up. It combines support-case, account-segment, response-time, satisfaction, and recurring-value fields into explainable summaries. All included records are synthetic.

## What it does

- Validates a documented CSV contract and keeps row-level quality findings visible.
- Summarizes response time, resolution time, CSAT, open workload, topics, and customer segments.
- Creates human-review signals for open cases older than 48 hours or resolved cases with CSAT 1–2. These are triage rules, not churn predictions.
- Writes CSV and JSON summaries, a Markdown report, and a replaceable SQLite snapshot.
- Uses Python's standard library only.

## Run it

Python 3.11 or later is required.

```powershell
python -m pip install -e .
customer-analytics --input data/sample_support_cases.csv --output-dir output
```

Or run from source:

```powershell
$env:PYTHONPATH = "src"
python -m customer_analytics --input data/sample_support_cases.csv --output-dir output
```

The output directory contains `report.md`, `summary.json`, `quality_findings.csv`, `segment_summary.csv`, `account_summary.csv`, and `customer_insights.sqlite`. The input CSV remains unchanged.

## Input contract

Required columns are `ticket_id`, `account_id`, `segment`, `region`, `topic`, `status`, `opened_at`, `first_response_minutes`, `resolved_at`, `csat`, and `monthly_value_eur`. Status is `open` or `resolved`; timestamps use ISO 8601. Open cases leave `resolved_at` and `csat` empty. Resolved cases require both. CSAT uses an integer scale from 1 to 5.

## How to interpret the results

Segment comparisons describe this input period; they do not establish causation. The review signals help prioritize human attention and do not predict churn. A flagged account should be reviewed in context before any action is taken. Synthetic sample data is not representative of a real business.

## Project structure

```text
data/                   synthetic support-case CSV
src/customer_analytics/ validation, analytics, SQLite, reports, CLI
```

## Limits

This is a local portfolio case study, not a production dashboard or customer-management system. It has no external integrations, no predictive model, no real customer data, and no claims of commercial deployment.

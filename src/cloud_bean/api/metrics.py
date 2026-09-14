"""Prometheus exposition metrics generator for Cloud-Bean."""

from typing import Any, Dict


def format_prometheus_metrics(
    total_events: int,
    total_candidates: int,
    total_findings: int,
    total_judgments: int,
    buffered_events: int,
    spent_usd: float,
    max_budget_usd: float,
    findings_by_pattern: Dict[str, int],
    candidates_by_signal: Dict[str, int],
) -> str:
    """Format operational telemetry into standard Prometheus text exposition format (RFC 0004)."""
    lines = [
        "# HELP cloud_bean_events_total Total number of fleet events processed.",
        "# TYPE cloud_bean_events_total counter",
        f"cloud_bean_events_total {total_events}",
        "",
        "# HELP cloud_bean_candidates_total Total candidate groups flagged for investigation.",
        "# TYPE cloud_bean_candidates_total counter",
        f"cloud_bean_candidates_total {total_candidates}",
        "",
        "# HELP cloud_bean_findings_total Total verified or alerted findings generated.",
        "# TYPE cloud_bean_findings_total counter",
        f"cloud_bean_findings_total {total_findings}",
        "",
        "# HELP cloud_bean_judgments_total Total model judgments processed and recorded.",
        "# TYPE cloud_bean_judgments_total counter",
        f"cloud_bean_judgments_total {total_judgments}",
        "",
        "# HELP cloud_bean_buffered_events Gauge of currently active in-memory events.",
        "# TYPE cloud_bean_buffered_events gauge",
        f"cloud_bean_buffered_events {buffered_events}",
        "",
        "# HELP cloud_bean_budget_spent_usd Cumulative LLM judge spend in USD.",
        "# TYPE cloud_bean_budget_spent_usd gauge",
        f"cloud_bean_budget_spent_usd {spent_usd:.4f}",
        "",
        "# HELP cloud_bean_budget_max_usd Configured maximum LLM judge budget cap in USD.",
        "# TYPE cloud_bean_budget_max_usd gauge",
        f"cloud_bean_budget_max_usd {max_budget_usd:.4f}",
        "",
        "# HELP cloud_bean_findings_by_pattern Findings partitioned by detected pattern.",
        "# TYPE cloud_bean_findings_by_pattern counter",
    ]
    for pattern, count in sorted(findings_by_pattern.items()):
        escaped_pattern = pattern.replace('"', '\\"')
        lines.append(f'cloud_bean_findings_by_pattern{{pattern="{escaped_pattern}"}} {count}')

    lines.extend([
        "",
        "# HELP cloud_bean_candidates_by_signal Candidate groups partitioned by triggering signal.",
        "# TYPE cloud_bean_candidates_by_signal counter",
    ])
    for signal, count in sorted(candidates_by_signal.items()):
        escaped_signal = signal.replace('"', '\\"')
        lines.append(f'cloud_bean_candidates_by_signal{{signal="{escaped_signal}"}} {count}')

    lines.append("")
    return "\n".join(lines)

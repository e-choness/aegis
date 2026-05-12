import pytest
from src.aegis.services.audit import AuditLogger
from src.aegis.models import AuditRecord


def _record(**kwargs) -> AuditRecord:
    defaults = dict(
        trace_id="t1",
        user_id="u1",
        team_id="team-a",
        model_alias="sonnet",
        model_id="claude-sonnet-4-6",
        provider="anthropic",
        tier=1,
        data_classification="INTERNAL",
        cost_usd=0.05,
    )
    defaults.update(kwargs)
    return AuditRecord(**defaults)


def test_records_are_stored():
    audit = AuditLogger()
    audit.log(_record())
    assert len(audit.get_records()) == 1


def test_filter_by_team():
    audit = AuditLogger()
    audit.log(_record(team_id="team-a"))
    audit.log(_record(team_id="team-b"))
    assert len(audit.get_records("team-a")) == 1
    assert len(audit.get_records("team-b")) == 1


def test_restricted_cloud_violations_invariant():
    audit = AuditLogger()
    # Correctly routed RESTRICTED record to tier 3 (Ollama) — should NOT be a violation
    audit.log(_record(data_classification="RESTRICTED", tier=3, provider="ollama"))
    assert audit.count_restricted_cloud_violations() == 0


def test_restricted_cloud_violation_detected():
    audit = AuditLogger()
    # Incorrectly routed RESTRICTED to tier 1 — must be detected
    audit.log(_record(data_classification="RESTRICTED", tier=1, provider="anthropic"))
    assert audit.count_restricted_cloud_violations() == 1

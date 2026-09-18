import os
import sys

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "test-token")
os.environ.setdefault("SLACK_WEBHOOK_OPS", "https://example.invalid/ops")
os.environ.setdefault("SLACK_WEBHOOK_EXEC", "https://example.invalid/exec")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import desired_engineering_priority_label, priority_label_plan, validate_origin_team_labels, p0_verification_status
from a2_quality_gate import evaluate_shared_quality_gate

def issue(labels, priority="High"):
    desc = "Company ID: c\nPCIH: p\nEntity Name: e\nState: CA\nTax Type: SIT\nIssue: details for the required description length.\nReviewed and signed off by: Lead"
    return {"key":"PF-1","fields":{"summary":"Company ID c PCIH p Entity Name e State CA Tax Type SIT","description":{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":desc}]}]},"labels":labels,"priority":{"name":priority},"assignee":{"displayName":"Engineer"},"reporter":{"displayName":"Reporter"},"status":{"name":"Triage"},"updated":"2026-09-18T00:00:00.000-0700","components":[{"name":"Tax Exchange"}]}}

def test_origin_labels():
    assert validate_origin_team_labels(["us-taxops-ticket"])["origin_team"] == "TaxOps"
    assert validate_origin_team_labels(["peo-ops-ticket"])["origin_team"] == "PEO Ops"
    assert validate_origin_team_labels(["compliance-tickets"])["origin_team"] == "Compliance"
    assert validate_origin_team_labels([])["failures"]
    assert validate_origin_team_labels(["us-taxops-ticket", "peo-ops-ticket"])["failures"]
    assert any("e2e-peo" in f for f in validate_origin_team_labels(["e2e-peo"])["failures"])

def test_priority_mapping_never_p0():
    assert desired_engineering_priority_label("Highest") == "p1_priority"
    assert desired_engineering_priority_label("High") == "p2_priority"
    assert desired_engineering_priority_label("Medium") == "p3_priority"
    assert desired_engineering_priority_label("Low") == "p4_priority"

def test_priority_plan_report_only_without_reviewer_validation():
    plan = priority_label_plan(["foo", "p3_priority"], "High", reviewer_validation_verified=False)
    assert plan["desired"] == "p2_priority"
    assert plan["to_add"] == []
    assert plan["to_remove"] == []

def test_p0_unverified_fails_closed():
    p0 = p0_verification_status(["p0_priority"])
    assert p0["verified"] is False
    assert p0["failure"]

def test_combined_gate_fails_closed_when_reviewer_config_missing(monkeypatch):
    monkeypatch.setattr("a2_quality_gate.has_salesforce_case_linked", lambda key: True)
    result = evaluate_shared_quality_gate(issue(["us-taxops-ticket", "NoticeQueue_task", "west-region", "rip-direct"]))
    assert result["quality_gate_passed"] is False
    assert result["desired_engineering_priority_label"] == "p2_priority"
    assert result["can_sync_priority_label"] is False
    assert result["can_transition_open"] is False
    assert result["reviewer_validation_status"] == "unavailable"

def test_same_rules_apply_to_all_origin_teams(monkeypatch):
    monkeypatch.setattr("a2_quality_gate.has_salesforce_case_linked", lambda key: True)
    for origin in ["us-taxops-ticket", "peo-ops-ticket", "compliance-tickets"]:
        result = evaluate_shared_quality_gate(issue([origin, "NoticeQueue_task", "west-region", "rip-direct"]))
        assert result["a2_failures"] == []
        assert result["a3_failures"] == []
        assert result["a4_failures"] == []
        assert result["reviewer_validation_status"] == "unavailable"

def test_a8_disabled_mode_preserves_legacy_auto_label(monkeypatch):
    import a8_auto_label
    monkeypatch.setenv("SHARED_QUALITY_GATE_ENABLED", "false")
    issue_obj = {"key": "PF-1", "fields": {"labels": ["NoticeQueue_task"], "summary": "s"}}
    calls = []
    monkeypatch.setattr(a8_auto_label, "jira_search", lambda *a, **k: [issue_obj])
    monkeypatch.setattr(a8_auto_label, "update_labels", lambda key, labels: calls.append((key, labels)))
    a8_auto_label.run()
    assert calls == [("PF-1", ["NoticeQueue_task", "us-taxops-ticket"])]


def test_a8_enabled_mode_no_origin_mutation(monkeypatch):
    import a8_auto_label
    monkeypatch.setenv("SHARED_QUALITY_GATE_ENABLED", "true")
    monkeypatch.setattr(a8_auto_label, "jira_search", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not search")))
    monkeypatch.setattr(a8_auto_label, "update_labels", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not mutate")))
    a8_auto_label.run()


def test_a8_preserves_existing_origin_labels_in_both_modes(monkeypatch):
    import a8_auto_label
    for enabled in ("false", "true"):
        monkeypatch.setenv("SHARED_QUALITY_GATE_ENABLED", enabled)
        calls = []
        issue_obj = {"key": "PF-1", "fields": {"labels": ["us-taxops-ticket", "NoticeQueue_task"], "summary": "s"}}
        monkeypatch.setattr(a8_auto_label, "jira_search", lambda *a, **k: [issue_obj])
        monkeypatch.setattr(a8_auto_label, "update_labels", lambda key, labels: calls.append((key, labels)))
        a8_auto_label.run()
        assert calls == []


def test_a8_shared_mode_does_not_guess_missing_or_non_taxops_origin(monkeypatch):
    import a8_auto_label
    monkeypatch.setenv("SHARED_QUALITY_GATE_ENABLED", "true")
    calls = []
    monkeypatch.setattr(a8_auto_label, "update_labels", lambda key, labels: calls.append((key, labels)))
    a8_auto_label.run()
    assert calls == []


def test_a8_shared_mode_never_stamps_peo_or_compliance_as_taxops(monkeypatch):
    import a8_auto_label
    monkeypatch.setenv("SHARED_QUALITY_GATE_ENABLED", "true")
    calls = []
    monkeypatch.setattr(a8_auto_label, "update_labels", lambda key, labels: calls.append((key, labels)))
    a8_auto_label.run()
    assert calls == []


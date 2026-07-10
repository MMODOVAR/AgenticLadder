"""Tests for the rung-tagged audit log."""
import json
import unittest

from rungguard.audit.log import AuditLog
from rungguard.models import AuditOutcome, PolicyEvaluation, PolicyOutcome, ActionCategory, _uid


def _make_evaluation(agent_id: str, rung: int, outcome: PolicyOutcome) -> PolicyEvaluation:
    return PolicyEvaluation(
        agent_id=agent_id,
        assignment_id=_uid("asgn"),
        rung=rung,
        action="test_action",
        action_category=ActionCategory.READ,
        outcome=outcome,
        reason="unit test",
    )


class TestAuditLog(unittest.TestCase):
    def test_record_action_appended(self):
        log = AuditLog()
        ev = _make_evaluation("agt-1", 2, PolicyOutcome.ALLOW)
        log.record_action(ev, AuditOutcome.ALLOWED)
        entries = log.recent(10)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].agent_id, "agt-1")

    def test_record_rung_change(self):
        log = AuditLog()
        log.record_rung_change(
            agent_id="agt-2",
            from_rung=1,
            to_rung=3,
            assignment_id="asgn-x",
            requested_by="admin",
            direction="promotion",
        )
        entries = log.recent(5)
        self.assertEqual(len(entries), 1)
        self.assertIn("rung", entries[0].action)

    def test_record_credential_event(self):
        log = AuditLog()
        log.record_credential_event(
            agent_id="agt-3",
            assignment_id="asgn-y",
            rung=2,
            event="issued",
            credential_id="cred-x",
            provider="env",
        )
        entries = log.recent(5)
        self.assertEqual(len(entries), 1)
        self.assertIn("credential", entries[0].action)

    def test_for_agent_filters(self):
        log = AuditLog()
        for i in range(3):
            ev = _make_evaluation(f"agt-{i}", i, PolicyOutcome.ALLOW)
            log.record_action(ev, AuditOutcome.ALLOWED)
        entries = log.for_agent("agt-1")
        self.assertEqual(len(entries), 1)

    def test_denied_filter(self):
        log = AuditLog()
        ev_allow = _make_evaluation("agt-a", 2, PolicyOutcome.ALLOW)
        ev_deny = _make_evaluation("agt-b", 1, PolicyOutcome.DENY)
        log.record_action(ev_allow, AuditOutcome.ALLOWED)
        log.record_action(ev_deny, AuditOutcome.DENIED)
        denied = log.denied()
        self.assertEqual(len(denied), 1)
        self.assertEqual(denied[0].agent_id, "agt-b")

    def test_stats_counts(self):
        log = AuditLog()
        for outcome in [PolicyOutcome.ALLOW, PolicyOutcome.ALLOW, PolicyOutcome.DENY]:
            ev = _make_evaluation("agt-s", 2, outcome)
            actual = AuditOutcome.ALLOWED if outcome == PolicyOutcome.ALLOW else AuditOutcome.DENIED
            log.record_action(ev, actual)
        stats = log.stats()
        self.assertEqual(stats["total_entries"], 3)
        self.assertEqual(stats["by_outcome"]["allowed"], 2)
        self.assertEqual(stats["by_outcome"]["denied"], 1)

    def test_export_jsonl(self):
        log = AuditLog()
        ev = _make_evaluation("agt-e", 3, PolicyOutcome.ALLOW)
        log.record_action(ev, AuditOutcome.ALLOWED)
        output = log.export_jsonl()
        lines = [l for l in output.strip().splitlines() if l]
        self.assertEqual(len(lines), 1)
        parsed = json.loads(lines[0])
        self.assertEqual(parsed["agent_id"], "agt-e")

    def test_writer_receives_dict(self):
        received = []
        from rungguard.audit.log import register_writer
        register_writer(lambda d: received.append(d))
        log = AuditLog()
        ev = _make_evaluation("agt-w", 2, PolicyOutcome.ALLOW)
        log.record_action(ev, AuditOutcome.ALLOWED)
        self.assertGreaterEqual(len(received), 1)
        self.assertEqual(received[-1]["agent_id"], "agt-w")

    def test_max_entries_eviction(self):
        log = AuditLog(max_entries=5)
        for i in range(10):
            ev = _make_evaluation(f"agt-{i}", 1, PolicyOutcome.ALLOW)
            log.record_action(ev, AuditOutcome.ALLOWED)
        entries = log.recent(100)
        self.assertEqual(len(entries), 5)

    def test_to_dict_serialisable(self):
        log = AuditLog()
        ev = _make_evaluation("agt-json", 2, PolicyOutcome.DENY)
        log.record_action(ev, AuditOutcome.DENIED)
        for entry in log.recent(5):
            json.dumps(entry.to_dict())

    def test_for_assignment_filters(self):
        log = AuditLog()
        ev1 = _make_evaluation("agt-fa", 2, PolicyOutcome.ALLOW)
        ev1.assignment_id = "asgn-target"
        ev2 = _make_evaluation("agt-fb", 2, PolicyOutcome.ALLOW)
        log.record_action(ev1, AuditOutcome.ALLOWED)
        log.record_action(ev2, AuditOutcome.ALLOWED)
        result = log.for_assignment("asgn-target")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].agent_id, "agt-fa")

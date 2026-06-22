import unittest

from decision_atlas.connectors import available_connectors, build_connector
from decision_atlas.connectors.audit_log import AuditLogConnector
from decision_atlas.connectors.jira import JiraConnector
from decision_atlas.connectors.approval import ApprovalConnector
from decision_atlas.connectors.workflow import WorkflowConnector


class TestRegistry(unittest.TestCase):
    def test_builtin_connectors_registered(self):
        names = available_connectors()
        for expected in ("audit_log", "jira", "approval", "workflow"):
            self.assertIn(expected, names)

    def test_build_connector_unknown_type(self):
        with self.assertRaises(ValueError):
            build_connector({"type": "does_not_exist"})

    def test_build_connector_from_spec(self):
        c = build_connector({"type": "audit_log", "path": "x.json", "name": "t"})
        self.assertIsInstance(c, AuditLogConnector)
        self.assertEqual(c.name, "t")


class TestAuditLogConnector(unittest.TestCase):
    def test_field_mapping_and_inputs_from_dict(self):
        records = [{
            "eventID": "e1", "eventName": "iam.CreateUser", "eventTime": "2026-01-01T00:00:00Z",
            "user": "arn:aws:iam::1:user/bob", "status": "ok",
            "params": {"username": 1, "group": 1}, "acct": "Platform",
        }]
        c = AuditLogConnector(path="-", records=records, mapping={
            "id": "eventID", "decision_key": "eventName", "timestamp": "eventTime",
            "actor": "user", "outcome": "status", "input_fields": "params",
            "domain": "acct",
        })
        events = c.fetch_events()
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e.decision_key, "iam.CreateUser")
        self.assertEqual(e.actor, "arn:aws:iam::1:user/bob")
        self.assertEqual(e.domain, "Platform")
        self.assertEqual(sorted(e.input_fields), ["group", "username"])
        self.assertIsNotNone(e.timestamp)

    def test_generates_id_when_missing(self):
        c = AuditLogConnector(path="-", records=[{"decision": "x"}])
        events = c.fetch_events()
        self.assertTrue(events[0].id)


class TestJiraConnector(unittest.TestCase):
    def test_only_decision_transitions_emitted_and_overturn(self):
        records = [{
            "key": "AB-1", "project": "AB", "type": "task", "domain": "Ops",
            "fields": {"a": 1, "b": 1},
            "transitions": [
                {"to": "in progress", "by": "x"},
                {"to": "resolved", "by": "y", "when": "2026-01-01T00:00:00Z"},
                {"to": "reopened", "by": "z"},
            ],
        }]
        events = JiraConnector(path="-", records=records).fetch_events()
        self.assertEqual(len(events), 1)  # only "resolved" is a decision status
        e = events[0]
        self.assertEqual(e.decision_key, "ab.task.resolved")
        self.assertTrue(e.overturned)  # reopened after resolution
        self.assertEqual(e.domain, "Ops")


class TestApprovalConnector(unittest.TestCase):
    def test_amount_maps_to_impact(self):
        records = [{"id": "1", "category": "wire", "amount": 250000,
                    "approver": "t", "decision": "approved"}]
        e = ApprovalConnector(path="-", records=records).fetch_events()[0]
        self.assertEqual(e.decision_key, "wire.approval")
        self.assertAlmostEqual(e.impact, 1.0, places=3)


class TestWorkflowConnector(unittest.TestCase):
    def test_only_decision_tasks(self):
        records = [{
            "workflow": "wf", "domain": "D", "run_id": "r1",
            "tasks": [
                {"type": "task", "name": "noop"},
                {"type": "gateway", "name": "Choose Path", "decision": "a",
                 "inputs": {"x": 1}},
            ],
        }]
        events = WorkflowConnector(path="-", records=records).fetch_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].decision_key, "wf.choose_path")


if __name__ == "__main__":
    unittest.main()

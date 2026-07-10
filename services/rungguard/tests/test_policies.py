"""Tests for the blast-radius policy engine."""
import unittest

from rungguard.models import PolicyOutcome, ActionCategory
from rungguard.policies.engine import evaluate, reset_rate_counters
from rungguard.policies.rules import RUNG_POLICIES, all_policies


class TestPolicyEngine(unittest.TestCase):
    def setUp(self):
        reset_rate_counters()

    def test_rung0_denies_everything(self):
        result = evaluate("agt-0", "asgn-0", 0, "read_file", {})
        self.assertEqual(result.outcome, PolicyOutcome.DENY)

    def test_rung1_allows_read(self):
        result = evaluate("agt-1", "asgn-1", 1, "read_database", {})
        self.assertEqual(result.outcome, PolicyOutcome.ALLOW)

    def test_rung1_denies_write(self):
        result = evaluate("agt-1", "asgn-1", 1, "write_file", {})
        self.assertEqual(result.outcome, PolicyOutcome.DENY)

    def test_rung2_allows_write(self):
        result = evaluate("agt-2", "asgn-2", 2, "write_document", {})
        self.assertEqual(result.outcome, PolicyOutcome.ALLOW)

    def test_rung2_requires_approval_for_communicate(self):
        result = evaluate("agt-2", "asgn-2", 2, "send_email", {})
        self.assertEqual(result.outcome, PolicyOutcome.REQUIRE_APPROVAL)

    def test_rung3_allows_communicate(self):
        result = evaluate("agt-3", "asgn-3", 3, "send_notification", {})
        self.assertEqual(result.outcome, PolicyOutcome.ALLOW)

    def test_rung3_requires_approval_for_financial(self):
        result = evaluate("agt-3", "asgn-3", 3, "financial_payment", {})
        self.assertEqual(result.outcome, PolicyOutcome.REQUIRE_APPROVAL)

    def test_rung3_denies_irreversible(self):
        result = evaluate("agt-3", "asgn-3", 3, "wipe_database", {})
        self.assertEqual(result.outcome, PolicyOutcome.DENY)

    def test_rung3_denies_access_control(self):
        result = evaluate("agt-3a", "asgn-3a", 3, "grant_role", {})
        self.assertEqual(result.outcome, PolicyOutcome.DENY)

    def test_rung4_allows_deploy(self):
        result = evaluate("agt-4", "asgn-4", 4, "deploy_service", {})
        self.assertIn(result.outcome,
                      (PolicyOutcome.ALLOW, PolicyOutcome.REQUIRE_APPROVAL))

    def test_rung5_allows_all(self):
        for action in ["read_data", "write_config", "deploy_service",
                       "delete_bucket", "execute_script", "financial_transfer"]:
            result = evaluate("agt-5", "asgn-5", 5, action, {})
            self.assertEqual(result.outcome, PolicyOutcome.ALLOW,
                             f"rung5 should allow {action}, got {result.outcome}")

    def test_financial_cap_rung4_triggers_escalate(self):
        result = evaluate("agt-4f", "asgn-4f", 4, "financial_payment",
                          {"amount": 100_000})
        self.assertEqual(result.outcome, PolicyOutcome.ESCALATE)

    def test_financial_within_cap_rung4_allows(self):
        result = evaluate("agt-4g", "asgn-4g", 4, "financial_transfer",
                          {"amount": 10_000})
        self.assertEqual(result.outcome, PolicyOutcome.ALLOW)

    def test_rate_limit_triggers(self):
        policy = RUNG_POLICIES[1]
        limit = policy.rate_limits.get("read", 200)
        for _ in range(limit):
            evaluate("agt-rl", "asgn-rl", 1, "read_data", {})
        result = evaluate("agt-rl", "asgn-rl", 1, "read_data", {})
        self.assertEqual(result.outcome, PolicyOutcome.RATE_LIMIT)

    def test_evaluation_includes_assignment_id(self):
        result = evaluate("agt-aid", "asgn-check", 2, "read_config", {})
        self.assertEqual(result.assignment_id, "asgn-check")

    def test_reason_is_populated(self):
        result = evaluate("agt-r", "asgn-r", 1, "write_record", {})
        self.assertIsInstance(result.reason, str)
        self.assertGreater(len(result.reason), 0)

    def test_policy_rules_applied_logged(self):
        result = evaluate("agt-rpa", "asgn-rpa", 2, "read_config", {})
        self.assertIsInstance(result.policy_rules_applied, list)
        self.assertGreater(len(result.policy_rules_applied), 0)

    def test_rung1_denies_execute(self):
        result = evaluate("agt-1e", "asgn-1e", 1, "execute_script", {})
        self.assertEqual(result.outcome, PolicyOutcome.DENY)

    def test_rung2_denies_delete(self):
        result = evaluate("agt-2d", "asgn-2d", 2, "delete_record", {})
        self.assertEqual(result.outcome, PolicyOutcome.DENY)


class TestPolicyRules(unittest.TestCase):
    def test_all_rungs_present(self):
        policies = all_policies()
        rungs = {p.rung for p in policies}
        self.assertEqual(rungs, {0, 1, 2, 3, 4, 5})

    def test_rung_policies_dict_complete(self):
        self.assertEqual(set(RUNG_POLICIES.keys()), {0, 1, 2, 3, 4, 5})

    def test_to_dict_serialisable(self):
        import json
        for policy in all_policies():
            d = policy.to_dict()
            json.dumps(d)

    def test_rung5_allows_all_categories(self):
        rung5 = RUNG_POLICIES[5]
        self.assertEqual(rung5.allowed_actions, set(ActionCategory))
        self.assertEqual(len(rung5.denied_actions), 0)

    def test_rung0_denies_all_categories(self):
        rung0 = RUNG_POLICIES[0]
        self.assertEqual(len(rung0.allowed_actions), 0)

    def test_financial_cap_increases_with_rung(self):
        cap1 = RUNG_POLICIES[1].max_financial_amount
        cap3 = RUNG_POLICIES[3].max_financial_amount
        cap4 = RUNG_POLICIES[4].max_financial_amount
        self.assertIsNotNone(cap3)
        self.assertIsNotNone(cap4)
        self.assertGreater(cap4, cap3)

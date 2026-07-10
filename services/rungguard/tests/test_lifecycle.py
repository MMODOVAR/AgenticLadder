"""Tests for the rung lifecycle engine and approval chains."""
import unittest

from rungguard.models import AgentStatus, ChangeDirection, WorkflowStatus
from rungguard.lifecycle.engine import LifecycleEngine
from rungguard.lifecycle.approval import resolve_chain


class TestResolveChain(unittest.TestCase):
    def test_promotion_rung5_requires_three_approvers(self):
        chain = resolve_chain(ChangeDirection.PROMOTION, from_rung=4, to_rung=5)
        self.assertEqual(len(chain.approver_roles), 3)

    def test_promotion_rung3_requires_domain_owner(self):
        chain = resolve_chain(ChangeDirection.PROMOTION, from_rung=2, to_rung=3)
        self.assertIn("domain_owner", chain.approver_roles)

    def test_demotion_requires_ai_governance(self):
        chain = resolve_chain(ChangeDirection.DEMOTION, from_rung=3, to_rung=1)
        self.assertIn("ai_governance_officer", chain.approver_roles)

    def test_suspension_requires_ciso(self):
        chain = resolve_chain(ChangeDirection.SUSPENSION, from_rung=3, to_rung=0)
        self.assertIn("ciso", chain.approver_roles)

    def test_low_promotion_requires_team_lead(self):
        chain = resolve_chain(ChangeDirection.PROMOTION, from_rung=0, to_rung=1)
        self.assertIn("team_lead", chain.approver_roles)

    def test_rung5_promotion_has_long_window(self):
        chain = resolve_chain(ChangeDirection.PROMOTION, from_rung=4, to_rung=5)
        self.assertGreaterEqual(chain.approval_window_hours, 72)

    def test_suspension_has_short_window(self):
        chain = resolve_chain(ChangeDirection.SUSPENSION, from_rung=2, to_rung=0)
        self.assertLessEqual(chain.approval_window_hours, 4)


class _NullChangeCallback:
    def __init__(self):
        self.calls = []

    def __call__(self, agent, assignment):
        self.calls.append((agent.id, assignment.rung))


def _make_engine():
    agents: dict = {}
    requests: dict = {}
    assignments: dict = {}
    cb = _NullChangeCallback()
    engine = LifecycleEngine(agents, requests, assignments, on_change=cb)
    return engine, agents, requests, assignments, cb


class TestLifecycleEngine(unittest.TestCase):
    def test_register_agent_creates_rung0(self):
        engine, agents, *_ = _make_engine()
        agent = engine.register_agent("BotA", "alice", initial_rung=0)
        self.assertIn(agent.id, agents)
        self.assertEqual(agent.current_rung, 0)
        self.assertEqual(agent.status, AgentStatus.ACTIVE)

    def test_register_agent_initial_rung_1(self):
        engine, agents, *_ = _make_engine()
        agent = engine.register_agent("BotB", "bob", initial_rung=1)
        self.assertEqual(agent.current_rung, 1)

    def test_register_agent_creates_initial_assignment(self):
        engine, agents, requests, assignments, _ = _make_engine()
        agent = engine.register_agent("BotC", "carol", initial_rung=2)
        self.assertIsNotNone(agent.current_assignment_id)
        self.assertIn(agent.current_assignment_id, assignments)

    def test_submit_change_request_creates_pending(self):
        engine, agents, requests, *_ = _make_engine()
        agent = engine.register_agent("BotD", "dave", initial_rung=1)
        req = engine.submit_change_request(
            agent_id=agent.id,
            to_rung=3,
            requested_by="dave",
            justification="needs more access",
        )
        self.assertEqual(req.status, WorkflowStatus.PENDING)
        self.assertIn(req.id, requests)
        self.assertEqual(req.from_rung, 1)
        self.assertEqual(req.to_rung, 3)

    def test_approve_step_with_correct_role(self):
        engine, agents, requests, assignments, cb = _make_engine()
        agent = engine.register_agent("BotF", "frank", initial_rung=1)
        req = engine.submit_change_request(
            agent_id=agent.id, to_rung=2,
            requested_by="frank", justification="tests",
        )
        engine.approve_step(req.id, "grace", "team_lead", "ok")
        updated_req = requests[req.id]
        self.assertEqual(updated_req.status, WorkflowStatus.APPROVED)
        engine.execute_change(req.id)
        self.assertEqual(agents[agent.id].current_rung, 2)
        self.assertEqual(len(cb.calls), 1)

    def test_reject_step_marks_rejected(self):
        engine, agents, requests, *_ = _make_engine()
        agent = engine.register_agent("BotG", "greta", initial_rung=2)
        req = engine.submit_change_request(
            agent_id=agent.id, to_rung=3,
            requested_by="greta", justification="needs more",
        )
        engine.reject_step(req.id, "hank", "domain_owner", "nope")
        self.assertEqual(requests[req.id].status, WorkflowStatus.REJECTED)
        self.assertEqual(agents[agent.id].current_rung, 2)

    def test_cancel_request(self):
        engine, _, requests, *_ = _make_engine()
        agent = engine.register_agent("BotH", "harry", initial_rung=1)
        req = engine.submit_change_request(
            agent_id=agent.id, to_rung=2,
            requested_by="harry", justification="cancel me",
        )
        engine.cancel_request(req.id, "harry")
        self.assertEqual(requests[req.id].status, WorkflowStatus.CANCELLED)

    def test_demotion_auto_approved_by_governance(self):
        engine, agents, requests, _, cb = _make_engine()
        agent = engine.register_agent("BotI", "ivan", initial_rung=4)
        req = engine.submit_change_request(
            agent_id=agent.id, to_rung=2,
            requested_by="secops",
            justification="policy violation",
            direction=ChangeDirection.DEMOTION,
        )
        self.assertEqual(req.status, WorkflowStatus.APPROVED)

    def test_suspension_marks_agent_suspended(self):
        engine, agents, requests, _, cb = _make_engine()
        agent = engine.register_agent("BotK", "kim", initial_rung=3)
        req = engine.submit_change_request(
            agent_id=agent.id, to_rung=0,
            requested_by="ciso_user",
            justification="security incident",
            direction=ChangeDirection.SUSPENSION,
        )
        if req.status == WorkflowStatus.APPROVED:
            engine.execute_change(req.id)
            self.assertEqual(agents[agent.id].status, AgentStatus.SUSPENDED)
            self.assertEqual(agents[agent.id].current_rung, 0)

    def test_history_returns_assignments(self):
        engine, _, _, assignments, _ = _make_engine()
        agent = engine.register_agent("BotJ", "julia", initial_rung=0)
        history = engine.get_agent_history(agent.id)
        self.assertEqual(len(history), 1)

    def test_expire_stale_requests(self):
        from datetime import timezone, timedelta
        engine, _, requests, *_ = _make_engine()
        agent = engine.register_agent("BotL", "leo", initial_rung=1)
        req = engine.submit_change_request(
            agent_id=agent.id, to_rung=2,
            requested_by="leo", justification="will expire",
        )
        req.expires_at = "2000-01-01T00:00:00+00:00"
        expired = engine.expire_stale_requests()
        self.assertIn(req.id, expired)
        self.assertEqual(requests[req.id].status, WorkflowStatus.EXPIRED)

    def test_execute_change_updates_assignment(self):
        engine, agents, _, assignments, _ = _make_engine()
        agent = engine.register_agent("BotM", "mia", initial_rung=1)
        req = engine.submit_change_request(
            agent_id=agent.id, to_rung=2,
            requested_by="mia", justification="ok",
        )
        engine.approve_step(req.id, "lead", "team_lead", "approved")
        engine.execute_change(req.id)
        self.assertEqual(agents[agent.id].current_rung, 2)
        new_asgn_id = agents[agent.id].current_assignment_id
        self.assertIsNotNone(new_asgn_id)
        self.assertIn(new_asgn_id, assignments)

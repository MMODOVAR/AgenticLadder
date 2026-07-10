"""Tests for the credential manager and env provider."""
import unittest

from rungguard.models import Agent, AgentStatus, CredentialStatus, RungAssignment, _uid, _ts
from rungguard.credentials.manager import CredentialManager
from rungguard.credentials.providers.env import EnvCredentialProvider
from rungguard.policies.rules import get_policy


def _agent(name: str = "TestBot", rung: int = 1,
           status: AgentStatus = AgentStatus.ACTIVE) -> Agent:
    return Agent(id=_uid("agt"), name=name, owner="owner",
                 current_rung=rung, status=status)


def _assignment(agent_id: str, rung: int) -> RungAssignment:
    return RungAssignment(
        id=_uid("asgn"),
        agent_id=agent_id,
        rung=rung,
        granted_by="test",
    )


class TestEnvCredentialProvider(unittest.TestCase):
    def test_issue_returns_active_credential(self):
        provider = EnvCredentialProvider(write_env=False)
        policy = get_policy(2)
        cred = provider.issue("agt-x", rung=2, policy=policy)
        self.assertEqual(cred.status, CredentialStatus.ACTIVE)
        self.assertIsNotNone(cred.secret_ref)
        self.assertEqual(cred.rung, 2)

    def test_revoke_removes_token(self):
        provider = EnvCredentialProvider(write_env=False)
        policy = get_policy(1)
        cred = provider.issue("agt-y", rung=1, policy=policy)
        token = provider.lookup(cred.secret_ref)
        self.assertIsNotNone(token)
        provider.revoke(cred.id, cred.secret_ref, cred.provider_metadata)
        self.assertIsNone(provider.lookup(cred.secret_ref))

    def test_credential_has_expiry_from_ttl(self):
        provider = EnvCredentialProvider(write_env=False)
        policy = get_policy(1)
        cred = provider.issue("agt-z", rung=1, policy=policy)
        self.assertIsNotNone(cred.expires_at)

    def test_credential_type_is_api_token(self):
        provider = EnvCredentialProvider(write_env=False)
        policy = get_policy(2)
        cred = provider.issue("agt-t", rung=2, policy=policy)
        self.assertEqual(cred.credential_type, "api_token")


class TestCredentialManager(unittest.TestCase):
    def _make_manager(self) -> tuple[CredentialManager, dict]:
        creds: dict = {}
        mgr = CredentialManager(creds, EnvCredentialProvider(write_env=False))
        return mgr, creds

    def test_rung0_issue_initial_returns_none(self):
        mgr, _ = self._make_manager()
        agent = _agent(rung=0)
        asgn = _assignment(agent.id, rung=0)
        result = mgr.issue_initial(agent, asgn)
        self.assertIsNone(result)

    def test_rung1_issue_initial_creates_credential(self):
        mgr, creds = self._make_manager()
        agent = _agent(rung=1)
        asgn = _assignment(agent.id, rung=1)
        cred = mgr.issue_initial(agent, asgn)
        self.assertIsNotNone(cred)
        self.assertEqual(cred.status, CredentialStatus.ACTIVE)
        self.assertIn(cred.id, creds)

    def test_credential_links_to_assignment(self):
        mgr, _ = self._make_manager()
        agent = _agent(rung=2)
        asgn = _assignment(agent.id, rung=2)
        cred = mgr.issue_initial(agent, asgn)
        self.assertEqual(cred.assignment_id, asgn.id)

    def test_on_rung_change_revokes_old_issues_new(self):
        mgr, creds = self._make_manager()
        agent = _agent(rung=2)
        asgn2 = _assignment(agent.id, rung=2)
        initial = mgr.issue_initial(agent, asgn2)
        self.assertIsNotNone(initial)

        asgn3 = _assignment(agent.id, rung=3)
        agent.current_rung = 3
        mgr.on_rung_change(agent, asgn3)

        self.assertEqual(creds[initial.id].status, CredentialStatus.REVOKED)

        active = mgr.active_for_agent(agent.id)
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0].rung, 3)

    def test_suspended_agent_no_new_cred_on_change(self):
        mgr, creds = self._make_manager()
        agent = _agent(rung=2)
        asgn2 = _assignment(agent.id, rung=2)
        initial = mgr.issue_initial(agent, asgn2)
        self.assertIsNotNone(initial)

        agent.status = AgentStatus.SUSPENDED
        agent.current_rung = 0
        asgn0 = _assignment(agent.id, rung=0)
        mgr.on_rung_change(agent, asgn0)

        self.assertEqual(creds[initial.id].status, CredentialStatus.REVOKED)
        active = mgr.active_for_agent(agent.id)
        self.assertEqual(len(active), 0)

    def test_active_for_agent_excludes_revoked(self):
        mgr, _ = self._make_manager()
        agent = _agent(rung=2)
        asgn = _assignment(agent.id, rung=2)
        old_cred = mgr.issue_initial(agent, asgn)

        asgn3 = _assignment(agent.id, rung=3)
        agent.current_rung = 3
        mgr.on_rung_change(agent, asgn3)

        active = mgr.active_for_agent(agent.id)
        self.assertEqual(len(active), 1)
        self.assertNotEqual(active[0].id, old_cred.id)

    def test_all_for_agent_includes_history(self):
        mgr, _ = self._make_manager()
        agent = _agent(rung=1)
        asgn1 = _assignment(agent.id, rung=1)
        mgr.issue_initial(agent, asgn1)

        asgn2 = _assignment(agent.id, rung=2)
        agent.current_rung = 2
        mgr.on_rung_change(agent, asgn2)

        all_creds = mgr.all_for_agent(agent.id)
        self.assertEqual(len(all_creds), 2)

    def test_summary_counts(self):
        mgr, _ = self._make_manager()
        for i in range(3):
            agent = _agent(rung=i + 1)
            asgn = _assignment(agent.id, rung=i + 1)
            mgr.issue_initial(agent, asgn)

        summary = mgr.summary()
        self.assertEqual(summary["total"], 3)
        self.assertEqual(summary["active"], 3)
        self.assertEqual(summary["revoked"], 0)

    def test_expire_stale_marks_expired(self):
        mgr, creds = self._make_manager()
        agent = _agent(rung=1)
        asgn = _assignment(agent.id, rung=1)
        cred = mgr.issue_initial(agent, asgn)

        cred.expires_at = "2000-01-01T00:00:00+00:00"
        mgr.expire_stale()
        self.assertEqual(creds[cred.id].status, CredentialStatus.EXPIRED)

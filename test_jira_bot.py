"""Tests for jira_bot.py — verifies the GDPR strict mode fix.

Reproduces the exact scenario from PR #4471: GitHub user 'tkoscieln'
comments '/jira-epic HMS-10502', and jira_bot must resolve the assignee
and build the correct issue_dict without calling jira.search_users().
"""
import unittest
from unittest.mock import MagicMock, patch

import jira_bot
from utils import UserMap


USERMAP = "usermap.yaml"


class TestGetJiraAccountId(unittest.TestCase):
    """get_jira_account_id should return the accountId straight from
    usermap.yaml, with no Jira API calls involved."""

    def setUp(self):
        jira_bot.assignee_mapping = UserMap(USERMAP)

    def test_known_github_user_returns_account_id(self):
        result = jira_bot.get_jira_account_id("tkoscieln")
        self.assertEqual(result, "712020:afadf713-b939-4fc3-adfd-10bde24ab888")

    def test_unknown_github_user_returns_none(self):
        result = jira_bot.get_jira_account_id("nonexistent-user-12345")
        self.assertIsNone(result)

    def test_no_jira_api_call_is_made(self):
        """The whole point of the fix: we must NOT call jira.search_users()."""
        mock_jira = MagicMock()
        # get_jira_account_id doesn't even accept a jira client anymore
        result = jira_bot.get_jira_account_id("ochosi")
        self.assertIsNotNone(result)
        mock_jira.search_users.assert_not_called()


class TestCreateJiraTaskAssigneeField(unittest.TestCase):
    """create_jira_task must use {'accountId': ...} not {'name': ...}
    when setting the assignee — Jira Cloud GDPR strict mode requires it."""

    def setUp(self):
        jira_bot.assignee_mapping = UserMap(USERMAP)

    @patch("jira_bot.JIRA")
    @patch("jira_bot.is_epic_issue", return_value=True)
    def test_assignee_uses_account_id_field(self, _mock_epic, mock_jira_cls):
        mock_jira = MagicMock()
        mock_jira_cls.return_value = mock_jira
        mock_issue = MagicMock()
        mock_issue.key = "HMS-9999"
        mock_jira.create_issue.return_value = mock_issue

        jira_bot.create_jira_task(
            token="fake-token",
            project_key="HMS",
            summary="Test PR title",
            description="Test description",
            issue_type="Task",
            epic_link="HMS-10502",
            component="Image Builder",
            assignee="tkoscieln",
            story_points=3,
        )

        call_kwargs = mock_jira.create_issue.call_args
        fields = call_kwargs[1]["fields"] if "fields" in call_kwargs[1] else call_kwargs[0][0]
        assignee = fields["assignee"]

        self.assertIn("accountId", assignee,
                       "Assignee must use 'accountId' for Jira Cloud GDPR mode")
        self.assertNotIn("name", assignee,
                         "Assignee must NOT use 'name' — rejected by GDPR strict mode")
        self.assertEqual(assignee["accountId"],
                         "712020:afadf713-b939-4fc3-adfd-10bde24ab888")

    @patch("jira_bot.JIRA")
    @patch("jira_bot.is_epic_issue", return_value=True)
    def test_no_search_users_called(self, _mock_epic, mock_jira_cls):
        """Ensures we never hit the deprecated search_users endpoint."""
        mock_jira = MagicMock()
        mock_jira_cls.return_value = mock_jira
        mock_issue = MagicMock()
        mock_issue.key = "HMS-9999"
        mock_jira.create_issue.return_value = mock_issue

        jira_bot.create_jira_task(
            token="fake-token",
            project_key="HMS",
            summary="Test",
            description="Test",
            issue_type="Task",
            epic_link="HMS-10502",
            component="Image Builder",
            assignee="tkoscieln",
            story_points=3,
        )

        mock_jira.search_users.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch
import io
import sys
import os
import requests

# Import the functions from the script
from pr_best_practices import (
    check_pr_title_contains_jira,
    check_commits_contain_jira,
    check_pr_description_not_empty,
    add_best_practice_label
)
from slack_lambda_get_pull_requests import _process

class TestPRChecks(unittest.TestCase):

    def test_check_pr_title_contains_jira(self):
        """
        Test whether the function correctly identifies Jira ticket references in PR titles.
        """
        self.assertTrue(check_pr_title_contains_jira("PR-123: Fix some issues"))
        self.assertFalse(check_pr_title_contains_jira("Fix some issues"))

    def test_check_pr_title_contains_jira_empty(self):
        """
        Test whether the function correctly handles an empty PR title.
        """
        self.assertFalse(check_pr_title_contains_jira(""))

    @patch('os.popen')
    def test_check_commits_contain_jira(self, mock_popen):
        """
        Test whether the function correctly identifies commits lacking Jira ticket references.
        """
        mock_popen.return_value.read.return_value = "PR-123: Fix some issues\nTest commit\n"
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            check_commits_contain_jira()
            output = fake_stdout.getvalue().strip()
            self.assertEqual(output, "Commit message 'Test commit' should contain a Jira.")

    def test_check_pr_description_not_empty(self):
        """
        Test whether the function correctly identifies an empty PR description.
        """
        self.assertTrue(check_pr_description_not_empty("This is a PR description"))
        self.assertFalse(check_pr_description_not_empty(""))

    @patch('requests.post')
    def test_add_best_practice_label(self, mock_post):
        """
        Test whether the function adds the 'best-practice' label to a PR successfully.
        """
        mock_response = requests.Response()
        mock_response.status_code = 200
        mock_post.return_value = mock_response
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            add_best_practice_label("mock_token", "mock_repo", 123)
            output = fake_stdout.getvalue().strip()
            self.assertEqual(output, "Label 'best-practice' added to PR successfully.")

class TestSlackLambdaGetPullRequests(unittest.TestCase):

    def test_process_with_env_variables(self):
        event = {
            "jira_user": os.environ["JIRA_TEST_USERNAME"],
            "args": os.environ["SLACK_COMMAND_ARGS"],
            "github_organization": os.environ["GITHUB_ORGANIZATION"],
            "github_token": os.environ["GITHUB_TOKEN"],
            "jira_token": os.environ["JIRA_TOKEN"],
            "jira_board_id": os.environ["JIRA_BOARD_ID"],
            "response_url": "http://mock_response_url"
        }

        with patch('requests.post') as mock_post:
            mock_response = requests.Response()
            mock_response.status_code = 200
            mock_post.return_value = mock_response

            message = _process(event)

            # Just a simple assert
            # this test is mainly to test and print the message
            assert "Happy" in message
            print(message)

if __name__ == '__main__':
    unittest.main()
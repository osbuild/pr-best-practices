import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
import io
import sys
import os
import requests

# Import the functions from the script
from pr_best_practices import (
    check_pr_title_contains_jira,
    check_commits_contain_jira,
    check_jira_issues_public,
    check_pr_description_not_empty,
    add_best_practice_label
)

class TestPRChecks(unittest.TestCase):

    def test_check_pr_title_contains_jira(self):
        """
        Test whether the function correctly identifies Jira ticket references in PR titles.
        """

        # None as a return just means that this does not sys.exit()…
        self.assertIsNone(check_pr_title_contains_jira("myfile.py: Fix some issues (PR-123)"))

        output = io.StringIO()
        with redirect_stdout(output):
            # the next call actually does a system exit, so we'll better be prepared
            with self.assertRaises(SystemExit) as cm:
                check_pr_title_contains_jira("Fix some issues")
        self.assertEqual(cm.exception.code, 2)
        self.assertIn("The pull request title should follow this schema", output.getvalue())

    def test_check_pr_title_contains_jira_empty(self):
        """
        Test whether the function correctly handles an empty PR title.
        """
        with self.assertRaises(SystemExit) as cm:
            self.assertFalse(check_pr_title_contains_jira(""))
        self.assertEqual(cm.exception.code, 2)

    @patch('os.popen')
    def test_check_commits_contain_jira(self, mock_popen):
        """
        Test whether the function correctly identifies commits lacking Jira ticket references.
        """
        # checking for empty message
        mock_popen.return_value.read.return_value = "myfile.py: Fix some issues (PR-123)\n \nTest commit\n"
        with patch('sys.stdout', new=io.StringIO()) as fake_stdout:
            with self.assertRaises(SystemExit) as cm:
                check_commits_contain_jira("HEAD")
            self.assertEqual(cm.exception.code, 2)
            output = fake_stdout.getvalue().strip()
            self.assertIn("Found empty commit message.", output)

    def test_check_pr_description_not_empty(self):
        """
        Test whether the function correctly identifies an empty PR description.
        """
        # None as a return just means that this does not sys.exit()…
        self.assertIsNone(check_pr_description_not_empty("This is a PR description"))

        with self.assertRaises(SystemExit) as cm:
            self.assertFalse(check_pr_description_not_empty(""))
        self.assertEqual(cm.exception.code, 1)

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

    def test_check_jira_issues_public(self):

        output = io.StringIO()
        with redirect_stdout(output):
            self.assertFalse(check_jira_issues_public("myfile.py: Fix some issues (PR-123)"))
        self.assertIn("is not publicly accessible", output.getvalue())
        self.assertTrue(check_jira_issues_public("myfile.py: Fix some issues (HMS-1442)"))


if __name__ == '__main__':
    unittest.main()
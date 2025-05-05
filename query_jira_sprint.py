#!/usr/bin/python3

"""
Script to query Jira issues for the current sprint and process them using a reusable DataProcessor class.
"""

import argparse
import logging
import os
import re
import sys
import json

from utils import format_help_as_md, Cache
from jira import JIRA, JIRAError

logger = logging.getLogger(__name__)

JIRA_HOST = os.getenv("JIRA_HOST", "https://issues.redhat.com")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

class JiraDataProcessor:
    def __init__(self, jira_token):
        self.jira_token = jira_token
        self.jira = JIRA(JIRA_HOST, token_auth=self.jira_token)
        self.issues = []

    def fetch_current_sprint_issues(self):
        """
        Fetch issues for the current sprint.
        """
        jql = "sprint in openSprints() and assignee = currentUser()"
        try:
            self.issues = self.jira.search_issues(jql_str=jql)
        except JIRAError as e:
            logger.error(f"Failed to fetch issues for the current sprint: {e}")
            sys.exit(1)

    def process_issues(self):
        """
        Process the fetched issues and return structured data.
        """
        processed_issues = []
        for issue in self.issues:
            processed_issues.append({
                'key': issue.key,
                'summary': issue.fields.summary,
                'assignee': issue.fields.assignee.displayName if issue.fields.assignee else "None",
                'description': issue.fields.description,
                'status': issue.fields.status.name
            })
        return processed_issues

def main():
    """Query Jira issues for the current sprint and process them."""
    parser = argparse.ArgumentParser(allow_abbrev=False,
        description=__doc__,
        epilog="You can set the `JIRA_TOKEN` environment variable instead of using the `--jira-token` argument."
    )

    parser.add_argument("--jira-token", help="Set the API token for Jira", required=(JIRA_TOKEN is None))
    parser.add_argument("--debug", help="Enable debug logging", action="store_true")
    parser.add_argument("--quiet", help="No info logging. Use for automations", action="store_true")
    parser.add_argument("--help-md", help="Show help as Markdown", action="store_true")

    if "--help-md" in sys.argv:
        print(format_help_as_md(parser))
        sys.exit(0)

    args = parser.parse_args()

    if args.jira_token:
        jira_token = args.jira_token
    elif JIRA_TOKEN:
        jira_token = JIRA_TOKEN
    else:
        parser.error("The JIRA_TOKEN environment variable or the --jira-token argument is required.")

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    elif args.quiet:
        logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    else:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
        logger.propagate = False

    data_processor = JiraDataProcessor(jira_token)
    data_processor.fetch_current_sprint_issues()
    processed_issues = data_processor.process_issues()

    with open("current_sprint_issues.json", "w") as f:
        f.write(json.dumps(processed_issues, ensure_ascii=False, indent=2))

    logger.info(f"Processed {len(processed_issues)} issues from the current sprint.")

if __name__ == "__main__":
    main()
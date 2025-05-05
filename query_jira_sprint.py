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
BACKLOG_FILTER_ID = os.getenv("JIRA_BACKLOG_FILTER_ID")
JIRA_BOARD_ID = int(os.getenv("JIRA_BOARD_ID"))

class JiraDataProcessor:
    def __init__(self, jira_token):
        self.jira_token = jira_token
        self.jira = JIRA(JIRA_HOST, token_auth=self.jira_token)


    def fetch_sprints(self, board_id):
        """
        Fetch all sprints for a given board ID.
        """
        try:
            print(f"Fetching sprints for board ID: {board_id}")
            sprints = self.jira.sprints(board_id)
            # Filter sprints by the given board ID
            sprints_filtered = [sprint for sprint in sprints if getattr(sprint, 'originBoardId', None)]
            ret = []
            for sprint in sprints_filtered:
                ret.append({
                    'id': sprint.id,
                    'originBoardId': sprint.originBoardId,
                    'name': sprint.name,
                    'state': sprint.state,
                    'startDate': sprint.startDate,
                    'endDate': sprint.endDate
                })
            return ret
        except JIRAError as e:
            logger.error(f"Failed to fetch sprints for board ID {board_id}: {e}")
            sys.exit(1)


    def fetch_boards(self, project_key):
        """
        Fetch all boards for a given project key.
        """
        try:
            boards = self.jira.boards(projectKeyOrID=project_key)
            ret = []
            for board in boards:
                ret.append({
                    'id': board.id,
                    'name': board.name,
                    'type': board.type
                })
            return ret
        except JIRAError as e:
            logger.error(f"Failed to fetch boards for project key {project_key}: {e}")
            sys.exit(1)


    def _process_issues(self, issues):
        """
        Internal method to process fetched issues and return structured data.
        """
        processed_issues = []
        for issue in issues:
            processed_issues.append({
                'key': issue.key,
                'summary': issue.fields.summary,
                'assignee': issue.fields.assignee.displayName if issue.fields.assignee else "None",
                'description': issue.fields.description,
                'status': issue.fields.status.name
            })
        return processed_issues

    def fetch_current_sprint_issues(self):
        """
        Fetch issues for the current sprint and process them.
        """
        jql = "sprint in openSprints() and assignee = currentUser()"
        try:
            issues = self.jira.search_issues(jql_str=jql)
        except JIRAError as e:
            logger.error(f"Failed to fetch issues for the current sprint: {e}")
            sys.exit(1)
        return self._process_issues(issues)

    def fetch_current_backlog_issues(self, jira_filter_id):
        """
        Fetch issues for the backlog using a specific Jira filter ID and process them.
        """
        jql = f'filter = {jira_filter_id} and assignee = currentUser()'
        try:
            issues = self.jira.search_issues(jql_str=jql)
        except JIRAError as e:
            logger.error(f"Failed to fetch backlog issues for filter ID {jira_filter_id}: {e}")
            sys.exit(1)
        return self._process_issues(issues)


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

    # Uncomment the following line to fetch boards for a specific project key
    # can be useful for debugging
    # print(json.dumps(data_processor.fetch_boards("COMPOSER"), indent=2))

    processed_issues = {
        "current_sprint": data_processor.fetch_current_sprint_issues(),
        "backlog": data_processor.fetch_current_backlog_issues(BACKLOG_FILTER_ID)
    }

    with open("current_sprint_issues.json", "w") as f:
        f.write(json.dumps(processed_issues, ensure_ascii=False, indent=2))

    sprints = data_processor.fetch_sprints(JIRA_BOARD_ID)
    print(json.dumps(sprints, indent=2))
if __name__ == "__main__":
    main()
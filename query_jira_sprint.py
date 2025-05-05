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
JIRA_USERNAME = os.getenv("JIRA_USERNAME")

class JiraDataProcessor:
    def __init__(self, jira_token, jira_username=None, backlog_filter_id=None):
        self.jira_token = jira_token
        self.jira = JIRA(JIRA_HOST, token_auth=self.jira_token)
        self.backlog_filter_id = backlog_filter_id
        if jira_username:
            self.jira_username = f"'{jira_username}'"
        else:
            self.jira_username = "currentUser()"


    def fetch_sprints(self, board_id):
        """
        Fetch all sprints for a given board ID.
        """
        try:
            start_at = 0
            max_results = 50
            all_sprints = []

            while True:
                sprints = self.jira.sprints(board_id, startAt=start_at, maxResults=max_results)
                # .sprints() seems to return all sprints
                # so we'll filter them by BOARD_ID
                all_sprints.extend([sprint for sprint in sprints if getattr(sprint, 'originBoardId', None) == board_id])

                if len(sprints) < max_results:
                    break
                start_at += max_results

            sprints_filtered = [sprint for sprint in all_sprints if getattr(sprint, 'originBoardId', None)]
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
                'status': issue.fields.status.name,
                'sprint': issue.fields.customfield_12310940 if hasattr(issue.fields, 'customfield_12310940') else [],
            })
        return processed_issues

    def fetch_current_sprint_issues(self):
        """
        Fetch issues for the current sprint and process them.
        """
        jql = f"sprint in openSprints() and assignee = {self.jira_username}"
        try:
            issues = self.jira.search_issues(jql_str=jql)
        except JIRAError as e:
            logger.error(f"Failed to fetch issues for the current sprint: {e}")
            sys.exit(1)
        return self._process_issues(issues)

    
    def fetch_current_backlog_issues(self, exclude_resolved=True):
        """
        Fetch issues for the backlog using a specific Jira filter ID and process them.
        """
        jql = f"filter = {self.backlog_filter_id} and issuetype != 'EPIC' and assignee = {self.jira_username}"
        try:
            issues = self.jira.search_issues(jql_str=jql)
            # optionally exclude resolved issues
            # some inconsistencies can happen in jira we'll just filter them out
            issues_filtered = [i for i in issues if not i.fields.resolution] if exclude_resolved else issues
            issues_filtered = [i for i in issues_filtered if i.fields.status.name.lower() != 'closed'] if exclude_resolved else issues_filtered
            issues_filtered = [i for i in issues_filtered if i.fields.status.name.lower() != 'resolved'] if exclude_resolved else issues_filtered
            issues_filtered = [i for i in issues_filtered if i.fields.status.name.lower() != 'release pending'] if exclude_resolved else issues_filtered

            # filter out issues that are in an "ACTIVE" sprint
            ret = []
            for i in issues_filtered:
                # ugly workaround to check if the issue is in an active sprint
                # as customfield_12310940 seems to be a string, not an object
                # TBD: proper implementation to get an object for the sprint
                if hasattr(i.fields, 'customfield_12310940') and \
                    i.fields.customfield_12310940 and \
                    any(["state=ACTIVE" in sprint for sprint in i.fields.customfield_12310940]):
                    continue
                ret.append(i)
        except JIRAError as e:
            logger.error(f"Failed to fetch backlog issues for filter ID {self.backlog_filter_id}: {e}")
            sys.exit(1)
        return self._process_issues(ret)


    def get_issue_overview(self):
        """
        Get an overview of issues in the current sprint and backlog.
        """
        current_sprint_issues = self.fetch_current_sprint_issues()
        backlog_issues = self.fetch_current_backlog_issues()

        return {
            'current_sprint': current_sprint_issues,
            'backlog': backlog_issues
        }

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

    data_processor = JiraDataProcessor(jira_token,JIRA_USERNAME, BACKLOG_FILTER_ID)

    # Uncomment the following line to fetch boards for a specific project key
    # can be useful for debugging or future use
    # print(json.dumps(data_processor.fetch_boards("COMPOSER"), indent=2))

    # Fetch sprints for the specified board ID
    # can be useful for debugging or future use
    # sprints = data_processor.fetch_sprints(JIRA_BOARD_ID)
    # print(json.dumps(sprints, indent=2))

    processed_issues = data_processor.get_issue_overview()

    with open("current_sprint_issues.json", "w") as f:
        f.write(json.dumps(processed_issues, ensure_ascii=False, indent=2))

    logger.info(f"User '{JIRA_USERNAME}' has {len(processed_issues['current_sprint'])} issues in the current sprint, and {len(processed_issues['backlog'])} issues in the backlog.")
if __name__ == "__main__":
    main()
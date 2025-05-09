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
import time

from utils import format_help_as_md, Cache
from jira import JIRA, JIRAError

logger = logging.getLogger(__name__)

JIRA_HOST = os.getenv("JIRA_HOST", "https://issues.redhat.com")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

JIRA_BOARD_ID = os.getenv("JIRA_BOARD_ID")

JIRA_USERNAME = os.getenv("JIRA_USERNAME")

class JiraDataProcessor:
    def __init__(self, jira_token, jira_username=None, jira_board_id=None, jira_backlog_filter_id=None):
        self.jira_token = jira_token
        self.jira = JIRA(JIRA_HOST, token_auth=self.jira_token)
        self.jira_board_id = jira_board_id
        self.backlog_filter_id = jira_backlog_filter_id

        if jira_username:
            self.jira_username = f"'{jira_username}'"
        else:
            self.jira_username = "currentUser()"

        board_data = self.fetch_board(self.jira_board_id)
        self.board_data = board_data


    def fetch_sprints(self, board_id, max_retries=5):
        """
        Fetch all sprints for a given board ID.
        """
        start_at = 0
        max_results = 50
        all_sprints = []
        attempt = 0
        while True:
            attempt += 1
            try:
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
                status = getattr(e.response, 'status_code', None)
                # Handle rate limit (429)
                if status == 429 and attempt <= max_retries:
                    retry_after = e.response.headers.get("Retry-After")
                    try:
                        wait = max(int(retry_after),2)
                    except (TypeError, ValueError):
                        # Fallback to a default backoff if header missing or invalid
                        wait = 60
                    logger.warning(
                        f"Rate limit exceeded (attempt {attempt}/{max_retries}). "
                        f"Waiting {wait}s before retrying..."
                    )
                    time.sleep(wait)
                    continue

                # If we've retried too many times or it's a different error:
                logger.error(
                    f"Failed to fetch sprints for board ID {board_id} "
                    f"(status={status}) after {attempt} attempts: {e}"
                )
                raise e


    def fetch_board(self, board_id, max_retries=5):
        """
        Fetch board details for a given board ID, with retry-on-429 handling.

        :param board_id: ID of the board to fetch.
        :param max_retries: Maximum number of times to retry after 429 responses.
        :return: Parsed JSON configuration of the board.
        :raises SystemExit: If non-429 error occurs or retries are exhausted.
        """
        url = f"{JIRA_HOST}/rest/agile/1.0/board/{board_id}/configuration"
        attempt = 0

        while True:
            attempt += 1
            try:
                resp = self.jira._session.get(url)
                # raise_for_status will raise HTTPError for 4xx/5xx
                resp.raise_for_status()
                return resp.json()

            except JIRAError as e:
                status = getattr(e.response, 'status_code', None)
                # Handle rate limit (429)
                if status == 429 and attempt <= max_retries:
                    retry_after = e.response.headers.get("Retry-After")
                    try:
                        wait = max(int(retry_after),2)
                    except (TypeError, ValueError):
                        # Fallback to a default backoff if header missing or invalid
                        wait = 60
                    logger.warning(
                        f"Rate limit exceeded (attempt {attempt}/{max_retries}). "
                        f"Waiting {wait}s before retrying..."
                    )
                    time.sleep(wait)
                    continue

                # If we've retried too many times or it's a different error:
                logger.error(
                    f"Failed to fetch board configuration for board ID {board_id} "
                    f"(status={status}) after {attempt} attempts: {e}"
                )
                sys.exit(1)

    def _extract_sprint_info(self, sprint_string):
        """
        Extract sprint information from a string with optional and reordered attributes.
        """
        patterns = {
            'id': r'id=(\d+)[],]',
            'rapidViewId': r'rapidViewId=(\d+)[],]',
            'state': r'state=(\w+)[],]',
            'name': r'name=(.*?)[],]',
            'startDate': r'startDate=(.*?)[],]',
            'endDate': r'endDate=(.*?)[],]',
            'completeDate': r'completeDate=(.*?)[],]',
            'activatedDate': r'activatedDate=(.*?)[],]',
            'sequence': r'sequence=(\d+)[],]',
            'goal': r'goal=(.*?)[],]',
            'synced': r'synced=(\w+)[],]',
            'autoStartStop': r'autoStartStop=(\w+)[],]',
            'incompleteIssuesDestinationId': r'incompleteIssuesDestinationId=(-?\d+)[],]'
        }

        sprint_info = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, sprint_string)
            if match:
                sprint_info[key] = match.group(1)

        return sprint_info

    def _extract_sprint(self, issue):
        """
        Extract sprint information from the issue.
        """
        if hasattr(issue.fields, 'customfield_12310940'):
            sprint_strings = issue.fields.customfield_12310940
            if not sprint_strings:
                return []
            sprint_info = [self._extract_sprint_info(sprint_string) for sprint_string in sprint_strings]
            if sprint_info:
                return sprint_info
            return []
        else:
            return []


    def _get_column(self, status_id):
        """
        Get the column name for a given status ID.
        """
        col_sort_id = 0
        for column in self.board_data['columnConfig']['columns']:
            col_sort_id += 1
            if column['statuses']:
                for status in column['statuses']:
                    if status['id'] == status_id:
                        return {"name": column['name']
                                , "sort_id": col_sort_id}
        return None

    def _process_issues(self, issues):
        """
        Internal method to process fetched issues and return structured data.
        """
        processed_issues = []
        for issue in issues:
            processed_issues.append({
                'key': issue.key,
                'url': f"{JIRA_HOST}/browse/{issue.key}",
                'summary': issue.fields.summary,
                'assignee': issue.fields.assignee.displayName if issue.fields.assignee else "None",
                'description': issue.fields.description,
                'status': issue.fields.status.name,
                'sprint': self._extract_sprint(issue),
                'sprint_column': self._get_column(issue.fields.status.id),
            })
        return processed_issues

    def fetch_current_sprint_issues(self):
        """
        Fetch issues for the current sprint and process them.
        """
        jql = f"sprint in openSprints() and assignee = {self.jira_username}"
        attempt = 0
        while True:
            attempt += 1
            try:
                issues = self.jira.search_issues(jql_str=jql)
                break
            except JIRAError as e:
                status = getattr(e.response, 'status_code', None)
                if status == 429 and attempt <= 5:
                    retry_after = e.response.headers.get("Retry-After")
                    try:
                        wait = max(int(retry_after),2)
                    except (TypeError, ValueError):
                        wait = 60
                    logger.warning(
                        f"Rate limit exceeded (attempt {attempt}/5). "
                        f"Waiting {wait}s before retrying..."
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    f"Failed to fetch issues for the current sprint (attempt {attempt}/5): {e}"
                )
                raise e
        return self._process_issues(issues)

    def get_issue(self, key, max_retries=5):
        jql = f"key = {key}"
        attempt = 0
        while True:
            attempt += 1
            try:
                issue = self.jira.search_issues(jql_str=jql)
                return self._process_issues(issue)[0]
            except JIRAError as e:
                status = getattr(e.response, 'status_code', None)
                if status == 429 and attempt <= max_retries:
                    retry_after = e.response.headers.get("Retry-After")
                    try:
                        wait = max(int(retry_after),2)
                    except (TypeError, ValueError):
                        wait = 60
                    logger.warning(
                        f"Rate limit exceeded (attempt {attempt}/{max_retries}). "
                        f"Waiting {wait}s before retrying..."
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    f"Failed to fetch issue {key} (attempt {attempt}/{max_retries}): {e}"
                )
                raise e
    
    def fetch_current_backlog_issues(self, exclude_resolved=True, max_retries=5):
        """
        Fetch issues for the backlog using a specific Jira filter ID and process them.
        """
        if not self.backlog_filter_id:
            self.backlog_filter_id = self.board_data['filter']['id']

        if not self.backlog_filter_id:
            logger.error(f"No backlog filter ID found for board ID {self.jira_board_id}.")
            sys.exit(1)
        jql = f"filter = {self.backlog_filter_id} and issuetype != 'EPIC' and assignee = {self.jira_username}"
        attempt = 0
        while True:
            attempt += 1
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
                return self._process_issues(ret)
            except JIRAError as e:
                status = getattr(e.response, 'status_code', None)
                if status == 429 and attempt <= max_retries:
                    retry_after = e.response.headers.get("Retry-After")
                    try:
                        wait = max(int(retry_after),2)
                    except (TypeError, ValueError):
                        wait = 60
                    logger.warning(
                        f"Rate limit exceeded (attempt {attempt}/{max_retries}). "
                        f"Waiting {wait}s before retrying..."
                    )
                    time.sleep(wait)
                    continue
                logger.error(
                    f"Failed to fetch issues for the backlog (attempt {attempt}/{max_retries}): {e}"
                )
                raise e


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

    data_processor = JiraDataProcessor(jira_token,JIRA_USERNAME, JIRA_BOARD_ID)

    # Uncomment the following line to fetch boards for a specific project key
    # can be useful for debugging or future use
    # print(json.dumps(data_processor.fetch_board(JIRA_BOARD_ID), indent=2))

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
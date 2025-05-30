""" jira_bot.py - Bot able to create jira-issues from pull-requests
"""
import argparse
import os
import sys

from jira import JIRA
from utils import UserMap, format_help_as_md

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://issues.redhat.com")
DEFAULT_PROJECT_KEY = os.getenv("DEFAULT_PROJECT_KEY", "HMS")
DEFAULT_ISSUE_TYPE = os.getenv("DEFAULT_ISSUE_TYPE", "Task")
DEFAULT_COMPONENT = os.getenv("DEFAULT_COMPONENT", "Image Builder")


def get_jira_username(jira, github_nick):
    """
    Find the Jira username corresponding to a GitHub nickname.
    Can also resolve E-Mail to Jira username
    """
    global assignee_mapping

    user = assignee_mapping.github2jira(github_nick)
    if not user:
        print(f"🟠 Warning: No Jira username found for GitHub nickname '{github_nick}'.", file=sys.stderr)
        return None

    resolved_user = jira.search_users(user)
    if len(resolved_user) != 1:
        print(f"🟠 Warning: Expected 1 user for '{github_nick}' but got {resolved_user}.", file=sys.stderr)
        return None

    return resolved_user[0].name


def is_epic_issue(jira, issue_key):
    """
    Check if a Jira issue exists and is of the type 'Epic'.
    """
    try:
        # Get the issue
        print(f"Check if issue '{issue_key}' exists.", file=sys.stderr)
        issue = jira.issue(issue_key)

        # Check if the issue type is 'Epic'
        print(f"Check if issue '{issue_key}' is an Epic.", file=sys.stderr)
        if issue.fields.issuetype.name.lower() == 'epic':
            return True
        else:
            print(f"The issue '{issue_key}' is not an Epic but a {issue.fields.issuetype.name}.", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return False


# pylint: disable=too-many-arguments
def create_jira_task(token, project_key, summary, description, issue_type, epic_link, component, assignee, story_points):
    """
    create_jira_task creates a jira issue with the given parameter
    """
    options = {
        'server': JIRA_SERVER,
        'headers': {
            'Authorization': f'Bearer {token}'
        }
    }
    try:
        jira = JIRA(options=options)
        print("Connected to Jira successfully using a personal access token.", file=sys.stderr)
    # pylint: disable=broad-exception-caught
    except Exception as e:
        print(f"🔴 Failed to connect to Jira: {e}", file=sys.stderr)
        return

    # Check if Epic exists
    if not is_epic_issue(jira, epic_link):
        print(f"🔴 The Jira issue '{epic_link}' does not exist or is not of issuetype Epic.", file=sys.stderr)
        sys.exit(1)

    # Task creation dictionary
    issue_dict = {
        'project': {'key': project_key},
        'summary': summary,
        'description': description,
        'issuetype': {'name': issue_type},
        'customfield_12310243': story_points,
    }

    # Add epic link if provided
    if epic_link:
        issue_dict['customfield_12311140'] = epic_link

    # Add assignee if provided
    if assignee:
        issue_dict['assignee'] = {'name': get_jira_username(jira, assignee)}

    # Add component if provided
    if component:
        issue_dict['components'] = [{'name': component}]

    try:
        new_issue = jira.create_issue(fields=issue_dict)
        print(f"🟢 Task created successfully: {new_issue.key}", file=sys.stderr)
        print(new_issue.key)
    # pylint: disable=broad-exception-caught
    except Exception as e:
        print(f"🔴 Failed to create task: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """ main - command line parsing and calling the bot """
    global assignee_mapping

    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Create a Jira task.")
    parser.add_argument('--token', required=True,
                        help="The Jira personal access token")
    parser.add_argument('--project-key', default=DEFAULT_PROJECT_KEY,
                        help=f"The Jira project id (optional, default: {DEFAULT_PROJECT_KEY})")
    parser.add_argument('--summary', required=True,
                        help="The summary of the task.")
    parser.add_argument('--description', required=True,
                        help="The description of the task.")
    parser.add_argument('--issuetype', default=DEFAULT_ISSUE_TYPE,
                        help=f"The issue type id (optional, default: {DEFAULT_ISSUE_TYPE})")
    parser.add_argument('--assignee',
                        help="The assignee of the task.")
    parser.add_argument('--story-points', type=int, default=3,
                        help="Story points to assign to the task (default: 3).")
    parser.add_argument('--epic-link', required=True,
                        help="The epic link (optional, e.g. 'HMS-123')")
    parser.add_argument('--component', default=DEFAULT_COMPONENT,
                        help=f"The component (default: '{DEFAULT_COMPONENT}').")
    parser.add_argument('--assignees-yaml', default='usermap.yaml',
                        help="Path to the YAML file containing GitHub-to-Jira username mappings (default: usermap.yaml).")
    parser.add_argument("--help-md", help="Show help as Markdown", action="store_true")

    # workaround that required attribute are not given for --help-md
    if "--help-md" in sys.argv:
        print(format_help_as_md(parser))
        sys.exit(0)

    args = parser.parse_args()

    assignee_mapping = UserMap(args.assignees_yaml)

    # Call the task creation function with parsed arguments
    create_jira_task(
        token=args.token,
        project_key=args.project_key,
        summary=args.summary,
        description=args.description,
        issue_type=args.issuetype,
        epic_link=args.epic_link,
        component=args.component,
        assignee=args.assignee,
        story_points=args.story_points
    )


if __name__ == "__main__":
    main()

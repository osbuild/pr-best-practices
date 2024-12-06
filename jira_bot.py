""" jira_bot.py - Bot able to create jira-issues from pull-requests
"""
import argparse
import os
import sys
import yaml

from jira import JIRA

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://issues.redhat.com")
DEFAULT_PROJECT_KEY = os.getenv("DEFAULT_PROJECT_KEY", "HMS")
DEFAULT_ISSUE_TYPE = os.getenv("DEFAULT_ISSUE_TYPE", "Task")
DEFAULT_COMPONENT = os.getenv("DEFAULT_COMPONENT", "Image Builder")


def load_assignee_mapping(file_path):
    """
    Load GitHub-to-Jira username mappings from a YAML file.
    """
    try:
        with open(file_path, 'r') as yaml_file:
            data = yaml.safe_load(yaml_file)
            return data.get('assignees', {})
    except Exception as e:
        print(f"Error loading YAML file '{file_path}': {e}", file=sys.stderr)
        return {}


def get_jira_username(github_nick, mapping):
    """
    Find the Jira username corresponding to a GitHub nickname.
    """
    return mapping.get(github_nick, None)


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
        issue_dict['assignee'] = {'name': assignee}

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


def main():
    """ main - command line parsing and calling the bot """
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
    parser.add_argument('--assignees-yaml', default='assignees.yaml',
                        help="Path to the YAML file containing GitHub-to-Jira username mappings (default: assignees.yaml).")

    args = parser.parse_args()

    # Get the Jira username based on the GitHub nickname, if provided
    assignee_mapping = load_assignee_mapping(args.assignees_yaml)
    jira_username = None
    if args.assignee:
        jira_username = get_jira_username(args.assignee, assignee_mapping)
        if not jira_username:
            print(f"🟠 Warning: No Jira username found for GitHub nickname '{args.assignee}'.", file=sys.stderr)

    # Call the task creation function with parsed arguments
    create_jira_task(
        token=args.token,
        project_key=args.project_key,
        summary=args.summary,
        description=args.description,
        issue_type=args.issuetype,
        epic_link=args.epic_link,
        component=args.component,
        assignee=jira_username,
        story_points=args.story_points
    )


if __name__ == "__main__":
    main()

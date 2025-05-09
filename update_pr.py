import argparse
import requests
import sys
from utils import format_help_as_md

def process_github_event(comment_url, issue_url, github_token, pr_title, pr_body, jira_key):
    """
    Add a rocket reaction to a comment and update a pull request title and body with a JIRA key.
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Authorization": f"Bearer {github_token}"
    }

    if comment_url:
        # Add a rocket reaction to the comment
        reaction_url = f"{comment_url}/reactions"
        reaction_payload = {"content": "rocket"}
        reaction_response = requests.post(
            reaction_url,
            headers=headers,
            json=reaction_payload
        )

        if reaction_response.status_code >= 200 and reaction_response.status_code < 300:
            print("🟢 Rocket reaction added to the comment.")
        else:
            print(f"Failed to add reaction: {reaction_response.status_code} - {reaction_response.text}")

    # Update the pull request title and body
    new_title = f"{pr_title} ({jira_key})"
    new_body = f"{pr_body}\n\nJIRA: [{jira_key}](https://issues.redhat.com/browse/{jira_key})"
    issue_payload = {"title": new_title, "body": new_body}
    issue_response = requests.patch(
        issue_url,
        headers=headers,
        json=issue_payload
    )

    if issue_response.status_code == 200:
        print("🟢 Pull request title and body updated.")
    else:
        print(f"Failed to update pull request: {issue_response.status_code} - {issue_response.text}")


def main():
    parser = argparse.ArgumentParser(description="Process a GitHub event to add a reaction and update PR metadata.")
    parser.add_argument("--comment-url", help="URL of the GitHub comment to react to.")
    parser.add_argument("--issue-url", required=True, help="URL of the GitHub issue or pull request to update.")
    parser.add_argument("--github-token", required=True, help="GitHub personal access token.")
    parser.add_argument("--pr-title", required=True, help="Current title of the pull request.")
    parser.add_argument("--pr-body", required=True, help="Current body of the pull request.")
    parser.add_argument("--jira-key", required=True, help="JIRA key to append to the pull request.")
    parser.add_argument("--help-md", help="Show help as Markdown", action="store_true")

    # workaround that required attribute are not given for --help-md
    if "--help-md" in sys.argv:
        print(format_help_as_md(parser))
        sys.exit(0)

    args = parser.parse_args()

    process_github_event(
        comment_url=args.comment_url,
        issue_url=args.issue_url,
        github_token=args.github_token,
        pr_title=args.pr_title,
        pr_body=args.pr_body,
        jira_key=args.jira_key
    )


if __name__ == "__main__":
    main()

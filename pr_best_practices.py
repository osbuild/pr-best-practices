import argparse
import re
import os
import sys
import requests
from utils import format_help_as_md

def check_jira_issues_public(text):
    for match in re.findall(r"[A-Z][A-Z0-9]+-[0-9]+", text):
        url = f"https://issues.redhat.com/browse/{match}"
        res = requests.get(url)

        if res.status_code != 200:
            print("⛔ Assumed issue {match!r} is not publicly accessible.")


def check_pr_title_contains_jira(title):
    regex = r"(.*[?<=:])(.*[?<= \(])(\([A-Z][A-Z0-9]+-[0-9]+\))"
    if re.search(regex, title):
        print("✅ Pull request title complies with our schema.")

        check_jira_issues_public(title)
    else:
        print("⛔ The pull request title should follow this schema:\n"
              " `component: This describes the change (JIRA-001)`\n"
              f"but instead looks like this:\n `{title}`")
        sys.exit(2)


def check_commits_contain_jira(head):
    cmd = f"git rev-list main..{head} --format='%s: %b' --no-commit-header"
    commits = os.popen(cmd).read().strip().split('\n')
    for commit in commits:
        # We can directly mark commits that are empty
        if not commit.strip():
            print(f"Commit message '{commit}' should contain a Jira.")
            continue

        check_jira_issues_public(commit)


def check_pr_description_not_empty(description):
    if description.strip():
        print("✅ Pull request description is not empty.")

        check_jira_issues_public(description.strip())
    else:
        print("⛔ The pull request needs a description.")
        sys.exit(1)


def check_pr_description_contains_jira(description):
    regex = r"JIRA: \[[A-Z]+-[0-9]+\]\(https:\/\/issues.redhat.com\/browse\/[A-Z]+-[0-9]+\)"
    match = re.search(regex, description)
    if match:
        print(f"Found a Jira reference in the PR description: '{match.group(0)}'")
        sys.exit(2)
    else:
        print("The pull request description doesn't contain a Jira reference yet. Continue.")


def add_best_practice_label(token, repository, pr_number):
    github_api_url = "https://api.github.com"
    url = f"{github_api_url}/repos/{repository}/issues/{pr_number}/labels"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json"
    }
    payload = {
        "labels": ["🌟 best practice"]
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        print(f"Failed to add label to PR. Status code: {response.status_code}")
        sys.exit(1)
    print("Label 'best-practice' added to PR successfully.")


if __name__ == "__main__":
    my_filename = os.path.basename(__file__)
    parser = argparse.ArgumentParser(
        description="Perform various checks and actions related to GitHub Pull Requests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Example usages:
python {my_filename} --pr-title "PR-123: Fix some issues"
python {my_filename} --check-commits
python {my_filename} --pr-description "This is a PR description"
python {my_filename} --add-label --token "your_token" --repository "your_repository" --pr-number 123"""
    )
    parser.add_argument("--pr-title", help="Check if PR title contains a Jira ticket")
    parser.add_argument("--check-commits", help="HEAD sha1 has of the pull request")
    parser.add_argument("--pr-description", help="Check if PR description is not empty")
    parser.add_argument("--pr-description-jira", help="Check if PR description contains a Jira reference")
    parser.add_argument("--add-label", action="store_true", help="Add 'best-practice' label to the PR")
    parser.add_argument("--token", help="GitHub token")
    parser.add_argument("--repository", help="GitHub repository")
    parser.add_argument("--pr-number", type=int, help="Pull Request number")
    parser.add_argument("--help-md", help="Show help as Markdown", action="store_true")

    args = parser.parse_args()

    if args.help_md:
        print(format_help_as_md(parser))
        sys.exit(0)

    if args.pr_title:
        check_pr_title_contains_jira(args.pr_title)
    if args.check_commits:
        check_commits_contain_jira(args.check_commits)
    if args.pr_description is not None:
        check_pr_description_not_empty(args.pr_description)
    if args.pr_description_jira is not None:
        check_pr_description_contains_jira(args.pr_description_jira)
    if args.add_label:
        if not (args.token and args.repository and args.pr_number):
            print("⛔ Token, repository, and PR number must be provided to add label.")
            sys.exit(1)
        add_best_practice_label(args.token, args.repository, args.pr_number)

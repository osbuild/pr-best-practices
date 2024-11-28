import argparse
import re
import os
import sys
import requests


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


def add_comment_to_pr(repository, pr_number, comment, github_token):
    """
    Add a comment to a GitHub pull request.

    Args:
        repo_owner (str): The owner of the repository (e.g., "octocat").
        repo_name (str): The name of the repository (e.g., "Hello-World").
        pr_number (int): The number of the pull request.
        comment (str): The comment to be added to the pull request.
        github_token (str): Personal access token for GitHub.

    Returns:
        dict: The response from the GitHub API.
    """
    url = f"https://api.github.com/repos/{repository}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload = {"body": comment}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perform various checks and actions related to GitHub Pull Requests.")
    parser.add_argument("--pr-title", help="Check if PR title contains a Jira ticket")
    parser.add_argument("--check-commits", help="HEAD sha1 has of the pull request")
    parser.add_argument("--pr-description", help="Check if PR description is not empty")
    parser.add_argument("--add-label", action="store_true", help="Add 'best-practice' label to the PR")
    parser.add_argument("--token", help="GitHub token")
    parser.add_argument("--repository", help="GitHub repository")
    parser.add_argument("--pr-number", type=int, help="Pull Request number")
    parser.add_argument("--add-comment", help="Comment to add to a pull request (also requires: repository, token, pr-number)")

    args = parser.parse_args()

    if args.pr_title:
        check_pr_title_contains_jira(args.pr_title)
    if args.check_commits:
        check_commits_contain_jira(args.check_commits)
    if args.pr_description is not None:
        check_pr_description_not_empty(args.pr_description)
    if args.add_comment_to_pr:
        add_comment(args.repository, args.pr_number, args.add_comment, args.token)
    if args.add_label:
        if not (args.token and args.repository and args.pr_number):
            print("⛔ Token, repository, and PR number must be provided to add label.")
            sys.exit(1)
        add_best_practice_label(args.token, args.repository, args.pr_number)

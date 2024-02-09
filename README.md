# GitHub Pull Request Checks and Actions Script

This Python script allows you to perform various checks and actions related to GitHub Pull Requests (PRs) conveniently from the command line. You can use it to ensure that your PRs adhere to certain standards and best practices before merging them into your codebase.

## Features

- **Check PR Title Contains Jira Ticket**: Verifies if the title of the pull request contains a Jira ticket reference.
- **Check Commits Contain Jira Ticket**: Scans the commits in the pull request to ensure each commit message contains a Jira ticket reference.
- **Check PR Description Is Not Empty**: Ensures that the pull request description is not empty.
- **Add 'best-practice' Label to PR**: Automatically adds the 'best-practice' label to the pull request on GitHub.

## Prerequisites

- Python 3 installed on your system.
- Access to the GitHub repository where you want to perform these checks and actions.
- Personal access token with the necessary permissions to interact with the GitHub API.

## Installation

1. Clone this repository to your local machine:

    ```bash
    git clone https://github.com/your_username/github-pr-checks.git
    ```

2. Navigate to the directory containing the script:

    ```bash
    cd github-pr-checks
    ```

3. Install the required dependencies (requests module):

    ```bash
    pip install requests
    ```

## Usage

Run the script with appropriate command-line arguments to execute specific checks or actions. Below are the available options:

- `--pr-title`: Check if the PR title contains a Jira ticket.
- `--check-commits`: Check if commits contain a Jira ticket.
- `--pr-description`: Check if the PR description is not empty.
- `--add-label`: Add the 'best-practice' label to the PR.
- `--token`: GitHub personal access token with necessary permissions.
- `--repository`: GitHub repository where the PR exists.
- `--pr-number`: Pull request number.

Example usages:

```bash
python pr_checks.py --pr-title "PR-123: Fix some issues"
python pr_checks.py --check-commits
python pr_checks.py --pr-description "This is a PR description"
python pr_checks.py --add-label --token "your_token" --repository "your_repository" --pr-number 123
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

You should replace placeholders like `your_username`, `your_token`, and `your_repository` with your actual GitHub username, token, and repository name, respectively. Additionally, make sure to update the license file (`LICENSE`) according to your preferences or requirements.
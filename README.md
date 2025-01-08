# GitHub Pull Request Checks and Actions Script

These Python scripts allow you to perform various checks and actions related to GitHub Pull Requests (PRs).
You can use them to ensure that your PRs adhere to certain standards and best practices before merging them into your codebase.

The simplest way to use this is by leveraging `action.yml` and integrate the scripts into your GitHub Actions workflow.

## Features

- **Check PR Title Contains Jira Ticket**: Verifies if the title of the pull request contains a Jira ticket reference.
- **Check Commits Contain Jira Ticket**: Scans the commits in the pull request to ensure each commit message contains a Jira ticket reference.
- **Check PR Description Is Not Empty**: Ensures that the pull request description is not empty.
- **Add 'best-practice' Label to PR**: Automatically adds the 'best-practice' label to the pull request on GitHub.
- **Creates a new Jira Ticket**: If the command `/jira-epic YOURJIRAKEY-1234` is detected in the **description** or a **comment** a Jira **Task** is created under the given Jira **Epic** "YOURJIRAKEY-1234"

## Integration in your GitHub project

create a file in `.github/workflows` e.g. `.github/workflows/pr_best_practices.yml`

```
name: "Verify PR best practices and check for `/jira-epic`"

on:
  pull_request_target:
    branches: [main]
    types: [opened, synchronize, reopened, edited]
  issue_comment:
    types: [created]

jobs:
  pr-best-practices:
    runs-on: ubuntu-latest
    steps:
      - name: PR best practice check
        uses: osbuild/pr-best-practices@main
        with:
          token: ${{ secrets.YOUR_GITHUB_ACCESS_TOKEN }}
          jira_token: ${{ secrets.YOUR_JIRA_ACCESS_TOKEN }}
```

## Local use & Development

Those script can also be used from the command line.

### Local Prerequisites

- Python 3 installed on your system.
- Access to the GitHub repository where you want to perform these checks and actions.
- Personal access token with the necessary permissions to interact with the GitHub API.

### Local Installation

1. Clone this repository to your local machine:

    ```bash
    git clone https://github.com/your_username/github-pr-checks.git
    ```

2. Navigate to the directory containing the script:

    ```bash
    cd github-pr-checks
    ```

3. Install the required dependencies:

    ```bash
    pip install -r requirements.txt
    ```

## Local Usage

 * [pr_best_practices.py](pr_best_practices.md)
 * [jira_bot.py](jira_bot.md)
 * [udpate_pr.py](update_pr.md)
 * `extract_jira_key.py`
   Extracts the jira key from the given text. The first argument is expected to be the whole text to process.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

You should replace placeholders like `your_username`, `your_token`, and `your_repository` with your actual GitHub username, token, and repository name, respectively. Additionally, make sure to update the license file (`LICENSE`) according to your preferences or requirements.
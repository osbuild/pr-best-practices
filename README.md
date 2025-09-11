# GitHub Pull Request Checks and Actions Script

These Python scripts allow you to perform various checks and actions related to GitHub Pull Requests (PRs).
You can use them to ensure that your PRs adhere to certain standards and best practices before merging them into your codebase.

The simplest way to use this is by leveraging `action.yml` and integrate the scripts into your GitHub Actions workflow.

The slack integration, also contained in this repository is [documented below](#slack-integration)

## Features

- **Check PR Title Contains Jira Ticket**: Verifies if the title of the pull request contains a Jira ticket reference.
- **Check Commits Contain Jira Ticket**: Scans the commits in the pull request to ensure each commit message contains a Jira ticket reference.
- **Check PR Description Is Not Empty**: Ensures that the pull request description is not empty.
- **Add 'best-practice' Label to PR**: Automatically adds the 'best-practice' label to the pull request on GitHub.
- **Creates a new Jira Ticket**: If the command `/jira-epic YOURJIRAKEY-1234` is detected in the **description** or a **comment** a Jira **Task** is created under the given Jira **Epic** "YOURJIRAKEY-1234"
 - **Auto-create Jira Task for Issues**: When a new GitHub Issue is opened, a Jira Task can be created automatically if an epic is configured via the `new_issues_jira_epic` input. If unset, no task is created. The created Jira key is appended to the GitHub Issue title and body.

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
  issues:
    types: [opened]

jobs:
  pr-best-practices:
    runs-on: ubuntu-latest
    steps:
      - name: PR best practice check
        uses: osbuild/pr-best-practices@main
        with:
          token: ${{ secrets.YOUR_GITHUB_ACCESS_TOKEN }}
          jira_token: ${{ secrets.YOUR_JIRA_ACCESS_TOKEN }}
          # Optional: create Jira tasks for newly opened GitHub Issues under this Epic
          # If omitted, no task will be created for new issues
          new_issues_jira_epic: HMS-5279
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

 * [get_pull_requests.py](get_pull_requests.md)
 * [pr_best_practices.py](pr_best_practices.md)
 * [jira_bot.py](jira_bot.md)
 * [udpate_pr.py](update_pr.md)
 * `extract_jira_key.py`
   Extracts the jira key from the given text. The first argument is expected to be the whole text to process.
 * [get_jira_sprint.py](get_jira_sprint.md)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

You should replace placeholders like `your_username`, `your_token`, and `your_repository` with your actual GitHub username, token, and repository name, respectively. Additionally, make sure to update the license file (`LICENSE`) according to your preferences or requirements.

# Slack integration
This repository also contains scripts (Amazon AWS lambda functions) to generate responses for Slack commands.

## Overview
The Slack integration works like this:

1. A Slack command is set up to trigger a "Request URL"
1. This "Request URL" is implemented by a "Function URL" of an AWS Lambda
1. The request gets validated with the `X-Slack-Signature` sent by Slack against the "Signing Secret"
1. An initial response is sent back (3 sec. timeout of Slack has to be taken into account)
1. Depending on the command another lambda function takes care of handling the real response

**All commands** are handled by [`slack_lambda.py`](slack_lambda.md), which validates
the request and sends the response back to Slack. This response sometimes is just
a confirmation of the received command and further processing is done in parallel.

The command `/sprint-overview` results in a second lambda implemented in
`slack_lambda_get_pull_requests.py`.
This uses [`get_jira_sprint.py`](get_jira_sprint.md) and [`get_pull_requets.py`](get_pull_requets.md) to collect and
send back an overview to the Slack user.

## Re-deployment
To deploy a new version, please run

```
make build
```

This will package all necessary files into ZIP files, ready to be uploaded to AWS.

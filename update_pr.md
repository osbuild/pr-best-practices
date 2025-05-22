# Usage
```
       update_pr.py [-h] [--comment-url COMMENT_URL] --issue-url ISSUE_URL
                    --github-token GITHUB_TOKEN --pr-title PR_TITLE --pr-body
                    PR_BODY --jira-key JIRA_KEY [--help-md]
```
Process a GitHub event to add a reaction and update PR metadata.

# Options
```
  -h, --help            show this help message and exit
  --comment-url COMMENT_URL
                        URL of the GitHub comment to react to.
  --issue-url ISSUE_URL
                        URL of the GitHub issue or pull request to update.
  --github-token GITHUB_TOKEN
                        GitHub personal access token.
  --pr-title PR_TITLE   Current title of the pull request.
  --pr-body PR_BODY     Current body of the pull request.
  --jira-key JIRA_KEY   JIRA key to append to the pull request.
  --help-md             Show help as Markdown
```
----
Update this by editing doc strings in `update_pr.py` and running `make docs`

# Usage
```
       get_pull_requests.py [-h] [--github-token GITHUB_TOKEN]
                            [--jira-host JIRA_HOST] [--jira-token JIRA_TOKEN]
                            --org ORG [--repo REPO] [--author AUTHOR]
                            [--dry-run | --no-dry-run] [--help-md]
```
Small script to return all pull requests for a given organisation, repository
and assignee

# Options
```
  -h, --help            show this help message and exit
  --github-token GITHUB_TOKEN
                        Set a token for github.com
  --jira-host JIRA_HOST
                        The jira hostname to use
  --jira-token JIRA_TOKEN
                        Set the API token for jira
  --org ORG             Set an organisation on github.com
  --repo REPO           Set a repo in `--org` on github.com
  --author AUTHOR       Author of pull requests
  --dry-run, --no-dry-run
                        Don't send Slack notifications
  --help-md             Show help as Markdown
```
You can set the `GITHUB_TOKEN` environment variable instead of using the
`--github-token` argument. You can also set the `PR_BEST_PRACTICES_TEST_CACHE`
environment variable to anything (e.g. `1`) use the cache.


# Usage
```
       get_pull_requests.py [-h] [--github-token GITHUB_TOKEN] --org ORG
                            [--repo REPO] [--author AUTHOR]
                            [--dry-run | --no-dry-run] [--help-md]
```
# Options
```
  -h, --help            show this help message and exit
  --github-token GITHUB_TOKEN
                        Set a token for github.com
  --org ORG             Set an organisation on github.com
  --repo REPO           Set a repo in `--org` on github.com
  --author AUTHOR       Author of pull requests
  --dry-run, --no-dry-run
                        Don't send Slack notifications
  --help-md             Show help as Markdown
```

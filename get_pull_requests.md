# Usage
```
       get_pull_requests.py [-h] --github-token GITHUB_TOKEN --org ORG
                            [--repo REPO] [--author AUTHOR]
                            [--dry-run | --no-dry-run] [--quiet] [--debug]
                            [--help-md]
```
Returns all pull requests for a given organisation, repository and assignee
Saves a `pr_data_collection.json` to be used with following scripts.
Alternatively the class `DataProcessor` can be used to get the data from
within python.

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
  --quiet               No info logging. Use for automations
  --debug               Enable debug logging
  --help-md             Show help as Markdown
```
You can set the `GITHUB_TOKEN` environment variable instead of using the
`--github-token` argument. You can also set the `PR_BEST_PRACTICES_TEST_CACHE`
environment variable to anything (e.g. `1`) use the cache.


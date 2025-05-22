# Usage
```
       get_jira_sprint.py [-h] --jira-token JIRA_TOKEN [--debug] [--quiet]
                          [--help-md]
```
Script to query Jira issues for the current sprint. Saves a
`current_sprint_issues.json` to be used with following scripts. Alternatively
the class `JiraDataProcessor` can be used to get the data from within python.

# Options
```
  -h, --help            show this help message and exit
  --jira-token JIRA_TOKEN
                        Set the API token for Jira
  --debug               Enable debug logging
  --quiet               No info logging. Use for automations
  --help-md             Show help as Markdown
```
You can set the `JIRA_TOKEN` environment variable instead of using the
`--jira-token` argument. The environment variable `JIRA_BOARD_ID` will be used
to get the underlying issue filter and sprint information. The environment
variable `JIRA_USERNAME` will be used to filter the information for this user.
When not set Jira's `currentUser()` will be used instead.

----
Update this by editing doc strings in `get_jira_sprint.py` and running `make docs`

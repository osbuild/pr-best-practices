# Usage
```
       jira_bot.py [-h] --token TOKEN [--project-key PROJECT_KEY] --summary
                   SUMMARY --description DESCRIPTION [--issuetype ISSUETYPE]
                   [--assignee ASSIGNEE] [--story-points STORY_POINTS]
                   --epic-link EPIC_LINK [--component COMPONENT]
                   [--assignees-yaml ASSIGNEES_YAML] [--help-md]
```
Create a Jira task.

# Options
```
  -h, --help            show this help message and exit
  --token TOKEN         The Jira personal access token
  --project-key PROJECT_KEY
                        The Jira project id (optional, default: HMS)
  --summary SUMMARY     The summary of the task.
  --description DESCRIPTION
                        The description of the task.
  --issuetype ISSUETYPE
                        The issue type id (optional, default: Task)
  --assignee ASSIGNEE   The assignee of the task.
  --story-points STORY_POINTS
                        Story points to assign to the task (default: 3).
  --epic-link EPIC_LINK
                        The epic link (optional, e.g. 'HMS-123')
  --component COMPONENT
                        The component (default: 'Image Builder').
  --assignees-yaml ASSIGNEES_YAML
                        Path to the YAML file containing GitHub-to-Jira
                        username mappings (default: usermap.yaml).
  --help-md             Show help as Markdown
```
----
Update this by editing doc strings in `jira_bot.py` and running `make docs`

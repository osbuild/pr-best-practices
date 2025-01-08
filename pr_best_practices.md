```
usage: pr_best_practices.py [-h] [--pr-title PR_TITLE]
                            [--check-commits CHECK_COMMITS]
                            [--pr-description PR_DESCRIPTION]
                            [--pr-description-jira PR_DESCRIPTION_JIRA]
                            [--add-label] [--token TOKEN]
                            [--repository REPOSITORY] [--pr-number PR_NUMBER]

Perform various checks and actions related to GitHub Pull Requests.

options:
  -h, --help            show this help message and exit
  --pr-title PR_TITLE   Check if PR title contains a Jira ticket
  --check-commits CHECK_COMMITS
                        HEAD sha1 has of the pull request
  --pr-description PR_DESCRIPTION
                        Check if PR description is not empty
  --pr-description-jira PR_DESCRIPTION_JIRA
                        Check if PR description contains a Jira reference
  --add-label           Add 'best-practice' label to the PR
  --token TOKEN         GitHub token
  --repository REPOSITORY
                        GitHub repository
  --pr-number PR_NUMBER
                        Pull Request number

Example usages:

python pr_best_practices.py --pr-title "PR-123: Fix some issues"
python pr_best_practices.py --check-commits
python pr_best_practices.py --pr-description "This is a PR description"
python pr_best_practices.py --add-label --token "your_token" --repository "your_repository" --pr-number 123
    
```

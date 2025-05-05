from datetime import datetime
import os
import requests

from get_jira_sprint import JiraDataProcessor
from get_pull_requests import DataProcessor
import logging

# Set the logging level to DEBUG for more verbose output
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def _process(event):
    user = event.get("user", "unknown")
    args = event.get("args", "unknown")

    github_organization = event.get("github_organization", "unknown")
    github_token = event.get("github_token", "unknown")

    jira_token = event.get("jira_token", "unknown")
    jira_user_domain = event.get("jira_user_domain", "unknown")
    jira_board_id = event.get("jira_board_id", "unknown")

    # TBD support "args" to contain two usernames (<slack_jira_user> <github_user>)
    # by default it only contains <github_user>

    pr_data_processor = DataProcessor(github_organization, None, args, True, github_token)
    pr_data_processor.process()

    jira_data_processor = JiraDataProcessor(jira_token, f"{user}@{jira_user_domain}", jira_board_id)
    processed_issues = jira_data_processor.get_issue_overview()

    message = f"Happy {datetime.now().strftime('%A')}! 👋\n\n"

    current_sprint_url = os.environ.get("CURRENT_SPRINT_URL")
    if current_sprint_url:
        current_sprint_url = f"<{current_sprint_url}|current sprint>"
    else:
        current_sprint_url = "current sprint"
    backlog_url = os.environ.get("BACKLOG_URL")

    if backlog_url:
        backlog_url = f"<{backlog_url}|backlog>"
    else:
        backlog_url = "backlog"

    # collect PRs not linked to sprint issues
    with_jira_for_backlog = []

    message += f"*Work from your {current_sprint_url}* 🟢\n"

    best_practice_issues = []
    normal_sprint_issues = []
    for sprint_issue in processed_issues["current_sprint"]:
        found = False
        for pr in pr_data_processor.with_jira:
            if pr["jira_key"] == sprint_issue["key"]:
                pr_title_link = f"<{pr['html_url']}|{pr['title']}>"
                jira_link = f"<{sprint_issue['url']}|{sprint_issue['key']} - {sprint_issue['summary']}>"
                entry = (
                    f" • {pr['repo']}: {pr_title_link} "
                    f"({jira_link})"
                )
                best_practice_issues.append(entry)
                found = True
            else:
                with_jira_for_backlog.append(pr)
        if not found:
            entry = f" • <{sprint_issue['url']}|{sprint_issue['key']}>: {sprint_issue['summary']}"
            normal_sprint_issues.append(entry)

    if best_practice_issues:
        message += "    Best practice:\n"
        message += "\n".join(best_practice_issues)
    if normal_sprint_issues:
        message += "    No implementation linked yet:\n"
        message += "\n".join(normal_sprint_issues)
    if not best_practice_issues and not normal_sprint_issues:
        message += "    :hanging-sloth: You don't have any issues in the current sprint"
    message += "\n\n"

    backlog_linked = []
    linked_non_backlog = []
    for backlog_issue in processed_issues["backlog"]:
        found = False
        for pr in with_jira_for_backlog:
            if pr["jira_key"] == backlog_issue["key"]:
                pr_title_link = f"<{pr['html_url']}|{pr['title']}>"
                jira_link = f"<{backlog_issue['url']}|{backlog_issue['key']} - {backlog_issue}>"
                entry = (
                    f" • {pr['repo']}: {pr_title_link} "
                    f"({jira_link})"
                )
                backlog_linked.append(entry)
                found = True
            else:
                pr_title_link = f"<{pr['html_url']}|{pr['title']}>"
                jira_link = f"<{backlog_issue['url']}|{backlog_issue['key']} - {backlog_issue}>"
                entry = (
                    f" • {pr['repo']}: {pr_title_link} "
                    f"({jira_link})"
                )
                linked_non_backlog.append(entry)
        if not found:
            pass
            # skip printings non-linked backlog issues for now
            # probably not needed

    if backlog_linked or linked_non_backlog:
        message += "*Other work* 🟡\n"
        if backlog_linked:
            message += f"    Already started implementation from {backlog_url}:\n"
            message += "\n".join(backlog_linked)
        if linked_non_backlog:
            message += f"    Implementation started but not in our {backlog_url}:\n"
            message += "\n".join(linked_non_backlog)
        message += "\n\n"
    # else section "other work" is skipped

    # Format the message for PRs without Jira keys
    if pr_data_processor.without_jira:
        pr_list = []
        for pr in pr_data_processor.without_jira:
            pr_title_link = f"<{pr['html_url']}|{pr['title']}>"
            entry = (
                f" • {pr['repo']}: {pr_title_link} "
                f"(+{pr['additions']}/-{pr['deletions']})"
            )
            pr_list.append(entry)
        pr_message = "\n".join(pr_list)
        # indenting does not work in slack, so we'll use some spaces for now
        pr_message += "\n\n    :cat_typing: Please add a Jira key to your PR title e.g by using `/jira-epic …` described <https://github.com/osbuild/pr-best-practices?tab=readme-ov-file#features|here>."
    else:
        if len(pr_data_processor.with_jira) == 0:
            pr_message = f"    *{user}* is not working on any PRs at the moment? :confusedoggo:"
        else:
            pr_message = "    :party-blob: All your PRs are best practice."

    message += f"*{len(pr_data_processor.without_jira)} of {len(pr_data_processor.with_jira) + len(pr_data_processor.without_jira)} PRs not tracked in Jira* 🟠\n"
    message += f"{pr_message}"
    return message


def lambda_handler(event, context):
    logger.debug(f"start processing {event}")

    message = _process(event)
    response_url = event.get("response_url")
    # updating doesn't work with response_url
    # original_message = event.get("original_message")

    logger.debug(f"responding to: {response_url}")

    response = {"text": message}
    r = requests.post(response_url, json=response)
    r.raise_for_status()

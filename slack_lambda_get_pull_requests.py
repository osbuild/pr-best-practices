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
    jira_user = event.get("jira_user", "unknown")
    args = event.get("args", "unknown")

    github_organization = event.get("github_organization", "unknown")
    github_token = event.get("github_token", "unknown")

    jira_token = event.get("jira_token", "unknown")
    jira_board_id = event.get("jira_board_id", "unknown")

    current_sprint_url = event.get("jira_current_sprint_url")
    backlog_url = event.get("jira_backlog_url")

    # the functionality is duplicated here (alos in slack_lambda.py)
    # for the testcases
    arg_array = args.split(" ")
    if len(arg_array) == 2:
        args = arg_array[0]
        jira_user = arg_array[1]
    elif len(arg_array) > 2:
        return ":stop: There are too many arguments. Please use the format: `/pr2jira [<github_user>|<github_user> <jira_user>]`"

    pr_data_processor = DataProcessor(github_organization, None, args, github_token)
    pr_data_processor.process()

    jira_data_processor = JiraDataProcessor(jira_token, f"{jira_user}", jira_board_id)
    processed_issues = jira_data_processor.get_issue_overview()

    if current_sprint_url:
        current_sprint_url = f"<{current_sprint_url}|current sprint>"
    else:
        current_sprint_url = "current sprint"

    if backlog_url:
        backlog_url = f"<{backlog_url}|backlog>"
    else:
        backlog_url = "backlog"

    best_practice_issues = []
    # copy current_sprint issues to normal_sprint_issues_items
    # to be transformed into strings later
    normal_sprint_issue_items = processed_issues["current_sprint"].copy()
    linked_backlog = []
    linked_non_backlog = []
    for pr in sorted(pr_data_processor.with_jira, key=lambda x: (x["repo"], x["number"])):
        matched = False
        pr_title_link = f"<{pr['html_url']}|{pr['title']}>"
        pr_info = f" • {pr_title_link}"
        for sprint_issue in processed_issues["current_sprint"]:
            if pr["jira_key"] == sprint_issue["key"]:
                jira_link = f"<{sprint_issue['url']}|{sprint_issue['key']}>"
                best_practice_issues.append(f"{pr_info}\n    {jira_link} - {sprint_issue['summary']}")
                normal_sprint_issue_items.remove(sprint_issue)
                matched = True
                break
        if matched:
            continue

        for backlog_issue in processed_issues["backlog"]:
            if pr["jira_key"] == backlog_issue["key"]:
                jira_link = f"<{backlog_issue['url']}|{backlog_issue['key']}>"
                linked_backlog.append(f"{pr_info}\n    {jira_link} - {backlog_issue['summary']}")
                matched = True
                break
        if matched:
            continue

        if pr["jira_url"]:
            jira_link = f"<{pr['jira_url']}|{pr['jira_key']}>"
        else:
            # should not happen, but just in case
            jira_link = f"{pr['jira_key']}"
        linked_non_backlog.append(f"{pr_info} ({jira_link})")

    normal_sprint_issues = []
    for sprint_issue in sorted(normal_sprint_issue_items, key=lambda x: (x["key"])):
        normal_sprint_issues.append(f" • <{sprint_issue['url']}|{sprint_issue['key']}>: {sprint_issue['summary']}")

    message = f"Happy {datetime.now().strftime('%A')}! 👋\n\n"

    message += f"*Work from your {current_sprint_url}* 🟢\n"

    if best_practice_issues:
        message += "    Best practice:\n"
        message += "\n".join(best_practice_issues)
        message += "\n\n"
    if normal_sprint_issues:
        message += "    No implementation linked yet:\n"
        message += "\n".join(normal_sprint_issues)
        message += "\n\n"
    if not best_practice_issues and not normal_sprint_issues:
        message += "    :hanging-sloth: You don't have any issues in the current sprint\n\n"

    if linked_backlog or linked_non_backlog:
        message += "*Other work* 🟡\n"
        if linked_backlog:
            message += f"    Already started implementation from {backlog_url}:\n"
            message += "\n".join(linked_backlog)
            message += "\n\n"
        if linked_non_backlog:
            message += f"    Implementation started but not in our {backlog_url}:\n"
            message += "\n".join(linked_non_backlog)
            message += "\n\n"

        # remaining "backlog non linked" issues are not printed
        # those are just all others
    # else section "other work" is skipped


    message += f"*{len(pr_data_processor.without_jira)} of {len(pr_data_processor.with_jira) + len(pr_data_processor.without_jira)} PRs not tracked in Jira* 🟠\n"
    # Format the message for PRs without Jira keys
    if pr_data_processor.without_jira:
        pr_list = []
        for pr in sorted(pr_data_processor.without_jira, key=lambda x: x["repo"]):
            pr_title_link = f"<{pr['html_url']}|{pr['title']}>"
            entry = f" • {pr['repo']}: {pr_title_link} "
            pr_list.append(entry)
        pr_message = "\n".join(pr_list)
        # indenting does not work in slack, so we'll use some spaces for now
        pr_message += "\n\n    :cat_typing: Please add a Jira key to your PR title e.g by using `/jira-epic …` described <https://github.com/osbuild/pr-best-practices?tab=readme-ov-file#features|here>."
    else:
        if len(pr_data_processor.with_jira) == 0:
            pr_message = f"    *{jira_user}* is not working on any PRs at the moment? :confusedoggo:"
        else:
            pr_message = "    :party-blob: All your PRs are best practice."

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

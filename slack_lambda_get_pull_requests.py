from datetime import datetime
import os
import requests

from get_jira_sprint import JiraDataProcessor
from get_pull_requests import DataProcessor
import logging

# Set the logging level to DEBUG for more verbose output
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def get_github_url(issue, pr_data_processor):
    for pr in pr_data_processor.with_jira:
        if issue["key"] == pr["jira_key"]:
            return pr["html_url"]
    return None

def get_github_number(issue, pr_data_processor):
    for pr in pr_data_processor.with_jira:
        if issue["key"] == pr["jira_key"]:
            return f"{pr["repo"]}#{pr["number"]}"
    return None

def is_practice_issue(issue, pr_data_processor):
    return get_github_url(issue, pr_data_processor) is not None

def is_backlog_issue(pr, processed_issues):
    for issue in processed_issues["backlog"]:
        if pr["jira_key"] == issue["key"]:
            return True
    return False

def is_sprint_issue(pr, processed_issues):
    for issue in processed_issues["current_sprint"]:
        if pr["jira_key"] == issue["key"]:
            return True
    return False


def get_issue_summary(jira_data_processor, pr, processed_issues):
    for issue in processed_issues["backlog"] + processed_issues["current_sprint"]:
        if pr["jira_key"] == issue["key"]:
            return issue["summary"]
    try:
        return jira_data_processor.get_issue(pr["jira_key"])["summary"]
    except:
        pass

    return pr["title"]


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

    message = f"Happy {datetime.now().strftime('%A')}! 👋\n\n"

    message += f"*Work from your {current_sprint_url}* 🟢\n"

    current_column = None
    for sprint_issue in sorted(
        processed_issues["current_sprint"],
        key=lambda x: (x["sprint_column"]["sort_id"], is_practice_issue(x, pr_data_processor), x["key"])):

        if current_column != sprint_issue["sprint_column"]["name"]:
            current_column = sprint_issue["sprint_column"]["name"]
            if current_column == "In Progress":
                message += f"\n  :progress: *{current_column}*\n"
            elif current_column == "To Do":
                message += f"\n  :todo-circle: *{current_column}*\n"
            elif current_column == "Done":
                message += f"\n  :check-done: *{current_column}*\n"
            else:
                message += f"\n  *{current_column}*\n"

        jira_link = f"<{sprint_issue['url']}|:jira-6472: {sprint_issue['key']}>"
        github_url = get_github_url(sprint_issue, pr_data_processor)

        if github_url:
            github_link = f", <{github_url}|:github: {get_github_number(sprint_issue, pr_data_processor)}>"
        else:
            if current_column == "In Progress":
                github_link = ", ⚠️ no PR linked"
            else:
                github_link = ""
        message += f"     • {sprint_issue['summary']} {jira_link}{github_link}\n"

    if not current_column:
        message += "    :hanging-sloth: You don't have any issues in the current sprint\n\n"
    else:
        message += "\n"

    section = None
    for pr in sorted(pr_data_processor.with_jira
                                , key=lambda x: is_backlog_issue(x, processed_issues)):
        if is_sprint_issue(pr, processed_issues):
            continue

        if section is None:
            message += "*Other work* 🟡\n"

        backlog_section = is_backlog_issue(pr, processed_issues)
        if section != backlog_section:
            section = backlog_section
            # skip sub-heading for simplicity for now
            #if section:
            #    message += f"    From our {backlog_url} (not in the current sprint)\n"
            #else:
            #    message += f"    Not related to our {backlog_url}\n"

        jira_link = f"<{pr['jira_url']}|:jira-6472: {pr['jira_key']}>"
        github_url = pr['html_url']
        github_link = ""
        if github_url:
            github_link = f", <{github_url}|:github: {pr['repo']}#{pr['number']}>"
        summary = get_issue_summary(jira_data_processor, pr, processed_issues)
        message += f" • {summary} {jira_link}{github_link}\n"

    if section is not None:
        message += "\n"

    message += f"*PRs not tracked in Jira* 🟠\n"
    # Format the message for PRs without Jira keys
    if pr_data_processor.without_jira:
        pr_list = []
        for pr in sorted(pr_data_processor.without_jira, key=lambda x: x["repo"]):
            entry = f" • {pr['title']} <{pr['html_url']}|:github: {pr['repo']}#{pr['number']}>"
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

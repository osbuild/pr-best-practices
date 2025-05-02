from datetime import datetime
import requests

from get_pull_requests import DataProcessor
import logging

# Set the logging level to DEBUG for more verbose output
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def _process(event):
    user = event.get("user", "unknown")
    organization = event.get("organization", "unknown")
    github_token = event.get("github_token", "unknown")

    data_processor = DataProcessor(organization, None, user, True, github_token)
    data_processor.process()

    # Format the message for PRs without Jira keys
    if data_processor.without_jira:
        pr_list = []
        for pr in data_processor.without_jira:
            pr_title_link = f"<{pr['html_url']}|{pr['title']}>"
            entry = (
                f" • {pr['repo']}: {pr_title_link} "
                f"(+{pr['additions']}/-{pr['deletions']})"
            )
            pr_list.append(entry)
        pr_message = "\n".join(pr_list)
        pr_message += "\n\n:cat_typing: Please add a Jira key to your PR title as described <https://addlinkhere.com|here>."
    else:
        if len(data_processor.with_jira) == 0:
            pr_message = f"{user} is not working on any PRs at the moment? :confusedoggo:"
        else:
            pr_message = ":party-blob: All your PRs are best practice."


    message = f"Happy {datetime.now().strftime('%A')}! 👋\n\n"

    message += f"*Work from {user}'s current sprint* 🟢\n"
    message += " • _TBD_\n\n"

    message += "*Other work* 🟡\n"
    message += " • _TBD_\n\n"

    message += f"*And {len(data_processor.without_jira)} of {len(data_processor.with_jira) + len(data_processor.without_jira)} PRs not tracked in Jira* 🟠\n"
    message += f"{pr_message}"
    return message


def lambda_handler(event, context):
    logger.debug(f"start processing {event}")

    message = _process(event)
    logger.debug(f"message: {message}")
    response_url = event.get("response_url")
    # updating doesn't work with response_url
    # original_message = event.get("original_message")

    logger.debug(f"responding to: {response_url}")

    response = {"text": message}
    r = requests.post(response_url, json=response)
    r.raise_for_status()

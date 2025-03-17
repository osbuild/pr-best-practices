#!/usr/bin/python3

"""
Small script to return all pull requests for a given organisation, repository and assignee
"""

import argparse
import os
import re
import requests
import time
import pickle
import sys

from ghapi.all import GhApi
from fastcore.foundation import L

from utils import format_help_as_md

if os.getenv("PR_BEST_PRACTICES_TEST_CACHE"):
    import requests_cache
    # NOTE: this will cache forever, until you remove the `test_cache.sqlite`
    requests_cache.install_cache(
        'test_cache',
        backend='sqlite',
        expire_after=None,
    )
    cache_all = True
    GH_cache_file = "test_cache.pkl"
    if os.path.exists(GH_cache_file):
        with open(GH_cache_file, "rb") as f:
            GH_cache = pickle.load(f)
    else:
        GH_cache = {}
else:
    cache_all = False

def get_archived_repos(github_api, org):
    """
    Return a list of archived or disabled repositories
    """
    res = None

    try:
        res = github_api.repos.list_for_org(org)
    except:  # pylint: disable=bare-except
        print(f"Couldn't get repositories for organisation {org}.")

    archived_repos = []

    if res is not None:
        for repo in res:
            if repo["archived"] is True or repo["disabled"] is True:
                archived_repos.append(repo["name"])

    if archived_repos:
        archived_repos_string = ", ".join(archived_repos)
        print(f"The following repositories are archived or disabled and will be ignored:\n  {archived_repos_string}")

    return archived_repos

def get_pull_request_details(github_api, repo, pull_request):
    """
    Return a pull_request_details object
    """

    pull_request_details = None
    for attempt in range(3):
        try:
            pull_request_details = github_api.pulls.get(repo=repo, pull_number=pull_request["number"])
        except:  # pylint: disable=bare-except
            time.sleep(2)  # avoid API blocking
        else:
            break
    else:
        print(f"Tried {attempt} times to get details for {pull_request.html_url}. Skipping.")

    if pull_request_details is not None:
        return pull_request_details

    print("Couldn't get any pull requests details.")
    sys.exit(1)

def get_pull_request_properties(github_api, pull_request, org, repo):
    """
    Return a dictionary of all relevant pull request properties
    """
    pr_properties = {}

    pull_request_details = get_pull_request_details(github_api, repo, pull_request)

    pr_properties["number"] = pull_request["number"]
    pr_properties["html_url"] = pull_request.html_url
    pr_properties["title"] = pull_request.title
    pr_properties["org"] = org
    pr_properties["repo"] = repo
    pr_properties["created_at"] = pull_request.created_at
    pr_properties["updated_at"] = pull_request.updated_at
    #pr_properties["last_updated_days"] = get_last_updated_days(pull_request.updated_at)
    #pr_properties["login"] = get_slack_userid(pull_request.user['login'])
    pr_properties["requested_reviewers"] = pull_request_details["requested_reviewers"]
    pr_properties["additions"] = pull_request_details["additions"]
    pr_properties["deletions"] = pull_request_details["deletions"]
    pr_properties["draft"] = pull_request_details["draft"]
    pr_properties["mergeable"] = pull_request_details["mergeable"]
    pr_properties["rebaseable"] = pull_request_details["rebaseable"]
    pr_properties["mergeable_state"] = pull_request_details["mergeable_state"]
    #pr_properties["changes_requested"] = get_review_state(github_api, repo, pull_request, "CHANGES_REQUESTED")
    #pr_properties["approved"] = get_review_state(github_api, repo, pull_request, "APPROVED")
    #pr_properties["status"], pr_properties["state"] = get_commit_status(github_api, repo, pull_request_details)#

    return pr_properties


def get_pull_request_list(github_api, org, repo, author):
    """
    Return a list of pull requests with their properties
    """
    pull_request_list = []
    res = None
    archived_repos = []

    if author:
        author_query = f"author:{author}"

    if repo:
        print(f"Fetching pull requests from one repository: {org}/{repo}")
        query = f"repo:{org}/{repo} type:pr is:open {author_query}"
        entire_org = False
    else:
        print(f"Fetching pull requests from an entire organisation: {org}")
        query = f"org:{org} type:pr is:open {author_query}"
        entire_org = True
        archived_repos = get_archived_repos(github_api, org)

    print(f"Query: {query}")

    try:
        res = github_api.search.issues_and_pull_requests(q=query, per_page=100, sort="updated", order="asc")
    except Exception as e:  # pylint: disable=broad-exception-caught
        print("Couldn't get any pull requests.", e)

    if res is not None:
        pull_requests = res["items"]
        print(f"{len(pull_requests)} pull requests retrieved.")

        for pull_request in pull_requests:
            if entire_org:  # necessary when iterating over an organisation
                repo = pull_request.repository_url.split('/')[-1]
                if archived_repos and repo in archived_repos:
                    print(f" * Repository '{org}/{repo}' is archived or disabled. Skipping.")
                    continue

            pull_request_props = get_pull_request_properties(github_api, pull_request, org, repo)
            print(f" * Processing {pull_request.html_url} ...")
            pull_request_list.append(pull_request_props)

    return pull_request_list


def generate_jira_link(jira_key):
    """
    Generate a Jira link and verify that it exists
    """
    jira_url = f"https://issues.redhat.com/browse/{jira_key}"
    response = requests.head(jira_url, timeout=3)
    return f"<{jira_url}|:jira-1992:{jira_key}>" if response.status_code == 200 else jira_key


def find_jira_key(pr_title, pr_html_url):
    """
    Look for a Jira key, when found generate a hyperlink and return the new pr_title_link
    """
    pr_title_link = f"<{pr_title}|{pr_html_url}>"

    match = re.match(r"([A-Z]+\-\d+)([: -]+)(.+)", pr_title)
    if match:
        jira_key, separator, title_remainder = match.groups()
        if jira_key:
            pr_title_link = f"{generate_jira_link(jira_key)}{separator}<{title_remainder}|{pr_html_url}>"

    return pr_title_link

def cache_test_result(cache_key, function, **kwargs):
    """
    Cache the result of a function call.
    """
    if cache_all:
        result = GH_cache.get(cache_key)
    else:
        result = None
    if result is None:
        result = function(**kwargs)
        if cache_all:
            GH_cache[cache_key] = result
            # better save now, so it's not lost if the script crashes
            with open(GH_cache_file, "wb") as f:
                pickle.dump(GH_cache, f)

    return result

def main():
    """Return a list of pull requests for a given organisation, repository and assignee"""
    parser = argparse.ArgumentParser(allow_abbrev=False,
        description=__doc__,
        epilog="""You can set the `GITHUB_TOKEN` environment variable instead of using the `--github-token` argument.
        You can also set the `PR_BEST_PRACTICES_TEST_CACHE` environment variable to anything (e.g. `1`) use the test cache.
        """
    )

    # GhApi() supports pulling the token out of the env - so if it's
    # set - we don't need to force this in the params
    if os.getenv("GITHUB_TOKEN"):
        token_arg_required = False
    else:
        token_arg_required = True

    parser.add_argument("--github-token", help="Set a token for github.com", required=token_arg_required)
    parser.add_argument("--org", help="Set an organisation on github.com", required=True)
    parser.add_argument("--repo", help="Set a repo in `--org` on github.com", required=False)
    parser.add_argument("--author", help="Author of pull requests", required=False)
    parser.add_argument("--dry-run", help="Don't send Slack notifications", default=False,
                        action=argparse.BooleanOptionalAction)
    parser.add_argument("--help-md", help="Show help as Markdown", action="store_true")

    # workaround that required attribute are not given for --help-md
    if "--help-md" in sys.argv:
        print(format_help_as_md(parser))
        sys.exit(0)

    args = parser.parse_args()
    # pylint: disable=global-statement

    github_api = GhApi(owner=args.org, token=args.github_token)

    print(f"Fetching pull requests for {args.org}/{args.repo} assigned to {args.author}")

    pull_request_list = cache_test_result(
        "get_pull_request_list",
        get_pull_request_list,
        github_api=github_api,
        org=args.org,
        repo=args.repo,
        author=args.author
    )

    jira_pattern = re.compile(r"\b[A-Z]+-\d+\b")
    with_jira = [item for item in pull_request_list if jira_pattern.search(item['title'])]
    without_jira = [item for item in pull_request_list if not jira_pattern.search(item['title'])]

    print("# Pull requests with Jira keys:")
    for pull_request in with_jira:
        pr_title_link = find_jira_key(pull_request['title'], pull_request['html_url'])
        entry = (
            f"*{pull_request['repo']}*: {pr_title_link}"
            f" (+{pull_request['additions']}/-{pull_request['deletions']})"
        )
        print(entry)
    
    print("# Pull requests without Jira keys:")
    for pull_request in without_jira:
        pr_title_link = find_jira_key(pull_request['title'], pull_request['html_url'])
        entry = (
            f"*{pull_request['repo']}*: {pr_title_link}"
            f" (+{pull_request['additions']}/-{pull_request['deletions']})"
        )
        print(entry)

if __name__ == "__main__":
    main()

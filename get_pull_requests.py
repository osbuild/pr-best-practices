#!/usr/bin/python3

"""
Small script to return all pull requests for a given organisation, repository and assignee

Saves a `data_collection.json` to be used with `ai_reasoning.py` for further analysis.
"""

import argparse
import os
import re
import requests
import time
import pickle
import sys
import json
from jira import JIRA, JIRAError

from ghapi.all import GhApi
from fastcore.foundation import L

from utils import format_help_as_md, Cache

doc_epilog = """You can set the `GITHUB_TOKEN` environment variable instead of using the `--github-token` argument.
You can also set the `PR_BEST_PRACTICES_TEST_CACHE` environment variable to anything (e.g. `1`) use the cache.
"""

JIRA_HOST = os.getenv("JIRA_HOST", "https://issues.redhat.com")
JIRA_TOKEN = os.getenv("JIRA_TOKEN")

doc_epilog += "The retrieval of issues starts with `JIRA_TOPLEVEL_FILTER_ID`."
# current quarter only
# JIRA_TOPLEVEL_FILTER_ID = 12444600
# whole portfolio plan
JIRA_TOPLEVEL_FILTER_ID = 12429182

# suggest those in case the other's don't really match
FALLBACK_ISSUES = os.getenv("FALLBACK_ISSUES", "COMPOSER-2246").split(',')

_child_issues_of_snippet = "\"), childIssuesOf(\"".join(FALLBACK_ISSUES)

_CHILD_ISSUE_JQL = "" if len(FALLBACK_ISSUES) == 0 else f"OR issue in (childIssuesOf(\"{_child_issues_of_snippet}\"))"

# double curly braces for the `.format()` later!
JIRA_CHILD_EPICS_JQL = f"issue in childIssuesOf(\"{{jira_key}}\") {_CHILD_ISSUE_JQL} AND type = Epic AND status != Closed"

JIRA_RE_KEY = r"[A-Z]+\-\d+"

# following two are redundant, just as a consistency check
JIRA_PARENT_LINK_FIELD_NAME = "Parent Link"
JIRA_PARENT_LINK_FIELD = "customfield_12313140"

JIRA_EPIC_LINK_FIELD_NAME = "Epic Link"
JIRA_EPIC_LINK_FIELD = "customfield_12311140"

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
    
    commits = []
    for attempt in range(3):
        try:
            commits = github_api.pulls.list_commits(repo=repo, pull_number=pull_request["number"])
        except:  # pylint: disable=bare-except
            time.sleep(2)  # avoid API blocking
        else:
            break
    else:
        print(f"Tried {attempt} times to get commits for {pull_request.html_url}. Skipping.")

    if pull_request_details is not None:
        # without the general details, it would not make sense to return the commit messages
        pull_request_details["commit_messages"] = [c.commit.message for c in commits]
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
    pr_properties["description"] = pull_request.body
    pr_properties["commit_messages"] = pull_request_details["commit_messages"]

    # TBD: when the PR contains a Jira key or other PR reference
    # this additional info should be fetched and fed to pr_properties/AI too.

    return pr_properties


def get_pull_request_list(github_api, org, repo, author):
    """
    Return a list of pull requests with their properties
    """
    pull_request_list = []
    res = None
    archived_repos = []

    if author:
        author_query = f" author:{author}"
    else:
        author_query = ""

    if repo:
        print(f"Fetching pull requests from one repository: {org}/{repo}")
        query = f"repo:{org}/{repo} type:pr is:open{author_query}"
        entire_org = False
    else:
        print(f"Fetching pull requests from an entire organisation: {org}")
        query = f"org:{org} type:pr is:open{author_query}"
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
    jira_url = f"{JIRA_HOST}/browse/{jira_key}"
    response = requests.head(jira_url, timeout=3)
    return f"<{jira_url}|:jira-1992:{jira_key}>" if response.status_code == 200 else jira_key


def find_all_jira_keys(text):
    match = re.findall(rf"(?:\W|^)({JIRA_RE_KEY})(?:\W|$)", text)
    return match

def find_jira_key(pr_title, pr_html_url):
    """
    Look for a Jira key, when found generate a hyperlink and return the new pr_title_link
    """
    pr_title_link = f"<{pr_title}|{pr_html_url}>"

    match = re.match(rf"({JIRA_RE_KEY})([: -]+)(.+)", pr_title)
    if match:
        jira_key, separator, title_remainder = match.groups()
        if jira_key:
            pr_title_link = f"{generate_jira_link(jira_key)}{separator}<{title_remainder}|{pr_html_url}>"

    return pr_title_link


def get_parent(issue):
    """Get the "parent" of the given issue.
    That's either via parent link or epic link.
    Just nesting the calls does not work if the field is _set_ to `None`
    """
    ret = getattr(issue.fields, JIRA_PARENT_LINK_FIELD, None)
    if ret is None:
        ret = getattr(issue.fields, JIRA_EPIC_LINK_FIELD, None)
    return ret


def main():
    """Return a list of pull requests for a given organisation, repository and assignee"""
    global cache
    parser = argparse.ArgumentParser(allow_abbrev=False,
        description=__doc__,
        epilog=doc_epilog
    )

    # GhApi() supports pulling the token out of the env - so if it's
    # set - we don't need to force this in the params
    if os.getenv("GITHUB_TOKEN"):
        token_arg_required = False
    else:
        token_arg_required = True

    parser.add_argument("--github-token", help="Set a token for github.com", required=token_arg_required)
    parser.add_argument("--jira-host", help="The jira hostname to use", required=(JIRA_HOST is None))
    parser.add_argument("--jira-token", help="Set the API token for jira", required=(JIRA_TOKEN is None))
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

    if os.getenv("PR_BEST_PRACTICES_TEST_CACHE"):
        print("Loading cache…")
        import requests_cache
        # NOTE: this will cache forever, until you remove the `test_cache.sqlite`
        requests_cache.install_cache(
            'test_cache',
            backend='sqlite',
            expire_after=None,
        )
        cache = Cache("test_cache.pkl")
    else:
        cache = Cache(None) # indicates not to use cache

    print(f"Fetching pull requests for {args.org}/{args.repo} assigned to {args.author}")

    pull_request_list = cache.cached_result(
        f"get_pull_request_list_{args.org}_{args.repo}_{args.author}",
        get_pull_request_list,
        github_api=github_api,
        org=args.org,
        repo=args.repo,
        author=args.author
    )

    jira_pattern = re.compile(r"\b[A-Z]+-\d+\b")
    with_jira = [item for item in pull_request_list if jira_pattern.search(item['title'])]
    without_jira = [item for item in pull_request_list if not jira_pattern.search(item['title'])]

    print("Fetching Jira issues")
    jira = JIRA(JIRA_HOST, token_auth=JIRA_TOKEN)
    jql = f'filter = {JIRA_TOPLEVEL_FILTER_ID}'
    issues = cache.cached_result("jira_search_issues_{jql}", jira.search_issues, jql_str=jql)

    fields = cache.cached_result("jira_fields", jira.fields)
    fieldmap = {f['id']: f['name'] for f in fields}
    if JIRA_PARENT_LINK_FIELD not in fieldmap or fieldmap[JIRA_PARENT_LINK_FIELD] != JIRA_PARENT_LINK_FIELD_NAME:
        print(f"ERROR: Field {JIRA_PARENT_LINK_FIELD} is not {JIRA_PARENT_LINK_FIELD_NAME}.")
        print(f"Jira changed somehow, please update the script.")
        sys.exit(1)

    if JIRA_EPIC_LINK_FIELD not in fieldmap or fieldmap[JIRA_EPIC_LINK_FIELD] != JIRA_EPIC_LINK_FIELD_NAME:
        print(f"ERROR: Field {JIRA_EPIC_LINK_FIELD} is not {JIRA_EPIC_LINK_FIELD_NAME}.")
        print(f"Jira changed somehow, please update the script.")
        print(json.dumps(fieldmap, indent=2))
        sys.exit(1)

    child_issues = {}
    cnt = 0
    for i in issues:
        cnt += 1
        print(f"Fetching children {cnt}/{len(issues)}: {i.key}…")
        child_issues[i.key] = cache.cached_result(f"jira_epic_children_{i.key}", jira.search_issues, jql_str=JIRA_CHILD_EPICS_JQL.format(jira_key=i.key))
    # print unique, sorted epics
    unique_sorted_epics = sorted(set([e for res in child_issues.values() for e in res]), key=lambda x: x.key)

    # initialize related with already fetched, to avoid fetching duplicates
    related_issues = { i.key: i for i in issues } | { i.key: i for i in unique_sorted_epics }

    print("Search PR titles and description for jira references")
    # skip though the PR title and description
    # and add the content of referenced jira issues
    # NOTE: related_issues now also contain keys with the PR-url
    # which are issues mentioned in the PR
    for item in pull_request_list:
        pr_key = item['html_url']
        print(f"Searching in: {pr_key}")
        ref_nr = 0

        jira_keys = find_all_jira_keys(item['title'])
        for k in jira_keys:
            try:
                unique_sorted_epics.append(cache.cached_result(f"jira_issue_{k}", jira.issue, id=k))
                ref_nr += 1
            except JIRAError as e:
                # skip issues without permissions
                if e.status_code in [403, 404]:
                    print(f"Skip getting JIRA issue {k}: {e.text}")
                    continue
                raise e
        if item['description']:
            jira_keys = find_all_jira_keys(item['description'])
            for k in jira_keys:
                try:
                    unique_sorted_epics.append(cache.cached_result(f"jira_issue_{k}", jira.issue, id=k))
                    ref_nr += 1
                except JIRAError as e:
                    # skip issues without permissions
                    if e.status_code in [403, 404]:
                        print(f"Skip getting JIRA issue {k}: {e.text}")
                        continue
                    raise e
    # drop duplicates again
    unique_sorted_epics = sorted(set([e for e in unique_sorted_epics]), key=lambda x: x.key)

    print(f"All open Epics: {len(unique_sorted_epics)}")
    for i in unique_sorted_epics:
        print(f"  {i.key}: {i.fields.summary}")
        print(f"  {' ' * len(i.key)}  {JIRA_HOST}/browse/{i.key}")
        print(f"  {' ' * len(i.key)}  Parent: {get_parent(i)}")
        parent = getattr(i.fields, JIRA_PARENT_LINK_FIELD, None)
        if parent and parent not in related_issues.keys():
            try:
                related_issues[parent] = cache.cached_result(f"jira_issue_{parent}", jira.issue, id=parent)
            except JIRAError as e:
                # skip issues without permissions
                if e.status_code in [403, 404]:
                    print(f"Skip getting JIRA issue {parent}: {e.text}")
                    continue
                raise e
        epic = getattr(i.fields, JIRA_EPIC_LINK_FIELD, None)
        if epic and epic not in related_issues.keys():
            try:
                related_issues[epic] = cache.cached_result(f"jira_issue_{epic}", jira.issue, id=epic)
            except JIRAError as e:
                # skip issues without permissions
                if e.status_code in [403, 404]:
                    print(f"Skip getting JIRA issue {epic}: {e.text}")
                    continue
                raise e

    # get all the parents for more context
    print("Fetching related issues…")
    get_more = True
    while get_more:
        get_more = False
        print(f"{len(related_issues)}", end="\r", flush=True)
        for i in list(related_issues.values()): # doing list to make a copy
            parent = getattr(i.fields, JIRA_PARENT_LINK_FIELD, None)
            if parent and parent not in related_issues.keys():
                try:
                    related_issues[parent] = cache.cached_result(f"jira_issue_{parent}", jira.issue, id=parent)
                    get_more = True
                except JIRAError as e:
                    # skip issues without permissions
                    if e.status_code in [403, 404]:
                        print(f"Skip getting JIRA issue {parent}: {e.text}")
                        continue
                    raise e
    print("Done.")

    data_collection = {
        "pull_requests": [
            { 'url': item['html_url'],
              'title': item['title'],
              'description': item['description'],
              'commit_messages': item['commit_messages']
            }  for item in pull_request_list if not jira_pattern.search(item['title'])
        ],
        "jira_issues": [
            { 'key': i.key,
              'summary': i.fields.summary,
              'assignee': i.fields.assignee.displayName if i.fields.assignee else "None",
              'description': i.fields.description,
              'comments': [ {'author': c.author.displayName, 'body': c.body} for c in i.fields.comment.comments ],
              'parent': get_parent(i)
            } for i in unique_sorted_epics
        ],
        "related_issues": {
            k: { 'key': k, # "duplicate" the key for easier access
                 'summary': v.fields.summary,
                 'assignee': v.fields.assignee.displayName if v.fields.assignee else "None",
                 'description': v.fields.description,
                 'comments': [ {'author': c.author.displayName, 'body': c.body} for c in v.fields.comment.comments ],
                 'parent': get_parent(v)
            } for k, v in related_issues.items()
        },
        "fallback_issues": FALLBACK_ISSUES
    }

    # for reference/testing - data with already linked PRs
    data_collection_jira = {
        "pull_requests": [
            { 'url': item['html_url'],
              'title': item['title'],
              'description': item['description'],
              'commit_messages': item['commit_messages']
            }  for item in pull_request_list if jira_pattern.search(item['title'])
        ],
        "jira_issues": [
            { 'key': i.key,
              'summary': i.fields.summary,
              'assignee': i.fields.assignee.displayName if i.fields.assignee else "None",
              'description': i.fields.description,
              'comments': [ {'author': c.author.displayName, 'body': c.body} for c in i.fields.comment.comments ],
              'parent': get_parent(i)
            } for i in unique_sorted_epics
        ],
        "related_issues": {
            k: { 'key': k, # "duplicate" the key for easier access
                 'summary': v.fields.summary,
                 'assignee': v.fields.assignee.displayName if v.fields.assignee else "None",
                 'description': v.fields.description,
                 'comments': [ {'author': c.author.displayName, 'body': c.body} for c in v.fields.comment.comments ],
                 'parent': get_parent(v)
            } for k, v in related_issues.items()
        },
        "fallback_issues": FALLBACK_ISSUES
    }

    with open("data_collection.json", "w") as f:
        f.write(json.dumps(data_collection))
    with open("data_collection_already_linked.json", "w") as f:
        f.write(json.dumps(data_collection_jira))

    print(f"# Pull requests with Jira keys: {len(with_jira)}")
    for pull_request in with_jira:
        pr_title_link = find_jira_key(pull_request['title'], pull_request['html_url'])
        entry = (
            f"*{pull_request['repo']}*: {pr_title_link}"
            f" (+{pull_request['additions']}/-{pull_request['deletions']})"
        )
        print(entry)
    
    print()
    print(f"# Pull requests without Jira keys: {len(without_jira)}")
    for pull_request in without_jira:
        pr_title_link = find_jira_key(pull_request['title'], pull_request['html_url'])
        entry = (
            f"*{pull_request['repo']}*: {pr_title_link}"
            f" (+{pull_request['additions']}/-{pull_request['deletions']})"
        )
        print(entry)

    print(f"Stats:")
    print(f"PRs with jira key: {len(with_jira)}")
    print(f"PRs without jira key: {len(without_jira)}")
    print(f"Open Epics: {len(unique_sorted_epics)}")
    print(f"Related Issues: {len(related_issues)}")

if __name__ == "__main__":
    main()

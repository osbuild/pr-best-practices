#!/usr/bin/python3
"""
This script uses AI to summarize the Epics (with the context of their issue-parents)
then uses sentence transformers (RAG) to find the most similar issues to the list of PRs.
Finally uses AI to figure out which of the issues match the PR the most.

It expects `get_pull_requests.py` to be run before and generate `data_collection.json`.
"""

import argparse
import requests
import json
import numpy as np
import os
import sys

from sklearn.metrics.pairwise import cosine_similarity
from utils import Cache, format_help_as_md

doc_epilog = ""

doc_epilog += """You can override the URL to Jira by setting the environment
variable `JIRA_HOST`.
"""
JIRA_HOST = os.getenv("JIRA_HOST", "https://issues.redhat.com")

# auto tokenizer should match the `OLLAMA_MODEL` but
# only needed for "debugging"
AUTO_TOKENIZER_MODEL = "deepseek-ai/DeepSeek-R1"

# Ollama API Endpoint
doc_epilog += """If you have ollama running on another host (with a decent GPU), you might want to set
the environment variable `OLLAMA_HOST` to something like `http://other_host:11434`.  
"""
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_GENERATE = os.getenv("OLLAMA_API_ENDPOINT", f"{OLLAMA_HOST}/api/generate")
OLLAMA_API_MODELS = os.getenv("OLLAMA_API_MODELS", f"{OLLAMA_HOST}/api/tags")

doc_epilog += """Also, you might want to set the environment variable `OLLAMA_MODEL` to something you have
downloaded in ollama.  
"""
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "deepseek-r1:7b")
# OLLAMA_MODEL ="granite3-dense:2b"
# OLLAMA_MODEL ="granite3.2:8b"
# OLLAMA_MODEL = "deepseek-r1:14b"
# OLLAMA_MODEL = "mistral:7b-instruct"

doc_epilog += "The environment variable `AI_REASONING_DEBUG` can be used to enable debug/verbose output.  \n"
DEBUG = bool(os.getenv("AI_REASONING_DEBUG", False))

SCENTENCE_TRANSFORMER_MODEL = "all-MiniLM-L6-v2"
doc_epilog += f"The transformer model for RAG is hardcoded in the script to `{SCENTENCE_TRANSFORMER_MODEL}`"

PROMPT_MAP_PR ="""You are an expert at mapping a GitHub pull request to Jira issues based on their descriptions, title and summary.

Pull Request:
URL: "{pr_url}"
Title: "{pr_title}"
Description: "{pr_description}"

Retrieved Jira Issues:
{relevant_issues}

If the pull request description clearly relates to any of these Jira issues, list the matching Jira issue KEYs.
You should prefer the "Retrieved Jira Issues"
If in doubt you can also match from those:
{fallback_issues}

Return your answer as a JSON object with the pull request URL as key and its value as either:
- a list of matching Jira issue KEYs, or
- the string "No good match found for this pull request."
- never return a Jira issue KEY that was not retrieved.
- never return both "No good match found for this pull request." and a list of Jira issue KEYs.

The output format should look like this:
{{ "{pr_url}": ["JIRA-123", "JIRA-456"] }}
"""

PROMPT_NEW_SUMMARY ="""You are an expert at creating a summary for a Jira issue based on its title, summary and description
as well as all its parents.

You focus on making the description brief but enrich the description with aspects of all parents, not loosing any detail.
Focus on aspects of the context that the parent issues describe, which are relevant for a technical implementation.

The input data:
{input}

Dont use formatting, just focus on the content.
"""

PROMPT_NEW_DEV_SUMMARY ="""You are an expert in creating instructions for a software developer based on the title, summary and description of a Jira issue.
The parent issues represent the context of the issue and are relevant for the implementation.
You also take into account the parent issues to create good instructions with the context of the issue.

You focus on making the description brief but enrich the description with aspects of all parents, not loosing any detail.
Focus on aspects of the context that the parent issues describe, which are relevant for the implementation.

The input data:
{input}

Dont use formatting, just focus on the content.
"""

def debug_print(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

def compute_embeddings(text_list, embedding_model):
    """Compute embeddings for a list of texts."""
    return embedding_model.encode(text_list, convert_to_tensor=False)

def build_jira_index(jira_issues, jira_issues_revised, embedding_model):
    """Build an index for Jira issues with their embeddings."""
    texts = [f"{issue.get('summary', "")}.\n{issue.get('description', "")}\n{jira_issues_revised.get(issue['key'], {'key': 'None'}).get('ai_description', "")}" for issue in jira_issues]

    embeddings = compute_embeddings(texts, embedding_model)
    index = []
    for idx, issue in enumerate(jira_issues):
        index.append({
            'key': issue['key'],
            'summary': issue.get('summary', ""),
            'description': issue.get('description', ""),
            'embedding': embeddings[idx]
        })
    return index

def retrieve_relevant_issues(pr_description, jira_index, top_k, threshold, embedding_model):
    """Retrieve the top_k most similar Jira issues above a similarity threshold."""
    pr_embedding = compute_embeddings([pr_description], embedding_model)[0]
    embeddings = np.array([item['embedding'] for item in jira_index])
    pr_embedding = np.array(pr_embedding).reshape(1, -1)
    sims = cosine_similarity(pr_embedding, embeddings)[0]
    top_indices = sims.argsort()[-top_k:][::-1]
    
    relevant = []
    for idx in top_indices:
        if sims[idx] >= threshold:
            relevant.append({
                'key': jira_index[idx]['key'],
                'summary': jira_index[idx]['summary'],
                'description': jira_index[idx]['description'],
                'similarity': float(sims[idx])
            })
    return relevant


def cleanup_json_response(result):
    """cleanup_json_response
    * support for deepseek - filter out the <think>...</think> content
    * sometimes the output is in a markdown code block, so filter that out too
    * some AI answers include an introductory text, so we filter that out too
    * if there are newlines - we'll remove them. They usually destroy the json syntax and are not relevant
    * once we have a '{' we start reading, as soon as all braces are closed again we break, avoiding trailing text
    """
    real_result = ""
    output = True
    ignore_heading_text = True
    braces = 0
    for line in result.split("\n"):
        if "<think>" in line:
            output = False
            continue
        if "</think>" in line:
            output = True
            continue
        if line in ["```", "```json"]:
            continue
        if '{' not in line and ignore_heading_text:
            continue
        braces += line.count('{')
        braces -= line.count('}')
        ignore_heading_text = False
        if output:
            real_result += line.replace("\n", " ").replace("\r", " ")
        if braces <= 0:
            break
    return real_result


def process_ai(task, prompt, model, auto_tokenizer_model, expect_json=True):
    """
    For a given pull request and its retrieved Jira issues,
    generate a mapping using the LLM.
    """
    print(task)
    tokenizer = AutoTokenizer.from_pretrained(auto_tokenizer_model)
    tokens = tokenizer.encode(prompt)
    # hint: e.g. deepseek can do ~ 2000 tokens - we could iterate and give more issues 
    # until we are just below 2000 tokens. Could be an extention for the future…
    debug_print(f"Current prompt: {len(prompt.split())} words = {len(tokens)} tokens")
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": 0.0,
        "max_tokens": 200
    }
    try:
        response = requests.post(OLLAMA_API_GENERATE, json=payload, stream=True)
        result = ""
        for line in response.iter_lines():
            if not line:
                continue
            decoded_line = line.decode('utf-8')
            data = json.loads(decoded_line)
            response = data.get("response", "")
            debug_print(response, end="", flush=True)
            result += response

        debug_print("\n----")

        if expect_json:
            real_result = cleanup_json_response(result)
            ret = json.loads(real_result)
        else:
            ret = result

        return ret
    except Exception as e:
        print(f"\nError while {task}: {e}")

        print("----")

        return {"error": str(e)}


def generate_mapping_for_pr(pr, relevant_issues, fallback_issues, model, auto_tokenizer_model, cache):
    prompt = PROMPT_MAP_PR.format(
        pr_url=pr['url'].replace("\"", "'"),
        pr_title=pr['title'].replace("\"", "'"),
        pr_description=pr['description'].replace("\"", "'"),
        relevant_issues=json.dumps(relevant_issues, indent=2),
        fallback_issues=json.dumps(fallback_issues, indent=2)
    )

    task = f"Thinking about {pr['url']}: \"{pr['title'].replace("\"", "'")}\"…"
    result = cache.cached_result(task, process_ai, task=task, prompt=prompt, model=model, auto_tokenizer_model=auto_tokenizer_model)
    try:
        if pr['url'] in result.keys():
            return result.get(pr['url'])
        # workaround if AI does not return the correct key
        if len(result.keys()) == 1:
            return result.get(list(result.keys())[0])
        return "No good match found for this pull request."
    except:
        return "No good match found for this pull request."


def create_ai_summary(jira_issues, related_issues, model, auto_tokenizer_model, cache):
    """Use the summary and description of the jira_issues as well as all it's parents
    to create a summary for the AI to learn from."""
    jira_issues_revised = {}
    i = 1
    for jira_issue in jira_issues:
        print(f"Creating AI Summary {i}/{len(jira_issues)}: {jira_issue.get('key')}")
        i += 1

        ai_input = []
        # remove None values
        summary = jira_issue.get('summary', '') if jira_issue.get('summary', '') else ""
        description = jira_issue.get('description', '') if jira_issue.get('description', '') else ""
        ai_input.append(f"""jira_issue = {{
"key": "{jira_issue.get('key')}"
"parent": "{jira_issue.get('parent')}"
"summary": "{summary.replace('"', '\'')}"
"description": "{description.replace('"', '\'')}"
}}

""")
        parent = related_issues.get(jira_issue.get('parent',""))
        parent_keys = []
        while parent:
            # remove None values
            summary = parent.get('summary', '') if parent.get('summary', '') else ""
            description = parent.get('description', '') if parent.get('description', '') else ""
            parent_keys.append(parent.get('key'))
            ai_input.append(f"""a_parent_to_consider = {{
"key": "{parent.get('key')}"
"parent": "{parent.get('parent')}"
"summary": "{summary.replace('"', '\'')}"
"description": "{description.replace('"', '\'')}"
}}

""")
            # get next parent
            parent = related_issues.get(parent.get('parent',""))
        current_jira_issue = {
            "key": jira_issue.get("key"),
            "summary": jira_issue.get("summary"),
            "description": jira_issue.get("description"),
            "ai_input": "".join(ai_input)
        }
        
        
        prompt = PROMPT_NEW_DEV_SUMMARY.format(
            input=current_jira_issue['ai_input'],
            jira_key=current_jira_issue['key']
        )

        print(f"Taking parents in to account: {" ".join(parent_keys)}")

        task = f"Thinking about {JIRA_HOST}/browse/{current_jira_issue['key']}: \"{current_jira_issue['summary']}\"…"
        result = cache.cached_result(task, process_ai, task=task, prompt=prompt, model=model, auto_tokenizer_model=auto_tokenizer_model, expect_json=False)
        try:
            current_jira_issue['ai_description'] = result
        except:
            current_jira_issue['ai_description'] = ""
        jira_issues_revised[jira_issue.get("key")] = current_jira_issue
    return jira_issues_revised


def map_prs_to_jira_rag(prs, jira_issues, jira_issues_revised, related_issues, fallback_issues, model, auto_tokenizer_model, top_k, threshold, cache, embedding_model):
    """
    For each pull request, retrieve the most similar Jira issues using embeddings,
    then generate a mapping via the LLM.
    """
    jira_index = build_jira_index(jira_issues, jira_issues_revised, embedding_model)
    final_mapping = {}
    for pr in prs:
        # act as if referenced issues in the PR are part of the description for context
        description = pr['description'].replace("\"", "'")
        for k in related_issues.keys():
            if pr['url'] in k:
                description += related_issues[k]['summary'].replace("\"", "'")
                description += related_issues[k]['description'].replace("\"", "'")
        pr['description'] = description
        data = f"{pr['url']} {pr['title']} {pr['description']}"
        relevant = retrieve_relevant_issues(data, jira_index, top_k=top_k, threshold=threshold, embedding_model=embedding_model)

        # patch in defaults
        fallback_issue_data = []
        for fallback_issue in fallback_issues:
            fallback_issue_data.append({
                'key': related_issues[fallback_issue]['key'],
                'summary': related_issues[fallback_issue]['summary'],
                'description': related_issues[fallback_issue]['description'],
                'similarity': float(1)
            })

        if not relevant:
            final_mapping[pr['url']] = "No good match found for this pull request."
        else:
            mapping = generate_mapping_for_pr(pr, relevant, fallback_issue_data, model=model, auto_tokenizer_model=auto_tokenizer_model, cache=cache)
            try:
                new_mapping = {}
                for key in mapping:
                    for entry in relevant:
                        if key == entry['key']:
                            new_mapping[key] = {
                                "key": key,
                                "similarity": entry['similarity'],
                            }
                    if key not in new_mapping:
                        new_mapping[key] = {
                            "key": key,
                            "similarity": None
                        }
                final_mapping[pr['url']] = new_mapping
            except:
                pass
            final_mapping[pr['url']] = mapping
    return final_mapping

def get_suggestions(json_input_file, rag_top_k, rag_threshold):
    # doing import LATE here, because it would take too long just for the "help"
    print("Loading sentence transformers...")
    from sentence_transformers import SentenceTransformer
    from transformers import AutoTokenizer

    print("Initializing Sentence Transformer…")
    # Initialize the embedding model (ensure you have the required package installed)
    embedding_model = SentenceTransformer(SCENTENCE_TRANSFORMER_MODEL)

    if __name__ == "__main__":
        print("Loading cache…")
    if os.getenv("PR_BEST_PRACTICES_TEST_CACHE"):
        cache = Cache("ai_cache.pkl")
    else:
        cache = Cache(None) # indicates not to use cache
    
    # Example pull requests and Jira issues
    #with open("data_collection.json") as f:
    #with open("data_collection_non_jira_large.json") as f:
    print("loading data...")
    with open(json_input_file, "r") as f:
        data = json.load(f)
    pull_requests = data['pull_requests']
    jira_issues = data['jira_issues']
    related_issues = data['related_issues']
    fallback_issues = data['fallback_issues']

    print(f"Getting available models from Ollama API on {OLLAMA_HOST}...")
    response = requests.get(OLLAMA_API_MODELS, timeout=60)

    model_response = response.json()
    models = [model["name"] for model in model_response.get("models", [])]

    print("Available models:")
    if len(models) == 0:
        print("No models available on Ollama API.")
    else:
        print(f" * {'\n * '.join(models)}")
    print()
    if OLLAMA_MODEL not in models:
        print(f"Model {OLLAMA_MODEL} not available on {OLLAMA_HOST}.")
        sys.exit(1)

    jira_issues_revised = create_ai_summary(jira_issues, related_issues, OLLAMA_MODEL, AUTO_TOKENIZER_MODEL, cache)

    mapping_result = map_prs_to_jira_rag(pull_requests, jira_issues, jira_issues_revised, related_issues, fallback_issues, model=OLLAMA_MODEL, auto_tokenizer_model=AUTO_TOKENIZER_MODEL, top_k=rag_top_k, threshold=rag_threshold, cache=cache, embedding_model=embedding_model)
    debug_print("Final Mapping Result:")
    # print(json.dumps(mapping_result, indent=2))
    prefix = f"{JIRA_HOST}/browse/"

    ret = {}
    for k, v in mapping_result.items():
        debug_print(f"\n{k}:")
        if k not in [p['url'] for p in pull_requests]:
            debug_print(f"{"^"* len(k)} HALLUCINATION")
            continue
        if isinstance(v, str):
            debug_print(v)
            ret[k] = []
        elif not v:
            debug_print("No good match found for this pull request.")
            ret[k] = []
        else:
            pr_issue_list = []
            for i in v:
                debug_print(f" {prefix}{i}")
                if i not in [j['key'] for j in jira_issues] and i not in related_issues.keys():
                    debug_print(f" {" " * len(prefix)}{"^"* len(i)} HALLUCINATION")
                else:
                    pr_issue_list.append(i)
            ret[k] = pr_issue_list
    return ret

if __name__ == "__main__":

    parser = argparse.ArgumentParser(allow_abbrev=False,
        description=__doc__,
        epilog=doc_epilog,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    # also show the default in the help
    parser.add_argument("--input", help="Input JSON file containing pull requests and Jira issues", default="data_collection.json")
    parser.add_argument("--rag_top_k", help="Number of top similar Jira issues to return for each PR", default=5, type=int)
    parser.add_argument("--rag_threshold", help="Threshold for similarity score to consider a Jira issue as similar to the given PR (range 0.0-1.0)", default=0.2, type=float)
    parser.add_argument("--help-md", help="Show help as Markdown", action="store_true")

    # workaround that required attribute are not given for --help-md
    if "--help-md" in sys.argv:
        print(format_help_as_md(parser))
        sys.exit(0)

    args = parser.parse_args()

    result = get_suggestions(args.input, args.rag_top_k, args.rag_threshold)

    print("\nFinal Mapping Result:")
    print(json.dumps(result, indent=2))
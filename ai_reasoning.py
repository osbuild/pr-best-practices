#!/usr/bin/python3
"""
This script uses AI to summarize the Epics (with the context of their issue-parents)
then uses sentence transformers (RAG) to find the most similar issues to the list of PRs.
Finally uses AI to figure out which of the issues match the PR the most.

It expects `get_pull_requests.py` to be run before and generate `data_collection.json`.

TBD: rewrite with langchain (e.g. using GitHub document loader directly?)
"""

import argparse
import signal
import threading
import requests
import json
import numpy as np
import os
import sys

import concurrent.futures

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
OLLAMA_HOST = os.getenv("OLLAMA_HOST")
OLLAMA_API_GENERATE = os.getenv("OLLAMA_API_GENERATE", f"{OLLAMA_HOST}/api/generate")
OLLAMA_API_MODELS = os.getenv("OLLAMA_API_MODELS", f"{OLLAMA_HOST}/api/tags")
OLLAMA_API_SHOW = os.getenv("OLLAMA_API_SHOW", f"{OLLAMA_HOST}/api/show")

doc_epilog += """Also, you might want to set the environment variable `OLLAMA_MODEL` to something you have
downloaded in ollama.  
"""
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "granite3.2:8b")

doc_epilog += """Alternatively you can also use vLLM via OpenAI API with `MODEL_API`, `MODEL_ID`
and `USER_KEY`.  
"""
MODEL_API = os.getenv("MODEL_API")
MODEL_ID = os.getenv("MODEL_ID", "/data/granite-3.2-8b-instruct")
USER_KEY = os.getenv("USER_KEY")

doc_epilog += "The environment variable `AI_REASONING_DEBUG` can be used to enable debug/verbose output.  \n"
DEBUG = bool(os.getenv("AI_REASONING_DEBUG", False))
LOG_FILE=""

# notes:
# all-MiniLM-L6-v2

SCENTENCE_TRANSFORMER_MODEL = "all-MiniLM-L6-v2"
doc_epilog += f"The transformer model for RAG is hardcoded in the script to `{SCENTENCE_TRANSFORMER_MODEL}`"

doc_epilog += """Some models have remote code as part of the model. To be on the safe side you have to explicitly
enable `AI_REASONING_TRUST_REMOTE_CODE`."""
TRUST_REMOTE_CODE = bool(os.getenv("AI_REASONING_TRUST_REMOTE_CODE", False))

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
    if LOG_FILE:
        with open(LOG_FILE, "a") as f:
            f.write(*args)
            f.write(str(kwargs.get('end', '\n')))

def compute_embeddings(text_list, embedding_model):
    """Compute embeddings for a list of texts."""
    tokenizer = embedding_model.tokenizer
    max_length = tokenizer.model_max_length

    for text in text_list:
        # Tokenize to count tokens
        tokens = tokenizer.encode(text, add_special_tokens=True)
        
        if len(tokens) > max_length:
            print(f"Checking embedding size of {text.split('\n')[0]}")
            print(f"⚠️ Input too long: {len(tokens)} tokens (max {max_length}). Matching will be bad.")
            # Truncate token list to max length
    print(f"Calculate embeddings of all {len(text_list)} entries.")
    ret = embedding_model.encode(text_list, convert_to_tensor=False)
    print(f"done")
    return ret

def build_jira_index(jira_issues, jira_issues_revised, embedding_model):
    """Build an index for Jira issues with their embeddings."""
    texts = [f"{issue['key']}: {issue.get('summary', "")}.\n{issue.get('description', "")}\n{jira_issues_revised.get(issue['key'], {'key': 'None'}).get('ai_description', "")}" for issue in jira_issues]

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

def retrieve_relevant_issues(pr_description, jira_index, pr, top_k, threshold, embedding_model):
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
                'summary': jira_index[idx].get('summary',""),
                'description': jira_index[idx].get('description',""),
                'similarity': float(sims[idx])
            })
    pr_key = "_".join(pr['url'].split('/')[:-3])
    with open(f"02_similarity_{pr_key}.json", "w") as f:
        json.dump(relevant, f, indent=2)
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


def process_ai(task, prompt, auto_tokenizer_model, expect_json=True):
    """
    For a given pull request and its retrieved Jira issues,
    generate a mapping using the LLM.
    """
    global ctx_len
    global stop_event
    print(task, flush=True)
    tokenizer = AutoTokenizer.from_pretrained(auto_tokenizer_model)
    tokens = tokenizer.encode(prompt)
    if len(tokens) > ctx_len:
        print(f"WARNING: Current prompt seems bigger than the model's context length {ctx_len}!")
        print("         Response might ignore some of the input!")
    # hint: e.g. deepseek can do ~ 2000 tokens - we could iterate and give more issues 
    # until we are just below 2000 tokens. Could be an extention for the future…
    debug_print(f"Current prompt: {len(prompt.split())} words = {len(tokens)} tokens")

    result = ""
    if OLLAMA_HOST:
        payload = {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "temperature": 0.0,
            "max_tokens": 200
        }
        try:
            response = requests.post(OLLAMA_API_GENERATE, json=payload, stream=True)
            for line in response.iter_lines():

                if stop_event.is_set():
                    return None
                if not line:
                    continue
                decoded_line = line.decode('utf-8')
                data = json.loads(decoded_line)
                response = data.get("response", "")
                debug_print(response, end="", flush=True)
                result += response

            debug_print("\n----")

        except Exception as e:
            print(f"\nError while {task}: {e}")

            print("----")

            return {"error": str(e)}
    elif MODEL_API:
        global llm
        stream = llm.stream(prompt)
        for line in stream:
            if stop_event.is_set():
                return None
            debug_print(line, end="", flush=True)
            result += line

    if expect_json:
        try:
            real_result = cleanup_json_response(result)
            ret = json.loads(real_result)
        except Exception as e:
            print(f"{task} Error while decoding json: {e}")
            print(result)
            ret = {"error": str(e)}
    else:
        ret = result

    return ret


def generate_mapping_for_pr(i, total, pr, relevant_issues, fallback_issues, auto_tokenizer_model, cache):
    prompt = PROMPT_MAP_PR.format(
        pr_url=pr['url'].replace("\"", "'"),
        pr_title=pr['title'].replace("\"", "'"),
        pr_description=pr['description'].replace("\"", "'"),
        relevant_issues=json.dumps(relevant_issues, indent=2),
        fallback_issues=json.dumps(fallback_issues, indent=2)
    )

    task = f"{i}/{total} thinking about {pr['url']}: \"{pr['title'].replace("\"", "'")}\"…"
    result = cache.cached_result(task, process_ai, task=task, prompt=prompt, auto_tokenizer_model=auto_tokenizer_model)
    try:
        if pr['url'] in result.keys():
            return result.get(pr['url'])
        # workaround if AI does not return the correct key
        if len(result.keys()) == 1:
            return result.get(list(result.keys())[0])
        return []
    except:
        return []


def _process_ai_summary(jira_issue, i, jira_issues_len, related_issues, auto_tokenizer_model, cache):
    print(f"{i}/{jira_issues_len}: Creating AI Summary for {jira_issue.get('key')}", flush=True)

    ai_input = []
    # remove None values
    summary = jira_issue.get('summary', '') if jira_issue.get('summary', '') else ""
    description = jira_issue.get('description', '') if jira_issue.get('description', '') else ""

    # present the content of the current jira issue to AI in a json format
    # TBD: test if AIs can handle markdown better?
    ai_input.append(f"""jira_issue = {{
"key": "{jira_issue.get('key')}",
"parent": "{jira_issue.get('parent')}",
"summary": "{summary.replace('"', '\'')}",
"description": "{description.replace('"', '\'')}",
"comments": "{jira_issue.get('comments')}"
}}

""")
    # also add all parents for context
    parent = related_issues.get(jira_issue.get('parent',""))
    parent_keys = []
    while parent:
        # remove None values
        summary = parent.get('summary', '') if parent.get('summary', '') else ""
        description = parent.get('description', '') if parent.get('description', '') else ""
        parent_keys.append(parent.get('key'))
        ai_input.append(f"""a_parent_to_consider = {{
"key": "{parent.get('key')}",
"parent": "{parent.get('parent')}",
"summary": "{summary.replace('"', '\'')}",
"description": "{description.replace('"', '\'')}",
"comments": "{jira_issue.get('comments')}"
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

    print(f"{i}/{jira_issues_len}: Taking parents in to account: {" ".join(parent_keys)}", flush=True)

    task = f"{i}/{jira_issues_len}: Thinking about {JIRA_HOST}/browse/{current_jira_issue['key']}: \"{current_jira_issue['summary']}\"…"
    result = cache.cached_result(task, process_ai, task=task, prompt=prompt, auto_tokenizer_model=auto_tokenizer_model, expect_json=False)
    try:
        current_jira_issue['ai_description'] = result
    except:
        current_jira_issue['ai_description'] = ""
    return current_jira_issue


def create_ai_summary(jira_issues, related_issues, auto_tokenizer_model, cache, threads):
    """Use the summary and description of the jira_issues as well as all it's parents
    to create a summary for the AI to learn from."""
    jira_issues_revised = {}
    i = 1
    global stop_event
    stop_event = threading.Event()
    if threads > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            tasks = {}
            for jira_issue in jira_issues:
                task = executor.submit(_process_ai_summary, jira_issue, i, len(jira_issues), related_issues, auto_tokenizer_model, cache)
                tasks[task] = jira_issue
                i += 1
            try:
                for task in concurrent.futures.as_completed(tasks):
                    jira_issue = tasks[task]
                    try:
                        jira_issues_revised[jira_issue['key']] = task.result()
                    except Exception as e:
                        print(f"Error processing {jira_issue['key']}: {e}")
            except KeyboardInterrupt:
                print("KeyboardInterrupt received, cancelling tasks...")
                for task in tasks:
                    task.cancel()
                executor.shutdown(wait=False)
                stop_event.set()
                raise
    else:
        for jira_issue in jira_issues:
            jira_issues_revised[jira_issue['key']] = _process_ai_summary(jira_issue, i, len(jira_issues), related_issues, auto_tokenizer_model, cache)
            i += 1

    return jira_issues_revised

def _process_pr(i, total, pr, related_issues, jira_index, top_k, threshold, embedding_model, fallback_issues, auto_tokenizer_model, cache):
    # act as if referenced issues in the PR are part of the description for context
    description = pr.get("description", "")
    if description is None:
        description = ""
    description = description.replace("\"", "'")
    for k in related_issues.keys():
        if pr['url'] in k:
            description += related_issues[k]['summary'].replace("\"", "'")
            description += related_issues[k]['description'].replace("\"", "'")
    pr['description'] = description
    data = f"{pr['url']} {pr['title']} {pr['description']}"
    relevant = retrieve_relevant_issues(data, jira_index, pr, top_k=top_k, threshold=threshold, embedding_model=embedding_model)

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
        ret = {"error": "No good match found for this pull request."}
    else:
        mapping = generate_mapping_for_pr(i, total, pr, relevant, fallback_issue_data, auto_tokenizer_model=auto_tokenizer_model, cache=cache)
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
                new_mapping[key]["url"] = f"{JIRA_HOST}/browse/{key}"
            new_mapping['considered'] = [{'key': v['key'], 'similarity': v['similarity'], 'url': f"{JIRA_HOST}/browse/{v['key']}"} for v in relevant]
            ret = new_mapping
        except:
            ret = mapping
    ret["key"] =  pr['url']
    return ret


def map_prs_to_jira_rag(prs, jira_issues, jira_issues_revised, related_issues, fallback_issues, auto_tokenizer_model, top_k, threshold, cache, embedding_model, threads):
    """
    For each pull request, retrieve the most similar Jira issues using embeddings,
    then generate a mapping via the LLM.
    """
    jira_index = build_jira_index(jira_issues, jira_issues_revised, embedding_model)
    final_mapping = {}

    stop_event = threading.Event()
    if threads > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            tasks = {}
            i = 1
            for pr in prs:
                task = executor.submit(_process_pr, i, len(prs), pr, related_issues, jira_index, top_k, threshold, embedding_model, fallback_issues, auto_tokenizer_model, cache)
                tasks[task] = pr
                i += 1
            try:
                for task in concurrent.futures.as_completed(tasks):
                    pr = tasks[task]
                    try:
                        final_mapping[pr["url"]] = task.result()
                    except Exception as e:
                        print(f"Error processing {pr['url']}: {e}")
            except KeyboardInterrupt:
                print("KeyboardInterrupt received, cancelling tasks...")
                for task in tasks:
                    task.cancel()
                executor.shutdown(wait=False)
                stop_event.set()
                raise
    else:
        i = 1
        for pr in prs:
            final_mapping[pr['url']] = _process_pr(i, len(prs), pr, related_issues, jira_index, top_k, threshold, embedding_model, fallback_issues, auto_tokenizer_model, cache)
            i += 1
    return final_mapping

def get_suggestions(json_input_file, rag_top_k, rag_threshold, threads):
    global ctx_len
    # doing import LATE here, because it would take too long just for the "help"
    print("Loading sentence transformers...")
    global SentenceTransformer
    from sentence_transformers import SentenceTransformer
    global AutoTokenizer
    from transformers import AutoTokenizer

    print("Initializing Sentence Transformer…")
    # Initialize the embedding model (ensure you have the required package installed)
    embedding_model = SentenceTransformer(SCENTENCE_TRANSFORMER_MODEL, trust_remote_code=TRUST_REMOTE_CODE)

    if os.getenv("PR_BEST_PRACTICES_TEST_CACHE"):
        print("Loading cache…")
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

    if OLLAMA_HOST:
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

        print("Get model info…")
        response = requests.post(OLLAMA_API_SHOW, timeout=60, json={"model": OLLAMA_MODEL})
        model_info = response.json()
        model_context_length_key = list(filter(lambda k: "context_length" in k, model_info.get('model_info',{}).keys()))
        if len(model_context_length_key) == 1:
            ctx_len = model_info.get('model_info',{}).get(model_context_length_key[0])
            print(f"Using {OLLAMA_MODEL} (Context length: {ctx_len})")
        else:
            print("Error reading 'context_length' from 'model card' - just informational, continuing…")
            print(model_info.get('model_info',{}))
    else:
        # TBD: get the context length! via vLLM
        ctx_len = 128000
        global llm
        import truststore
        truststore.inject_into_ssl()
        from langchain_community.llms import VLLMOpenAI

        max_request_tokens = 50000
        llm = VLLMOpenAI(openai_api_key=USER_KEY, openai_api_base=f"{MODEL_API}/v1", model_name=MODEL_ID, streaming=True, max_tokens=ctx_len - max_request_tokens)


    jira_issues_revised = create_ai_summary(jira_issues, related_issues, AUTO_TOKENIZER_MODEL, cache, threads)
    
    jira_ai_summary_path = "01_jira_ai_summary.json"
    with open(jira_ai_summary_path, "w") as f:
        json.dump(jira_issues_revised, f, indent=2)

    mapping_result = map_prs_to_jira_rag(pull_requests, jira_issues, jira_issues_revised, related_issues, fallback_issues, AUTO_TOKENIZER_MODEL, rag_top_k, rag_threshold, cache, embedding_model, threads)
    debug_print("Final Mapping Result:")
    # print(json.dumps(mapping_result, indent=2))
    prefix = f"{JIRA_HOST}/browse/"


    ret = {}
    for pr, pr_data in mapping_result.items():
        ret[pr] = {}
        ret[pr]['match'] = []
        debug_print(f"\n{pr}:")
        if pr not in [p['url'] for p in pull_requests]:
            debug_print(f"{"^"* len(pr)} HALLUCINATION")
            continue
        if isinstance(pr_data, str):
            debug_print(pr_data)
        elif not pr_data:
            debug_print("No good match found for this pull request.")
        else:
            for issue_found, issue_data in pr_data.items():
                debug_print(f" {prefix}{issue_found}")
                if issue_found not in [j['key'] for j in jira_issues] and issue_found not in related_issues.keys():
                    debug_print(f" {" " * len(prefix)}{"^"* len(issue_found)} HALLUCINATION")
                else:
                    ret[pr]['match'].append(issue_data)
        ret[pr]['considered'] = pr_data['considered']
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
    parser.add_argument("--log", help="Create a logfile with debug messages", default="", type=str)
    parser.add_argument("--output", help="Output JSON file containing the mapping result", default="rag_mapping_result.json")
    parser.add_argument("--threads", help="Number of threads to run AI in parallel", default=1, type=int)
    parser.add_argument("--help-md", help="Show help as Markdown", action="store_true")

    # workaround that required attribute are not given for --help-md
    if "--help-md" in sys.argv:
        print(format_help_as_md(parser))
        sys.exit(0)

    args = parser.parse_args()

    if MODEL_API is None and OLLAMA_HOST is None:
        print("Please provide either `MODEL_API` or `OLLAMA_HOST`")
        parser.print_help()
        sys.exit(1)

    LOG_FILE = args.log

    result = get_suggestions(args.input, args.rag_top_k, args.rag_threshold, args.threads)

    print(f"\nFinal Mapping Result (saved to `{args.output}`):")

    show_condensed = {
        k: [ { "key": m['key'], "summary": m['summary'], "url": m['url']} for m in v['match']]
        for k, v in result.items() 
    }
    print(json.dumps(show_condensed, indent=2))

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)

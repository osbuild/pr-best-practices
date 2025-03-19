import requests
import json
import numpy as np
import os
import sys
if __name__ == "__main__":
    print("Loading sentence transformers...")
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import AutoTokenizer
from utils import Cache

JIRA_HOST = os.getenv("JIRA_HOST", "https://issues.redhat.com")
# MODEL ="granite3-dense:2b"
# MODEL ="granite3.2:8b"
MODEL = "deepseek-r1:7b"
# MODEL = "deepseek-r1:14b"
# MODEL = "mistral:7b-instruct"
AUTO_TOKENIZER_MODEL = "deepseek-ai/DeepSeek-R1"

# Ollama API Endpoint
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_API_GENERATE = os.getenv("OLLAMA_API_ENDPOINT", f"{OLLAMA_HOST}/api/generate")
OLLAMA_API_MODELS = os.getenv("OLLAMA_API_MODELS", f"{OLLAMA_HOST}/api/tags")
DEBUG = True


PROMPT_MAP_PR ="""You are an expert at mapping a GitHub pull request to Jira issues based on their descriptions, title and summary.

Pull Request:
URL: "{pr_url}"
Title: "{pr_title}"
Description: "{pr_description}"

Retrieved Jira Issues:
{relevant_issues}

If the pull request description clearly relates to any of these Jira issues, list the matching Jira issue KEYs.
If not, output "No good match found for this pull request."

Return your answer as a JSON object with the pull request URL as key and its value as either:
- a list of matching Jira issue KEYs, or
- the string "No good match found for this pull request."
- never return a Jira issue KEY that was not retrieved.
- never return both "No good match found for this pull request." and a list of Jira issue KEYs.

The output format should look like this:
{{ "{{pr['url']}}": ["JIRA-123", "JIRA-456"] }}
"""

PROMPT_NEW_SUMMARY ="""You are an expert at creating a summary for a Jira issue based on its title, summary and description
as well as all its parents.

You focus on making the description brief but enrich the description with aspects of all parents, not loosing any detail.
Focus on aspects of the context that the parent issues describe, which are relevant for a technical implementation.
Don't worry about the formatting, just focus on the content.

The input data:
{input}

Return your answer solely as JSON object where you repeat exactly the 'key' of the jira_issue with an additional key 'ai_description' that
contains your generated summary.

The output format should look like this:
{{  "key": "{jira_key}",
    "ai_description": "Your generated summary of the Jira issue" }}
"""

PROMPT_NEW_DEV_SUMMARY ="""You are an expert in creating instructions for a software developer based on the title, summary and description of a Jira issue.
The parent issues represent the context of the issue and are relevant for the implementation.
You also take into account the parent issues to create good instructions with the context of the issue.

You focus on making the description brief but enrich the description with aspects of all parents, not loosing any detail.
Focus on aspects of the context that the parent issues describe, which are relevant for the implementation.
Don't worry about the formatting, just focus on the content.

The input data:
{input}

Return your answer solely as JSON object where you repeat exactly the 'key' of the jira_issue with an additional key 'ai_description' that
contains your generated instructions. No formatting of your output is required.

The output format should look like this:
{{  "key": "{jira_key}",
    "ai_description": "Your generated instructions for the Jira issue" }}
"""

if __name__ == "__main__":
    print("Initializing Sentence Transformer…")
# Initialize the embedding model (ensure you have the required package installed)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

if __name__ == "__main__":
    print("Loading cache…")
if os.getenv("PR_BEST_PRACTICES_TEST_CACHE"):
    cache = Cache("ai_cache.pkl")
else:
    cache = Cache(None) # indicates not to use cache

def compute_embeddings(text_list):
    """Compute embeddings for a list of texts."""
    return embedding_model.encode(text_list, convert_to_tensor=False)

def build_jira_index(jira_issues, jira_issues_revised):
    """Build an index for Jira issues with their embeddings."""
    texts = [f"{issue.get('summary', "")}.\n{issue.get('description', "")}\n{jira_issues_revised.get(issue['key'], {'key': 'None'}).get('ai_description', "")}" for issue in jira_issues]

    embeddings = compute_embeddings(texts)
    index = []
    for idx, issue in enumerate(jira_issues):
        index.append({
            'key': issue['key'],
            'summary': issue.get('summary', ""),
            'description': issue.get('description', ""),
            'embedding': embeddings[idx]
        })
    return index

def retrieve_relevant_issues(pr_description, jira_index, top_k, threshold):
    """Retrieve the top_k most similar Jira issues above a similarity threshold."""
    pr_embedding = compute_embeddings([pr_description])[0]
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


def process_ai(task, prompt, model, auto_tokenizer_model):
    """
    For a given pull request and its retrieved Jira issues,
    generate a mapping using the LLM.
    """
    print(task)
    tokenizer = AutoTokenizer.from_pretrained(auto_tokenizer_model)
    tokens = tokenizer.encode(prompt)
    # hint: e.g. deepseek can do ~ 2000 tokens - we could iterate and give more issues 
    # until we are just below 2000 tokens. Could be an extention for the future…
    print(f"Current prompt: {len(prompt.split())} words = {len(tokens)} tokens")
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
            print(response, end="", flush=True)
            result += response

        real_result = cleanup_json_response(result)
        mapping = json.loads(real_result)
        print ("\n----")
        return mapping
    except Exception as e:
        print(f"\nError while {task}: {e}")

        print("----")

        return {"error": str(e)}


def generate_mapping_for_pr(pr, relevant_issues, model, auto_tokenizer_model):
    prompt = PROMPT_MAP_PR.format(
        pr_url=pr['url'].replace("\"", "'"),
        pr_title=pr['title'].replace("\"", "'"),
        pr_description=pr['description'].replace("\"", "'"),
        relevant_issues=json.dumps(relevant_issues, indent=2)
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


def create_ai_summary(jira_issues, related_issues, model, auto_tokenizer_model):
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
        result = cache.cached_result(task, process_ai, task=task, prompt=prompt, model=model, auto_tokenizer_model=auto_tokenizer_model)
        try:
            current_jira_issue['ai_description'] = result.get('ai_description', "")
        except:
            current_jira_issue['ai_description'] = ""
        jira_issues_revised[jira_issue.get("key")] = current_jira_issue
    return jira_issues_revised

def map_prs_to_jira_rag(prs, jira_issues, jira_issues_revised, related_issues, model, auto_tokenizer_model, top_k, threshold):
    """
    For each pull request, retrieve the most similar Jira issues using embeddings,
    then generate a mapping via the LLM.
    """
    jira_index = build_jira_index(jira_issues, jira_issues_revised)
    final_mapping = {}
    for pr in prs:
        # act as if referenced issues in the PR are part of the description for context
        description = pr['description'].replace("\"", "'")
        for k in related_issues.keys():
            if pr['url'] in k:
                description += related_issues[k]['summary'].replace("\"", "'")
                description += related_issues[k]['description'].replace("\"", "'")
        pr['description'] = description
        data = f"{pr['title']} {pr['description']}"
        relevant = retrieve_relevant_issues(data, jira_index, top_k=top_k, threshold=threshold)
        if not relevant:
            final_mapping[pr['url']] = "No good match found for this pull request."
        else:
            mapping = generate_mapping_for_pr(pr, relevant, model=model, auto_tokenizer_model=auto_tokenizer_model)
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

if __name__ == "__main__":

    # Example pull requests and Jira issues
    #with open("data_collection.json") as f:
    #with open("data_collection_non_jira_large.json") as f:
    print("loading data...")
    with open("data_collection_already_linked_cleaned.json") as f:
        data = json.load(f)
    pull_requests = data['pull_requests']
    jira_issues = data['jira_issues']
    related_issues = data['related_issues']

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
    if MODEL not in models:
        print(f"Model {MODEL} not available on {OLLAMA_HOST}.")
        sys.exit(1)

    jira_issues_revised = create_ai_summary(jira_issues, related_issues, MODEL, AUTO_TOKENIZER_MODEL)

    mapping_result = map_prs_to_jira_rag(pull_requests, jira_issues, jira_issues_revised, related_issues, model=MODEL, auto_tokenizer_model=AUTO_TOKENIZER_MODEL, top_k=5, threshold=0)
    print("Final Mapping Result:")
    # print(json.dumps(mapping_result, indent=2))
    prefix = " https://issues.redhat.com/browse/"

    for k, v in mapping_result.items():
        print(f"\n{k}:")
        if k not in [p['url'] for p in pull_requests]:
            print(f"{"^"* len(k)} HALLUCINATION")
        if isinstance(v, str):
            print(v)
        elif not v:
            print("No good match found for this pull request.")
        else:
            for i in v:
                print(f"{prefix}{i}")
                if i not in [j['key'] for j in jira_issues]:
                    print(f"{" " * len(prefix)}{"^"* len(i)} HALLUCINATION")


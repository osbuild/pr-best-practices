import requests
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# Initialize the embedding model (ensure you have the required package installed)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

# URL for the Ollama API endpoint – adjust as needed.
API_URL = "http://localhost:11434/api/generate"

def compute_embeddings(text_list):
    """Compute embeddings for a list of texts."""
    return embedding_model.encode(text_list, convert_to_tensor=False)

def build_jira_index(jira_issues):
    """Build an index for Jira issues with their embeddings."""
    texts = [f"{issue.get('summary', "")} {issue.get('description', "")}" for issue in jira_issues]
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

def retrieve_relevant_issues(pr_description, jira_index, top_k=3, threshold=0.5):
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

def generate_mapping_for_pr(pr, relevant_issues, model="mistral"):
    """
    For a given pull request and its retrieved Jira issues,
    generate a mapping using the LLM.
    """
    prompt = f"""
You are an expert at mapping GitHub pull requests to Jira issues based on their descriptions.

Pull Request:
URL: {pr['url']}
Title: {pr['title']}
Description: {pr['description']}

Retrieved Jira Issues:
{json.dumps(relevant_issues, indent=2)}

If the pull request description clearly relates to any of these Jira issues, list the matching Jira issue KEYs.
If not, output "No good match found for this pull request."

Return your answer as a JSON object with the pull request URL as key and its value as either:
- a list of matching Jira issue KEYs, or
- the string "No good match found for this pull request."
"""
    payload = {
        "model": model,
        "prompt": prompt,
        "temperature": 0.0,
        "max_tokens": 200
    }
    try:
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()
        result = ""
        for line in response.text.split("\n"):
            if not line:
                continue
            data = json.loads(line)
            result += data.get("response", "")
        mapping = json.loads(result)
        return mapping.get(pr['url'], "No good match found for this pull request.")
    except Exception as e:
        print(f"Error generating mapping for PR {pr['url']}: {e}")
        return "No good match found for this pull request."


def map_prs_to_jira_rag(prs, jira_issues, model="mistral", top_k=3, threshold=0.5):
    """
    For each pull request, retrieve the most similar Jira issues using embeddings,
    then generate a mapping via the LLM.
    """
    jira_index = build_jira_index(jira_issues)
    final_mapping = {}
    for pr in prs:
        data = f"{pr['title']} {pr['description']}"
        relevant = retrieve_relevant_issues(data, jira_index, top_k=top_k, threshold=threshold)
        if not relevant:
            final_mapping[pr['url']] = "No good match found for this pull request."
        else:
            mapping = generate_mapping_for_pr(pr, relevant, model=model)
            final_mapping[pr['url']] = mapping
    return final_mapping

if __name__ == "__main__":
    # Example pull requests and Jira issues
    with open("data_collection.json") as f:
        data = json.load(f)
    pull_requests = data['pull_requests']
    jira_issues = data['jira_issues']
    mapping_result = map_prs_to_jira_rag(pull_requests, jira_issues, model="granite3-dense:2b", top_k=30, threshold=0.1)
    print("Final Mapping Result:")
    # print(json.dumps(mapping_result, indent=2))
    for k, v in mapping_result.items():
        print(f"\n{k}:")
        if isinstance(v, str):
            print(v)
        else:
            for i in v:
                print(f" https://issues.redhat.com/browse/{i}")


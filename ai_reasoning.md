# Usage
```
       ai_reasoning.py [-h] [--input INPUT] [--rag_top_k RAG_TOP_K]
                       [--rag_threshold RAG_THRESHOLD] [--log LOG]
                       [--output OUTPUT] [--help-md]
```
This script uses AI to summarize the Epics (with the context of their issue-
parents) then uses sentence transformers (RAG) to find the most similar issues
to the list of PRs. Finally uses AI to figure out which of the issues match
the PR the most. It expects `get_pull_requests.py` to be run before and
generate `data_collection.json`.

# Options
```
  -h, --help            show this help message and exit
  --input INPUT         Input JSON file containing pull requests and Jira
                        issues (default: data_collection.json)
  --rag_top_k RAG_TOP_K
                        Number of top similar Jira issues to return for each
                        PR (default: 5)
  --rag_threshold RAG_THRESHOLD
                        Threshold for similarity score to consider a Jira
                        issue as similar to the given PR (range 0.0-1.0)
                        (default: 0.2)
  --log LOG             Create a logfile with debug messages (default: )
  --output OUTPUT       Output JSON file containing the mapping result
                        (default: rag_mapping_result.json)
  --help-md             Show help as Markdown (default: False)
```
You can override the URL to Jira by setting the environment variable
`JIRA_HOST`. If you have ollama running on another host (with a decent GPU),
you might want to set the environment variable `OLLAMA_HOST` to something like
`http://other_host:11434`. Also, you might want to set the environment
variable `OLLAMA_MODEL` to something you have downloaded in ollama. The
environment variable `AI_REASONING_DEBUG` can be used to enable debug/verbose
output. The transformer model for RAG is hardcoded in the script to `all-
MiniLM-L6-v2`


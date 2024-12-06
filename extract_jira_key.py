import sys
import re

def extract_jira_issue_key(text):
    """
    Extracts a Jira issue key from the input text following the /jira-epic pattern.
    """
    # regular expression to match the /jira-epic command and extract the issuekey
    pattern = r"/jira-epic (\b[A-Z]+-\d+\b)"
    # Search for the pattern in the text
    match = re.search(pattern, text)
    # Return the captured group if a match is found
    return match.group(1) if match else None


if __name__ == "__main__":
    # Read input text from the command line argument
    if len(sys.argv) > 1:
        input_text = sys.argv[1]
        # Extract and print the Jira issue key
        jira_issue_key = extract_jira_issue_key(input_text)
        if jira_issue_key:
            print(jira_issue_key)
        else:
            sys.exit(0)
    else:
        print("Please provide the input text as an argument.")

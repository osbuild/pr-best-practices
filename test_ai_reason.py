from ai_reason import map_prs_to_jira_rag

def test_full_program():
    pull_requests = [
        {
            "id": "PR-101",
            "description": "Fixes bug in login process and resolves session management issue."
        },
        {
            "id": "PR-102",
            "description": "Adds a new feature for user profile customization."
        },
        {
            "id": "PR-103",
            "description": "Updates documentation for deployment process."
        },
        {
            "id": "PR-104",
            "description": "Implement new program for recipe storage."
        }
    ]
    
    jira_issues = [
        {
            "id": "JIRA-200",
            "description": "Issue with login failure and session expiration."
        },
        {
            "id": "JIRA-201",
            "description": "Documentation updates required for the deployment process."
        },
        {
            "id": "JIRA-202",
            "description": "Implement user profile customization functionality."
        }
    ]
    mapping_result = map_prs_to_jira_rag(pull_requests, jira_issues, model="granite3-dense:2b", top_k=3, threshold=0.5)
    assert mapping_result == {
        "PR-101": ["JIRA-200"],
        "PR-102": ["JIRA-202"],
        "PR-103": ["JIRA-201"],
        "PR-104": "No good match found for this pull request."
    }
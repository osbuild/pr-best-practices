from ai_reasoning import map_prs_to_jira_rag

def test_full_program():
    pull_requests = [
        {
            "url": "http://jira/browse/PR-101",
            "title": "Fix login process",
            "description": "Fixes bug in login process and resolves session management issue."
        },
        {
            "url": "http://jira/browse/PR-102",
            "title": "User profile customization",
            "description": "Adds a new feature for user profile customization."
        },
        {
            "url": "http://jira/browse/PR-103",
            "title": "Update deployment process",
            "description": "Updates documentation for deployment process."
        },
        {
            "url": "http://jira/browse/PR-104",
            "title": "Recipe storage",
            "description": "Implement new program for recipe storage."
        }
    ]
    
    jira_issues = [
        {
            "key": "JIRA-200",
            "summary": "Login failure and session expiration",
            "description": "Issue with login failure and session expiration."
        },
        {
            "key": "JIRA-201",
            "summary": "Deployment documentation",
            "description": "Documentation updates required for the deployment process."
        },
        {
            "key": "JIRA-202",
            "summary": "User profile customization",
            "description": "Implement user profile customization functionality."
        }
    ]
    mapping_result = map_prs_to_jira_rag(pull_requests, jira_issues, model="granite3-dense:2b", top_k=3, threshold=0.5)
    assert mapping_result == {
        "http://jira/browse/PR-101": ["JIRA-200"],
        "http://jira/browse/PR-102": ["JIRA-202"],
        "http://jira/browse/PR-103": ["JIRA-201"],
        "http://jira/browse/PR-104": "No good match found for this pull request."
    }
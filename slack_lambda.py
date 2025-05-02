#!/usr/bin/env python3
"""
Slack Lambda Function to be used in AWS Lambda.
This function handles incoming requests from Slack, verifies the request signature,
and processes commands sent to the Slack bot.
"""

import boto3
import os
import json
import time
import hmac
import hashlib
import urllib.parse
import base64

lambda_client = boto3.client('lambda')

def _handle_request(params):
    user = params.get("user_name", ["there"])[0]
    command = params.get("command")
    text = params.get("text", [""])[0]

    if not command:
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": {"error": "Missing command"}
        }
    command = command[0].lstrip("/").lower()
    if command == "hi":
        # Prepare the response message
        message = f"👋 {command} {user}, nice to meet you! I'm healthy, up & running."
    elif command == "pr2jira":
        if text.lower() == "help":
            message = f"""The command `/{command}` can show you, if your <https://github.com/pulls|PRs in Github> are 
linked to a Jira ticket as described <https://addlinkhere.com|here>.
If you add a username to `/{command}`, it will list you the same for another user, so you can nag them :meow_halo:.
"""
        else:
            user = text if text else user
            github_token = os.environ.get('GITHUB_TOKEN')
            organization = os.environ.get('GITHUB_ORGANIZATION')
            payload = {
                "user": user,
                "organization": organization,
                "github_token": github_token,
                "response_url": params.get('response_url')[0],
            }
            lambda_client.invoke(
                    FunctionName='schutzbot_command_get_pull_requests',
                    InvocationType='Event',  # async invoke
                    Payload=json.dumps(payload)
            )
            message = f"👋 I will check the PRs of {user} and let you know if they are linked to a Jira ticket."
    else:
        message = f"👋 Hello {user}. The command '{command}' + '{text}' is not yet implemented. You are ahead of time!"

    # Return a valid JSON response
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": {"text": message}
    }


def _check_request_validity(event):
    signing_secret = os.environ.get('SLACK_SIGNING_SECRET')
    if not signing_secret:
        return None, {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": {"error": "I'm not configured properly"}
        }

    headers = event.get("headers", {})
    slack_signature = headers.get("X-Slack-Signature") or headers.get("x-slack-signature")
    slack_request_timestamp = headers.get("X-Slack-Request-Timestamp") or headers.get("x-slack-request-timestamp")
    
    if not slack_signature or not slack_request_timestamp:
        return None, {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": {"error": "Missing signature or timestamp"}
        }
    
    try:
        timestamp = int(slack_request_timestamp)
    except ValueError:
        return None, {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": {"error": "Invalid timestamp"}
        }
    
    # Prevent replay attacks by ensuring the timestamp is recent (within 5 minutes)
    current_time = int(time.time())
    if abs(current_time - timestamp) > 60 * 5:
        return None, {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": {"error": "Request timestamp too old"}
        }
    
    isBase64Encoded = event.get("isBase64Encoded", False)
    if isBase64Encoded:
        body = base64.b64decode(event["body"]).decode("utf-8")
    else:
        body = event.get("body", "")
    
    # Build the basestring as required by Slack: "v0:{timestamp}:{body}"
    sig_basestring = f"v0:{slack_request_timestamp}:{body}"
    
    # Create an HMAC SHA256 hash using the signing secret
    computed_hash = hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    computed_signature = f"v0={computed_hash}"
    
    # Compare the computed signature with the one from Slack
    if not hmac.compare_digest(computed_signature, slack_signature):
        return None, {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": {"error": "Invalid request signature"}
        }
    return body, None

def lambda_handler(event, context):

    body, error = _check_request_validity(event)    
    if error:
        return error

    params = urllib.parse.parse_qs(body)

    return _handle_request(params)


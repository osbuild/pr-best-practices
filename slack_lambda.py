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

from utils import UserMap
from botocore.exceptions import ClientError

import logging

# Set the logging level to DEBUG for more verbose output
logger = logging.getLogger()
logger.setLevel(logging.INFO)

lambda_client = boto3.client('lambda')

def _handle_request(params, staging=False):
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
    message = None
    if staging:
        command = command.removesuffix("_staging")
    if command == "hi":
        # Prepare the response message
        message = f"👋 {command} {user}, nice to meet you! I'm healthy, up & running."
    elif command == "pr2jira":
        if text.lower() == "help":
            message = f"""The command `/{command}` can show you, if your <https://github.com/pulls|PRs in Github> are 
linked to a Jira ticket.
Please add your *GitHub username* after `/{command}` if it's not the same as the slack username.
"""
        else:
            user_map = UserMap(os.environ.get('USER_MAP_FILE', 'usermap.yaml'))
            args = text if text else user_map.slack2github(user)
            jira_user = user_map.slack2jira(user)
            arg_array = args.split(" ")
            if len(arg_array) == 2:
                args = arg_array[0]
                jira_user = arg_array[1]
            elif len(arg_array) > 2:
                return ":stop: There are too many arguments. Please use the format: `/pr2jira [<github_user>|<github_user> <jira_user>]`"

            if not message:
                github_token = get_secret("SCHUTZBOT_GITHUB_TOKEN")
                github_organization = os.environ.get('GITHUB_ORGANIZATION')

                jira_token = get_secret("SLACK_COMMAND_JIRA_TOKEN")
                jira_board_id = os.environ.get('JIRA_BOARD_ID')

                jira_current_sprint_url = os.environ.get("JIRA_CURRENT_SPRINT_URL")
                jira_backlog_url = os.environ.get("JIRA_BACKLOG_URL")

                message = f":waittime: I will check the PRs of `{args}` correlate with issues from `{jira_user}` and let you know if all is good…"
                payload = {
                    "jira_user": jira_user,
                    "args": args,
                    "github_organization": github_organization,
                    "github_token": github_token,
                    "jira_token": jira_token,
                    "jira_board_id": jira_board_id,
                    "jira_current_sprint_url": jira_current_sprint_url,
                    "jira_backlog_url": jira_backlog_url,
                    "original_message": message,
                    "response_url": params.get('response_url')[0],
                }
                lambda_client.invoke(
                        FunctionName='schutzbot_command_get_pull_requests' if not staging else 'schutzbot_command_staging_get_pull_requests',
                        InvocationType='Event',  # async invoke
                        Payload=json.dumps(payload)
                )

    else:
        message = f":stop: Hello {user}. The command '{command}' + '{text}' is not yet implemented. You are ahead of time!"

    if staging:
        message = f"I'm the staging version!\n\n{message}"
    # Return a valid JSON response
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": {"text": message}
    }


def get_secret(secret_name):
    """
    Retrieve a secret from AWS Secrets Manager.
    or fallback to environment variable if not found.
    """
    logger.debug(f"Getting secret {secret_name}")

    try:
        get_secret_value_response = secretmanager_client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    secret = get_secret_value_response['SecretString']
    if secret:
        return secret
    else:
        logger.warning(f"Falling back to get {secret_name} from env")
        return os.environ.get(secret_name)


def _check_request_validity(event):
    signing_secret = get_secret("SLACK_SCHUTZBOT_SIGNING_SECRET")
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

    global secretmanager_client

    region_name = os.environ.get('SECRETMANAGER_AWS_REGION', 'us-east-1')

    # Create a Secrets Manager client
    session = boto3.session.Session()
    secretmanager_client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    body, error = _check_request_validity(event)    
    if error:
        return error

    logger.debug("Request valid")
    params = urllib.parse.parse_qs(body)

    function_name = context.function_name.lower()
    staging = "staging" in function_name
    ret = _handle_request(params, staging)
    logger.debug("Request done")
    return ret


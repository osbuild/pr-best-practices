import os
import argparse
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

def send_dm(token, user_id, message):
    client = WebClient(token=token)
    try:
        response = client.conversations_open(users=[user_id])
        channel_id = response["channel"]["id"]
        client.chat_postMessage(channel=channel_id, text=message)
        print("Message sent successfully!")
    except SlackApiError as e:
        print(f"Error sending message: {e.response['error']}")

def main():
    parser = argparse.ArgumentParser(description="Send a direct message on Slack.")
    parser.add_argument("-t", "--token", type=str, default=os.getenv("SLACK_BOT_TOKEN"),
                        help="Slack Bot User OAuth Token (defaults to env var SLACK_BOT_TOKEN)")
    parser.add_argument("-u", "--user", type=str, required=True, help="Slack User ID to send the message to")
    parser.add_argument("-m", "--message", type=str, required=True, help="Message to send")
    
    args = parser.parse_args()
    
    if not args.token:
        print("Error: Slack token is required (provide via argument or set SLACK_BOT_TOKEN env variable).")
        exit(1)

    send_dm(args.token, args.user, args.message)

if __name__ == "__main__":
    main()
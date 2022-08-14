import os
import sys
from tweepy import Client

release_version = sys.argv[1]
if release_version.endswith(".0"):
    client = Client(
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_KEY_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
    )
    link = "https://docs.pulpproject.org/pulpcore/changes.html"
    msg = f"pulpcore-{release_version} - Check out for more details: {link}"
    release_msg = f"Hey! We've just released {msg}"
    client.create_tweet(text=release_msg)

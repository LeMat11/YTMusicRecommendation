import os
from dotenv import load_dotenv
from ytmusicapi import setup_oauth

load_dotenv()

CLIENT_ID = os.getenv("YTMUSIC_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("YTMUSIC_CLIENT_SECRET", "")

if not CLIENT_ID or not CLIENT_SECRET:
    print("❌ YTMUSIC_CLIENT_ID or YTMUSIC_CLIENT_SECRET not set in .env")
    exit(1)

print("Attempting to talk to Google...")
setup_oauth(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
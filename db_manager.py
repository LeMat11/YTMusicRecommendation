import sqlite3
from datetime import datetime, timedelta
import os

DB_NAME = "music_memory.db"

def init_db():
    # Delete old DB if it exists to prevent schema conflicts from previous versions
    # Only do this the very first time if you had an old version.
    # if os.path.exists(DB_NAME): return 

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Create table with USER_ID column
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (user_id TEXT, video_id TEXT, title TEXT, date_added TEXT, 
                 PRIMARY KEY (user_id, video_id))''')
    conn.commit()
    conn.close()

def add_to_memory(user_id, video_id, title):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        # Save song for specific user
        c.execute("INSERT OR IGNORE INTO history VALUES (?, ?, ?, ?)", 
                  (user_id, video_id, title, str(datetime.now().date())))
        conn.commit()
    except:
        pass
    conn.close()

def get_recent_recommendations(user_id, days=30):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    cutoff = str(datetime.now().date() - timedelta(days=days))
    # Retrieve songs only for this specific user
    c.execute("SELECT video_id FROM history WHERE user_id = ? AND date_added > ?", 
              (user_id, cutoff))
    results = [row[0] for row in c.fetchall()]
    conn.close()
    return set(results)
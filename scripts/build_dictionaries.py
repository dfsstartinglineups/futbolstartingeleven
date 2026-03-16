import json
import os
import urllib.request
import time
from datetime import datetime, timezone

# --- CONFIGURATION ---
API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ.get("FOOTBALL_API_KEY")

# Script is in /scripts, data is in /data at root
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
os.makedirs(DATA_DIR, exist_ok=True)

TEAM_DICT_PATH = os.path.join(DATA_DIR, "master_teams.json")
PLAYER_DICT_PATH = os.path.join(DATA_DIR, "master_players.json")

# 41 Leagues to Sync
TOP_LEAGUE_IDS = [
    39, 40, 140, 135, 78, 61, 88, 94, 203, 144, 179, 119, # Europe
    253, 262, 71, 128, 239, # Americas
    307, 98, 188, 292, # World
    2, 3, 848, 13, 11, 16, 528, 45, 48, 143, 137, 81, # Cups
    1, 4, 9, 5, 531, # International
    44, 254 # Women
]

def fetch_data(endpoint):
    req = urllib.request.Request(f"{API_HOST}/{endpoint}")
    req.add_header("x-apisports-key", API_KEY)
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            time.sleep(0.6) # Slightly slower for maximum safety
            return data
    except Exception as e:
        print(f"Error fetching {endpoint}: {e}")
        return None

def sync_all_leagues():
    # Load existing to merge rather than overwrite (even safer!)
    if os.path.exists(TEAM_DICT_PATH):
        with open(TEAM_DICT_PATH, 'r') as f: master_teams = json.load(f)
    else: master_teams = {}

    if os.path.exists(PLAYER_DICT_PATH):
        with open(PLAYER_DICT_PATH, 'r') as f: master_players = json.load(f)
    else: master_players = {}

    this_year = 2026
    last_year = 2025

    print(f"🚀 Starting SAFE Master Sync (Dictionaries Only)...")

    for league_id in TOP_LEAGUE_IDS:
        season = this_year if league_id in [253, 262, 71, 128, 239, 307, 98, 188, 292, 254, 531, 11, 13, 16, 528] else last_year
        print(f"\n--- League ID: {league_id} (Season {season}) ---")
        
        standings_data = fetch_data(f"standings?league={league_id}&season={season}")
        team_ids_in_league = []
        
        if standings_data and standings_data.get("response"):
            try:
                standings_list = standings_data["response"][0]["league"].get("standings", [])
                if standings_list:
                    for row in standings_list[0]:
                        t_id = row['team']['id']
                        team_ids_in_league.append(t_id)
                        # Sync rank and record only
                        master_teams[f"{t_id}_{league_id}"] = {
                            "rank": row["rank"],
                            "record": f"{row['all']['win']}-{row['all']['draw']}-{row['all']['lose']}"
                        }
                print(f"✅ Standings synced.")
            except Exception:
                print(f"⚠️ Standings skip.")

        for t_id in team_ids_in_league:
            print(f"   Roster: Team {t_id}...")
            page = 1
            while True:
                player_data = fetch_data(f"players?team={t_id}&season={season}&page={page}")
                if not player_data or not player_data.get("response"):
                    break
                for entry in player_data["response"]:
                    master_players[str(entry["player"]["id"])] = entry
                if page >= player_data.get("paging", {}).get("total", 1):
                    break
                page += 1

    with open(TEAM_DICT_PATH, 'w') as f: json.dump(master_teams, f, indent=4)
    with open(PLAYER_DICT_PATH, 'w') as f: json.dump(master_players, f, indent=4)
    print("\n✅ Master Dictionaries updated. Ready for Scraper to use.")

if __name__ == "__main__":
    if not API_KEY:
        print("❌ Error: API Key not found.")
    else:
        sync_all_leagues()

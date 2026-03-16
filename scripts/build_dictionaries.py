import json
import os
import urllib.request
import time
from datetime import datetime, timedelta, timezone

# --- CONFIGURATION ---
API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ.get("FOOTBALL_API_KEY")
DATA_DIR = "data"
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
            # Basic rate limit safety (30 calls per minute fallback)
            time.sleep(0.5) 
            return data
    except Exception as e:
        print(f"Error fetching {endpoint}: {e}")
        return None

def sync_all_leagues():
    master_teams = {}
    master_players = {}
    current_season = 2025 # Adjust if API reports 2024 for certain leagues

    print(f"🚀 Starting Master Sync for {len(TOP_LEAGUE_IDS)} leagues...")

    for league_id in TOP_LEAGUE_IDS:
        print(f"\n--- Processing League ID: {league_id} ---")
        
        # 1. Sync Standings & Team Logos
        standings_data = fetch_data(f"standings?league={league_id}&season={current_season}")
        team_ids_in_league = []
        
        if standings_data and standings_data.get("response"):
            try:
                standings_list = standings_data["response"][0]["league"].get("standings", [])
                if standings_list:
                    for row in standings_list[0]:
                        t_id = row['team']['id']
                        team_ids_in_league.append(t_id)
                        
                        # Save Rich Team Data
                        master_teams[f"{t_id}_{league_id}"] = {
                            "rank": row["rank"],
                            "record": f"{row['all']['win']}-{row['all']['draw']}-{row['all']['lose']}",
                            "points": row.get("points"),
                            "goalsDiff": row.get("goalsDiff"),
                            "form": row.get("form"),
                            "logo": row['team'].get('logo')
                        }
                print(f"✅ Standings synced. Found {len(team_ids_in_league)} teams.")
            except Exception as e:
                print(f"⚠️ League {league_id} standings skip (likely cup format).")

        # 2. Sync Full Rosters (The Heavy Lifter)
        for t_id in team_ids_in_league:
            print(f"   Fetching Roster: Team {t_id}...")
            page = 1
            while True:
                player_data = fetch_data(f"players?team={t_id}&season={current_season}&page={page}")
                if not player_data or not player_data.get("response"):
                    break
                
                for entry in player_data["response"]:
                    p_id = str(entry["player"]["id"])
                    master_players[p_id] = entry
                
                if page >= player_data.get("paging", {}).get("total", 1):
                    break
                page += 1

    # Save Master Dictionaries
    with open(TEAM_DICT_PATH, 'w') as f:
        json.dump(master_teams, f, indent=4)
    with open(PLAYER_DICT_PATH, 'w') as f:
        json.dump(master_players, f, indent=4)
    
    print("\n✅ Master Dictionaries saved successfully.")

def sync_future_schedules():
    print("\n🚀 Building Future 30-Day Schedule...")
    now = datetime.now(timezone.utc)
    
    for i in range(31):
        target_date = (now + timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"   Processing {target_date}...")
        
        data = fetch_data(f"fixtures?date={target_date}&timezone=America/New_York")
        if data and data.get("response"):
            # Filter for our 41 leagues
            filtered = [g for g in data["response"] if g['league']['id'] in TOP_LEAGUE_IDS]
            
            # Simple format for daily files
            daily_games = []
            for game in filtered:
                daily_games.append({
                    "fixture": game['fixture'],
                    "league": game['league'],
                    "teams": {"home": game['teams']['home'], "away": game['teams']['away']},
                    "goals": game['goals'],
                    "homeLineup": None, "awayLineup": None,
                    "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
                    "injuries": {"home": [], "away": []},
                    "events": [], "post_game_sync": False
                })
            
            with open(os.path.join(DATA_DIR, f"games_{target_date}.json"), 'w') as f:
                json.dump(daily_games, f, indent=4)

if __name__ == "__main__":
    if not API_KEY:
        print("❌ Error: FOOTBALL_API_KEY environment variable not set.")
    else:
        sync_all_leagues()
        sync_future_schedules()

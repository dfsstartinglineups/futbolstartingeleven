import os
import json
import urllib.request
import time
from datetime import datetime

# Grab the secret key from your environment
API_KEY = os.environ.get("FOOTBALL_API_KEY")
API_HOST = "https://v3.football.api-sports.io"

# The expanded global league list
TOP_LEAGUE_IDS = [
    39, 40, 45, 140, 135, 78, 61, 72, 94,  # Europe
    2, 3, 13,                          # Continental
    253, 262, 71, 128,                 # Americas
    307, 98                            # World
] 

def fetch_data(endpoint):
    req = urllib.request.Request(f"{API_HOST}/{endpoint}")
    req.add_header("x-apisports-key", API_KEY)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Failed to fetch {endpoint}: {e}")
        return None

def get_current_season(league_id, current_date):
    # MLS, Brazil, Argentina, Japan run Spring-to-Fall (Season = Current Year)
    if league_id in [253, 71, 128, 98]:
        return current_date.year
    # Europe, Liga MX, Saudi run Fall-to-Spring (Season = Year - 1 if before July)
    else:
        return current_date.year - 1 if current_date.month < 7 else current_date.year

def main():
    if not API_KEY:
        print("CRITICAL ERROR: FOOTBALL_API_KEY environment variable not set.")
        return

    os.makedirs("data", exist_ok=True)
    dict_filepath = "data/player_stats_dict.json"
    tracker_filepath = "data/completed_leagues.json"
    
    now = datetime.now()

    # Load existing player dictionary if we are resuming
    player_dict = {}
    if os.path.exists(dict_filepath):
        with open(dict_filepath, "r") as f:
            try:
                player_dict = json.load(f)
            except Exception:
                pass

    # Load the tracker so we don't repeat leagues we already paid for
    completed_leagues = []
    if os.path.exists(tracker_filepath):
        with open(tracker_filepath, "r") as f:
            try:
                completed_leagues = json.load(f)
            except Exception:
                pass

    print(f"--- Starting Player Stats Harvester ---")
    print(f"Currently have {len(player_dict)} players saved.\n")

    for league_id in TOP_LEAGUE_IDS:
        if league_id in completed_leagues:
            print(f"[League {league_id}] Already completed. Skipping...")
            continue

        season = get_current_season(league_id, now)
        print(f"[League {league_id} - Season {season}] Starting fetch...")
        
        page = 1
        total_pages = 1
        
        while page <= total_pages:
            print(f"  -> Fetching page {page}/{total_pages}...")
            # We use the /players endpoint to get the bio AND the season stats
            data = fetch_data(f"players?league={league_id}&season={season}&page={page}")
            
            if not data or "response" not in data or len(data["response"]) == 0:
                print("  -> No more data found for this league.")
                break
                
            total_pages = data.get("paging", {}).get("total", 1)
            
            for item in data["response"]:
                # Grab the FULL payload for the player and their stats
                player_data = item.get("player", {})
                stats_data = item.get("statistics", [])
                
                p_id = str(player_data.get("id"))
                
                # Save absolutely everything to the backend dictionary
                if p_id and p_id != "None":
                    player_dict[p_id] = {
                        "player": player_data,
                        "statistics": stats_data
                    }
                
            page += 1
            # Tiny sleep between pages to respect 10 req/sec limits
            time.sleep(0.5)

        # League is completely finished! Save progress immediately.
        with open(dict_filepath, "w") as f:
            json.dump(player_dict, f, indent=4)
            
        completed_leagues.append(league_id)
        with open(tracker_filepath, "w") as f:
            json.dump(completed_leagues, f)
            
        print(f"[League {league_id}] Finished and saved! Total players in DB: {len(player_dict)}")
        
        # The 60-Second Cooldown between leagues
        print("Sleeping for 60 seconds to respect API minute-limits...\n")
        time.sleep(60)

    print("✅ HARVEST COMPLETE! All leagues have been processed.")

if __name__ == "__main__":
    main()

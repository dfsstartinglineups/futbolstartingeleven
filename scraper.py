import os
import json
import urllib.request
from datetime import datetime

# Grab the secret key from GitHub Actions
API_KEY = os.environ.get("FOOTBALL_API_KEY")
API_HOST = "https://v3.football.api-sports.io"

# The leagues we want to fetch
TOP_LEAGUE_IDS = [39, 140, 135, 78, 61, 2, 253] # EPL, La Liga, Serie A, Bundes, Ligue 1, UCL, MLS

def fetch_data(endpoint):
    req = urllib.request.Request(f"{API_HOST}/{endpoint}")
    req.add_header("x-apisports-key", API_KEY)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"Failed to fetch {endpoint}: {e}")
        return None

def process_date(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    print(f"\n--- Fetching fixtures for {date_str} ---")
    
    fixtures_data = fetch_data(f"fixtures?date={date_str}")
    if not fixtures_data or "response" not in fixtures_data:
        print("No fixtures found or API error.")
        return

    # Filter for our top leagues
    matches = [m for m in fixtures_data["response"] if m["league"]["id"] in TOP_LEAGUE_IDS]
    
    all_game_data = []
    
    for match in matches:
        fixture_id = match["fixture"]["id"]
        print(f"Fetching lineups for fixture {fixture_id} ({match['teams']['home']['name']} vs {match['teams']['away']['name']})...")
        
        lineups_data = fetch_data(f"fixtures/lineups?fixture={fixture_id}")
        
        home_lineup = None
        away_lineup = None
        
        if lineups_data and "response" in lineups_data and len(lineups_data["response"]) == 2:
            home_lineup = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["home"]["id"]), None)
            away_lineup = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["away"]["id"]), None)

        all_game_data.append({
            "fixture": match["fixture"],
            "league": match["league"],
            "teams": match["teams"],
            "goals": match["goals"],
            "homeLineup": home_lineup,
            "awayLineup": away_lineup
        })

    # Save to a local JSON file designated by date
    os.makedirs("data", exist_ok=True)
    with open(f"data/games_{date_str}.json", "w") as f:
        json.dump(all_game_data, f)
    
    print(f"Data successfully saved to data/games_{date_str}.json")

def main():
    if not API_KEY:
        print("CRITICAL ERROR: FOOTBALL_API_KEY environment variable not set.")
        return

    # Only scrape TODAY to save API credits and build historical files organically
    today = datetime.now()
    dates_to_fetch = [today] 
    
    for d in dates_to_fetch:
        process_date(d)

if __name__ == "__main__":
    main()

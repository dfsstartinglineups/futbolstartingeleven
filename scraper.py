import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta

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
    filepath = f"data/games_{date_str}.json"
    
    print(f"\n--- Fetching live fixtures & scores for {date_str} ---")
    
    # 1. Fetch the master schedule to get live scores and time elapsed
    fixtures_data = fetch_data(f"fixtures?date={date_str}&timezone=America/New_York")
    
    if not fixtures_data or "response" not in fixtures_data:
        print("No fixtures found or API error.")
        return

    # Filter for our top leagues
    matches = [m for m in fixtures_data["response"] if m["league"]["id"] in TOP_LEAGUE_IDS]
    
    # 2. Load existing local data (The "Memory")
    existing_data = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            try:
                loaded = json.load(f)
                for game in loaded:
                    existing_data[game["fixture"]["id"]] = game
            except Exception:
                pass

    all_game_data = []
    now_utc = datetime.now(timezone.utc)
    
    for match in matches:
        fixture_id = match["fixture"]["id"]
        
        # Check our memory to see if we already have the lineups
        existing_game = existing_data.get(fixture_id, {})
        home_lineup = existing_game.get("homeLineup")
        away_lineup = existing_game.get("awayLineup")
        
        # Parse the kickoff time (API-Football returns ISO format)
        try:
            game_time_str = match['fixture']['date']
            if game_time_str.endswith('Z'):
                game_time_str = game_time_str[:-1] + '+00:00'
            game_time = datetime.fromisoformat(game_time_str)
        except Exception as e:
            print(f"Error parsing date {match['fixture']['date']}: {e}")
            game_time = now_utc + timedelta(days=1) # Default to future if error
            
        # 3. The Smart Logic Checks
        needs_lineups = not home_lineup or not away_lineup
        within_window = now_utc >= (game_time - timedelta(minutes=60))
        valid_status = match["fixture"]["status"]["short"] not in ['PST', 'CANC', 'ABD']
        
        # If we need them, we are within an hour of kickoff, and game isn't canceled
        if needs_lineups and within_window and valid_status:
            print(f"[{match['teams']['home']['name']} vs {match['teams']['away']['name']}] within 60 mins. Fetching lineups...")
            lineups_data = fetch_data(f"fixtures/lineups?fixture={fixture_id}")
            
            if lineups_data and "response" in lineups_data and len(lineups_data["response"]) == 2:
                home_lineup = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["home"]["id"]), None)
                away_lineup = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["away"]["id"]), None)
                if home_lineup and away_lineup:
                    print(f"✅ Lineups successfully locked in for {fixture_id}!")
            else:
                print(f"Lineups not yet available for {fixture_id}.")
                
        all_game_data.append({
            "fixture": match["fixture"],
            "league": match["league"],
            "teams": match["teams"],
            "goals": match["goals"],
            "homeLineup": home_lineup,
            "awayLineup": away_lineup
        })

    # Save everything back to the file
    os.makedirs("data", exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(all_game_data, f, indent=4)
    
    print(f"Data successfully saved to {filepath}")

def main():
    if not API_KEY:
        print("CRITICAL ERROR: FOOTBALL_API_KEY environment variable not set.")
        return

    # Only scrape TODAY
    today = datetime.now()
    dates_to_fetch = [today] 
    
    for d in dates_to_fetch:
        process_date(d)

if __name__ == "__main__":
    main()

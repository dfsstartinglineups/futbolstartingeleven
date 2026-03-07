import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta

# Grab the secret key from GitHub Actions
API_KEY = os.environ.get("FOOTBALL_API_KEY")
API_HOST = "https://v3.football.api-sports.io"

# The expanded global league list (17 Leagues)
TOP_LEAGUE_IDS = [
    39, 40, 140, 135, 78, 61, 72, 94,  # Europe (EPL, Championship, La Liga, Serie A, Bundes, Ligue 1, Eredivisie, Portugal)
    2, 13,                             # Continental (UCL, Copa Libertadores)
    253, 262, 71, 128,                 # Americas (MLS, Liga MX, Brazil, Argentina)
    307, 98, 292                       # World (Saudi Pro League, J1 League, K League 1)
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

def process_date(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    filepath = f"data/games_{date_str}.json"
    
    print(f"\n--- Fetching live fixtures & scores for {date_str} ---")
    
    # 1. Fetch the master schedule
    fixtures_data = fetch_data(f"fixtures?date={date_str}&timezone=America/New_York")
    
    if not fixtures_data or "response" not in fixtures_data:
        print("No fixtures found or API error.")
        return

    matches = [m for m in fixtures_data["response"] if m["league"]["id"] in TOP_LEAGUE_IDS]
    
    # 2. Fetch the Odds for the day (Bet365 is bookmaker id 8)
    print(f"--- Fetching Odds for {date_str} ---")
    odds_dict = {}
    odds_res = fetch_data(f"odds?date={date_str}&bookmaker=8")
    
    if odds_res and "response" in odds_res:
        for odd_item in odds_res["response"]:
            fix_id = odd_item["fixture"]["id"]
            # Default odds structure
            match_odds = {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "2.5", "over": "TBD", "under": "TBD"}
            
            if odd_item.get("bookmakers"):
                bets = odd_item["bookmakers"][0].get("bets", [])
                for bet in bets:
                    # Bet ID 1 is Match Winner (Home/Draw/Away)
                    if bet["id"] == 1: 
                        for v in bet["values"]:
                            # Keep exact decimal odds format
                            if v["value"] == "Home": match_odds["home"] = str(v["odd"])
                            if v["value"] == "Draw": match_odds["draw"] = str(v["odd"])
                            if v["value"] == "Away": match_odds["away"] = str(v["odd"])
                    # Bet ID 5 is Goals Over/Under
                    elif bet["id"] == 5: 
                        for v in bet["values"]:
                            # Target the standard 2.5 goals line
                            if "Over 2.5" in str(v["value"]):
                                match_odds["over"] = str(v["odd"])
                            elif "Under 2.5" in str(v["value"]):
                                match_odds["under"] = str(v["odd"])
            
            odds_dict[fix_id] = match_odds

    # 3. Load existing local data (The "Memory")
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
        
        existing_game = existing_data.get(fixture_id, {})
        home_lineup = existing_game.get("homeLineup")
        away_lineup = existing_game.get("awayLineup")
        
        try:
            game_time_str = match['fixture']['date']
            if game_time_str.endswith('Z'):
                game_time_str = game_time_str[:-1] + '+00:00'
            game_time = datetime.fromisoformat(game_time_str)
        except Exception as e:
            game_time = now_utc + timedelta(days=1)
            
        needs_lineups = not home_lineup or not away_lineup
        within_window = now_utc >= (game_time - timedelta(minutes=60))
        valid_status = match["fixture"]["status"]["short"] not in ['PST', 'CANC', 'ABD']
        
        if needs_lineups and within_window and valid_status:
            print(f"[{match['teams']['home']['name']} vs {match['teams']['away']['name']}] within 60 mins. Fetching lineups...")
            lineups_data = fetch_data(f"fixtures/lineups?fixture={fixture_id}")
            
            if lineups_data and "response" in lineups_data and len(lineups_data["response"]) == 2:
                home_lineup = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["home"]["id"]), None)
                away_lineup = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["away"]["id"]), None)
                
        # Retrieve the odds we parsed earlier for this specific game
        game_odds = odds_dict.get(fixture_id, {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"})
                
        all_game_data.append({
            "fixture": match["fixture"],
            "league": match["league"],
            "teams": match["teams"],
            "goals": match["goals"],
            "homeLineup": home_lineup,
            "awayLineup": away_lineup,
            "odds": game_odds # Append the odds object to the final JSON
        })

    os.makedirs("data", exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(all_game_data, f, indent=4)
    
    print(f"Data successfully saved to {filepath}")

def main():
    if not API_KEY:
        print("CRITICAL ERROR: FOOTBALL_API_KEY environment variable not set.")
        return

    today = datetime.now()
    dates_to_fetch = [today] 
    
    for d in dates_to_fetch:
        process_date(d)

if __name__ == "__main__":
    main()

import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta

# Grab the secret key from GitHub Actions
API_KEY = os.environ.get("FOOTBALL_API_KEY")
API_HOST = "https://v3.football.api-sports.io"

# The expanded global league list (16 Leagues - K-League 292 dropped)
TOP_LEAGUE_IDS = [
    39, 40, 140, 135, 78, 61, 72, 94,  # Europe
    2, 13,                             # Continental
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

def process_date(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    filepath = f"data/games_{date_str}.json"
    
    print(f"\n--- Fetching live fixtures & scores for {date_str} ---")
    
    # 1. Fetch the master schedule
    fixtures_data = fetch_data(f"fixtures?date={date_str}&timezone=America/New_York")
    
    if not fixtures_data or "response" not in fixtures_data:
        print("No fixtures found or API error.")
        return

    # Filter down to just our 16 leagues
    matches = [m for m in fixtures_data["response"] if m["league"]["id"] in TOP_LEAGUE_IDS]

    # --- 2. LOAD MEMORY FIRST ---
    existing_data = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            try:
                loaded = json.load(f)
                for game in loaded:
                    existing_data[game["fixture"]["id"]] = game
            except Exception:
                pass

    # --- 3. ONLY FETCH ODDS IF A LEAGUE HAS "TBD" GAMES ---
    leagues_needing_odds = set()
    for match in matches:
        fixture_id = match["fixture"]["id"]
        league_id = match["league"]["id"]
        season = match["league"]["season"] 
        
        # Look at this specific game in our memory
        existing_game = existing_data.get(fixture_id, {})
        existing_odds = existing_game.get("odds", {"home": "TBD"})
        
        # If even ONE game in this league is missing odds, we add the league to our fetch list
        if existing_odds.get("home") == "TBD":
            leagues_needing_odds.add((league_id, season))

    print(f"--- Found {len(leagues_needing_odds)} leagues that still need odds. ---")
    odds_dict = {}
    
    for league_id, season in leagues_needing_odds:
        page = 1
        total_pages = 1
        
        while page <= total_pages:
            odds_res = fetch_data(f"odds?league={league_id}&season={season}&date={date_str}&bookmaker=8&page={page}")
            
            if not odds_res or "response" not in odds_res:
                break
                
            for odd_item in odds_res["response"]:
                fix_id = odd_item["fixture"]["id"]
                match_odds = {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"}
                
                if odd_item.get("bookmakers"):
                    bets = odd_item["bookmakers"][0].get("bets", [])
                    for bet in bets:
                        if bet["id"] == 1: 
                            for v in bet["values"]:
                                if v["value"] == "Home": match_odds["home"] = str(v["odd"])
                                if v["value"] == "Draw": match_odds["draw"] = str(v["odd"])
                                if v["value"] == "Away": match_odds["away"] = str(v["odd"])
                        elif bet["id"] == 5: 
                            for v in bet["values"]:
                                if "Over 2.5" in str(v["value"]):
                                    match_odds["over"] = str(v["odd"])
                                    match_odds["total"] = "2.5"
                                elif "Under 2.5" in str(v["value"]):
                                    match_odds["under"] = str(v["odd"])
                                    match_odds["total"] = "2.5"
                
                odds_dict[fix_id] = match_odds
                
            total_pages = odds_res.get("paging", {}).get("total", 1)
            page += 1

    # --- 4. MAP DATA AND FETCH LINEUPS ---
    all_game_data = []
    now_utc = datetime.now(timezone.utc)
    
    for match in matches:
        fixture_id = match["fixture"]["id"]
        
        existing_game = existing_data.get(fixture_id, {})
        home_lineup = existing_game.get("homeLineup")
        away_lineup = existing_game.get("awayLineup")
        
        # Grab the odds we just fetched for this specific fixture, or fallback to memory
        game_odds = odds_dict.get(fixture_id, existing_game.get("odds", {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"}))
        
        try:
            game_time_str = match['fixture']['date']
            if game_time_str.endswith('Z'):
                game_time_str = game_time_str[:-1] + '+00:00'
            game_time = datetime.fromisoformat(game_time_str)
        except Exception as e:
            game_time = now_utc + timedelta(days=1)
            
        needs_lineups = not home_lineup or not away_lineup
        within_window = now_utc >= (game_time - timedelta(minutes=60))
        
        # Stop fetching if the game is postponed, canceled, finished, or reached Halftime
        stop_statuses = ['PST', 'CANC', 'ABD', 'HT', 'FT', 'AET', 'PEN']
        valid_status = match["fixture"]["status"]["short"] not in stop_statuses
        
        if needs_lineups and within_window and valid_status:
            print(f"[{match['teams']['home']['name']} vs {match['teams']['away']['name']}] Fetching lineups...")
            lineups_data = fetch_data(f"fixtures/lineups?fixture={fixture_id}")
            
            if lineups_data and "response" in lineups_data:
                # Grab whatever we can find. If only one team's lineup is available, save it!
                new_home = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["home"]["id"]), None)
                new_away = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["away"]["id"]), None)
                
                if new_home: home_lineup = new_home
                if new_away: away_lineup = new_away
                
        all_game_data.append({
            "fixture": match["fixture"],
            "league": match["league"],
            "teams": match["teams"],
            "goals": match["goals"],
            "homeLineup": home_lineup,
            "awayLineup": away_lineup,
            "odds": game_odds 
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

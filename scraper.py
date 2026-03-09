import os
import json
import urllib.request
import zoneinfo
from datetime import datetime, timezone, timedelta

# Grab the secret key from GitHub Actions
API_KEY = os.environ.get("FOOTBALL_API_KEY")
API_HOST = "https://v3.football.api-sports.io"
DATA_DIR = "data"

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# --- LOAD MASTER PLAYER DICTIONARY ---
MASTER_PLAYER_DICT = {}
dict_filepath = os.path.join(DATA_DIR, "player_stats_dict.json")
if os.path.exists(dict_filepath):
    try:
        with open(dict_filepath, "r") as f:
            MASTER_PLAYER_DICT = json.load(f)
        print(f"Loaded Master Player Dictionary ({len(MASTER_PLAYER_DICT)} players).")
    except Exception as e:
        print(f"Warning: Could not load player dictionary: {e}")

# The expanded global league list (16 Leagues)
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

def fetch_fixtures_by_date(date_str):
    return fetch_data(f"fixtures?date={date_str}")

def fetch_lineups(fixture_id):
    return fetch_data(f"fixtures/lineups?fixture={fixture_id}")

def fetch_injuries(fixture_id):
    return fetch_data(f"injuries?fixture={fixture_id}")

# --- NEW: FETCH EVENTS FUNCTION ---
def fetch_events(fixture_id):
    return fetch_data(f"fixtures/events?fixture={fixture_id}")

# --- INJECTION FUNCTION ---
def inject_player_stats(lineups):
    """Enriches lineup data with photos and season stats from the master dictionary."""
    if not MASTER_PLAYER_DICT:
        return lineups 
    
    for team_lineup in lineups:
        # 1. Inject into Starting XI
        for starter in team_lineup.get("startXI", []):
            player_info = starter.get("player", {})
            p_id = str(player_info.get("id"))
            
            if p_id in MASTER_PLAYER_DICT:
                cached_data = MASTER_PLAYER_DICT[p_id]
                player_bio = cached_data.get("player", {})
                stats_list = cached_data.get("statistics", [])
                primary_stats = stats_list[0] if len(stats_list) > 0 else {}
                
                player_info["photo"] = player_bio.get("photo")
                player_info["age"] = player_bio.get("age")
                player_info["nationality"] = player_bio.get("nationality")
                
                player_info["season_stats"] = {
                    "games": primary_stats.get("games", {}).get("appearences", 0) or 0,
                    "goals": primary_stats.get("goals", {}).get("total", 0) or 0,
                    "assists": primary_stats.get("goals", {}).get("assists", 0) or 0,
                    "yellow_cards": primary_stats.get("cards", {}).get("yellow", 0) or 0,
                    "red_cards": primary_stats.get("cards", {}).get("red", 0) or 0,
                    "rating": primary_stats.get("games", {}).get("rating") or "N/A"
                }

        # 2. Inject into Substitutes (Bench)
        for sub in team_lineup.get("substitutes", []):
            player_info = sub.get("player", {})
            p_id = str(player_info.get("id"))
            
            if p_id in MASTER_PLAYER_DICT:
                cached_data = MASTER_PLAYER_DICT[p_id]
                player_bio = cached_data.get("player", {})
                stats_list = cached_data.get("statistics", [])
                primary_stats = stats_list[0] if len(stats_list) > 0 else {}
                
                player_info["photo"] = player_bio.get("photo")
                player_info["age"] = player_bio.get("age")
                player_info["nationality"] = player_bio.get("nationality")
                
                player_info["season_stats"] = {
                    "games": primary_stats.get("games", {}).get("appearences", 0) or 0,
                    "goals": primary_stats.get("goals", {}).get("total", 0) or 0,
                    "assists": primary_stats.get("goals", {}).get("assists", 0) or 0,
                    "yellow_cards": primary_stats.get("cards", {}).get("yellow", 0) or 0,
                    "red_cards": primary_stats.get("cards", {}).get("red", 0) or 0,
                    "rating": primary_stats.get("games", {}).get("rating") or "N/A"
                }
                
    return lineups

def build_daily_games(date_str):
    print(f"\n--- Building Initial Board for {date_str} ---")
    fixtures_data = fetch_fixtures_by_date(date_str)
    
    if not fixtures_data or not fixtures_data.get("response"):
        print("No fixtures found or API error.")
        return []

    all_games = fixtures_data["response"]
    premium_games = [g for g in all_games if g['league']['id'] in TOP_LEAGUE_IDS]
    
    formatted_games = []
    
    for game in premium_games:
        fixture_id = game['fixture']['id']
        status_short = game['fixture']['status']['short']
        
        game_entry = {
            "fixture": game['fixture'],
            "league": game['league'],
            "teams": {
                "home": {**game['teams']['home'], "rank": None, "record": None},
                "away": {**game['teams']['away'], "rank": None, "record": None}
            },
            "goals": game['goals'],
            "homeLineup": None,
            "awayLineup": None,
            "lineup_checks": 0,  
            "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
            "last_odds_check": None,
            "injuries": {"home": [], "away": [], "fetched": False},
            "events": []
        }

        # Check time to Kickoff
        kickoff_time = datetime.fromisoformat(game['fixture']['date'])
        now = datetime.now(timezone.utc)
        time_to_kickoff_minutes = (kickoff_time - now).total_seconds() / 60

        if status_short not in ['FT', 'AET', 'PEN', 'CANC', 'PST']:
            # Checkpoint 1: Initial 60-minute pull if script runs late in the day
            if time_to_kickoff_minutes <= 60 and game_entry['lineup_checks'] == 0:
                print(f"[{fixture_id}] Match is within 60 mins. Fetching initial lineups...")
                lineups_data = fetch_lineups(fixture_id)
                if lineups_data and lineups_data.get("response"):
                    enriched_lineups = inject_player_stats(lineups_data["response"])
                    if len(enriched_lineups) >= 2:
                        game_entry['homeLineup'] = enriched_lineups[0]
                        game_entry['awayLineup'] = enriched_lineups[1]
                        game_entry['lineup_checks'] = 1  
                        print(f"[{fixture_id}] Lineups & Stats Injected (Check 1/3)!")
                        
            # Injuries check
            if time_to_kickoff_minutes <= (24 * 60) and not game_entry['injuries']['fetched']:
                print(f"[{fixture_id}] Fetching injuries...")
                inj_data = fetch_injuries(fixture_id)
                if inj_data and inj_data.get("response"):
                    for injury in inj_data["response"]:
                        player_name = injury["player"]["name"]
                        team_id = injury["team"]["id"]
                        if team_id == game_entry["teams"]["home"]["id"]:
                            game_entry["injuries"]["home"].append(player_name)
                        elif team_id == game_entry["teams"]["away"]["id"]:
                            game_entry["injuries"]["away"].append(player_name)
                game_entry['injuries']['fetched'] = True
                
        formatted_games.append(game_entry)

    return formatted_games

def process_date(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    games_file = os.path.join(DATA_DIR, f"games_{date_str}.json")

    if not os.path.exists(games_file):
        daily_games = build_daily_games(date_str)
        with open(games_file, 'w') as f:
            json.dump(daily_games, f, indent=4)
        print(f"Created initial {games_file}")
    else:
        print(f"\n--- Updating Live Board for {date_str} ---")
        with open(games_file, 'r') as f:
            daily_games = json.load(f)

        current_fixtures_data = fetch_fixtures_by_date(date_str)
        if not current_fixtures_data or not current_fixtures_data.get("response"):
            return
            
        current_fixtures_map = {g['fixture']['id']: g for g in current_fixtures_data["response"]}
        updated = False
        
        for game in daily_games:
            fixture_id = game['fixture']['id']
            status_short = game['fixture']['status']['short']
            
            if status_short in ['FT', 'AET', 'PEN', 'CANC', 'PST']:
                continue
                
            latest_data = current_fixtures_map.get(fixture_id)
            if not latest_data:
                continue
                
            latest_status = latest_data['fixture']['status']['short']
            
            # --- NEW: FETCH LIVE EVENTS IF GAME IS ACTIVE ---
            if latest_status in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT']:
                game['fixture']['status'] = latest_data['fixture']['status']
                game['goals'] = latest_data['goals']
                
                print(f"[{fixture_id}] Match is live. Fetching events...")
                events_data = fetch_events(fixture_id)
                if events_data and events_data.get("response"):
                    # We map only the specific fields the frontend needs to keep the JSON light
                    cleaned_events = []
                    for ev in events_data["response"]:
                        if ev["type"] in ["Goal", "Card"]: # We only care about Goals and Cards
                            cleaned_events.append({
                                "time": ev["time"]["elapsed"],
                                "team_id": ev["team"]["id"],
                                "player": ev["player"]["name"],
                                "type": ev["type"],
                                "detail": ev["detail"]
                            })
                    game["events"] = cleaned_events
                
                updated = True
                
            # Lineup Verification System
            kickoff_time = datetime.fromisoformat(game['fixture']['date'])
            now = datetime.now(timezone.utc)
            time_to_kickoff_minutes = (kickoff_time - now).total_seconds() / 60
            
            checks = game.get("lineup_checks", 0)
            needs_initial_pull = (time_to_kickoff_minutes <= 60 and checks == 0)
            needs_15m_verify   = (time_to_kickoff_minutes <= 15 and checks == 1)
            needs_5m_verify    = (time_to_kickoff_minutes <= 5  and checks == 2)

            if latest_status == 'NS' and (needs_initial_pull or needs_15m_verify or needs_5m_verify):
                print(f"[{fixture_id}] Reaching lineup checkpoint ({checks + 1}/3). Fetching...")
                lineups_data = fetch_lineups(fixture_id)
                
                if lineups_data and lineups_data.get("response"):
                    enriched_lineups = inject_player_stats(lineups_data["response"])
                    if len(enriched_lineups) >= 2:
                        game['homeLineup'] = enriched_lineups[0]
                        game['awayLineup'] = enriched_lineups[1]
                        game['lineup_checks'] = checks + 1  
                        updated = True
                        print(f"[{fixture_id}] Lineups & Stats Injected (Check {checks + 1}/3)!")

        if updated:
            with open(games_file, 'w') as f:
                json.dump(daily_games, f, indent=4)
            print(f"Daily JSON for {date_str} updated successfully.")
        else:
            print(f"No live updates needed for {date_str}.")

def prepopulate_future_days(days_ahead=30):
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    for i in range(1, days_ahead + 1):
        future_date = now_est + timedelta(days=i)
        date_str = future_date.strftime("%Y-%m-%d")
        future_filepath = os.path.join(DATA_DIR, f"games_{date_str}.json")
        
        if not os.path.exists(future_filepath):
            print(f"Pre-populating board for {date_str}...")
            fixtures_data = fetch_fixtures_by_date(date_str)
            
            if fixtures_data and fixtures_data.get("response"):
                all_games = fixtures_data["response"]
                premium_games = [g for g in all_games if g['league']['id'] in TOP_LEAGUE_IDS]
                
                future_game_data = []
                for match in premium_games:
                    future_game_data.append({
                        "fixture": match["fixture"],
                        "league": match["league"],
                        "teams": {
                            "home": {**match["teams"]["home"], "rank": None, "record": None},
                            "away": {**match["teams"]["away"], "rank": None, "record": None}
                        },
                        "goals": match["goals"],
                        "homeLineup": None,
                        "awayLineup": None,
                        "lineup_checks": 0,  
                        "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
                        "last_odds_check": None,
                        "injuries": {"home": [], "away": [], "fetched": False},
                        "events": []
                    })
                with open(future_filepath, "w") as f:
                    json.dump(future_game_data, f, indent=4)


def main():
    if not API_KEY:
        print("CRITICAL ERROR: FOOTBALL_API_KEY environment variable not set.")
        return

    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    
    # Run the prepopulator to ensure the rolling 30-day calendar exists
    prepopulate_future_days(30)

    dates_to_process = [now_est]

    # Late Night Rule
    if now_est.hour < 6:
        dates_to_process.insert(0, now_est - timedelta(days=1))

    for target_date in dates_to_process:
        process_date(target_date)

if __name__ == "__main__":
    main()

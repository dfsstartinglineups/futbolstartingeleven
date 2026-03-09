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

# --- LOAD MASTER DICTIONARIES ---
MASTER_PLAYER_DICT = {}
PLAYER_DICT_PATH = os.path.join(DATA_DIR, "player_stats_dict.json")
if os.path.exists(PLAYER_DICT_PATH):
    try:
        with open(PLAYER_DICT_PATH, "r") as f:
            MASTER_PLAYER_DICT = json.load(f)
        print(f"Loaded Master Player Dictionary ({len(MASTER_PLAYER_DICT)} players).")
    except Exception as e:
        print(f"Warning: Could not load player dictionary: {e}")

MASTER_TEAM_DICT = {}
TEAM_DICT_PATH = os.path.join(DATA_DIR, "team_stats_dict.json")
if os.path.exists(TEAM_DICT_PATH):
    try:
        with open(TEAM_DICT_PATH, "r") as f:
            MASTER_TEAM_DICT = json.load(f)
        print(f"Loaded Master Team Dictionary ({len(MASTER_TEAM_DICT)} teams).")
    except Exception as e:
        pass

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
    # Forcing API into EST/EDT to prevent midnight UTC day-crossover bugs
    return fetch_data(f"fixtures?date={date_str}&timezone=America/New_York")

def fetch_lineups(fixture_id):
    return fetch_data(f"fixtures/lineups?fixture={fixture_id}")

def fetch_injuries(fixture_id):
    return fetch_data(f"injuries?fixture={fixture_id}")

def fetch_events(fixture_id):
    return fetch_data(f"fixtures/events?fixture={fixture_id}")

def fetch_all_players(team_id, season):
    """Handles API pagination to get an entire roster's season stats."""
    all_players = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        data = fetch_data(f"players?team={team_id}&season={season}&page={page}")
        if not data or not data.get("response"):
            break
        all_players.extend(data["response"])
        total_pages = data.get("paging", {}).get("total", 1)
        page += 1
    return all_players

# --- INJECTION FUNCTION ---
def inject_player_stats(lineups):
    if not MASTER_PLAYER_DICT:
        return lineups 
    
    for team_lineup in lineups:
        for section in ["startXI", "substitutes"]:
            for slot in team_lineup.get(section, []):
                player_info = slot.get("player", {})
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
        
        home_id = str(game['teams']['home']['id'])
        away_id = str(game['teams']['away']['id'])
        
        home_rank = MASTER_TEAM_DICT.get(home_id, {}).get("rank", None)
        home_record = MASTER_TEAM_DICT.get(home_id, {}).get("record", None)
        away_rank = MASTER_TEAM_DICT.get(away_id, {}).get("rank", None)
        away_record = MASTER_TEAM_DICT.get(away_id, {}).get("record", None)
        
        game_entry = {
            "fixture": game['fixture'],
            "league": game['league'],
            "teams": {
                "home": {**game['teams']['home'], "rank": home_rank, "record": home_record},
                "away": {**game['teams']['away'], "rank": away_rank, "record": away_record}
            },
            "goals": game['goals'],
            "homeLineup": None,
            "awayLineup": None,
            "lineup_checks": 0,  
            "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
            "last_odds_check": None,
            "injuries": {"home": [], "away": [], "checks": 0}, # NEW INJURY TRACKER
            "events": [],
            "match_ended_at": None,
            "post_game_sync": False
        }
                
        formatted_games.append(game_entry)

    return formatted_games

def process_date(target_date):
    # Safety Check: Never process historical files (allows yesterday for late games)
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    if target_date.date() < (now_est.date() - timedelta(days=1)):
        return

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
            
            latest_data = current_fixtures_map.get(fixture_id)
            if not latest_data:
                continue
                
            latest_status = latest_data['fixture']['status']['short']
            
            # --- 1. FETCH LIVE EVENTS (Goals & Cards) ---
            if latest_status in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT']:
                game['fixture']['status'] = latest_data['fixture']['status']
                game['goals'] = latest_data['goals']
                
                events_data = fetch_events(fixture_id)
                if events_data and events_data.get("response"):
                    cleaned_events = []
                    for ev in events_data["response"]:
                        if ev["type"] in ["Goal", "Card"]: 
                            cleaned_events.append({
                                "time": ev["time"]["elapsed"],
                                "team_id": ev["team"]["id"],
                                "player": ev["player"]["name"],
                                "type": ev["type"],
                                "detail": ev["detail"]
                            })
                    game["events"] = cleaned_events
                updated = True

            # --- 2. MARK END TIME ONCE FINISHED ---
            is_finished = latest_status in ['FT', 'AET', 'PEN']
            if is_finished:
                game['fixture']['status'] = latest_data['fixture']['status']
                game['goals'] = latest_data['goals']
                
                if not game.get("match_ended_at"):
                    print(f"[{fixture_id}] Match just finished! Starting 90-min cooldown timer.")
                    game["match_ended_at"] = datetime.now(timezone.utc).isoformat()
                    updated = True
                
            kickoff_time = datetime.fromisoformat(game['fixture']['date'])
            now = datetime.now(timezone.utc)
            time_to_kickoff_minutes = (kickoff_time - now).total_seconds() / 60

            # --- 3. INJURY VERIFICATION SYSTEM (7 Checkpoints) ---
            if latest_status == 'NS':
                INJURY_THRESHOLDS = [1440, 1080, 720, 360, 60, 15, 5]
                inj_checks = game.get("injuries", {}).get("checks", 0)
                
                # Backwards compatibility if updating from the old JSON structure
                if inj_checks == 0 and game.get("injuries", {}).get("fetched") is True:
                    inj_checks = 1 

                # Find the target check level based on current time countdown
                target_check_level = 0
                for threshold in INJURY_THRESHOLDS:
                    if time_to_kickoff_minutes <= threshold:
                        target_check_level += 1
                    else:
                        break # Break early since thresholds are descending

                # If the target level is higher than our current checks, we owe the system an update
                if inj_checks < target_check_level:
                    print(f"[{fixture_id}] Reaching Injury Checkpoint {target_check_level}/7. Fetching injuries...")
                    inj_data = fetch_injuries(fixture_id)
                    
                    game["injuries"]["home"] = []
                    game["injuries"]["away"] = []
                    
                    if inj_data and inj_data.get("response"):
                        for injury in inj_data["response"]:
                            player_name = injury["player"]["name"]
                            team_id = injury["team"]["id"]
                            if team_id == game["teams"]["home"]["id"]:
                                game["injuries"]["home"].append(player_name)
                            elif team_id == game["teams"]["away"]["id"]:
                                game["injuries"]["away"].append(player_name)
                    
                    game["injuries"]["checks"] = target_check_level
                    game["injuries"].pop("fetched", None) # Clean up old key if it exists
                    updated = True

            # --- 4. LINEUP VERIFICATION SYSTEM (Aggressive Polling) ---
            checks = game.get("lineup_checks", 0)
            needs_lineup_pull = False
            
            if latest_status == 'NS':
                if time_to_kickoff_minutes <= 60 and checks == 0:
                    needs_lineup_pull = True
                elif time_to_kickoff_minutes <= 15 and checks == 1:
                    needs_lineup_pull = True
                elif time_to_kickoff_minutes <= 5 and checks == 2:
                    needs_lineup_pull = True

            if needs_lineup_pull:
                print(f"[{fixture_id}] Polling for lineups (Target Check {checks + 1}/3)...")
                lineups_data = fetch_lineups(fixture_id)
                
                # ONLY increment the counter if the API returns the actual lineups
                # If it's empty, `checks` stays the same and it will poll again next minute!
                if lineups_data and lineups_data.get("response") and len(lineups_data["response"]) >= 2:
                    enriched_lineups = inject_player_stats(lineups_data["response"])
                    game['homeLineup'] = enriched_lineups[0]
                    game['awayLineup'] = enriched_lineups[1]
                    
                    game['lineup_checks'] = checks + 1  
                    updated = True
                    print(f"[{fixture_id}] SUCCESS! Lineups acquired and injected (Check {checks + 1}/3 completed).")
                else:
                    print(f"[{fixture_id}] Lineups not released yet. Will retry next minute.")

            # --- 5. POST-GAME GRAND SYNC (Canary Check + DB Update) ---
            needs_sync = not game.get("post_game_sync", False)
            if is_finished and needs_sync and game.get("match_ended_at"):
                ended_time = datetime.fromisoformat(game["match_ended_at"])
                
                # Check if 90 minutes have passed since final whistle
                if (now - ended_time).total_seconds() >= (90 * 60):
                    print(f"[{fixture_id}] Cooldown complete. Running Canary Check...")
                    
                    league_id = game['league']['id']
                    season = game['league']['season']
                    home_id = game['teams']['home']['id']
                    away_id = game['teams']['away']['id']
                    
                    old_record = game['teams']['home'].get('record') or '0-0-0'
                    old_games_played = sum(int(x) for x in old_record.split('-')) if old_record != '0-0-0' else 0
                    
                    standings_data = fetch_data(f"standings?league={league_id}&season={season}")
                    is_fresh = False
                    
                    if standings_data and standings_data.get("response"):
                        league_info = standings_data["response"][0]["league"]
                        if league_info.get("standings") and len(league_info["standings"]) > 0:
                            for row in league_info["standings"][0]:
                                t_id = str(row["team"]["id"])
                                MASTER_TEAM_DICT[t_id] = {
                                    "rank": row["rank"],
                                    "record": f"{row['all']['win']}-{row['all']['draw']}-{row['all']['lose']}"
                                }
                                if t_id == str(home_id) and row["all"]["played"] > old_games_played:
                                    is_fresh = True
                        else:
                            is_fresh = True # Cup tournament (no standings), assume fresh
                    else:
                        is_fresh = True # Fallback if API fails, prevents infinite stalling

                    if is_fresh:
                        print(f"[{fixture_id}] Canary ALIVE! Syncing entire rosters to Master Dictionary...")
                        
                        # Sync Teams
                        with open(TEAM_DICT_PATH, "w") as f:
                            json.dump(MASTER_TEAM_DICT, f, indent=4)
                            
                        # Sync Players (Pagination handled automatically per team)
                        for t_id in [home_id, away_id]:
                            roster_data = fetch_all_players(t_id, season)
                            for p_data in roster_data:
                                p_id = str(p_data["player"]["id"])
                                MASTER_PLAYER_DICT[p_id] = p_data
                        
                        with open(PLAYER_DICT_PATH, "w") as f:
                            json.dump(MASTER_PLAYER_DICT, f, indent=4)

                        game["post_game_sync"] = True
                        updated = True
                        print(f"[{fixture_id}] Grand Sync Complete!")
                    else:
                        print(f"[{fixture_id}] Canary DEAD (Data Stale). Will retry later.")

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
                    # Look up current records dynamically for future matches
                    home_id = str(match['teams']['home']['id'])
                    away_id = str(match['teams']['away']['id'])
                    home_rank = MASTER_TEAM_DICT.get(home_id, {}).get("rank", None)
                    home_rec = MASTER_TEAM_DICT.get(home_id, {}).get("record", None)
                    away_rank = MASTER_TEAM_DICT.get(away_id, {}).get("rank", None)
                    away_rec = MASTER_TEAM_DICT.get(away_id, {}).get("record", None)
                    
                    future_game_data.append({
                        "fixture": match["fixture"],
                        "league": match["league"],
                        "teams": {
                            "home": {**match["teams"]["home"], "rank": home_rank, "record": home_rec},
                            "away": {**match["teams"]["away"], "rank": away_rank, "record": away_rec}
                        },
                        "goals": match["goals"],
                        "homeLineup": None,
                        "awayLineup": None,
                        "lineup_checks": 0,  
                        "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
                        "last_odds_check": None,
                        "injuries": {"home": [], "away": [], "checks": 0}, # NEW INJURY TRACKER
                        "events": [],
                        "match_ended_at": None,
                        "post_game_sync": False
                    })
                with open(future_filepath, "w") as f:
                    json.dump(future_game_data, f, indent=4)
        else:
            # THE FILE EXISTS: Silently update the ranks & records if they changed!
            try:
                with open(future_filepath, 'r') as f:
                    future_games = json.load(f)
                
                changed = False
                for game in future_games:
                    home_id = str(game['teams']['home']['id'])
                    away_id = str(game['teams']['away']['id'])
                    
                    if home_id in MASTER_TEAM_DICT:
                        new_h_rank = MASTER_TEAM_DICT[home_id].get("rank")
                        new_h_rec = MASTER_TEAM_DICT[home_id].get("record")
                        if game['teams']['home'].get('rank') != new_h_rank or game['teams']['home'].get('record') != new_h_rec:
                            game['teams']['home']['rank'] = new_h_rank
                            game['teams']['home']['record'] = new_h_rec
                            changed = True
                            
                    if away_id in MASTER_TEAM_DICT:
                        new_a_rank = MASTER_TEAM_DICT[away_id].get("rank")
                        new_a_rec = MASTER_TEAM_DICT[away_id].get("record")
                        if game['teams']['away'].get('rank') != new_a_rank or game['teams']['away'].get('record') != new_a_rec:
                            game['teams']['away']['rank'] = new_a_rank
                            game['teams']['away']['record'] = new_a_rec
                            changed = True
                            
                if changed:
                    with open(future_filepath, 'w') as f:
                        json.dump(future_games, f, indent=4)
            except Exception as e:
                print(f"Error updating future file {date_str}: {e}")

def main():
    if not API_KEY:
        print("CRITICAL ERROR: FOOTBALL_API_KEY environment variable not set.")
        return

    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    
    # Run the prepopulator to ensure the rolling 30-day calendar exists and future ranks are synced
    prepopulate_future_days(30)

    dates_to_process = [now_est]

    # Extended Late Night Rule: Process yesterday's file up until NOON EST 
    # to guarantee 90-minute cooldowns finish for late West Coast / Liga MX games
    if now_est.hour < 12:
        dates_to_process.insert(0, now_est - timedelta(days=1))

    for target_date in dates_to_process:
        process_date(target_date)

if __name__ == "__main__":
    main()

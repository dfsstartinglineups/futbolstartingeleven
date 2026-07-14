import json
import os
import urllib.request
import zoneinfo
import re
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION ---
API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ.get("FOOTBALL_API_KEY")

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

TEAM_DICT_PATH = os.path.join(DATA_DIR, "master_teams.json")

# Load persistent dictionaries
def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f: return json.load(f)
    return {}

MASTER_TEAM_DICT = load_json(TEAM_DICT_PATH)
# =========================================================
# API-FOOTBALL LEAGUE ID MAPPING (41 LEAGUES)
# =========================================================
TOP_LEAGUE_IDS = [
    # --- EUROPE (Domestic Leagues) ---
    39,  # Premier League (England)
    40,  # Championship (England)
    140, # La Liga (Spain)
    135, # Serie A (Italy)
    78,  # Bundesliga (Germany)
    61,  # Ligue 1 (France)
    88,  # Eredivisie (Netherlands)
    94,  # Primeira Liga (Portugal)
    203, # Süper Lig (Turkey)
    144, # Pro League (Belgium)
    179, # Premiership (Scotland)
    119, # Superliga (Denmark)

    # --- AMERICAS (Domestic Leagues) ---
    253, # MLS (USA)
    262, # Liga MX (Mexico)
    71,  # Brasileirão (Brazil)
    128, # Liga Profesional (Argentina)
    239, # Primera A (Colombia)

    # --- WORLD (Domestic Leagues) ---
    307, # Saudi Pro League (Saudi Arabia)
    98,  # J1 League (Japan)
    188, # A-League (Australia)
    292, # K League 1 (South Korea)

    # --- CUPS & CONTINENTAL TOURNAMENTS ---
    2,   # UEFA Champions League
    3,   # UEFA Europa League
    848, # UEFA Conference League
    13,  # Copa Libertadores (CONMEBOL)
    11,  # Copa Sudamericana (CONMEBOL)
    16,  # CONCACAF Champions Cup
    528, # Leagues Cup (CONCACAF/MLS/LigaMX)
    45,  # FA Cup (England)
    48,  # EFL Cup / Carabao Cup (England)
    143, # Copa del Rey (Spain)
    137, # Coppa Italia (Italy)
    81,  # DFB-Pokal (Germany)

    # --- INTERNATIONAL (National Teams) ---
    1,   # FIFA World Cup
    4,   # UEFA Euro Championship
    9,   # Copa America
    5,   # UEFA Nations League
    531, # CONCACAF Nations League
    10,  # International Friendlies

    # --- WOMEN'S LEAGUES ---
    254  # NWSL (USA)
]

# =========================================================
# AGGREGATE SCORING ROUNDS
# =========================================================
AGGREGATE_ROUNDS = {
    2: ["round of 16", "quarter-finals", "semi-finals"], # UCL
    3: ["knockout round play-offs", "round of 16", "quarter-finals", "semi-finals"], # UEL
    848: ["knockout round play-offs", "round of 16", "quarter-finals", "semi-finals"], # UECL
    13: ["round of 16", "quarter-finals", "semi-finals"], # Libertadores
    11: ["play-offs", "round of 16", "quarter-finals", "semi-finals"], # Sudamericana
    16: ["round one", "round of 16", "quarter-finals", "semi-finals"], # CONCACAF Champions Cup
    48: ["semi-finals"], # EFL Cup
    143: ["semi-finals"], # Copa del Rey
    137: ["semi-finals"], # Coppa Italia
    262: ["quarter-finals", "semi-finals", "final"], # Liga MX Liguilla
    40: ["semi-finals"], # Championship Playoffs
    188: ["semi-finals"], # A-League Playoffs
    239: ["final"], # Colombia Primera A
    5: ["quarter-finals", "play-outs"], # UEFA Nations League
    531: ["quarter-finals"] # CONCACAF Nations League
}

def is_youth_team(home_name, away_name):
    """
    Regex filter to detect Youth National Teams (e.g. U17, U19, U21, U23).
    \b ensures it matches a whole word.
    """
    pattern = r'\bU-?\d{2}\b'
    if re.search(pattern, home_name, re.IGNORECASE) or re.search(pattern, away_name, re.IGNORECASE):
        return True
    return False

def fetch_data(endpoint):
    req = urllib.request.Request(f"{API_HOST}/{endpoint}")
    req.add_header("x-apisports-key", API_KEY)
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            
            # --- NEW: Catch hidden API-level errors (like Rate Limits) ---
            api_errors = data.get("errors")
            if api_errors:
                # API-Football errors can be formatted as a dict or a list
                if isinstance(api_errors, dict) and len(api_errors) > 0:
                    print(f"   🚨 API ERROR on {endpoint}: {api_errors}")
                elif isinstance(api_errors, list) and len(api_errors) > 0:
                    print(f"   🚨 API ERROR on {endpoint}: {api_errors}")
                    
            return data
    except Exception as e:
        print(f"Failed to fetch {endpoint}: {e}")
        return None

def fetch_fixtures_by_date(date_str):
    return fetch_data(f"fixtures?date={date_str}&timezone=America/New_York")

def fetch_lineups(fixture_id):
    return fetch_data(f"fixtures/lineups?fixture={fixture_id}")

def fetch_injuries(fixture_id):
    return fetch_data(f"injuries?fixture={fixture_id}")

def fetch_odds(fixture_id):
    """Fetches Match Winner and Over/Under odds for a fixture."""
    data = fetch_data(f"odds?fixture={fixture_id}")
    if not data or not data.get("response"):
        return None
    
    odds_result = {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"}
    
    try:
        bookmakers = data["response"][0].get("bookmakers", [])
        if not bookmakers: return None
            
        found_mw = False
        found_ou = False
        
        # Loop through ALL bookmakers instead of just bookmakers[0]
        for bookmaker in bookmakers:
            for bet in bookmaker.get("bets", []):
                
                # Check Match Winner
                if bet["name"] == "Match Winner" and not found_mw:
                    for val in bet["values"]:
                        if val["value"] == "Home": odds_result["home"] = val["odd"]
                        elif val["value"] == "Draw": odds_result["draw"] = val["odd"]
                        elif val["value"] == "Away": odds_result["away"] = val["odd"]
                    found_mw = True
            
                # Check Over/Under (using multiple valid names just to be safe)
                elif bet["name"] in ["Goals Over/Under", "Over/Under"] and not found_ou:
                    ou_pairs = {}
                    for val in bet["values"]:
                        parts = str(val["value"]).split(" ")
                        if len(parts) == 2:
                            side = parts[0].lower() # "over" or "under"
                            total = parts[1]        # "2.5", "3.5", etc.
                            if total not in ou_pairs:
                                ou_pairs[total] = {}
                            try:
                                ou_pairs[total][side] = float(val["odd"])
                            except ValueError:
                                pass
                                
                    best_total = None
                    min_diff = float('inf')
                    
                    for total, odds in ou_pairs.items():
                        if "over" in odds and "under" in odds:
                            diff = abs(odds["over"] - odds["under"])
                            if diff < min_diff:
                                min_diff = diff
                                best_total = total
                                
                    if best_total:
                        odds_result["total"] = best_total
                        odds_result["over"] = str(ou_pairs[best_total]["over"])
                        odds_result["under"] = str(ou_pairs[best_total]["under"])
                        found_ou = True
                        
            # If we successfully found both lines, stop looping to save processing time
            if found_mw and found_ou:
                break
                
    except (IndexError, KeyError):
        return None
        
    return odds_result

def fetch_events(fixture_id):
    return fetch_data(f"fixtures/events?fixture={fixture_id}")

def fetch_fixture_statistics(fixture_id):
    return fetch_data(f"fixtures/statistics?fixture={fixture_id}")

def fetch_fixture_players(fixture_id):
    return fetch_data(f"fixtures/players?fixture={fixture_id}")

def fetch_all_players(team_id, season):
    all_players = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        data = fetch_data(f"players?team={team_id}&season={season}&page={page}")
        if not data or not data.get("response"): break
        all_players.extend(data["response"])
        total_pages = data.get("paging", {}).get("total", 1)
        page += 1
    return all_players

def fetch_first_leg_score(league_id, season, current_round, home_id, away_id, current_timestamp):
    """
    Queries the H2H endpoint to find the 1st leg score between two teams.
    Returns a dictionary mapping Team IDs to their 1st leg goals.
    """
    h2h_endpoint = f"fixtures/headtohead?h2h={home_id}-{away_id}"
    data = fetch_data(h2h_endpoint)
    
    if not data or not data.get("response"): 
        return None

    matches = sorted(data["response"], key=lambda x: x["fixture"]["timestamp"], reverse=True)

    for match in matches:
        m_league = match.get("league", {})
        m_fixture = match.get("fixture", {})
        
        # Look for a finished match in the EXACT same league, season, AND round,
        # that happened BEFORE the current match.
        if (m_league.get("id") == league_id and 
            m_league.get("season") == season and 
            m_league.get("round") == current_round and
            m_fixture.get("timestamp", 0) < current_timestamp and
            m_fixture.get("status", {}).get("short") in ['FT', 'AET', 'PEN']):
            
            past_home_id = str(match["teams"]["home"]["id"])
            past_away_id = str(match["teams"]["away"]["id"])
            past_home_goals = match.get("goals", {}).get("home") or 0
            past_away_goals = match.get("goals", {}).get("away") or 0
            
            print(f"      -> 1st Leg Found! {past_home_id}:{past_home_goals} | {past_away_id}:{past_away_goals}")
            
            return {
                past_home_id: past_home_goals,
                past_away_id: past_away_goals
            }
                
    return None

    # Sort matches by date descending (newest first)
    matches = sorted(data["response"], key=lambda x: x["fixture"]["timestamp"], reverse=True)

    for match in matches:
        # Look for a finished match in the EXACT same league and season
        if (match["league"]["id"] == league_id and 
            match["league"]["season"] == season and 
            match["fixture"]["status"]["short"] in ['FT', 'AET', 'PEN']):
            
            # --- SAFETY PATCH: Protect against 'null' rounds crashing the bot ---
            round_info = str(match["league"].get("round", ""))
            
            # Verify it was the 1st leg
            if "1st Leg" in round_info:
                past_home_id = str(match["teams"]["home"]["id"])
                past_away_id = str(match["teams"]["away"]["id"])
                past_home_goals = match["goals"]["home"] or 0
                past_away_goals = match["goals"]["away"] or 0
                
                print(f"      -> 1st Leg Found! {past_home_id}:{past_home_goals} | {past_away_id}:{past_away_goals}")
                
                return {
                    past_home_id: past_home_goals,
                    past_away_id: past_away_goals
                }
                
    return None

def inject_player_stats(lineups, home_roster, away_roster):
    """Stateless JIT Injection: Calculates season stats from raw API roster arrays."""
    
    # 1. Build a temporary dictionary in memory for lightning-fast lookups
    temp_player_dict = {}
    for p in home_roster + away_roster:
        p_id = str(p.get("player", {}).get("id"))
        if p_id and p_id != "None":
            temp_player_dict[p_id] = p
            
    for team_lineup in lineups:
        for section in ["startXI", "substitutes"]:
            for slot in team_lineup.get(section, []):
                player_info = slot.get("player", {})
                p_id = str(player_info.get("id"))
                
                if p_id in temp_player_dict:
                    cached_data = temp_player_dict[p_id]
                    player_bio = cached_data.get("player", {})
                    stats_list = cached_data.get("statistics", [])
                    
                    # --- EXPANDED STATS TRACKING ---
                    total_games, total_goals, total_assists = 0, 0, 0
                    total_yellows, total_reds = 0, 0
                    total_saves, total_conceded = 0, 0
                    total_shots_on, total_key_passes = 0, 0
                    total_tackles, total_interceptions = 0, 0
                    
                    total_pass_acc_sum = 0
                    total_pass_acc_games = 0
                    
                    ratings = []
                    competitions = {}
                    
                    for stat in stats_list:
                        league_name = stat.get("league", {}).get("name", "Unknown")
                        c_games = stat.get("games", {}).get("appearences") or 0
                        
                        if c_games == 0: continue # Skip comps where they didn't play
                        
                        c_goals = stat.get("goals", {}).get("total") or 0
                        c_assists = stat.get("goals", {}).get("assists") or 0
                        c_saves = stat.get("goals", {}).get("saves") or 0
                        c_conceded = stat.get("goals", {}).get("conceded") or 0
                        c_shots_on = stat.get("shots", {}).get("on") or 0
                        c_key_passes = stat.get("passes", {}).get("key") or 0
                        
                        c_pass_acc_raw = stat.get("passes", {}).get("accuracy")
                        c_pass_acc = int(c_pass_acc_raw) if c_pass_acc_raw else 0
                        
                        c_tackles = stat.get("tackles", {}).get("total") or 0
                        c_interceptions = stat.get("tackles", {}).get("interceptions") or 0
                        
                        c_yellows = stat.get("cards", {}).get("yellow") or 0
                        c_reds = stat.get("cards", {}).get("red") or 0
                        c_rating = stat.get("games", {}).get("rating")
                        
                        total_games += c_games
                        total_goals += c_goals
                        total_assists += c_assists
                        total_saves += c_saves
                        total_conceded += c_conceded
                        total_shots_on += c_shots_on
                        total_key_passes += c_key_passes
                        total_tackles += c_tackles
                        total_interceptions += c_interceptions
                        
                        if c_pass_acc > 0:
                            total_pass_acc_sum += (c_pass_acc * c_games)
                            total_pass_acc_games += c_games
                        
                        if c_rating:
                            try: ratings.append(float(c_rating))
                            except ValueError: pass
                                
                        competitions[league_name] = {
                            "games": c_games, "goals": c_goals, "assists": c_assists,
                            "saves": c_saves, "conceded": c_conceded,
                            "shots_on": c_shots_on, "key_passes": c_key_passes,
                            "pass_acc": c_pass_acc, "tackles": c_tackles, "interceptions": c_interceptions,
                            "yellow_cards": c_yellows, "red_cards": c_reds,
                            "rating": f"{float(c_rating):.2f}" if c_rating else "N/A"
                        }
                            
                    avg_rating = f"{sum(ratings)/len(ratings):.2f}" if ratings else "N/A"
                    avg_pass_acc = round(total_pass_acc_sum / total_pass_acc_games) if total_pass_acc_games > 0 else 0
                    
                    player_info.update({"photo": player_bio.get("photo"), "age": player_bio.get("age"), "nationality": player_bio.get("nationality")})
                    
                    player_info["season_stats"] = {
                        "total": {
                            "games": total_games, "goals": total_goals, "assists": total_assists,
                            "saves": total_saves, "conceded": total_conceded,
                            "shots_on": total_shots_on, "key_passes": total_key_passes,
                            "pass_acc": avg_pass_acc, "tackles": total_tackles, "interceptions": total_interceptions,
                            "yellow_cards": total_yellows, "red_cards": total_reds, "rating": avg_rating
                        },
                        "competitions": competitions
                    }
                    
    return lineups

def update_future_files_for_league(league_id, start_date_str):
    """Updates rank/record for a specific league in all future daily JSON files."""
    league_id_str = str(league_id)
    
    for filename in os.listdir(DATA_DIR):
        if filename.startswith("games_") and filename.endswith(".json"):
            file_date_str = filename.replace("games_", "").replace(".json", "")
            
            # Process files strictly AFTER the date of the match that just finished
            if file_date_str > start_date_str:
                filepath = os.path.join(DATA_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        day_games = json.load(f)
                    
                    file_updated = False
                    for g in day_games:
                        if str(g.get("league", {}).get("id")) == league_id_str:
                            for side in ['home', 'away']:
                                t_id = str(g['teams'][side]['id'])
                                t_data = MASTER_TEAM_DICT.get(f"{t_id}_{league_id_str}")
                                
                                if t_data and t_data.get("rank"):
                                    if g['teams'][side].get("rank") != t_data["rank"] or g['teams'][side].get("record") != t_data["record"]:
                                        g['teams'][side]['rank'] = t_data["rank"]
                                        g['teams'][side]['record'] = t_data["record"]
                                        file_updated = True
                                        
                    if file_updated:
                        with open(filepath, 'w') as f:
                            json.dump(day_games, f, indent=4)
                except Exception as e:
                    print(f"Error updating future file {filename}: {e}")

def migrate_game_if_needed(game, current_file_date_str):
    """
    Checks if a game belongs in a different daily JSON file based on its true EST date.
    If it does, it injects the game into the correct file and returns True.
    """
    try:
        # Calculate the true EST date of the kickoff
        kickoff = datetime.fromisoformat(game['fixture']['date']).astimezone(zoneinfo.ZoneInfo("America/New_York"))
        true_date_str = kickoff.strftime("%Y-%m-%d")
    except Exception:
        return False # If date is missing or malformed, do nothing
        
    if true_date_str != current_file_date_str:
        print(f"[{game['fixture']['id']}] Timezone/Reschedule mismatch. Moving from {current_file_date_str} to {true_date_str}...")
        
        new_file_path = os.path.join(DATA_DIR, f"games_{true_date_str}.json")
        
        # 1. Safely load the target file
        if os.path.exists(new_file_path):
            try:
                with open(new_file_path, 'r') as f:
                    target_games = json.load(f)
            except Exception:
                target_games = []
        else:
            target_games = []
            
        # 2. Inject the game (if it isn't already in there)
        if not any(str(g.get('fixture', {}).get('id')) == str(game['fixture']['id']) for g in target_games):
            target_games.append(game)
            with open(new_file_path, 'w') as f:
                json.dump(target_games, f, indent=4)
                
        # 3. Return True to signal the main loop to delete this game
        return True 
        
    return False

def build_daily_games(date_str):
    print(f"\n--- Building Initial Board for {date_str} ---")
    fixtures_data = fetch_fixtures_by_date(date_str)
    if not fixtures_data or not fixtures_data.get("response"): return []

    formatted_games = []
    for game in [g for g in fixtures_data["response"] if g['league']['id'] in TOP_LEAGUE_IDS]:
        home_name = game['teams']['home']['name']
        away_name = game['teams']['away']['name']
        
        # Skip this iteration if it's a youth match!
        if is_youth_team(home_name, away_name):
            continue
        home_id, away_id, league_id_str = str(game['teams']['home']['id']), str(game['teams']['away']['id']), str(game['league']['id'])
        
        # --- FIX: STRICT LEAGUE MATCHING ONLY (No domestic fallback!) ---
        home_data = MASTER_TEAM_DICT.get(f"{home_id}_{league_id_str}", {})
        away_data = MASTER_TEAM_DICT.get(f"{away_id}_{league_id_str}", {})
        
        # --- AGGREGATE SCORE DETECTOR ---
        first_leg_goals = None
        league_id = game['league']['id']
        round_info = str(game.get('league', {}).get('round', ''))
        
        if league_id in AGGREGATE_ROUNDS and any(r.lower() in round_info.lower() for r in AGGREGATE_ROUNDS[league_id]):
            print(f"      -> Checking for 1st Leg data: {home_name} vs {away_name} ({round_info})...")
            first_leg_goals = fetch_first_leg_score(league_id, game['league']['season'], round_info, home_id, away_id, game['fixture']['timestamp'])
        
        formatted_games.append({
            "fixture": game['fixture'], "league": game['league'],
            "teams": {
                "home": {**game['teams']['home'], "rank": home_data.get("rank"), "record": home_data.get("record")},
                "away": {**game['teams']['away'], "rank": away_data.get("rank"), "record": away_data.get("record")}
            },
            "goals": game['goals'], "homeLineup": None, "awayLineup": None, "lineup_checks": 0,  
            "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
            "last_odds_check": None, "injuries": {"home": [], "away": [], "checks": 0},
            "events": [], "match_ended_at": None, "post_game_sync": False,
            "first_leg_goals": first_leg_goals # Safely holds the 1st leg dict (or None)
        })
    return formatted_games

def process_date(target_date, force_master_sync=False):
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    if target_date.date() < (now_est.date() - timedelta(days=1)): return

    date_str = target_date.strftime("%Y-%m-%d")
    games_file = os.path.join(DATA_DIR, f"games_{date_str}.json")

    if not os.path.exists(games_file):
        daily_games = build_daily_games(date_str)
        with open(games_file, 'w') as f: json.dump(daily_games, f, indent=4)
    else:
        with open(games_file, 'r') as f: daily_games = json.load(f)

        # -------------------------------------------------------------
        # THE EFFICIENCY CHECK: Are all games completely finished and synced?
        # If yes, we don't need to make any API calls for this day!
        # -------------------------------------------------------------
        if isinstance(daily_games, list):
            if len(daily_games) == 0:
                # print(f"[{date_str}] No games scheduled. Skipping API call.")
                return # Hibernate immediately on empty days
            if all(game.get("post_game_sync") for game in daily_games):
                # print(f"[{date_str}] All games fully synced. Skipping API call.")
                return # Hibernate when all games are fully synced
            
        now = datetime.now(timezone.utc)
        updated = False
        
        # -------------------------------------------------------------
        # THE DEEP SLEEP CHECK: Do we need the live master schedule?
        # Only if a game is live, or kicking off in the next 75 minutes.
        # -------------------------------------------------------------
        needs_live_board = not bool(daily_games) or force_master_sync  # NEW LOGIC
        for g in daily_games:
            status = g.get('fixture', {}).get('status', {}).get('short', '')
            if status not in ['FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD']:
                kickoff = datetime.fromisoformat(g['fixture']['date'])
                mins_to_kickoff = (kickoff - now).total_seconds() / 60
                if status != 'NS' or mins_to_kickoff <= 75:
                    needs_live_board = True
                    break

        current_fixtures_map = {}
        if needs_live_board:
            print(f"\n--- Fetching Live Master Board for {date_str} ---")
            fixtures_data = fetch_fixtures_by_date(date_str)
            if fixtures_data and fixtures_data.get("response"):
                current_fixtures_map = {g['fixture']['id']: g for g in fixtures_data["response"]}

                # --- NEW SCHEDULE ADDITION CHECK ---
                existing_fixture_ids = {g['fixture']['id'] for g in daily_games}
                new_games_to_add = [
                    g for g in fixtures_data["response"] 
                    if g['league']['id'] in TOP_LEAGUE_IDS 
                    and g['fixture']['id'] not in existing_fixture_ids
                    and not is_youth_team(g['teams']['home']['name'], g['teams']['away']['name'])
                ]
                
                if new_games_to_add:
                    print(f"[{date_str}] Found {len(new_games_to_add)} newly scheduled games. Injecting...")
                    for game in new_games_to_add:
                        home_id, away_id, league_id_str = str(game['teams']['home']['id']), str(game['teams']['away']['id']), str(game['league']['id'])
                        home_data = MASTER_TEAM_DICT.get(f"{home_id}_{league_id_str}") or MASTER_TEAM_DICT.get(home_id, {})
                        away_data = MASTER_TEAM_DICT.get(f"{away_id}_{league_id_str}") or MASTER_TEAM_DICT.get(away_id, {})
                        
                        # --- AGGREGATE SCORE DETECTOR (Late Additions) ---
                        first_leg_goals = None
                        league_id = game['league']['id']
                        round_info = str(game.get('league', {}).get('round', ''))
                        
                        if league_id in AGGREGATE_ROUNDS and any(r.lower() in round_info.lower() for r in AGGREGATE_ROUNDS[league_id]):
                            h_name = game['teams']['home']['name']
                            a_name = game['teams']['away']['name']
                            print(f"      -> Late Checking 1st Leg: {h_name} vs {a_name} ({round_info})...")
                            first_leg_goals = fetch_first_leg_score(league_id, game['league']['season'], round_info, home_id, away_id, game['fixture']['timestamp'])
                        
                        daily_games.append({
                            "fixture": game['fixture'], "league": game['league'],
                            "teams": {
                                "home": {**game['teams']['home'], "rank": home_data.get("rank"), "record": home_data.get("record")},
                                "away": {**game['teams']['away'], "rank": away_data.get("rank"), "record": away_data.get("record")}
                            },
                            "goals": game['goals'], "homeLineup": None, "awayLineup": None, "lineup_checks": 0,  
                            "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
                            "last_odds_check": None, "injuries": {"home": [], "away": [], "checks": 0},
                            "events": [], "match_ended_at": None, "post_game_sync": False,
                            "first_leg_goals": first_leg_goals # Safely holds the 1st leg dict (or None)
                        })
                    updated = True
        else:
            # Print is optional, just confirms it is working
            # print(f"[{date_str}] Pre-Game Deep Sleep. Next kickoff is > 75 mins away. Skipping Master Board API.")
            pass
        games_to_remove = []
        
        for game in daily_games:
            fixture_id = game['fixture']['id']
            league_id_str = str(game['league']['id'])
            
           # --- 🔄 DYNAMIC RANK & RECORD SYNC (Pre-Game JIT Healing) ---
            if not hasattr(process_date, "checked_leagues"): process_date.checked_leagues = set()

            for side in ['home', 'away']:
                team = game['teams'][side]
                t_key = f"{team['id']}_{league_id_str}"
                
                curr_rank = team.get('rank')
                curr_rec = team.get('record')
                
                t_data = MASTER_TEAM_DICT.get(t_key, {})
                mast_rank = t_data.get('rank')
                mast_rec = t_data.get('record')
                
                # 1. TRIGGER: Check for bad data in current file OR missing League-Specific Master data
                bad_flags = ["null", "none"]
                curr_bad = (curr_rank is None or str(curr_rank).lower() == "null" or curr_rec is None or any(b in str(curr_rec).lower() for b in bad_flags))
                mast_bad = (mast_rank is None or str(mast_rank).lower() == "null" or mast_rec is None or any(b in str(mast_rec).lower() for b in bad_flags))
                
                if curr_bad or mast_bad:
                    if mast_bad and league_id_str not in process_date.checked_leagues:
                        print(f"[{fixture_id}] Missing specific League {league_id_str} data for {team['name']}. Fetching...")
                        process_date.checked_leagues.add(league_id_str)
                        
                        standings_data = fetch_data(f"standings?league={game['league']['id']}&season={game['league']['season']}")
                        
                        fetched_standings = False
                        if standings_data and standings_data.get("response"):
                            standings_list = standings_data["response"][0]["league"].get("standings", [])
                            if standings_list and len(standings_list) > 0:
                                fetched_standings = True
                                
                                # A. Update Master Dict (Safely avoiding unplayed future phases!)
                                for group in standings_list:
                                    for row in group:
                                        all_stats = row.get('all', {})
                                        w, d, l = all_stats.get('win'), all_stats.get('draw'), all_stats.get('lose')
                                        played = all_stats.get('played', 0)
                                        
                                        if w is None or d is None or l is None: continue
                                            
                                        row_t_key = f"{row['team']['id']}_{league_id_str}"
                                        existing_rec = MASTER_TEAM_DICT.get(row_t_key, {}).get("record", "")
                                        
                                        if played == 0 and existing_rec and existing_rec not in ["", "0-0-0"] and "none" not in existing_rec.lower():
                                            continue
                                            
                                        MASTER_TEAM_DICT[row_t_key] = {"rank": row.get("rank"), "record": f"{w}-{d}-{l}"}
                                        
                                with open(TEAM_DICT_PATH, "w") as f: json.dump(MASTER_TEAM_DICT, f, indent=4)
                                
                                # B. Sweep & Heal ALL of TODAY's games for this league
                                for g in daily_games:
                                    if str(g['league']['id']) == league_id_str:
                                        for s in ['home', 'away']:
                                            g_team = g['teams'][s]
                                            g_key = f"{g_team['id']}_{league_id_str}"
                                            g_data = MASTER_TEAM_DICT.get(g_key)
                                            if g_data and g_data.get('rank') is not None:
                                                g_team['rank'] = g_data.get('rank')
                                                g_team['record'] = g_data.get('record')
                                                updated = True
                                                
                                # C. Sweep & Heal ALL FUTURE games for this league
                                update_future_files_for_league(game['league']['id'], date_str)

                        # --- THE "CLEAN" CUP SAFEGUARD ---
                        # If it's a knockout cup (empty standings), save empty strings so UI stays clean and it doesn't fetch again!
                        if not fetched_standings:
                            MASTER_TEAM_DICT[t_key] = {"rank": "", "record": ""}
                            with open(TEAM_DICT_PATH, "w") as f: json.dump(MASTER_TEAM_DICT, f, indent=4)

                # 3. APPLY TO CURRENT TEAM (If Master Dict already had it, or we just fetched it)
                t_data = MASTER_TEAM_DICT.get(t_key, {})
                if t_data.get('rank') is not None and str(t_data.get('rank')).lower() != "null":
                    if team.get('rank') != t_data.get('rank') or team.get('record') != t_data.get('record'):
                        team['rank'] = t_data.get('rank')
                        team['record'] = t_data.get('record')
                        updated = True
            # ---------------------------------------------------------
            
            # Use live data if we woke up to fetch it, otherwise use our local memory
            if current_fixtures_map:
                if fixture_id in current_fixtures_map:
                    latest_data = current_fixtures_map[fixture_id]
                else:
                    # 🚨 THE VANISHING GAME CATCH 🚨
                    print(f"[{fixture_id}] Missing from daily schedule! Polling directly for status/time change...")
                    fallback = fetch_data(f"fixtures?id={fixture_id}")
                    if fallback and fallback.get("response"):
                        latest_data = fallback["response"][0]
                    else:
                        latest_data = {"fixture": game["fixture"], "goals": game["goals"]}
            else:
                latest_data = {"fixture": game["fixture"], "goals": game["goals"]}
                
            # --- 🕒 FIX: SYNC SCHEDULED KICKOFF TIMES ---
            # If the league moved the kickoff time (common in South America), update our local file
            latest_date = latest_data['fixture'].get('date')
            if latest_date and game['fixture'].get('date') != latest_date:
                print(f"[{fixture_id}] Kickoff time changed from {game['fixture'].get('date')} to {latest_date}. Updating...")
                game['fixture']['date'] = latest_date
                updated = True

            # --- 🚀 CALL OUR NEW MIGRATION METHOD ---
            if migrate_game_if_needed(game, date_str):
                games_to_remove.append(game)
                continue # Skip the rest of the loop for this game, it's gone!
                
            latest_status = latest_data['fixture']['status']['short']
            local_status = game.get('fixture', {}).get('status', {}).get('short', '')
            
            # --- 🛑 TIME TRAVEL BLOCKER ---
            # API load balancers often send stale payloads. Reject backward time travel,
            # UNLESS the official match status has changed (e.g. blowing the whistle caps time back to 90 or 120)
            new_elapsed = latest_data.get('fixture', {}).get('status', {}).get('elapsed') or 0
            old_elapsed = game.get('fixture', {}).get('status', {}).get('elapsed') or 0
            
            if new_elapsed < old_elapsed and latest_status == local_status:
                continue # Skip this game loop entirely. The API is lagging!
            
            
            # 1. LIVE EVENTS (Stripped down for the GM)
            is_active_half = latest_status in ['1H', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT']
            just_hit_ht = (latest_status == 'HT' and local_status != 'HT')
            just_ended = (latest_status in ['FT', 'AET', 'PEN'] and local_status not in ['FT', 'AET', 'PEN'])
            
            if is_active_half or just_hit_ht or just_ended:
                game['fixture']['status'], game['goals'] = latest_data['fixture']['status'], latest_data['goals']
                updated = True
                
            elif latest_status == 'HT':
                # The game is resting at halftime. Just sync the UI status.
                if game['fixture']['status'] != latest_data['fixture']['status']:
                    game['fixture']['status'] = latest_data['fixture']['status']
                    game['goals'] = latest_data['goals']
                    updated = True

            # 2. MATCH COMPLETION
            is_finished = latest_status in ['FT', 'AET', 'PEN']
            is_dead = latest_status in ['PST', 'CANC', 'ABD', 'AWD', 'WO'] # Postponed, Cancelled, Abandoned
            
            if is_finished:
                game['fixture']['status'], game['goals'] = latest_data['fixture']['status'], latest_data['goals']
                if not game.get("match_ended_at"):
                    game["match_ended_at"] = datetime.now(timezone.utc).isoformat()
                    updated = True
                    
            # If the game is postponed or cancelled, instantly mark it synced so we can hibernate
            elif is_dead and not game.get("post_game_sync"):
                game['fixture']['status'] = latest_data['fixture']['status']
                game["post_game_sync"] = True
                updated = True
                
            kickoff_time = datetime.fromisoformat(game['fixture']['date'])
            now = datetime.now(timezone.utc)
            time_to_kickoff_minutes = (kickoff_time - now).total_seconds() / 60

            # 3. PRE-GAME DATA (INJURIES & ODDS) - 7 Checkpoints
            if latest_status == 'NS':
                THRESHOLDS = [1440, 1080, 720, 360, 60, 15, 5]
                checks = game.get("injuries", {}).get("checks", 0)
                target_level = sum(1 for t in THRESHOLDS if time_to_kickoff_minutes <= t)

                if checks < target_level:
                    print(f"[{fixture_id}] Checkpoint {target_level}/7: Polling Injuries...")
                    inj_data = fetch_injuries(fixture_id)
                    game["injuries"]["home"], game["injuries"]["away"] = [], []
                    if inj_data and inj_data.get("response"):
                        for inj in inj_data["response"]:
                            team_key = "home" if inj["team"]["id"] == game["teams"]["home"]["id"] else "away"
                            game["injuries"][team_key].append(inj["player"]["name"])
                    
                    # --- OPTIMIZED ODDS POLLING LOGIC ---
                    needs_odds = False
                    
                    # 1. If we don't have odds yet, fetch them.
                    if game.get("odds", {}).get("home") == "TBD" or game.get("odds", {}).get("total") == "TBD":
                        needs_odds = True
                        
                    # 2. If we are within 60 mins and haven't done our final check, fetch them again.
                    elif time_to_kickoff_minutes <= 60 and not game.get("final_odds_check"):
                        needs_odds = True
                        game["final_odds_check"] = True  # Mark that we attempted the final check
                        
                    if needs_odds:
                        print(f"[{fixture_id}] Polling Odds...")
                        new_odds = fetch_odds(fixture_id)
                        if new_odds:
                            game["odds"] = new_odds
                            game["last_odds_check"] = now.isoformat()
                    # ------------------------------------
                    
                    game["injuries"]["checks"] = target_level
                    updated = True

            # 4. LINEUPS (Throttled Continuous Polling)
            has_full_lineup = bool(game.get('homeLineup') and game.get('homeLineup').get('startXI'))
            
            # Check our 5-Minute Cooldown Lock
            last_check_str = game.get("last_lineup_check")
            if last_check_str:
                try:
                    last_check_time = datetime.fromisoformat(last_check_str)
                except ValueError:
                    last_check_time = datetime.min.replace(tzinfo=timezone.utc)
            else:
                last_check_time = datetime.min.replace(tzinfo=timezone.utc)
                
            mins_since_last_check = (now - last_check_time).total_seconds() / 60
            
            # Late Scratch Checks
            needs_15m_refresh = (time_to_kickoff_minutes <= 15) and not game.get("refreshed_15m", False)
            needs_5m_refresh = (time_to_kickoff_minutes <= 5) and not game.get("refreshed_5m", False)
            
            # Keep checking from T-90 all the way until the game officially ends
            is_eligible_for_lineup = not is_finished and not is_dead and time_to_kickoff_minutes <= 90
            
            # ONLY fetch if we don't have it AND it's been 5+ mins since our last check (or a forced refresh)
            needs_lineup = is_eligible_for_lineup and (
                (not has_full_lineup and mins_since_last_check >= 5) or 
                needs_15m_refresh or 
                needs_5m_refresh
            )
            
            if needs_lineup:
                game["last_lineup_check"] = now.isoformat() # 🔒 Lock it for 5 minutes
                
                print(f"[{fixture_id}] Polling API for Lineups (T-{int(time_to_kickoff_minutes)} mins)...")
                lineups_data = fetch_lineups(fixture_id)

                # --- NEW: Dump the raw payload to the terminal ---
                print(f"   RAW API PAYLOAD: {lineups_data}")
                
                if lineups_data and lineups_data.get("response") and len(lineups_data["response"]) >= 2:
                    
                    # 1. Safely identify Home and Away (API does not guarantee array order!)
                    home_id = game["teams"]["home"]["id"]
                    raw_home = next((l for l in lineups_data["response"] if l.get("team", {}).get("id") == home_id), None)
                    raw_away = next((l for l in lineups_data["response"] if l.get("team", {}).get("id") != home_id), None)
                    
                    if raw_home and raw_away:
                        # 2. Use 'or []' to prevent crashes if the API temporarily sends null
                        h_start = raw_home.get("startXI") or []
                        a_start = raw_away.get("startXI") or []
                        
                        if len(h_start) > 0 and len(a_start) > 0:
                            print(f"   ✅ Lineup found at T-{int(time_to_kickoff_minutes)} mins!")
                            season = game['league']['season']
                            
                            # --- JIT ROSTER FETCH ---
                            print(f"   📥 Fetching JIT Season Rosters for {game['teams']['home']['name']} and {game['teams']['away']['name']}...")
                            home_roster_data = fetch_all_players(home_id, season)
                            away_roster_data = fetch_all_players(game["teams"]["away"]["id"], season)
                            
                            enriched = inject_player_stats([raw_home, raw_away], home_roster_data, away_roster_data)
                            game['homeLineup'], game['awayLineup'] = enriched[0], enriched[1]
                        else:
                            print(f"   ⚠️ API returned empty arrays. Ignoring glitch to protect memory.")
                else:
                    print(f"   ⏳ API-Football has not published the official match sheet yet. Retrying in 5 mins.")
                
                # Mark late refreshes as complete
                if time_to_kickoff_minutes <= 15: game["refreshed_15m"] = True
                if time_to_kickoff_minutes <= 5:  game["refreshed_5m"] = True
                
                updated = True
                
            # 5. POST-GAME SYNC (The Official Box Score Sweep)
            if is_finished and not game.get("post_game_sync") and game.get("match_ended_at"):
                # Wait 90 minutes (5400 seconds) for official corrections before sweeping
                if (now - datetime.fromisoformat(game["match_ended_at"])).total_seconds() >= 5400:
                    print(f"[{fixture_id}] 🧹 Running Final Official Box Score Sweep...")
                    
                    # A. Fetch Final Official Events
                    events_data = fetch_events(fixture_id)
                    parsed_events = []
                    if events_data and events_data.get("response"):
                        for ev in events_data["response"]:
                            if ev["type"] in ["Goal", "Card", "subst"]:
                                if ev["type"] == "Goal" and ev["detail"] == "Missed Penalty": continue
                                
                                elapsed_time = ev["time"]["elapsed"]
                                extra_time = ev["time"].get("extra")
                                display_time = f"{elapsed_time}+{extra_time}" if extra_time else str(elapsed_time)

                                event_obj = {
                                    "time": display_time,
                                    "team_id": ev["team"]["id"],
                                    "player": ev["player"]["name"] if ev.get("player") else None,
                                    "player_id": ev["player"]["id"] if ev.get("player") else None,
                                    "type": ev["type"],
                                    "detail": ev["detail"],
                                    "assist": ev["assist"]["name"] if ev.get("assist") else None
                                }
                                if ev["type"] == "subst":
                                    event_obj["player_out"] = ev["assist"]["name"] if ev.get("assist") else None
                                    event_obj["player_out_id"] = ev["assist"]["id"] if ev.get("assist") else None
                                    
                                parsed_events.append(event_obj)
                    game["events"] = parsed_events

                    # B. Fetch Final Official Team Stats
                    stats_data = fetch_fixture_statistics(fixture_id)
                    if stats_data and stats_data.get("response"):
                        team_stats = {"home": {}, "away": {}}
                        for t_stat in stats_data["response"]:
                            t_id = t_stat["team"]["id"]
                            side = "home" if t_id == game["teams"]["home"]["id"] else "away"
                            
                            parsed_t_stats = {
                                "possession": 50, "total_shots": 0, "shots_on_target": 0,
                                "corners": 0, "fouls": 0, "yellow_cards": 0, "red_cards": 0
                            }
                            
                            for s in t_stat["statistics"]:
                                val = s["value"]
                                if val is None: continue
                                
                                stype = s["type"]
                                if stype == "Ball Possession": parsed_t_stats["possession"] = int(str(val).replace('%', ''))
                                elif stype == "Total Shots": parsed_t_stats["total_shots"] = int(val)
                                elif stype == "Shots on Goal": parsed_t_stats["shots_on_target"] = int(val)
                                elif stype == "Corner Kicks": parsed_t_stats["corners"] = int(val)
                                elif stype == "Fouls": parsed_t_stats["fouls"] = int(val)
                                elif stype == "Yellow Cards": parsed_t_stats["yellow_cards"] = int(val)
                                elif stype == "Red Cards": parsed_t_stats["red_cards"] = int(val)
                                
                            team_stats[side] = parsed_t_stats
                        game["team_stats"] = team_stats

                    # C. Fetch Final Official Match Player Stats & Subs
                    if game.get("homeLineup") and game.get("awayLineup"):
                        live_players_data = fetch_fixture_players(fixture_id)
                        live_player_map = {}
                        
                        if live_players_data and live_players_data.get("response"):
                            for tp in live_players_data["response"]:
                                for p in tp["players"]:
                                    p_id = str(p["player"]["id"])
                                    p_stats = p["statistics"][0] if len(p["statistics"]) > 0 else {}
                                    
                                    live_player_map[p_id] = {
                                        # 🎯 NEW: Collect final minutes played
                                        "minutes": p_stats.get("games", {}).get("minutes") or 0,
                                        "goals": p_stats.get("goals", {}).get("total") or 0,
                                        "assists": p_stats.get("goals", {}).get("assists") or 0,
                                        "total_shots": p_stats.get("shots", {}).get("total") or 0,
                                        "shots_on_target": p_stats.get("shots", {}).get("on") or 0,
                                        "offsides": p_stats.get("offsides") or 0,
                                        "passes": p_stats.get("passes", {}).get("total") or 0,
                                        "key_passes": p_stats.get("passes", {}).get("key") or 0,
                                        "pass_acc": p_stats.get("passes", {}).get("accuracy") or 0,
                                        "tackles": p_stats.get("tackles", {}).get("total") or 0,
                                        "blocks": p_stats.get("tackles", {}).get("blocks") or 0,
                                        "interceptions": p_stats.get("tackles", {}).get("interceptions") or 0,
                                        "duels_total": p_stats.get("duels", {}).get("total") or 0,
                                        "duels_won": p_stats.get("duels", {}).get("won") or 0,
                                        "clearances": p_stats.get("tackles", {}).get("blocks") or 0,
                                        "saves": p_stats.get("goals", {}).get("saves") or 0,
                                        "conceded": p_stats.get("goals", {}).get("conceded") or 0,
                                        "yellow_cards": p_stats.get("cards", {}).get("yellow") or 0,
                                        "red_cards": p_stats.get("cards", {}).get("red") or 0,
                                        "fouls_drawn": p_stats.get("fouls", {}).get("drawn") or 0,
                                        "fouls_committed": p_stats.get("fouls", {}).get("committed") or 0,
                                        "rating": p_stats.get("games", {}).get("rating") or "N/A"
                                    }

                        # Process Substitutions Idempotently
                        for ev in parsed_events:
                            if ev["type"] == "subst":
                                player_in_id = str(ev["player_id"])
                                player_out_id = str(ev["player_out_id"])
                                
                                for side in ["homeLineup", "awayLineup"]:
                                    lineup = game[side]
                                    if not lineup: continue
                                    
                                    in_is_sub = any(str(s["player"]["id"]) == player_in_id for s in lineup.get("substitutes", []))
                                    out_is_sub = any(str(s["player"]["id"]) == player_out_id for s in lineup.get("substitutes", []))
                                    in_is_starter = any(str(s["player"]["id"]) == player_in_id for s in lineup.get("startXI", []))
                                    out_is_starter = any(str(s["player"]["id"]) == player_out_id for s in lineup.get("startXI", []))
                                    
                                    # API ERROR CORRECTION
                                    if in_is_starter and out_is_sub:
                                        try:
                                            starter_idx = next(i for i, s in enumerate(lineup["startXI"]) if str(s["player"]["id"]) == player_in_id)
                                            sub_idx = next(i for i, s in enumerate(lineup["substitutes"]) if str(s["player"]["id"]) == player_out_id)
                                            
                                            temp = lineup["startXI"][starter_idx]
                                            lineup["startXI"][starter_idx] = lineup["substitutes"][sub_idx]
                                            lineup["substitutes"][sub_idx] = temp
                                            
                                            in_is_sub, out_is_starter = True, True
                                        except StopIteration: pass
                                            
                                    if in_is_sub and out_is_starter:
                                        try:
                                            incoming_sub = next(s for s in lineup["substitutes"] if str(s["player"]["id"]) == player_in_id)
                                            
                                            for slot in lineup["startXI"]:
                                                if str(slot["player"]["id"]) == player_out_id:
                                                    if "sub_history" not in slot:
                                                        slot["sub_history"] = []
                                                        
                                                    slot["sub_history"].insert(0, slot["player"].copy())
                                                    
                                                    slot["player"] = incoming_sub["player"]
                                                    slot["player"]["isSubbedIn"] = True
                                                    slot["player"]["subMinute"] = ev["time"]
                                                    slot["player"]["pos"] = slot["sub_history"][0].get("pos", "M")
                                                    
                                                    lineup["substitutes"] = [s for s in lineup["substitutes"] if str(s["player"]["id"]) != player_in_id]
                                                    break
                                        except StopIteration: pass

                        # Attach Final Live Stats to Active Players, Subbed-Out Players, AND Bench
                        for side in ["homeLineup", "awayLineup"]:
                            lineup = game[side]
                            if not lineup: continue
                            
                            for slot in lineup.get("startXI", []):
                                p_id = str(slot["player"]["id"])
                                if p_id in live_player_map:
                                    slot["player"]["live_stats"] = live_player_map[p_id]
                                    
                                for sub_hist in slot.get("sub_history", []):
                                    h_id = str(sub_hist["id"])
                                    if h_id in live_player_map:
                                        sub_hist["live_stats"] = live_player_map[h_id]
                                        
                            for sub in lineup.get("substitutes", []):
                                p_id = str(sub["player"]["id"])
                                if p_id in live_player_map:
                                    sub["player"]["live_stats"] = live_player_map[p_id]

                    # D. Fetch Final Standings & Update Teams
                    standings_data = fetch_data(f"standings?league={game['league']['id']}&season={game['league']['season']}")
                    if standings_data and standings_data.get("response"):
                        try:
                            standings_list = standings_data["response"][0]["league"].get("standings", [])
                            if standings_list and len(standings_list) > 0:
                                for group in standings_list:
                                    for row in group:
                                        all_stats = row.get('all', {})
                                        w = all_stats.get('win')
                                        d = all_stats.get('draw')
                                        l = all_stats.get('lose')
                                        played = all_stats.get('played', 0)
                                        
                                        if w is None or d is None or l is None:
                                            continue
                                            
                                        row_t_key = f"{row['team']['id']}_{game['league']['id']}"
                                        existing_rec = MASTER_TEAM_DICT.get(row_t_key, {}).get("record", "")
                                        
                                        if played == 0 and existing_rec and existing_rec not in ["", "0-0-0"] and "none" not in existing_rec.lower():
                                            continue
                                            
                                        MASTER_TEAM_DICT[row_t_key] = {
                                            "rank": row.get("rank"), 
                                            "record": f"{w}-{d}-{l}"
                                        }
                                with open(TEAM_DICT_PATH, "w") as f: json.dump(MASTER_TEAM_DICT, f, indent=4)
                            
                            # Push the league-wide update to all FUTURE files
                            update_future_files_for_league(game['league']['id'], date_str)
                            
                        except Exception as e:
                            pass 
                    
                    

                    # F. MARK AS COMPLETE SO WE DON'T GET STUCK IN A LOOP
                    game["post_game_sync"] = True
                    updated = True

        # --- PURGE MIGRATED GAMES FROM THE CURRENT FILE ---
        if games_to_remove:
            for g in games_to_remove:
                if g in daily_games:
                    daily_games.remove(g)
            updated = True
        
        
        if updated:
            with open(games_file, 'w') as f: json.dump(daily_games, f, indent=4)

def main():
    if not API_KEY: return
    
    # Establish Current Time
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    
    # Start with Today's Date
    dates_to_process = [now_est]
    
    # MORNING RULE (Midnight to Noon): Check Yesterday (for late night west coast/international games that are finishing up)
    if now_est.hour < 12: 
        dates_to_process.insert(0, now_est - timedelta(days=1))
        
    # EVENING RULE (8:00 PM to Midnight): Check Tomorrow (for midnight or early AM kickoffs so we can pull pre-game lineups)
    if now_est.hour >= 20: 
        dates_to_process.append(now_est + timedelta(days=1))
        
    # --- THE ONCE-A-DAY TRIGGER ---
    # Look exactly 30 days into the future. 
    # If the JSON file for that day doesn't exist, a new day just started!
    day_30_date = now_est + timedelta(days=30)
    day_30_str = day_30_date.strftime("%Y-%m-%d")
    day_30_file = os.path.join(DATA_DIR, f"games_{day_30_str}.json")
    
    needs_daily_maintenance = not os.path.exists(day_30_file)

    if needs_daily_maintenance:
        print("\n🧹 --- NEW DAY DETECTED: RUNNING DAILY MAINTENANCE (SYNCING NEXT 30 DAYS) --- 🧹")

        # --- NEW: AGGREGATE SCORE SWEEP ---
        print("   🔍 Sweeping future files for missing 1st leg aggregate scores...")
        today_str = now_est.strftime("%Y-%m-%d")
        
        for filename in os.listdir(DATA_DIR):
            if filename.startswith("games_") and filename.endswith(".json"):
                file_date_str = filename.replace("games_", "").replace(".json", "")
                
                # Only sweep today and future files to save I/O
                if file_date_str >= today_str:
                    filepath = os.path.join(DATA_DIR, filename)
                    try:
                        with open(filepath, 'r') as f:
                            day_games = json.load(f)
                        
                        file_updated = False
                        for g in day_games:
                            if g.get("first_leg_goals") is None:
                                league_id = g.get('league', {}).get('id')
                                round_info = str(g.get('league', {}).get('round', ''))
                                
                                if league_id in AGGREGATE_ROUNDS and any(r.lower() in round_info.lower() for r in AGGREGATE_ROUNDS[league_id]):
                                    h_id, a_id = str(g['teams']['home']['id']), str(g['teams']['away']['id'])
                                    print(f"      -> Checking missing 1st Leg for: {g['teams']['home']['name']} vs {g['teams']['away']['name']} ({file_date_str})...")
                                    score = fetch_first_leg_score(league_id, g['league']['season'], round_info, h_id, a_id, g['fixture']['timestamp'])
                                    
                                    if score:
                                        g["first_leg_goals"] = score
                                        file_updated = True
                                        
                        if file_updated:
                            with open(filepath, 'w') as f:
                                json.dump(day_games, f, indent=4)
                    except Exception as e:
                        print(f"Error checking aggregates in {filename}: {e}")
        # Queue up days 2 through 30 (Today and Tomorrow are already handled)
        for i in range(1, 31):
            maintenance_date = now_est + timedelta(days=i)
            if maintenance_date not in dates_to_process:
                dates_to_process.append(maintenance_date)

    # Run the scraper on the determined dates
    for d in dates_to_process: 
        process_date(d, force_master_sync=needs_daily_maintenance)

if __name__ == "__main__":
    main()

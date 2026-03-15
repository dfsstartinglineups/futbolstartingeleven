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
PLAYER_DICT_PATH = os.path.join(DATA_DIR, "master_players.json")

# Load persistent dictionaries
def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f: return json.load(f)
    return {}

MASTER_TEAM_DICT = load_json(TEAM_DICT_PATH)
MASTER_PLAYER_DICT = load_json(PLAYER_DICT_PATH)
# =========================================================
# API-FOOTBALL LEAGUE ID MAPPING
# =========================================================
# --- Top 5 Europe + Championship ---
#  39 : Premier League (England)
#  40 : Championship (England)
# 140 : La Liga (Spain)
#  61 : Ligue 1 (France)
# 135 : Serie A (Italy)
#  78 : Bundesliga (Germany)
#
# --- Euro Tournaments ---
#   2 : UEFA Champions League
#   3 : UEFA Europa League
# 848 : UEFA Conference League
#
# --- Americas (North & South) ---
# 262 : Liga MX (Mexico)
# 253 : Major League Soccer / MLS (USA)
#  71 : Serie A / Brasileirão (Brazil)
# 128 : Liga Profesional (Argentina)
# 528 : Leagues Cup (CONCACAF)
#  13 : Copa Libertadores (CONMEBOL)
#  16 : Copa Sudamericana (CONMEBOL)
#
# --- International ---
#   1 : FIFA World Cup
#   4 : UEFA European Championship (Euros)
#   9 : Copa America
#
# --- English Cups ---
#  45 : FA Cup (England)
#  48 : League Cup / Carabao Cup (England)
#
# --- Best of the Rest ---
# 307 : Saudi Pro League (Saudi Arabia)
#  94 : Primeira Liga (Portugal)
#  88 : Eredivisie (Netherlands)
#  98 : J1 League (Japan)
# =========================================================
TOP_LEAGUE_IDS = [# Top 5 Europe + Championship
    39, 40, 140, 61, 135, 78, 
    # Euro Tournaments 
    2, 3, 848, 
    # Americas (Mexico, MLS, Brazil, Argentina, Leagues Cup, Copa Lib)
    262, 253, 71, 128, 528, 13,16, 
    # International
    1, 4, 9, 
    # English Cups
    45, 48,
    # Best of the Rest (Saudi, Portugal, Netherlands, Japan)
    307, 94, 88,98]

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

def inject_player_stats(lineups):
    if not MASTER_PLAYER_DICT: return lineups 
    
    for team_lineup in lineups:
        for section in ["startXI", "substitutes"]:
            for slot in team_lineup.get(section, []):
                player_info = slot.get("player", {})
                p_id = str(player_info.get("id"))
                
                if p_id in MASTER_PLAYER_DICT:
                    cached_data = MASTER_PLAYER_DICT[p_id]
                    player_bio = cached_data.get("player", {})
                    stats_list = cached_data.get("statistics", [])
                    
                    # --- NEW EXPANDED STATS TRACKING ---
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
                        
                        # New extracted stats
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

def update_future_files_for_league(league_id):
    """Updates rank/record for a specific league in all future daily JSON files."""
    league_id_str = str(league_id)
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    today_str = now_est.strftime("%Y-%m-%d")
    
    for filename in os.listdir(DATA_DIR):
        if filename.startswith("games_") and filename.endswith(".json"):
            file_date_str = filename.replace("games_", "").replace(".json", "")
            
            # Process files for tomorrow or later (today is handled by the live loop)
            if file_date_str > today_str:
                filepath = os.path.join(DATA_DIR, filename)
                try:
                    with open(filepath, 'r') as f:
                        day_games = json.load(f)
                    
                    file_updated = False
                    for g in day_games:
                        # Check if this future game is in the league we just updated
                        if str(g.get("league", {}).get("id")) == league_id_str:
                            for side in ['home', 'away']:
                                t_id = str(g['teams'][side]['id'])
                                t_data = MASTER_TEAM_DICT.get(f"{t_id}_{league_id_str}")
                                
                                if t_data and t_data.get("rank"):
                                    # If the rank or record has changed, update it
                                    if g['teams'][side].get("rank") != t_data["rank"] or g['teams'][side].get("record") != t_data["record"]:
                                        g['teams'][side]['rank'] = t_data["rank"]
                                        g['teams'][side]['record'] = t_data["record"]
                                        file_updated = True
                                        
                    if file_updated:
                        with open(filepath, 'w') as f:
                            json.dump(day_games, f, indent=4)
                except Exception as e:
                    print(f"Error updating future file {filename}: {e}")

def build_daily_games(date_str):
    print(f"\n--- Building Initial Board for {date_str} ---")
    fixtures_data = fetch_fixtures_by_date(date_str)
    if not fixtures_data or not fixtures_data.get("response"): return []

    formatted_games = []
    for game in [g for g in fixtures_data["response"] if g['league']['id'] in TOP_LEAGUE_IDS]:
        home_id, away_id, league_id_str = str(game['teams']['home']['id']), str(game['teams']['away']['id']), str(game['league']['id'])
        
        home_data = MASTER_TEAM_DICT.get(f"{home_id}_{league_id_str}") or MASTER_TEAM_DICT.get(home_id, {})
        away_data = MASTER_TEAM_DICT.get(f"{away_id}_{league_id_str}") or MASTER_TEAM_DICT.get(away_id, {})
        
        formatted_games.append({
            "fixture": game['fixture'], "league": game['league'],
            "teams": {
                "home": {**game['teams']['home'], "rank": home_data.get("rank"), "record": home_data.get("record")},
                "away": {**game['teams']['away'], "rank": away_data.get("rank"), "record": away_data.get("record")}
            },
            "goals": game['goals'], "homeLineup": None, "awayLineup": None, "lineup_checks": 0,  
            "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
            "last_odds_check": None, "injuries": {"home": [], "away": [], "checks": 0},
            "events": [], "match_ended_at": None, "post_game_sync": False
        })
    return formatted_games

def process_date(target_date):
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
        needs_live_board = not bool(daily_games)
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
                new_games_to_add = [g for g in fixtures_data["response"] if g['league']['id'] in TOP_LEAGUE_IDS and g['fixture']['id'] not in existing_fixture_ids]
                
                if new_games_to_add:
                    print(f"[{date_str}] Found {len(new_games_to_add)} newly scheduled games. Injecting...")
                    for game in new_games_to_add:
                        home_id, away_id, league_id_str = str(game['teams']['home']['id']), str(game['teams']['away']['id']), str(game['league']['id'])
                        home_data = MASTER_TEAM_DICT.get(f"{home_id}_{league_id_str}") or MASTER_TEAM_DICT.get(home_id, {})
                        away_data = MASTER_TEAM_DICT.get(f"{away_id}_{league_id_str}") or MASTER_TEAM_DICT.get(away_id, {})
                        
                        daily_games.append({
                            "fixture": game['fixture'], "league": game['league'],
                            "teams": {
                                "home": {**game['teams']['home'], "rank": home_data.get("rank"), "record": home_data.get("record")},
                                "away": {**game['teams']['away'], "rank": away_data.get("rank"), "record": away_data.get("record")}
                            },
                            "goals": game['goals'], "homeLineup": None, "awayLineup": None, "lineup_checks": 0,  
                            "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
                            "last_odds_check": None, "injuries": {"home": [], "away": [], "checks": 0},
                            "events": [], "match_ended_at": None, "post_game_sync": False
                        })
                    updated = True
        else:
            # Print is optional, just confirms it is working
            # print(f"[{date_str}] Pre-Game Deep Sleep. Next kickoff is > 75 mins away. Skipping Master Board API.")
            pass

        for game in daily_games:
            fixture_id = game['fixture']['id']
            league_id_str = str(game['league']['id'])
            
            # --- HEAL MISSING RANKS/RECORDS FOR TODAY (0 API Cost) ---
            for side in ['home', 'away']:
                team = game['teams'][side]
                if team.get('rank') is None or team.get('rank') == "null":
                    t_data = MASTER_TEAM_DICT.get(f"{team['id']}_{league_id_str}")
                    if t_data and t_data.get("rank"):
                        team['rank'] = t_data["rank"]
                        team['record'] = t_data["record"]
                        updated = True
            # ---------------------------------------------------------
            
            # Use live data if we woke up to fetch it, otherwise use our local memory
            if current_fixtures_map and fixture_id in current_fixtures_map:
                latest_data = current_fixtures_map[fixture_id]
            else:
                latest_data = {"fixture": game["fixture"], "goals": game["goals"]}
                
            latest_status = latest_data['fixture']['status']['short']
            local_status = game.get('fixture', {}).get('status', {}).get('short', '')
            
            # --- 🛑 TIME TRAVEL BLOCKER ---
            # API load balancers often send stale payloads. If the API tries to send us 
            # backward in time, we reject it entirely so goals don't temporarily vanish!
            new_elapsed = latest_data.get('fixture', {}).get('status', {}).get('elapsed') or 0
            old_elapsed = game.get('fixture', {}).get('status', {}).get('elapsed') or 0
            
            if new_elapsed < old_elapsed:
                continue # Skip this game loop entirely. The API is lagging!
            
            
            # 1. LIVE EVENTS
            # Actively poll if playing, OR if it JUST hit HT, OR if it JUST ended (to catch stoppage-time goals!)
            is_active_half = latest_status in ['1H', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT']
            just_hit_ht = (latest_status == 'HT' and local_status != 'HT')
            just_ended = (latest_status in ['FT', 'AET', 'PEN'] and local_status not in ['FT', 'AET', 'PEN'])
            
            if is_active_half or just_hit_ht or just_ended:
                game['fixture']['status'], game['goals'] = latest_data['fixture']['status'], latest_data['goals']
                events_data = fetch_events(fixture_id)
                
                if events_data and events_data.get("response"):
                    parsed_events = []
                    for ev in events_data["response"]:
                        if ev["type"] in ["Goal", "Card", "subst"]:
                            
                            # --- 🛑 HOTFIX: IGNORE MISSED PENALTIES ---
                            # API-Sports weirdly classifies missed penalties as "Goals". Reject them!
                            if ev["type"] == "Goal" and ev["detail"] == "Missed Penalty":
                                continue
                                
                            # Grab both parts of the time
                            elapsed_time = ev["time"]["elapsed"]
                            extra_time = ev["time"].get("extra")
                            
                            # Combine them if extra exists (e.g., "90+4"), otherwise just use elapsed
                            display_time = f"{elapsed_time}+{extra_time}" if extra_time else str(elapsed_time)

                            event_obj = {
                                "time": display_time,
                                "team_id": ev["team"]["id"],
                                "player": ev["player"]["name"] if ev.get("player") else None,
                                "player_id": ev["player"]["id"] if ev.get("player") else None,
                                "type": ev["type"],
                                "detail": ev["detail"]
                            }
                            
                            # If it's a substitution, grab the player coming OUT
                            if ev["type"] == "subst":
                                event_obj["player_out"] = ev["assist"]["name"] if ev.get("assist") else None
                                event_obj["player_out_id"] = ev["assist"]["id"] if ev.get("assist") else None
                                
                            parsed_events.append(event_obj)
                            
                    game["events"] = parsed_events
                updated = True
                
            elif latest_status == 'HT':
                # The game is resting at halftime. Just sync the UI status, don't waste API calls on events!
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

            # 4. LINEUPS (Strict Pre-Game Polling & Late Scratches)
            l_checks = game.get("lineup_checks", 0)
            
            # Check if we already have the FULL lineup with actual players
            has_full_lineup = bool(game.get('homeLineup') and game.get('homeLineup').get('startXI'))
            
            # Check every 5 minutes in the final hour
            checkpoints = [60, 55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 4, 3, 2, 1]
            target_checks = sum(1 for c in checkpoints if time_to_kickoff_minutes <= c)
            
            # Late Scratch Checks: Force a re-check at 15m and 5m even if we have the lineup
            needs_15m_refresh = (time_to_kickoff_minutes <= 15) and not game.get("refreshed_15m", False)
            needs_5m_refresh = (time_to_kickoff_minutes <= 5) and not game.get("refreshed_5m", False)
            
            # STRICT RULE: ONLY check if the game has NOT started ('NS')
            needs_lineup = (latest_status == 'NS') and (
                (not has_full_lineup and l_checks < target_checks) or 
                needs_15m_refresh or 
                needs_5m_refresh
            )
            
            if needs_lineup:
                lineups_data = fetch_lineups(fixture_id)
                if lineups_data and lineups_data.get("response") and len(lineups_data["response"]) >= 2:
                    enriched = inject_player_stats(lineups_data["response"])
                    game['homeLineup'], game['awayLineup'] = enriched[0], enriched[1]
                
                # Mark late refreshes as complete so they only fire exactly once
                if time_to_kickoff_minutes <= 15: game["refreshed_15m"] = True
                if time_to_kickoff_minutes <= 5:  game["refreshed_5m"] = True
                
                # Update counter so we don't spam the API
                game['lineup_checks'] = target_checks if not has_full_lineup else (l_checks + 1)
                updated = True
                
            # 5. POST-GAME SYNC
            if is_finished and not game.get("post_game_sync") and game.get("match_ended_at"):
                if (now - datetime.fromisoformat(game["match_ended_at"])).total_seconds() >= 5400:
                    
                    # A. Try to fetch Standings (Knockout Cups might be empty/different)
                    standings_data = fetch_data(f"standings?league={game['league']['id']}&season={game['league']['season']}")
                    if standings_data and standings_data.get("response"):
                        try:
                            # 1. Update the entire league in the Master Dict
                            for row in standings_data["response"][0]["league"]["standings"][0]:
                                MASTER_TEAM_DICT[f"{row['team']['id']}_{game['league']['id']}"] = {"rank": row["rank"], "record": f"{row['all']['win']}-{row['all']['draw']}-{row['all']['lose']}"}
                            with open(TEAM_DICT_PATH, "w") as f: json.dump(MASTER_TEAM_DICT, f, indent=4)
                            
                            # 2. Push the league-wide update to all future files!
                            update_future_files_for_league(game['league']['id'])
                            
                        except Exception as e:
                            pass # Silently handle weird cup structures
                    
                    # B. Fetch Player Data (We want this even if Standings fail!)
                    try:
                        for t_id in [game['teams']['home']['id'], game['teams']['away']['id']]:
                            for p in fetch_all_players(t_id, game['league']['season']): 
                                MASTER_PLAYER_DICT[str(p["player"]["id"])] = p
                        with open(PLAYER_DICT_PATH, "w") as f: json.dump(MASTER_PLAYER_DICT, f, indent=4)
                    except Exception as e:
                        print(f"[{fixture_id}] Post-game player sync error: {e}")

                    # C. MARK AS COMPLETE SO WE DON'T GET STUCK IN A LOOP
                    game["post_game_sync"] = True
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
        
    # Run the scraper on the determined dates
    for d in dates_to_process: 
        process_date(d)

if __name__ == "__main__":
    main()

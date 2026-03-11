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
    # Best of the Rest (Saudi, Portugal, Netherlands)
    307, 94, 88]

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
            
        # Use the first bookmaker provided
        for bet in bookmakers[0].get("bets", []):
            if bet["name"] == "Match Winner":
                for val in bet["values"]:
                    if val["value"] == "Home": odds_result["home"] = val["odd"]
                    elif val["value"] == "Draw": odds_result["draw"] = val["odd"]
                    elif val["value"] == "Away": odds_result["away"] = val["odd"]
            
            elif bet["name"] == "Goals Over/Under":
                for val in bet["values"]:
                    if val["value"] == "Over 2.5": 
                        odds_result["over"] = val["odd"]
                        odds_result["total"] = "2.5"
                    elif val["value"] == "Under 2.5":
                        odds_result["under"] = val["odd"]
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
                    
                    total_games, total_goals, total_assists, total_yellows, total_reds = 0, 0, 0, 0, 0
                    ratings = []
                    competitions = {}
                    
                    for stat in stats_list:
                        league_name = stat.get("league", {}).get("name", "Unknown")
                        c_games = stat.get("games", {}).get("appearences") or 0
                        c_goals = stat.get("goals", {}).get("total") or 0
                        c_assists = stat.get("goals", {}).get("assists") or 0
                        c_yellows = stat.get("cards", {}).get("yellow") or 0
                        c_reds = stat.get("cards", {}).get("red") or 0
                        c_rating = stat.get("games", {}).get("rating")
                        
                        total_games += c_games
                        total_goals += c_goals
                        total_assists += c_assists
                        total_yellows += c_yellows
                        total_reds += c_reds
                        
                        if c_rating:
                            try: ratings.append(float(c_rating))
                            except ValueError: pass
                                
                        competitions[league_name] = {
                            "games": c_games, "goals": c_goals, "assists": c_assists,
                            "yellow_cards": c_yellows, "red_cards": c_reds,
                            "rating": f"{float(c_rating):.2f}" if c_rating else "N/A"
                        }
                            
                    avg_rating = f"{sum(ratings)/len(ratings):.2f}" if ratings else "N/A"
                    player_info.update({"photo": player_bio.get("photo"), "age": player_bio.get("age"), "nationality": player_bio.get("nationality")})
                    player_info["season_stats"] = {
                        "total": {"games": total_games, "goals": total_goals, "assists": total_assists, "yellow_cards": total_yellows, "red_cards": total_reds, "rating": avg_rating},
                        "competitions": competitions
                    }
    return lineups

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
        print(f"\n--- Updating Live Board for {date_str} ---")
        with open(games_file, 'r') as f: daily_games = json.load(f)

        fixtures_data = fetch_fixtures_by_date(date_str)
        if not fixtures_data or not fixtures_data.get("response"): return
        current_fixtures_map = {g['fixture']['id']: g for g in fixtures_data["response"]}
        updated = False

        # --- THE NEW SCHEDULE ADDITION CHECK ---
        existing_fixture_ids = {g['fixture']['id'] for g in daily_games}
        new_games_to_add = [g for g in fixtures_data["response"] if g['league']['id'] in TOP_LEAGUE_IDS and g['fixture']['id'] not in existing_fixture_ids]
        
        if new_games_to_add:
            print(f"[{date_str}] Found {len(new_games_to_add)} newly scheduled games from API. Injecting into local file...")
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
        # ---------------------------------------
        
        for game in daily_games:
            fixture_id = game['fixture']['id']
            latest_data = current_fixtures_map.get(fixture_id)
            if not latest_data: continue
                
            latest_status = latest_data['fixture']['status']['short']
            
            # 1. LIVE EVENTS
            if latest_status in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT']:
                game['fixture']['status'], game['goals'] = latest_data['fixture']['status'], latest_data['goals']
                events_data = fetch_events(fixture_id)
                if events_data and events_data.get("response"):
                    game["events"] = [{"time": ev["time"]["elapsed"], "team_id": ev["team"]["id"], "player": ev["player"]["name"], "type": ev["type"], "detail": ev["detail"]} for ev in events_data["response"] if ev["type"] in ["Goal", "Card"]]
                updated = True

            # 2. MATCH COMPLETION
            is_finished = latest_status in ['FT', 'AET', 'PEN']
            if is_finished:
                game['fixture']['status'], game['goals'] = latest_data['fixture']['status'], latest_data['goals']
                if not game.get("match_ended_at"):
                    game["match_ended_at"] = datetime.now(timezone.utc).isoformat()
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
                    print(f"[{fixture_id}] Checkpoint {target_level}/7: Polling Injuries & Odds...")
                    inj_data = fetch_injuries(fixture_id)
                    game["injuries"]["home"], game["injuries"]["away"] = [], []
                    if inj_data and inj_data.get("response"):
                        for inj in inj_data["response"]:
                            team_key = "home" if inj["team"]["id"] == game["teams"]["home"]["id"] else "away"
                            game["injuries"][team_key].append(inj["player"]["name"])
                    
                    new_odds = fetch_odds(fixture_id)
                    if new_odds:
                        game["odds"] = new_odds
                        game["last_odds_check"] = now.isoformat()
                    
                    game["injuries"]["checks"] = target_level
                    updated = True

            # 4. LINEUPS (Polling 60, 15, 5 mins before)
            l_checks = game.get("lineup_checks", 0)
            needs_lineup = (time_to_kickoff_minutes <= 60 and l_checks == 0) or (time_to_kickoff_minutes <= 15 and l_checks == 1) or (time_to_kickoff_minutes <= 5 and l_checks == 2)

            if latest_status == 'NS' and needs_lineup:
                lineups_data = fetch_lineups(fixture_id)
                if lineups_data and lineups_data.get("response") and len(lineups_data["response"]) >= 2:
                    enriched = inject_player_stats(lineups_data["response"])
                    game['homeLineup'], game['awayLineup'], game['lineup_checks'] = enriched[0], enriched[1], l_checks + 1
                    updated = True
                
            # 5. POST-GAME SYNC
            if is_finished and not game.get("post_game_sync") and game.get("match_ended_at"):
                if (now - datetime.fromisoformat(game["match_ended_at"])).total_seconds() >= 5400:
                    standings_data = fetch_data(f"standings?league={game['league']['id']}&season={game['league']['season']}")
                    if standings_data and standings_data.get("response"):
                        for row in standings_data["response"][0]["league"]["standings"][0]:
                            MASTER_TEAM_DICT[f"{row['team']['id']}_{game['league']['id']}"] = {"rank": row["rank"], "record": f"{row['all']['win']}-{row['all']['draw']}-{row['all']['lose']}"}
                        with open(TEAM_DICT_PATH, "w") as f: json.dump(MASTER_TEAM_DICT, f, indent=4)
                        for t_id in [game['teams']['home']['id'], game['teams']['away']['id']]:
                            for p in fetch_all_players(t_id, game['league']['season']): MASTER_PLAYER_DICT[str(p["player"]["id"])] = p
                        with open(PLAYER_DICT_PATH, "w") as f: json.dump(MASTER_PLAYER_DICT, f, indent=4)
                        game["post_game_sync"] = True
                        updated = True

        if updated:
            with open(games_file, 'w') as f: json.dump(daily_games, f, indent=4)

def main():
    if not API_KEY: return
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    dates = [now_est]
    if now_est.hour < 12: dates.insert(0, now_est - timedelta(days=1))
    for d in dates: process_date(d)

if __name__ == "__main__":
    main()

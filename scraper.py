import os
import json
import urllib.request
import zoneinfo
from datetime import datetime, timezone, timedelta

# Grab the secret key from GitHub Actions
API_KEY = os.environ.get("FOOTBALL_API_KEY")
API_HOST = "https://v3.football.api-sports.io"

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

def get_current_season(league_id, current_date):
    # MLS, Brazil, Argentina, Japan run Spring-to-Fall (Season = Current Year)
    if league_id in [253, 71, 128, 98]:
        return current_date.year
    # Europe, Liga MX, Saudi run Fall-to-Spring (Season = Year - 1 if before July)
    else:
        return current_date.year - 1 if current_date.month < 7 else current_date.year

def process_date(target_date):
    date_str = target_date.strftime("%Y-%m-%d")
    filepath = f"data/games_{date_str}.json"
    ranks_filepath = f"data/ranks_{date_str}.json"
    now_utc = datetime.now(timezone.utc)
    today_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    
    os.makedirs("data", exist_ok=True)
    
    # ==========================================
    # 0. HIBERNATION CHECK (Sequential Logic)
    # ==========================================
    needs_update = False
    
    # Step 0A: Check Yesterday's File First
    yesterday_date = today_est.date() - timedelta(days=1)
    yesterday_str = yesterday_date.strftime("%Y-%m-%d")
    yesterday_file = f"data/games_{yesterday_str}.json"
    
    yesterday_needs_attention = False
    if os.path.exists(yesterday_file):
        try:
            with open(yesterday_file, "r") as yf:
                y_games = json.load(yf)
                for y_game in y_games:
                    y_status = y_game.get("fixture", {}).get("status", {}).get("short", "")
                    if y_status in ['1H', '2H', 'HT', 'ET', 'BT', 'P', 'LIVE', 'INT', 'SUSP', 'NS', 'TBD']:
                        yesterday_needs_attention = True
                        break
        except Exception:
            pass

    if yesterday_needs_attention:
        needs_update = True
    else:
        # Step 0B: Only if yesterday is complete, check today's criteria
        if os.path.exists(filepath):
            try:
                with open(filepath, "r") as f:
                    local_games = json.load(f)
                    
                for game in local_games:
                    status = game.get("fixture", {}).get("status", {}).get("short", "")
                    
                    try:
                        game_time_str = game['fixture']['date']
                        if game_time_str.endswith('Z'):
                            game_time_str = game_time_str[:-1] + '+00:00'
                        game_time = datetime.fromisoformat(game_time_str)
                    except Exception:
                        game_time = now_utc + timedelta(days=1)
                        
                    time_to_kickoff = (game_time - now_utc).total_seconds() / 60
                    
                    if status in ['1H', '2H', 'HT', 'ET', 'BT', 'P', 'LIVE', 'INT', 'SUSP']:
                        needs_update = True
                        break
                        
                    if status in ['NS', 'TBD'] and time_to_kickoff <= 75:
                        needs_update = True
                        break
            except Exception:
                needs_update = True 
        else:
            needs_update = True 

    if not needs_update:
        print(f"[{date_str}] 💤 Hibernating: Yesterday is complete and today has no immediate games.")
        return

    print(f"\n--- Fetching live fixtures & scores for {date_str} ---")
    
    fixtures_data = fetch_data(f"fixtures?date={date_str}&timezone=America/New_York")
    if not fixtures_data or "response" not in fixtures_data:
        return

    matches = [m for m in fixtures_data["response"] if m["league"]["id"] in TOP_LEAGUE_IDS]

    existing_data = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            try:
                loaded = json.load(f)
                for game in loaded:
                    existing_data[game["fixture"]["id"]] = game
            except Exception:
                pass
                
    # --- 3. MASTER STANDINGS FETCHING (Once Per Day) ---
    global_ranks = {}
    if os.path.exists(ranks_filepath):
        with open(ranks_filepath, "r") as f:
            try:
                global_ranks = json.load(f)
            except Exception:
                pass

    if not global_ranks:
        print(f"--- Fetching Master Standings Dictionary for all standard leagues ---")
        for league_id in TOP_LEAGUE_IDS:
            if league_id in [2, 3, 13, 45]: 
                continue # Skip Cup Tournaments
            
            season = get_current_season(league_id, today_est)
            stand_data = fetch_data(f"standings?league={league_id}&season={season}")
            
            if stand_data and stand_data.get("response"):
                for lg in stand_data["response"]:
                    for group in lg["league"]["standings"]:
                        for team in group:
                            tid = str(team["team"]["id"])
                            rank = team.get("rank")
                            wins = team.get("all", {}).get("win", 0)
                            draws = team.get("all", {}).get("draw", 0)
                            losses = team.get("all", {}).get("lose", 0)
                            
                            global_ranks[tid] = {
                                "rank": rank,
                                "record": f"{wins}-{draws}-{losses}"
                            }
                            
        # Save the massive new master dictionary
        with open(ranks_filepath, "w") as f:
            json.dump(global_ranks, f, indent=4)

        # --- 3B. FUTURE FILE STANDINGS SYNC ---
        # Update all 30 days of pre-populated future games with these fresh global standings!
        print("--- Syncing fresh master standings to all future scheduled games... ---")
        for filename in os.listdir("data"):
            if filename.startswith("games_") and filename.endswith(".json"):
                file_date_str = filename.replace("games_", "").replace(".json", "")
                if file_date_str > date_str: # Only touch future files
                    future_filepath = os.path.join("data", filename)
                    try:
                        with open(future_filepath, "r") as ff:
                            future_games = json.load(ff)
                        
                        made_changes = False
                        for fg in future_games:
                            h_id = str(fg["teams"]["home"]["id"])
                            a_id = str(fg["teams"]["away"]["id"])
                            
                            if h_id in global_ranks and isinstance(global_ranks[h_id], dict):
                                fg["teams"]["home"]["rank"] = global_ranks[h_id].get("rank")
                                fg["teams"]["home"]["record"] = global_ranks[h_id].get("record")
                                made_changes = True
                            if a_id in global_ranks and isinstance(global_ranks[a_id], dict):
                                fg["teams"]["away"]["rank"] = global_ranks[a_id].get("rank")
                                fg["teams"]["away"]["record"] = global_ranks[a_id].get("record")
                                made_changes = True
                                
                        if made_changes:
                            with open(future_filepath, "w") as ff:
                                json.dump(future_games, ff, indent=4)
                    except Exception:
                        pass

    # --- 4. IDENTIFY MISSING PRE-MATCH ODDS ---
    leagues_needing_odds = set()
    
    for match in matches:
        fixture_id = match["fixture"]["id"]
        league_id = match["league"]["id"]
        season = match["league"]["season"] 
        
        existing_game = existing_data.get(fixture_id, {})
        existing_odds = existing_game.get("odds", {"home": "TBD"})
        last_odds_check_str = existing_game.get("last_odds_check")
        
        mins_since_check = 999  
        if last_odds_check_str:
            try:
                last_check_time = datetime.fromisoformat(last_odds_check_str)
                mins_since_check = (now_utc - last_check_time).total_seconds() / 60
            except Exception:
                pass

        if existing_odds.get("home") == "TBD" and mins_since_check > 60:
            leagues_needing_odds.add((league_id, season))

    # --- 5. BULK ODDS FETCHING ---
    odds_dict = {}
    if leagues_needing_odds:
        print(f"--- Fetching bulk odds for {len(leagues_needing_odds)} leagues. ---")
        for league_id, season in leagues_needing_odds:
            page = 1
            total_pages = 1
            while page <= total_pages:
                odds_res = fetch_data(f"odds?league={league_id}&season={season}&date={date_str}&bookmaker=8&page={page}")
                if not odds_res or "response" not in odds_res: break
                    
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

    # --- 6. MAP DATA AND FETCH LIVE/PRE-MATCH METADATA ---
    all_game_data = []
    
    for match in matches:
        fixture_id = match["fixture"]["id"]
        league_id = match["league"]["id"]
        status = match["fixture"]["status"]["short"]
        
        existing_game = existing_data.get(fixture_id, {})
        home_lineup = existing_game.get("homeLineup")
        away_lineup = existing_game.get("awayLineup")
        game_odds = odds_dict.get(fixture_id, existing_game.get("odds", {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"}))
        injuries = existing_game.get("injuries", {"home": [], "away": [], "fetched": False})
        events = existing_game.get("events", [])
        last_odds_check_str = existing_game.get("last_odds_check")
        
        # We mapped odds above, apply cooldown
        if existing_game.get("odds", {}).get("home") == "TBD" and game_odds.get("home") != "TBD":
             last_odds_check_str = now_utc.isoformat()
            
        try:
            game_time_str = match['fixture']['date']
            if game_time_str.endswith('Z'):
                game_time_str = game_time_str[:-1] + '+00:00'
            game_time = datetime.fromisoformat(game_time_str)
        except Exception:
            game_time = now_utc + timedelta(days=1)
            
        time_to_kickoff = (game_time - now_utc).total_seconds() / 60
        within_window = now_utc >= (game_time - timedelta(minutes=60))
        valid_status = status not in ['PST', 'CANC', 'ABD']
        
        in_odds_window = 0 <= time_to_kickoff <= 60
        mins_since_check = 999  

        if last_odds_check_str:
            try:
                last_check_time = datetime.fromisoformat(last_odds_check_str)
                mins_since_check = (now_utc - last_check_time).total_seconds() / 60
            except Exception:
                pass

        if in_odds_window and mins_since_check >= 10 and valid_status:
            print(f"[{fixture_id}] Fetching live odds (T-{int(time_to_kickoff)} mins)...")
            odds_res = fetch_data(f"odds?fixture={fixture_id}&bookmaker=8")
            if odds_res and "response" in odds_res and len(odds_res["response"]) > 0:
                odd_item = odds_res["response"][0]
                if odd_item.get("bookmakers"):
                    for bet in odd_item["bookmakers"][0].get("bets", []):
                        if bet["id"] == 1: 
                            for v in bet["values"]:
                                if v["value"] == "Home": game_odds["home"] = str(v["odd"])
                                if v["value"] == "Draw": game_odds["draw"] = str(v["odd"])
                                if v["value"] == "Away": game_odds["away"] = str(v["odd"])
                        elif bet["id"] == 5: 
                            for v in bet["values"]:
                                if "Over 2.5" in str(v["value"]):
                                    game_odds["over"] = str(v["odd"])
                                    game_odds["total"] = "2.5"
                                elif "Under 2.5" in str(v["value"]):
                                    game_odds["under"] = str(v["odd"])
                                    game_odds["total"] = "2.5"
            last_odds_check_str = now_utc.isoformat()

        if within_window and not injuries.get("fetched") and valid_status:
            print(f"[{fixture_id}] Fetching injury reports...")
            inj_res = fetch_data(f"injuries?fixture={fixture_id}")
            if inj_res and "response" in inj_res:
                for inj in inj_res["response"]:
                    team_id = inj["team"]["id"]
                    player_name = inj["player"]["name"]
                    if team_id == match["teams"]["home"]["id"]:
                        injuries["home"].append(player_name)
                    else:
                        injuries["away"].append(player_name)
            injuries["fetched"] = True

        needs_lineups = not home_lineup or not away_lineup
        stop_statuses = ['PST', 'CANC', 'ABD', 'HT', 'FT', 'AET', 'PEN']
        
        if needs_lineups and within_window and status not in stop_statuses:
            print(f"[{match['teams']['home']['name']} vs {match['teams']['away']['name']}] Fetching lineups...")
            lineups_data = fetch_data(f"fixtures/lineups?fixture={fixture_id}")
            if lineups_data and "response" in lineups_data:
                new_home = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["home"]["id"]), None)
                new_away = next((l for l in lineups_data["response"] if l["team"]["id"] == match["teams"]["away"]["id"]), None)
                if new_home: home_lineup = new_home
                if new_away: away_lineup = new_away

        is_live = valid_status and status in ['1H', '2H', 'HT', 'ET', 'BT', 'P', 'LIVE']
        if is_live:
            ev_res = fetch_data(f"fixtures/events?fixture={fixture_id}")
            if ev_res and "response" in ev_res:
                parsed_events = []
                for ev in ev_res["response"]:
                    if ev["type"] == "Goal" or (ev["type"] == "Card" and "Red" in ev["detail"]):
                        parsed_events.append({
                            "time": ev["time"]["elapsed"],
                            "team_id": ev["team"]["id"],
                            "player": ev["player"]["name"],
                            "type": ev["type"],
                            "detail": ev["detail"]
                        })
                events = parsed_events

        h_id = str(match["teams"]["home"]["id"])
        a_id = str(match["teams"]["away"]["id"])
        
        h_rank_data = global_ranks.get(h_id)
        a_rank_data = global_ranks.get(a_id)
        
        h_rank = h_rank_data.get("rank") if isinstance(h_rank_data, dict) else h_rank_data
        h_record = h_rank_data.get("record") if isinstance(h_rank_data, dict) else None
        
        a_rank = a_rank_data.get("rank") if isinstance(a_rank_data, dict) else a_rank_data
        a_record = a_rank_data.get("record") if isinstance(a_rank_data, dict) else None

        all_game_data.append({
            "fixture": match["fixture"],
            "league": match["league"],
            "teams": {
                "home": {**match["teams"]["home"], "rank": h_rank, "record": h_record},
                "away": {**match["teams"]["away"], "rank": a_rank, "record": a_record}
            },
            "goals": match["goals"],
            "homeLineup": home_lineup,
            "awayLineup": away_lineup,
            "odds": game_odds,
            "last_odds_check": last_odds_check_str,
            "injuries": injuries,
            "events": events
        })

    with open(filepath, "w") as f:
        json.dump(all_game_data, f, indent=4)
        
    print(f"Data successfully saved to {filepath}")


def prepopulate_future_days(days_out=30):
    """
    Ensures that we always have basic schedule JSON files generated for the next X days.
    Costs exactly 1 API call per missing day.
    """
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    os.makedirs("data", exist_ok=True)
    
    for i in range(1, days_out + 1):
        future_date = now_est + timedelta(days=i)
        future_str = future_date.strftime("%Y-%m-%d")
        future_filepath = f"data/games_{future_str}.json"
        
        if not os.path.exists(future_filepath):
            print(f"--- Pre-populating future schedule for {future_str} ---")
            fixtures_data = fetch_data(f"fixtures?date={future_str}&timezone=America/New_York")
            
            if fixtures_data and "response" in fixtures_data:
                future_matches = [m for m in fixtures_data["response"] if m["league"]["id"] in TOP_LEAGUE_IDS]
                future_game_data = []
                
                for match in future_matches:
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

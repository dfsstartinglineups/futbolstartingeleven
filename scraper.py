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
    2, 3, 13,                          # Continental (Added Europa League ID 3)
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
    ranks_filepath = f"data/ranks_{date_str}.json"
    now_utc = datetime.now(timezone.utc)
    
    # Ensure data directory exists early for our cache files
    os.makedirs("data", exist_ok=True)
    
    # ==========================================
    # 0. HIBERNATION CHECK (Save API Calls)
    # ==========================================
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                local_games = json.load(f)
                
            needs_update = False
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
                
                # Condition A: Game is actively being played or paused
                if status in ['1H', '2H', 'HT', 'ET', 'BT', 'P', 'LIVE', 'INT', 'SUSP']:
                    needs_update = True
                    break
                    
                # Condition B: Game is coming up within 75 minutes (wake up to catch 60min lineups/odds)
                # Or a game was supposed to start but is stuck in NS/TBD (time_to_kickoff <= 0)
                if status in ['NS', 'TBD'] and time_to_kickoff <= 75:
                    needs_update = True
                    break

            if not needs_update:
                print(f"[{date_str}] 💤 Hibernating: No active games and next match is > 75 mins away.")
                return

        except Exception:
            pass # If the file is corrupt or empty, we skip hibernation and fetch normally
    
    print(f"\n--- Fetching live fixtures & scores for {date_str} ---")
    
    # 1. Fetch the master schedule
    fixtures_data = fetch_data(f"fixtures?date={date_str}&timezone=America/New_York")
    
    if not fixtures_data or "response" not in fixtures_data:
        print("No fixtures found or API error.")
        return

    # Filter down to just our leagues
    matches = [m for m in fixtures_data["response"] if m["league"]["id"] in TOP_LEAGUE_IDS]

    # --- 2. LOAD MEMORY ---
    existing_data = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            try:
                loaded = json.load(f)
                for game in loaded:
                    existing_data[game["fixture"]["id"]] = game
            except Exception:
                pass
                
    # Load Daily Ranks Cache
    global_ranks = {}
    if os.path.exists(ranks_filepath):
        with open(ranks_filepath, "r") as f:
            try:
                global_ranks = json.load(f)
            except Exception:
                pass

    # --- 3. IDENTIFY MISSING DATA (Odds & Standings) ---
    leagues_needing_odds = set()
    leagues_needing_standings = set()
    
    for match in matches:
        fixture_id = match["fixture"]["id"]
        league_id = match["league"]["id"]
        season = match["league"]["season"] 
        
        home_id = str(match["teams"]["home"]["id"])
        away_id = str(match["teams"]["away"]["id"])
        
        existing_game = existing_data.get(fixture_id, {})
        existing_odds = existing_game.get("odds", {"home": "TBD"})
        last_odds_check_str = existing_game.get("last_odds_check")
        
        # Calculate time since we last checked this specific game's odds
        mins_since_check = 999  
        if last_odds_check_str:
            try:
                last_check_time = datetime.fromisoformat(last_odds_check_str)
                mins_since_check = (now_utc - last_check_time).total_seconds() / 60
            except Exception:
                pass

        # Check Odds Needs (Only request bulk odds if it's TBD AND we haven't checked in 60 mins)
        if existing_odds.get("home") == "TBD" and mins_since_check > 60:
            leagues_needing_odds.add((league_id, season))

        # Check Standings Needs
        if league_id in [2, 3, 13, 45]:
            # Cup competitions don't have standard global ranks, mark as None to prevent retries
            global_ranks[home_id] = None
            global_ranks[away_id] = None
        else:
            # If either team is missing from our daily cache, OR if it's the old integer format, force a fetch
            h_data = global_ranks.get(home_id)
            a_data = global_ranks.get(away_id)
            
            if home_id not in global_ranks or isinstance(h_data, int):
                leagues_needing_standings.add((league_id, season))
            if away_id not in global_ranks or isinstance(a_data, int):
                leagues_needing_standings.add((league_id, season))

    # --- 4. BULK STANDINGS FETCHING (Optimized: Once per day per league) ---
    if leagues_needing_standings:
        print(f"--- Fetching Standings for {len(leagues_needing_standings)} missing leagues to get Ranks & Records ---")
        for league_id, season in leagues_needing_standings:
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
                            
                            # Store both the Rank and the Record in a dictionary
                            global_ranks[tid] = {
                                "rank": rank,
                                "record": f"{wins}-{draws}-{losses}"
                            }
                            
        # Post-Fetch cleanup: If a team is still missing (e.g. API glitch), mark as None so we don't loop endlessly
        for match in matches:
            if match["league"]["id"] in [l[0] for l in leagues_needing_standings]:
                h_id = str(match["teams"]["home"]["id"])
                a_id = str(match["teams"]["away"]["id"])
                if h_id not in global_ranks: global_ranks[h_id] = None
                if a_id not in global_ranks: global_ranks[a_id] = None
                
        # Save the updated ranks to the daily cache
        with open(ranks_filepath, "w") as f:
            json.dump(global_ranks, f, indent=4)

    # --- 5. BULK ODDS FETCHING (Only if TBD) ---
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
        season = match["league"]["season"]
        status = match["fixture"]["status"]["short"]
        
        existing_game = existing_data.get(fixture_id, {})
        home_lineup = existing_game.get("homeLineup")
        away_lineup = existing_game.get("awayLineup")
        game_odds = odds_dict.get(fixture_id, existing_game.get("odds", {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"}))
        injuries = existing_game.get("injuries", {"home": [], "away": [], "fetched": False})
        events = existing_game.get("events", [])
        last_odds_check_str = existing_game.get("last_odds_check")
        
        # Apply the cooldown timestamp if this game's league was part of the bulk fetch we just did
        if (league_id, season) in leagues_needing_odds:
            last_odds_check_str = now_utc.isoformat()
            
        # Parse match time
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
        
        # A. LIVE ODDS REFRESH (Every 10 mins during the 60 mins before kickoff)
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

        # B. FETCH INJURIES (Once per game, exactly when we start looking for lineups)
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

        # C. FETCH LINEUPS
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

        # D. FETCH LIVE EVENTS (Goals & Red Cards)
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

        # Extract Rank and Record smoothly to inject into final payload
        h_id = str(match["teams"]["home"]["id"])
        a_id = str(match["teams"]["away"]["id"])
        
        h_rank_data = global_ranks.get(h_id)
        a_rank_data = global_ranks.get(a_id)
        
        # Fallback handling in case of old cache ghosts
        h_rank = h_rank_data.get("rank") if isinstance(h_rank_data, dict) else h_rank_data
        h_record = h_rank_data.get("record") if isinstance(h_rank_data, dict) else None
        
        a_rank = a_rank_data.get("rank") if isinstance(a_rank_data, dict) else a_rank_data
        a_record = a_rank_data.get("record") if isinstance(a_rank_data, dict) else None

        # E. COMPILE MATCH PAYLOAD
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

    # --- 7. ORPHAN INJECTION (Late Night Crossover) ---
    today_est_date = datetime.now(zoneinfo.ZoneInfo("America/New_York")).date()
    if target_date.date() == today_est_date:
        yesterday_date = target_date - timedelta(days=1)
        yesterday_file = f"data/games_{yesterday_date.strftime('%Y-%m-%d')}.json"
        
        if os.path.exists(yesterday_file):
            try:
                with open(yesterday_file, "r") as f:
                    yesterday_games = json.load(f)
                    
                for y_game in yesterday_games:
                    status = y_game.get("fixture", {}).get("status", {}).get("short", "")
                    try:
                        g_time_str = y_game['fixture']['date']
                        if g_time_str.endswith('Z'):
                            g_time_str = g_time_str[:-1] + '+00:00'
                        g_time = datetime.fromisoformat(g_time_str)
                    except Exception:
                        g_time = now_utc - timedelta(hours=10)
                        
                    hours_since_kickoff = (now_utc - g_time).total_seconds() / 3600
                    
                    # Keep it if it is actively playing
                    is_active = status in ['1H', '2H', 'HT', 'ET', 'BT', 'P', 'LIVE', 'INT', 'SUSP']
                    # Keep it on the board if it finished within the last 8 hours
                    is_recent_finish = status in ['FT', 'AET', 'PEN'] and hours_since_kickoff < 8
                    
                    if is_active or is_recent_finish:
                        y_game["is_orphan"] = True
                        all_game_data.append(y_game)
            except Exception as e:
                print(f"Failed to inject orphans: {e}")

    with open(filepath, "w") as f:
        json.dump(all_game_data, f, indent=4)
        
    print(f"Data successfully saved to {filepath}")

def main():
    if not API_KEY:
        print("CRITICAL ERROR: FOOTBALL_API_KEY environment variable not set.")
        return

    # Automatically handles EST/EDT shifts
    now_est = datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    
    # Always process the current EST date
    dates_to_process = [now_est]

    # The Late Night Rule: 
    # If it's between Midnight and 6 AM Eastern, games from "yesterday" (like West Coast MLS)
    # might still be playing. We must update yesterday's file alongside today's.
    if now_est.hour < 6:
        dates_to_process.insert(0, now_est - timedelta(days=1))

    for target_date in dates_to_process:
        process_date(target_date)

if __name__ == "__main__":
    main()

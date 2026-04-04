import os
import json
import requests
import zoneinfo
import time
import re
from datetime import datetime, timedelta

# --- FIREBASE IMPORTS ---
import firebase_admin
from firebase_admin import credentials, db

# ==========================================================
# --- SECURE FIREBASE INITIALIZATION ---
# ==========================================================
raw_firebase_secret = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
if raw_firebase_secret:
    try:
        if not firebase_admin._apps:
            cred_dict = json.loads(raw_firebase_secret)
            cred = credentials.Certificate(cred_dict)
            
            # 🚨 ACTUAL FIREBASE DB URL 🚨
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://nbastartingfive-8b420-default-rtdb.firebaseio.com/'
            })
            print("✅ Firebase securely authenticated!")
    except Exception as e:
        print(f"❌ Firebase Auth Failed: {e}")
else:
    print("⚠️ FIREBASE_SERVICE_ACCOUNT env var not found. Firebase pushing will be skipped.")

# ==========================================================
# --- FOLDER & API SETUP ---
# ==========================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, '..', 'data')
LIVE_DIR = os.path.join(DATA_DIR, 'LIVE')

os.makedirs(LIVE_DIR, exist_ok=True)

API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ.get("FOOTBALL_API_KEY")

# ==========================================================
# --- HELPER FUNCTIONS ---
# ==========================================================
def fetch_api(endpoint):
    """Helper to fetch from API-Football using requests"""
    url = f"{API_HOST}/{endpoint}"
    headers = {"x-apisports-key": API_KEY}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"⚠️ API Fetch Failed ({endpoint}): {e}")
        return None

def inspect_and_sanitize(obj, current_path="root"):
    """
    Recursively walks the JSON tree. If it finds an illegal Firebase key, 
    it prints the EXACT path to the console so you can see the culprit, 
    and then safely fixes it.
    """
    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            k_str = str(k).strip()
            safe_key = k_str
            
            if not k_str:
                safe_key = "empty_key"
            
            illegal_match = re.search(r'[.$#\[\]/]', safe_key)
            if illegal_match:
                safe_key = re.sub(r'[.$#\[\]/]', '_', safe_key)
                
            new_dict[safe_key] = inspect_and_sanitize(v, f"{current_path} -> {safe_key}")
        return new_dict
        
    elif isinstance(obj, list):
        return [inspect_and_sanitize(item, f"{current_path}[{i}]") for i, item in enumerate(obj)]
    else:
        return obj

# ==========================================================
# --- CORE ENGINE LOGIC ---
# ==========================================================
def main():
    if not API_KEY:
        print("❌ Missing FOOTBALL_API_KEY. Exiting.")
        return 3600 

    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    now_est = datetime.now(ny_tz)
    now_ts = now_est.timestamp()
    
    potential_dates = [now_est]
    if now_est.hour < 12:
        potential_dates.insert(0, now_est - timedelta(days=1))
        
    dates_to_process = []
    
    for d in potential_dates:
        d_str = d.strftime("%Y-%m-%d")
        base_path = os.path.join(DATA_DIR, f"games_{d_str}.json")
        
        if not os.path.exists(base_path):
            dates_to_process.append(d)
            continue
            
        with open(base_path, 'r') as f:
            try:
                check_games = json.load(f)
            except:
                dates_to_process.append(d)
                continue
        
        all_done = True
        for g in check_games:
            status = g.get('fixture', {}).get('status', {}).get('short', '')
            synced = g.get('post_game_sync', False)
            if status not in ['FT', 'AET', 'PEN'] or not synced:
                all_done = False
                break
        
        if all_done and len(check_games) > 0:
            print(f"✅ Date {d_str} is fully synced and finished. Retiring from live polling.")
        else:
            dates_to_process.append(d)

    if not dates_to_process:
        print("💤 All scheduled dates are finished and synced. No API calls needed.")
        return 600 

    all_new_live_data = {}
    active_games_found = 0
    has_live_games = False
    next_upcoming_ts = None  
    missing_schedule = False

    old_live_data = {}
    for d in dates_to_process:
        date_str = d.strftime("%Y-%m-%d")
        live_file_path = os.path.join(LIVE_DIR, f"futbol_live_{date_str}.json")
        if os.path.exists(live_file_path):
            try:
                with open(live_file_path, 'r') as f:
                    old_live_data.update(json.load(f))
            except: pass

    for target_date in dates_to_process:
        current_date_str = target_date.strftime("%Y-%m-%d")
        base_file_path = os.path.join(DATA_DIR, f"games_{current_date_str}.json")
        live_file_path = os.path.join(LIVE_DIR, f"futbol_live_{current_date_str}.json")
        
        if not os.path.exists(base_file_path):
            missing_schedule = True
            continue
            
        with open(base_file_path, 'r') as f:
            daily_games = json.load(f)
            
        if not daily_games:
            missing_schedule = True
            continue

        for base_game in daily_games:
            g_status = base_game.get('fixture', {}).get('status', {}).get('short', '')
            g_synced = base_game.get('post_game_sync', False)
            g_ts = base_game.get('fixture', {}).get('timestamp', 0)
            
            if (g_status in ['FT', 'AET', 'PEN'] and g_synced) or g_status in ['PST', 'CANC', 'ABD', 'AWD', 'WO']:
                continue
                
            if g_ts <= now_ts:
                if not has_live_games: 
                    print(f"👀 Local JSON: Games should be live right now (e.g., {base_game['teams']['home']['name']}). Forcing engine awake.")
                has_live_games = True
            else:
                if next_upcoming_ts is None or g_ts < next_upcoming_ts:
                    next_upcoming_ts = g_ts

        fixtures_data = fetch_api(f"fixtures?date={current_date_str}&timezone=America/New_York")
        if not fixtures_data or not fixtures_data.get("response"):
            continue
            
        live_master_map = {str(g['fixture']['id']): g for g in fixtures_data["response"]}
        day_live_data = {}

        for base_game in daily_games:
            fix_id = str(base_game['fixture']['id'])
            
            if fix_id not in live_master_map: continue
            
            latest_data = live_master_map[fix_id]
            status = latest_data['fixture']['status']['short']
            
            is_playing = status in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT']
            is_finished = status in ['FT', 'AET', 'PEN']
            
            base_status = base_game.get('fixture', {}).get('status', {}).get('short', '')
            scraper_has_synced = (base_status in ['FT', 'AET', 'PEN']) or base_game.get('post_game_sync', False)
            
            if is_finished:
                if scraper_has_synced:
                    continue 
                else:
                    if fix_id in old_live_data:
                        live_game_obj = old_live_data[fix_id]
                        live_game_obj['fixture']['status'] = latest_data['fixture']['status']
                        live_game_obj['goals'] = latest_data['goals']
                        
                        day_live_data[fix_id] = live_game_obj
                        all_new_live_data[fix_id] = live_game_obj
                        active_games_found += 1 
                    continue 

            if not is_playing and not is_finished:
                continue 

            active_games_found += 1

            if status == 'HT':
                if fix_id in old_live_data and 'events' in old_live_data[fix_id]:
                    print(f"☕ Halftime: {latest_data['teams']['home']['name']} vs {latest_data['teams']['away']['name']}. Pausing API pulls.")
                    live_game_obj = old_live_data[fix_id]
                    live_game_obj['fixture']['status'] = latest_data['fixture']['status']
                    live_game_obj['goals'] = latest_data['goals']
                    day_live_data[fix_id] = live_game_obj
                    all_new_live_data[fix_id] = live_game_obj
                    continue 
            
            print(f"⚽ Processing Live Match: {latest_data['teams']['home']['name']} vs {latest_data['teams']['away']['name']} ({status})")
            
            live_game_obj = dict(base_game) 
            live_game_obj['fixture']['status'] = latest_data['fixture']['status']
            live_game_obj['goals'] = latest_data['goals']

            # A. FETCH EVENTS
            events_data = fetch_api(f"fixtures/events?fixture={fix_id}")
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
                live_game_obj["events"] = parsed_events

            # =========================================================
            # B. STATELESS TEAM STATS FETCH
            # =========================================================
            stats_data = fetch_api(f"fixtures/statistics?fixture={fix_id}")
            has_deep_stats_this_loop = False
            
            if stats_data and isinstance(stats_data.get("response"), list) and len(stats_data["response"]) > 0:
                has_deep_stats_this_loop = True
                team_stats = {"home": {}, "away": {}}
                for t_stat in stats_data["response"]:
                    side = "home" if t_stat["team"]["id"] == latest_data["teams"]["home"]["id"] else "away"
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
                live_game_obj["team_stats"] = team_stats
            else:
                # Early game or API hiccup. Fallback to memory so UI doesn't drop to 0.
                if fix_id in old_live_data and "team_stats" in old_live_data[fix_id]:
                    live_game_obj["team_stats"] = old_live_data[fix_id]["team_stats"]


            # =========================================================
            # C. STATELESS PLAYER STATS & SUBSTITUTIONS
            # =========================================================
            # 1. Build a fallback map from memory in case the API or Scraper is delayed
            old_player_stats = {}
            if fix_id in old_live_data:
                for side in ["homeLineup", "awayLineup"]:
                    lineup_mem = old_live_data[fix_id].get(side, {})
                    if isinstance(lineup_mem, dict):
                        for slot in lineup_mem.get("startXI", []):
                            if "live_stats" in slot.get("player", {}):
                                old_player_stats[str(slot["player"]["id"])] = slot["player"]["live_stats"]
                        for sub in lineup_mem.get("substitutes", []):
                            if "live_stats" in sub.get("player", {}):
                                old_player_stats[str(sub["player"]["id"])] = sub["player"]["live_stats"]

            # 2. Check if the scraper has populated the JSON with lineups yet
            home_lu = live_game_obj.get("homeLineup")
            away_lu = live_game_obj.get("awayLineup")
            valid_lineups = isinstance(home_lu, dict) and isinstance(away_lu, dict)

            # 3. Only fetch player stats if Team Stats exist AND Lineups exist
            live_player_map = {}
            if has_deep_stats_this_loop and valid_lineups:
                live_players_data = fetch_api(f"fixtures/players?fixture={fix_id}")
                if live_players_data and live_players_data.get("response"):
                    for tp in live_players_data["response"]:
                        for p in tp["players"]:
                            p_id = str(p["player"]["id"])
                            p_stats = p["statistics"][0] if len(p["statistics"]) > 0 else {}
                            live_player_map[p_id] = {
                                "goals": p_stats.get("goals", {}).get("total") or 0,
                                "assists": p_stats.get("goals", {}).get("assists") or 0,
                                "total_shots": p_stats.get("shots", {}).get("total") or 0,
                                "shots_on_target": p_stats.get("shots", {}).get("on") or 0,
                                "passes": p_stats.get("passes", {}).get("total") or 0,
                                "key_passes": p_stats.get("passes", {}).get("key") or 0,
                                "tackles": p_stats.get("tackles", {}).get("total") or 0,
                                "interceptions": p_stats.get("tackles", {}).get("interceptions") or 0,
                                "saves": p_stats.get("goals", {}).get("saves") or 0,
                                "conceded": p_stats.get("goals", {}).get("conceded") or 0,
                                "yellow_cards": p_stats.get("cards", {}).get("yellow") or 0,
                                "red_cards": p_stats.get("cards", {}).get("red") or 0,
                                "rating": p_stats.get("games", {}).get("rating") or "N/A"
                            }

            if valid_lineups:
                # Apply dynamic substitutions
                for ev in parsed_events:
                    if ev["type"] == "subst":
                        player_in_id = str(ev["player_id"])
                        player_out_id = str(ev["player_out_id"])
                        
                        for side in ["homeLineup", "awayLineup"]:
                            lineup = live_game_obj[side]
                            
                            in_is_sub = any(str(s["player"]["id"]) == player_in_id for s in lineup.get("substitutes", []))
                            out_is_starter = any(str(s["player"]["id"]) == player_out_id for s in lineup.get("startXI", []))
                            
                            in_is_starter = any(str(s["player"]["id"]) == player_in_id for s in lineup.get("startXI", []))
                            out_is_sub_err = any(str(s["player"]["id"]) == player_out_id for s in lineup.get("substitutes", []))
                            if in_is_starter and out_is_sub_err:
                                try:
                                    s_idx = next(i for i, s in enumerate(lineup["startXI"]) if str(s["player"]["id"]) == player_in_id)
                                    sub_idx = next(i for i, s in enumerate(lineup["substitutes"]) if str(s["player"]["id"]) == player_out_id)
                                    temp = lineup["startXI"][s_idx]
                                    lineup["startXI"][s_idx] = lineup["substitutes"][sub_idx]
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

                # Attach Live Stats (prefer new API fetch, fall back to memory)
                for side in ["homeLineup", "awayLineup"]:
                    lineup = live_game_obj[side]
                    for slot in lineup.get("startXI", []):
                        p_id = str(slot["player"]["id"])
                        if p_id in live_player_map: 
                            slot["player"]["live_stats"] = live_player_map[p_id]
                        elif p_id in old_player_stats:
                            slot["player"]["live_stats"] = old_player_stats[p_id]
                            
                        for sub_hist in slot.get("sub_history", []):
                            h_id = str(sub_hist["id"])
                            if h_id in live_player_map: 
                                sub_hist["live_stats"] = live_player_map[h_id]
                            elif h_id in old_player_stats:
                                sub_hist["live_stats"] = old_player_stats[h_id]
                                
                    for sub in lineup.get("substitutes", []):
                        p_id = str(sub["player"]["id"])
                        if p_id in live_player_map: 
                            sub["player"]["live_stats"] = live_player_map[p_id]
                        elif p_id in old_player_stats:
                            sub["player"]["live_stats"] = old_player_stats[p_id]


            day_live_data[fix_id] = live_game_obj
            all_new_live_data[fix_id] = live_game_obj
            
        if day_live_data:
            with open(live_file_path, 'w') as f:
                json.dump(day_live_data, f, indent=2)

    # =========================================================
    # 3. SECURE PUSH TO FIREBASE
    # =========================================================
    if active_games_found > 0:
        if firebase_admin._apps:
            try:
                safe_payload = inspect_and_sanitize(all_new_live_data)
                
                ref = db.reference('futbol_live_games')
                ref.set(safe_payload)
                print(f"🚀 Pushed {active_games_found} active futbol games to Firebase!")
            except Exception as e:
                print(f"⚠️ Failed to push: {e}")
    else:
        print("\n💤 No active futbol games right now.")
        if firebase_admin._apps:
            try: db.reference('futbol_live_games').delete()
            except: pass

    # 4. SLEEP CALCULATION
    if has_live_games:
        print("⚡ Active/Imminent games detected. Fast-polling.")
        return 30 

    if next_upcoming_ts:
        target_sleep = (next_upcoming_ts - now_ts) - 120 
        calculated_sleep = max(60, min(target_sleep, 3600))
        print(f"⏰ Next game approaches. Calculated sleep: {int(calculated_sleep)}s")
        return calculated_sleep
        
    if missing_schedule:
        print("📭 Today's schedule hasn't been built by the scraper yet. Waiting 2 minutes...")
        return 120
            
    print("📭 No live games, no delayed games, and no future games found. Sleeping for 1 hour.")
    return 3600 


if __name__ == "__main__":
    print("⚽ Starting Futbol Live Real-Time Engine...")
    while True:
        try:
            sleep_seconds = main()
            if sleep_seconds == 30:
                print("⏱️ Fast poll active (30s)...\n")
            else:
                print(f"⏳ Sleeping {int(sleep_seconds // 60)} minutes...\n")
            time.sleep(sleep_seconds)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\n❌ Loop crashed: {e}. Restarting in 60s...")
            time.sleep(60)

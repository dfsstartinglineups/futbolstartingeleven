import os
import json
import requests
import zoneinfo
import time
import re
import copy
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
        data = response.json()
        
        # --- Catch hidden API-level errors (like Rate Limits) ---
        api_errors = data.get("errors")
        if api_errors:
            if isinstance(api_errors, dict) and len(api_errors) > 0:
                print(f"   🚨 API ERROR on {endpoint}: {api_errors}")
            elif isinstance(api_errors, list) and len(api_errors) > 0:
                print(f"   🚨 API ERROR on {endpoint}: {api_errors}")
                
        return data
    except Exception as e:
        print(f"⚠️ API Fetch Failed ({endpoint}): {e}")
        return None

def inspect_and_sanitize(obj, current_path="root"):
    """
    Recursively walks the JSON tree. If it finds an illegal Firebase key, 
    it fixes it and logs the path.
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
def main(local_memory):
    if not API_KEY:
        print("❌ Missing FOOTBALL_API_KEY. Exiting.")
        return 3600, local_memory 

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
            # Bulletproof status check
            status = ((g.get('fixture') or {}).get('status') or {}).get('short', '')
            synced = g.get('post_game_sync', False)
            
            # If it's a finished game, it MUST be synced. 
            if status in ['FT', 'AET', 'PEN'] and not synced:
                all_done = False
                break
            # If it's not finished and not a dead status, it's still pending.
            elif status not in ['FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD']:
                all_done = False
                break
        
        if all_done and len(check_games) > 0:
            print(f"✅ Date {d_str} is fully synced and finished. Retiring from live polling.")
        else:
            dates_to_process.append(d)

    if not dates_to_process:
        print("💤 All scheduled dates are finished and synced. No API calls needed.")
        return 600, local_memory

    all_new_live_data = {}
    active_games_found = 0
    has_live_games = False
    next_upcoming_ts = None  
    missing_schedule = False
    api_failure = False 
    suspicious_pending_game = False

    # =========================================================
    # 🧠 THE LOCAL MEMORY GATEKEEPER
    # =========================================================
    old_live_data = {}
    if local_memory is None:
        if firebase_admin._apps:
            try:
                print("🗄️ COLD START: Fetching current state from Firebase to initialize memory...")
                fb_state = db.reference('futbol_live_games').get()
                if fb_state and isinstance(fb_state, dict):
                    old_live_data = fb_state
            except Exception as e:
                print(f"⚠️ Failed to fetch memory from Firebase: {e}")
    else:
        old_live_data = local_memory

    for target_date in dates_to_process:
        current_date_str = target_date.strftime("%Y-%m-%d")
        github_raw_url = f"https://raw.githubusercontent.com/dfsstartinglineups/futbolstartingeleven/refs/heads/main/data/games_{current_date_str}.json"
        
        try:
            headers = {'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
            response = requests.get(github_raw_url, headers=headers, timeout=10)
            if response.status_code == 404:
                missing_schedule = True
                continue
            response.raise_for_status()
            daily_games = response.json()
        except Exception as e:
            print(f"⚠️ Failed to fetch schedule from GitHub: {e}")
            missing_schedule = True
            continue
            
        if not daily_games:
            missing_schedule = True
            continue

        fixtures_data = fetch_api(f"fixtures?date={current_date_str}&timezone=America/New_York")
        if not fixtures_data or not fixtures_data.get("response"):
            api_failure = True
            continue
            
        # 🛡️ Crash Protection: Ensure every response item has the expected structure
        live_master_map = {}
        for g in fixtures_data["response"]:
            f_id = (g.get('fixture') or {}).get('id')
            if f_id:
                live_master_map[str(f_id)] = g

        # 🛡️ THE CACHE BUSTER: Overwrite stale crossover games with true real-time clocks
        live_data = fetch_api("fixtures?live=all")
        if live_data and live_data.get("response"):
            for g in live_data["response"]:
                f_id = (g.get('fixture') or {}).get('id')
                if f_id:
                    live_master_map[str(f_id)] = g

        for base_game in daily_games:
            fix_id = str((base_game.get('fixture') or {}).get('id', ''))
            
            # Catch games mysteriously missing from the API feed
            if not fix_id or fix_id not in live_master_map:
                base_status = ((base_game.get('fixture') or {}).get('status') or {}).get('short', '')
                if base_status not in ['FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD']:
                    print(f"👻 [{fix_id}] Missing from live API schedule! Polling directly by ID...")
                    fallback = fetch_api(f"fixtures?id={fix_id}")
                    if fallback and fallback.get("response"):
                        live_master_map[fix_id] = fallback["response"][0]
                        suspicious_pending_game = True
                    else:
                        suspicious_pending_game = True 
                        continue
                else:
                    continue
            
            latest_data = live_master_map[fix_id]
            # Bulletproof status extraction
            status = ((latest_data.get('fixture') or {}).get('status') or {}).get('short', '')
            
            is_playing = status in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT', 'LIVE']
            is_finished = status in ['FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD']
            
            scraper_has_synced = base_game.get('post_game_sync', False)
            
            if is_finished:
                if scraper_has_synced:
                    continue 
                else:
                    memory_is_complete = False
                    if fix_id in old_live_data:
                        mem_game = old_live_data[fix_id]
                        mem_status = ((mem_game.get('fixture') or {}).get('status') or {}).get('short', '')
                        has_events = "events" in mem_game
                        has_team_stats = "team_stats" in mem_game and "home" in mem_game["team_stats"]
                        
                        has_player_stats = False
                        home_start = mem_game.get("homeLineup", {}).get("startXI", [])
                        if home_start and len(home_start) > 0:
                            # Bulletproof live_stats check
                            if "live_stats" in (home_start[0].get("player") or {}):
                                has_player_stats = True
                            
                        if has_events and has_team_stats and has_player_stats and mem_status in ['FT', 'AET', 'PEN']:
                            memory_is_complete = True

                    if memory_is_complete:
                        live_game_obj = old_live_data[fix_id]
                        live_game_obj['fixture']['status'] = latest_data['fixture']['status']
                        live_game_obj['goals'] = latest_data.get('goals', {"home": 0, "away": 0})
                        all_new_live_data[fix_id] = live_game_obj
                        active_games_found += 1 
                        continue 
                    else:
                        print(f"🕵️ [{fix_id}] FT Stats incomplete. Fetching from API...")

            if not is_playing and not is_finished:
                g_ts = (base_game.get('fixture') or {}).get('timestamp', 0)
                
                if status in ['TBD', 'AWD', 'WO'] or g_ts == 0:
                    suspicious_pending_game = True
                    continue
                    
                if g_ts > 0 and g_ts <= now_ts:
                    if (now_ts - g_ts) > 14400:
                        continue
                    has_live_games = True
                elif g_ts > 0:
                    if next_upcoming_ts is None or g_ts < next_upcoming_ts:
                        next_upcoming_ts = g_ts
                continue 

            active_games_found += 1
            has_live_games = True

            if status == 'HT' and fix_id in old_live_data and 'events' in old_live_data[fix_id]:
                live_game_obj = copy.deepcopy(old_live_data[fix_id]) 
                live_game_obj['fixture']['status'] = latest_data['fixture']['status']
                live_game_obj['goals'] = latest_data.get('goals', {"home": 0, "away": 0})
                all_new_live_data[fix_id] = live_game_obj
                continue
            
            home_name = ((latest_data.get('teams') or {}).get('home') or {}).get('name', 'Home')
            away_name = ((latest_data.get('teams') or {}).get('away') or {}).get('name', 'Away')
            print(f"⚽ Processing Live Match: {home_name} vs {away_name} ({status})")
            
            if fix_id in old_live_data and "homeLineup" in old_live_data[fix_id]:
                live_game_obj = copy.deepcopy(old_live_data[fix_id])
            else:
                live_game_obj = copy.deepcopy(base_game)
                
            # Bulletproof raw_status extraction
            raw_status = (latest_data.get('fixture') or {}).get('status') or {}
            
            if raw_status.get('elapsed') is None:
                short_s = raw_status.get('short', '')
                if short_s in ['1H', 'HT']:
                    raw_status['elapsed'] = 45
                elif short_s in ['2H', 'FT', 'AET', 'PEN']:
                    raw_status['elapsed'] = 90
                elif short_s == 'ET':
                    raw_status['elapsed'] = 120
                else:
                    raw_status['elapsed'] = 0 
                    
            live_game_obj['fixture']['status'] = raw_status
            live_game_obj['goals'] = latest_data.get('goals')

            # A. FETCH EVENTS
            events_data = fetch_api(f"fixtures/events?fixture={fix_id}")
            if events_data and isinstance(events_data.get("response"), list) and len(events_data["response"]) > 0:
                parsed_events = []
                for ev in events_data["response"]:
                    if ev.get("type") in ["Goal", "Card", "subst"]:
                        if ev.get("type") == "Goal" and ev.get("detail") == "Missed Penalty": continue
                        
                        # Bulletproof Events Extraction
                        elapsed = (ev.get("time") or {}).get("elapsed", 0)
                        extra = (ev.get("time") or {}).get("extra")
                        display_time = f"{elapsed}+{extra}" if extra else str(elapsed)

                        event_obj = {
                            "time": display_time,
                            "team_id": (ev.get("team") or {}).get("id"),
                            "player": (ev.get("player") or {}).get("name"),
                            "player_id": (ev.get("player") or {}).get("id"),
                            "type": ev.get("type"),
                            "detail": ev.get("detail"),
                            "assist": (ev.get("assist") or {}).get("name")
                        }
                        if ev.get("type") == "subst":
                            event_obj["player_out"] = (ev.get("assist") or {}).get("name")
                            event_obj["player_out_id"] = (ev.get("assist") or {}).get("id")
                        parsed_events.append(event_obj)
                live_game_obj["events"] = parsed_events
                
                # 🔄 PROCESS SUBSTITUTIONS
                for ev in parsed_events:
                    if ev.get("type") == "subst":
                        player_in_id = str(ev.get("player_id", ""))
                        player_out_id = str(ev.get("player_out_id", ""))
                        
                        for side in ["homeLineup", "awayLineup"]:
                            lineup = live_game_obj.get(side)
                            if not lineup: continue
                            
                            # Bulletproof Substitute Matchers
                            in_is_sub = any(str((s.get("player") or {}).get("id")) == player_in_id for s in lineup.get("substitutes", []))
                            out_is_sub = any(str((s.get("player") or {}).get("id")) == player_out_id for s in lineup.get("substitutes", []))
                            in_is_starter = any(str((s.get("player") or {}).get("id")) == player_in_id for s in lineup.get("startXI", []))
                            out_is_starter = any(str((s.get("player") or {}).get("id")) == player_out_id for s in lineup.get("startXI", []))
                            
                            if in_is_starter and out_is_sub:
                                try:
                                    starter_idx = next(i for i, s in enumerate(lineup["startXI"]) if str((s.get("player") or {}).get("id")) == player_in_id)
                                    sub_idx = next(i for i, s in enumerate(lineup["substitutes"]) if str((s.get("player") or {}).get("id")) == player_out_id)
                                    
                                    temp = lineup["startXI"][starter_idx]
                                    lineup["startXI"][starter_idx] = lineup["substitutes"][sub_idx]
                                    lineup["substitutes"][sub_idx] = temp
                                    
                                    in_is_sub, out_is_starter = True, True
                                except StopIteration: pass
                                    
                            if in_is_sub and out_is_starter:
                                try:
                                    incoming_sub = next(s for s in lineup["substitutes"] if str((s.get("player") or {}).get("id")) == player_in_id)
                                    
                                    for slot in lineup["startXI"]:
                                        if str((slot.get("player") or {}).get("id")) == player_out_id:
                                            if "sub_history" not in slot:
                                                slot["sub_history"] = []
                                                
                                            slot["sub_history"].insert(0, slot["player"].copy())
                                            
                                            slot["player"] = incoming_sub["player"]
                                            slot["player"]["isSubbedIn"] = True
                                            slot["player"]["subMinute"] = ev["time"]
                                            slot["player"]["pos"] = slot["sub_history"][0].get("pos", "M")
                                            
                                            lineup["substitutes"] = [s for s in lineup["substitutes"] if str((s.get("player") or {}).get("id")) != player_in_id]
                                            break
                                except StopIteration: pass

            # B. TEAM STATS
            stats_data = fetch_api(f"fixtures/statistics?fixture={fix_id}")
            if stats_data and isinstance(stats_data.get("response"), list) and len(stats_data["response"]) > 0:
                team_stats = {"home": {}, "away": {}}
                
                # Bulletproof Team ID
                home_id = ((latest_data.get("teams") or {}).get("home") or {}).get("id")
                
                for t_stat in stats_data["response"]:
                    t_id = (t_stat.get("team") or {}).get("id")
                    if not t_id: continue
                    side = "home" if t_id == home_id else "away"
                    parsed_t_stats = {"possession": 50, "total_shots": 0, "shots_on_target": 0, "corners": 0, "fouls": 0, "yellow_cards": 0, "red_cards": 0}
                    for s in t_stat.get("statistics", []):
                        val, stype = s.get("value"), s.get("type")
                        if val is None: continue
                        if stype == "Ball Possession": parsed_t_stats["possession"] = int(str(val).replace('%', ''))
                        elif stype == "Total Shots": parsed_t_stats["total_shots"] = int(val)
                        elif stype == "Shots on Goal": parsed_t_stats["shots_on_target"] = int(val)
                        elif stype == "Corner Kicks": parsed_t_stats["corners"] = int(val)
                        elif stype == "Fouls": parsed_t_stats["fouls"] = int(val)
                        elif stype == "Yellow Cards": parsed_t_stats["yellow_cards"] = int(val)
                        elif stype == "Red Cards": parsed_t_stats["red_cards"] = int(val)
                    team_stats[side] = parsed_t_stats
                live_game_obj["team_stats"] = team_stats

            # C. PLAYER STATS
            live_players_data = fetch_api(f"fixtures/players?fixture={fix_id}")
            if live_players_data and live_players_data.get("response"):
                live_player_map = {}
                for tp in live_players_data["response"]:
                    for p in tp.get("players", []):
                        p_id = (p.get("player") or {}).get("id")
                        if not p_id: continue
                        
                        stats_list = p.get("statistics") or []
                        p_stats = stats_list[0] if len(stats_list) > 0 else {}
                        
                        live_player_map[str(p_id)] = {
                            "goals": (p_stats.get("goals") or {}).get("total") or 0,
                            "assists": (p_stats.get("goals") or {}).get("assists") or 0,
                            "total_shots": (p_stats.get("shots") or {}).get("total") or 0,
                            "shots_on_target": (p_stats.get("shots") or {}).get("on") or 0,
                            "passes": (p_stats.get("passes") or {}).get("total") or 0,
                            "key_passes": (p_stats.get("passes") or {}).get("key") or 0,
                            "tackles": (p_stats.get("tackles") or {}).get("total") or 0,
                            "interceptions": (p_stats.get("tackles") or {}).get("interceptions") or 0,
                            "saves": (p_stats.get("goals") or {}).get("saves") or 0,
                            "conceded": (p_stats.get("goals") or {}).get("conceded") or 0,
                            "yellow_cards": (p_stats.get("cards") or {}).get("yellow") or 0,
                            "red_cards": (p_stats.get("cards") or {}).get("red") or 0,
                            "rating": (p_stats.get("games") or {}).get("rating") or "N/A"
                        }

                # Attach and Merge Stats Safely
                for side in ["homeLineup", "awayLineup"]:
                    lineup = live_game_obj.get(side)
                    if not lineup: continue
                    for slot in lineup.get("startXI", []):
                        pid = str((slot.get("player") or {}).get("id", ""))
                        if pid in live_player_map: slot["player"]["live_stats"] = live_player_map[pid]
                        for sub_hist in slot.get("sub_history", []):
                            hid = str(sub_hist.get("id", ""))
                            if hid in live_player_map: sub_hist["live_stats"] = live_player_map[hid]
                    for sub in lineup.get("substitutes", []):
                        sid = str((sub.get("player") or {}).get("id", ""))
                        if sid in live_player_map: sub["player"]["live_stats"] = live_player_map[sid]

            all_new_live_data[fix_id] = live_game_obj

    # =========================================================
    # 3. SECURE PUSH TO FIREBASE (DELTA UPDATES ONLY)
    # =========================================================
    if active_games_found > 0:
        if firebase_admin._apps:
            try:
                delta_payload = {}
                for fix_id, game_data in all_new_live_data.items():
                    if fix_id not in old_live_data or old_live_data[fix_id] != game_data:
                        delta_payload[fix_id] = game_data
                for fix_id in old_live_data:
                    if fix_id not in all_new_live_data:
                        delta_payload[fix_id] = None  
                        
                if delta_payload:
                    safe_delta = inspect_and_sanitize(delta_payload)
                    db.reference('futbol_live_games').update(safe_delta)
                    print(f"🚀 Pushed deltas for {len(delta_payload)} games to Firebase!")
                else:
                    pass 
                    
            except Exception as e:
                print(f"⚠️ Failed to push: {e}")
    else:
        print("\n💤 No active futbol games. Memory will carry over until next kickoff.")

    # 4. SLEEP CALCULATION & LOCAL MEMORY RETURN
    if has_live_games: 
        print("🎯 Target cycle: 30s (Active game updates)...")
        return 30, all_new_live_data 

    if api_failure:
        print("⚠️ API fetch failed. Target cycle: 60s (Retrying)...")
        return 60, all_new_live_data 
        
    if suspicious_pending_game:
        if next_upcoming_ts:
            sleep_time = max(60, min((next_upcoming_ts - now_ts) - 120, 300))
            print(f"🎯 Target cycle: {int(sleep_time)}s (Monitoring delayed games)...")
            return sleep_time, all_new_live_data
        else:
            print("🎯 Target cycle: 300s (Monitoring delayed, TBD, or missing games)...")
            return 300, all_new_live_data
            
    if next_upcoming_ts: 
        sleep_time = max(60, min((next_upcoming_ts - now_ts) - 120, 3600))
        print(f"🎯 Target cycle: {int(sleep_time)}s (Waiting for next scheduled kickoff)...")
        return sleep_time, all_new_live_data

    if missing_schedule: 
        print("🎯 Target cycle: 120s (Waiting for today's JSON schedule to be published)...")
        return 120, all_new_live_data
        
    print("🎯 Target cycle: 3600s (Default sleep - All scheduled games finished)...")
    return 3600, all_new_live_data

if __name__ == "__main__":
    print("⚽ Starting Futbol Live Real-Time Engine...")
    persisted_memory = None
    
    while True:
        try:
            loop_start_time = time.time()
            target_sleep_sec, persisted_memory = main(persisted_memory)
            loop_elapsed = time.time() - loop_start_time
            actual_sleep = max(0.0, target_sleep_sec - loop_elapsed)
            
            if actual_sleep > 0:
                print(f"⏳ Loop took {loop_elapsed:.1f}s. Sleeping remaining {actual_sleep:.1f}s to hit target...")
                time.sleep(actual_sleep)
            else:
                print(f"⚡ Loop took {loop_elapsed:.1f}s! (Exceeded {target_sleep_sec}s target). Restarting IMMEDIATELY!")
                
        except Exception as e:
            print(f"\n❌ Loop crashed: {e}. Restarting in 60s...")
            persisted_memory = None 
            time.sleep(60)

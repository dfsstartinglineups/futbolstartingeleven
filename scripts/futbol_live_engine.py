import os
import json
import requests
import zoneinfo
import time
from datetime import datetime, timedelta
import base64

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

ARCHIVED_DATES = set()

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

def archive_to_github(date_str, json_data):
    """Pushes the final JSON file to the GitHub repository permanently"""
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO") 
    
    if not token or not repo:
        print("⚠️ GitHub credentials missing. Skipping permanent archive.")
        return False

    url = f"https://api.github.com/repos/{repo}/contents/data/LIVE/futbol_live_{date_str}.json"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    sha = None
    get_res = requests.get(url, headers=headers)
    if get_res.status_code == 200:
        sha = get_res.json().get("sha")

    content_b64 = base64.b64encode(json.dumps(json_data, indent=2).encode('utf-8')).decode('utf-8')
    data = {
        "message": f"⚽ Auto-archiving final live futbol data for {date_str}",
        "content": content_b64,
        "branch": "main" 
    }
    if sha: 
        data["sha"] = sha

    put_res = requests.put(url, headers=headers, json=data)
    if put_res.status_code in [200, 201]:
        print(f"📦 Successfully archived Futbol {date_str} to GitHub!")
        return True
    else:
        print(f"❌ Failed to archive to GitHub: {put_res.text}")
        return False

# ==========================================================
# --- CORE ENGINE LOGIC ---
# ==========================================================
def main():
    if not API_KEY:
        print("❌ Missing FOOTBALL_API_KEY. Exiting.")
        return False

    ny_tz = zoneinfo.ZoneInfo("America/New_York")
    now_est = datetime.now(ny_tz)
    
    # 🌙 MIDNIGHT ROLLOVER FIX (Keeps games wrapping past midnight on the same day's file)
    futbol_day = now_est - timedelta(hours=4)
    current_date_str = futbol_day.strftime("%Y-%m-%d")
    
    base_file_path = os.path.join(DATA_DIR, f"games_{current_date_str}.json")
    live_file_path = os.path.join(LIVE_DIR, f"futbol_live_{current_date_str}.json")
    
    # 1. LOAD THE BASELINE (Built by scraper.py)
    if not os.path.exists(base_file_path):
        print(f"💤 No base schedule found for {current_date_str}. Waiting for scraper.py to build it...")
        return False
        
    with open(base_file_path, 'r') as f:
        daily_games = json.load(f)
        
    if not daily_games:
        return False

    # 2. LOAD PREVIOUS LIVE MEMORY (For cooldown tracking)
    old_live_data = {}
    if os.path.exists(live_file_path):
        try:
            with open(live_file_path, 'r') as f:
                old_live_data = json.load(f)
        except: pass

    # 3. FETCH LIVE SCOREBOARD FOR TODAY
    fixtures_data = fetch_api(f"fixtures?date={current_date_str}&timezone=America/New_York")
    if not fixtures_data or not fixtures_data.get("response"):
        return False
        
    live_master_map = {str(g['fixture']['id']): g for g in fixtures_data["response"]}

    new_live_data = {}
    active_games_found = 0

    for base_game in daily_games:
        fix_id = str(base_game['fixture']['id'])
        
        # If the game vanished from the API (rescheduled), skip it
        if fix_id not in live_master_map: continue
        
        latest_data = live_master_map[fix_id]
        status = latest_data['fixture']['status']['short']
        
        is_playing = status in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT']
        is_finished = status in ['FT', 'AET', 'PEN']
        
        # 🛑 10-MINUTE COOLDOWN FOR FINISHED GAMES
        if is_finished:
            if fix_id in old_live_data and 'match_ended_at' in old_live_data[fix_id]:
                ended_time_str = old_live_data[fix_id]['match_ended_at']
                try:
                    ended_time = datetime.fromisoformat(ended_time_str)
                    if now_est > ended_time + timedelta(minutes=10):
                        new_live_data[fix_id] = old_live_data[fix_id]
                        continue # Safely locked. Skip active polling.
                except: pass

        if not is_playing and not is_finished:
            continue # Game is 'NS' (Not Started) or 'PST' (Postponed). Skip polling.

        active_games_found += 1
        
        # --- WE HAVE AN ACTIVE OR RECENTLY FINISHED GAME. LET'S BUILD IT! ---
        print(f"⚽ Processing Live Match: {latest_data['teams']['home']['name']} vs {latest_data['teams']['away']['name']} ({status})")
        
        # Start fresh from the Base Game so substitutions don't infinitely stack
        live_game_obj = dict(base_game) 
        live_game_obj['fixture']['status'] = latest_data['fixture']['status']
        live_game_obj['goals'] = latest_data['goals']
        
        if is_finished and ('match_ended_at' not in old_live_data.get(fix_id, {})):
            live_game_obj['match_ended_at'] = now_est.isoformat()
        elif is_finished:
            live_game_obj['match_ended_at'] = old_live_data[fix_id]['match_ended_at']

        # A. FETCH EVENTS (Goals, Cards, Subs)
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

        # B. FETCH TEAM STATS (Possession, Shots)
        stats_data = fetch_api(f"fixtures/statistics?fixture={fix_id}")
        if stats_data and stats_data.get("response"):
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

        # C. FETCH PLAYER STATS & APPLY SUBSTITUTIONS
        if live_game_obj.get("homeLineup") and live_game_obj.get("awayLineup"):
            live_players_data = fetch_api(f"fixtures/players?fixture={fix_id}")
            live_player_map = {}
            
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

            # Inject Substitutions dynamically into the fresh baseline array
            for ev in parsed_events:
                if ev["type"] == "subst":
                    player_in_id = str(ev["player_id"])
                    player_out_id = str(ev["player_out_id"])
                    
                    for side in ["homeLineup", "awayLineup"]:
                        lineup = live_game_obj[side]
                        
                        in_is_sub = any(str(s["player"]["id"]) == player_in_id for s in lineup.get("substitutes", []))
                        out_is_starter = any(str(s["player"]["id"]) == player_out_id for s in lineup.get("startXI", []))
                        
                        # API Error Correction (Swapped at kickoff)
                        in_is_starter = any(str(s["player"]["id"]) == player_in_id for s in lineup.get("startXI", []))
                        out_is_sub_err = any(str(s["player"]["id"]) == player_out_id for s in lineup.get("substitutes", []))
                        if in_is_starter and out_is_sub_err:
                            s_idx = next(i for i, s in enumerate(lineup["startXI"]) if str(s["player"]["id"]) == player_in_id)
                            sub_idx = next(i for i, s in enumerate(lineup["substitutes"]) if str(s["player"]["id"]) == player_out_id)
                            temp = lineup["startXI"][s_idx]
                            lineup["startXI"][s_idx] = lineup["substitutes"][sub_idx]
                            lineup["substitutes"][sub_idx] = temp
                            in_is_sub, out_is_starter = True, True
                            
                        if in_is_sub and out_is_starter:
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

            # Attach Live Stats
            for side in ["homeLineup", "awayLineup"]:
                lineup = live_game_obj[side]
                for slot in lineup.get("startXI", []):
                    p_id = str(slot["player"]["id"])
                    if p_id in live_player_map: slot["player"]["live_stats"] = live_player_map[p_id]
                    for sub_hist in slot.get("sub_history", []):
                        h_id = str(sub_hist["id"])
                        if h_id in live_player_map: sub_hist["live_stats"] = live_player_map[h_id]
                for sub in lineup.get("substitutes", []):
                    p_id = str(sub["player"]["id"])
                    if p_id in live_player_map: sub["player"]["live_stats"] = live_player_map[p_id]

        # Key the dictionary by fixture_id so script.js can find it effortlessly
        new_live_data[fix_id] = live_game_obj

    # =========================================================
    # THE DOUBLE-WRITE: SAVE TO FILE AND PUSH TO FIREBASE
    # =========================================================
    has_live_games = False

    # 1. ALWAYS SAVE TO FILE IF DATA HAS CHANGED
    if new_live_data and new_live_data != old_live_data:
        with open(live_file_path, 'w') as f:
            json.dump(new_live_data, f, indent=2)
        print(f"\n✅ Successfully updated {live_file_path} with {len(new_live_data)} games.")

    if active_games_found > 0:
        # 2. PUSH TO FIREBASE
        if firebase_admin._apps:
            try:
                ref = db.reference('futbol_live_games')
                ref.set(new_live_data)
                print("🚀 Pushed live futbol data to Firebase!")
            except Exception as e:
                print(f"⚠️ Failed to push to Firebase: {e}")

        # Are there actively playing games, or just games in cooldown?
        has_live_games = any(g['fixture']['status']['short'] in ['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT'] for g in new_live_data.values())
    else:
        global ARCHIVED_DATES
        print("\n💤 No active futbol games right now.")
        
        # 1. Wipe Firebase clean
        if firebase_admin._apps:
            try: db.reference('futbol_live_games').delete()
            except: pass

        # 2. Push permanent archive to GitHub 10 mins after ALL games end
        unstarted_games = sum(1 for e in fixtures_data.get('response', []) if e['fixture']['status']['short'] in ['NS', 'TBD'])
        
        if unstarted_games == 0 and current_date_str not in ARCHIVED_DATES and new_live_data:
            if any(g['fixture']['status']['short'] in ['FT', 'AET', 'PEN'] for g in new_live_data.values()):
                success = archive_to_github(current_date_str, new_live_data)
                if success:
                    ARCHIVED_DATES.add(current_date_str)

    return has_live_games


if __name__ == "__main__":
    print("⚽ Starting Futbol Live Real-Time Engine...")
    while True:
        try:
            needs_fast_poll = main()
            
            # Since API efficiency is not a primary concern (75k limit), we can poll very fast.
            if needs_fast_poll:
                print("⏱️ Fast poll active. Waiting 20 seconds...\n")
                time.sleep(20)
            else:
                print("⏳ No live games. Resting for 2 minutes...\n")
                time.sleep(120)
                
        except KeyboardInterrupt:
            print("\n🛑 Live Engine manually stopped. Exiting.")
            break
        except Exception as e:
            print(f"\n❌ Master loop crashed: {e}. Restarting in 60s...")
            time.sleep(60)

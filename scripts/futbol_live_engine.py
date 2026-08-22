import os
import json
import time
import re
import random
from datetime import datetime, timedelta
import pytz
import asyncio
from curl_cffi import requests
from curl_cffi.requests import AsyncSession
import firebase_admin
from firebase_admin import credentials, db

# ==========================================
# 1. FIREBASE INITIALIZATION & CACHE SETUP
# ==========================================
if not firebase_admin._apps:
    raw_service_key = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    db_url = os.environ.get(
        "FIREBASE_DATABASE_URL", 
        "https://nbastartingfive-8b420-default-rtdb.firebaseio.com"
    )
    if raw_service_key:
        try:
            cred_dict = json.loads(raw_service_key)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {'databaseURL': db_url})
            print("✅ Firebase initialized for Live Futbol Pusher.")
        except Exception as e:
            print(f"❌ Firebase initialization failed: {e}")
            firebase_admin.initialize_app(options={'databaseURL': db_url})
    else:
        firebase_admin.initialize_app(options={'databaseURL': db_url})

# Cache to throttle individual player Core API calls
PLAYER_CORE_CACHE = {}
CORE_STATS_THROTTLE_SEC = 120

# ==========================================
# 2. MATCH CLOCK & DATA HELPERS
# ==========================================
def extract_match_clock(status_obj):
    if not status_obj:
        return "LIVE"
    status_type = status_obj.get('type') or {}
    state = status_type.get('state', 'pre')

    if state == 'pre': return "NS"
    if state == 'post': return "FT"
    if status_type.get('name') == 'STATUS_HALFTIME' or status_type.get('shortDetail') == 'HT':
        return "HT"

    detail = str(status_type.get('detail', ''))
    short_detail = str(status_type.get('shortDetail', ''))
    display_clock = str(status_obj.get('displayClock', ''))

    for string_to_check in [display_clock, short_detail, detail]:
        if '+' in string_to_check:
            clean_str = string_to_check.replace(' ', '').replace("'", "").replace('+', " + ")
            parts = clean_str.split(" + ")
            if len(parts) == 2:
                return f"{parts[0]}' + {parts[1]}'"
            return string_to_check

    if display_clock and ':' in display_clock:
        try:
            mins, secs = map(int, display_clock.split(':'))
            total_mins = mins + (1 if secs > 0 else 0)
            if total_mins > 90 and total_mins < 105 and "ET" not in detail and "Extra" not in detail:
                return f"90' + {total_mins - 90}'"
            elif total_mins > 45 and total_mins < 55 and ("1st" in detail or "Half" in detail):
                return f"45' + {total_mins - 45}'"
            return str(total_mins)
        except: pass

    raw_clock = status_obj.get('clock', 0) or 0
    if raw_clock > 0:
        total_mins = int(raw_clock // 60) + 1
        if total_mins > 90 and total_mins < 105 and "ET" not in detail and "Extra" not in detail:
            return f"90' + {total_mins - 90}'"
        elif total_mins > 45 and total_mins < 55 and ("1st" in detail or "Half" in detail):
            return f"45' + {total_mins - 45}'"

    if short_detail:
        clean_short = short_detail.replace("'", "").replace("Half", "").strip()
        if clean_short.isdigit():
            return clean_short

    if raw_clock > 0:
        return str(int(raw_clock // 60) + 1)

    return "LIVE"

def shorten_player_name(full_name):
    if not full_name: return "Unknown"
    parts = str(full_name).strip().split(' ')
    if len(parts) == 1: return parts[0]
    return f"{parts[0][0].upper()}. {' '.join(parts[1:])}"

def extract_player_live_stats(core_stats):
    live_stats = {}
    if not core_stats or not isinstance(core_stats, dict):
        return live_stats

    def cnum(v):
        try:
            cleaned = re.sub(r'[^0-9.-]', '', str(v))
            return int(float(cleaned)) if cleaned else 0
        except: return 0

    def cflt(v):
        try:
            cleaned = re.sub(r'[^0-9.-]', '', str(v).strip('%'))
            return round(float(cleaned), 2) if cleaned else 0.0
        except: return 0.0

    field_map = {
        'minutes': ('minutes', cnum),
        'touches': ('touches', cnum),
        'expectedGoals': ('xg', cflt),
        'expectedAssists': ('xa', cflt),
        'shotsOnTarget': ('shots_on_target', cnum),
        'totalShots': ('total_shots', cnum),
        'bigChanceCreated': ('bcc', cnum),
        'defensiveInterventions': ('dint', cnum),
        'duelsWon': ('duels_won', cnum),
        'accuratePasses': ('accurate_passes', cnum),
        'effectiveTackles': ('tackles', cnum),
        'totalTackles': ('tackles', cnum),
        'totalGoals': ('goals', cnum),
        'goalAssists': ('assists', cnum),
        'goalsConceded': ('conceded', cnum),
        'saves': ('saves', cnum),
        'expectedGoalsConceded': ('xga', cflt),
        'shotsOnGoalAgainst': ('shots_faced', cnum)
    }

    for raw_k, (out_k, cvt_fn) in field_map.items():
        if raw_k in core_stats:
            val = cvt_fn(core_stats[raw_k])
            live_stats[out_k] = max(live_stats.get(out_k, 0 if cvt_fn == cnum else 0.0), val)

    return live_stats

# ==========================================
# 3. ASYNC STATS & SUMMARY INGESTION
# ==========================================
async def fetch_single_player_core_stats(session, internal_slug, event_id, team_id, player_id, sem):
    url = f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{internal_slug}/events/{event_id}/competitions/{event_id}/competitors/{team_id}/roster/{player_id}/statistics/0"
    async with sem:
        try:
            resp = await session.get(url, timeout=4)
            if resp.status_code == 200:
                data = resp.json()
                stats_dict = {}
                categories = (data.get('splits') or {}).get('categories') or []
                for cat in categories:
                    for stat in cat.get('stats', []):
                        stats_dict[stat.get('name')] = stat.get('value')
                return str(player_id), stats_dict
        except Exception:
            pass
    return str(player_id), {}

async def get_core_stats_concurrently(internal_slug, event_id, player_list):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    sem = asyncio.Semaphore(10)
    async with AsyncSession(headers=headers, impersonate="chrome") as session:
        tasks = [
            fetch_single_player_core_stats(session, internal_slug, event_id, tid, pid, sem) 
            for tid, pid in player_list
        ]
        results = await asyncio.gather(*tasks)
        return {pid: stats for pid, stats in results if stats}

def parse_live_match_summary(event_id):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9'
    }
    url = f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={event_id}"
    try:
        r = requests.get(url, headers=headers, impersonate="chrome", timeout=5)
        if r.status_code != 200: return None
        data = r.json()
    except:
        return None

    try:
        header = data.get('header', {})
        comp_list = header.get('competitions', [{}])
        comp_head = comp_list[0] if comp_list else {}
        status_obj = comp_head.get('status', {})
        game_state = (status_obj.get('type') or {}).get('state', 'pre')

        internal_slug = (header.get('league') or {}).get('slug', '')

        # Live score & Team info extraction (THE FIX)
        scores = {"home": 0, "away": 0}
        teams_info = {"home": {"id": "", "name": ""}, "away": {"id": "", "name": ""}}
        
        for comp in comp_head.get('competitors', []):
            ha = comp.get('homeAway')
            if ha in ['home', 'away']:
                t_obj = comp.get('team') or {}
                teams_info[ha]["id"] = str(t_obj.get('id', ''))
                teams_info[ha]["name"] = t_obj.get('displayName') or t_obj.get('name') or ''
                
                if comp.get('score') is not None:
                    try: scores[ha] = int(comp.get('score'))
                    except: pass

        # Team stats extraction
        team_stats = {
            "home": {"possession": 50, "total_shots": 0, "shots_on_target": 0, "corners": 0, "yellow_cards": 0, "red_cards": 0},
            "away": {"possession": 50, "total_shots": 0, "shots_on_target": 0, "corners": 0, "yellow_cards": 0, "red_cards": 0}
        }
        teams_box = (data.get('boxscore') or {}).get('teams', [])
        if len(teams_box) == 2:
            def extract_stat_dict(slist): return {s.get('name'): s.get('displayValue', '0') for s in slist if isinstance(s, dict)}
            h_idx = 0 if teams_box[0].get('homeAway') == 'home' else 1
            a_idx = 1 if h_idx == 0 else 0
            h_raw = extract_stat_dict(teams_box[h_idx].get('statistics', []))
            a_raw = extract_stat_dict(teams_box[a_idx].get('statistics', []))

            def clean_n(v):
                try: return int(float(re.sub(r'[^0-9.]', '', str(v))))
                except: return 0

            team_stats = {
                "home": {"possession": clean_n(h_raw.get('possessionPct', 50)), "total_shots": clean_n(h_raw.get('totalShots', 0)), "shots_on_target": clean_n(h_raw.get('shotsOnTarget', 0)), "corners": clean_n(h_raw.get('cornerKicks', 0)), "yellow_cards": clean_n(h_raw.get('yellowCards', 0)), "red_cards": clean_n(h_raw.get('redCards', 0))},
                "away": {"possession": clean_n(a_raw.get('possessionPct', 50)), "total_shots": clean_n(a_raw.get('totalShots', 0)), "shots_on_target": clean_n(a_raw.get('shotsOnTarget', 0)), "corners": clean_n(a_raw.get('cornerKicks', 0)), "yellow_cards": clean_n(a_raw.get('yellowCards', 0)), "red_cards": clean_n(a_raw.get('redCards', 0))}
            }

        # Events extraction + sub tracking
        subbed_in_set = set()
        events_list = []
        key_events = data.get('keyEvents', [])
        if isinstance(key_events, list):
            for ev in key_events:
                ev_text = (ev.get('type') or {}).get('text', '').lower()
                is_goal = "goal" in ev_text or "penalty - scored" in ev_text
                is_sub = "substitution" in ev_text or "sub" in ev_text
                is_card = "card" in ev_text
                if not (is_goal or is_sub or is_card): continue

                ev_type = "Goal" if is_goal else ("subst" if is_sub else ("Red Card" if "red" in ev_text else "Yellow Card"))
                parts = ev.get('participants', [])
                p_in = (parts[0].get('athlete') or {}).get('displayName', '') if parts else ''
                p_out = (parts[1].get('athlete') or {}).get('displayName', '') if len(parts) > 1 else ''

                if is_sub:
                    if parts: subbed_in_set.add(str((parts[0].get('athlete') or {}).get('id', '')))
                    if p_in: subbed_in_set.add(p_in.lower())

                events_list.append({
                    "time": (ev.get('clock') or {}).get('displayValue', "0'").replace("'", ""),
                    "team_id": str((ev.get('team') or {}).get('id', '')),
                    "type": ev_type,
                    "player": p_out if ev_type == "subst" else p_in,
                    "player_out": p_in if ev_type == "subst" else None,
                    "assist": p_out if ev_type == "Goal" else None
                })

        # Core player stats extraction
        player_live_stats = {}
        now_ts = time.time()
        cached_player_data = PLAYER_CORE_CACHE.get(str(event_id), {})
        last_fetched = cached_player_data.get('last_fetched', 0)

        if (now_ts - last_fetched) > CORE_STATS_THROTTLE_SEC:
            rosters = data.get('rosters', [])
            if isinstance(rosters, list) and len(rosters) >= 2 and internal_slug:
                active_players = []
                for r_data in rosters:
                    t_id = str((r_data.get('team') or {}).get('id', ''))
                    for entry in r_data.get('roster', []):
                        ath = entry.get('athlete') or {}
                        p_id = str(ath.get('id', ''))
                        p_name = ath.get('displayName', '')
                        if entry.get('starter') or entry.get('subbedIn') or entry.get('didPlay') or entry.get('played') or (p_id in subbed_in_set or p_name.lower() in subbed_in_set):
                            if t_id and p_id: 
                                active_players.append((t_id, p_id))

                if active_players:
                    try:
                        raw_core = asyncio.run(get_core_stats_concurrently(internal_slug, event_id, active_players))
                        for pid, s_dict in raw_core.items():
                            player_live_stats[pid] = extract_player_live_stats(s_dict)
                            
                        PLAYER_CORE_CACHE[str(event_id)] = {
                            'last_fetched': now_ts,
                            'stats': player_live_stats
                        }
                    except Exception as e:
                        print(f"⚠️ Core stats fetch error for event {event_id}: {e}")
                        player_live_stats = cached_player_data.get('stats', {})
        else:
            player_live_stats = cached_player_data.get('stats', {})

        clock_str = extract_match_clock(status_obj)

        return {
            "id": str(event_id),
            "state": game_state,
            "status_short": (status_obj.get('type') or {}).get('shortDetail', 'LIVE'),
            "clock": clock_str,
            "scores": scores,
            "teams": teams_info, # THIS ALLOWS THE JS TO BUILD THE ACCORDION!
            "team_stats": team_stats,
            "events": events_list,
            "player_stats": player_live_stats,
            "updated_at": int(time.time())
        }
    except Exception as e:
        print(f"❌ Error parsing summary for event {event_id}: {e}")
        return None

# ==========================================
# 4. MAIN REALTIME ENGINE
# ==========================================
def main():
    print("🚀 Starting Render Live Futbol Pusher Engine...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    }
    
    while True:
        try:
            est = pytz.timezone('America/New_York')
            now_est = datetime.now(est)
            today_str = now_est.strftime('%Y%m%d')

            # Fetch Today's master scoreboard
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={today_str}&limit=1000"
            res = requests.get(url, headers=headers, impersonate="chrome", timeout=8)
            
            if res.status_code != 200:
                print(f"⚠️ Scoreboard returned status {res.status_code}. Sleeping 30s...")
                time.sleep(30)
                continue

            events = res.json().get('events', [])
            live_event_ids = []

            for ev in events:
                state = ((ev.get('status') or {}).get('type') or {}).get('state', 'pre')
                ev_id = str(ev.get('id', ''))
                
                # Fetch if match is in-progress
                if state == 'in':
                    live_event_ids.append(ev_id)

            if not live_event_ids:
                print(f"[{now_est.strftime('%I:%M:%S %p')}] 💤 No live matches in progress. Sleeping 60s...")
                time.sleep(60)
                continue

            print(f"[{now_est.strftime('%I:%M:%S %p')}] ⚡ {len(live_event_ids)} LIVE match(es) active. Syncing with Firebase...")
            
            updates = {}
            for ev_id in live_event_ids:
                payload = parse_live_match_summary(ev_id)
                if payload:
                    updates[f"live_futbol/{ev_id}"] = payload

            if updates:
                db.reference().update(updates)
                print(f"  └─ ✅ Successfully updated {len(updates)} live matches (including player stats) in Firebase.")

            # Fast polling interval during live matches with random jitter (20 to 30 seconds)
            sleep_duration = random.uniform(20, 30)
            time.sleep(sleep_duration)

        except Exception as e:
            print(f"❌ Worker loop exception: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()

import os
import re
import json
import requests
import unicodedata
from datetime import datetime, timedelta
import pytz
import asyncio
import aiohttp
import hashlib
from jinja2 import Template

HUMAN_LEAGUE_FLAGS = {
    "afc asian cup": "https://a.espncdn.com/combiner/i?img=/i/leaguelogos/soccer/500/2243.png",
    "afc asian cup qualifiers": "https://a.espncdn.com/i/leaguelogos/soccer/500/2246.png",
    "afc champions league elite": "https://a.espncdn.com/i/leaguelogos/soccer/500/2200.png",
    "afc champions league two": "https://a.espncdn.com/i/leaguelogos/soccer/500/2243.png",
    "asean championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/2261.png",
    "africa cup of nations": "https://a.espncdn.com/i/leaguelogos/soccer/500/76.png",
    "argentine copa de la superliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/2407.png",
    "argentine liga profesional de fútbol": "https://a.espncdn.com/i/leaguelogos/soccer/500/1.png",
    "argentine nacional b": "https://a.espncdn.com/i/leaguelogos/soccer/500/2294.png",
    "argentine primera b": "https://a.espncdn.com/i/leaguelogos/soccer/500/2308.png",
    "argentine supercopa": "https://a.espncdn.com/i/leaguelogos/soccer/500/2343.png",
    "australian a-league men": "https://a.espncdn.com/i/leaguelogos/soccer/500/1308.png",
    "australian a-league women": "https://a.espncdn.com/i/leaguelogos/soccer/500/2402.png",
    "austrian bundesliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/5.png",
    "belgian pro league": "https://a.espncdn.com/i/leaguelogos/soccer/500/6.png",
    "bolivian liga profesional": "https://a.espncdn.com/i/leaguelogos/soccer/500/1949.png",
    "brazilian campeonato carioca": "https://a.espncdn.com/i/leaguelogos/soccer/500/2265.png",
    "brazilian campeonato gaucho": "https://a.espncdn.com/i/leaguelogos/soccer/500/2272.png",
    "brazilian campeonato mineiro": "https://a.espncdn.com/i/leaguelogos/soccer/500/2360.png",
    "brazilian campeonato paulista": "https://a.espncdn.com/i/leaguelogos/soccer/500/2322.png",
    "brazilian serie a": "https://a.espncdn.com/i/leaguelogos/soccer/500/85.png",
    "brazilian serie b": "https://a.espncdn.com/i/leaguelogos/soccer/500/2299.png",
    "caf champions league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2391.png",
    "conmebol libertadores": "https://a.espncdn.com/i/leaguelogos/soccer/500/58.png",
    "conmebol pre-olympic tournament": "https://a.espncdn.com/i/leaguelogos/soccer/500/19727.png",
    "conmebol recopa": "https://a.espncdn.com/i/leaguelogos/soccer/500/2335.png",
    "conmebol sudamericana": "https://a.espncdn.com/i/leaguelogos/soccer/500/1208.png",
    "chilean primera división": "https://a.espncdn.com/i/leaguelogos/soccer/500/86.png",
    "chinese super league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2350.png",
    "colombian primera a": "https://a.espncdn.com/i/leaguelogos/soccer/500/1543.png",
    "colombian superliga": "https://a.espncdn.com/i/leaguelogos/soccer/500-dark/2405.png",
    "concacaf champions cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2298.png",
    "concacaf gold cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/59.png",
    "concacaf nations league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2406.png",
    "concacaf w championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/18969.png",
    "copa américa": "https://a.espncdn.com/i/leaguelogos/soccer/500/83.png",
    "copa argentina": "https://a.espncdn.com/i/leaguelogos/soccer/500/2320.png",
    "copa chile": "https://a.espncdn.com/i/leaguelogos/soccer/500/2331.png",
    "copa colombia": "https://a.espncdn.com/i/leaguelogos/soccer/500/2332.png",
    "copa do brasil": "https://a.espncdn.com/i/leaguelogos/soccer/500/528.png",
    "coppa italia": "https://a.espncdn.com/i/leaguelogos/soccer/500/2192.png",
    "costa rican primera division": "https://a.espncdn.com/i/leaguelogos/soccer/500/2245.png",
    "coupe de france": "https://a.espncdn.com/i/leaguelogos/soccer/500/182.png",
    "dutch eredivisie": "https://a.espncdn.com/i/leaguelogos/soccer/500/11.png",
    "dutch knvb beker": "https://a.espncdn.com/i/leaguelogos/soccer/500/2196.png",
    "dutch keuken kampioen divisie": "https://a.espncdn.com/i/leaguelogos/soccer/500/105.png",
    "dutch vrouwen eredivisie": "https://a.espncdn.com/i/leaguelogos/soccer/500/2453.png",
    "english carabao cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/41.png",
    "english efl trophy": "https://a.espncdn.com/i/leaguelogos/soccer/500/42.png",
    "english fa cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/40.png",
    "english league championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/24.png",
    "english league one": "https://a.espncdn.com/i/leaguelogos/soccer/500/25.png",
    "english league two": "https://a.espncdn.com/i/leaguelogos/soccer/500/26.png",
    "english premier league": "https://a.espncdn.com/i/leaguelogos/soccer/500/23.png",
    "english women's super league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2314.png",
    "fifa club world cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/1932.png",
    "fifa under-17 world cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2288.png",
    "fifa under-20 world cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2285.png",
    "fifa women's world cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/60.png",
    "fifa world cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/4.png",
    "french ligue 1": "https://a.espncdn.com/i/leaguelogos/soccer/500/9.png",
    "french ligue 2": "https://a.espncdn.com/i/leaguelogos/soccer/500/96.png",
    "german 2. bundesliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/97.png",
    "german bundesliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/10.png",
    "german cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2061.png",
    "greek super league": "https://a.espncdn.com/i/leaguelogos/soccer/500/98.png",
    "italian serie a": "https://a.espncdn.com/i/leaguelogos/soccer/500/12.png",
    "italian serie b": "https://a.espncdn.com/i/leaguelogos/soccer/500/99.png",
    "japanese j.league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2199.png",
    "leagues cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2410.png",
    "liga mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/22.png",
    "liga bbva mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/22.png",
    "mls": "https://a.espncdn.com/i/leaguelogos/soccer/500/19.png",
    "nwsl": "https://a.espncdn.com/i/leaguelogos/soccer/500/2323.png",
    "portuguese primeira liga": "https://a.espncdn.com/i/leaguelogos/soccer/500/14.png",
    "saudi pro league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2488.png",
    "scottish premiership": "https://a.espncdn.com/i/leaguelogos/soccer/500/45.png",
    "spanish copa del rey": "https://a.espncdn.com/i/leaguelogos/soccer/500/80.png",
    "spanish laliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/15.png",
    "spanish laliga 2": "https://a.espncdn.com/i/leaguelogos/soccer/500/107.png",
    "swedish allsvenskan": "https://a.espncdn.com/i/leaguelogos/soccer/500/16.png",
    "turkish super lig": "https://a.espncdn.com/i/leaguelogos/soccer/500/18.png",
    "uefa champions league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2.png",
    "uefa conference league": "https://a.espncdn.com/i/leaguelogos/soccer/500/20296.png",
    "uefa europa league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2310.png",
    "usl championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/2292.png",
}

COUNTRY_FLAG_URLS = {
    "belgian": "be", "chilean": "cl", "chinese": "cn", "dutch": "nl",
    "english": "gb-eng", "french": "fr", "german": "de", "bolivian": "bo",
    "norwegian": "no", "russian": "ru", "portuguese": "pt", "scottish": "gb-sct",
    "swedish": "se", "argentine": "ar", "brazilian": "br", "italian": "it",
    "mexican": "mx", "paraguayan": "py", "japanese": "jp", "spanish": "es",
    "danish": "dk", "indian": "in", "uruguay": "uy", "peruvian": "pe",
    "salvadoran": "sv", "costa rican": "cr"
}

def normalize_text(text):
    if not text: return ""
    nfkd_form = unicodedata.normalize('NFD', text)
    return "".join([c for c in nfkd_form if unicodedata.category(c) != 'Mn']).lower().strip()

NORMALIZED_HUMAN_LEAGUE_FLAGS = {
    normalize_text(key): val for key, val in HUMAN_LEAGUE_FLAGS.items()
}

def get_local_image_url(url, subfolder="images/teams"):
    """
    Downloads an external image to a local directory during SSG build
    and returns the relative web path for the HTML tag.
    """
    if not url or not url.startswith('http'):
        return url

    # Target folder path on disk: v2/images/teams or v2/images/leagues
    local_dir = os.path.join("v2", subfolder)
    os.makedirs(local_dir, exist_ok=True)
    
    # Extract extension or default to .png
    ext = url.split('.')[-1].split('?')[0].lower()
    if ext not in ['png', 'jpg', 'jpeg', 'svg', 'webp']:
        ext = 'png'
    
    # Generate unique 12-char filename based on original URL
    filename = f"{hashlib.md5(url.encode()).hexdigest()[:12]}.{ext}"
    local_file_path = os.path.join(local_dir, filename)
    
    # HTML src path (e.g. "images/teams/a1b2c3d4e5f6.png")
    web_path = f"{subfolder}/{filename}"

    # Download only if we don't already have it locally
    if not os.path.exists(local_file_path):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                with open(local_file_path, 'wb') as f:
                    f.write(resp.content)
                return web_path
        except Exception:
            return url # Graceful fallback to original URL if download fails

    return web_path

# ====================================================================
# ASYNC CORE API PLAYER STATS FETCHER
# ====================================================================
async def fetch_single_player_core_stats(session, internal_slug, event_id, team_id, player_id):
    url = f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{internal_slug}/events/{event_id}/competitions/{event_id}/competitors/{team_id}/roster/{player_id}/statistics/0"
    try:
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                stats_dict = {}
                for cat in data.get('splits', {}).get('categories', []):
                    for stat in cat.get('stats', []):
                        stats_dict[stat.get('name')] = stat.get('value')
                return str(player_id), stats_dict
    except Exception:
        pass
    return str(player_id), {}

async def get_core_stats_concurrently(internal_slug, event_id, player_list):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [
            fetch_single_player_core_stats(session, internal_slug, event_id, tid, pid) 
            for tid, pid in player_list
        ]
        results = await asyncio.gather(*tasks)
        return {pid: stats for pid, stats in results if stats}

# ====================================================================
# HELPER UTILITIES & GROUPING
# ====================================================================
def create_slug(name):
    if not name: return ""
    slug = name.lower()
    slug = re.sub(r'[\/]', '-', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')

def get_position_category(raw_pos):
    if not raw_pos: return 'M'
    p = str(raw_pos).strip().upper()
    if p in ['G', 'GK', 'GOALKEEPER']: return 'G'
    if any(term in p for term in ['CF', 'ST', 'FW', 'LW', 'RW', 'WF', 'SS', 'ATT', 'STR', 'AM', 'CAM']) or p == 'F': return 'F'
    if any(term in p for term in ['CD', 'CB', 'LB', 'RB', 'WB', 'SW', 'DF', 'DEF']) or p == 'D': return 'D'
    return 'M'

def is_valid_sub_minute(minute_val):
    if not minute_val: return False
    cleaned = re.sub(r'[^0-9]', '', str(minute_val))
    return int(cleaned) > 0 if cleaned else False

def extract_match_clock(status_obj):
    if not status_obj: return "LIVE"
    status_type = status_obj.get('type', {})
    state = status_type.get('state', 'pre')
    if state == 'pre': return "NS"
    if state == 'post': return "FT"
    if status_type.get('name') == 'STATUS_HALFTIME' or status_type.get('shortDetail') == 'HT': return "HT"

    short_detail = status_type.get('shortDetail', '')
    if short_detail:
        tick_match = re.search(r"(\d+\+?\d*)\'", short_detail)
        if tick_match: return tick_match.group(1)
        nums = re.findall(r"\d+", short_detail)
        if len(nums) > 1: return nums[-1]
        elif len(nums) == 1 and "Half" not in short_detail: return nums[0]

    display_clock = status_obj.get('displayClock', '')
    if display_clock:
        if ':' in str(display_clock):
            try:
                mins, secs = map(int, display_clock.split(':'))
                total_mins = mins + (1 if secs > 0 else 0)
                return str(total_mins)
            except: pass
        return str(display_clock).replace("'", "")

    raw_clock = status_obj.get('clock', 0)
    if raw_clock > 0:
        return str(int(raw_clock // 60) + 1)
    return "LIVE"

def generate_league_abbrev(name):
    if not name or name == "Global Football": return "GLB"
    name_upper = name.upper()
    overrides = {
        "ENGLISH PREMIER LEAGUE": "EPL", "SCOTTISH PREMIERSHIP": "SCO", "RUSSIAN PREMIER": "RUS", "PREMIER LEAGUE": "EPL", 
        "BRAZILIAN SERIE A": "BSA", "ECUADORIAN SERIE A": "ECU", "ITALIAN SERIE A": "SERA", "SERIE A": "SERA", 
        "MEXICAN LIGA BBVA MX": "LMX", "SPANISH LALIGA": "LIGA", "LALIGA": "LIGA", "GERMAN BUNDESLIGA": "BUND",
        "BUNDESLIGA": "BUND", "FRENCH LIGUE 1": "LIG1", "LIGUE 1": "LIG1", "MAJOR LEAGUE SOCCER": "MLS", "MLS": "MLS",
        "UEFA CHAMPIONS LEAGUE": "UCL", "UEFA EUROPA LEAGUE": "UEL", "DUTCH EREDIVISIE": "ERED"
    }
    for k, v in overrides.items():
        if k in name_upper: return v
    clean_name = re.sub(r'\b(THE|OF|AND|FOR|MEN|WOMEN|MENS|WOMENS|DEL|LA)\b', '', name_upper).strip()
    words = clean_name.split()
    if len(words) >= 3: return "".join([w[0] for w in words[:3]])
    elif len(words) == 2: return words[0][:3]
    elif len(words) == 1: return words[0][:4]
    return name[:4].upper()

def get_3day_dates():
    est = pytz.timezone('America/New_York')
    now = datetime.now(est)
    if now.hour < 3: now -= timedelta(days=1)
    y_dt = now - timedelta(days=1)
    t_dt = now
    tm_dt = now + timedelta(days=1)
    return {
        "dates": {"yesterday": y_dt.strftime('%Y%m%d'), "today": t_dt.strftime('%Y%m%d'), "tomorrow": tm_dt.strftime('%Y%m%d')},
        "display": {"yesterday": y_dt.strftime('%a, %b %d'), "today": t_dt.strftime('%a, %b %d'), "tomorrow": tm_dt.strftime('%a, %b %d')}
    }

def should_fetch_summary(event):
    status_obj = event.get('status', {})
    status_type = status_obj.get('type', {})
    state = status_type.get('state', 'pre')
    if state in ['in', 'post']: return True, f"State is '{state}'"
    if state == 'pre':
        event_date_str = event.get('date')
        if event_date_str:
            try:
                event_dt = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
                now_utc = datetime.now(pytz.utc)
                minutes_until_kickoff = (event_dt - now_utc).total_seconds() / 60.0
                if minutes_until_kickoff <= 60: return True, f"Pre-game, starting in {int(minutes_until_kickoff)} mins"
                return False, f"Pre-game (>60m)"
            except Exception as e: return False, f"Date parse error: {e}"
    return False, f"State '{state}' not eligible"

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

def parse_espn_summary(event_id):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    summary_data = {
        "team_stats": None, "homeLineup": None, "awayLineup": None, "events": [],
        "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
        "injuries": {"home": [], "away": []}, "live_score": {}, "status_obj": None
    }
    
    url = f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={event_id}"
    try:
        r = requests.get(url, headers=headers, timeout=6)
        if r.status_code != 200: return summary_data
        data = r.json()
    except:
        return summary_data

    try:
        comp_head = data.get('header', {}).get('competitions', [{}])[0]
        summary_data["status_obj"] = comp_head.get('status', {})
        game_state = comp_head.get('status', {}).get('type', {}).get('state', 'pre')

        internal_slug = data.get('header', {}).get('league', {}).get('slug', '')

        live_scores = {}
        for comp in comp_head.get('competitors', []):
            if comp.get('homeAway') in ['home', 'away'] and comp.get('score') is not None:
                try: live_scores[comp.get('homeAway')] = int(comp.get('score'))
                except: pass
        if live_scores: summary_data["live_score"] = live_scores

        teams_box = data.get('boxscore', {}).get('teams', [])
        if len(teams_box) == 2:
            def extract_stat_dict(stats_list): return {s.get('name'): s.get('displayValue', '0') for s in stats_list if isinstance(s, dict)}
            h_idx = 0 if teams_box[0].get('homeAway') == 'home' else 1
            a_idx = 1 if h_idx == 0 else 0
            h_raw = extract_stat_dict(teams_box[h_idx].get('statistics', []))
            a_raw = extract_stat_dict(teams_box[a_idx].get('statistics', []))

            def clean_num(val_str):
                try: return int(float(re.sub(r'[^0-9.]', '', str(val_str))))
                except: return 0

            if h_raw or a_raw:
                summary_data["team_stats"] = {
                    "home": {"possession": clean_num(h_raw.get('possessionPct', 50)), "total_shots": clean_num(h_raw.get('totalShots', 0)), "shots_on_target": clean_num(h_raw.get('shotsOnTarget', 0)), "corners": clean_num(h_raw.get('cornerKicks', 0)), "yellow_cards": clean_num(h_raw.get('yellowCards', 0)), "red_cards": clean_num(h_raw.get('redCards', 0))},
                    "away": {"possession": clean_num(a_raw.get('possessionPct', 50)), "total_shots": clean_num(a_raw.get('totalShots', 0)), "shots_on_target": clean_num(a_raw.get('shotsOnTarget', 0)), "corners": clean_num(a_raw.get('cornerKicks', 0)), "yellow_cards": clean_num(a_raw.get('yellowCards', 0)), "red_cards": clean_num(a_raw.get('redCards', 0))}
                }

        sub_to_starter = {}
        subbed_in, subbed_out = set(), set()
        key_events = data.get('keyEvents', [])
        if isinstance(key_events, list):
            for ev in key_events:
                ev_text = ev.get('type', {}).get('text', '').lower()
                if "substitution" in ev_text or "sub" in ev_text:
                    parts = ev.get('participants', [])
                    if len(parts) >= 2:
                        p_in = parts[0].get('athlete', {}).get('displayName', '').lower()
                        p_out = parts[1].get('athlete', {}).get('displayName', '').lower()
                        if p_in and p_out: sub_to_starter[p_in] = p_out
                        subbed_in.add(p_in); subbed_in.add(str(parts[0].get('athlete', {}).get('id', '')))
                        subbed_out.add(p_out); subbed_out.add(str(parts[1].get('athlete', {}).get('id', '')))

        rosters = data.get('rosters', [])
        if isinstance(rosters, list) and len(rosters) >= 2:
            
            core_stats_cache = {}
            if game_state != 'pre' and internal_slug:
                active_player_list = []
                for r_data in rosters:
                    t_id = str(r_data.get('team', {}).get('id', ''))
                    for entry in r_data.get('roster', []):
                        ath = entry.get('athlete', {})
                        p_id = str(ath.get('id', ''))
                        p_name = ath.get('displayName', '')
                        if entry.get('starter') or entry.get('subbedIn') or entry.get('didPlay') or entry.get('played') or (p_id in subbed_in or p_name.lower() in subbed_in):
                            if t_id and p_id:
                                active_player_list.append((t_id, p_id))

                if active_player_list:
                    try:
                        core_stats_cache = asyncio.run(get_core_stats_concurrently(internal_slug, event_id, active_player_list))
                    except Exception:
                        pass

            for r_data in rosters:
                ha = r_data.get('homeAway', 'home')
                team_obj = r_data.get('team', {})
                start_xi, subs = [], []
                starters_look = {}
                
                for entry in r_data.get('roster', []):
                    if not entry.get('starter', False): continue
                    ath = entry.get('athlete', {})
                    p_id = str(ath.get('id', ''))
                    p_name = ath.get('displayName', 'Unknown')
                    pos = entry.get('position', {}).get('abbreviation') or ath.get('position', {}).get('abbreviation') or 'M'
                    
                    sub_in_flag = entry.get('subbedIn', False)
                    sub_in = sub_in_flag or (game_state != 'pre' and (p_id in subbed_in or p_name.lower() in subbed_in or is_valid_sub_minute(entry.get('subbedInMinute'))))
                    sub_out = game_state != 'pre' and (p_id in subbed_out or p_name.lower() in subbed_out or is_valid_sub_minute(entry.get('subbedOutMinute')))
                    
                    p_stats = extract_player_live_stats(core_stats_cache.get(p_id))
                    
                    p_obj = {
                        "id": p_id, "name": p_name, "pos": pos.upper(), "category": get_position_category(pos),
                        "number": str(entry.get('jersey', '')), "photo": ath.get('headshot', {}).get('href', '') if isinstance(ath.get('headshot'), dict) else '',
                        "live_stats": p_stats,
                        "isSubbedIn": sub_in, "isSubbedOut": sub_out, "subMinute": str(entry.get('subbedInMinute') or entry.get('subbedOutMinute') or '')
                    }
                    start_xi.append({"player": p_obj})
                    starters_look[p_name.lower()] = p_obj

                for entry in r_data.get('roster', []):
                    if entry.get('starter', False): continue
                    ath = entry.get('athlete', {})
                    p_id = str(ath.get('id', ''))
                    p_name = ath.get('displayName', 'Unknown')
                    pos = ath.get('position', {}).get('abbreviation') or entry.get('position', {}).get('abbreviation') or 'M'
                    if pos.upper() in ['SUB', 'S', 'SUBSTITUTE', '']:
                        replaced = sub_to_starter.get(p_name.lower())
                        pos_cat = starters_look[replaced]['category'] if replaced in starters_look else 'M'
                    else: pos_cat = get_position_category(pos)
                    
                    sub_in_flag = entry.get('subbedIn', False)
                    sub_in = sub_in_flag or (game_state != 'pre' and (p_id in subbed_in or p_name.lower() in subbed_in or is_valid_sub_minute(entry.get('subbedInMinute'))))
                    sub_out = game_state != 'pre' and (p_id in subbed_out or p_name.lower() in subbed_out or is_valid_sub_minute(entry.get('subbedOutMinute')))
                    
                    p_stats = extract_player_live_stats(core_stats_cache.get(p_id))
                    
                    if entry.get('didPlay') or entry.get('played') or sub_in or p_stats:
                        subs.append({"player": {
                            "id": p_id, "name": p_name, "pos": pos.upper(), "category": pos_cat,
                            "number": str(entry.get('jersey', '')), "photo": ath.get('headshot', {}).get('href', '') if isinstance(ath.get('headshot'), dict) else '',
                            "live_stats": p_stats, "isSubbedIn": sub_in, "isSubbedOut": sub_out, "subMinute": str(entry.get('subbedInMinute') or entry.get('subbedOutMinute') or '')
                        }})
                
                if start_xi: summary_data["homeLineup" if ha == 'home' else "awayLineup"] = {"formation": r_data.get('formation', '4-3-3'), "team": {"colors": {"player": {"primary": team_obj.get('color', '0d6efd')}}}, "startXI": start_xi, "substitutes": subs}

        if isinstance(key_events, list) and key_events:
            for ev in key_events:
                ev_text = ev.get('type', {}).get('text', '').lower()
                is_goal = "goal" in ev_text or "penalty - scored" in ev_text
                is_sub = "substitution" in ev_text or "sub" in ev_text
                is_card = "card" in ev_text
                if not (is_goal or is_sub or is_card): continue
                
                ev_type = "Goal" if is_goal else ("subst" if is_sub else ("Red Card" if "red" in ev_text else "Yellow Card"))
                parts = ev.get('participants', [])
                p_in = parts[0].get('athlete', {}).get('displayName', '') if parts else ''
                if not p_in and parts: p_in = parts[0].get('coach', {}).get('displayName', '')
                p_out = parts[1].get('athlete', {}).get('displayName', '') if len(parts) > 1 else ''
                
                p_player = p_out if ev_type == "subst" else p_in
                if not p_player:
                    raw_text = ev.get('shortText') or ev.get('text') or ''
                    p_player = raw_text.split(" - ")[-1].strip() if " - " in raw_text else (raw_text[:20]+'...' if len(raw_text)>20 else raw_text)
                
                summary_data["events"].append({
                    "time": ev.get('clock', {}).get('displayValue', "0'").replace("'", ""), "team_id": str(ev.get('team', {}).get('id', '')),
                    "type": ev_type, "detail": ev.get('type', {}).get('text', ''), "player": p_player,
                    "player_out": p_in if ev_type == "subst" else (p_out if p_out else None), "assist": p_out if ev_type == "Goal" else None
                })

        pickcenter = data.get('pickcenter', []) or data.get('odds', [])
        if isinstance(pickcenter, list) and pickcenter:
            odds_item = pickcenter[0]
            summary_data["odds"] = {
                "home": f"+{odds_item.get('homeTeamOdds', {}).get('moneyLine')}" if odds_item.get('homeTeamOdds', {}).get('moneyLine') and int(odds_item.get('homeTeamOdds', {}).get('moneyLine')) > 0 else str(odds_item.get('homeTeamOdds', {}).get('moneyLine') or 'TBD'),
                "draw": f"+{odds_item.get('drawOdds', {}).get('moneyLine')}" if odds_item.get('drawOdds', {}).get('moneyLine') and int(odds_item.get('drawOdds', {}).get('moneyLine')) > 0 else str(odds_item.get('drawOdds', {}).get('moneyLine') or 'TBD'),
                "away": f"+{odds_item.get('awayTeamOdds', {}).get('moneyLine')}" if odds_item.get('awayTeamOdds', {}).get('moneyLine') and int(odds_item.get('awayTeamOdds', {}).get('moneyLine')) > 0 else str(odds_item.get('awayTeamOdds', {}).get('moneyLine') or 'TBD'),
                "total": str(odds_item.get('overUnder', odds_item.get('total', {}).get('displayName', 'TBD'))), "over": str(odds_item.get('overOdds', 'TBD')), "under": str(odds_item.get('underOdds', 'TBD'))
            }

        inj_raw = data.get('injuries', [])
        if isinstance(inj_raw, list) and len(inj_raw) == 2:
            summary_data["injuries"] = {"home": [i.get('athlete', {}).get('displayName', '') for i in inj_raw[0].get('injuries', [])], "away": [i.get('athlete', {}).get('displayName', '') for i in inj_raw[1].get('injuries', [])]}

    except Exception as e:
        print(f"    ❌ EXCEPTION in parse_espn_summary for event {event_id}: {e}")

    return summary_data

def shorten_player_name(full_name):
    if not full_name: return "Unknown"
    parts = str(full_name).strip().split(' ')
    if len(parts) == 1: return parts[0]
    return f"{parts[0][0].upper()}. {' '.join(parts[1:])}"

def get_contrast_color(hex_color):
    if not hex_color: return '#ffffff'
    hex_color = str(hex_color).replace('#', '')
    if len(hex_color) == 3: hex_color = "".join([c*2 for c in hex_color])
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000
        return '#000000' if yiq >= 128 else '#ffffff'
    except: return '#ffffff'

def get_team_color(lineup, default_hex):
    if not lineup: return default_hex
    try:
        c = lineup.get('team', {}).get('colors', {}).get('player', {}).get('primary')
        return f"#{str(c).replace('#', '')}" if c else default_hex
    except:
        return default_hex

def get_time_badge_html(data):
    status = str(data['fixture']['status'].get('short', ''))
    elapsed = data['fixture']['status'].get('elapsed')
    date_str = str(data['fixture'].get('date', ''))
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        dt_local = dt.astimezone(pytz.timezone('America/New_York'))
        time_str = dt_local.strftime("%I:%M%p").lstrip('0').lower()
        match_time = f"{dt_local.strftime('%a')} {time_str}"
    except: match_time = date_str

    if status in ['PST', 'CANC', 'ABD']: return f'<span class="badge bg-danger text-white border px-2 py-1" style="font-size: 0.75rem;">{status}</span>'
    elif status in ['FT', 'AET', 'PEN']: return f'<span class="badge bg-dark text-white border px-2 py-1" style="font-size: 0.75rem;">FT</span>'
    elif status not in ['NS', 'TBD']:
        display_min = str(elapsed) if (elapsed and elapsed != 'LIVE' and str(elapsed).endswith("'")) else (f"{elapsed}'" if elapsed and elapsed != 'LIVE' else 'LIVE')
        if status == 'HT': display_min = 'HT'
        return f'<span class="badge bg-success text-white border px-2 py-1" style="font-size: 0.75rem;"><span class="live-dot"></span>{display_min}</span>'
    else: return f'<span class="badge bg-white text-dark border px-1 py-1 local-time-badge" data-utc="{date_str}" style="font-size: 0.65rem; white-space: nowrap;">{match_time}</span>'

def get_latest_event_html(data, is_ribbon=False):
    events = data.get('events', [])
    if not events: return '<div class="text-muted text-start w-100 ps-2" style="font-size: 0.6rem; font-style: italic;">No Events</div>' if is_ribbon else ''
    last_ev = events[-1]
    is_home = str(last_ev.get('team_id')) == str(data['teams']['home'].get('id', ''))
    team_name = str(data['teams']['home'].get('name', 'TBD')) if is_home else str(data['teams']['away'].get('name', 'TBD'))
    team_logo = str(data['teams']['home'].get('logo', '')) if is_home else str(data['teams']['away'].get('logo', ''))

    if last_ev.get('type') == 'subst':
        p_out = shorten_player_name(last_ev.get('player'))
        p_in = shorten_player_name(last_ev.get('player_out'))
        if is_ribbon:
            return f'''<div class="text-dark fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3;"><div class="text-truncate">🔄 <img src="{team_logo}" loading="lazy" decoding="async" style="width: 12px; height: 12px;" class="me-1">{last_ev.get('time', '')}'</div><div class="text-truncate">🟢 <span class="text-success">{p_in}</span></div><div class="text-muted text-truncate">🔴 {p_out}</div></div>'''
        else:
            return f'''<div class="ms-2 d-flex align-items-center text-dark fw-bold" style="font-size: 0.65rem; line-height: 1.2; min-width: 0;"><div class="d-flex align-items-center me-2"><span class="bg-primary text-white rounded d-flex justify-content-center align-items-center me-1" style="width: 14px; height: 14px; font-size: 0.55rem;">🔄</span><img src="{team_logo}" loading="lazy" decoding="async" style="width: 14px; height: 14px; object-fit: contain;" class="me-1"><span>{last_ev.get('time', '')}'</span></div><div class="d-flex flex-column text-start" style="min-width: 0;"><div class="text-truncate"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color:#20c997; margin-bottom:1px; margin-right:3px;"></span>{p_in}</div><div class="text-muted text-truncate"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color:#dc3545; margin-bottom:1px; margin-right:3px;"></span>{p_out}</div></div></div>'''
    else:
        icon, text_color = '🟨', 'text-warning'
        if last_ev.get('type') == 'Goal': icon, text_color = '⚽', 'text-success'
        elif last_ev.get('type') == 'Red Card': icon, text_color = '🟥', 'text-danger'
        p_name = shorten_player_name(last_ev.get('player') or team_name)
        ast_html = f'<div class="text-muted text-truncate" style="font-size: 0.55rem;">👟 {shorten_player_name(last_ev.get("assist"))}</div>' if last_ev.get('type') == 'Goal' and last_ev.get('assist') else ''
        ast_html_full = f'<div class="text-muted text-truncate fw-normal" style="font-size: 0.55rem;"><span style="display:inline-block; width:12px;"></span>👟 {shorten_player_name(last_ev.get("assist"))}</div>' if last_ev.get('type') == 'Goal' and last_ev.get('assist') else ''
        if is_ribbon:
            return f'''<div class="{text_color} fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3;"><div class="text-truncate"><img src="{team_logo}" loading="lazy" decoding="async" style="width: 12px; height: 12px;" class="me-1">{last_ev.get('time', '')}'</div><div class="text-truncate">{icon} {p_name}</div>{ast_html}</div>'''
        else:
            return f'''<div class="ms-2 d-flex flex-column text-start {text_color} fw-bold" style="font-size: 0.65rem; line-height: 1.2; min-width: 0;"><div class="text-truncate">{icon} {last_ev.get('time', '')}' <img src="{team_logo}" loading="lazy" decoding="async" style="width: 12px; height: 12px;" class="mx-1">{p_name}</div>{ast_html_full}</div>'''

def get_ribbon_html(data):
    is_pre = data['fixture']['status']['short'] in ['NS', 'TBD', 'PST', 'CANC', 'ABD']
    h_score = '-' if is_pre else data.get('goals', {}).get('home', 0)
    a_score = '-' if is_pre else data.get('goals', {}).get('away', 0)
    
    l_flag = str(data["league"].get("flag") or "")
    flag_html = f'<img src="{l_flag}" loading="lazy" decoding="async" style="width: 20px; height: 20px; object-fit: contain; margin-right: 6px; vertical-align: middle; border-radius: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">' if l_flag.startswith('http') or l_flag.startswith('images/') else f'<span style="font-size: 1.1rem; margin-right: 6px; vertical-align: middle; line-height: 1;">{l_flag or "🏆"}</span>'
    
    return f'''
    <div class="row g-0 align-items-center py-2" style="transition: background-color 0.2s;">
        <div class="col-3 text-center d-flex flex-column justify-content-center align-items-center border-end pe-1 ps-1"><div style="margin-bottom: 3px;">{get_time_badge_html(data)}</div><a href="/leagues/{data["league"]["slug"]}/" onclick="event.stopPropagation();" class="text-decoration-none text-muted fw-bold text-truncate w-100 px-1 d-inline-block" style="font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase;" title="{data["league"]["name"]}">{flag_html}{data["league"]["abbrev"]}</a></div>
        <div class="col-5 px-2">
            <div class="d-flex justify-content-between align-items-center mb-1"><span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 88%;"><img src="{data['teams']['home']['logo']}" loading="lazy" decoding="async" width="14" height="14" class="me-1" style="object-fit:contain;">{data['teams']['home']['name']}</span><div class="text-end" style="min-width: fit-content; white-space: nowrap;"><span class="fw-bold text-dark" style="font-size: 0.85rem;">{h_score}</span></div></div>
            <div class="d-flex justify-content-between align-items-center"><span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 88%;"><img src="{data['teams']['away']['logo']}" loading="lazy" decoding="async" width="14" height="14" class="me-1" style="object-fit:contain;">{data['teams']['away']['name']}</span><div class="text-end" style="min-width: fit-content; white-space: nowrap;"><span class="fw-bold text-dark" style="font-size: 0.85rem;">{a_score}</span></div></div>
        </div>
        <div class="col-4 text-center border-start d-flex justify-content-center align-items-center">{get_latest_event_html(data, True)}</div>
    </div>'''

def get_center_column_html(data):
    is_pre = data['fixture']['status']['short'] in ['NS', 'TBD', 'PST', 'CANC', 'ABD']
    h_score = data.get('goals', {}).get('home', 0)
    a_score = data.get('goals', {}).get('away', 0)
    if is_pre or not data.get('team_stats'): 
        return f'<div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">{"vs" if is_pre else f"{h_score} - {a_score}"}</div>'
    
    t_stats = data['team_stats']
    h_color = get_team_color(data.get('homeLineup'), '#0d6efd')
    a_color = get_team_color(data.get('awayLineup'), '#dc3545')

    def build_bar(label, h_val, a_val, is_pct=False):
        tot = h_val + a_val
        h_pct = (h_val / tot * 100) if tot > 0 else 50
        a_pct = (a_val / tot * 100) if tot > 0 else 50
        return f'''<div class="text-center w-100 px-1"><div class="stat-label-tiny">{label}</div><div class="stat-bar-container"><div class="stat-bar-segment" style="width: {h_pct}%; background-color: {h_color}; color: {get_contrast_color(h_color)};">{f"{h_val}%" if is_pct else h_val}</div><div class="stat-bar-segment" style="width: {a_pct}%; background-color: {a_color}; color: {get_contrast_color(a_color)};">{f"{a_val}%" if is_pct else a_val}</div></div></div>'''

    return f'''<div class="fw-bold text-dark mx-2 mb-1" style="font-size: 1.1rem; line-height: 1;">{h_score} - {a_score}</div>{build_bar("Possession", t_stats['home'].get('possession',0), t_stats['away'].get('possession',0), True)}{build_bar("Total Shots", t_stats['home'].get('total_shots',0), t_stats['away'].get('total_shots',0))}{build_bar("Shots on Target", t_stats['home'].get('shots_on_target',0), t_stats['away'].get('shots_on_target',0))}{build_bar("Corners", t_stats['home'].get('corners',0), t_stats['away'].get('corners',0))}<div class="text-center w-100 px-1 mt-1"><div class="stat-label-tiny" style="margin-bottom: 0px;">Cards</div><div class="d-flex justify-content-between text-muted" style="font-size: 0.65rem; font-weight: 700;"><span>🟨 {t_stats['home'].get('yellow_cards',0)} 🟥 {t_stats['home'].get('red_cards',0)}</span><span>🟨 {t_stats['away'].get('yellow_cards',0)} 🟥 {t_stats['away'].get('red_cards',0)}</span></div></div>'''

def get_events_html(data):
    if not data.get('events'): return ''
    h_id, a_id = str(data['teams']['home']['id']), str(data['teams']['away']['id'])
    h_evs = list(reversed([e for e in data['events'] if str(e.get('team_id')) == h_id]))
    a_evs = list(reversed([e for e in data['events'] if str(e.get('team_id')) == a_id]))
    
    def fmt_ev(e, team_name):
        if e.get('type') == 'subst': return f'''<div class="d-flex align-items-start mb-1" style="line-height: 1.1;"><div class="text-secondary fw-bold pe-1" style="width: 25px; text-align: right; font-size: 0.6rem;">{e.get('time', '')}'</div><div style="width: 16px; text-align: center;" class="me-1">🔄</div><div class="text-truncate"><span class="text-dark fw-bold">{shorten_player_name(e.get('player_out'))}</span> IN<br><span class="text-muted" style="font-size: 0.55rem;">({shorten_player_name(e.get('player'))} OUT)</span></div></div>'''
        icon = '⚽' if e.get('type') == 'Goal' else ('🟥' if e.get('type') == 'Red Card' else '🟨')
        ast = f'''<br><span class="text-muted fw-normal" style="font-size: 0.55rem;">👟 {shorten_player_name(e.get('assist'))}</span>''' if e.get('type') == 'Goal' and e.get('assist') else ''
        return f'''<div class="d-flex align-items-start mb-1" style="line-height: 1.1;"><div class="text-secondary fw-bold pe-1" style="width: 25px; text-align: right; font-size: 0.6rem;">{e.get('time', '')}'</div><div style="width: 16px; text-align: center;" class="me-1">{icon}</div><div class="text-truncate"><span class="text-dark fw-bold">{shorten_player_name(e.get('player') or team_name)}</span>{ast}</div></div>'''

    needs_col = max(len(h_evs), len(a_evs)) > 1
    h_first = fmt_ev(h_evs[0], data['teams']['home']['name']) if h_evs else ''
    a_first = fmt_ev(a_evs[0], data['teams']['away']['name']) if a_evs else ''
    h_all = "".join([fmt_ev(e, data['teams']['home']['name']) for e in h_evs])
    a_all = "".join([fmt_ev(e, data['teams']['away']['name']) for e in a_evs])
    toggle = "const isExp = this.classList.toggle('is-expanded'); this.querySelector('.event-collapsed').classList.toggle('d-none', isExp); this.querySelector('.event-expanded').classList.toggle('d-none', !isExp);" if needs_col else ""
    return f'''<div class="w-100 px-2 pt-1 mt-1 border-top text-muted" style="font-size: 0.65rem; cursor: pointer; transition: background-color 0.2s;" onclick="{toggle}" title="{"Click to expand/collapse match timeline" if needs_col else ""}"><div class="event-collapsed"><div class="d-flex justify-content-between"><div class="text-start" style="flex: 1; min-width: 0;">{h_first}</div><div class="text-start" style="flex: 1; min-width: 0;">{a_first}</div></div>{"<div class='text-center text-secondary w-100' style='font-size: 0.60rem;'>▼</div>" if needs_col else ""}</div><div class="event-expanded d-none"><div class="d-flex justify-content-between"><div class="text-start" style="flex: 1; min-width: 0;">{h_all}</div><div class="text-start" style="flex: 1; min-width: 0;">{a_all}</div></div><div class="text-center text-secondary w-100" style="font-size: 0.60rem;">▲</div></div></div>'''

def get_odds_html(data):
    odds = data.get('odds', {})
    if not odds or (odds.get('home') == "TBD" and odds.get('over') == "TBD"): return ''
    return f'''<div class="d-flex justify-content-between text-center bg-white border-top border-bottom py-1" style="font-size: 0.70rem;"><div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">1 (HOME)</div><div class="fw-bold text-dark">{odds.get('home','')}</div></div><div class="w-25 border-start border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">X (DRAW)</div><div class="fw-bold text-dark">{odds.get('draw','')}</div></div><div class="w-25 border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">2 (AWAY)</div><div class="fw-bold text-dark">{odds.get('away','')}</div></div><div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">O/U {odds.get('total','')}</div><div class="fw-bold text-dark"><span class="text-success">O</span> {odds.get('over','')} <span class="text-danger">U</span> {odds.get('under','')}</div></div></div>'''

def get_injuries_html(data):
    inj = data.get('injuries', {})
    h_inj = ", ".join([shorten_player_name(p) for p in inj.get('home', []) if p])
    a_inj = ", ".join([shorten_player_name(p) for p in inj.get('away', []) if p])
    if not h_inj and not a_inj: return ''
    return f'''<div class="border-bottom px-2 py-1 text-truncate" style="font-size: 0.65rem; background-color: #fff5f5; color: #dc3545;"><strong>🤕 OUT:</strong> <span class="text-dark"><b>H:</b> {h_inj or 'None'} | <b>A:</b> {a_inj or 'None'}</span></div>'''

def build_lineup_list(lineup_data):
    if not lineup_data or not lineup_data.get('startXI'): return '<div class="p-3 text-center text-muted small fst-italic">Lineup pending...</div>'
    items = ""
    for s in lineup_data['startXI']:
        p = s.get('player', {})
        pho = f'''<img data-src="{p.get('photo', '')}" style="width: 22px; height: 22px; border-radius: 50%; object-fit: cover;" class="me-2 player-headshot">''' if p.get('photo') else '''<div style="width:22px; height:22px; border-radius:50%; background:#e9ecef;" class="me-2 d-inline-block"></div>'''
        sub = '''<span class="text-primary fw-bold me-1" title="Subbed Out">↻</span>''' if p.get('isSubbedOut') else ''
        items += f'''<li class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="font-size: 0.8rem;"><span class="text-muted fw-bold me-2" style="font-size: 0.65rem; min-width: 32px; display: inline-block; text-align: left;">{p.get('pos','M')}</span>{pho}<span class="batter-name text-dark text-truncate">{sub}{shorten_player_name(p.get('name'))}</span><span class="ms-auto text-muted" style="font-size: 0.65rem;">#{p.get('number','')}</span></li>'''
    return f'''<div class="w-100 text-center py-1 fw-bold text-white bg-success" style="font-size: 0.65rem;">✅ {lineup_data.get('formation', '4-3-3')}</div><ul class="batting-order w-100 m-0 p-0">{items}</ul>'''

def build_live_stats_grid(lineup_data, hex_color):
    if not lineup_data or not lineup_data.get('startXI'): return '<div class="p-3 text-center text-muted small fw-bold">Awaiting live stats...</div>'
    grps = {'F': {'t': 'FWD', 's': ['G','A','xG','SOG'], 'k': ['goals','assists','xg','shots_on_target']}, 'M': {'t': 'MID', 's': ['G','A','PAS','DUEL'], 'k': ['goals','assists','accurate_passes','duels_won']}, 'D': {'t': 'DEF', 's': ['G','DINT','TK','DUEL'], 'k': ['goals','dint','tackles','duels_won']}, 'G': {'t': 'GK', 's': ['SV','GA','xGA','SHF'], 'k': ['saves','conceded','xga','shots_faced']}}
    grouped = {'F': [], 'M': [], 'D': [], 'G': []}
    players = [s.get('player', {}) for s in lineup_data['startXI']] + [s.get('player', {}) for s in lineup_data.get('substitutes', []) if s.get('player', {}).get('isSubbedIn')]
    for p in players: grouped[p.get('category', 'M')].append(p)
    
    c = str(hex_color) if hex_color else '#6c757d'
    html = ''
    for pk in ['F', 'M', 'D', 'G']:
        if not grouped[pk]: continue
        g = grps[pk]
        html += f'''<div class="d-flex w-100 px-2 py-1 align-items-center bg-light border-bottom" style="font-size: 0.6rem; font-weight: 700;"><div style="flex: 1; color: {c};">{g['t']}</div><div style="width: 18px; text-align: center;">{g['s'][0]}</div><div style="width: 22px; text-align: center;">{g['s'][1]}</div><div style="width: 28px; text-align: center;">{g['s'][2]}</div><div style="width: 24px; text-align: center;">{g['s'][3]}</div></div>'''
        for p in grouped[pk]:
            pre = '<span class="text-success fw-bold me-1">▲</span>' if p.get('isSubbedIn') else ('<span class="text-primary fw-bold me-1">↻</span>' if p.get('isSubbedOut') else '')
            st = p.get('live_stats', {})
            html += f'''<div class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="font-size: 0.70rem;"><div class="text-start text-truncate" style="flex: 1;">{pre}{shorten_player_name(p.get('name'))}</div><div class="text-muted" style="width: 18px; text-align: center; font-weight: 600;">{st.get(g['k'][0],0)}</div><div class="text-muted" style="width: 22px; text-align: center; font-weight: 600;">{st.get(g['k'][1],0)}</div><div class="text-muted" style="width: 28px; text-align: center; font-weight: 600;">{st.get(g['k'][2],0)}</div><div class="text-muted" style="width: 24px; text-align: center; font-weight: 600;">{st.get(g['k'][3],0)}</div></div>'''
    return html

def pre_render_game_card(data):
    fix_id = str(data['fixture'].get('id', ''))
    is_pre = data['fixture']['status'].get('short', '') in ['NS', 'TBD']
    has_stats = bool(data.get('team_stats'))
    
    l_flag = str(data['league'].get('flag') or "")
    flag_html = f'<img src="{l_flag}" loading="lazy" decoding="async" style="width: 24px; height: 24px; object-fit: contain; margin-right: 6px; vertical-align: middle; border-radius: 3px; filter: drop-shadow(0 1px 1px rgba(0,0,0,0.1));">' if l_flag.startswith('http') or l_flag.startswith('images/') else f'<span style="font-size: 1.3rem; margin-right: 6px; vertical-align: middle; line-height: 1;">{l_flag or "🏆"}</span>'
    
    h_col = get_team_color(data.get('homeLineup'), '#0d6efd')
    a_col = get_team_color(data.get('awayLineup'), '#dc3545')

    return f'''<!-- MATCH_{fix_id} -->
    <div class="lineup-card shadow-sm" id="card-{fix_id}">
        <div class="ribbon-view" id="ribbon-{fix_id}" onclick="toggleSingleCard('{fix_id}')">{get_ribbon_html(data)}</div>
        <div class="full-view d-none" id="full-{fix_id}">
            <div class="p-2 pb-1" style="background-color: #fcfcfc;">
                <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom" style="cursor: pointer;" onclick="toggleSingleCard('{fix_id}')">
                    <div class="pe-2 d-flex align-items-center flex-shrink-0" id="time-{fix_id}" style="white-space: nowrap;">{get_time_badge_html(data)} {get_latest_event_html(data)}</div>
                    <a href="/leagues/{data['league']['slug']}/" class="text-decoration-none text-muted fw-bold text-uppercase text-end ms-auto text-truncate d-flex align-items-center justify-end" style="font-size: 0.75rem; min-width: 0;" title="{data['league']['name']}">{flag_html} <span class="text-truncate">{data['league']['name']}</span></a>
                </div>
                <div class="d-flex justify-content-between align-items-center px-1 py-1 w-100">
                    <div class="text-center" style="width: 30%;"><img src="{data['teams']['home']['logo']}" loading="lazy" decoding="async" class="team-logo mb-1"><div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">{data['teams']['home']['name']}</div></div>
                    <div class="text-center d-flex flex-column align-items-center justify-content-center" style="width: 40%;" id="score-{fix_id}">{get_center_column_html(data)}</div>
                    <div class="text-center" style="width: 30%;"><img src="{data['teams']['away']['logo']}" loading="lazy" decoding="async" class="team-logo mb-1"><div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">{data['teams']['away']['name']}</div></div>
                </div>
                <div class="w-100" id="events-{fix_id}">{get_events_html(data)}</div>
            </div>
            <div class="w-100" id="odds-{fix_id}">{get_odds_html(data)}</div>
            <div class="w-100" id="injuries-{fix_id}">{get_injuries_html(data)}</div>
            <div class="bg-light border-bottom d-flex justify-content-center align-items-center px-2 py-1">
                <div class="d-flex gap-4 w-100">
                    <div class="lineup-tab {'active' if (not has_stats or is_pre) else ''}" id="tab-xi-{fix_id}" onclick="switchLineupTab(event, '{fix_id}', 'xi')" style="flex: 1; text-align: center;">{'STARTING XI' if is_pre else 'FINAL XI'}</div>
                    <div class="lineup-tab {'active' if (has_stats and not is_pre) else ''} {'d-none' if not has_stats else ''}" id="tab-stats-{fix_id}" onclick="switchLineupTab(event, '{fix_id}', 'stats')" style="flex: 1; text-align: center;">LIVE STATS</div>
                </div>
            </div>
            <div class="collapse show lineup-container" id="lineup-collapse-{fix_id}">
                <div id="view-xi-{fix_id}" class="{'d-none' if (has_stats and not is_pre) else ''}"><div class="row g-0 bg-white border-top"><div class="col-6 border-end">{build_lineup_list(data.get('homeLineup'))}</div><div class="col-6">{build_lineup_list(data.get('awayLineup'))}</div></div></div>
                <div id="view-stats-{fix_id}" class="{'d-none' if (not has_stats or is_pre) else ''}"><div class="row g-0 bg-white border-top"><div class="col-6 border-end">{build_live_stats_grid(data.get('homeLineup'), h_col)}</div><div class="col-6">{build_live_stats_grid(data.get('awayLineup'), a_col)}</div></div></div>
            </div>
        </div>
    </div>
    <!-- END_MATCH_{fix_id} -->'''

def group_and_sort_matches_by_league(matches):
    if not matches:
        return []
    leagues_map = {}
    for m in matches:
        l_info = m.get('league', {})
        l_slug = l_info.get('slug') or create_slug(l_info.get('name', 'other'))
        l_name = l_info.get('name', 'Global Football')
        l_flag = l_info.get('flag', '')
        match_date = m.get('fixture', {}).get('date', '9999-99-99') or '9999-99-99'

        if l_slug not in leagues_map:
            leagues_map[l_slug] = {
                'name': l_name,
                'slug': l_slug,
                'flag': l_flag,
                'earliest_date': match_date,
                'matches': []
            }
        
        leagues_map[l_slug]['matches'].append(m)
        if match_date < leagues_map[l_slug]['earliest_date']:
            leagues_map[l_slug]['earliest_date'] = match_date

    league_list = list(leagues_map.values())
    
    # Sort matches within each league chronologically
    for lg in league_list:
        lg['matches'].sort(key=lambda x: x.get('fixture', {}).get('date', '9999-99-99') or '9999-99-99')

    # Sort leagues by earliest match date
    league_list.sort(key=lambda x: x['earliest_date'])
    return league_list

def fetch_espn_scores_for_date(date_str, old_html):
    headers = {'User-Agent': 'Mozilla/5.0'}
    raw_events = []
    seen_ids = set()
    page, max_pages = 1, 10

    while page <= max_pages:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}&limit=1000&page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200: break
            events = res.json().get('events', [])
            if not events: break
            added_this_page = 0
            for ev in events:
                ev_id = str(ev.get('id', ''))
                if ev_id and ev_id not in seen_ids:
                    seen_ids.add(ev_id); raw_events.append(ev); added_this_page += 1
            if added_this_page == 0: break
            page += 1
        except: break

    matches = []
    for event in raw_events:
        try:
            event_id = str(event.get('id', ''))
            state = event.get('status', {}).get('type', {}).get('state', 'pre')

            comps = event.get('competitions', [])
            if not comps: continue
            comp = comps[0]
            
            home_comp = next((c for c in comp.get('competitors', []) if c.get('homeAway') == 'home'), None)
            away_comp = next((c for c in comp.get('competitors', []) if c.get('homeAway') == 'away'), None)
            if not home_comp or not away_comp: continue

            h_team = home_comp.get('team', {})
            a_team = away_comp.get('team', {})
            
            # Localize Team Logos
            home_id = str(h_team.get('id', ''))
            away_id = str(a_team.get('id', ''))
            home_name = str(h_team.get('displayName') or h_team.get('name') or "TBD")
            away_name = str(a_team.get('displayName') or a_team.get('name') or "TBD")
            home_logo = get_local_image_url(str(h_team.get('logo') or ""), subfolder="images/teams")
            away_logo = get_local_image_url(str(a_team.get('logo') or ""), subfolder="images/teams")

            league_obj = event.get('league') or comp.get('league') or (event.get('leagues', [{}])[0] if event.get('leagues') else {})
            raw_name = str(comp.get('altGameNote') or league_obj.get('name') or league_obj.get('displayName') or "Global Football")
            final_league_name = re.sub(r'^\d{4}-\d{4}\s+', '', raw_name).strip()
            league_slug = create_slug(final_league_name)
            
            clean_league = normalize_text(final_league_name)
            league_flag = NORMALIZED_HUMAN_LEAGUE_FLAGS.get(clean_league, "")
            if not league_flag: league_flag = NORMALIZED_HUMAN_LEAGUE_FLAGS.get(re.sub(r'\s+(qualifying|qualifiers|playoffs?)\b', '', clean_league), "")
            if not league_flag:
                logos = league_obj.get('logos', [])
                if logos: league_flag = logos[0].get('href', '')
                elif isinstance(league_obj.get('logo'), str): league_flag = league_obj.get('logo')

            if not league_flag or 'default-team-logo' in str(league_flag):
                for ctry, code in COUNTRY_FLAG_URLS.items():
                    if re.search(rf'\b{ctry}\b', clean_league): league_flag = f"https://flagcdn.com/w40/{code}.png"; break
                if not league_flag and re.search(r'\b(africa|african|caf)\b', clean_league): league_flag = "🌍"
                if not league_flag and re.search(r'\b(international|concacaf|conmebol|uefa|olympic|nations|saff|americ)\b', clean_league): league_flag = "🌎"
                if not league_flag and 'friendly' in clean_league: league_flag = "🤝"
                if not league_flag and 'cup' in clean_league: league_flag = "🏆"

            # Localize League Flags
            league_flag = get_local_image_url(str(league_flag or ""), subfolder="images/leagues")

            if state == 'post' and old_html:
                match_pattern = f"<!-- MATCH_{event_id} -->(.*?)<!-- END_MATCH_{event_id} -->"
                saved_block = re.search(match_pattern, old_html, re.DOTALL)
                if saved_block:
                    card_content = saved_block.group(1)
                    if any(badge in card_content for badge in ['>FT</span>', '>AET</span>', '>PEN</span>']):
                        matches.append({
                            "fixture": {"id": event_id, "date": event.get('date', ''), "status": {"short": "FT"}},
                            "teams": {"home": {"name": home_name}, "away": {"name": away_name}},
                            "league": {"name": final_league_name, "abbrev": generate_league_abbrev(final_league_name), "slug": league_slug, "flag": league_flag},
                            "html_card": f"<!-- MATCH_{event_id} -->{card_content}<!-- END_MATCH_{event_id} -->"
                        })
                        continue

            should_fetch, _ = should_fetch_summary(event)
            summary = parse_espn_summary(event_id) if should_fetch else {
                "team_stats": None, "homeLineup": None, "awayLineup": None, "events": [], 
                "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"}, 
                "injuries": {"home": [], "away": []}, 
                "live_score": {},
                "status_obj": None
            }

            fresh_status = summary.get("status_obj") or event.get('status', {})
            fresh_type = fresh_status.get('type', {})
            st = fresh_type.get('state', state)
            status_short = 'NS' if st == 'pre' else ('FT' if st == 'post' else fresh_type.get('shortDetail', 'LIVE'))

            match_entry = {
                "fixture": {"id": event_id, "date": event.get('date', ''), "status": {"short": status_short, "elapsed": extract_match_clock(fresh_status)}},
                "league": {"id": event_id, "name": final_league_name, "abbrev": generate_league_abbrev(final_league_name), "slug": league_slug, "flag": league_flag},
                "teams": {
                    "home": {"id": home_id, "name": home_name, "logo": home_logo},
                    "away": {"id": away_id, "name": away_name, "logo": away_logo}
                },
                "goals": {
                    "home": int((summary.get('live_score') or {}).get('home') or home_comp.get('score') or 0), 
                    "away": int((summary.get('live_score') or {}).get('away') or away_comp.get('score') or 0)
                },
                "team_stats": summary["team_stats"], "homeLineup": summary["homeLineup"], "awayLineup": summary["awayLineup"],
                "events": summary["events"], "odds": summary["odds"], "injuries": summary["injuries"]
            }
            
            match_entry["html_card"] = pre_render_game_card(match_entry)
            matches.append(match_entry)

        except Exception as e: 
            print(f"❌ ERROR parsing match item {event.get('id')}: {e}")

    return matches

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#212529">
    <title>Futbol Starting Eleven | Live Soccer Starting Lineups, Scores, Injuries & Odds</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script>
        // Immediately terminate any hanging/broken image requests
        document.addEventListener('error', function (e) {
            if (e.target.tagName === 'IMG') {
                e.target.style.display = 'none'; // Hide broken image immediately
            }
        }, true);
    </script>
    <style>
        body { background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .header-brand { font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; font-style: italic; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
        .header-brand a { color: inherit; }
        .header-brand span { text-shadow: none !important; background: linear-gradient(to bottom, #20c997 0%, #198754 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; filter: drop-shadow(0 0 12px rgba(32, 201, 151, 0.6)); }
        .day-tab-btn { font-size: 0.85rem; font-weight: 700; border-radius: 20px; padding: 6px 18px; transition: all 0.2s; }
        .lineup-card { background: #fff; border: 1px solid #dee2e6; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 16px; overflow: hidden; }
        .team-logo { width: 45px; height: 45px; object-fit: contain; filter: drop-shadow(0px 2px 2px rgba(0,0,0,0.1)); }
        .batting-order { padding-left: 0; list-style-type: none; margin-bottom: 0; }
        .batting-order li { padding: 6px 12px; font-size: 0.85rem; border-bottom: 1px solid #f1f3f5; display: flex; justify-content: space-between; align-items: center; }
        .batting-order li:last-child { border-bottom: none; }
        .batter-name { font-weight: 600; color: #495057; }
        #team-search { color: #ffffff !important; color-scheme: dark; width: 45px; transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1); background-color: #343a40; border: 1px solid #495057; cursor: pointer; }
        #team-search:focus { width: 160px; background-color: #495057 !important; border-color: #20c997 !important; box-shadow: 0 0 0 0.2rem rgba(32, 201, 151, 0.25) !important; cursor: text; }
        .live-dot { display: inline-block; width: 7px; height: 7px; background-color: #fff; border-radius: 50%; margin-right: 5px; margin-bottom: 1px; animation: pulse-green 2s infinite; }
        @keyframes pulse-green { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(32, 201, 151, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0); } }
        .stat-bar-container { display: flex; width: 100%; height: 14px; background-color: #e9ecef; border-radius: 4px; overflow: hidden; margin-top: 2px; }
        .stat-bar-segment { display: flex; align-items: center; justify-content: center; font-size: 0.60rem; font-weight: 800; padding: 0 4px; transition: width 0.5s ease-in-out; }
        .stat-label-tiny { font-size: 0.55rem; text-transform: uppercase; font-weight: 700; color: #6c757d; margin-top: 4px; }
        .lineup-tab { font-size: 0.65rem; font-weight: 700; padding: 6px 4px; color: #adb5bd; cursor: pointer; transition: all 0.2s ease; border-bottom: 2px solid transparent; text-transform: uppercase; }
        .lineup-tab.active { color: #20c997; border-bottom: 2px solid #20c997; }

        .league-banner { background: #ffffff; border-left: 4px solid #198754; border-radius: 8px; }

        @keyframes glowGoal { 0% { border-color: #20c997; box-shadow: 0 0 25px rgba(32, 201, 151, 0.8); transform: scale(1.02); } 100% { border-color: #dee2e6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); transform: scale(1); } }
        @keyframes headerGoal { 0% { background-color: #d1e7dd !important; } 100% { background-color: #fcfcfc !important; } }
        .glow-goal { animation: glowGoal 4s ease-out !important; border: 3px solid #20c997 !important; position: relative !important; z-index: 10 !important; }
        .glow-goal .p-2.pb-1 { animation: headerGoal 4s ease-out !important; }

        @keyframes glowRed { 0% { border-color: #dc3545; box-shadow: 0 0 25px rgba(220, 53, 69, 0.8); transform: scale(1.02); } 100% { border-color: #dee2e6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); transform: scale(1); } }
        @keyframes headerRed { 0% { background-color: #f8d7da !important; } 100% { background-color: #fcfcfc !important; } }
        .glow-red-card { animation: glowRed 4s ease-out !important; border: 3px solid #dc3545 !important; position: relative !important; z-index: 10 !important; }
        .glow-red-card .p-2.pb-1 { animation: headerRed 4s ease-out !important; }

        @keyframes glowYellow { 0% { border-color: #ffc107; box-shadow: 0 0 25px rgba(255, 193, 7, 0.8); transform: scale(1.02); } 100% { border-color: #dee2e6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); transform: scale(1); } }
        @keyframes headerYellow { 0% { background-color: #fff3cd !important; } 100% { background-color: #fcfcfc !important; } }
        .glow-yellow-card { animation: glowYellow 4s ease-out !important; border: 3px solid #ffc107 !important; position: relative !important; z-index: 10 !important; }
        .glow-yellow-card .p-2.pb-1 { animation: headerYellow 4s ease-out !important; }

        @keyframes glowSub { 0% { border-color: #212529; box-shadow: 0 0 25px rgba(33, 37, 41, 0.6); transform: scale(1.02); } 100% { border-color: #dee2e6; box-shadow: 0 2px 4px rgba(0,0,0,0.05); transform: scale(1); } }
        @keyframes headerSub { 0% { background-color: #e9ecef !important; } 100% { background-color: #fcfcfc !important; } }
        .glow-subst { animation: glowSub 4s ease-out !important; border: 3px solid #212529 !important; position: relative !important; z-index: 10 !important; }
        .glow-subst .p-2.pb-1 { animation: headerSub 4s ease-out !important; }
    </style>
</head>
<body>

<nav class="navbar sticky-top shadow-sm pt-2 pb-2 mb-0" style="background-color: #212529; z-index: 1050;">
    <div class="container d-flex justify-content-between align-items-center">
        <div class="header-brand"><a href="/" class="text-decoration-none">Futbol Starting <span>Eleven</span></a></div>
        <div class="d-flex align-items-center gap-2"><input type="text" id="team-search" class="form-control form-control-sm" placeholder="🔍 Search..."></div>
    </div>
</nav>

<div class="container mt-3 mb-2 text-center">
    <h1 class="h5 fw-bold text-dark mb-1">Futbol Starting Eleven: Live Soccer Starting Lineups, Scores & Odds</h1>
    <p class="text-muted mb-2" style="font-size: 0.85rem;">Real-time starting XIs, match injuries, goalscorers, and betting odds for global football.</p>
    
    <div class="d-flex justify-content-center gap-2 my-3" id="day-selector">
        <button class="btn btn-outline-dark day-tab-btn" data-day="yesterday">Yesterday<br><small style="font-size: 0.65rem;">{{ display_dates.yesterday }}</small></button>
        <button class="btn btn-dark day-tab-btn active" data-day="today">Today<br><small style="font-size: 0.65rem;">{{ display_dates.today }}</small></button>
        <button class="btn btn-outline-dark day-tab-btn" data-day="tomorrow">Tomorrow<br><small style="font-size: 0.65rem;">{{ display_dates.tomorrow }}</small></button>
    </div>
</div>

<!-- CONTROLS & LEAGUE JUMP DROPDOWN -->
<div class="container mb-3">
    <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
        <div class="d-flex align-items-center gap-2">
            <label for="league-select" class="fw-bold text-dark small mb-0" style="white-space: nowrap;">🏆 Jump to League:</label>
            <select id="league-select" class="form-select form-select-sm shadow-sm" style="min-width: 200px; max-width: 320px; font-weight: 600;">
                <option value="">-- Select League --</option>
            </select>
        </div>
        <div>
            <button id="toggle-all-cards" class="btn btn-sm btn-dark text-white shadow-sm px-3 py-1 me-2" style="font-size: 0.70rem; font-weight: 700; border-radius: 20px;">🔽 COMPACT SCOREBOARD</button>
            <button id="toggle-all-lineups" class="btn btn-sm btn-dark text-white shadow-sm px-3 py-1 d-none" style="font-size: 0.70rem; font-weight: 700; border-radius: 20px;">🔼 COLLAPSE ALL LINEUPS</button>
        </div>
    </div>
</div>

<div class="container pb-5">
    <div id="games-container" class="row justify-content-start">
        {% for day, leagues in leagues_by_day.items() %}
            <div id="partition-{{ day }}" class="day-partition {{ '' if day == 'today' else 'd-none' }} row w-100 m-0 justify-content-start">
                {% if leagues | length == 0 %}
                    <div class="col-12 text-center mt-5 empty-state">
                        <div class="card p-4 shadow-sm border-0"><div class="h4 text-muted">🏟️ No matches scheduled for this partition.</div></div>
                    </div>
                {% else %}
                    <div class="col-12 text-center mt-5 empty-state d-none">
                        <div class="card p-4 shadow-sm border-0"><div class="h4 text-muted">🏟️ No matches found.</div></div>
                    </div>
                    {% for league in leagues %}
                        <!-- LEAGUE HEADER -->
                        <div class="col-12 league-header mt-3 mb-2 px-1" id="league-{{ day }}-{{ league.slug }}" data-league-name="{{ league.name }}">
                            <div class="d-flex align-items-center p-2 rounded-3 shadow-sm league-banner">
                                {% if league.flag and (league.flag.startswith('http') or league.flag.startswith('images/')) %}
                                    <img src="{{ league.flag }}" loading="lazy" decoding="async" alt="" style="width: 22px; height: 22px; object-fit: contain;" class="me-2 rounded-1">
                                {% else %}
                                    <span class="me-2" style="font-size: 1.1rem;">{{ league.flag or '🏆' }}</span>
                                {% endif %}
                                <h2 class="h6 mb-0 fw-bold text-dark text-uppercase" style="letter-spacing: 0.5px;">{{ league.name }}</h2>
                                <span class="badge bg-light text-secondary border ms-auto px-2 py-1" style="font-size: 0.65rem;">{{ league.matches | length }} {{ 'Match' if league.matches | length == 1 else 'Matches' }}</span>
                            </div>
                        </div>
                        <!-- MATCH CARDS -->
                        {% for match in league.matches %}
                            <div class="col-md-6 col-lg-6 col-xl-4 mb-3 game-card-wrapper" data-search="{{ (match.teams.home.name | default('')) | lower }} {{ (match.teams.away.name | default('')) | lower }} {{ (match.league.name | default('')) | lower }} {{ (match.league.abbrev | default('')) | lower }}">
                                {{ match.html_card | safe }}
                            </div>
                        {% endfor %}
                    {% endfor %}
                {% endif %}
            </div>
        {% endfor %}
    </div>
</div>

<script>
    const STATIC_MATCHES = {{ matches_json | safe }};
    let ACTIVE_DAY = "today";
    let globalScoreboardMode = true;

    document.addEventListener('DOMContentLoaded', () => {
        populateLeagueDropdown();

        // Convert EST fallback times to user's local timezone
        document.querySelectorAll('.local-time-badge').forEach(badge => {
            const utcStr = badge.getAttribute('data-utc');
            if (utcStr) {
                const dt = new Date(utcStr);
                const day = new Intl.DateTimeFormat('en-US', { weekday: 'short' }).format(dt);
                let time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).format(dt).toLowerCase().replace(' ', '');
                badge.textContent = `${day} ${time}`;
            }
        });

        document.querySelectorAll('.day-tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.day-tab-btn').forEach(b => { b.classList.remove('btn-dark', 'active'); b.classList.add('btn-outline-dark'); });
                e.target.closest('.day-tab-btn').classList.remove('btn-outline-dark'); e.target.closest('.day-tab-btn').classList.add('btn-dark', 'active');
                ACTIVE_DAY = e.target.closest('.day-tab-btn').getAttribute('data-day');
                
                document.querySelectorAll('.day-partition').forEach(p => p.classList.add('d-none'));
                document.getElementById('partition-' + ACTIVE_DAY)?.classList.remove('d-none');
                
                populateLeagueDropdown();
                applySearchFilter();
            });
        });

        document.getElementById('team-search')?.addEventListener('input', applySearchFilter);

        document.getElementById('toggle-all-cards')?.addEventListener('click', (e) => {
            globalScoreboardMode = !globalScoreboardMode;
            e.target.innerHTML = globalScoreboardMode ? '🔼 EXPAND ALL CARDS' : '🔽 COMPACT SCOREBOARD';
            document.querySelectorAll('.ribbon-view').forEach(el => el.classList.toggle('d-none', !globalScoreboardMode));
            document.querySelectorAll('.full-view').forEach(el => el.classList.toggle('d-none', globalScoreboardMode));
            document.getElementById('toggle-all-lineups')?.classList.toggle('d-none', globalScoreboardMode);
        });

        document.getElementById('league-select')?.addEventListener('change', (e) => {
            const targetId = e.target.value;
            if (!targetId) return;
            const targetEl = document.getElementById(targetId);
            if (targetEl) {
                const navOffset = 70;
                const elementPosition = targetEl.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - navOffset;
                window.scrollTo({
                    top: offsetPosition,
                    behavior: 'smooth'
                });
            }
        });

        setInterval(pollAndUpdateDOM, 30000);
    });

    function populateLeagueDropdown() {
        const select = document.getElementById('league-select');
        if (!select) return;

        select.innerHTML = '<option value="">-- Select League --</option>';
        const activePartition = document.getElementById('partition-' + ACTIVE_DAY);
        if (!activePartition) return;

        // Filter visible headers and sort them alphabetically A-Z
        const headers = Array.from(activePartition.querySelectorAll('.league-header'))
            .filter(h => !h.classList.contains('d-none'))
            .sort((a, b) => {
                const nameA = (a.getAttribute('data-league-name') || '').toLowerCase();
                const nameB = (b.getAttribute('data-league-name') || '').toLowerCase();
                return nameA.localeCompare(nameB);
            });

        headers.forEach(h => {
            const opt = document.createElement('option');
            opt.value = h.id;
            opt.textContent = h.getAttribute('data-league-name') || 'League';
            select.appendChild(opt);
        });
    }

    function applySearchFilter() {
        const searchText = (document.getElementById('team-search')?.value || '').toLowerCase();
        const activePartition = document.getElementById('partition-' + ACTIVE_DAY);
        if (!activePartition) return;
        
        let totalVisibleMatches = 0;

        activePartition.querySelectorAll('.league-header').forEach(header => {
            let visibleInLeague = 0;
            let sibling = header.nextElementSibling;
            
            while (sibling && !sibling.classList.contains('league-header')) {
                if (sibling.classList.contains('game-card-wrapper')) {
                    const searchData = sibling.getAttribute('data-search') || '';
                    if (searchData.includes(searchText)) {
                        sibling.classList.remove('d-none');
                        visibleInLeague++;
                        totalVisibleMatches++;
                    } else {
                        sibling.classList.add('d-none');
                    }
                }
                sibling = sibling.nextElementSibling;
            }

            header.classList.toggle('d-none', visibleInLeague === 0);
        });

        const emptyState = activePartition.querySelector('.empty-state');
        if (emptyState) emptyState.classList.toggle('d-none', totalVisibleMatches > 0);

        populateLeagueDropdown();
    }

    window.toggleSingleCard = function(fixId) {
    const fullView = document.getElementById(`full-${fixId}`);
    document.getElementById(`ribbon-${fixId}`)?.classList.toggle('d-none');
    fullView?.classList.toggle('d-none');

        // Load headshots for this card only when opened
        if (fullView && !fullView.classList.contains('d-none')) {
            fullView.querySelectorAll('img[data-src]').forEach(img => {
                img.src = img.getAttribute('data-src');
                img.removeAttribute('data-src');
            });
        }
    };

    window.switchLineupTab = function(event, fixId, tabName) {
        if (event && event.stopPropagation) event.stopPropagation();
        const xiTab = document.getElementById(`tab-xi-${fixId}`), statsTab = document.getElementById(`tab-stats-${fixId}`);
        const xiView = document.getElementById(`view-xi-${fixId}`), statsView = document.getElementById(`view-stats-${fixId}`);

        if (tabName === 'xi') {
            xiTab?.classList.add('active'); statsTab?.classList.remove('active');
            xiView?.classList.remove('d-none'); statsView?.classList.add('d-none');
        } else if (tabName === 'stats') {
            statsTab?.classList.add('active'); xiTab?.classList.remove('active');
            statsView?.classList.remove('d-none'); xiView?.classList.add('d-none');
        }
    };

    function shortenPlayerName(fn) { if (!fn) return "Unknown"; const p = fn.split(' '); return p.length === 1 ? fn : `${p[0].charAt(0).toUpperCase()}. ${p.slice(1).join(' ')}`; }
    function getContrastColor(h) { if (!h) return '#ffffff'; h = h.replace('#', ''); const y = ((parseInt(h.substr(0,2),16)*299) + (parseInt(h.substr(2,2),16)*587) + (parseInt(h.substr(4,2),16)*114))/1000; return y >= 128 ? '#000000' : '#ffffff'; }
    
    function getTimeBadgeHtml(data) {
        const s = data.fixture.status.short, e = data.fixture.status.elapsed;
        let dMin = e && e !== 'LIVE' ? (String(e).endsWith("'") ? e : `${e}'`) : 'LIVE'; if (s === 'HT') dMin = 'HT';
        if (['PST','CANC','ABD'].includes(s)) return `<span class="badge bg-danger text-white border px-2 py-1" style="font-size: 0.75rem;">${s}</span>`;
        if (['FT','AET','PEN'].includes(s)) return `<span class="badge bg-dark text-white border px-2 py-1" style="font-size: 0.75rem;">FT</span>`;
        if (!['NS','TBD'].includes(s)) return `<span class="badge bg-success text-white border px-2 py-1" style="font-size: 0.75rem;"><span class="live-dot"></span>${dMin}</span>`;
        
        try {
            const dt = new Date(data.fixture.date);
            const day = new Intl.DateTimeFormat('en-US', { weekday: 'short' }).format(dt);
            let time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).format(dt).toLowerCase().replace(' ', '');
            return `<span class="badge bg-white text-dark border px-1 py-1 local-time-badge" data-utc="${data.fixture.date}" style="font-size: 0.65rem; white-space: nowrap;">${day} ${time}</span>`;
        } catch (err) {
            return `<span class="badge bg-white text-dark border px-1 py-1" style="font-size: 0.65rem; white-space: nowrap;">${data.fixture.date}</span>`;
        }
    }
    
    function getLatestEventHtml(data, rib = false) {
        if (!data.events || data.events.length === 0) return rib ? `<div class="text-muted text-start w-100 ps-2" style="font-size: 0.6rem; font-style: italic;">No Events</div>` : '';
        const ev = data.events[data.events.length - 1], isH = ev.team_id === data.teams.home.id;
        const n = isH ? data.teams.home.name : data.teams.away.name, lg = isH ? data.teams.home.logo : data.teams.away.logo;
        if (ev.type === 'subst') {
            const pOut = shortenPlayerName(ev.player), pIn = shortenPlayerName(ev.player_out);
            return rib ? `<div class="text-dark fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3;"><div class="text-truncate">🔄 <img src="${lg}" loading="lazy" decoding="async" style="width: 12px; height: 12px;" class="me-1">${ev.time}'</div><div class="text-truncate">🟢 <span class="text-success">${pIn}</span></div><div class="text-muted text-truncate">🔴 ${pOut}</div></div>`
                       : `<div class="ms-2 d-flex align-items-center text-dark fw-bold" style="font-size: 0.65rem; line-height: 1.2; min-width: 0;"><div class="d-flex align-items-center me-2"><span class="bg-primary text-white rounded d-flex justify-content-center align-items-center me-1" style="width: 14px; height: 14px; font-size: 0.55rem;">🔄</span><img src="${lg}" loading="lazy" decoding="async" style="width: 14px; height: 14px; object-fit: contain;" class="me-1"><span>${ev.time}'</span></div><div class="d-flex flex-column text-start" style="min-width: 0;"><div class="text-truncate"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color:#20c997; margin-bottom:1px; margin-right:3px;"></span>${pIn}</div><div class="text-muted text-truncate"><span style="display:inline-block; width:8px; height:8px; border-radius:50%; background-color:#dc3545; margin-bottom:1px; margin-right:3px;"></span>${pOut}</div></div></div>`;
        } else {
            let ic = '🟨', tc = 'text-warning'; if (ev.type === 'Goal') { ic = '⚽'; tc = 'text-success'; } else if (ev.type === 'Red Card') { ic = '🟥'; tc = 'text-danger'; }
            const pn = shortenPlayerName(ev.player || n);
            return rib ? `<div class="${tc} fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3;"><div class="text-truncate"><img src="${lg}" loading="lazy" decoding="async" style="width: 12px; height: 12px;" class="me-1">${ev.time}'</div><div class="text-truncate">${ic} ${pn}</div>${ev.type==='Goal'&&ev.assist?`<div class="text-muted text-truncate" style="font-size: 0.55rem;">👟 ${shortenPlayerName(ev.assist)}</div>`:''}</div>`
                       : `<div class="ms-2 d-flex flex-column text-start ${tc} fw-bold" style="font-size: 0.65rem; line-height: 1.2; min-width: 0;"><div class="text-truncate">${ic} ${ev.time}' <img src="${lg}" loading="lazy" decoding="async" style="width: 12px; height: 12px;" class="mx-1">${pn}</div>${ev.type==='Goal'&&ev.assist?`<div class="text-muted text-truncate fw-normal" style="font-size: 0.55rem;"><span style="display:inline-block; width:12px;"></span>👟 ${shortenPlayerName(ev.assist)}</div>`:''}</div>`;
        }
    }
    
    function getRibbonHtml(data) {
        const isPre = ['NS','TBD','PST','CANC','ABD'].includes(data.fixture.status.short);
        const l_flag = data.league.flag || "";
        const flg = l_flag.startsWith('http') || l_flag.startswith('images/') ? `<img src="${l_flag}" loading="lazy" decoding="async" style="width: 20px; height: 20px; object-fit: contain; margin-right: 6px; vertical-align: middle; border-radius: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">` : `<span style="font-size: 1.1rem; margin-right: 6px; vertical-align: middle; line-height: 1;">${l_flag || "🏆"}</span>`;
        return `<div class="row g-0 align-items-center py-2" style="transition: background-color 0.2s;"><div class="col-3 text-center d-flex flex-column justify-content-center align-items-center border-end pe-1 ps-1"><div style="margin-bottom: 3px;">${getTimeBadgeHtml(data)}</div><a href="/leagues/${data.league.slug}/" onclick="event.stopPropagation();" class="text-decoration-none text-muted fw-bold text-truncate w-100 px-1 d-inline-block" style="font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase;" title="${data.league.name}">${flg}${data.league.abbrev}</a></div><div class="col-5 px-2"><div class="d-flex justify-content-between align-items-center mb-1"><span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 88%;"><img src="${data.teams.home.logo}" loading="lazy" decoding="async" width="14" height="14" class="me-1" style="object-fit:contain;">${data.teams.home.name}</span><div class="text-end" style="min-width: fit-content; white-space: nowrap;"><span class="fw-bold text-dark" style="font-size: 0.85rem;">${isPre?'-':(data.goals?.home??0)}</span></div></div><div class="d-flex justify-content-between align-items-center"><span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 88%;"><img src="${data.teams.away.logo}" loading="lazy" decoding="async" width="14" height="14" class="me-1" style="object-fit:contain;">${data.teams.away.name}</span><div class="text-end" style="min-width: fit-content; white-space: nowrap;"><span class="fw-bold text-dark" style="font-size: 0.85rem;">${isPre?'-':(data.goals?.away??0)}</span></div></div></div><div class="col-4 text-center border-start d-flex justify-content-center align-items-center">${getLatestEventHtml(data, true)}</div></div>`;
    }
    
    function getCenterColumnHtml(data) {
        if (['NS','TBD','PST','CANC','ABD'].includes(data.fixture.status.short) || !data.team_stats) return `<div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">${data.goals?.home??0} - ${data.goals?.away??0}</div>`;
        const ts = data.team_stats;
        const hc = (data.homeLineup?.team?.colors?.player?.primary) ? `#${data.homeLineup.team.colors.player.primary.replace('#','')}` : '#0d6efd';
        const ac = (data.awayLineup?.team?.colors?.player?.primary) ? `#${data.awayLineup.team.colors.player.primary.replace('#','')}` : '#dc3545';
        const bb = (lbl, hv, av, p) => `<div class="text-center w-100 px-1"><div class="stat-label-tiny">${lbl}</div><div class="stat-bar-container"><div class="stat-bar-segment" style="width: ${hv+av===0?50:hv/(hv+av)*100}%; background-color: ${hc}; color: ${getContrastColor(hc)};">${p?hv+'%':hv}</div><div class="stat-bar-segment" style="width: ${hv+av===0?50:av/(hv+av)*100}%; background-color: ${ac}; color: ${getContrastColor(ac)};">${p?av+'%':av}</div></div></div>`;
        return `<div class="fw-bold text-dark mx-2 mb-1" style="font-size: 1.1rem; line-height: 1;">${data.goals?.home??0} - ${data.goals?.away??0}</div>${bb("Possession", ts.home?.possession??0, ts.away?.possession??0, true)}${bb("Total Shots", ts.home?.total_shots??0, ts.away?.total_shots??0)}${bb("Shots on Target", ts.home?.shots_on_target??0, ts.away?.shots_on_target??0)}${bb("Corners", ts.home?.corners??0, ts.away?.corners??0)}<div class="text-center w-100 px-1 mt-1"><div class="stat-label-tiny" style="margin-bottom: 0px;">Cards</div><div class="d-flex justify-content-between text-muted" style="font-size: 0.65rem; font-weight: 700;"><span>🟨 ${ts.home?.yellow_cards??0} 🟥 ${ts.home?.red_cards??0}</span><span>🟨 ${ts.away?.yellow_cards??0} 🟥 ${ts.away?.red_cards??0}</span></div></div>`;
    }
    
    function getEventsHtml(data) {
        if (!data.events || !data.events.length) return '';
        const fe = (e, tn) => {
            if (e.type === 'subst') return `<div class="d-flex align-items-start mb-1" style="line-height: 1.1;"><div class="text-secondary fw-bold pe-1" style="width: 25px; text-align: right; font-size: 0.6rem;">${e.time}'</div><div style="width: 16px; text-align: center;" class="me-1">🔄</div><div class="text-truncate"><span class="text-dark fw-bold">${shortenPlayerName(e.player_out)}</span> IN<br><span class="text-muted" style="font-size: 0.55rem;">(${shortenPlayerName(e.player)} OUT)</span></div></div>`;
            return `<div class="d-flex align-items-start mb-1" style="line-height: 1.1;"><div class="text-secondary fw-bold pe-1" style="width: 25px; text-align: right; font-size: 0.6rem;">${e.time}'</div><div style="width: 16px; text-align: center;" class="me-1">${e.type==='Goal'?'⚽':(e.type==='Red Card'?'🟥':'🟨')}</div><div class="text-truncate"><span class="text-dark fw-bold">${shortenPlayerName(e.player||tn)}</span>${e.type==='Goal'&&e.assist?`<br><span class="text-muted fw-normal" style="font-size: 0.55rem;">👟 ${shortenPlayerName(e.assist)}</span>`:''}</div></div>`;
        };
        const he = [...data.events].filter(e=>e.team_id===data.teams.home.id).reverse(), ae = [...data.events].filter(e=>e.team_id===data.teams.away.id).reverse(), nc = Math.max(he.length, ae.length) > 1;
        return `<div class="w-100 px-2 pt-1 mt-1 border-top text-muted" style="font-size: 0.65rem; cursor: pointer; transition: background-color 0.2s;" onclick="if(${nc}) { const isExp = this.classList.toggle('is-expanded'); this.querySelector('.event-collapsed').classList.toggle('d-none', isExp); this.querySelector('.event-expanded').classList.toggle('d-none', !isExp); }"><div class="event-collapsed"><div class="d-flex justify-content-between"><div class="text-start" style="flex: 1; min-width: 0;">${he.length?fe(he[0], data.teams.home.name):''}</div><div class="text-start" style="flex: 1; min-width: 0;">${ae.length?fe(ae[0], data.teams.away.name):''}</div></div>${nc?`<div class="text-center text-secondary w-100" style="font-size: 0.60rem;">▼</div>`:''}</div><div class="event-expanded d-none"><div class="d-flex justify-content-between"><div class="text-start" style="flex: 1; min-width: 0;">${he.map(e=>fe(e, data.teams.home.name)).join('')}</div><div class="text-start" style="flex: 1; min-width: 0;">${ae.map(e=>fe(e, data.teams.away.name)).join('')}</div></div><div class="text-center text-secondary w-100" style="font-size: 0.60rem;">▲</div></div></div>`;
    }
    
    function triggerCardGlow(fixId, eventType) {
        const card = document.getElementById(`card-${fixId}`); if (!card) return;
        const typeLower = (eventType || '').toLowerCase();
        let glowClass = 'glow-goal';
        if (typeLower.includes('red')) glowClass = 'glow-red-card';
        else if (typeLower.includes('yellow')) glowClass = 'glow-yellow-card';
        else if (typeLower.includes('sub')) glowClass = 'glow-subst';
        card.classList.remove('glow-goal', 'glow-red-card', 'glow-yellow-card', 'glow-subst');
        void card.offsetWidth; 
        card.classList.add(glowClass);
        setTimeout(() => { card.classList.remove(glowClass); }, 4000);
    }
    
    function detectNewEventsAndGlow(oldEvents, newEvents, fixId) {
        if (!newEvents || newEvents.length === 0) return;
        const known = new Set((oldEvents || []).map(e => `${e.time}_${e.type}_${e.player}_${e.player_out || ''}`));
        const fresh = newEvents.filter(e => !known.has(`${e.time}_${e.type}_${e.player}_${e.player_out || ''}`));
        if (fresh.length) triggerCardGlow(fixId, fresh[fresh.length - 1].type);
    }

    async function pollAndUpdateDOM() {
        try {
            const res = await fetch(window.location.href, { cache: 'no-store' }); if (!res.ok) return;
            const htmlText = await res.text(), startStr = "const STATIC_MATCHES = ", sIdx = htmlText.indexOf(startStr);
            if (sIdx === -1) return;
            const jStart = sIdx + startStr.length, jEnd = htmlText.indexOf("let ACTIVE_DAY", jStart);
            if (jEnd === -1) return;
            
            const rawJson = htmlText.substring(jStart, jEnd).trim().replace(/;$/, '');
            const freshData = JSON.parse(rawJson);
            const freshMatches = freshData[ACTIVE_DAY] || [], oldMatches = STATIC_MATCHES[ACTIVE_DAY] || [];

            const finishedStates = ['FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD'];

            freshMatches.forEach(nm => {
                const fixId = nm.fixture.id, om = oldMatches.find(m => m.fixture.id === fixId);
                if (!om) return;

                const freshStatus = nm.fixture?.status?.short;
                const oldStatus = om.fixture?.status?.short;
                if (finishedStates.includes(freshStatus) || finishedStates.includes(oldStatus)) {
                    return;
                }

                detectNewEventsAndGlow(om.events, nm.events, fixId);

                const tEl = document.getElementById(`time-${fixId}`); if (tEl) { const html = `${getTimeBadgeHtml(nm)} ${getLatestEventHtml(nm)}`; if(tEl.innerHTML!==html) tEl.innerHTML=html; }
                const sEl = document.getElementById(`score-${fixId}`); if (sEl) { const html = getCenterColumnHtml(nm); if(sEl.innerHTML!==html) sEl.innerHTML=html; }
                const eEl = document.getElementById(`events-${fixId}`); if (eEl) { const html = getEventsHtml(nm); if(eEl.innerHTML!==html) eEl.innerHTML=html; }
                const rEl = document.getElementById(`ribbon-${fixId}`); if (rEl) { const html = getRibbonHtml(nm); if(rEl.innerHTML!==html) rEl.innerHTML=html; }

                Object.assign(om, nm);
            });
        } catch (err) { console.error("Silent update check failed:", err); }
    }
</script>
</body>
</html>
"""

def generate_v2_index():
    print("\n==================================================")
    print("⏳ STARTING SSG BUILD PIPELINE (PURE JSON API)")
    print("==================================================")
    
    os.makedirs('v2', exist_ok=True)
    file_path = 'v2/index.html'

    old_html = ""
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            old_html = f.read()

    day_info = get_3day_dates()
    
    raw_matches_by_day = {
        "yesterday": fetch_espn_scores_for_date(day_info["dates"]["yesterday"], old_html),
        "today": fetch_espn_scores_for_date(day_info["dates"]["today"], old_html),
        "tomorrow": fetch_espn_scores_for_date(day_info["dates"]["tomorrow"], old_html)
    }

    leagues_by_day = {
        day: group_and_sort_matches_by_league(matches)
        for day, matches in raw_matches_by_day.items()
    }
    
    print(f"\n==================================================")
    print(f"📊 SSG BUILD SUMMARY:")
    print(f"  ├─ Yesterday ({day_info['dates']['yesterday']}): {len(raw_matches_by_day['yesterday'])} matches parsed")
    print(f"  ├─ Today     ({day_info['dates']['today']}):     {len(raw_matches_by_day['today'])} matches parsed")
    print(f"  └─ Tomorrow  ({day_info['dates']['tomorrow']}):  {len(raw_matches_by_day['tomorrow'])} matches parsed")
    print(f"==================================================")
    
    template = Template(HTML_TEMPLATE)
    output_html = template.render(
        leagues_by_day=leagues_by_day,
        matches_json=json.dumps(raw_matches_by_day),
        display_dates=day_info["display"]
    )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(output_html)
    
    file_size_kb = round(os.path.getsize(file_path) / 1024, 2)
    print(f"\n🎉 Successfully compiled TRUE STATIC frontend at {file_path} ({file_size_kb} KB)")

if __name__ == "__main__":
    generate_v2_index()

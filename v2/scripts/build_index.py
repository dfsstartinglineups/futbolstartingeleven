import os
import re
import json
import requests
import traceback
import unicodedata
from datetime import datetime, timedelta
import pytz
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
    "fifa world cup qualifying - afc": "https://a.espncdn.com/i/leaguelogos/soccer/500/62.png",
    "fifa world cup qualifying - caf": "https://a.espncdn.com/i/leaguelogos/soccer/500/63.png",
    "fifa world cup qualifying - conmebol": "https://a.espncdn.com/i/leaguelogos/soccer/500/65.png",
    "fifa world cup qualifying - concacaf": "https://a.espncdn.com/i/leaguelogos/soccer/500/64.png",
    "fifa world cup qualifying - ofc": "https://a.espncdn.com/i/leaguelogos/soccer/500/66.png",
    "fifa world cup qualifying - uefa": "https://a.espncdn.com/i/leaguelogos/soccer/500/67.png",
    "french ligue 1": "https://a.espncdn.com/i/leaguelogos/soccer/500/9.png",
    "french ligue 2": "https://a.espncdn.com/i/leaguelogos/soccer/500/96.png",
    "german 2. bundesliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/97.png",
    "german bundesliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/10.png",
    "german cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2061.png",
    "greek super league": "https://a.espncdn.com/i/leaguelogos/soccer/500/98.png",
    "guatemalan liga nacional": "https://a.espncdn.com/i/leaguelogos/soccer/500/2248.png",
    "honduran liga nacional": "https://a.espncdn.com/i/leaguelogos/soccer/500/2247.png",
    "indian super league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2334.png",
    "international friendly": "https://a.espncdn.com/i/leaguelogos/soccer/500/53.png",
    "italian serie a": "https://a.espncdn.com/i/leaguelogos/soccer/500/12.png",
    "italian serie b": "https://a.espncdn.com/i/leaguelogos/soccer/500/99.png",
    "japanese j.league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2199.png",
    "leagues cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2410.png",
    "liga mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/22.png",
    "liga bbva mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/22.png",
    "liga expansion mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/2306.png",
    "liga de expansion mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/2306.png",
    "liga auf uruguaya": "https://a.espncdn.com/i/leaguelogos/soccer/500/1592.png",
    "ligapro ecuador": "https://a.espncdn.com/i/leaguelogos/soccer/500/1944.png",
    "mls": "https://a.espncdn.com/i/leaguelogos/soccer/500/19.png",
    "men's olympic soccer tournament": "https://a.espncdn.com/i/leaguelogos/soccer/500/71.png",
    "mexican liga bbva mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/22.png",
    "mexican liga de expansión mx": "https://a.espncdn.com/i/leaguelogos/soccer/500/2306.png",
    "ncaa men's soccer": "https://a.espncdn.com/combiner/i?img=/redesign/assets/img/icons/sports-soccer-solid.png",
    "ncaa women's soccer": "https://a.espncdn.com/combiner/i?img=/redesign/assets/img/icons/sports-soccer-solid.png",
    "northern super league": "https://flagcdn.com/w40/ca.png",
    "nwsl": "https://a.espncdn.com/i/leaguelogos/soccer/500/2323.png",
    "nwsl challenge cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/2445.png",
    "paraguayan primera división": "https://a.espncdn.com/i/leaguelogos/soccer/500/1892.png",
    "peruvian liga 1": "https://a.espncdn.com/i/leaguelogos/soccer/500/1813.png",
    "portuguese primeira liga": "https://a.espncdn.com/i/leaguelogos/soccer/500/14.png",
    "russian premier league": "https://a.espncdn.com/i/leaguelogos/soccer/500/106.png",
    "salvadoran primera division": "https://a.espncdn.com/i/leaguelogos/soccer/500/2244.png",
    "saudi pro league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2488.png",
    "scottish premiership": "https://a.espncdn.com/i/leaguelogos/soccer/500/45.png",
    "spanish copa del rey": "https://a.espncdn.com/i/leaguelogos/soccer/500/80.png",
    "spanish laliga": "https://a.espncdn.com/i/leaguelogos/soccer/500/15.png",
    "spanish laliga 2": "https://a.espncdn.com/i/leaguelogos/soccer/500/107.png",
    "spanish supercopa": "https://a.espncdn.com/i/leaguelogos/soccer/500/431.png",
    "swedish allsvenskan": "https://a.espncdn.com/i/leaguelogos/soccer/500/16.png",
    "trofeo joan gamper": "🏆",
    "turkish super lig": "https://a.espncdn.com/i/leaguelogos/soccer/500/18.png",
    "u.s. open cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/69.png",
    "uefa champions league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2.png",
    "uefa conference league": "https://a.espncdn.com/i/leaguelogos/soccer/500/20296.png",
    "uefa europa league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2310.png",
    "uefa european championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/74.png",
    "uefa european championship qualifying": "https://a.espncdn.com/i/leaguelogos/soccer/500/56.png",
    "uefa european under-19 championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/2297.png",
    "uefa european under-21 championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/2284.png",
    "uefa nations league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2395.png",
    "uefa super cup": "https://a.espncdn.com/i/leaguelogos/soccer/500/1272.png",
    "uefa women's champions league": "https://a.espncdn.com/i/leaguelogos/soccer/500/2408.png",
    "uefa women's european championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/2381.png",
    "usl championship": "https://a.espncdn.com/i/leaguelogos/soccer/500/2292.png",
    "usl league one": "https://a.espncdn.com/i/leaguelogos/soccer/500/2452.png",
    "usl super league": "https://flagcdn.com/w40/us.png",
    "venezuelan primera división": "https://a.espncdn.com/i/leaguelogos/soccer/500/1947.png",
    "women's international friendly": "https://a.espncdn.com/i/leaguelogos/soccer/500/70.png",
    "women's olympic soccer tournament": "https://a.espncdn.com/i/leaguelogos/soccer/500/84.png",
}

COUNTRY_FLAG_URLS = {
    "belgian": "be", "chilean": "cl", "chinese": "cn", "dutch": "nl",
    "english": "gb-eng", "french": "fr", "german": "de", "bolivian": "bo", "bolivia": "bo",
    "norwegian": "no", "russian": "ru", "portuguese": "pt", "portugal": "pt",
    "scottish": "gb-sct", "swedish": "se", "argentine": "ar", "brazilian": "br", "brazil": "br",
    "italian": "it", "mexican": "mx", "mexico": "mx", "mx": "mx", "paraguayan": "py", "japanese": "jp",
    "spanish": "es", "danish": "dk", "indian": "in", "uruguay": "uy", 
    "peruvian": "pe", "peru": "pe", "salvadoran": "sv", "el salvador": "sv",
    "costa rican": "cr", "costa rica": "cr", "fpd": "cr"
}

def normalize_text(text):
    if not text: return ""
    nfkd_form = unicodedata.normalize('NFD', text)
    return "".join([c for c in nfkd_form if unicodedata.category(c) != 'Mn']).lower().strip()

# Pre-normalize dictionary keys on startup
NORMALIZED_HUMAN_LEAGUE_FLAGS = {
    normalize_text(key): val for key, val in HUMAN_LEAGUE_FLAGS.items()
}

# Map text abbreviations to ESPN Slugs
ABBREV_TO_SLUG = {
    "EPL": "eng.1", "MLS": "usa.1", "UCL": "uefa.champions",
    "UEL": "uefa.europa", "UECL": "uefa.europa.conf", "LIGA": "esp.1",
    "SERA": "ita.1", "BUND": "ger.1", "LIG1": "fra.1",
    "LMX": "mex.1", "EXP": "mex.2", "NWSL": "usa.nwsl",
    "DEN": "den.1", "SWE": "swe.1", "LPF": "arg.1",
    "RUS": "rus.1", "USL": "usa.usl.1", "SCO": "sco.1",
    "ERED": "ned.1", "POR": "por.1", "BSA": "bra.1", "ECU": "ecu.1",
    "CDR": "esp.copa_del_rey", "FA": "eng.fa", "EFL": "eng.league_cup",
    "DFB": "ger.dfb_pokal", "COPPA": "ita.coppa_italia", "ASEAN": "aff.championship"
}

def create_slug(name):
    if not name: return ""
    slug = name.lower()
    slug = re.sub(r'[\/]', '-', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')

def to_snake_case(name):
    s = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s).lower()

def generate_league_abbrev(name):
    if not name or name == "Global Football": return "GLB"
    name_upper = name.upper()
    
    overrides = {
        "ENGLISH PREMIER LEAGUE": "EPL", "SCOTTISH PREMIERSHIP": "SCO",
        "RUSSIAN PREMIER": "RUS", "PREMIER LEAGUE": "EPL", 
        "BRAZILIAN SERIE A": "BSA", "ECUADORIAN SERIE A": "ECU",
        "ITALIAN SERIE A": "SERA", "SERIE A": "SERA", 
        "MEXICAN LIGA BBVA MX": "LMX", "LIGA DE EXPANSIÓN MX": "EXP",
        "LIGA DE EXPANSION MX": "EXP", "LIGA MX": "LMX",
        "SPANISH LALIGA": "LIGA", "LALIGA": "LIGA", "PORTUGUESE LIGA": "POR",
        "GERMAN BUNDESLIGA": "BUND", "BUNDESLIGA": "BUND",
        "FRENCH LIGUE 1": "LIG1", "LIGUE 1": "LIG1",
        "DANISH SUPERLIGA": "DEN", "DENMARK SUPERLIGA": "DEN",
        "SWEDISH ALLSVENSKAN": "SWE", "ALLSVENSKAN": "ALLS",
        "ARGENTINE LPF": "LPF", "ARGENTINA LPF": "LPF",
        "MAJOR LEAGUE SOCCER": "MLS", "MLS": "MLS", "NWSL": "NWSL",
        "USL CHAMPIONSHIP": "USL", "UEFA EUROPA CONFERENCE LEAGUE": "UECL",
        "UEFA CHAMPIONS LEAGUE": "UCL", "UEFA EUROPA LEAGUE": "UEL",
        "CLUB FRIENDLY": "FRND", "FRIENDLY": "FRND",
        "ASEAN CHAMP": "ASEAN", "DUTCH EREDIVISIE": "ERED",
        "COPA DEL REY": "CDR", "FA CUP": "FA", "EFL CUP": "EFL",
        "DFB POKAL": "DFB", "COPPA ITALIA": "COPPA"
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

def parse_espn_summary(event_id, league_code="all", match_label="Match"):
    headers = {'User-Agent': 'Mozilla/5.0'}
    summary_data = {
        "team_stats": None, "homeLineup": None, "awayLineup": None, "events": [],
        "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
        "injuries": {"home": [], "away": []}
    }

    urls_to_try = []
    if league_code and league_code not in ["all", "soccer", ""]:
        urls_to_try.append(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_code}/summary?event={event_id}")
    urls_to_try.append(f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={event_id}")
    urls_to_try.append(f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/all/summary?event={event_id}")

    res = None
    for url in urls_to_try:
        try:
            r = requests.get(url, headers=headers, timeout=6)
            if r.status_code == 200:
                res = r
                break
        except Exception: continue

    if not res or res.status_code != 200: return summary_data

    try:
        data = res.json()
        boxscore = data.get('boxscore', {})
        teams_box = boxscore.get('teams', [])
        if len(teams_box) == 2:
            def extract_stat_dict(stats_list):
                if not isinstance(stats_list, list): return {}
                return {s.get('name'): s.get('displayValue', '0') for s in stats_list if isinstance(s, dict)}

            home_idx = 0 if teams_box[0].get('homeAway') == 'home' else 1
            away_idx = 1 if home_idx == 0 else 0
            h_raw = extract_stat_dict(teams_box[home_idx].get('statistics', []))
            a_raw = extract_stat_dict(teams_box[away_idx].get('statistics', []))

            def clean_num(val_str):
                cleaned = re.sub(r'[^0-9.]', '', str(val_str))
                return int(float(cleaned)) if cleaned else 0

            if h_raw or a_raw:
                summary_data["team_stats"] = {
                    "home": {
                        "possession": clean_num(h_raw.get('possessionPct', 50)),
                        "total_shots": clean_num(h_raw.get('totalShots', 0)),
                        "shots_on_target": clean_num(h_raw.get('shotsOnTarget', 0)),
                        "corners": clean_num(h_raw.get('cornerKicks', 0)),
                        "yellow_cards": clean_num(h_raw.get('yellowCards', 0)),
                        "red_cards": clean_num(h_raw.get('redCards', 0))
                    },
                    "away": {
                        "possession": clean_num(a_raw.get('possessionPct', 50)),
                        "total_shots": clean_num(a_raw.get('totalShots', 0)),
                        "shots_on_target": clean_num(a_raw.get('shotsOnTarget', 0)),
                        "corners": clean_num(a_raw.get('cornerKicks', 0)),
                        "yellow_cards": clean_num(a_raw.get('yellowCards', 0)),
                        "red_cards": clean_num(a_raw.get('redCards', 0))
                    }
                }

        rosters = data.get('rosters', [])
        if isinstance(rosters, list) and len(rosters) >= 2:
            for r_data in rosters:
                home_away = r_data.get('homeAway', 'home')
                key = "homeLineup" if home_away == 'home' else "awayLineup"
                formation = r_data.get('formation', '4-3-3')
                team_obj = r_data.get('team', {})
                start_xi, subs = [], []
                
                player_entries = r_data.get('roster', [])
                if isinstance(player_entries, list):
                    for entry in player_entries:
                        ath = entry.get('athlete', {})
                        pos_abbr = entry.get('position', {}).get('abbreviation', 'M')
                        is_starter = entry.get('starter', False)
                        subbed_in = entry.get('subbedIn', False) or bool(entry.get('subbedInMinute'))
                        subbed_out = entry.get('subbedOut', False) or bool(entry.get('subbedOutMinute'))
                        did_play = entry.get('didPlay', False) or entry.get('played', False) or subbed_in

                        stats_raw = entry.get('stats', [])
                        live_stats = {}
                        if isinstance(stats_raw, list):
                            for st in stats_raw:
                                if isinstance(st, dict):
                                    raw_k = st.get('name', '')
                                    raw_v = st.get('displayValue', st.get('value', 0))
                                    try: num_v = int(float(str(raw_v)))
                                    except (ValueError, TypeError): num_v = raw_v

                                    live_stats[raw_k] = num_v
                                    snake_k = to_snake_case(raw_k)
                                    live_stats[snake_k] = num_v

                                    if raw_k == 'goalsConceded': live_stats['conceded'] = num_v
                                    elif raw_k == 'shotsOnTarget': live_stats['shots_on_target'] = num_v
                                    elif raw_k == 'totalShots': live_stats['total_shots'] = num_v
                                    elif raw_k == 'keyPasses': live_stats['key_passes'] = num_v
                                    elif raw_k == 'yellowCards': live_stats['yellow_cards'] = num_v

                        player_obj = {
                            "id": str(ath.get('id', '')), "name": ath.get('displayName', 'Unknown'),
                            "pos": pos_abbr, "number": str(entry.get('jersey', '')),
                            "photo": ath.get('headshot', {}).get('href', '') if isinstance(ath.get('headshot'), dict) else '',
                            "live_stats": live_stats, "isSubbedIn": subbed_in, "isSubbedOut": subbed_out,
                            "subMinute": str(entry.get('subbedInMinute') or entry.get('subbedOutMinute') or '')
                        }
                        
                        if is_starter: start_xi.append({"player": player_obj, "sub_history": []})
                        else:
                            if did_play or live_stats: subs.append({"player": player_obj})

                if start_xi:
                    summary_data[key] = {
                        "formation": formation, "team": {"colors": {"player": {"primary": team_obj.get('color', '0d6efd')}}},
                        "startXI": start_xi, "substitutes": subs
                    }

        key_events = data.get('keyEvents', [])
        if isinstance(key_events, list) and len(key_events) > 0:
            for ev in key_events:
                ev_text = ev.get('type', {}).get('text', '')
                clock_text = ev.get('clock', {}).get('displayValue', "0'")
                team_id = str(ev.get('team', {}).get('id', ''))
                
                participants = ev.get('participants', [])
                p_in = participants[0].get('athlete', {}).get('displayName', '') if len(participants) > 0 else ''
                p_out = participants[1].get('athlete', {}).get('displayName', '') if len(participants) > 1 else ''

                is_sub = "substitution" in ev_text.lower() or "sub" in ev_text.lower()
                ev_type = "Goal" if "goal" in ev_text.lower() else ("subst" if is_sub else "Card")

                if ev_type == "subst":
                    p_player = p_out if p_out else "Unknown"
                    p_player_out = p_in if p_in else "Unknown"
                else:
                    p_player = p_in if p_in else "Unknown"
                    p_player_out = p_out if p_out else None

                summary_data["events"].append({
                    "time": clock_text.replace("'", ""), "team_id": team_id, "type": ev_type,
                    "detail": ev_text, "player": p_player, "player_out": p_player_out, "assist": p_out if ev_type == "Goal" else None
                })

        pickcenter = data.get('pickcenter', []) or data.get('odds', [])
        if isinstance(pickcenter, list) and len(pickcenter) > 0:
            odds_item = pickcenter[0]
            h_ml = odds_item.get('homeTeamOdds', {}).get('moneyLine')
            a_ml = odds_item.get('awayTeamOdds', {}).get('moneyLine')
            d_ml = odds_item.get('drawOdds', {}).get('moneyLine')
            ou_line = odds_item.get('overUnder', odds_item.get('total', {}).get('displayName', 'TBD'))

            summary_data["odds"] = {
                "home": f"+{h_ml}" if h_ml and int(h_ml) > 0 else str(h_ml or 'TBD'),
                "draw": f"+{d_ml}" if d_ml and int(d_ml) > 0 else str(d_ml or 'TBD'),
                "away": f"+{a_ml}" if a_ml and int(a_ml) > 0 else str(a_ml or 'TBD'),
                "total": str(ou_line), "over": str(odds_item.get('overOdds', 'TBD')), "under": str(odds_item.get('underOdds', 'TBD'))
            }

        injuries_raw = data.get('injuries', [])
        if isinstance(injuries_raw, list) and len(injuries_raw) == 2:
            for idx, key in [(0, "home"), (1, "away")]:
                inj_list = [item.get('athlete', {}).get('displayName', '') for item in injuries_raw[idx].get('injuries', []) if item.get('athlete', {}).get('displayName')]
                summary_data["injuries"][key] = inj_list

    except Exception as e: print(f"    ❌ EXCEPTION in parse_espn_summary for event {event_id}: {e}")
    return summary_data

def fetch_espn_scores_for_date(date_str):
    headers = {'User-Agent': 'Mozilla/5.0'}
    raw_events = []
    seen_ids = set()

    print(f"\n==================================================")
    print(f"📅 FETCHING MASTER SCOREBOARD FOR DATE: {date_str}")
    print(f"==================================================")

    page = 1
    max_pages = 10

    while page <= max_pages:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}&limit=1000&page={page}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200: break
            
            data = res.json()
            events = data.get('events', [])
            if not events: break

            added_this_page = 0
            for ev in events:
                ev_id = str(ev.get('id', ''))
                if ev_id and ev_id not in seen_ids:
                    seen_ids.add(ev_id)
                    raw_events.append(ev)
                    added_this_page += 1

            print(f"  ├─ Page {page}: fetched {len(events)} events ({added_this_page} new)")
            if added_this_page == 0: break
            page += 1
        except Exception as e:
            print(f"  ❌ Error fetching page {page} for {date_str}: {e}")
            break

    print(f"✅ Total unique matches retrieved for {date_str}: {len(raw_events)}")

    matches = []
    summary_calls = 0

    for event in raw_events:
        try:
            event_id = str(event['id'])
            competitions = event.get('competitions', [])
            if not competitions: continue

            comp = competitions[0]
            competitors = comp.get('competitors', [])
            
            home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
            away = next((c for c in competitors if c.get('homeAway') == 'away'), None)
            if not home or not away: continue

            home_name = home['team']['displayName']
            away_name = away['team']['displayName']
            match_label = f"{home_name} vs {away_name}"

            alt_note = comp.get('altGameNote')
            league_obj = (
                event.get('league') or comp.get('league') or 
                (event.get('leagues', [{}])[0] if isinstance(event.get('leagues'), list) and event.get('leagues') else {}) or
                (comp.get('leagues', [{}])[0] if isinstance(comp.get('leagues'), list) and comp.get('leagues') else {})
            )

            fallback_name = league_obj.get('name') or league_obj.get('displayName') or league_obj.get('midsizeName') or "Global Football"
            final_league_name = alt_note if alt_note else fallback_name
            final_league_name = re.sub(r'^\d{4}-\d{4}\s+', '', final_league_name).strip()

            espn_league_slug = (league_obj.get('slug') or event.get('league', {}).get('slug') or comp.get('league', {}).get('slug') or 'all')

            league_abbrev = generate_league_abbrev(final_league_name)
            league_slug = create_slug(final_league_name)
            
            # RESOLVE LEAGUE FLAG (Direct accent-insensitive mapping)
            clean_league_name = normalize_text(final_league_name)
            league_flag = NORMALIZED_HUMAN_LEAGUE_FLAGS.get(clean_league_name, "")
            
            # PARENT STRIPPER RULE
            if not league_flag:
                base_name = re.sub(r'\s+(qualifying|qualifiers|playoffs?)\b', '', clean_league_name)
                league_flag = NORMALIZED_HUMAN_LEAGUE_FLAGS.get(base_name, "")
                
            if not league_flag:
                league_logos = league_obj.get('logos', [])
                if isinstance(league_logos, list) and len(league_logos) > 0:
                    href = league_logos[0].get('href', '')
                    if href and 'default-team-logo' not in href:
                        league_flag = href
                elif isinstance(league_obj.get('logo'), str):
                    logo = league_obj.get('logo')
                    if logo and 'default-team-logo' not in logo:
                        league_flag = logo

            # SMART FALLBACK RULES (Country -> Africa -> Continental -> Friendlies -> Cups)
            if not league_flag:
                name_lower = clean_league_name
                
                # Rule 1: Country Flags
                for country, code in COUNTRY_FLAG_URLS.items():
                    if re.search(rf'\b{country}\b', name_lower):
                        league_flag = f"https://flagcdn.com/w40/{code}.png"
                        break
                        
                # Rule 2: Africa
                if not league_flag and re.search(r'\b(africa|african|caf)\b', name_lower):
                    league_flag = "🌍"
                
                # Rule 3: International / Continental
                if not league_flag and re.search(r'\b(international|concacaf|conmebol|uefa|olympic|nations|saff|americ)\b', name_lower):
                    league_flag = "🌎"
                    
                # Rule 4: Friendlies
                if not league_flag and 'friendly' in name_lower:
                    league_flag = "🤝"
                    
                # Rule 5: Cups (Lowest Priority catch-all)
                if not league_flag and 'cup' in name_lower:
                    league_flag = "🏆"

            status_obj = event.get('status', {})
            status_type = status_obj.get('type', {})
            state = status_type.get('state', 'pre')
            short_detail = status_type.get('shortDetail', '')

            if state == 'pre': status_short = 'NS'
            elif state == 'post': status_short = 'FT'
            else: status_short = short_detail if short_detail else 'LIVE'

            elapsed = status_obj.get('period', 0)
            should_fetch, fetch_reason = should_fetch_summary(event)

            if should_fetch:
                summary = parse_espn_summary(event_id, league_code=espn_league_slug, match_label=match_label)
                summary_calls += 1
            else:
                summary = {
                    "team_stats": None, "homeLineup": None, "awayLineup": None, "events": [],
                    "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"},
                    "injuries": {"home": [], "away": []}
                }

            matches.append({
                "fixture": {"id": event_id, "date": event['date'], "status": {"short": status_short, "elapsed": elapsed}},
                "league": {"id": event_id, "name": final_league_name, "abbrev": league_abbrev, "slug": league_slug, "flag": league_flag},
                "teams": {
                    "home": {"id": str(home['team']['id']), "name": home_name, "logo": home['team'].get('logo', ''), "rank": home.get('curatedRank', {}).get('current', ''), "record": home.get('records', [{}])[0].get('summary', '') if home.get('records') else ''},
                    "away": {"id": str(away['team']['id']), "name": away_name, "logo": away['team'].get('logo', ''), "rank": away.get('curatedRank', {}).get('current', ''), "record": away.get('records', [{}])[0].get('summary', '') if away.get('records') else ''}
                },
                "goals": {"home": int(home.get('score', 0)), "away": int(away.get('score', 0))},
                "team_stats": summary["team_stats"], "homeLineup": summary["homeLineup"], "awayLineup": summary["awayLineup"],
                "events": summary["events"], "odds": summary["odds"], "injuries": summary["injuries"], "isFallback": summary["homeLineup"] is None
            })
        except Exception as e: print(f"❌ ERROR parsing match item {event.get('id', 'unknown')}: {e}")

    print(f"📊 Deep summary fetches completed for {date_str}: {summary_calls}/{len(raw_events)}")
    return matches

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#212529">
    <title>Futbol Starting Eleven | Live Soccer Starting Lineups, Scores, Injuries & Odds</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    
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

    <div class="text-center mt-2">
        <button id="toggle-all-cards" class="btn btn-sm btn-dark text-white shadow-sm px-3 py-1 me-2" style="font-size: 0.70rem; font-weight: 700; border-radius: 20px;">🔽 COMPACT SCOREBOARD</button>
        <button id="toggle-all-lineups" class="btn btn-sm btn-dark text-white shadow-sm px-3 py-1 d-none" style="font-size: 0.70rem; font-weight: 700; border-radius: 20px;">🔼 COLLAPSE ALL LINEUPS</button>
    </div>
</div>

<div class="container pb-5"><div id="games-container" class="row justify-content-center"></div></div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

<script>
    const STATIC_MATCHES = {{ matches_json | safe }};
    let ACTIVE_DAY = "today";
    let globalScoreboardMode = true;
    let globalLineupsExpanded = true;

    function shortenPlayerName(fullName) {
        if (!fullName) return "Unknown";
        const parts = fullName.split(' ');
        if (parts.length === 1) return fullName;
        return `${parts[0].charAt(0).toUpperCase()}. ${parts.slice(1).join(' ')}`;
    }

    function getContrastColor(hexColor) {
        if (!hexColor) return '#ffffff';
        hexColor = hexColor.replace('#', '');
        const r = parseInt(hexColor.substr(0, 2), 16), g = parseInt(hexColor.substr(2, 2), 16), b = parseInt(hexColor.substr(4, 2), 16);
        const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
        return (yiq >= 128) ? '#000000' : '#ffffff';
    }

    function colorDistance(hex1, hex2) {
        if (!hex1 || !hex2) return 100;
        const getRgb = (hex) => {
            let h = hex.replace('#', '');
            if (h.length === 3) h = h.split('').map(x => x + x).join('');
            return { r: parseInt(h.substr(0, 2), 16), g: parseInt(h.substr(2, 2), 16), b: parseInt(h.substr(4, 2), 16) };
        };
        const c1 = getRgb(hex1), c2 = getRgb(hex2);
        return Math.sqrt(Math.pow(c1.r - c2.r, 2) + Math.pow(c1.g - c2.g, 2) + Math.pow(c1.b - c2.b, 2));
    }

    function getTimeBadgeHtml(data) {
        const status = data.fixture.status.short;
        const dateObj = new Date(data.fixture.date);
        const timeString = dateObj.toLocaleTimeString([], {hour: 'numeric', minute:'2-digit'}).replace(' ', '');
        const matchTime = `${dateObj.toLocaleDateString([], {weekday: 'short'})} ${timeString}`;
        const isFinished = ['FT', 'AET', 'PEN'].includes(status);
        const isPreGame = ['NS', 'TBD'].includes(status);
        const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);

        if (isDelayed) return `<span class="badge bg-danger text-white border px-2 py-1" style="font-size: 0.75rem;">${status}</span>`;
        else if (isFinished) return `<span class="badge bg-dark text-white border px-2 py-1" style="font-size: 0.75rem;">FT</span>`;
        else if (!isPreGame) {
            let displayMin = data.fixture.status.elapsed || 'LIVE';
            if (status === 'HT') displayMin = 'HT';
            return `<span class="badge bg-success text-white border px-2 py-1" style="font-size: 0.75rem;"><span class="live-dot"></span>${displayMin}'</span>`;
        } else return `<span class="badge bg-white text-dark border px-1 py-1" style="font-size: 0.65rem; white-space: nowrap;">${matchTime}</span>`;
    }

    function getLatestEventHtml(data, isRibbon = false) {
        if (!data.events || data.events.length === 0) return isRibbon ? `<div class="text-muted text-start w-100 ps-2" style="font-size: 0.6rem; font-style: italic;">No Events</div>` : '';
        const lastEv = data.events[data.events.length - 1];
        const isHomeTeam = lastEv.team_id === data.teams.home.id;
        const teamName = isHomeTeam ? data.teams.home.name : data.teams.away.name;
        const teamLogo = isHomeTeam ? data.teams.home.logo : data.teams.away.logo;

        if (lastEv.type === 'subst') {
            let pOut = shortenPlayerName(lastEv.player), pIn = shortenPlayerName(lastEv.player_out);  
            if (isRibbon) {
                return `<div class="text-dark fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3;">
                            <div class="text-truncate">🔄 <img src="${teamLogo}" style="width: 12px; height: 12px;" class="me-1">${lastEv.time}'</div>
                            <div class="text-truncate">🟢 <span class="text-success">${pIn}</span></div>
                            <div class="text-muted text-truncate">🔴 ${pOut}</div>
                        </div>`;
            } else {
                return `<span class="ms-2 text-dark fw-bold text-truncate" style="font-size: 0.65rem;">🔄 ${lastEv.time}' <img src="${teamLogo}" style="width: 12px; height: 12px;" class="me-1"> 🟢 ${pIn} <span class="text-muted">🔴 ${pOut}</span></span>`;
            }
        } else {
            let icon = lastEv.type === 'Goal' ? '⚽' : '🟨';
            let playerName = shortenPlayerName(lastEv.player || teamName);
            let textColor = lastEv.type === 'Goal' ? 'text-success' : 'text-warning';
            if (isRibbon) {
                let assistHtml = (lastEv.type === 'Goal' && lastEv.assist) ? `<div class="text-muted text-truncate" style="font-size: 0.55rem;">👟 ${shortenPlayerName(lastEv.assist)}</div>` : '';
                return `<div class="${textColor} fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3;">
                            <div class="text-truncate"><img src="${teamLogo}" style="width: 12px; height: 12px;" class="me-1">${lastEv.time}'</div>
                            <div class="text-truncate">${icon} ${playerName}</div>${assistHtml}
                        </div>`;
            } else {
                return `<span class="ms-2 ${textColor} fw-bold text-truncate" style="font-size: 0.65rem;">${icon} ${lastEv.time}' <img src="${teamLogo}" style="width: 12px; height: 12px;" class="me-1">${playerName}</span>`;
            }
        }
    }

    function getRibbonHtml(data) {
        const home = data.teams.home, away = data.teams.away, status = data.fixture.status.short;
        const isPreGame = ['NS', 'TBD'].includes(status), isDelayed = ['PST', 'CANC', 'ABD'].includes(status);
        const homeScore = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals?.home ?? 0) : '-';
        const awayScore = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals?.away ?? 0) : '-';
        
        const flagHtml = data.league.flag 
            ? (data.league.flag.startsWith('http') 
                ? `<img src="${data.league.flag}" style="width: 20px; height: 20px; object-fit: contain; margin-right: 6px; vertical-align: middle; border-radius: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">`
                : `<span style="font-size: 1.1rem; margin-right: 6px; vertical-align: middle; line-height: 1;">${data.league.flag}</span>`)
            : `<span style="font-size: 0.85rem; margin-right: 6px; vertical-align: middle;">🏆</span>`;

        return `
        <div class="row g-0 align-items-center py-2" style="transition: background-color 0.2s;">
            <div class="col-3 text-center d-flex flex-column justify-content-center align-items-center border-end pe-1 ps-1">
                <div style="margin-bottom: 3px;">${getTimeBadgeHtml(data)}</div>
                <a href="/leagues/${data.league.slug}/" onclick="event.stopPropagation();" class="text-decoration-none text-muted fw-bold text-truncate w-100 px-1 d-inline-block" style="font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase;" title="${data.league.name}">
                    ${flagHtml}${data.league.abbrev}
                </a>
            </div>
            <div class="col-5 px-2">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 88%;"><img src="${home.logo}" width="14" height="14" class="me-1" style="object-fit:contain;">${home.name}</span>
                    <div class="text-end" style="min-width: fit-content; white-space: nowrap;"><span class="fw-bold text-dark" style="font-size: 0.85rem;">${homeScore}</span></div>
                </div>
                <div class="d-flex justify-content-between align-items-center">
                    <span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 88%;"><img src="${away.logo}" width="14" height="14" class="me-1" style="object-fit:contain;">${away.name}</span>
                    <div class="text-end" style="min-width: fit-content; white-space: nowrap;"><span class="fw-bold text-dark" style="font-size: 0.85rem;">${awayScore}</span></div>
                </div>
            </div>
            <div class="col-4 text-center border-start d-flex justify-content-center align-items-center">${getLatestEventHtml(data, true)}</div>
        </div>`;
    }

    function getCenterColumnHtml(data) {
        const status = data.fixture.status.short, isPreGame = ['NS', 'TBD'].includes(status), isDelayed = ['PST', 'CANC', 'ABD'].includes(status);
        const showScore = !isPreGame && !isDelayed && !data.isFallback;

        if (!showScore || !data.team_stats) return `<div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">${showScore ? `${data.goals?.home ?? 0} - ${data.goals?.away ?? 0}` : `vs`}</div>`;

        const tStats = data.team_stats;
        let hColor = data.homeLineup?.team?.colors?.player?.primary ? `#${data.homeLineup.team.colors.player.primary}` : '#0d6efd';
        let aColor = data.awayLineup?.team?.colors?.player?.primary ? `#${data.awayLineup.team.colors.player.primary}` : '#dc3545';
        if (colorDistance(hColor, aColor) < 60) aColor = '#343a40';

        const buildBar = (label, hVal, aVal, isPercentage = false) => {
            const total = hVal + aVal;
            let hPct = 50, aPct = 50;
            if (total > 0) { hPct = (hVal / total) * 100; aPct = (aVal / total) * 100; }
            return `<div class="text-center w-100 px-1"><div class="stat-label-tiny">${label}</div><div class="stat-bar-container"><div class="stat-bar-segment" style="width: ${hPct}%; background-color: ${hColor}; color: ${getContrastColor(hColor)};">${isPercentage ? `${hVal}%` : hVal}</div><div class="stat-bar-segment" style="width: ${aPct}%; background-color: ${aColor}; color: ${getContrastColor(aColor)};">${isPercentage ? `${aVal}%` : aVal}</div></div></div>`;
        };

        return `
            <div class="fw-bold text-dark mx-2 mb-1" style="font-size: 1.1rem; line-height: 1;">${data.goals?.home ?? 0} - ${data.goals?.away ?? 0}</div>
            ${buildBar("Possession", tStats.home?.possession ?? 0, tStats.away?.possession ?? 0, true)}
            ${buildBar("Total Shots", tStats.home?.total_shots ?? 0, tStats.away?.total_shots ?? 0)}
            ${buildBar("Shots on Target", tStats.home?.shots_on_target ?? 0, tStats.away?.shots_on_target ?? 0)}
            ${buildBar("Corners", tStats.home?.corners ?? 0, tStats.away?.corners ?? 0)}
            <div class="text-center w-100 px-1 mt-1"><div class="stat-label-tiny" style="margin-bottom: 0px;">Cards</div><div class="d-flex justify-content-between text-muted" style="font-size: 0.65rem; font-weight: 700;"><span>🟨 ${tStats.home?.yellow_cards ?? 0} 🟥 ${tStats.home?.red_cards ?? 0}</span><span>🟨 ${tStats.away?.yellow_cards ?? 0} 🟥 ${tStats.away?.red_cards ?? 0}</span></div></div>`;
    }

    function getEventsHtml(data) {
        if (!data.events || data.events.length === 0) return '';
        const homeEvents = data.events.filter(e => e.team_id === data.teams.home.id), awayEvents = data.events.filter(e => e.team_id === data.teams.away.id);

        const formatSingleEvent = (e, teamName) => {
            if (e.type === 'subst') return `<div class="d-flex align-items-start mb-1" style="line-height: 1.1;"><div class="text-secondary fw-bold pe-1" style="width: 25px; text-align: right; font-size: 0.6rem;">${e.time}'</div><div style="width: 16px; text-align: center;" class="me-1">🔄</div><div class="text-truncate"><span class="text-dark fw-bold">${shortenPlayerName(e.player_out)}</span> IN<br><span class="text-muted" style="font-size: 0.55rem;">(${shortenPlayerName(e.player)} OUT)</span></div></div>`;
            return `<div class="d-flex align-items-start mb-1" style="line-height: 1.1;"><div class="text-secondary fw-bold pe-1" style="width: 25px; text-align: right; font-size: 0.6rem;">${e.time}'</div><div style="width: 16px; text-align: center;" class="me-1">${e.type === 'Goal' ? '⚽' : '🟨'}</div><div class="text-truncate"><span class="text-dark fw-bold">${shortenPlayerName(e.player || teamName)}</span>${(e.type === 'Goal' && e.assist) ? `<br><span class="text-muted fw-normal" style="font-size: 0.55rem;">👟 ${shortenPlayerName(e.assist)}</span>` : ''}</div></div>`;
        };

        const homeReversed = [...homeEvents].reverse(), awayReversed = [...awayEvents].reverse();
        const needsCollapse = Math.max(homeReversed.length, awayReversed.length) > 1;

        return `<div class="w-100 px-2 pt-1 mt-1 border-top text-muted" style="font-size: 0.65rem; cursor: pointer; transition: background-color 0.2s;" onclick="if(${needsCollapse}) { const isExp = this.classList.toggle('is-expanded'); this.querySelector('.event-collapsed').classList.toggle('d-none', isExp); this.querySelector('.event-expanded').classList.toggle('d-none', !isExp); }" title="${needsCollapse ? 'Click to expand/collapse match timeline' : ''}"><div class="event-collapsed"><div class="d-flex justify-content-between"><div class="text-start" style="flex: 1; min-width: 0;">${homeReversed.length > 0 ? formatSingleEvent(homeReversed[0], data.teams.home.name) : ''}</div><div class="text-start" style="flex: 1; min-width: 0;">${awayReversed.length > 0 ? formatSingleEvent(awayReversed[0], data.teams.away.name) : ''}</div></div>${needsCollapse ? `<div class="text-center text-secondary w-100" style="font-size: 0.60rem;">▼</div>` : ''}</div><div class="event-expanded d-none"><div class="d-flex justify-content-between"><div class="text-start" style="flex: 1; min-width: 0;">${homeReversed.map(e => formatSingleEvent(e, data.teams.home.name)).join('')}</div><div class="text-start" style="flex: 1; min-width: 0;">${awayReversed.map(e => formatSingleEvent(e, data.teams.away.name)).join('')}</div></div><div class="text-center text-secondary w-100" style="font-size: 0.60rem;">▲</div></div></div>`;
    }

    function getOddsHtml(data) {
        if (!data.odds || (data.odds.home === "TBD" && data.odds.over === "TBD")) return '';
        return `<div class="d-flex justify-content-between text-center bg-white border-top border-bottom py-1" style="font-size: 0.70rem;"><div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">1 (HOME)</div><div class="fw-bold text-dark">${data.odds.home}</div></div><div class="w-25 border-start border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">X (DRAW)</div><div class="fw-bold text-dark">${data.odds.draw}</div></div><div class="w-25 border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">2 (AWAY)</div><div class="fw-bold text-dark">${data.odds.away}</div></div><div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">O/U ${data.odds.total}</div><div class="fw-bold text-dark"><span class="text-success">O</span> ${data.odds.over} <span class="text-danger">U</span> ${data.odds.under}</div></div></div>`;
    }

    function getInjuriesHtml(data) {
        const hInj = data.injuries?.home?.map(shortenPlayerName).join(', '), aInj = data.injuries?.away?.map(shortenPlayerName).join(', ');
        if (!hInj && !aInj) return '';
        return `<div class="border-bottom px-2 py-1 text-truncate" style="font-size: 0.65rem; background-color: #fff5f5; color: #dc3545;"><strong>🤕 OUT:</strong> <span class="text-dark"><b>H:</b> ${hInj || 'None'} | <b>A:</b> ${aInj || 'None'}</span></div>`;
    }

    function buildLiveStatsGrid(lineupData, teamColorHex) {
        if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) return `<div class="p-3 text-center text-muted small fw-bold">Awaiting live stats...</div>`;
        const groups = { 'F': { title: 'FWD', stats: ['G', 'A', 'SOT', 'SH'], keys: ['goals', 'assists', 'shots_on_target', 'total_shots'] }, 'M': { title: 'MID', stats: ['G', 'A', 'KP', 'TK'], keys: ['goals', 'assists', 'key_passes', 'tackles'] }, 'D': { title: 'DEF', stats: ['G', 'A', 'TK', 'IN'], keys: ['goals', 'assists', 'tackles', 'interceptions'] }, 'G': { title: 'GK',  stats: ['SV', 'GC', 'PA', 'YC'], keys: ['saves', 'conceded', 'passes', 'yellow_cards'] } };
        const groupedPlayers = { 'F': [], 'M': [], 'D': [], 'G': [] };
        
        let flatPlayers = [];
        lineupData.startXI.forEach(slot => flatPlayers.push({ ...slot.player }));
        if (lineupData.substitutes) lineupData.substitutes.forEach(sub => flatPlayers.push({ ...sub.player }));
        flatPlayers.forEach(p => groupedPlayers[p.pos || 'M'] ? groupedPlayers[p.pos || 'M'].push(p) : groupedPlayers['M'].push(p));

        let html = '', tColor = teamColorHex ? `#${teamColorHex.replace('#', '')}` : '#6c757d';
        ['F', 'M', 'D', 'G'].forEach(posKey => {
            const players = groupedPlayers[posKey];
            if (players.length === 0) return;
            const gConf = groups[posKey];
            html += `<div class="d-flex w-100 px-2 py-1 align-items-center bg-light border-bottom" style="font-size: 0.6rem; font-weight: 700;"><div style="flex: 1; color: ${tColor};">${gConf.title}</div><div style="width: 14px; text-align: center;">${gConf.stats[0]}</div><div style="width: 14px; text-align: center;">${gConf.stats[1]}</div><div style="width: 26px; text-align: center;">${gConf.stats[2]}</div><div style="width: 22px; text-align: center;">${gConf.stats[3]}</div></div>`;
            players.forEach(p => {
                let prefix = p.isSubbedIn ? `<span class="text-success fw-bold me-1">▲</span>` : (p.isSubbedOut ? `<span class="text-primary fw-bold me-1">↻</span>` : '');
                html += `<div class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="font-size: 0.70rem;"><div class="text-start text-truncate" style="flex: 1;">${prefix}${shortenPlayerName(p.name || 'Unknown')}</div><div class="text-muted" style="width: 14px; text-align: center; font-weight: 600;">${(p.live_stats || {})[gConf.keys[0]] || 0}</div><div class="text-muted" style="width: 14px; text-align: center; font-weight: 600;">${(p.live_stats || {})[gConf.keys[1]] || 0}</div><div class="text-muted" style="width: 26px; text-align: center; font-weight: 600;">${(p.live_stats || {})[gConf.keys[2]] || 0}</div><div class="text-muted" style="width: 22px; text-align: center; font-weight: 600;">${(p.live_stats || {})[gConf.keys[3]] || 0}</div></div>`;
            });
        });
        return html;
    }

    function buildLineupList(lineupData) {
        if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) return `<div class="p-3 text-center text-muted small fst-italic">Lineup pending...</div>`;
        const listItems = lineupData.startXI.map(slot => `<li class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="font-size: 0.8rem;"><span class="text-muted fw-bold me-2" style="font-size: 0.65rem; width: 12px;">${slot.player.pos || 'M'}</span>${slot.player.photo ? `<img src="${slot.player.photo}" style="width: 22px; height: 22px; border-radius: 50%; object-fit: cover;" class="me-2">` : `<div style="width:22px; height:22px; border-radius:50%; background:#e9ecef;" class="me-2 d-inline-block"></div>`}<span class="batter-name text-dark text-truncate">${slot.player.isSubbedOut ? `<span class="text-primary fw-bold me-1" title="Subbed Out">↻</span>` : ''}${shortenPlayerName(slot.player.name || 'Unknown')}</span><span class="ms-auto text-muted" style="font-size: 0.65rem;">#${slot.player.number || ''}</span></li>`).join('');
        return `<div class="w-100 text-center py-1 fw-bold text-white bg-success" style="font-size: 0.65rem;">✅ ${lineupData.formation || '4-3-3'}</div><ul class="batting-order w-100 m-0 p-0">${listItems}</ul>`;
    }

    function createGameCard(data) {
        const gameCard = document.createElement('div');
        gameCard.className = 'col-md-6 col-lg-6 col-xl-4 mb-3';
        const fixId = data.fixture.id, isPreGame = ['NS', 'TBD'].includes(data.fixture.status.short);
        
        const fullFlagHtml = data.league.flag 
            ? (data.league.flag.startsWith('http')
                ? `<img src="${data.league.flag}" style="width: 24px; height: 24px; object-fit: contain; margin-right: 6px; vertical-align: middle; border-radius: 3px; filter: drop-shadow(0 1px 1px rgba(0,0,0,0.1));">`
                : `<span style="font-size: 1.3rem; margin-right: 6px; vertical-align: middle; line-height: 1;">${data.league.flag}</span>`)
            : `<span style="font-size: 1rem; margin-right: 6px; vertical-align: middle;">🏆</span>`;

        gameCard.innerHTML = `
            <div class="lineup-card shadow-sm" id="card-${fixId}">
                <div class="ribbon-view ${globalScoreboardMode ? '' : 'd-none'}" id="ribbon-${fixId}" onclick="toggleSingleCard('${fixId}')">${getRibbonHtml(data)}</div>
                <div class="full-view ${globalScoreboardMode ? 'd-none' : ''}" id="full-${fixId}">
                    <div class="p-2 pb-1" style="background-color: #fcfcfc;">
                        <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom" style="cursor: pointer;" onclick="toggleSingleCard('${fixId}')">
                            <div class="pe-2 d-flex align-items-center flex-shrink-0" id="time-${fixId}" style="white-space: nowrap;">${getTimeBadgeHtml(data)} ${getLatestEventHtml(data)}</div>
                            <a href="/leagues/${data.league.slug}/" class="text-decoration-none text-muted fw-bold text-uppercase text-end ms-auto text-truncate d-flex align-items-center justify-content-end" style="font-size: 0.75rem; min-width: 0;" title="${data.league.name}">
                                ${fullFlagHtml} <span class="text-truncate">${data.league.name}</span>
                            </a>
                        </div>
                        <div class="d-flex justify-content-between align-items-center px-1 py-1 w-100">
                            <div class="text-center" style="width: 30%;"><img src="${data.teams.home.logo}" class="team-logo mb-1"><div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">${data.teams.home.name}</div></div>
                            <div class="text-center d-flex flex-column align-items-center justify-content-center" style="width: 40%;">${getCenterColumnHtml(data)}</div>
                            <div class="text-center" style="width: 30%;"><img src="${data.teams.away.logo}" class="team-logo mb-1"><div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">${data.teams.away.name}</div></div>
                        </div>
                        <div class="w-100">${getEventsHtml(data)}</div>
                    </div>
                    <div class="w-100">${getOddsHtml(data)}</div><div class="w-100">${getInjuriesHtml(data)}</div>
                    <div class="bg-light border-bottom d-flex justify-content-center align-items-center px-2 py-1">
                        <div class="d-flex gap-4 w-100">
                            <div class="lineup-tab ${(!data.team_stats || isPreGame) ? 'active' : ''}" id="tab-xi-${fixId}" onclick="switchLineupTab('${fixId}', 'xi')" style="flex: 1; text-align: center;">${isPreGame ? 'STARTING XI' : 'FINAL XI'}</div>
                            <div class="lineup-tab ${(data.team_stats && !isPreGame) ? 'active' : ''} ${!data.team_stats ? 'd-none' : ''}" id="tab-stats-${fixId}" onclick="switchLineupTab('${fixId}', 'stats')" style="flex: 1; text-align: center;">LIVE STATS</div>
                        </div>
                    </div>
                    <div class="collapse ${globalLineupsExpanded ? 'show' : ''} lineup-container" id="lineup-collapse-${fixId}">
                        <div id="view-xi-${fixId}" class="${(data.team_stats && !isPreGame) ? 'd-none' : ''}"><div class="row g-0 bg-white border-top"><div class="col-6 border-end">${buildLineupList(data.homeLineup)}</div><div class="col-6">${buildLineupList(data.awayLineup)}</div></div></div>
                        <div id="view-stats-${fixId}" class="${(!data.team_stats || isPreGame) ? 'd-none' : ''}"><div class="row g-0 bg-white border-top"><div class="col-6 border-end">${buildLiveStatsGrid(data.homeLineup, data.homeLineup?.team?.colors?.player?.primary)}</div><div class="col-6">${buildLiveStatsGrid(data.awayLineup, data.awayLineup?.team?.colors?.player?.primary)}</div></div></div>
                    </div>
                </div>
            </div>`;
        return gameCard;
    }

    window.toggleSingleCard = function(fixId) {
        document.getElementById(`ribbon-${fixId}`)?.classList.toggle('d-none');
        document.getElementById(`full-${fixId}`)?.classList.toggle('d-none');
    };

    window.switchLineupTab = function(fixId, tabName) {
        if (tabName === 'xi') {
            document.getElementById(`tab-xi-${fixId}`)?.classList.add('active'); document.getElementById(`tab-stats-${fixId}`)?.classList.remove('active');
            document.getElementById(`view-xi-${fixId}`)?.classList.remove('d-none'); document.getElementById(`view-stats-${fixId}`)?.classList.add('d-none');
        } else {
            document.getElementById(`tab-stats-${fixId}`)?.classList.add('active'); document.getElementById(`tab-xi-${fixId}`)?.classList.remove('active');
            document.getElementById(`view-stats-${fixId}`)?.classList.remove('d-none'); document.getElementById(`view-stats-${fixId}`)?.classList.add('d-none');
        }
    };

    function renderGames() {
        const container = document.getElementById('games-container');
        container.innerHTML = '';
        const searchText = (document.getElementById('team-search')?.value || '').toLowerCase();
        const filtered = (STATIC_MATCHES[ACTIVE_DAY] || []).filter(m => (m.teams.home.name + " " + m.teams.away.name + " " + m.league.name + " " + m.league.abbrev).toLowerCase().includes(searchText));

        if (filtered.length === 0) container.innerHTML = `<div class="col-12 text-center mt-5"><div class="card p-4 shadow-sm border-0"><div class="h4 text-muted">🏟️ No matches scheduled for this partition.</div><p class="text-muted">Select another day button above.</p></div></div>`;
        else filtered.forEach(item => container.appendChild(createGameCard(item)));
    }

    document.addEventListener('DOMContentLoaded', () => {
        renderGames();
        document.querySelectorAll('.day-tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.day-tab-btn').forEach(b => { b.classList.remove('btn-dark', 'active'); b.classList.add('btn-outline-dark'); });
                e.target.closest('.day-tab-btn').classList.remove('btn-outline-dark'); e.target.closest('.day-tab-btn').classList.add('btn-dark', 'active');
                ACTIVE_DAY = e.target.closest('.day-tab-btn').getAttribute('data-day');
                renderGames();
            });
        });

        document.getElementById('team-search')?.addEventListener('input', renderGames);
        document.getElementById('toggle-all-cards')?.addEventListener('click', (e) => {
            globalScoreboardMode = !globalScoreboardMode;
            e.target.innerHTML = globalScoreboardMode ? '🔼 EXPAND ALL CARDS' : '🔽 COMPACT SCOREBOARD';
            document.querySelectorAll('.ribbon-view').forEach(el => el.classList.toggle('d-none', !globalScoreboardMode));
            document.querySelectorAll('.full-view').forEach(el => el.classList.toggle('d-none', globalScoreboardMode));
            document.getElementById('toggle-all-lineups')?.classList.toggle('d-none', globalScoreboardMode);
        });
    });
</script>
</body>
</html>
"""

def generate_v2_index():
    print("\n==================================================")
    print("⏳ STARTING SSG BUILD PIPELINE")
    print("==================================================")
    day_info = get_3day_dates()
    
    matches_by_day = {
        "yesterday": fetch_espn_scores_for_date(day_info["dates"]["yesterday"]),
        "today": fetch_espn_scores_for_date(day_info["dates"]["today"]),
        "tomorrow": fetch_espn_scores_for_date(day_info["dates"]["tomorrow"])
    }
    
    print(f"\n==================================================")
    print(f"📊 SSG BUILD SUMMARY:")
    print(f"  ├─ Yesterday ({day_info['dates']['yesterday']}): {len(matches_by_day['yesterday'])} matches parsed")
    print(f"  ├─ Today     ({day_info['dates']['today']}):     {len(matches_by_day['today'])} matches parsed")
    print(f"  └─ Tomorrow  ({day_info['dates']['tomorrow']}):  {len(matches_by_day['tomorrow'])} matches parsed")
    print(f"==================================================")
    
    template = Template(HTML_TEMPLATE)
    output_html = template.render(
        matches_json=json.dumps(matches_by_day),
        display_dates=day_info["display"]
    )
    
    os.makedirs('v2', exist_ok=True)
    file_path = 'v2/index.html'
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(output_html)
    
    file_size_kb = round(os.path.getsize(file_path) / 1024, 2)
    print(f"\n🎉 Successfully compiled static frontend at {file_path} ({file_size_kb} KB)")

if __name__ == "__main__":
    generate_v2_index()

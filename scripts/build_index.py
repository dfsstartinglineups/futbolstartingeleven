import os
import time
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
from concurrent.futures import ThreadPoolExecutor, as_completed

CORE_LEAGUES_URL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues?limit=1000"

def safe_get(d, *keys):
    """Safely traverse nested dicts, guarding against missing keys and null/None values."""
    for key in keys:
        if isinstance(d, dict) and d.get(key) is not None:
            d = d.get(key)
        else:
            return None
    return d

def fetch_single_league_detail(ref_url):
    """Fetch individual core league detail payload from ESPN $ref URL."""
    try:
        res = requests.get(ref_url, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

def build_hydrated_core_index():
    """Builds parallel-hydrated master lookup for IDs, display names, and reverse slug-to-name mappings."""
    cache_file = 'data/core_index.json'
    
    # Check cache freshness (24 hours = 86400 seconds)
    if os.path.exists(cache_file):
        if time.time() - os.path.getmtime(cache_file) < 86400:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    print("⚡ Loaded Core Index from local disk cache.")
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Cache read failed ({e}), rebuilding index...")

    print("🔄 Hydrating Master Core API Directory (Parallel Threads)...")
    
    index = {
        "id_map": {},
        "name_map": {
            "club friendly": "club.friendly",
            "international friendly": "fifa.friendly",
            "friendly": "club.friendly",
            "men's international friendly": "fifa.friendly",
            "asean champ": "aff.championship",
            "asean championship": "aff.championship"
        },
        "slug_to_name": {
            "club.friendly": "Club Friendly",
            "fifa.friendly": "International Friendly",
            "aff.championship": "ASEAN Championship"
        }
    }
    
    try:
        master_res = requests.get(CORE_LEAGUES_URL, timeout=10).json()
        items = master_res.get('items', [])
        ref_urls = [item['$ref'] for item in items if '$ref' in item]
        
        with ThreadPoolExecutor(max_workers=25) as executor:
            future_to_url = {executor.submit(fetch_single_league_detail, url): url for url in ref_urls}
            for future in as_completed(future_to_url):
                data = future.result()
                if not data:
                    continue
                    
                league_id = str(data.get('id')) if data.get('id') else None
                slug = data.get('slug')
                name = data.get('name')
                short_name = data.get('shortName')
                abbrev = data.get('abbreviation')
                
                if slug:
                    # Save clean display name for slug
                    if name:
                        index["slug_to_name"][slug] = name
                    elif short_name:
                        index["slug_to_name"][slug] = short_name
                        
                    # Map numeric IDs
                    if league_id:
                        index["id_map"][league_id] = slug
                        
                    # Map string variations to slug
                    if name:
                        index["name_map"][name.lower().strip()] = slug
                    if short_name:
                        index["name_map"][short_name.lower().strip()] = slug
                    if abbrev:
                        index["name_map"][abbrev.lower().strip()] = slug

        print(f"✅ Core Index Hydrated! Mapped {len(index['id_map'])} League IDs & {len(index['name_map'])} Name Variations.\n")
        
        # Save the successful build to cache
        os.makedirs('data', exist_ok=True)
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(index, f, indent=2)
            
    except Exception as e:
        print(f"⚠️ Warning: Core API Index hydration failed ({e}). Pipeline will fallback to standard resolution.\n")
        
    return index

def resolve_event_league(event, core_index):
    """
    4-Tier League Resolver:
    Returns tuple: (league_pill, display_name)
    """
    if not core_index:
        return None, None

    comps = event.get('competitions', [])
    first_comp = comps[0] if comps else {}

    # Tier 1: Direct league.slug on event object
    t1_slug = safe_get(event, 'league', 'slug')
    if t1_slug:
        disp_name = core_index['slug_to_name'].get(t1_slug) or safe_get(event, 'league', 'name') or t1_slug.replace('.', ' ').title()
        return t1_slug, disp_name

    # Tier 2: Core API Lookup via numeric league.id
    league_id = safe_get(event, 'league', 'id') or safe_get(first_comp, 'league', 'id')
    if league_id and str(league_id) in core_index['id_map']:
        found_slug = core_index['id_map'][str(league_id)]
        disp_name = core_index['slug_to_name'].get(found_slug) or safe_get(event, 'league', 'name') or found_slug.replace('.', ' ').title()
        return found_slug, disp_name

    # Tier 3: Odds tracking tags metadata
    if comps:
        odds_list = first_comp.get('odds', [])
        if odds_list:
            first_odd = odds_list[0]
            tags = safe_get(first_odd, 'total', 'over', 'close', 'link', 'tracking', 'tags') or \
                   safe_get(first_odd, 'moneyline', 'home', 'close', 'link', 'tracking', 'tags')
            if isinstance(tags, dict) and tags.get('league'):
                found_slug = tags.get('league')
                disp_name = core_index['slug_to_name'].get(found_slug) or safe_get(first_comp, 'league', 'name') or found_slug.replace('.', ' ').title()
                return found_slug, disp_name

    # Tier 4: Normalized Name / altGameNote Matching against Core Directory
    candidates = []
    raw_strings = [
        safe_get(event, 'league', 'name'),
        safe_get(event, 'league', 'shortName'),
        safe_get(first_comp, 'league', 'name'),
        safe_get(first_comp, 'league', 'shortName'),
        first_comp.get('altGameNote')
    ]
    for s in raw_strings:
        if not s or not isinstance(s, str):
            continue
        s_clean = s.strip()
        candidates.append(s_clean.lower())
        for delimiter in [',', '-', '|', '–']:
            if delimiter in s_clean:
                base_part = s_clean.split(delimiter)[0].strip()
                if base_part:
                    candidates.append(base_part.lower())

    for cand in list(dict.fromkeys(candidates)):
        if cand in core_index['name_map']:
            found_slug = core_index['name_map'][cand]
            disp_name = core_index['slug_to_name'].get(found_slug) or cand.title()
            return found_slug, disp_name

    # Tier 4 Substring Fallback
    for cand in candidates:
        for name_key, found_slug in core_index['name_map'].items():
            if len(name_key) > 3 and name_key in cand:
                disp_name = core_index['slug_to_name'].get(found_slug) or name_key.title()
                return found_slug, disp_name

    return None, None

# Load Player Stats Cache
PLAYER_STATS_CACHE = {}
if os.path.exists('data/player_cache.json'):
    try:
        with open('data/player_cache.json', 'r', encoding='utf-8') as f:
            PLAYER_STATS_CACHE = json.load(f)
    except: pass

# Load API-Football headshots cache
HEADSHOTS_CACHE = {}
if os.path.exists('data/headshots.json'):
    try:
        with open('data/headshots.json', 'r') as f:
            HEADSHOTS_CACHE = json.load(f)
    except: pass

def get_player_headshot(pid, espn_fallback=""):
    if not pid: return espn_fallback
    if str(pid) in HEADSHOTS_CACHE:
        return HEADSHOTS_CACHE[str(pid)]
    return espn_fallback or f"https://a.espncdn.com/i/headshots/soccer/players/full/{pid}.png"

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
    "northern super league": "https://flagcdn.com/w40/ca.png",
    "canadian premier league": "https://flagcdn.com/w40/ca.png",
}

KNOWN_LEAGUE_PILLS = {
    "english premier league": "eng.1",
    "english league championship": "eng.2",
    "english league one": "eng.3",
    "english league two": "eng.4",
    "english fa cup": "eng.fa",
    "english carabao cup": "eng.league_cup",
    "spanish laliga": "esp.1",
    "spanish laliga 2": "esp.2",
    "spanish copa del rey": "esp.copa_del_rey",
    "italian serie a": "ita.1",
    "italian serie b": "ita.2",
    "coppa italia": "ita.coppa_italia",
    "german bundesliga": "ger.1",
    "german 2. bundesliga": "ger.2",
    "german cup": "ger.dfb_pokal",
    "french ligue 1": "fra.1",
    "french ligue 2": "fra.2",
    "coupe de france": "fra.coupe_de_france",
    "dutch eredivisie": "ned.1",
    "portuguese primeira liga": "por.1",
    "turkish super lig": "tur.1",
    "scottish premiership": "sco.1",
    "mls": "usa.1",
    "usl championship": "usa.usl.1",
    "nwsl": "usa.w.1",
    "liga mx": "mex.1",
    "liga bbva mx": "mex.1",
    "argentine liga profesional de fútbol": "arg.1",
    "brazilian serie a": "bra.1",
    "colombian primera a": "col.1",
    "chilean primera división": "chi.1",
    "saudi pro league": "sau.1",
    "australian a-league men": "aus.1",
    "japanese j.league": "jpn.1",
    "chinese super league": "chn.1",
    "uefa champions league": "uefa.champions",
    "uefa europa league": "uefa.europa",
    "uefa conference league": "uefa.europa.conf",
    "conmebol libertadores": "conmebol.libertadores",
    "conmebol sudamericana": "conmebol.sudamericana",
    "concacaf champions cup": "concacaf.champions",
}

COUNTRY_FLAG_URLS = {
    "belgian": "be", "chilean": "cl", "chinese": "cn", "dutch": "nl",
    "english": "gb-eng", "french": "fr", "german": "de", "bolivian": "bo",
    "norwegian": "no", "russian": "ru", "portuguese": "pt", "scottish": "gb-sct",
    "swedish": "se", "argentine": "ar", "brazilian": "br", "italian": "it",
    "mexican": "mx", "paraguayan": "py", "japanese": "jp", "spanish": "es",
    "danish": "dk", "indian": "in", "salvadoran": "sv", "costa rican": "cr",
    "peruvian": "pe", "peru": "pe",
    "uruguay": "uy", "uruguayan": "uy", "uruguaya": "uy",
    "canadian": "ca", "canada": "ca",
    "brazil": "br",
    "ecuador": "ec", "ecuadorian": "ec",
    "mexico": "mx", "mx": "mx",
    "guatemalan": "gt", "guatemala": "gt",
    "croatian": "hr", "croatia": "hr", "fpd": "hr",
    "honduran": "hn", "honduras": "hn",
    "venezuelan": "ve", "venezuela": "ve"
}

def normalize_text(text):
    if not text: return ""
    nfkd_form = unicodedata.normalize('NFD', text)
    return "".join([c for c in nfkd_form if unicodedata.category(c) != 'Mn']).lower().strip()

NORMALIZED_HUMAN_LEAGUE_FLAGS = {
    normalize_text(key): val for key, val in HUMAN_LEAGUE_FLAGS.items()
}

def get_local_image_url(url, subfolder="images/teams"):
    if not url or not url.startswith('http'):
        return url
    local_dir = subfolder
    os.makedirs(local_dir, exist_ok=True)
    ext = url.split('.')[-1].split('?')[0].lower()
    if ext not in ['png', 'jpg', 'jpeg', 'svg', 'webp']:
        ext = 'png'
    filename = f"{hashlib.md5(url.encode()).hexdigest()[:12]}.{ext}"
    local_file_path = os.path.join(local_dir, filename)
    web_path = f"/{subfolder}/{filename}"
    if not os.path.exists(local_file_path):
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                with open(local_file_path, 'wb') as f:
                    f.write(resp.content)
                return web_path
        except Exception:
            return url
    return web_path

# ====================================================================
# SLUG & STATE MANAGEMENT (SEO & ROUND-ROBIN)
# ====================================================================
def create_slug(name):
    if not name: return ""
    nfkd_form = unicodedata.normalize('NFKD', str(name))
    slug = nfkd_form.encode('ascii', 'ignore').decode('utf-8').lower()
    slug = re.sub(r'[\/]', '-', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')

def sync_league_state(all_active_matches):
    state_file = 'data/site_pages.json'
    os.makedirs('data', exist_ok=True)
    state = {}
    
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except: pass
        
    for name, flag_url in HUMAN_LEAGUE_FLAGS.items():
        slug = create_slug(name)
        pill_fallback = KNOWN_LEAGUE_PILLS.get(normalize_text(name), "")
        if slug not in state:
            state[slug] = {"name": name.title(), "pill": pill_fallback, "last_updated": 0.0, "flag": flag_url}
        elif not state[slug].get('pill') and pill_fallback:
            state[slug]['pill'] = pill_fallback

    for m in all_active_matches:
        l_info = m.get('league', {})
        slug = l_info.get('slug')
        pill = l_info.get('pill', '')
        flag = l_info.get('flag', '')
        
        if slug:
            if slug not in state:
                state[slug] = {"name": l_info.get('name', slug), "pill": pill, "last_updated": 0.0, "flag": flag}
            elif pill:
                state[slug]['pill'] = pill
            
    return state, state_file

def sync_team_state(matches):
    state_file = 'data/site_teams.json'
    os.makedirs('data', exist_ok=True)
    team_state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                team_state = json.load(f)
        except: pass

    for m in matches:
        for t_side in ['home', 'away']:
            team_info = m['teams'].get(t_side, {})
            team_id = str(team_info.get('id', ''))
            team_name = team_info.get('name', '')
            if team_id and team_name:
                slug = create_slug(team_name)
                if slug not in team_state:
                    team_state[slug] = {
                        "id": team_id,
                        "name": team_name,
                        "slug": slug,
                        "logo": team_info.get('logo', ''),
                        "last_match_id": "",
                        "last_updated": 0.0,
                        "is_final": False,
                        "squad_synced": False
                    }
    return team_state, state_file

def sync_player_state(matches):
    state_file = 'data/site_players.json'
    os.makedirs('data', exist_ok=True)
    player_state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                player_state = json.load(f)
        except: pass

    for m in matches:
        for side in ['home', 'away']:
            lineup = m.get(side + 'Lineup')
            if not lineup: continue
            team_info = m['teams'][side]
            
            players = []
            if lineup.get('startXI'): players.extend(lineup['startXI'])
            if lineup.get('substitutes'): players.extend(lineup['substitutes'])
            
            for s_obj in players:
                p = s_obj.get('player', {})
                pid = str(p.get('id', ''))
                pname = p.get('name', '')
                if pid and pname:
                    slug = f"{create_slug(pname)}-{pid}"
                    if slug not in player_state:
                        player_state[slug] = {
                            "id": pid,
                            "name": pname,
                            "slug": slug,
                            "team_name": team_info.get('name', ''),
                            "team_slug": create_slug(team_info.get('name', '')),
                            "position": p.get('pos', 'M'),
                            "photo": p.get('photo', ''),
                            "last_match_id": "",
                            "last_updated": 0.0,
                            "is_final": False
                        }
    return player_state, state_file

def get_league_pill_for_team(team_id):
    """Fetches a team's official league pill directly from ESPN's Core API."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        url = f"https://sports.core.api.espn.com/v2/sports/soccer/teams/{team_id}"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            ref = res.json().get("defaultLeague", {}).get("$ref", "")
            if "/leagues/" in ref:
                return ref.split("/leagues/")[1].split("?")[0]
    except Exception:
        pass
    return None

def sync_team_squads(matches, team_state, player_state, upcoming_pool, nav_html, day_info, league_state=None, max_rosters=5):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    rosters_fetched = 0
    
    for m in matches:
        if rosters_fetched >= max_rosters:
            break

        l_info = m.get('league') or {}
        l_slug = l_info.get('slug', '')
        fallback_pill = l_info.get('pill', '')
        
        if not fallback_pill and league_state and l_slug in league_state:
            fallback_pill = league_state[l_slug].get('pill', '')
            
        if not fallback_pill and l_info.get('name'):
            fallback_pill = KNOWN_LEAGUE_PILLS.get(normalize_text(l_info.get('name')), '')

        for side in ['home', 'away']:
            if rosters_fetched >= max_rosters:
                break

            t_info = (m.get('teams') or {}).get(side) or {}
            t_id = str(t_info.get('id', ''))
            t_name = t_info.get('name', '')
            if not t_id or not t_name:
                continue
                
            t_slug = create_slug(t_name)
            if t_slug in team_state and team_state[t_slug].get('squad_synced'):
                continue

            # Use cached pill from team_state if available, otherwise fetch once
            team_pill = team_state.get(t_slug, {}).get('league_pill')
            if not team_pill:
                team_pill = get_league_pill_for_team(t_id) or fallback_pill
                if t_slug in team_state:
                    team_state[t_slug]['league_pill'] = team_pill

            if not team_pill or team_pill == 'global':
                team_pill = 'global'
                
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{team_pill}/teams/{t_id}/roster"
            try:
                r = requests.get(url, headers=headers, timeout=5)
                if r.status_code == 200:
                    data = r.json()
                    athletes_groups = data.get('athletes', [])
                    new_players_count = 0
                    
                    for group in athletes_groups:
                        items = group.get('items', []) if isinstance(group, dict) and 'items' in group else [group]
                        for p in items:
                            if not isinstance(p, dict): continue
                            pid = str(p.get('id', ''))
                            pname = p.get('displayName') or p.get('fullName') or p.get('name', '')
                            if not pid or not pname: continue
                            
                            p_slug = f"{create_slug(pname)}-{pid}"
                            pos_obj = p.get('position') or {}
                            raw_pos = pos_obj.get('abbreviation') or pos_obj.get('name') or 'M'
                            
                            headshot = p.get('headshot') or {}
                            raw_espn_url = headshot.get('href', '') if isinstance(headshot, dict) else str(headshot)
                            photo_url = get_player_headshot(pid, raw_espn_url)
                                
                            is_new = p_slug not in player_state
                            if is_new:
                                player_state[p_slug] = {
                                    "id": pid,
                                    "name": pname,
                                    "slug": p_slug,
                                    "team_name": t_name,
                                    "team_slug": t_slug,
                                    "position": raw_pos.upper(),
                                    "photo": photo_url,
                                    "jersey": str(p.get('jersey', '')),
                                    "last_match_id": "",
                                    "last_updated": 0.0,
                                    "is_final": False
                                }
                                new_players_count += 1
                            else:
                                if photo_url and not player_state[p_slug].get('photo'):
                                    player_state[p_slug]['photo'] = photo_url
                                if not player_state[p_slug].get('team_name'):
                                    player_state[p_slug]['team_name'] = t_name
                                    player_state[p_slug]['team_slug'] = t_slug
                            
                            p_page_path = os.path.join('players', p_slug, 'index.html')
                            if is_new or not os.path.exists(p_page_path):
                                next_m, next_is_home = find_next_fixture_for_entity(t_slug, upcoming_pool)
                                dummy_match = next_m if next_m else {
                                    "fixture": {"status": {"short": "FT"}},
                                    "teams": {"home": {"name": t_name}, "away": {"name": "Opponent"}},
                                    "goals": {"home": 0, "away": 0}
                                }
                                build_single_player_page(
                                    p_slug, player_state[p_slug], dummy_match,
                                    is_home=next_is_home,
                                    nav_html=nav_html,
                                    today_date_str=day_info["display"]["today"],
                                    next_match_tuple=(next_m, next_is_home) if next_m else None
                                )

                    if t_slug in team_state:
                        team_state[t_slug]['squad_synced'] = True
                    rosters_fetched += 1
                    print(f"  └─ Squad auto-discovery ({rosters_fetched}/{max_rosters}) for {t_name} via '{team_pill}': registered {new_players_count} players.")
            except Exception as e:
                print(f"  └─ ⚠️ Failed to fetch squad for {t_name} ({t_id}) via pill '{team_pill}': {e}")
                
def generate_nav_leagues_html(state):
    sorted_leagues = sorted(state.items(), key=lambda x: x[1]['name'].lower())
    html = ""
    for slug, data in sorted_leagues:
        html += f'<li><a class="dropdown-item" href="/leagues/{slug}/" style="font-size: 0.85rem; font-weight: 500;">{data["name"]}</a></li>'
    return html

def find_next_fixture_for_entity(team_id_or_slug, upcoming_matches):
    target = str(team_id_or_slug).lower()
    for m in upcoming_matches:
        h_id = str(m['teams']['home'].get('id', '')).lower()
        a_id = str(m['teams']['away'].get('id', '')).lower()
        h_slug = create_slug(m['teams']['home'].get('name', '')).lower()
        a_slug = create_slug(m['teams']['away'].get('name', '')).lower()
        
        if target in [h_id, a_id, h_slug, a_slug]:
            is_home = (target in [h_id, h_slug])
            return m, is_home
    return None, False

# ====================================================================
# ASYNC CORE API PLAYER STATS FETCHER
# ====================================================================
async def fetch_single_player_core_stats(session, internal_slug, event_id, team_id, player_id, sem):
    url = f"https://sports.core.api.espn.com/v2/sports/soccer/leagues/{internal_slug}/events/{event_id}/competitions/{event_id}/competitors/{team_id}/roster/{player_id}/statistics/0"
    async with sem:
        try:
            async with session.get(url, timeout=4) as resp:
                if resp.status == 200:
                    data = await resp.json()
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
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    sem = asyncio.Semaphore(8)  # Cap concurrent requests per match to 8
    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = [
            fetch_single_player_core_stats(session, internal_slug, event_id, tid, pid, sem) 
            for tid, pid in player_list
        ]
        results = await asyncio.gather(*tasks)
        return {pid: stats for pid, stats in results if stats}

# ====================================================================
# ESPN COMMON V3 ATHLETE OVERVIEW & GAMELOG FETCHER
# ====================================================================
def fetch_athlete_overview_and_gamelog(player_id, position='M'):
    default_headers_comp = {"col2": "Gls", "col3": "Ast", "col4": "Shots (SOG)"}
    default_headers_log = {"col1": "App", "col2": "Gls", "col3": "Ast", "col4": "Shots"}
    default_return = {
        "overview_totals": {"matches": "-", "goals": "0", "assists": "0", "shots": "0", "label1": "Matches", "label2": "Goals", "label3": "Assists", "label4": "Shots"},
        "competition_splits": [],
        "gamelogs": [],
        "comp_headers": default_headers_comp,
        "log_headers": default_headers_log,
        "headshot": ""
    }
    if not player_id:
        return default_return

    now_ts = time.time()
    # Check memory cache (6 hours = 21600 seconds)
    if player_id in PLAYER_STATS_CACHE:
        cached_entry = PLAYER_STATS_CACHE[player_id]
        if now_ts - cached_entry.get('fetched_at', 0) < 21600:
            return cached_entry.get('data', default_return)

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    overview_url = f"https://site.web.api.espn.com/apis/common/v3/sports/soccer/athletes/{player_id}/overview"

    comp_splits = []
    tot_apps, tot_val2, tot_val3, tot_val4 = 0, 0, 0, 0
    has_overview_data = False
    fetched_headshot = ""

    try:
        r_ov = requests.get(overview_url, headers=headers, timeout=5)
        if r_ov.status_code == 200:
            ov_data = r_ov.json()
            
            ath_obj = ov_data.get('athlete') or {}
            hs_obj = ath_obj.get('headshot') or {}
            raw_espn_photo = ""
            if isinstance(hs_obj, dict):
                raw_espn_photo = hs_obj.get('href', '')
            elif isinstance(hs_obj, str):
                raw_espn_photo = hs_obj
            fetched_headshot = get_player_headshot(player_id, raw_espn_photo)

            stats_obj = ov_data.get('statistics') or {}
            labels = stats_obj.get('labels') or []
            splits = stats_obj.get('splits') or []

            is_gk = (str(position).upper() in ['G', 'GK', 'GOALKEEPER']) or any(l in labels for l in ['SV', 'SAVES', 'GA', 'CS'])

            for s in splits:
                comp_name = s.get('displayName') or s.get('teamSlug') or (s.get('competition') or {}).get('displayName') or 'Competition'
                raw_stats = s.get('stats') or []
                s_dict = {}
                if raw_stats and isinstance(raw_stats[0], dict):
                    for st in raw_stats:
                        s_name = st.get('name') or st.get('abbreviation') or st.get('label')
                        val = st.get('displayValue', st.get('value', '0'))
                        if s_name: s_dict[s_name] = str(val)
                else:
                    s_dict = dict(zip(labels, [str(v) for v in raw_stats]))

                def get_stat(keys, default='0'):
                    for k in keys:
                        if k in s_dict: return str(s_dict[k])
                    return default

                strt = get_stat(['STRT', 'starts', 'gamesStarted'])
                app = get_stat(['APP', 'appearances', 'gamesPlayed'], strt)
                of = get_stat(['OF', 'offsides'])
                fc = get_stat(['FC', 'foulsCommitted'])
                fa = get_stat(['FA', 'foulsSuffered'])
                yc = get_stat(['YC', 'yellowCards'])
                rc = get_stat(['RC', 'redCards'])

                try: tot_apps += int(app)
                except: pass

                if is_gk:
                    sv = get_stat(['SV', 'saves'])
                    ga = get_stat(['GA', 'goalsConceded', 'conceded'])
                    shf = get_stat(['SHOT', 'shotsFaced', 'shotsOnGoalAgainst', 'SOG'])
                    cs = get_stat(['CS', 'cleanSheets'])

                    try: tot_val2 += int(sv)
                    except: pass
                    try: tot_val3 += int(ga)
                    except: pass
                    try: tot_val4 += int(cs)
                    except: pass

                    comp_splits.append({
                        "competition": comp_name,
                        "strt": strt,
                        "goals": sv,
                        "assists": ga,
                        "shots_sog": shf,
                        "fouls": f"{fc}/{fa}",
                        "offsides": of,
                        "cards": f"{yc}/{rc}"
                    })
                else:
                    gls = get_stat(['G', 'totalGoals', 'goals'])
                    ast = get_stat(['A', 'goalAssists', 'assists'])
                    shot = get_stat(['SHOT', 'totalShots', 'shots'])
                    sog = get_stat(['SOG', 'shotsOnTarget'])

                    try: tot_val2 += int(gls)
                    except: pass
                    try: tot_val3 += int(ast)
                    except: pass
                    try: tot_val4 += int(shot)
                    except: pass

                    comp_splits.append({
                        "competition": comp_name,
                        "strt": strt,
                        "goals": gls,
                        "assists": ast,
                        "shots_sog": f"{shot} ({sog})",
                        "fouls": f"{fc}/{fa}",
                        "offsides": of,
                        "cards": f"{yc}/{rc}"
                    })
                has_overview_data = True

            gamelogs = []
            gamelog_data = ov_data.get('gameLog') or {}
            events_map = gamelog_data.get('events') or {}
            stats_list = gamelog_data.get('statistics') or []

            gl_labels = []
            entries = []

            if stats_list and isinstance(stats_list, list) and len(stats_list) > 0:
                stat_group = stats_list[0]
                gl_labels = stat_group.get('labels') or []
                stat_entries = stat_group.get('events') or []
                if isinstance(stat_entries, list):
                    entries = stat_entries
                elif isinstance(stat_entries, dict):
                    entries = list(stat_entries.values())

            def format_app_status(val):
                if not val or val == '-': return '-'
                s = str(val).strip()
                s_lower = s.lower()
                if 'started' in s_lower: return 'STRT'
                if 'sub' in s_lower: return 'SUB'
                if 'unused' in s_lower: return 'BENCH'
                return s[:6]

            for entry in entries:
                ev_id = str(entry.get('eventId') or entry.get('id', ''))
                ev_info = events_map.get(ev_id) or {}

                date_str = ev_info.get('gameDate') or ev_info.get('date', '')
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    formatted_date = dt.strftime('%b %d')
                except:
                    formatted_date = date_str[:10] if date_str else '-'

                opp_obj = ev_info.get('opponent') or {}
                opp_name = opp_obj.get('displayName') or opp_obj.get('name') or 'Opponent'
                opp_logo = opp_obj.get('logo') or ''

                game_result = ev_info.get('gameResult', '')
                score_str = ev_info.get('score', '')
                result_display = f"{game_result} {score_str}".strip() if game_result else score_str

                raw_stats = entry.get('stats') or []
                stats_dict = {}
                if isinstance(raw_stats, list):
                    stats_dict = dict(zip(gl_labels, [str(v) for v in raw_stats]))
                elif isinstance(raw_stats, dict):
                    stats_dict = {k: str(v) for k, v in raw_stats.items()}

                app_val = stats_dict.get('APP') or stats_dict.get('MIN') or stats_dict.get('minutes') or '-'
                formatted_app = format_app_status(app_val)

                yc_val = stats_dict.get('YC') or stats_dict.get('yellowCards') or '0'
                rc_val = stats_dict.get('RC') or stats_dict.get('redCards') or '0'

                if is_gk:
                    sv_val = stats_dict.get('SV') or stats_dict.get('saves') or '0'
                    ga_val = stats_dict.get('GA') or stats_dict.get('goalsConceded') or '0'
                    shf_val = stats_dict.get('SHOT') or stats_dict.get('shotsFaced') or stats_dict.get('SOG') or '0'

                    gamelogs.append({
                        "date": formatted_date,
                        "opponent": opp_name,
                        "opp_logo": opp_logo,
                        "result": result_display,
                        "minutes": formatted_app,
                        "goals": sv_val,
                        "assists": ga_val,
                        "shots": shf_val,
                        "cards": f"{yc_val}/{rc_val}"
                    })
                else:
                    gls_val = stats_dict.get('G') or stats_dict.get('goals') or '0'
                    ast_val = stats_dict.get('A') or stats_dict.get('assists') or '0'
                    shot_val = stats_dict.get('SHOT') or stats_dict.get('shots') or '0'

                    gamelogs.append({
                        "date": formatted_date,
                        "opponent": opp_name,
                        "opp_logo": opp_logo,
                        "result": result_display,
                        "minutes": formatted_app,
                        "goals": gls_val,
                        "assists": ast_val,
                        "shots": shot_val,
                        "cards": f"{yc_val}/{rc_val}"
                    })

            comp_headers = {
                "col2": "Saves" if is_gk else "Gls",
                "col3": "GA" if is_gk else "Ast",
                "col4": "Shots Faced" if is_gk else "Shots (SOG)"
            }
            log_headers = {
                "col1": "App",
                "col2": "Saves" if is_gk else "Gls",
                "col3": "GA" if is_gk else "Ast",
                "col4": "Shots Faced" if is_gk else "Shots"
            }

            overview_totals = {
                "matches": str(tot_apps) if has_overview_data else "-",
                "goals": str(tot_val2) if has_overview_data else "0",
                "assists": str(tot_val3) if has_overview_data else "0",
                "shots": str(tot_val4) if has_overview_data else "0",
                "label1": "Matches",
                "label2": "Saves" if is_gk else "Goals",
                "label3": "Goals Conceded" if is_gk else "Assists",
                "label4": "Clean Sheets" if is_gk else "Shots"
            }

            result = {
                "overview_totals": overview_totals,
                "competition_splits": comp_splits,
                "gamelogs": gamelogs[:20],
                "comp_headers": comp_headers,
                "log_headers": log_headers,
                "headshot": fetched_headshot
            }
            
            # Save to memory cache
            PLAYER_STATS_CACHE[player_id] = {
                'fetched_at': now_ts,
                'data': result
            }
            return result
    except Exception as e:
        pass

    return default_return

# ====================================================================
# HELPER UTILITIES & GROUPING
# ====================================================================
def get_position_category(raw_pos):
    if not raw_pos: return 'M'
    p = str(raw_pos).strip().upper()
    if p in ['G', 'GK', 'GOALKEEPER']: return 'G'
    if any(term in p for term in ['CF', 'ST', 'FW', 'LW', 'RW', 'WF', 'SS', 'ATT', 'STR', 'AM', 'CAM']) or p == 'F': return 'F'
    if any(term in p for term in ['CD', 'CB', 'LB', 'RB', 'WB', 'SW', 'DF', 'DEF']) or p == 'D': return 'D'
    return 'M'

def get_formation(lineup_data):
    if lineup_data and lineup_data.get('formation'):
        return str(lineup_data['formation'])
    if lineup_data and lineup_data.get('startXI'):
        d = m = f = 0
        for s in lineup_data['startXI']:
            cat = s.get('player', {}).get('category', 'M')
            if cat == 'D': d += 1
            elif cat == 'M': m += 1
            elif cat == 'F': f += 1
        if d + m + f > 0:
            return f"{d}-{m}-{f}"
    return "4-4-2"

def is_valid_sub_minute(minute_val):
    if not minute_val: return False
    cleaned = re.sub(r'[^0-9]', '', str(minute_val))
    return int(cleaned) > 0 if cleaned else False

def extract_match_clock(status_obj):
    if not status_obj: return "LIVE"
    status_type = status_obj.get('type') or {}
    state = status_type.get('state', 'pre')
    if state == 'pre': return "NS"
    if state == 'post': return "FT"
    if status_type.get('name') == 'STATUS_HALFTIME' or status_type.get('shortDetail') == 'HT': return "HT"

    detail = status_type.get('detail', '')
    short_detail = status_type.get('shortDetail', '')
    
    # First, check both detail and shortDetail for the stoppage time pattern (e.g. "90+8" or "90 + 8")
    for string_to_check in [detail, short_detail]:
        if string_to_check:
            stoppage_match = re.search(r"(\d+\s*\+\s*\d+)", string_to_check)
            if stoppage_match:
                return stoppage_match.group(1).replace(" ", "")

    # If no stoppage time, check for standard tick marks (e.g. "82'")
    if short_detail:
        tick_match = re.search(r"(\d+)\'", short_detail)
        if tick_match: 
            return tick_match.group(1)
        
        # Fallback for a standalone number
        nums = re.findall(r"\d+", short_detail)
        if len(nums) == 1 and "Half" not in short_detail: 
            return nums[0]

    display_clock = status_obj.get('displayClock', '')
    if display_clock:
        if ':' in str(display_clock):
            try:
                mins, secs = map(int, display_clock.split(':'))
                total_mins = mins + (1 if secs > 0 else 0)
                return str(total_mins)
            except: pass
        return str(display_clock).replace("'", "")

    raw_clock = status_obj.get('clock') if status_obj.get('clock') is not None else 0
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
    status_obj = event.get('status') or {}
    status_type = status_obj.get('type') or {}
    state = status_type.get('state', 'pre')
    if state in ['in', 'post']: return True, f"State is '{state}'"
    if state == 'pre':
        event_date_str = event.get('date')
        if event_date_str:
            try:
                event_dt = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
                now_utc = datetime.now(pytz.utc)
                minutes_until_kickoff = (event_dt - now_utc).total_seconds() / 60.0
                if minutes_until_kickoff <= 90: return True, f"Pre-game, starting in {int(minutes_until_kickoff)} mins"
                return False, f"Pre-game (>90m)"
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
        header = data.get('header') or {}
        comp_list = header.get('competitions') or [{}]
        comp_head = comp_list[0] if comp_list else {}
        
        summary_data["status_obj"] = comp_head.get('status') or {}
        game_state = ((comp_head.get('status') or {}).get('type') or {}).get('state', 'pre')

        internal_slug = (header.get('league') or {}).get('slug', '')

        live_scores = {}
        for comp in comp_head.get('competitors', []):
            if comp.get('homeAway') in ['home', 'away'] and comp.get('score') is not None:
                try: live_scores[comp.get('homeAway')] = int(comp.get('score'))
                except: pass
        if live_scores: summary_data["live_score"] = live_scores

        teams_box = (data.get('boxscore') or {}).get('teams') or []
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
                ev_text = (ev.get('type') or {}).get('text', '').lower()
                if "substitution" in ev_text or "sub" in ev_text:
                    parts = ev.get('participants', [])
                    if len(parts) >= 2:
                        p_in = (parts[0].get('athlete') or {}).get('displayName', '').lower()
                        p_out = (parts[1].get('athlete') or {}).get('displayName', '').lower()
                        if p_in and p_out: sub_to_starter[p_in] = p_out
                        subbed_in.add(p_in); subbed_in.add(str((parts[0].get('athlete') or {}).get('id', '')))
                        subbed_out.add(p_out); subbed_out.add(str((parts[1].get('athlete') or {}).get('id', '')))

        rosters = data.get('rosters', [])
        if isinstance(rosters, list) and len(rosters) >= 2:
            
            core_stats_cache = {}
            if game_state != 'pre' and internal_slug:
                active_player_list = []
                for r_data in rosters:
                    t_id = str((r_data.get('team') or {}).get('id', ''))
                    for entry in r_data.get('roster', []):
                        ath = entry.get('athlete') or {}
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
                team_obj = r_data.get('team') or {}
                start_xi, subs = [], []
                starters_look = {}
                
                for entry in r_data.get('roster', []):
                    if not entry.get('starter', False): continue
                    ath = entry.get('athlete') or {}
                    p_id = str(ath.get('id', ''))
                    p_name = ath.get('displayName', 'Unknown')
                    pos = (entry.get('position') or {}).get('abbreviation') or (ath.get('position') or {}).get('abbreviation') or 'M'
                    
                    sub_in_flag = entry.get('subbedIn', False)
                    sub_in = sub_in_flag or (game_state != 'pre' and (p_id in subbed_in or p_name.lower() in subbed_in or is_valid_sub_minute(entry.get('subbedInMinute'))))
                    sub_out = game_state != 'pre' and (p_id in subbed_out or p_name.lower() in subbed_out or is_valid_sub_minute(entry.get('subbedOutMinute')))
                    
                    p_stats = extract_player_live_stats(core_stats_cache.get(p_id))
                    
                    raw_photo = (ath.get('headshot') or {}).get('href', '') if isinstance(ath.get('headshot'), dict) else ''
                    p_obj = {
                        "id": p_id, "name": p_name, "pos": pos.upper(), "category": get_position_category(pos),
                        "number": str(entry.get('jersey', '')), "photo": get_player_headshot(p_id, raw_photo),
                        "live_stats": p_stats,
                        "isSubbedIn": sub_in, "isSubbedOut": sub_out, "subMinute": str(entry.get('subbedInMinute') or entry.get('subbedOutMinute') or '')
                    }
                    start_xi.append({"player": p_obj})
                    starters_look[p_name.lower()] = p_obj

                for entry in r_data.get('roster', []):
                    if entry.get('starter', False): continue
                    ath = entry.get('athlete') or {}
                    p_id = str(ath.get('id', ''))
                    p_name = ath.get('displayName', 'Unknown')
                    pos = (ath.get('position') or {}).get('abbreviation') or (entry.get('position') or {}).get('abbreviation') or 'M'
                    if pos.upper() in ['SUB', 'S', 'SUBSTITUTE', '']:
                        replaced = sub_to_starter.get(p_name.lower())
                        pos_cat = starters_look[replaced]['category'] if replaced in starters_look else 'M'
                    else: pos_cat = get_position_category(pos)
                    
                    sub_in_flag = entry.get('subbedIn', False)
                    sub_in = sub_in_flag or (game_state != 'pre' and (p_id in subbed_in or p_name.lower() in subbed_in or is_valid_sub_minute(entry.get('subbedInMinute'))))
                    sub_out = game_state != 'pre' and (p_id in subbed_out or p_name.lower() in subbed_out or is_valid_sub_minute(entry.get('subbedOutMinute')))
                    
                    p_stats = extract_player_live_stats(core_stats_cache.get(p_id))
                    
                    if entry.get('didPlay') or entry.get('played') or sub_in or p_stats:
                        raw_sub_photo = (ath.get('headshot') or {}).get('href', '') if isinstance(ath.get('headshot'), dict) else ''
                        subs.append({"player": {
                            "id": p_id, "name": p_name, "pos": pos.upper(), "category": pos_cat,
                            "number": str(entry.get('jersey', '')), "photo": get_player_headshot(p_id, raw_sub_photo),
                            "live_stats": p_stats, "isSubbedIn": sub_in, "isSubbedOut": sub_out, "subMinute": str(entry.get('subbedInMinute') or entry.get('subbedOutMinute') or '')
                        }})
                
                if start_xi: summary_data["homeLineup" if ha == 'home' else "awayLineup"] = {"formation": r_data.get('formation', '4-3-3'), "team": {"colors": {"player": {"primary": team_obj.get('color', '0d6efd')}}}, "startXI": start_xi, "substitutes": subs}

        if isinstance(key_events, list) and key_events:
            for ev in key_events:
                ev_text = (ev.get('type') or {}).get('text', '').lower()
                is_goal = "goal" in ev_text or "penalty - scored" in ev_text
                is_sub = "substitution" in ev_text or "sub" in ev_text
                is_card = "card" in ev_text
                if not (is_goal or is_sub or is_card): continue
                
                ev_type = "Goal" if is_goal else ("subst" if is_sub else ("Red Card" if "red" in ev_text else "Yellow Card"))
                parts = ev.get('participants', [])
                p_in = (parts[0].get('athlete') or {}).get('displayName', '') if parts else ''
                if not p_in and parts: p_in = (parts[0].get('coach') or {}).get('displayName', '')
                p_out = (parts[1].get('athlete') or {}).get('displayName', '') if len(parts) > 1 else ''
                
                p_player = p_out if ev_type == "subst" else p_in
                if not p_player:
                    raw_text = ev.get('shortText') or ev.get('text') or ''
                    p_player = raw_text.split(" - ")[-1].strip() if " - " in raw_text else (raw_text[:20]+'...' if len(raw_text)>20 else raw_text)
                
                summary_data["events"].append({
                    "time": (ev.get('clock') or {}).get('displayValue', "0'").replace("'", ""), "team_id": str((ev.get('team') or {}).get('id', '')),
                    "type": ev_type, "detail": (ev.get('type') or {}).get('text', ''), "player": p_player,
                    "player_out": p_in if ev_type == "subst" else (p_out if p_out else None), "assist": p_out if ev_type == "Goal" else None
                })

        pickcenter = data.get('pickcenter', []) or data.get('odds', [])
        if isinstance(pickcenter, list) and pickcenter:
            odds_item = pickcenter[0]
            home_odds = odds_item.get('homeTeamOdds') or {}
            draw_odds = odds_item.get('drawOdds') or {}
            away_odds = odds_item.get('awayTeamOdds') or {}
            
            summary_data["odds"] = {
                "home": f"+{home_odds.get('moneyLine')}" if home_odds.get('moneyLine') and int(home_odds.get('moneyLine')) > 0 else str(home_odds.get('moneyLine') or 'TBD'),
                "draw": f"+{draw_odds.get('moneyLine')}" if draw_odds.get('moneyLine') and int(draw_odds.get('moneyLine')) > 0 else str(draw_odds.get('moneyLine') or 'TBD'),
                "away": f"+{away_odds.get('moneyLine')}" if away_odds.get('moneyLine') and int(away_odds.get('moneyLine')) > 0 else str(away_odds.get('moneyLine') or 'TBD'),
                "total": str(odds_item.get('overUnder', (odds_item.get('total') or {}).get('displayName', 'TBD'))), "over": str(odds_item.get('overOdds', 'TBD')), "under": str(odds_item.get('underOdds', 'TBD'))
            }

        inj_raw = data.get('injuries', [])
        if isinstance(inj_raw, list) and len(inj_raw) == 2:
            summary_data["injuries"] = {"home": [(i.get('athlete') or {}).get('displayName', '') for i in inj_raw[0].get('injuries', [])], "away": [(i.get('athlete') or {}).get('displayName', '') for i in inj_raw[1].get('injuries', [])]}

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
        c = (((lineup.get('team') or {}).get('colors') or {}).get('player') or {}).get('primary')
        return f"#{str(c).replace('#', '')}" if c else default_hex
    except:
        return default_hex

# ====================================================================
# TACTICAL PITCH HTML GENERATOR (PYTHON RENDERING)
# ====================================================================
def generate_pitch_html(lineup, default_hex, team_logo="", formation_str=""):
    if not lineup or not lineup.get('startXI'):
        return '''<div class="d-flex align-items-center justify-content-center" style="width:100%; aspect-ratio: 2/3; background: #2e8b57; margin: 0 auto; border-radius: 8px;">
            <span class="text-white fw-bold" style="font-size: 1.2rem; text-align: center; padding: 20px;">Awaiting Live Lineup Data</span>
        </div>'''
        
    formation = get_formation(lineup) if not formation_str else formation_str
    color = get_team_color(lineup, default_hex)
    contrast = get_contrast_color(color)
    
    try:
        rows = [int(x) for x in formation.split('-')]
        if sum(rows) != 10:
            rows = [4, 4, 2] 
    except:
        rows = [4, 4, 2]

    starters = lineup.get('startXI', [])
    gk = None
    field_players = []
    
    for s in starters:
        p = s.get('player', {})
        if p.get('category') == 'G' and not gk:
            gk = p
        else:
            field_players.append(p)
            
    # Mowed Grass effect + Chalk lines
    html = f'''<div class="pitch-container shadow-lg" style="position:relative; width: 100%; max-width: 500px; aspect-ratio: 2/3; margin: 0 auto; border: 3px solid #fff; border-radius: 12px; overflow: hidden; background: repeating-linear-gradient(0deg, #2e8b57, #2e8b57 10%, #297d4e 10%, #297d4e 20%);">'''
    
    # Watermark Logo
    if team_logo:
        html += f'<div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:65%; height:65%; opacity: 0.15; background-image: url(\'{team_logo}\'); background-size: contain; background-position: center; background-repeat: no-repeat; z-index: 1;"></div>'

    # Pitch Markings
    html += '<div style="position:absolute; top:50%; left:0; width:100%; height:2px; background:rgba(255,255,255,0.4); z-index: 2;"></div>' # Center Line
    html += '<div style="position:absolute; top:50%; left:50%; transform:translate(-50%, -50%); width:80px; height:80px; border:2px solid rgba(255,255,255,0.4); border-radius:50%; z-index: 2;"></div>' # Center Circle
    html += '<div style="position:absolute; top:0; left:20%; width:60%; height:16%; border:2px solid rgba(255,255,255,0.4); border-top:none; z-index: 2;"></div>' # Top Penalty Box
    html += '<div style="position:absolute; top:0; left:35%; width:30%; height:6%; border:2px solid rgba(255,255,255,0.4); border-top:none; z-index: 2;"></div>' # Top Goalie Box
    html += '<div style="position:absolute; bottom:0; left:20%; width:60%; height:16%; border:2px solid rgba(255,255,255,0.4); border-bottom:none; z-index: 2;"></div>' # Bottom Penalty Box
    html += '<div style="position:absolute; bottom:0; left:35%; width:30%; height:6%; border:2px solid rgba(255,255,255,0.4); border-bottom:none; z-index: 2;"></div>' # Bottom Goalie Box
    
    # Formation integrated on field
    if formation:
        html += f'<div style="position:absolute; top:15px; left:50%; transform:translateX(-50%); background:rgba(0,0,0,0.6); color:#fff; padding:4px 12px; border-radius:12px; font-size:0.75rem; font-weight:bold; z-index: 3; box-shadow:0 2px 4px rgba(0,0,0,0.3); border:1px solid rgba(255,255,255,0.2); backdrop-filter: blur(2px);">Formation: {formation}</div>'

    def render_pitch_player(player, x, y, bg_color, text_color):
        if not player: return ""
        name = shorten_player_name(player.get('name'))
        photo = player.get('photo', '')
        number = str(player.get('number', ''))
        p_id = str(player.get('id', ''))
        p_slug = f"{create_slug(player.get('name', ''))}-{p_id}"
        
        if photo:
            # We add an onload check: if ESPN returns a 1x1 transparent pixel, swap it to the silhouette.
            # Note: We use {{ and }} to escape the curly braces for the JavaScript inside the Python f-string.
            avatar = f'<img src="{photo}" loading="lazy" decoding="async" style="width:100%; height:100%; object-fit:cover; border-radius:50%; border: 3px solid {bg_color}; background-color: #f8f9fa; box-shadow: 0 4px 8px rgba(0,0,0,0.4);" onload="if(this.naturalWidth <= 1) {{ this.onload=null; this.src=\'https://a.espncdn.com/combiner/i?img=/i/headshots/nophoto.png\'; }}" onerror="this.onerror=null;this.src=\'https://a.espncdn.com/combiner/i?img=/i/headshots/nophoto.png\';">'
        else:
            initial = name[0] if name else ''
            avatar = f'<div style="width:100%; height:100%; border-radius:50%; background:{bg_color}; color:{text_color}; display:flex; align-items:center; justify-content:center; font-weight:bold; font-size:1.2rem; border: 3px solid #fff; box-shadow: 0 4px 8px rgba(0,0,0,0.4);">{initial}</div>'
            
        badge_html = ""
        if number:
            badge_html = f'<div style="position:absolute; bottom:-4px; right:-4px; background:#fff; color:#000; font-size:0.6rem; font-weight:bold; width:22px; height:22px; border-radius:50%; display:flex; align-items:center; justify-content:center; border:1px solid #ccc; box-shadow:0 2px 4px rgba(0,0,0,0.4); z-index:15;">{number}</div>'
            
        return f'''<div class="pitch-player" style="position:absolute; left:{x}%; top:{y}%; transform:translate(-50%, -50%); display:flex; flex-direction:column; align-items:center; width: clamp(60px, 15vw, 100px); z-index: 10;">
            <a href="/players/{p_slug}/" class="text-decoration-none" style="display:flex; flex-direction:column; align-items:center; color:inherit; width:100%;">
                <div style="position:relative; width: clamp(45px, 11vw, 66px); height: clamp(45px, 11vw, 66px); border-radius: 50%;">
                    {avatar}
                    {badge_html}
                </div>
                <div style="background: rgba(255,255,255,0.95); color: #000; font-size: clamp(0.55rem, 2vw, 0.75rem); font-weight: 800; padding: 3px 6px; border-radius: 4px; margin-top: 6px; white-space: nowrap; max-width: 100%; overflow: hidden; text-overflow: ellipsis; box-shadow: 0 2px 5px rgba(0,0,0,0.3); border: 1px solid {bg_color}; text-align:center;">{name}</div>
            </a>
        </div>'''
    html += render_pitch_player(gk, 50, 88, color, contrast)
    
    def get_x_weight(pos_str):
        pos = str(pos_str).upper()
        # Wide Left (LB, LM, LW, LWB)
        if pos.startswith('L') and '-' not in pos: return -2
        # Inner Left (CD-L, CM-L, CF-L)
        if pos.endswith('-L'): return -1
        # Inner Right (CD-R, CM-R, CF-R)
        if pos.endswith('-R'): return 1
        # Wide Right (RB, RM, RW, RWB)
        if pos.startswith('R') and '-' not in pos: return 2
        # Center (C, CD, CM, F, ST)
        return 0

    player_idx = 0
    for r_idx, count in enumerate(rows):
        # Spread lines vertically between 72% (Defense) and 15% (Attack)
        if len(rows) > 1:
            y_pos = 72 - (r_idx * (57 / (len(rows) - 1)))
        else:
            y_pos = 45
            
        # Extract the exact number of players for this row
        row_players = []
        for _ in range(count):
            if player_idx < len(field_players):
                row_players.append(field_players[player_idx])
                player_idx += 1
                
        # Sort them Left-to-Right based on our weighting function
        row_players.sort(key=lambda p: get_x_weight(p.get('pos', '')))
            
        # Render the sorted row
        for c_idx, player in enumerate(row_players):
            # Spread players horizontally across the field width (15% to 85%)
            if count > 1:
                x_pos = 15 + c_idx * (70 / (count - 1))
            else:
                x_pos = 50
                
            html += render_pitch_player(player, x_pos, y_pos, color, contrast)
                
    html += '</div>'
    return html

def get_time_badge_html(data):
    status = str((data['fixture']['status'] or {}).get('short', ''))
    elapsed = (data['fixture']['status'] or {}).get('elapsed')
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
    is_home = str(last_ev.get('team_id')) == str((data['teams']['home'] or {}).get('id', ''))
    team_name = str((data['teams']['home'] or {}).get('name', 'TBD')) if is_home else str((data['teams']['away'] or {}).get('name', 'TBD'))
    team_logo = str((data['teams']['home'] or {}).get('logo', '')) if is_home else str((data['teams']['away'] or {}).get('logo', ''))

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
    is_pre = (data['fixture']['status'] or {}).get('short') in ['NS', 'TBD', 'PST', 'CANC', 'ABD']
    h_score = '-' if is_pre else (data.get('goals') or {}).get('home', 0)
    a_score = '-' if is_pre else (data.get('goals') or {}).get('away', 0)
    
    l_flag = str(data["league"].get("flag") or "")
    flag_html = f'<img src="{l_flag}" loading="lazy" decoding="async" style="width: 20px; height: 20px; object-fit: contain; margin-right: 6px; vertical-align: middle; border-radius: 2px; box-shadow: 0 1px 2px rgba(0,0,0,0.1);">' if l_flag.startswith('http') or l_flag.startswith('/images/') else f'<span style="font-size: 1.1rem; margin-right: 6px; vertical-align: middle; line-height: 1;">{l_flag or "🏆"}</span>'
    
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
    is_pre = (data['fixture']['status'] or {}).get('short') in ['NS', 'TBD', 'PST', 'CANC', 'ABD']
    h_score = (data.get('goals') or {}).get('home', 0)
    a_score = (data.get('goals') or {}).get('away', 0)
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
        p_id = str(p.get('id', ''))
        p_slug = f"{create_slug(p.get('name', ''))}-{p_id}"
        pho = f'''<img data-src="{p.get('photo', '')}" style="width: 22px; height: 22px; border-radius: 50%; object-fit: cover;" class="me-2 player-headshot" onerror="this.onerror=null;this.src='https://a.espncdn.com/combiner/i?img=/i/headshots/nophoto.png';">''' if p.get('photo') else '''<div style="width:22px; height:22px; border-radius:50%; background:#e9ecef;" class="me-2 d-inline-block"></div>'''
        sub = '''<span class="text-primary fw-bold me-1" title="Subbed Out">↻</span>''' if p.get('isSubbedOut') else ''
        items += f'''<li class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="font-size: 0.8rem;"><span class="text-muted fw-bold me-2" style="font-size: 0.65rem; min-width: 32px; display: inline-block; text-align: left;">{p.get('pos','M')}</span>{pho}<a href="/players/{p_slug}/" class="batter-name text-dark text-decoration-none text-truncate">{sub}{shorten_player_name(p.get('name'))}</a><span class="ms-auto text-muted" style="font-size: 0.65rem;">#{p.get('number','')}</span></li>'''
    return f'''<div class="w-100 text-center py-1 fw-bold text-white bg-success" style="font-size: 0.65rem;">✅ {get_formation(lineup_data)}</div><ul class="batting-order w-100 m-0 p-0">{items}</ul>'''

def is_match_live(match):
    """Returns True if the match is currently in-play (live)."""
    status_short = str((match.get('fixture', {}) or {}).get('status', {}).get('short', '')).upper()
    return status_short not in ['FT', 'AET', 'NS', 'TBD', 'PST', 'CANC', 'ABD']

def get_live_sort_weight(match):
    """
    Calculates a weight so that matches nearest to the end of the game 
    have the highest weight and sort to the top.
    """
    status_info = match.get('fixture', {}).get('status', {}) or {}
    status_code = str(status_info.get('short', '')).upper()
    
    elapsed_raw = status_info.get('elapsed', 0)
    try:
        elapsed = int(re.sub(r'[^0-9]', '', str(elapsed_raw)))
    except (ValueError, TypeError):
        elapsed = 0

    if status_code in ['P', 'PEN', 'PENALTY']:
        return 200 + elapsed
    elif status_code in ['ET', '2ET', '1ET']:
        return 100 + elapsed
    elif status_code == '2H' or (status_code not in ['1H', 'HT'] and elapsed > 45):
        return 50 + elapsed
    elif status_code in ['HT', 'BT']:
        return 46
    elif status_code in ['1H']:
        return elapsed
    else:
        return elapsed

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
            p_id = str(p.get('id', ''))
            p_slug = f"{create_slug(p.get('name', ''))}-{p_id}"
            pre = '<span class="text-success fw-bold me-1">▲</span>' if p.get('isSubbedIn') else ('<span class="text-primary fw-bold me-1">↻</span>' if p.get('isSubbedOut') else '')
            st = p.get('live_stats', {})
            html += f'''<div class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="font-size: 0.70rem;"><div class="text-start text-truncate" style="flex: 1;"><a href="/players/{p_slug}/" class="text-dark text-decoration-none text-truncate">{pre}{shorten_player_name(p.get('name'))}</a></div><div class="text-muted" style="width: 18px; text-align: center; font-weight: 600;">{st.get(g['k'][0],0)}</div><div class="text-muted" style="width: 22px; text-align: center; font-weight: 600;">{st.get(g['k'][1],0)}</div><div class="text-muted" style="width: 28px; text-align: center; font-weight: 600;">{st.get(g['k'][2],0)}</div><div class="text-muted" style="width: 24px; text-align: center; font-weight: 600;">{st.get(g['k'][3],0)}</div></div>'''
    return html

def pre_render_game_card(data, is_live_section=False):
    fix_id = str(data['fixture'].get('id', ''))
    dom_id = f"live-{fix_id}" if is_live_section else fix_id
    is_pre = (data['fixture']['status'] or {}).get('short', '') in ['NS', 'TBD']
    has_stats = bool(data.get('team_stats'))
    
    l_flag = str(data['league'].get('flag') or "")
    flag_html = f'<img src="{l_flag}" loading="lazy" decoding="async" style="width: 24px; height: 24px; object-fit: contain; margin-right: 6px; vertical-align: middle; border-radius: 3px; filter: drop-shadow(0 1px 1px rgba(0,0,0,0.1));">' if l_flag.startswith('http') or l_flag.startswith('/images/') else f'<span style="font-size: 1.3rem; margin-right: 6px; vertical-align: middle; line-height: 1;">{l_flag or "🏆"}</span>'
    
    h_col = get_team_color(data.get('homeLineup'), '#0d6efd')
    a_col = get_team_color(data.get('awayLineup'), '#dc3545')
    
    home_slug = create_slug(data['teams']['home']['name'])
    away_slug = create_slug(data['teams']['away']['name'])
    
    home_lineup_html = f'<a href="/teams/{home_slug}/lineup/" class="text-decoration-none text-primary" style="font-size:0.65rem; display:block; margin-top:-2px;">Lineup</a>' if data.get('is_today_partition') else ''
    away_lineup_html = f'<a href="/teams/{away_slug}/lineup/" class="text-decoration-none text-primary" style="font-size:0.65rem; display:block; margin-top:-2px;">Lineup</a>' if data.get('is_today_partition') else ''

    return f'''<!-- MATCH_{dom_id} -->
    <div class="lineup-card shadow-sm" id="card-{dom_id}">
        <div class="ribbon-view" id="ribbon-{dom_id}" onclick="toggleSingleCard('{dom_id}')">{get_ribbon_html(data)}</div>
        <div class="full-view d-none" id="full-{dom_id}">
            <div class="p-2 pb-1" style="background-color: #fcfcfc;">
                <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom" style="cursor: pointer;" onclick="toggleSingleCard('{dom_id}')">
                    <div class="pe-2 d-flex align-items-center flex-shrink-0" id="time-{dom_id}" style="white-space: nowrap;">{get_time_badge_html(data)} {get_latest_event_html(data)}</div>
                    <a href="/leagues/{data['league']['slug']}/" class="text-decoration-none text-muted fw-bold text-uppercase text-end ms-auto text-truncate d-flex align-items-center justify-end" style="font-size: 0.75rem; min-width: 0;" title="{data['league']['name']}">{flag_html} <span class="text-truncate">{data['league']['name']}</span></a>
                </div>
                <div class="d-flex justify-content-between align-items-center px-1 py-1 w-100">
                    <div class="text-center" style="width: 30%;"><img src="{data['teams']['home']['logo']}" loading="lazy" decoding="async" class="team-logo mb-1"><div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">{data['teams']['home']['name']}</div>{home_lineup_html}</div>
                    <div class="text-center d-flex flex-column align-items-center justify-content-center" style="width: 40%;" id="score-{dom_id}">{get_center_column_html(data)}</div>
                    <div class="text-center" style="width: 30%;"><img src="{data['teams']['away']['logo']}" loading="lazy" decoding="async" class="team-logo mb-1"><div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">{data['teams']['away']['name']}</div>{away_lineup_html}</div>
                </div>
                <div class="w-100" id="events-{dom_id}">{get_events_html(data)}</div>
            </div>
            <div class="w-100" id="odds-{dom_id}">{get_odds_html(data)}</div>
            <div class="w-100" id="injuries-{dom_id}">{get_injuries_html(data)}</div>
            <a href="https://weatherfootball.com/teams/{home_slug}/" class="d-block w-100 text-center py-2 border-bottom text-decoration-none fw-bold" style="background-color: #e0f2fe; color: #0284c7; font-size: 0.75rem;">🌤️ Weather Forecast</a>
            <div class="bg-light border-bottom d-flex justify-content-center align-items-center px-2 py-1">
                <div class="d-flex gap-4 w-100">
                    <div class="lineup-tab {'active' if (not has_stats or is_pre) else ''}" id="tab-xi-{dom_id}" onclick="switchLineupTab(event, '{dom_id}', 'xi')" style="flex: 1; text-align: center;">{'STARTING XI' if is_pre else 'FINAL XI'}</div>
                    <div class="lineup-tab {'active' if (has_stats and not is_pre) else ''} {'d-none' if not has_stats else ''}" id="tab-stats-{dom_id}" onclick="switchLineupTab(event, '{dom_id}', 'stats')" style="flex: 1; text-align: center;">LIVE STATS</div>
                </div>
            </div>
            <div class="collapse show lineup-container" id="lineup-collapse-{dom_id}">
                <div id="view-xi-{dom_id}" class="{'d-none' if (has_stats and not is_pre) else ''}"><div class="row g-0 bg-white border-top"><div class="col-6 border-end">{build_lineup_list(data.get('homeLineup'))}</div><div class="col-6">{build_lineup_list(data.get('awayLineup'))}</div></div></div>
                <div id="view-stats-{dom_id}" class="{'d-none' if (not has_stats or is_pre) else ''}"><div class="row g-0 bg-white border-top"><div class="col-6 border-end">{build_live_stats_grid(data.get('homeLineup'), h_col)}</div><div class="col-6">{build_live_stats_grid(data.get('awayLineup'), a_col)}</div></div></div>
            </div>
        </div>
    </div>
    <!-- END_MATCH_{dom_id} -->'''

def group_and_sort_matches_by_league(matches):
    if not matches: return []
    leagues_map = {}
    for m in matches:
        l_info = m.get('league') or {}
        l_slug = l_info.get('slug') or create_slug(l_info.get('name', 'other'))
        l_name = l_info.get('name', 'Global Football')
        l_flag = l_info.get('flag', '')
        match_date = (m.get('fixture') or {}).get('date', '9999-99-99') or '9999-99-99'

        if l_slug not in leagues_map:
            leagues_map[l_slug] = {'name': l_name, 'slug': l_slug, 'flag': l_flag, 'earliest_date': match_date, 'matches': []}
        
        leagues_map[l_slug]['matches'].append(m)
        if match_date < leagues_map[l_slug]['earliest_date']:
            leagues_map[l_slug]['earliest_date'] = match_date

    league_list = list(leagues_map.values())
    for lg in league_list: lg['matches'].sort(key=lambda x: (x.get('fixture') or {}).get('date', '9999-99-99') or '9999-99-99')
    league_list.sort(key=lambda x: x['earliest_date'])
    return league_list

def fetch_espn_scores_for_date(date_str, old_html, pill=None, end_date_str=None, is_today_partition=False, core_index=None):
    headers = {'User-Agent': 'Mozilla/5.0'}
    raw_events = []
    league_pill_map = {}
    seen_ids = set()
    page, max_pages = 1, 10

    while page <= max_pages:
        if pill and end_date_str:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{pill}/scoreboard?dates={date_str}-{end_date_str}&limit=1000&page={page}"
        else:
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}&limit=1000&page={page}"
            
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200: break
            res_json = res.json()

            for lg in res_json.get('leagues', []):
                lg_id = str(lg.get('id', ''))
                lg_slug = lg.get('slug', '')
                if lg_id and lg_slug:
                    league_pill_map[lg_id] = lg_slug

            events = res_json.get('events', [])
            if not events: break
            added_this_page = 0
            for ev in events:
                ev_id = str(ev.get('id', ''))
                if ev_id and ev_id not in seen_ids:
                    seen_ids.add(ev_id); raw_events.append(ev); added_this_page += 1
            if added_this_page == 0: break
            page += 1
        except: break

    # --- PRE-FETCH MATCH SUMMARIES IN PARALLEL ---
    events_to_fetch = []
    for event in raw_events:
        event_id = str(event.get('id', ''))
        state = ((event.get('status') or {}).get('type') or {}).get('state', 'pre')
        
        # 1. Check if finished match is cached in old_html
        is_cached = False
        if state == 'post' and old_html:
            match_pattern = f"<!-- MATCH_{event_id} -->(.*?)<!-- END_MATCH_{event_id} -->"
            saved_block = re.search(match_pattern, old_html, re.DOTALL)
            if saved_block and any(badge in saved_block.group(1) for badge in ['>FT</span>', '>AET</span>', '>PEN</span>', '>PST</span>', '>CANC</span>', '>ABD</span>']):
                is_cached = True

        if not is_cached:
            should_fetch, _ = should_fetch_summary(event)
            if should_fetch and event_id:
                events_to_fetch.append(event_id)

    pre_fetched_summaries = {}
    if events_to_fetch:
        print(f"    ⚡ Threading {len(events_to_fetch)} Match Summaries...")
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_id = {executor.submit(parse_espn_summary, eid): eid for eid in events_to_fetch}
            for future in as_completed(future_to_id):
                eid = future_to_id[future]
                try: 
                    res = future.result()
                    if res: pre_fetched_summaries[eid] = res
                except Exception: 
                    pass
    # ---------------------------------------------

    matches = []
    for event in raw_events:
        try:
            event_id = str(event.get('id', ''))
            state = ((event.get('status') or {}).get('type') or {}).get('state', 'pre')

            comps = event.get('competitions', [])
            if not comps: continue
            comp = comps[0]
            
            home_comp = next((c for c in comp.get('competitors', []) if c.get('homeAway') == 'home'), None)
            away_comp = next((c for c in comp.get('competitors', []) if c.get('homeAway') == 'away'), None)
            if not home_comp or not away_comp: continue

            h_team = home_comp.get('team') or {}
            a_team = away_comp.get('team') or {}
            
            home_id = str(h_team.get('id', ''))
            away_id = str(a_team.get('id', ''))
            home_name = str(h_team.get('displayName') or h_team.get('name') or "TBD")
            away_name = str(a_team.get('displayName') or a_team.get('name') or "TBD")
            home_logo = get_local_image_url(str(h_team.get('logo') or ""), subfolder="images/teams")
            away_logo = get_local_image_url(str(a_team.get('logo') or ""), subfolder="images/teams")

            # --- 🎯 NEW 4-TIER RESOLUTION ENGINE ---
            resolved_pill, resolved_display_name = resolve_event_league(event, core_index)

            # Fallbacks if core resolver is not active
            league_list = event.get('leagues') or []
            first_league = league_list[0] if isinstance(league_list, list) and len(league_list) > 0 else {}
            league_obj = event.get('league') or comp.get('league') or first_league
            league_id = str(league_obj.get('id', ''))

            raw_name = resolved_display_name or str(comp.get('altGameNote') or league_obj.get('name') or league_obj.get('displayName') or "Global Football")
            final_league_name = re.sub(r'^\d{4}-\d{4}\s+', '', raw_name).strip()
            
            # Clean comma/group clutter for page titles
            if ',' in final_league_name and not resolved_display_name:
                final_league_name = final_league_name.split(',')[0].strip()

            league_slug = create_slug(final_league_name)

            extracted_numeric_pill = ""
            uid = event.get('uid', '')
            if uid:
                for part in uid.split('~'):
                    if part.startswith('l:'):
                        extracted_numeric_pill = part.replace('l:', '')
                        break

            league_pill = (
                resolved_pill or
                extracted_numeric_pill or
                league_pill_map.get(league_id) or 
                first_league.get('slug') or 
                league_obj.get('slug') or 
                KNOWN_LEAGUE_PILLS.get(normalize_text(final_league_name), '')
            )
            # ----------------------------------------

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

            league_flag = get_local_image_url(str(league_flag or ""), subfolder="images/leagues")

            if state == 'post' and old_html:
                match_pattern = f"<!-- MATCH_{event_id} -->(.*?)<!-- END_MATCH_{event_id} -->"
                saved_block = re.search(match_pattern, old_html, re.DOTALL)
                if saved_block:
                    card_content = saved_block.group(1)
                    # Add >PST</span>, >CANC</span>, and >ABD</span> to the cache list
                    if any(badge in card_content for badge in ['>FT</span>', '>AET</span>', '>PEN</span>', '>PST</span>', '>CANC</span>', '>ABD</span>']):
                        matches.append({
                            "fixture": {"id": event_id, "date": event.get('date', ''), "status": {"short": "FT"}}, # Note: this dummy status here is fine since the HTML is pre-rendered
                            "teams": {"home": {"id": home_id, "name": home_name, "logo": home_logo}, "away": {"id": away_id, "name": away_name, "logo": away_logo}},
                            "goals": {"home": int(home_comp.get('score') or 0), "away": int(away_comp.get('score') or 0)},
                            "league": {"name": final_league_name, "abbrev": generate_league_abbrev(final_league_name), "slug": league_slug, "flag": league_flag, "pill": league_pill},
                            "html_card": f"<!-- MATCH_{event_id} -->{card_content}<!-- END_MATCH_{event_id} -->",
                            "is_today_partition": is_today_partition
                        })
                        continue

            should_fetch, _ = should_fetch_summary(event)
            # Pull from our parallel pre-fetched dictionary instead of making a blocking call
            summary = pre_fetched_summaries.get(event_id) if should_fetch else None
            
            if not summary:
                summary = {
                    "team_stats": None, "homeLineup": None, "awayLineup": None, "events": [], 
                    "odds": {"home": "TBD", "draw": "TBD", "away": "TBD", "total": "TBD", "over": "TBD", "under": "TBD"}, 
                    "injuries": {"home": [], "away": []}, 
                    "live_score": {}, "status_obj": None
                }

            fresh_status = summary.get("status_obj") or event.get('status') or {}
            fresh_type = fresh_status.get('type') or {}
            st = fresh_type.get('state', state)
            status_name = fresh_type.get('name', '')
            
            # Explicitly catch Postponements/Cancellations before defaulting to FT/NS
            if status_name == 'STATUS_POSTPONED':
                status_short = 'PST'
            elif status_name in ['STATUS_CANCELED', 'STATUS_CANCELLED']:
                status_short = 'CANC'
            elif status_name == 'STATUS_ABANDONED':
                status_short = 'ABD'
            else:
                status_short = 'NS' if st == 'pre' else ('FT' if st == 'post' else fresh_type.get('shortDetail', 'LIVE'))

            match_entry = {
                "fixture": {"id": event_id, "date": event.get('date', ''), "status": {"short": status_short, "elapsed": extract_match_clock(fresh_status)}},
                "league": {"id": event_id, "name": final_league_name, "abbrev": generate_league_abbrev(final_league_name), "slug": league_slug, "flag": league_flag, "pill": league_pill},
                "teams": {
                    "home": {"id": home_id, "name": home_name, "logo": home_logo},
                    "away": {"id": away_id, "name": away_name, "logo": away_logo}
                },
                "goals": {
                    "home": int((summary.get('live_score') or {}).get('home') or home_comp.get('score') or 0), 
                    "away": int((summary.get('live_score') or {}).get('away') or away_comp.get('score') or 0)
                },
                "team_stats": summary["team_stats"], "homeLineup": summary["homeLineup"], "awayLineup": summary["awayLineup"],
                "events": summary["events"], "odds": summary["odds"], "injuries": summary["injuries"],
                "is_today_partition": is_today_partition
            }
            
            match_entry["html_card"] = pre_render_game_card(match_entry)
            matches.append(match_entry)

        except Exception as e: 
            print(f"❌ ERROR parsing match item {event.get('id')}: {e}")

    return matches

# ====================================================================
# HTML TEMPLATES (MAIN + LEAGUE + TEAM + PLAYER)
# ====================================================================
BASE_HEADER = """
<nav class="navbar sticky-top shadow-sm pt-2 pb-2 mb-0" style="background-color: #212529; z-index: 1050;">
    <div class="container d-flex justify-content-between align-items-center">
        <div class="header-brand"><a href="/" class="text-decoration-none">Futbol Starting <span>Eleven</span></a></div>
        <div class="d-flex align-items-center gap-2">
            <div class="dropdown league-search-container">
                <input type="text" id="leagueSearchNavInput" class="form-control form-control-sm" placeholder="🏆 Search leagues..." data-bs-toggle="dropdown" aria-expanded="false" style="width: 160px; background-color: #343a40; color: white; border: 1px solid #495057; cursor: pointer;" autocomplete="off">
                <ul id="leagueSearchList" class="dropdown-menu dropdown-menu-end shadow-sm mt-2" style="max-height: 400px; overflow-y: auto; width: 260px; border-radius: 8px;">
                    {{ nav_leagues_html | safe }}
                </ul>
            </div>
            <input type="text" id="team-search" class="form-control form-control-sm ms-2" placeholder="🔍 Search...">
        </div>
    </div>
</nav>
"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#212529">
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-WKSS7R4E02"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-WKSS7R4E02');
    </script>
    <!-- Title & SEO Meta Tags -->
    <title>Futbol Starting Eleven | Live Soccer-Futbol-Football Starting Lineups, Starting XI, Scores, Injuries & Odds</title>
    <meta name="description" content="Real-time soccer and football starting XIs, live match scores, goalscorers, injuries, and betting odds. Up-to-the-minute data for Premier League, Champions League, MLS, La Liga, and global football.">
    <meta name="keywords" content="soccer starting lineups, football starting xi, live soccer scores, missing players, soccer injuries, premier league lineups, la liga lineups, mls lineups, soccer betting odds, live match stats">

    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Futbol Starting Eleven">
    <meta property="og:url" content="https://futbolstartingeleven.com/">
    <meta property="og:title" content="Futbol Starting Eleven | Live Soccer Starting Lineups, Scores & Injuries">
    <meta property="og:description" content="Real-time soccer starting XIs, live scores, goalscorers, injuries, and matchup stats for the world's top leagues.">
    <meta property="og:image" content="https://futbolstartingeleven.com/social-share1.png">
    
    <!-- Twitter -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:domain" content="futbolstartingeleven.com">
    <meta name="twitter:url" content="https://futbolstartingeleven.com/">
    <meta name="twitter:title" content="Futbol Starting Eleven | Live Soccer Starting Lineups, Scores & Injuries">
    <meta name="twitter:description" content="Real-time soccer starting XIs, live match scores, injuries, and betting odds.">
    <meta name="twitter:image" content="https://futbolstartingeleven.com/social-share1.png">
    
    <!-- Canonical -->
    <link rel="canonical" id="canonical-url" href="https://futbolstartingeleven.com/">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        document.addEventListener('error', function (e) { if (e.target.tagName === 'IMG') { e.target.style.display = 'none'; } }, true);
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
    {{ schema_json | safe }}
</head>
<body>

""" + BASE_HEADER + """

<div class="container mt-3 mb-2 text-center">
    <h1 class="h5 fw-bold text-dark mb-1">Futbol Starting Eleven: Live Soccer Starting Lineups, Scores & Odds</h1>
    <p class="text-muted mb-2" style="font-size: 0.85rem;">Real-time starting XIs, match injuries, goalscorers, and betting odds for global football.</p>
    
    <div class="d-flex justify-content-center gap-2 my-3" id="day-selector">
        <button class="btn btn-outline-dark day-tab-btn" data-day="yesterday">Yesterday<br><small style="font-size: 0.65rem;">{{ display_dates.yesterday }}</small></button>
        <button class="btn btn-dark day-tab-btn active" data-day="today">Today<br><small style="font-size: 0.65rem;">{{ display_dates.today }}</small></button>
        <button class="btn btn-outline-dark day-tab-btn" data-day="tomorrow">Tomorrow<br><small style="font-size: 0.65rem;">{{ display_dates.tomorrow }}</small></button>
    </div>
</div>

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
                {% if day == 'today' and live_cards and live_cards | length > 0 %}
                    <div class="col-12 live-header mt-2 mb-2 px-1" id="live-matches-section">
                        <div class="d-flex align-items-center p-2 rounded-3 shadow-sm" style="background: #212529; border-left: 4px solid #20c997;">
                            <span class="live-dot me-2"></span>
                            <h2 class="h6 mb-0 fw-bold text-white text-uppercase" style="letter-spacing: 0.5px;">🔥 LIVE MATCHES NOW</h2>
                            <span class="badge bg-success text-white border ms-auto px-2 py-1" style="font-size: 0.65rem;">{{ live_cards | length }} {{ 'Match' if live_cards | length == 1 else 'Matches' }}</span>
                        </div>
                    </div>
                    {% for match in live_cards %}
                        <div class="col-md-6 col-lg-6 col-xl-4 mb-3 game-card-wrapper" data-search="{{ match.search }}">
                            {{ match.html_card | safe }}
                        </div>
                    {% endfor %}
                {% endif %}

                {% if leagues | length == 0 and (day != 'today' or (live_cards | length == 0)) %}
                    <div class="col-12 text-center mt-5 empty-state">
                        <div class="card p-4 shadow-sm border-0"><div class="h4 text-muted">🏟️ No matches scheduled for this partition.</div></div>
                    </div>
                {% else %}
                    <div class="col-12 text-center mt-5 empty-state d-none">
                        <div class="card p-4 shadow-sm border-0"><div class="h4 text-muted">🏟️ No matches found.</div></div>
                    </div>
                    {% for league in leagues %}
                        <div class="col-12 league-header mt-3 mb-2 px-1" id="league-{{ day }}-{{ league.slug }}" data-league-name="{{ league.name }}">
                            <div class="d-flex align-items-center p-2 rounded-3 shadow-sm league-banner">
                                {% if league.flag and (league.flag.startswith('http') or league.flag.startswith('/images/')) %}
                                    <img src="{{ league.flag }}" loading="lazy" decoding="async" alt="" style="width: 22px; height: 22px; object-fit: contain;" class="me-2 rounded-1">
                                {% else %}
                                    <span class="me-2" style="font-size: 1.1rem;">{{ league.flag or '🏆' }}</span>
                                {% endif %}
                                <h2 class="h6 mb-0 fw-bold text-dark text-uppercase" style="letter-spacing: 0.5px;"><a href="/leagues/{{ league.slug }}/" class="text-dark text-decoration-none">{{ league.name }}</a></h2>
                                <span class="badge bg-light text-secondary border ms-auto px-2 py-1" style="font-size: 0.65rem;">{{ league.matches | length }} {{ 'Match' if league.matches | length == 1 else 'Matches' }}</span>
                            </div>
                        </div>
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
    let ACTIVE_DAY = "today";
    let globalScoreboardMode = true;

    document.addEventListener('DOMContentLoaded', () => {
        populateLeagueDropdown();
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
        document.getElementById('leagueSearchNavInput')?.addEventListener('input', function(e) {
            const text = e.target.value.toLowerCase();
            document.querySelectorAll('#leagueSearchList li').forEach(li => {
                const leagueName = li.textContent.toLowerCase();
                li.style.display = leagueName.includes(text) ? '' : 'none';
            });
        });

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
                window.scrollTo({ top: offsetPosition, behavior: 'smooth' });
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
        const headers = Array.from(activePartition.querySelectorAll('.league-header'))
            .filter(h => !h.classList.contains('d-none'))
            .sort((a, b) => (a.getAttribute('data-league-name') || '').localeCompare(b.getAttribute('data-league-name') || ''));
        headers.forEach(h => {
            const opt = document.createElement('option');
            opt.value = h.id; opt.textContent = h.getAttribute('data-league-name') || 'League';
            select.appendChild(opt);
        });
    }

    function applySearchFilter() {
        const searchText = (document.getElementById('team-search')?.value || '').toLowerCase();
        const activePartition = document.getElementById('partition-' + ACTIVE_DAY);
        if (!activePartition) return;
        let totalVisibleMatches = 0;
        activePartition.querySelectorAll('.league-header, .live-header').forEach(header => {
            let visibleInLeague = 0, sibling = header.nextElementSibling;
            while (sibling && !sibling.classList.contains('league-header') && !sibling.classList.contains('live-header')) {
                if (sibling.classList.contains('game-card-wrapper')) {
                    if ((sibling.getAttribute('data-search') || '').includes(searchText)) {
                        sibling.classList.remove('d-none'); visibleInLeague++; totalVisibleMatches++;
                    } else { sibling.classList.add('d-none'); }
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
        if (fullView && !fullView.classList.contains('d-none')) {
            fullView.querySelectorAll('img[data-src]').forEach(img => { img.src = img.getAttribute('data-src'); img.removeAttribute('data-src'); });
        }
    };

    window.switchLineupTab = function(event, fixId, tabName) {
        if (event && event.stopPropagation) event.stopPropagation();
        const xiTab = document.getElementById(`tab-xi-${fixId}`), statsTab = document.getElementById(`tab-stats-${fixId}`);
        const xiView = document.getElementById(`view-xi-${fixId}`), statsView = document.getElementById(`view-stats-${fixId}`);
        if (tabName === 'xi') { xiTab?.classList.add('active'); statsTab?.classList.remove('active'); xiView?.classList.remove('d-none'); statsView?.classList.add('d-none'); }
        else if (tabName === 'stats') { statsTab?.classList.add('active'); xiTab?.classList.remove('active'); statsView?.classList.remove('d-none'); xiView?.classList.add('d-none'); }
    };

    function triggerCardGlow(cardEl, newestEventText) {
        if (!cardEl || !newestEventText) return;
        const text = newestEventText.toLowerCase();
        
        // Simple mapping based ONLY on the single new event string
        let glowClass = 'glow-goal'; 
        if (text.includes('🟥') || text.includes('red')) glowClass = 'glow-red-card';
        else if (text.includes('🟨') || text.includes('yellow')) glowClass = 'glow-yellow-card';
        else if (text.includes('🔄') || text.includes('sub')) glowClass = 'glow-subst';

        cardEl.classList.remove('glow-goal', 'glow-red-card', 'glow-yellow-card', 'glow-subst');
        void cardEl.offsetWidth;
        cardEl.classList.add(glowClass);
        setTimeout(() => { cardEl.classList.remove(glowClass); }, 4000);
    }

    async function pollAndUpdateDOM() {
        try {
            const res = await fetch(window.location.href, { cache: 'no-store' });
            if (!res.ok) return;
            const htmlText = await res.text();
            
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(htmlText, 'text/html');

            document.querySelectorAll('.lineup-card').forEach(currentCard => {
                const cardId = currentCard.id;
                if (!cardId) return;
                const fixId = cardId.replace('card-', '');
                const newCard = newDoc.getElementById(cardId);
                
                if (!newCard) return;

                if (currentCard.innerHTML === newCard.innerHTML) return;

                const currentEventsHtml = currentCard.querySelector(`#events-${fixId}`)?.innerHTML || '';
                const newEventsHtml = newCard.querySelector(`#events-${fixId}`)?.innerHTML || '';
                const hasNewEvent = currentEventsHtml !== newEventsHtml && newEventsHtml.trim() !== '';

                let newestEventText = '';
                if (hasNewEvent) {
                    const oldRows = Array.from(currentCard.querySelectorAll('.event-expanded .d-flex.align-items-start')).map(el => el.textContent);
                    const newRows = Array.from(newCard.querySelectorAll('.event-expanded .d-flex.align-items-start'));
                    
                    // Grab the first row in the new DOM that isn't in the old DOM (which is the latest event)
                    for (let row of newRows) {
                        if (!oldRows.includes(row.textContent)) {
                            newestEventText = row.textContent;
                            break;
                        }
                    }
                }

                const isRibbonVisible = !currentCard.querySelector('.ribbon-view')?.classList.contains('d-none');
                const isFullVisible = !currentCard.querySelector('.full-view')?.classList.contains('d-none');
                const activeTab = currentCard.querySelector('.lineup-tab.active')?.id;

                currentCard.innerHTML = newCard.innerHTML;

                if (isRibbonVisible !== undefined && isFullVisible !== undefined) {
                    currentCard.querySelector('.ribbon-view')?.classList.toggle('d-none', !isRibbonVisible);
                    currentCard.querySelector('.full-view')?.classList.toggle('d-none', !isFullVisible);
                }
                if (activeTab) {
                    const tabName = activeTab.includes('stats') ? 'stats' : 'xi';
                    window.switchLineupTab(null, fixId, tabName);
                }

                if (newestEventText) {
                    triggerCardGlow(currentCard, newestEventText);
                }
            });
        } catch (err) {
            console.error("DOM update failed:", err);
        }
    }
</script>
</body>
</html>
"""

LEAGUE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#212529">
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-WKSS7R4E02"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-WKSS7R4E02');
    </script>
    <title>{{ seo_title }}</title>
    <meta name="description" content="{{ seo_desc }}">
    <link class="canonical" href="https://futbolstartingeleven.com/leagues/{{ league_slug }}/">
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:title" content="{{ seo_title }}">
    <meta property="og:description" content="{{ seo_desc }}">
    
    <!-- Twitter -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{{ seo_title }}">
    <meta name="twitter:description" content="{{ seo_desc }}">
    
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        document.addEventListener('error', function (e) { if (e.target.tagName === 'IMG') { e.target.style.display = 'none'; } }, true);
    </script>
    <style>
        body { background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .header-brand { font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; font-style: italic; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
        .header-brand a { color: inherit; }
        .header-brand span { text-shadow: none !important; background: linear-gradient(to bottom, #20c997 0%, #198754 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; filter: drop-shadow(0 0 12px rgba(32, 201, 151, 0.6)); }
        
        .lineup-card { background: #fff; border: 1px solid #dee2e6; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 16px; overflow: hidden; }
        .team-logo { width: 45px; height: 45px; object-fit: contain; filter: drop-shadow(0px 2px 2px rgba(0,0,0,0.1)); }
        .batting-order { padding-left: 0; list-style-type: none; margin-bottom: 0; }
        .batting-order li { padding: 6px 12px; font-size: 0.85rem; border-bottom: 1px solid #f1f3f5; display: flex; justify-content: space-between; align-items: center; }
        .batting-order li:last-child { border-bottom: none; }
        .batter-name { font-weight: 600; color: #495057; }
        
        .date-subheader { background: #ffffff; border-left: 4px solid #0d6efd; border-radius: 8px; font-weight: 700; color: #343a40; text-transform: uppercase; letter-spacing: 0.5px; }
        
        .live-dot { display: inline-block; width: 7px; height: 7px; background-color: #fff; border-radius: 50%; margin-right: 5px; margin-bottom: 1px; animation: pulse-green 2s infinite; }
        @keyframes pulse-green { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(32, 201, 151, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0); } }
        .stat-bar-container { display: flex; width: 100%; height: 14px; background-color: #e9ecef; border-radius: 4px; overflow: hidden; margin-top: 2px; }
        .stat-bar-segment { display: flex; align-items: center; justify-content: center; font-size: 0.60rem; font-weight: 800; padding: 0 4px; transition: width 0.5s ease-in-out; }
        .stat-label-tiny { font-size: 0.55rem; text-transform: uppercase; font-weight: 700; color: #6c757d; margin-top: 4px; }
        .lineup-tab { font-size: 0.65rem; font-weight: 700; padding: 6px 4px; color: #adb5bd; cursor: pointer; transition: all 0.2s ease; border-bottom: 2px solid transparent; text-transform: uppercase; }
        .lineup-tab.active { color: #20c997; border-bottom: 2px solid #20c997; }

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
    {{ schema_json | safe }}
</head>
<body>

""" + BASE_HEADER + """

<div class="container mt-4 mb-3 text-center">
    <h1 class="h4 fw-bold text-dark mb-1">{{ page_h1 }}</h1>
    {% if not is_today %}
        <p class="text-muted mb-2" style="font-size: 0.85rem;">Upcoming 14-day schedule, betting odds, and match info.</p>
    {% endif %}
</div>

<div class="container pb-5">
    <div class="row justify-content-start">
        {% if grouped_matches | length == 0 %}
            <div class="col-12 text-center mt-5">
                <div class="card p-5 shadow-sm border-0 rounded-4">
                    <div class="h3 mb-3">🏖️</div>
                    <div class="h4 text-dark fw-bold mb-2">{{ league_name }} is currently on break.</div>
                    <p class="text-muted">There are no upcoming matches scheduled for this league in the next 14 days. Please check back as we get closer to match day.</p>
                </div>
            </div>
        {% else %}
            {% for date_str, matches in grouped_matches.items() %}
                {% if not is_today %}
                <div class="col-12 mt-4 mb-3 px-1">
                    <div class="d-flex align-items-center p-2 rounded-3 shadow-sm date-subheader">
                        <span style="font-size: 1.1rem; margin-right: 8px;">📅</span> 
                        <h2 class="h6 mb-0">{{ date_str }}</h2>
                    </div>
                </div>
                {% endif %}
                
                {% for match in matches %}
                <div class="col-md-6 col-lg-6 col-xl-4 mb-3">
                    {{ match.html_card | safe }}
                </div>
                {% endfor %}
            {% endfor %}
        {% endif %}
    </div>
</div>

<script>
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('leagueSearchNavInput')?.addEventListener('input', function(e) {
            const text = e.target.value.toLowerCase();
            document.querySelectorAll('#leagueSearchList li').forEach(li => {
                const leagueName = li.textContent.toLowerCase();
                li.style.display = leagueName.includes(text) ? '' : 'none';
            });
        });

        document.querySelectorAll('.local-time-badge').forEach(badge => {
            const utcStr = badge.getAttribute('data-utc');
            if (utcStr) {
                const dt = new Date(utcStr);
                const day = new Intl.DateTimeFormat('en-US', { weekday: 'short' }).format(dt);
                let time = new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit', hour12: true }).format(dt).toLowerCase().replace(' ', '');
                badge.textContent = `${day} ${time}`;
            }
        });

        setInterval(pollAndUpdateDOM, 30000);
    });

    window.toggleSingleCard = function(fixId) {
        const fullView = document.getElementById(`full-${fixId}`);
        document.getElementById(`ribbon-${fixId}`)?.classList.toggle('d-none');
        fullView?.classList.toggle('d-none');
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

    function triggerCardGlow(cardEl, newestEventText) {
        if (!cardEl || !newestEventText) return;
        const text = newestEventText.toLowerCase();
        
        let glowClass = 'glow-goal'; 
        if (text.includes('🟥') || text.includes('red')) glowClass = 'glow-red-card';
        else if (text.includes('🟨') || text.includes('yellow')) glowClass = 'glow-yellow-card';
        else if (text.includes('🔄') || text.includes('sub')) glowClass = 'glow-subst';

        cardEl.classList.remove('glow-goal', 'glow-red-card', 'glow-yellow-card', 'glow-subst');
        void cardEl.offsetWidth;
        cardEl.classList.add(glowClass);
        setTimeout(() => { cardEl.classList.remove(glowClass); }, 4000);
    }
    async function pollAndUpdateDOM() {
        try {
            const res = await fetch(window.location.href, { cache: 'no-store' });
            if (!res.ok) return;
            const htmlText = await res.text();
            
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(htmlText, 'text/html');

            document.querySelectorAll('.lineup-card').forEach(currentCard => {
                const cardId = currentCard.id;
                if (!cardId) return;
                const fixId = cardId.replace('card-', '');
                const newCard = newDoc.getElementById(cardId);
                
                if (!newCard) return;

                if (currentCard.innerHTML === newCard.innerHTML) return;

                const currentEventsHtml = currentCard.querySelector(`#events-${fixId}`)?.innerHTML || '';
                const newEventsHtml = newCard.querySelector(`#events-${fixId}`)?.innerHTML || '';
                const hasNewEvent = currentEventsHtml !== newEventsHtml && newEventsHtml.trim() !== '';

                let newestEventText = '';
                if (hasNewEvent) {
                    const oldRows = Array.from(currentCard.querySelectorAll('.event-expanded .d-flex.align-items-start')).map(el => el.textContent);
                    const newRows = Array.from(newCard.querySelectorAll('.event-expanded .d-flex.align-items-start'));
                    for (let row of newRows) {
                        if (!oldRows.includes(row.textContent)) {
                            newestEventText = row.textContent;
                            break;
                        }
                    }
                }

                const isRibbonVisible = !currentCard.querySelector('.ribbon-view')?.classList.contains('d-none');
                const isFullVisible = !currentCard.querySelector('.full-view')?.classList.contains('d-none');
                const activeTab = currentCard.querySelector('.lineup-tab.active')?.id;

                currentCard.innerHTML = newCard.innerHTML;

                if (isRibbonVisible !== undefined && isFullVisible !== undefined) {
                    currentCard.querySelector('.ribbon-view')?.classList.toggle('d-none', !isRibbonVisible);
                    currentCard.querySelector('.full-view')?.classList.toggle('d-none', !isFullVisible);
                }
                if (activeTab) {
                    const tabName = activeTab.includes('stats') ? 'stats' : 'xi';
                    window.switchLineupTab(null, fixId, tabName);
                }

                if (newestEventText) {
                    triggerCardGlow(currentCard, newestEventText);
                }
            });
        } catch (err) {
            console.error("DOM update failed:", err);
        }
    }
</script>
</body>
</html>
"""

TEAM_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#212529">
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-WKSS7R4E02"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-WKSS7R4E02');
    </script>
    <title>{{ seo_title }}</title>
    <meta name="description" content="{{ seo_desc }}">
    <link class="canonical" href="https://futbolstartingeleven.com/teams/{{ team_slug }}/lineup/">
    
    <!-- Open Graph / Facebook -->
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Futbol Starting Eleven">
    <meta property="og:url" content="https://futbolstartingeleven.com/teams/{{ team_slug }}/lineup/">
    <meta property="og:title" content="{{ seo_title }}">
    <meta property="og:description" content="{{ seo_desc }}">
    <meta property="og:image" content="https://futbolstartingeleven.com/social-share1.png">

    <!-- Twitter -->
    <meta name="twitter:card" content="summary">
    <meta name="twitter:domain" content="futbolstartingeleven.com">
    <meta name="twitter:url" content="https://futbolstartingeleven.com/teams/{{ team_slug }}/lineup/">
    <meta name="twitter:title" content="{{ seo_title }}">
    <meta name="twitter:description" content="{{ seo_desc }}">
    <meta name="twitter:image" content="https://futbolstartingeleven.com/social-share1.png">

    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <style>
        body { background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .header-brand { font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; font-style: italic; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
        .header-brand a { color: inherit; }
        .header-brand span { text-shadow: none !important; background: linear-gradient(to bottom, #20c997 0%, #198754 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; filter: drop-shadow(0 0 12px rgba(32, 201, 151, 0.6)); }
    </style>
</head>
<body>

""" + BASE_HEADER + """

<div class="container mt-3 mb-2 text-center">
    <!-- League Banner Top -->
    <div class="mb-3 d-inline-flex align-items-center bg-white px-3 py-1 rounded-pill shadow-sm border">
        {{ league_logo_html | safe }}
        <span class="text-muted fw-bold text-uppercase" style="font-size: 0.75rem; letter-spacing: 0.5px;">{{ league_name }}</span>
    </div>
    
    <!-- Team Name with Inline Logo -->
    <div class="d-flex justify-content-center align-items-center mb-1">
        <img src="{{ team_logo }}" style="width: 45px; height: 45px; object-fit: contain; margin-right: 12px; filter: drop-shadow(0 2px 4px rgba(0,0,0,0.1));">
        <h1 class="h3 fw-bold text-dark mb-0">{{ team_name }} Lineup</h1>
    </div>
    
    <!-- Opponent and Date (Logo handled in Python logic) -->
    <h2 class="h6 text-muted mt-2 mb-3 d-flex justify-content-center align-items-center">{{ header_state | safe }}</h2>
</div>

<div class="container pb-5">
    <div class="row justify-content-center">
        <div class="col-12 col-md-8 col-lg-6">
            {{ pitch_html | safe }}
        </div>
    </div>
</div>

<script>
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('leagueSearchNavInput')?.addEventListener('input', function(e) {
            const text = e.target.value.toLowerCase();
            document.querySelectorAll('#leagueSearchList li').forEach(li => {
                const leagueName = li.textContent.toLowerCase();
                li.style.display = leagueName.includes(text) ? '' : 'none';
            });
        });
    });
</script>
</body>
</html>
"""

PLAYER_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-WKSS7R4E02"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-WKSS7R4E02');
    </script>
    <title>{{ seo_title }}</title>
    <meta name="description" content="{{ seo_desc }}">
    <meta name="robots" content="index, follow">
    <link class="canonical" href="https://futbolstartingeleven.com/players/{{ player_slug }}/">

    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    
    <style>
        body { background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow-x: hidden; }
        .header-brand { font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; font-style: italic; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }
        .header-brand a { color: inherit; }
        .header-brand span { text-shadow: none !important; background: linear-gradient(to bottom, #20c997 0%, #198754 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; filter: drop-shadow(0 0 12px rgba(32, 201, 151, 0.6)); }
        .profile-sidebar-card { background: #fff; border: 1px solid #dee2e6; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); padding: 24px; text-align: center; }
        .player-avatar-wrapper { position: relative; width: 110px; height: 110px; margin: 0 auto 15px auto; }
        .player-avatar { width: 100%; height: 100%; object-fit: cover; border-radius: 50%; border: 4px solid #20c997; background-color: #f8f9fa; }
        .sidebar-player-name { font-size: 1.4rem; font-weight: 800; color: #212529; margin-bottom: 2px; }
        .sidebar-player-meta { font-size: 0.8rem; font-weight: 700; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 20px; }
        .seo-link { color: inherit; text-decoration: none; transition: color 0.15s ease-in-out; }
        .sidebar-player-meta .seo-link:hover { color: #20c997; }
        .info-card { background: #fff; border: 1px solid #dee2e6; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); padding: 20px; margin-bottom: 24px; }
        .info-card h3 { font-size: 1rem; font-weight: 800; color: #212529; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #f1f3f5; text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f8f9fa; }
        .stat-row:last-child { border-bottom: none; }
        .stat-label { color: #6c757d; font-size: 0.85rem; font-weight: 600; }
        .stat-value { color: #212529; font-size: 0.9rem; font-weight: 700; text-align: right; }
        .table-responsive { border-radius: 8px; overflow-x: auto; border: 1px solid #dee2e6; width: 100%; }
        .table thead th { background-color: #212529; color: #fff; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; border: none; padding: 12px; white-space: nowrap; }
        .table tbody td { font-size: 0.85rem; font-weight: 600; color: #495057; padding: 12px; vertical-align: middle; border-bottom: 1px solid #f1f3f5; white-space: nowrap; }
        .table tbody tr:hover { background-color: #f8f9fa; }
        .big-stat-box { background: #f8f9fa; border-radius: 8px; padding: 12px; text-align: center; border: 1px solid #e9ecef; }
        .big-stat-value { font-size: 1.6rem; font-weight: 900; color: #198754; line-height: 1; }
        .big-stat-label { font-size: 0.7rem; font-weight: 700; color: #6c757d; text-transform: uppercase; margin-top: 5px; letter-spacing: 0.5px; }
        @keyframes pulse-green { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(32, 201, 151, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0); } }
        .live-dot { display: inline-block; width: 8px; height: 8px; background-color: #20c997; border-radius: 50%; margin-right: 6px; margin-bottom: 1px; animation: pulse-green 2s infinite; }
        @media (max-width: 576px) { .header-brand { font-size: 1.5rem; } }
    </style>
</head>
<body>

""" + BASE_HEADER + """

    <div class="container mb-5 mt-4">
        <div class="row g-4">
            <div class="col-lg-4">
                <div class="profile-sidebar-card">
                    <div class="player-avatar-wrapper">
                        <img src="{{ player_photo }}" alt="{{ player_name }}" class="player-avatar" onerror="this.onerror=null;this.src='https://a.espncdn.com/combiner/i?img=/i/headshots/nophoto.png';">
                    </div>
                    <div class="sidebar-player-name">{{ player_name }}</div>
                    <div class="sidebar-player-meta">
                        <a href="/teams/{{ team_slug }}/lineup/" class="seo-link fw-bold">{{ team_name }}</a> • <span>{{ position }}</span>
                        <div class="mt-3 d-flex justify-content-center align-items-center gap-2">
                            <span class="badge {{ badge_class }} py-2 px-3 fw-bold shadow-sm" style="font-size: 0.85rem; border-radius: 6px;">{{ badge_text }}</span>
                        </div>
                    </div>
                    <hr style="border-color: #dee2e6; opacity: 1; margin: 15px 0;">
                    <div class="text-start">
                        <div class="stat-row"><span class="stat-label">Team</span><span class="stat-value">{{ team_name }}</span></div>
                        <div class="stat-row"><span class="stat-label">Position</span><span class="stat-value">{{ position }}</span></div>
                    </div>
                </div>
            </div>

            <div class="col-lg-8">
                <div id="live-match-widget" class="info-card border-dark" style="border-left: 5px solid #212529; margin-bottom: 20px;">
                    {{ live_widget_html | safe }}
                </div>

                <div class="info-card">
                    <h3>Season Overview</h3>
                    <div class="row g-3">
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{{ season_stats.matches }}</div><div class="big-stat-label">{{ season_stats.label1 or 'Matches' }}</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{{ season_stats.goals }}</div><div class="big-stat-label">{{ season_stats.label2 or 'Goals' }}</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{{ season_stats.assists }}</div><div class="big-stat-label">{{ season_stats.label3 or 'Assists' }}</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{{ season_stats.shots }}</div><div class="big-stat-label">{{ season_stats.label4 or 'Shots' }}</div></div></div>
                    </div>
                </div>

                <div class="info-card">
                    <h3>Performance by Competition</h3>
                    <div class="table-responsive">
                        <table class="table table-borderless mb-0">
                            <thead>
                                <tr>
                                    <th>Competition</th>
                                    <th class="text-center">STRT</th>
                                    <th class="text-center">{{ comp_headers.col2 if comp_headers else 'Gls' }}</th>
                                    <th class="text-center">{{ comp_headers.col3 if comp_headers else 'Ast' }}</th>
                                    <th class="text-center">{{ comp_headers.col4 if comp_headers else 'Shots (SOG)' }}</th>
                                    <th class="text-center">Fouls (Com/Suf)</th>
                                    <th class="text-center">Offsides</th>
                                    <th class="text-center">Cards (Y/R)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% if competition_splits %}
                                    {% for comp in competition_splits %}
                                    <tr>
                                        <td><strong>{{ comp.competition }}</strong></td>
                                        <td class="text-center">{{ comp.strt }}</td>
                                        <td class="text-center">{{ comp.goals }}</td>
                                        <td class="text-center">{{ comp.assists }}</td>
                                        <td class="text-center">{{ comp.shots_sog }}</td>
                                        <td class="text-center">{{ comp.fouls }}</td>
                                        <td class="text-center">{{ comp.offsides }}</td>
                                        <td class="text-center">{{ comp.cards }}</td>
                                    </tr>
                                    {% endfor %}
                                {% else %}
                                    <tr><td colspan="8" class="text-center text-muted fst-italic py-3">Detailed season data currently unavailable.</td></tr>
                                {% endif %}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="info-card">
                    <h3>Recent Match Logs</h3>
                    <div class="table-responsive">
                        <table class="table table-borderless mb-0">
                            <thead>
                                <tr>
                                    <th>Date</th>
                                    <th>Opponent</th>
                                    <th class="text-center">Result</th>
                                    <th class="text-center">{{ log_headers.col1 if log_headers else 'App' }}</th>
                                    <th class="text-center">{{ log_headers.col2 if log_headers else 'Gls' }}</th>
                                    <th class="text-center">{{ log_headers.col3 if log_headers else 'Ast' }}</th>
                                    <th class="text-center">{{ log_headers.col4 if log_headers else 'Shots' }}</th>
                                    <th class="text-center">Cards (Y/R)</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% if match_gamelogs %}
                                    {% for log in match_gamelogs %}
                                    <tr>
                                        <td>{{ log.date }}</td>
                                        <td>
                                            {% if log.opp_logo %}
                                            <img src="{{ log.opp_logo }}" width="16" height="16" class="me-1" style="object-fit:contain;">
                                            {% endif %}
                                            {{ log.opponent }}
                                        </td>
                                        <td class="text-center">{{ log.result }}</td>
                                        <td class="text-center">{{ log.minutes }}</td>
                                        <td class="text-center">{{ log.goals }}</td>
                                        <td class="text-center">{{ log.assists }}</td>
                                        <td class="text-center">{{ log.shots }}</td>
                                        <td class="text-center">{{ log.cards }}</td>
                                    </tr>
                                    {% endfor %}
                                {% else %}
                                    <tr><td colspan="8" class="text-center text-muted fst-italic py-3">No recent game logs available.</td></tr>
                                {% endif %}
                            </tbody>
                        </table>
                    </div>
                </div>

            </div>
        </div>
    </div>

<script>
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('leagueSearchNavInput')?.addEventListener('input', function(e) {
            const text = e.target.value.toLowerCase();
            document.querySelectorAll('#leagueSearchList li').forEach(li => {
                const leagueName = li.textContent.toLowerCase();
                li.style.display = leagueName.includes(text) ? '' : 'none';
            });
        });
    });
    
    async function pollAndUpdateDOM() {
        try {
            const res = await fetch(window.location.href, { cache: 'no-store' });
            if (!res.ok) return;
            const htmlText = await res.text();
            
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(htmlText, 'text/html');
            
            const currentWidget = document.getElementById('live-match-widget');
            const newWidget = newDoc.getElementById('live-match-widget');
            if (currentWidget && newWidget && currentWidget.innerHTML !== newWidget.innerHTML) {
                currentWidget.innerHTML = newWidget.innerHTML;
            }
            
            const currentBadge = document.querySelector('.sidebar-player-meta .badge');
            const newBadge = newDoc.querySelector('.sidebar-player-meta .badge');
            if (currentBadge && newBadge && currentBadge.outerHTML !== newBadge.outerHTML) {
                currentBadge.outerHTML = newBadge.outerHTML;
            }
        } catch (err) {
            console.error("DOM update failed:", err);
        }
    }
    setInterval(pollAndUpdateDOM, 30000);
</script>
</body>
</html>
"""

def build_single_league_page(league_slug, league_data, matches, is_today, nav_html, today_date_str):
    league_dir = os.path.join('leagues', league_slug)
    os.makedirs(league_dir, exist_ok=True)
    
    league_name = league_data.get('name', 'League')
    
    if is_today:
        seo_title = f"Today's {league_name} Starting Lineups & Live Scores - {today_date_str}"
        page_h1 = f"Today's {league_name} Matches - {today_date_str}"
        seo_desc = f"Get real-time starting lineups, live scores, injuries, and betting odds for today's {league_name} matches on {today_date_str}."
        grouped_matches = {"Today": matches}
    else:
        seo_title = f"{league_name} Upcoming Match Schedule & Odds"
        page_h1 = f"{league_name} Upcoming Matches & Schedule"
        seo_desc = f"View the latest results, upcoming 14-day schedule, betting odds, and match info for the {league_name}."
        grouped_matches = {}
        for m in matches:
            date_raw = m['fixture'].get('date', '')
            try:
                dt = datetime.fromisoformat(date_raw.replace('Z', '+00:00'))
                dt_local = dt.astimezone(pytz.timezone('America/New_York'))
                date_header = dt_local.strftime('%A, %B %-d')
            except:
                date_header = "Upcoming"
                
            if date_header not in grouped_matches:
                grouped_matches[date_header] = []
            grouped_matches[date_header].append(m)

    # Generate schema only if it's the today version
    schema_json = generate_homepage_schema(matches) if is_today else ""

    template = Template(LEAGUE_HTML_TEMPLATE)
    output = template.render(
        seo_title=seo_title,
        seo_desc=seo_desc,
        page_h1=page_h1,
        league_slug=league_slug,
        league_name=league_name,
        is_today=is_today,
        grouped_matches=grouped_matches,
        nav_leagues_html=nav_html,
        schema_json=schema_json
    )
    
    with open(os.path.join(league_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(output)


def build_team_lineup_page(team_slug, team_data, match_data, is_home, nav_html, today_date_str, next_match_tuple=None):
    team_dir = os.path.join('teams', team_slug, 'lineup')
    os.makedirs(team_dir, exist_ok=True)
    
    team_name = team_data.get('name', 'Team')
    team_logo = team_data.get('logo', '')
    
    opp_side = 'away' if is_home else 'home'
    opp_name = match_data['teams'][opp_side]['name']
    opp_logo = match_data['teams'][opp_side]['logo']
    
    league_name = match_data.get('league', {}).get('name', 'Global Football')
    l_flag = match_data.get('league', {}).get('flag', '')
    
    if l_flag.startswith('http') or l_flag.startswith('/images/'):
        league_logo_html = f'<img src="{l_flag}" style="width: 20px; height: 20px; object-fit: contain; margin-right: 8px; border-radius: 2px;">'
    else:
        league_logo_html = f'<span style="font-size: 1.1rem; margin-right: 8px;">{l_flag}</span>'
    
    status_short = match_data['fixture']['status']['short']
    is_final = status_short in ['FT', 'AET', 'PEN']

    lineup = match_data.get('homeLineup') if is_home else match_data.get('awayLineup')
    formation_str = get_formation(lineup)
    
    if is_final:
        next_m, next_is_home = next_match_tuple if next_match_tuple else (None, False)
        if next_m:
            next_opp_side = 'away' if next_is_home else 'home'
            next_opp_name = next_m['teams'][next_opp_side]['name']
            next_opp_logo = next_m['teams'][next_opp_side]['logo']
            try:
                dt = datetime.fromisoformat(next_m['fixture']['date'].replace('Z', '+00:00'))
                dt_local = dt.astimezone(pytz.timezone('America/New_York'))
                date_str = dt_local.strftime('%a, %b %d • %I:%M%p').replace(' 0', ' ').lower()
            except:
                date_str = "Upcoming"
            header_state = f'Next Match: vs <img src="{next_opp_logo}" style="width:18px; height:18px; object-fit:contain; margin-bottom:2px; margin-right: 4px; margin-left: 4px;"> {next_opp_name} • {date_str}'
            seo_title = f"{team_name} Next Match & Starting Lineup vs {next_opp_name}"
            seo_desc = f"Upcoming starting lineup and match details for {team_name} vs {next_opp_name}."
        else:
            header_state = f'Last Match: vs <img src="{opp_logo}" style="width:18px; height:18px; object-fit:contain; margin-bottom:2px; margin-right: 4px; margin-left: 4px;"> {opp_name}'
            seo_title = f"{team_name} Starting Lineup - Tactical Formation"
            seo_desc = f"View the latest starting lineup and tactical formation for {team_name}."
    else:
        header_state = f'vs <img src="{opp_logo}" style="width:18px; height:18px; object-fit:contain; margin-bottom:2px; margin-right: 4px;"> {opp_name} • {today_date_str}'
        seo_title = f"{team_name} Starting Lineup vs {opp_name} - {today_date_str}"
        seo_desc = f"Official starting lineup and tactical formation for {team_name} vs {opp_name} on {today_date_str}."

    pitch_html = generate_pitch_html(lineup, '#333333', team_logo=team_logo, formation_str=formation_str)

    template = Template(TEAM_HTML_TEMPLATE)
    output = template.render(
        seo_title=seo_title,
        seo_desc=seo_desc,
        league_name=league_name,
        league_logo_html=league_logo_html,
        team_name=team_name,
        team_slug=team_slug,
        team_logo=team_logo,
        header_state=header_state,
        pitch_html=pitch_html,
        nav_leagues_html=nav_html
    )
    
    with open(os.path.join(team_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(output)


def build_single_player_page(player_slug, player_data, match_data, is_home, nav_html, today_date_str, next_match_tuple=None):
    player_dir = os.path.join('players', player_slug)
    os.makedirs(player_dir, exist_ok=True)
    
    p_name = player_data.get('name', 'Player')
    t_name = player_data.get('team_name', 'Team')
    t_slug = player_data.get('team_slug', '')
    
    POS_FULL_NAMES = {
        'F': 'Forward', 'FW': 'Forward', 'ST': 'Forward', 'CF': 'Forward', 'LW': 'Forward', 'RW': 'Forward',
        'M': 'Midfielder', 'MF': 'Midfielder', 'CM': 'Midfielder', 'AM': 'Midfielder', 'DM': 'Midfielder', 'CAM': 'Midfielder',
        'D': 'Defender', 'DF': 'Defender', 'CB': 'Defender', 'LB': 'Defender', 'RB': 'Defender', 'WB': 'Defender',
        'G': 'Goalkeeper', 'GK': 'Goalkeeper'
    }
    raw_pos = str(player_data.get('position', 'M')).upper()
    cat = get_position_category(raw_pos)
    p_pos = POS_FULL_NAMES.get(raw_pos) or POS_FULL_NAMES.get(cat, 'Midfielder')
    
    p_photo = player_data.get('photo') or 'https://a.espncdn.com/combiner/i?img=/i/headshots/nophoto.png'
    
    status_short = match_data['fixture']['status']['short'] if match_data and 'fixture' in match_data else 'NS'
    is_pre = status_short in ['NS', 'TBD']
    is_final = status_short in ['FT', 'AET', 'PEN']

    opp_side = 'away' if is_home else 'home'
    team_side = 'home' if is_home else 'away'
    opp_name = match_data['teams'][opp_side]['name'] if match_data and 'teams' in match_data else 'Opponent'
    
    if is_final:
        seo_title = f"{p_name} - Lineup Status, Stats & Profile | Futbol Starting Eleven"
        seo_desc = f"View performance stats and season overview for {p_name} ({t_name})."
    else:
        seo_title = f"Is {p_name} Starting Today? Lineup Status & Stats | Futbol Starting Eleven"
        seo_desc = f"Is {p_name} starting today for {t_name}? Get real-time starting lineup status, match performance stats, and position updates."
        
    lineup = match_data.get(team_side + 'Lineup') or {} if match_data else {}
    p_obj = None
    p_status = 'not_in_squad'
    
    for s in lineup.get('startXI', []):
        if str(s.get('player', {}).get('id')) == str(player_data['id']):
            p_obj = s.get('player', {})
            p_status = 'subbed_out' if p_obj.get('isSubbedOut') else 'on_pitch'
            break
            
    if not p_obj:
        for s in lineup.get('substitutes', []):
            if str(s.get('player', {}).get('id')) == str(player_data['id']):
                p_obj = s.get('player', {})
                if p_obj.get('isSubbedIn'):
                    p_status = 'subbed_out' if p_obj.get('isSubbedOut') else 'on_pitch'
                else:
                    p_status = 'bench'
                break
                
    has_lineups = bool(lineup.get('startXI'))
    if p_status == 'not_in_squad' and not has_lineups:
        p_status = 'pending'

    badge_class = "bg-secondary"
    badge_text = "Lineup Pending"
    if p_status == 'on_pitch':
        badge_class = "bg-success"
        badge_text = "In the Starting XI" if is_pre else "On Field"
    elif p_status == 'subbed_out':
        badge_class = "bg-secondary text-white"
        badge_text = "Off Field"
    elif p_status == 'bench':
        badge_class = "bg-warning text-dark"
        badge_text = "Bench"
    elif p_status == 'not_in_squad':
        badge_class = "bg-danger"
        badge_text = "Not in Squad"

    player_stats_html = ""
    if p_obj and not is_pre:
        ls = p_obj.get('live_stats', {})
        
        grps = {
            'F': {'s': ['G','A','xG','SOG'], 'k': ['goals','assists','xg','shots_on_target']},
            'M': {'s': ['G','A','PAS','DUEL'], 'k': ['goals','assists','accurate_passes','duels_won']},
            'D': {'s': ['G','DINT','TK','DUEL'], 'k': ['goals','dint','tackles','duels_won']},
            'G': {'s': ['SV','GA','xGA','SHF'], 'k': ['saves','conceded','xga','shots_faced']}
        }
        g = grps.get(cat, grps['M'])
        v1, v2, v3, v4 = ls.get(g['k'][0],0), ls.get(g['k'][1],0), ls.get(g['k'][2],0), ls.get(g['k'][3],0)
        
        minutes_played = ls.get('minutes', '-')
        if minutes_played == 0 and not is_pre:
            minutes_played = '-'

        player_stats_html = f'''
        <div class="mt-2 d-flex justify-content-end">
            <div class="d-flex align-items-center bg-light border rounded px-3 py-1 gap-3 shadow-sm">
                <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">MIN</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">{minutes_played}</div></div>
                <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">{g['s'][0]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">{v1}</div></div>
                <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">{g['s'][1]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">{v2}</div></div>
                <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">{g['s'][2]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">{v3}</div></div>
                <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">{g['s'][3]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">{v4}</div></div>
            </div>
        </div>
        '''

    header_class = "text-dark"
    live_indicator = ""
    elapsed = match_data['fixture']['status'].get('elapsed', '') if match_data and 'fixture' in match_data else ''
    
    if is_final:
        next_m, next_is_home = next_match_tuple if next_match_tuple else (None, False)
        if next_m:
            next_opp = next_m['teams']['away']['name'] if next_is_home else next_m['teams']['home']['name']
            try:
                dt = datetime.fromisoformat(next_m['fixture']['date'].replace('Z', '+00:00'))
                dt_local = dt.astimezone(pytz.timezone('America/New_York'))
                date_str = dt_local.strftime('%a, %b %d • %I:%M%p').replace(' 0', ' ').lower()
            except: date_str = "Upcoming"
            header_text = f"Next Match: vs {next_opp} • {date_str}"
            score_html = '<span class="mx-2 text-muted">vs</span>'
            h_team = next_m['teams']['home']
            a_team = next_m['teams']['away']
        else:
            header_text = "Match Finished"
            home_score = match_data['goals']['home']
            away_score = match_data['goals']['away']
            score_html = f'<span class="mx-3 fw-bold text-dark" style="font-size: 1.3rem;">{home_score} - {away_score}</span>'
            h_team = match_data['teams']['home']
            a_team = match_data['teams']['away']
    elif not is_pre:
        display_min = 'HT' if status_short == 'HT' else f"{elapsed}'"
        header_text = f"LIVE: {display_min}"
        header_class = "text-success"
        live_indicator = '<span class="live-dot"></span>'
        home_score = match_data['goals']['home']
        away_score = match_data['goals']['away']
        score_html = f'<span class="mx-3 fw-bold text-dark" style="font-size: 1.3rem;">{home_score} - {away_score}</span>'
        h_team = match_data['teams']['home']
        a_team = match_data['teams']['away']
    else:
        try:
            dt = datetime.fromisoformat(match_data['fixture']['date'].replace('Z', '+00:00'))
            dt_local = dt.astimezone(pytz.timezone('America/New_York'))
            time_str = dt_local.strftime("%I:%M%p").lstrip('0').lower()
            header_text = f"{dt_local.strftime('%a, %b %d')} • {time_str}"
        except: header_text = "Upcoming"
        score_html = '<span class="mx-2 text-muted">vs</span>'
        h_team = match_data['teams']['home']
        a_team = match_data['teams']['away']

    live_widget_html = f'''
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-3" style="width: 100%;">
        <div class="d-flex flex-column align-items-start">
            <span class="fw-bold {header_class} mb-1" style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center;">
                {live_indicator} {header_text}
            </span>
            <div class="d-flex align-items-center" style="font-size: 1rem; font-weight: 700;">
                <a href="/teams/{create_slug(h_team['name'])}/lineup/" class="text-decoration-none text-dark" style="color: inherit;">
                    <img src="{h_team.get('logo', '')}" width="18" height="18" class="me-1" style="object-fit:contain;">
                    {h_team['name']} 
                </a>
                {score_html} 
                <a href="/teams/{create_slug(a_team['name'])}/lineup/" class="text-decoration-none text-dark" style="color: inherit;">
                    <img src="{a_team.get('logo', '')}" width="18" height="18" class="me-1" style="object-fit:contain;">
                    {a_team['name']}
                </a>
            </div>
        </div>
        <div class="text-end">
            <div class="d-flex justify-content-end align-items-center gap-2">
                <a href="/teams/{t_slug}/lineup/" class="text-decoration-none fw-bold" style="font-size: 0.7rem; color: #6c757d;">View Lineup &rarr;</a>
            </div>
            {player_stats_html}
        </div>
    </div>
    '''

    player_stats_data = fetch_athlete_overview_and_gamelog(player_data.get('id'), position=cat)
    if player_stats_data.get('headshot') and ('nophoto' in p_photo or not p_photo):
        p_photo = player_stats_data['headshot']

    template = Template(PLAYER_HTML_TEMPLATE)
    output = template.render(
        seo_title=seo_title,
        seo_desc=seo_desc,
        player_slug=player_slug,
        player_photo=p_photo,
        player_name=p_name,
        team_name=t_name,
        team_slug=t_slug,
        position=p_pos,
        live_widget_html=live_widget_html,
        season_stats=player_stats_data["overview_totals"],
        competition_splits=player_stats_data["competition_splits"],
        match_gamelogs=player_stats_data["gamelogs"],
        comp_headers=player_stats_data.get("comp_headers"),
        log_headers=player_stats_data.get("log_headers"),
        nav_leagues_html=nav_html,
        badge_class=badge_class,
        badge_text=badge_text.upper()
    )
    
    with open(os.path.join(player_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(output)

def build_sitemaps(league_state, team_state, player_state):
    base_url = "https://futbolstartingeleven.com"
    now_iso = datetime.now(pytz.utc).isoformat(timespec='seconds')
    
    def format_w3c_date(timestamp):
        if not timestamp: return now_iso
        return datetime.fromtimestamp(timestamp, tz=pytz.utc).isoformat(timespec='seconds')

    print("\n🗺️ Generating XML Sitemaps...")

    # 1. Main Sitemap (Homepage)
    main_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>{base_url}/</loc>
        <lastmod>{now_iso}</lastmod>
    </url>
</urlset>'''
    with open("sitemap-main.xml", "w", encoding="utf-8") as f:
        f.write(main_xml)

    # 2. Leagues Sitemap
    leagues_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for slug, data in league_state.items():
        lmod = format_w3c_date(data.get('last_updated', 0))
        leagues_xml += f'    <url>\n        <loc>{base_url}/leagues/{slug}/</loc>\n        <lastmod>{lmod}</lastmod>\n    </url>\n'
    leagues_xml += '</urlset>'
    with open("sitemap-leagues.xml", "w", encoding="utf-8") as f:
        f.write(leagues_xml)

    # 3. Lineups (Teams) Sitemap
    lineups_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for slug, data in team_state.items():
        lmod = format_w3c_date(data.get('last_updated', 0))
        lineups_xml += f'    <url>\n        <loc>{base_url}/teams/{slug}/lineup/</loc>\n        <lastmod>{lmod}</lastmod>\n    </url>\n'
    lineups_xml += '</urlset>'
    with open("sitemap-lineups.xml", "w", encoding="utf-8") as f:
        f.write(lineups_xml)

    # 4. Players Sitemap
    players_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for slug, data in player_state.items():
        lmod = format_w3c_date(data.get('last_updated', 0))
        players_xml += f'    <url>\n        <loc>{base_url}/players/{slug}/</loc>\n        <lastmod>{lmod}</lastmod>\n    </url>\n'
    players_xml += '</urlset>'
    with open("sitemap-players.xml", "w", encoding="utf-8") as f:
        f.write(players_xml)

    # 5. Sitemap Index (The Master File)
    index_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <sitemap>
        <loc>{base_url}/sitemap-main.xml</loc>
        <lastmod>{now_iso}</lastmod>
    </sitemap>
    <sitemap>
        <loc>{base_url}/sitemap-leagues.xml</loc>
        <lastmod>{now_iso}</lastmod>
    </sitemap>
    <sitemap>
        <loc>{base_url}/sitemap-lineups.xml</loc>
        <lastmod>{now_iso}</lastmod>
    </sitemap>
    <sitemap>
        <loc>{base_url}/sitemap-players.xml</loc>
        <lastmod>{now_iso}</lastmod>
    </sitemap>
</sitemapindex>'''
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(index_xml)
        
    print(f"  └─ Successfully created sitemap.xml and 4 child maps.")

def ping_indexnow(changed_urls):
    if not changed_urls:
        return
        
    payload = {
        "host": "futbolstartingeleven.com",
        "key": "a3906b30a82f4301be25cdda8e63972b",
        "keyLocation": "https://futbolstartingeleven.com/a3906b30a82f4301be25cdda8e63972b.txt",
        "urlList": changed_urls
    }
    
    print(f"\n⚡ Pinging IndexNow with {len(changed_urls)} updated URLs...")
    try:
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        response = requests.post("https://api.indexnow.org/indexnow", json=payload, headers=headers, timeout=10)
        if response.status_code in [200, 202]:
            print("  └─ Successfully submitted to IndexNow.")
        else:
            print(f"  └─ ⚠️ IndexNow submission returned status {response.status_code}: {response.text}")
    except Exception as e:
        print(f"  └─ ⚠️ Failed to ping IndexNow: {e}")

def generate_homepage_schema(today_matches):
    schema_list = []
    
    for m in today_matches:
        home_name = m['teams']['home']['name']
        away_name = m['teams']['away']['name']
        match_date = m['fixture'].get('date', '')
        status_short = m['fixture']['status']['short']
        
        # Map your custom status to Schema.org EventStatus
        if status_short in ['NS', 'TBD']:
            event_status = "https://schema.org/EventScheduled"
        elif status_short in ['PST', 'CANC', 'ABD']:
            event_status = "https://schema.org/EventCancelled"
        elif status_short in ['FT', 'AET', 'PEN']:
            event_status = "https://schema.org/EventMovedOnline" # Sometimes used as a fallback, but generally EventPostponed or similar. Better yet, omit or use standard.
            # Actually, standard for finished is EventScheduled in the past, or we just let Google infer from the date. 
            # A more accurate mapping for finished events is leaving it as EventScheduled but date is past. 
            event_status = "https://schema.org/EventScheduled" 
        else:
            # LIVE
            event_status = "https://schema.org/EventScheduled" # Google uses EventScheduled for live events as well, relying on the startDate.

        event_schema = {
            "@context": "https://schema.org",
            "@type": "SportsEvent",
            "name": f"{home_name} vs {away_name}",
            "sport": "Soccer",
            "startDate": match_date,
            "eventStatus": event_status,
            "homeTeam": {
                "@type": "SportsOrganization",
                "name": home_name
            },
            "awayTeam": {
                "@type": "SportsOrganization",
                "name": away_name
            }
        }
        schema_list.append(event_schema)
        
    # Wrap the list in a script tag
    if not schema_list:
        return ""
        
    json_string = json.dumps(schema_list, indent=2, ensure_ascii=False)
    return f'<script type="application/ld+json">\n{json_string}\n</script>'

# ====================================================================
# MAIN GENERATOR PIPELINE
# ====================================================================
def generate_v2_index():
    script_start_time = datetime.now().timestamp()
    
    print("\n==================================================")
    print("⏳ STARTING SSG BUILD PIPELINE & LEAGUE/TEAM/PLAYER GENERATOR")
    print("==================================================")

    # 1. HYDRATE CORE DIRECTORY ONCE AT STARTUP
    core_index = build_hydrated_core_index()
    
    os.makedirs('data', exist_ok=True)
    file_path = 'index.html'
    old_html = ""
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f: old_html = f.read()

    day_info = get_3day_dates()
    
    # Pass core_index to all daily fetches in parallel
    dates_to_fetch = [
        ("yesterday", day_info["dates"]["yesterday"], False),
        ("today", day_info["dates"]["today"], True),
        ("tomorrow", day_info["dates"]["tomorrow"], False)
    ]
    raw_matches_by_day = {}
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_day = {
            executor.submit(
                fetch_espn_scores_for_date, 
                d_str, old_html, None, None, is_today, core_index
            ): day_key
            for day_key, d_str, is_today in dates_to_fetch
        }
        for future in as_completed(future_to_day):
            day_key = future_to_day[future]
            try:
                raw_matches_by_day[day_key] = future.result()
            except Exception as e:
                print(f"❌ Error fetching {day_key} scoreboard: {e}")
                raw_matches_by_day[day_key] = []

    all_active_matches = raw_matches_by_day['yesterday'] + raw_matches_by_day['today'] + raw_matches_by_day['tomorrow']

    # 2. Sync Registries & Generate Global HTML Dropdown
    state, state_file = sync_league_state(all_active_matches)
    team_state, team_state_file = sync_team_state(all_active_matches)
    player_state, player_state_file = sync_player_state(all_active_matches)
    nav_html = generate_nav_leagues_html(state)
    
    # 3. Generate Active League Pages instantly from memory
    combined_active_leagues = {}
    for m in all_active_matches:
        slug = m.get('league', {}).get('slug')
        if not slug: continue
        if slug not in combined_active_leagues:
            combined_active_leagues[slug] = []
        if m['fixture']['id'] not in [x['fixture']['id'] for x in combined_active_leagues[slug]]:
            combined_active_leagues[slug].append(m)

    today_slugs = {lg['slug'] for lg in group_and_sort_matches_by_league(raw_matches_by_day['today'])}
    yesterday_slugs = {lg['slug'] for lg in group_and_sort_matches_by_league(raw_matches_by_day['yesterday'])}
    active_slugs = set()
    
    for slug, matches in combined_active_leagues.items():
        active_slugs.add(slug)
        if slug in state:
            matches.sort(key=lambda x: (x.get('fixture') or {}).get('date', '9999-99-99') or '9999-99-99')
            is_today_treatment = slug in today_slugs
            
            if is_today_treatment:
                today_matches_for_league = [m for m in raw_matches_by_day['today'] if m.get('league', {}).get('slug') == slug]
                build_single_league_page(
                    slug, state[slug], today_matches_for_league, 
                    is_today=True, nav_html=nav_html, 
                    today_date_str=day_info["display"]["today"]
                )
            else:
                build_single_league_page(
                    slug, state[slug], matches, 
                    is_today=False, nav_html=nav_html, 
                    today_date_str=""
                )
            state[slug]['last_updated'] = datetime.now().timestamp()

    # 3b. 14-Day Schedule Fetch for Yesterday's Completed Leagues (Crossover Refresh)
    leagues_needing_schedule = yesterday_slugs - today_slugs
    fourteen_day_lookahead_matches = []
    crossovers_actually_refreshed = 0
    
    # Establish today's date strings once
    est = pytz.timezone('America/New_York')
    now = datetime.now(est)
    current_date_str = now.strftime('%Y-%m-%d')
    start_date = now.strftime('%Y%m%d')
    end_date = (now + timedelta(days=14)).strftime('%Y%m%d')

    for slug in leagues_needing_schedule:
        if slug in state and state[slug].get('pill'):
            
            # Check the gatekeeper: Did we already fetch this league today?
            if state[slug].get('last_crossover_date') != current_date_str:
                print(f"🔄 CROSSOVER: Fetching 14-day schedule for completed yesterday league -> {state[slug]['name']}")
                crossovers_actually_refreshed += 1
                
                l_matches = fetch_espn_scores_for_date(
                    start_date, "", pill=state[slug]['pill'], end_date_str=end_date, is_today_partition=False, core_index=core_index
                )
                if l_matches:
                    fourteen_day_lookahead_matches.extend(l_matches)
                    sync_team_state(l_matches)
                    sync_player_state(l_matches)
                    build_single_league_page(
                        slug, state[slug], l_matches, 
                        is_today=False, nav_html=nav_html, today_date_str=""
                    )
                    state[slug]['last_updated'] = datetime.now().timestamp()
                
                # Save the flag to site_pages.json state to skip future runs today
                state[slug]['last_crossover_date'] = current_date_str
            else:
                print(f"⏭️ SKIPPING CROSSOVER: Already fetched today for -> {state[slug]['name']}")

    # Pool upcoming matches for Next Match lookups
    upcoming_pool = raw_matches_by_day['tomorrow'] + fourteen_day_lookahead_matches

    # 3c. Squad Auto-Discovery & Immediate Player Page Generation
    print(f"🔄 Running Squad Auto-Discovery & Immediate Player Page Generation...")
    all_matches_for_squads = all_active_matches + fourteen_day_lookahead_matches
    sync_team_squads(all_matches_for_squads, team_state, player_state, upcoming_pool, nav_html, day_info, league_state=state)

    # 4. Update Team & Player Pages for Active Slate (Today + Crossover Yesterday Matches)
    print(f"🔄 Updating Team Lineups and Player Profiles (Today + Yesterday Crossover)...")
    
    matches_to_process = raw_matches_by_day['yesterday'] + raw_matches_by_day['today']
    
    for m in matches_to_process:
        match_id = str(m['fixture']['id'])
        status_short = m['fixture']['status']['short']
        is_ft = (status_short in ['FT', 'AET', 'PEN'])
        is_live = status_short not in ['FT', 'AET', 'PEN', 'NS', 'TBD', 'PST', 'CANC', 'ABD']
        
        for side in ['home', 'away']:
            team_info = m['teams'][side]
            t_slug = create_slug(team_info['name'])
            
            # TEAM GENERATION
            if t_slug in team_state:
                t_data = team_state[t_slug]
                time_since_update = datetime.now().timestamp() - t_data.get('last_updated', 0)
                
                needs_update = False
                if t_data.get('last_match_id') != match_id:
                    needs_update = True
                elif is_live:
                    needs_update = True
                elif is_ft and not t_data.get('is_final'):
                    needs_update = True
                elif time_since_update > 300 and not is_ft: # 5 min throttle for pre-game/postponed
                    needs_update = True
                
                if needs_update:
                    # CHECK: Prevent overwriting a good lineup with a blank one.
                    # Bypassed ONLY if it's a brand new match OR if the match is Full Time AND is no longer on today's schedule.
                    is_new_match = (t_data.get('last_match_id') != match_id)
                    is_past_ft = (is_ft and not m.get('is_today_partition'))
                    
                    if not is_new_match and not is_past_ft:
                        current_lineup = m.get(side + 'Lineup')
                        has_new_lineup = bool(current_lineup and current_lineup.get('startXI'))
                        
                        index_file = os.path.join('teams', t_slug, 'lineup', 'index.html')
                        page_already_has_lineup = False
                        
                        if os.path.exists(index_file):
                            try:
                                with open(index_file, 'r', encoding='utf-8') as f:
                                    if "Awaiting Live Lineup Data" not in f.read():
                                        page_already_has_lineup = True
                            except: pass
                            
                        # If the page has a lineup, and the API payload is empty, preserve the page!
                        if page_already_has_lineup and not has_new_lineup:
                            t_data['last_updated'] = datetime.now().timestamp()
                            continue
                            
                    next_match_tuple = find_next_fixture_for_entity(t_slug, upcoming_pool) if is_ft else (None, False)
                    
                    build_team_lineup_page(
                        t_slug, t_data, m, 
                        is_home=(side=='home'), 
                        nav_html=nav_html, 
                        today_date_str=day_info["display"]["today"],
                        next_match_tuple=next_match_tuple
                    )
                    t_data['last_updated'] = datetime.now().timestamp()
                    t_data['last_match_id'] = match_id
                    t_data['is_final'] = is_ft

            # PLAYER GENERATION
            lineup = m.get(side + 'Lineup')
            if lineup:
                roster = []
                if lineup.get('startXI'): roster.extend(lineup['startXI'])
                if lineup.get('substitutes'): roster.extend(lineup['substitutes'])
                
                for s_obj in roster:
                    p_info = s_obj.get('player', {})
                    pid = str(p_info.get('id', ''))
                    pname = p_info.get('name', '')
                    if pid and pname:
                        p_slug = f"{create_slug(pname)}-{pid}"
                        
                        if p_slug in player_state:
                            p_data = player_state[p_slug]
                            time_since_update = datetime.now().timestamp() - p_data.get('last_updated', 0)
                            
                            needs_update = False
                            if p_data.get('last_match_id') != match_id:
                                needs_update = True
                            elif is_live:
                                needs_update = True
                            elif is_ft and not p_data.get('is_final'):
                                needs_update = True
                            elif time_since_update > 300 and not is_ft: # 5 min throttle for pre-game/postponed
                                needs_update = True
                            
                            if needs_update:
                                next_match_tuple = find_next_fixture_for_entity(t_slug, upcoming_pool) if is_ft else (None, False)
                                
                                build_single_player_page(
                                    p_slug, p_data, m, 
                                    is_home=(side=='home'), 
                                    nav_html=nav_html, 
                                    today_date_str=day_info["display"]["today"],
                                    next_match_tuple=next_match_tuple
                                )
                                p_data['last_updated'] = datetime.now().timestamp()
                                p_data['last_match_id'] = match_id
                                p_data['is_final'] = is_ft

    # 5. Generate ONE Dormant League (14-Day Trickle Round Robin)
    dormant_leagues = [s for s, d in state.items() if s not in active_slugs and d.get('pill')]
    if dormant_leagues:
        dormant_leagues.sort(key=lambda s: state[s].get('last_updated', 0))
        target_slug = dormant_leagues[0]
        target_data = state[target_slug]
        
        print(f"🔄 TRICKLE UPDATE: Fetching 14-day schedule for dormant league -> {target_data['name']}")
        
        est = pytz.timezone('America/New_York')
        now = datetime.now(est)
        start_date = now.strftime('%Y%m%d')
        end_date = (now + timedelta(days=14)).strftime('%Y%m%d')
        
        fourteen_day_matches = fetch_espn_scores_for_date(
            start_date, "", pill=target_data['pill'], end_date_str=end_date, is_today_partition=False, core_index=core_index
        )
        if fourteen_day_matches:
            sync_team_state(fourteen_day_matches)
            sync_player_state(fourteen_day_matches)
            sync_team_squads(fourteen_day_matches, team_state, player_state, upcoming_pool, nav_html, day_info, league_state=state)
            
        build_single_league_page(
            target_slug, target_data, fourteen_day_matches, 
            is_today=False, nav_html=nav_html, today_date_str=""
        )
        state[target_slug]['last_updated'] = datetime.now().timestamp()

    # 5b. Silent Player Background Trickle Update (Batch Size: 5 dormant players per run)
    active_player_ids = set()
    for m in matches_to_process:
        for side in ['home', 'away']:
            lineup = m.get(side + 'Lineup') or {}
            for entry in (lineup.get('startXI', []) + lineup.get('substitutes', [])):
                p_id = str(entry.get('player', {}).get('id', ''))
                if p_id: active_player_ids.add(p_id)

    dormant_players = [
        (p_slug, p_data) for p_slug, p_data in player_state.items()
        if str(p_data.get('id')) not in active_player_ids
    ]
    if dormant_players:
        dormant_players.sort(key=lambda x: x[1].get('last_updated', 0))
        target_players = dormant_players[:5]
        print(f"🔄 SILENT TRICKLE: Refreshing 5 dormant player profiles...")
        for p_slug, p_data in target_players:
            t_slug = p_data.get('team_slug', '')
            next_m, next_is_home = find_next_fixture_for_entity(t_slug, upcoming_pool)
            dummy_match = next_m if next_m else {
                "fixture": {"status": {"short": "FT"}},
                "teams": {"home": {"name": p_data.get('team_name', 'Team')}, "away": {"name": "Opponent"}},
                "goals": {"home": 0, "away": 0}
            }
            build_single_player_page(
                p_slug, p_data, dummy_match, 
                is_home=next_is_home, 
                nav_html=nav_html, 
                today_date_str=day_info["display"]["today"],
                next_match_tuple=(next_m, next_is_home) if next_m else None
            )
            p_data['last_updated'] = datetime.now().timestamp()

    # Save Registry States
    with open(state_file, 'w', encoding='utf-8') as f: json.dump(state, f, indent=2, ensure_ascii=False)
    with open(team_state_file, 'w', encoding='utf-8') as f: json.dump(team_state, f, indent=2, ensure_ascii=False)
    with open(player_state_file, 'w', encoding='utf-8') as f: json.dump(player_state, f, indent=2, ensure_ascii=False)
    
    # Save Player Stats Cache
    with open('data/player_cache.json', 'w', encoding='utf-8') as f: json.dump(PLAYER_STATS_CACHE, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # NEW: GENERATE DAILY LINEUPS JSON FOR TWEET BOT WITH PLAYERS
    # -------------------------------------------------------------------------
    print("🔄 Generating daily_lineups.json for the Tweet Bot...")
    daily_lineups = {}
    
    # Establish today's date for the unique keys (respecting the 3 AM EST crossover)
    est_tz = pytz.timezone('America/New_York')
    now_est = datetime.now(est_tz)
    if now_est.hour < 3: 
        now_est -= timedelta(days=1)
    iso_today = now_est.strftime('%Y-%m-%d')

    def extract_starting_xi(lineup_data):
        """Extracts starting XI sorted with Goalkeeper (G) first, then D, M, F."""
        if not lineup_data or not lineup_data.get('startXI'):
            return []
        
        players = []
        for s in lineup_data['startXI']:
            p = s.get('player', {})
            if not p: continue
            
            p_name = p.get('name', 'Unknown')
            pos = p.get('pos', 'M')
            cat = p.get('category', get_position_category(pos))
            
            players.append({
                "name": p_name,
                "short_name": shorten_player_name(p_name),
                "pos": pos,
                "category": cat,
                "number": str(p.get('number', ''))
            })
            
        # Category weights ensure Goalkeeper (G) is always first
        category_weights = {'G': 0, 'D': 1, 'M': 2, 'F': 3}
        players.sort(key=lambda x: category_weights.get(x['category'], 4))
        return players

    def is_valid_starting_xi(xi_players):
        """Validates that a starting XI has exactly 11 players with proper pitch positions."""
        # 1. Must have exactly 11 starting players
        if len(xi_players) != 11:
            return False
            
        valid_categories = {'G', 'D', 'M', 'F'}
        has_gk = False
        
        for p in xi_players:
            cat = p.get('category')
            pos = str(p.get('pos', '')).strip().upper()
            
            # 2. Reject unassigned positions, sub tags, or broken entries
            if cat not in valid_categories or pos in ['SUB', 'S', 'SUBSTITUTE', '', 'UNKNOWN', 'NONE']:
                return False
                
            if cat == 'G':
                has_gk = True
                
        # 3. Must have at least 1 designated goalkeeper
        if not has_gk:
            return False
            
        return True

    for m in raw_matches_by_day['today']:
        home_lineup = m.get('homeLineup')
        away_lineup = m.get('awayLineup')
        
        fixture_id = str(m['fixture'].get('id', ''))
        home_name = m['teams']['home']['name']
        away_name = m['teams']['away']['name']
        home_slug = create_slug(home_name)
        away_slug = create_slug(away_name)
        
        league_name_raw = m['league'].get('name', '')
        l_flag = str(m['league'].get('flag', ''))
        
        emoji_flag = ""
        if l_flag and not l_flag.startswith('http') and not l_flag.startswith('/images/'):
            emoji_flag = l_flag
        elif "ca.png" in l_flag or "canadian" in league_name_raw.lower() or "northern super" in league_name_raw.lower():
            emoji_flag = "🇨🇦"
            
        league_name = f"{emoji_flag} {league_name_raw}" if emoji_flag else league_name_raw
        league_hashtag = f"#{league_name_raw.replace(' ', '')}"

        # Extract & Validate Home Lineup
        home_xi = extract_starting_xi(home_lineup)
        if is_valid_starting_xi(home_xi):
            home_key = f"{fixture_id}_{home_slug}_{iso_today}"
            daily_lineups[home_key] = {
                "fixture_id": fixture_id,
                "date": iso_today,
                "team_name": home_name,
                "team_slug": home_slug,
                "lineup_url": f"https://futbolstartingeleven.com/teams/{home_slug}/lineup/",
                "opponent_name": away_name,
                "opponent_slug": away_slug,
                "side": "home",
                "league_name": league_name,
                "league_hashtag": league_hashtag,
                "formation": get_formation(home_lineup),
                "starting_xi": home_xi
            }

        # Extract & Validate Away Lineup
        away_xi = extract_starting_xi(away_lineup)
        if is_valid_starting_xi(away_xi):
            away_key = f"{fixture_id}_{away_slug}_{iso_today}"
            daily_lineups[away_key] = {
                "fixture_id": fixture_id,
                "date": iso_today,
                "team_name": away_name,
                "team_slug": away_slug,
                "lineup_url": f"https://futbolstartingeleven.com/teams/{away_slug}/lineup/",
                "opponent_name": home_name,
                "opponent_slug": home_slug,
                "side": "away",
                "league_name": league_name,
                "league_hashtag": league_hashtag,
                "formation": get_formation(away_lineup),
                "starting_xi": away_xi
            }
            
    with open('data/daily_lineups.json', 'w', encoding='utf-8') as f:
        json.dump(daily_lineups, f, indent=2, ensure_ascii=False)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # NEW: GENERATE DAILY GOALS JSON FOR TWEET BOT SCENARIOS
    # -------------------------------------------------------------------------
    print("🔄 Generating daily_goals.json for the Tweet Bot...")
    daily_goals = {}
    
    def get_actual_minute(time_str):
        t_str = str(time_str).replace("'", "").strip()
        if '+' in t_str:
            parts = t_str.split('+')
            try: return int(parts[0]) + int(parts[1])
            except: return int(parts[0]) if parts[0].isdigit() else 90
        return int(t_str) if t_str.isdigit() else 0

    def get_decimal_odds(american_str):
        if not american_str or american_str == 'TBD': return 0.0
        try:
            val = int(str(american_str).replace('+', ''))
            if val > 0: return (val / 100.0) + 1.0
            elif val < 0: return (100.0 / abs(val)) + 1.0
        except: pass
        return 0.0

    for m in raw_matches_by_day['today'] + raw_matches_by_day['yesterday']:
        events = m.get('events', [])
        # Include all goal variations, filter out substitutions or cards
        goal_events = [e for e in events if e.get('type') == 'Goal' and e.get('detail') in ['Normal Goal', 'Penalty', 'Own Goal', 'Goal']]
        if not goal_events: continue
        
        # Sort chronologically by the actual minute
        goal_events.sort(key=lambda x: get_actual_minute(x.get('time', '0')))
        
        fixture_id = str(m['fixture'].get('id', ''))
        match_date = m['fixture'].get('date', iso_today)[:10]
        
        h_id = str(m['teams']['home']['id'])
        a_id = str(m['teams']['away']['id'])
        h_name = m['teams']['home']['name']
        a_name = m['teams']['away']['name']
        
        home_odds_dec = get_decimal_odds(m.get('odds', {}).get('home', 'TBD'))
        away_odds_dec = get_decimal_odds(m.get('odds', {}).get('away', 'TBD'))
        
        league_name_raw = m['league'].get('name', '')
        l_flag = str(m['league'].get('flag', ''))
        
        # Map emojis for tweet payloads even when using image flags on the site
        emoji_flag = ""
        if l_flag and not l_flag.startswith('http') and not l_flag.startswith('/images/'):
            emoji_flag = l_flag
        elif "ca.png" in l_flag or "canadian" in league_name_raw.lower() or "northern super" in league_name_raw.lower():
            emoji_flag = "🇨🇦"
            
        if emoji_flag:
            league_name = f"{emoji_flag} {league_name_raw}"
        else:
            league_name = league_name_raw
            
        league_slug = m['league'].get('slug', '')
        league_hashtag = f"#{league_name_raw.replace(' ', '')}"
        
        current_home_score = 0
        current_away_score = 0
        player_goal_counts = {}
        
        for event in goal_events:
            event_time = get_actual_minute(event.get('time', '0'))
            team_id = str(event.get('team_id', ''))
            
            if team_id == h_id: current_home_score += 1
            else: current_away_score += 1
            
            p_name = event.get('player', 'Unknown')
            if not p_name or p_name.lower() == 'null': continue
            
            # Simple hash fallback if player_id is missing from ESPN's event payload
            p_id = event.get('player_id') or create_slug(p_name)
            
            player_goal_counts[p_id] = player_goal_counts.get(p_id, 0) + 1
            p_goals = player_goal_counts[p_id]
            
            # Scenario Logic Calculations
            is_stoppage = event_time >= 90
            is_late = 75 <= event_time < 90
            is_equalizer = current_home_score == current_away_score
            is_go_ahead = (team_id == h_id and current_home_score - current_away_score == 1) or (team_id == a_id and current_away_score - current_home_score == 1)
            
            # FIXED: Only True if the SCORING team is extending their lead
            is_two_goal_lead = (team_id == h_id and current_home_score - current_away_score == 2) or (team_id == a_id and current_away_score - current_home_score == 2)
            is_blowout = (team_id == h_id and current_home_score - current_away_score >= 3) or (team_id == a_id and current_away_score - current_home_score >= 3)
            
            # NEW: True if the SCORING team is still trailing by 2 or more goals AFTER the goal
            is_consolation = (team_id == h_id and current_away_score - current_home_score >= 2) or (team_id == a_id and current_home_score - current_away_score >= 2)
            
            scorer_odds = home_odds_dec if team_id == h_id else away_odds_dec
            is_standard_upset = is_go_ahead and (4.00 <= scorer_odds < 7.00)
            is_massive_upset = is_go_ahead and (scorer_odds >= 7.00)
            is_tight_clash = abs(current_home_score - current_away_score) <= 1
            
            scenario_key = "standard_goal" # Default Fallback
            if p_goals == 3: scenario_key = "hat_trick"
            elif p_goals == 2: scenario_key = "brace"
            elif is_stoppage and (is_standard_upset or is_massive_upset): scenario_key = "stoppage_upset"
            elif is_late and (is_standard_upset or is_massive_upset): scenario_key = "late_upset"
            elif is_stoppage and is_go_ahead: scenario_key = "stoppage_go_ahead"
            elif is_stoppage and is_equalizer: scenario_key = "stoppage_equalizer"
            elif is_late and is_go_ahead: scenario_key = "late_go_ahead"
            elif is_late and is_equalizer: scenario_key = "late_equalizer"
            elif event_time <= 10: scenario_key = "lightning_start"
            elif is_massive_upset: scenario_key = "massive_upset"
            elif is_standard_upset: scenario_key = "standard_upset"
            elif is_blowout: scenario_key = "blowout"
            elif is_consolation: scenario_key = "consolation_goal"  # <--- ADDED HERE
            elif is_two_goal_lead: scenario_key = "takes_control"
            elif event_time > 10 and is_tight_clash: scenario_key = "tight_clash_goal"
            
            scoring_team_name = h_name if team_id == h_id else a_name
            conceding_team_name = a_name if team_id == h_id else h_name
            american_odds_str = m.get('odds', {}).get('home', 'TBD') if team_id == h_id else m.get('odds', {}).get('away', 'TBD')
            
            # Deterministic unique key ensuring no duplicate tweets
            goal_key = f"GOAL_{fixture_id}_{team_id}_{event_time}_{p_id}"
            
            daily_goals[goal_key] = {
                "fixture_id": fixture_id,
                "date": match_date,
                "timestamp": int(time.time()),
                "minute": event_time,
                "display_minute": event.get('time', str(event_time)),
                "team_id": team_id,
                "scoring_team": scoring_team_name,
                "conceding_team": conceding_team_name,
                "home_team": h_name,
                "away_team": a_name,
                "scorer": p_name,
                "assist": event.get('assist', ''),
                "is_own_goal": event.get('detail') == 'Own Goal',
                "home_score": current_home_score,
                "away_score": current_away_score,
                "scenario": scenario_key,
                "american_odds": american_odds_str,
                "league_name": league_name,
                "league_hashtag": league_hashtag,
                "match_url": f"https://futbolstartingeleven.com/leagues/{league_slug}/#match-{fixture_id}"
            }
            
    with open('data/daily_goals.json', 'w', encoding='utf-8') as f:
        json.dump(daily_goals, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # NEW: GENERATE GAME SUMMARY JSON FOR TWEET BOT (FULL-TIME RECAPS)
    # -------------------------------------------------------------------------
    print("🔄 Generating game_summary.json for the Tweet Bot...")
    game_summaries = {}
    summary_file_path = 'data/game_summary.json'
    
    # 1. Load existing summaries for O(1) deduplication
    if os.path.exists(summary_file_path):
        try:
            with open(summary_file_path, 'r', encoding='utf-8') as f:
                game_summaries = json.load(f)
        except Exception as e:
            print(f"  └─ ⚠️ Could not read existing {summary_file_path}: {e}")
            game_summaries = {}

    # 2. 48-Hour Pruning (Keep memory/file size microscopic)
    now_ts = int(time.time())
    forty_eight_hours_sec = 48 * 3600
    game_summaries = {
        fid: data for fid, data in game_summaries.items()
        if (now_ts - data.get('created_at', now_ts)) < forty_eight_hours_sec
    }

    # Helper function to convert American odds to Decimal
    def parse_decimal_odds(american_str):
        if not american_str or american_str == 'TBD': return 0.0
        try:
            val = int(str(american_str).replace('+', ''))
            if val > 0: return (val / 100.0) + 1.0
            elif val < 0: return (100.0 / abs(val)) + 1.0
        except: pass
        return 0.0

    # 3. Process Today's and Yesterday's Completed Matches
    new_summaries_count = 0
    for m in raw_matches_by_day['today'] + raw_matches_by_day['yesterday']:
        status_short = str((m.get('fixture', {}) or {}).get('status', {}).get('short', '')).upper()
        
        # Only process finalized matches
        if status_short not in ['FT', 'AET', 'PEN']:
            continue

        fixture_id = str(m['fixture'].get('id', ''))
        if not fixture_id or fixture_id in game_summaries:
            continue  # Instant O(1) skip if already recorded

        h_id = str(m['teams']['home']['id'])
        a_id = str(m['teams']['away']['id'])
        h_name = m['teams']['home']['name']
        a_name = m['teams']['away']['name']
        h_score = int((m.get('goals') or {}).get('home', 0))
        a_score = int((m.get('goals') or {}).get('away', 0))

        # Build clean Goalscorer Strings (with Assists and Own Goals)
        events = m.get('events', [])
        goal_events = [e for e in events if e.get('type') == 'Goal' and e.get('detail') in ['Normal Goal', 'Penalty', 'Own Goal', 'Goal']]
        
        # Sort goals chronologically
        goal_events.sort(key=lambda x: get_actual_minute(x.get('time', '0')))
        
        home_scorers = []
        away_scorers = []
        
        for ge in goal_events:
            p_name = ge.get('player', 'Unknown')
            if not p_name or p_name.lower() == 'null':
                continue
            
            p_short = shorten_player_name(p_name)
            time_str = ge.get('time', "0'")
            if not time_str.endswith("'"): time_str = f"{time_str}'"
            
            detail = ge.get('detail', '')
            assist_name = ge.get('assist', '')
            
            # Format individual entry
            if detail == 'Own Goal':
                entry = f"{p_short} {time_str} (OG)"
            elif assist_name:
                entry = f"{p_short} {time_str} (Ast: {shorten_player_name(assist_name)})"
            else:
                entry = f"{p_short} {time_str}"
                
            if str(ge.get('team_id')) == h_id:
                home_scorers.append(entry)
            else:
                away_scorers.append(entry)

        # Odds context
        h_odds_str = m.get('odds', {}).get('home', 'TBD')
        a_odds_str = m.get('odds', {}).get('away', 'TBD')
        d_odds_str = m.get('odds', {}).get('draw', 'TBD')
        h_dec_odds = parse_decimal_odds(h_odds_str)
        a_dec_odds = parse_decimal_odds(a_odds_str)

        # Match outcome logic
        if h_score > a_score:
            outcome = "home_win"
            winner_name = h_name
            loser_name = a_name
            is_upset = (h_dec_odds >= 3.50)
        elif a_score > h_score:
            outcome = "away_win"
            winner_name = a_name
            loser_name = h_name
            is_upset = (a_dec_odds >= 3.50)
        else:
            outcome = "draw"
            winner_name = None
            loser_name = None
            is_upset = False

        score_diff = abs(h_score - a_score)

        # Summary Scenario Determination
        if outcome == "draw":
            if h_score == 0:
                scenario_key = "goalless_draw"
            else:
                scenario_key = "thrilling_draw" if h_score >= 2 else "standard_draw"
        elif is_upset:
            scenario_key = "massive_upset_win" if (h_dec_odds >= 6.0 or a_dec_odds >= 6.0) else "upset_win"
        elif score_diff >= 3:
            scenario_key = "blowout_win"
        elif score_diff == 1:
            scenario_key = "narrow_win"
        else:
            scenario_key = "comfortable_win"

        # Team stats fallback protection
        t_stats = m.get('team_stats') or {
            "home": {"possession": 50, "total_shots": 0, "shots_on_target": 0, "yellow_cards": 0, "red_cards": 0},
            "away": {"possession": 50, "total_shots": 0, "shots_on_target": 0, "yellow_cards": 0, "red_cards": 0}
        }

        league_name_raw = m['league'].get('name', '')
        l_flag = str(m['league'].get('flag', ''))
        emoji_flag = ""
        if l_flag and not l_flag.startswith('http') and not l_flag.startswith('/images/'):
            emoji_flag = l_flag
        elif "ca.png" in l_flag or "canadian" in league_name_raw.lower() or "northern super" in league_name_raw.lower():
            emoji_flag = "🇨🇦"

        league_name = f"{emoji_flag} {league_name_raw}" if emoji_flag else league_name_raw
        league_hashtag = f"#{league_name_raw.replace(' ', '')}"

        # Construct Final Object
        game_summaries[fixture_id] = {
            "fixture_id": fixture_id,
            "created_at": now_ts,
            "match_date": m['fixture'].get('date', iso_today)[:10],
            "status_short": status_short,
            "home_team": h_name,
            "away_team": a_name,
            "home_score": h_score,
            "away_score": a_score,
            "outcome": outcome,
            "winner_name": winner_name,
            "loser_name": loser_name,
            "scenario": scenario_key,
            "home_scorers": home_scorers,
            "away_scorers": away_scorers,
            "stats": {
                "home_possession": t_stats['home'].get('possession', 50),
                "away_possession": t_stats['away'].get('possession', 50),
                "home_shots_on_target": t_stats['home'].get('shots_on_target', 0),
                "away_shots_on_target": t_stats['away'].get('shots_on_target', 0),
                "home_total_shots": t_stats['home'].get('total_shots', 0),
                "away_total_shots": t_stats['away'].get('total_shots', 0),
                "home_red_cards": t_stats['home'].get('red_cards', 0),
                "away_red_cards": t_stats['away'].get('red_cards', 0)
            },
            "odds": {
                "home": h_odds_str,
                "draw": d_odds_str,
                "away": a_odds_str
            },
            "league_name": league_name,
            "league_hashtag": league_hashtag,
            "match_url": f"https://futbolstartingeleven.com/leagues/{m['league'].get('slug', '')}/#match-{fixture_id}"
        }
        new_summaries_count += 1

    # 4. Save to Disk
    with open(summary_file_path, 'w', encoding='utf-8') as f:
        json.dump(game_summaries, f, indent=2, ensure_ascii=False)
        
    print(f"  └─ Successfully updated {summary_file_path} ({new_summaries_count} new summaries added, {len(game_summaries)} total stored).")
    # -------------------------------------------------------------------------

    # Extract & sort live matches for top section
    live_matches = [m for m in raw_matches_by_day['today'] if is_match_live(m)]
    live_matches.sort(key=get_live_sort_weight, reverse=True)
    
    live_cards = []
    for m in live_matches:
        home_n = m['teams']['home']['name'].lower()
        away_n = m['teams']['away']['name'].lower()
        lg_n = m['league']['name'].lower()
        lg_a = m['league']['abbrev'].lower()
        live_cards.append({
            "html_card": pre_render_game_card(m, is_live_section=True),
            "search": f"{home_n} {away_n} {lg_n} {lg_a}"
        })

    # 6. Build Main Global Homepage
    leagues_by_day = {
        day: group_and_sort_matches_by_league(matches)
        for day, matches in raw_matches_by_day.items()
    }
    
    print(f"\n==================================================")
    print(f"📊 SSG BUILD SUMMARY:")
    print(f"  ├─ Yesterday: {len(raw_matches_by_day['yesterday'])} matches")
    print(f"  ├─ Today:     {len(raw_matches_by_day['today'])} matches")
    print(f"  └─ Tomorrow:  {len(raw_matches_by_day['tomorrow'])} matches")
    print(f"  ├─ Active League Pages Generated: {len(active_slugs)}")
    print(f"  ├─ Crossover Leagues Refreshed: {crossovers_actually_refreshed}")
    print(f"  ├─ Silent Player Profiles Synced: {min(5, len(dormant_players))}")
    print(f"  └─ Dormant Pages Synced: 1 (Round Robin)")
    print(f"==================================================")
    
    # Generate the JSON-LD schema using ONLY today's matches
    homepage_schema = generate_homepage_schema(raw_matches_by_day['today'])

    template = Template(HTML_TEMPLATE)
    output_html = template.render(
        leagues_by_day=leagues_by_day,
        live_cards=live_cards,
        display_dates=day_info["display"],
        nav_leagues_html=nav_html,
        schema_json=homepage_schema
    )
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(output_html)
        
    # Generate Sitemaps using the latest states
    build_sitemaps(state, team_state, player_state)
    
    # Gather changed URLs and ping IndexNow
    base_url = "https://futbolstartingeleven.com"
    changed_urls = [f"{base_url}/"]  # The homepage always has live updates
    
    for slug, data in state.items():
        if data.get('last_updated', 0) >= script_start_time:
            changed_urls.append(f"{base_url}/leagues/{slug}/")
            
    for slug, data in team_state.items():
        if data.get('last_updated', 0) >= script_start_time:
            changed_urls.append(f"{base_url}/teams/{slug}/lineup/")
            
    for slug, data in player_state.items():
        if data.get('last_updated', 0) >= script_start_time:
            changed_urls.append(f"{base_url}/players/{slug}/")
            
    ping_indexnow(changed_urls)
    
    file_size_kb = round(os.path.getsize(file_path) / 1024, 2)
    print(f"\n🎉 Successfully compiled TRUE STATIC frontend at {file_path} ({file_size_kb} KB)")

if __name__ == "__main__":
    generate_v2_index()

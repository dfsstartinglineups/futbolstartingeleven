import os
import re
import json
import urllib.request
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta, timezone
import unicodedata
import zoneinfo
import time
import urllib.error

# --- CONFIGURATION ---
API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ.get("FOOTBALL_API_KEY", "YOUR_API_KEY_HERE")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, '..')
DATA_DIR = os.path.join(ROOT_DIR, 'data')
PLAYERS_DIR = os.path.join(ROOT_DIR, 'players')

DATABASE_PATH = os.path.join(DATA_DIR, "player_database.json")
SITEMAP_PATH = os.path.join(ROOT_DIR, "sitemap-players.xml")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PLAYERS_DIR, exist_ok=True)

# 41 Supported Leagues
TOP_LEAGUE_IDS = [
    39, 40, 140, 135, 78, 61, 88, 94, 203, 144, 179, 119, # Europe
    253, 262, 71, 128, 239, # Americas
    307, 98, 188, 292, # World
    2, 3, 848, 13, 11, 16, 528, 45, 48, 143, 137, 81, # Cups
    1, 4, 9, 5, 531, 10, # International
    254 # Women (NWSL)
]

# Explicitly flag international leagues so the script can identify national teams
INT_LEAGUE_IDS = [1, 4, 9, 5, 531, 10]

TEAM_NEXT_MATCH_CACHE = {}

def fetch_api(endpoint, retries=5):
    """Fetches data from the API as fast as possible, only pausing when rate limited."""
    req = urllib.request.Request(f"{API_HOST}/{endpoint}")
    req.add_header("x-apisports-key", API_KEY)
    
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                
                # Catch "soft" rate limits where the API returns 200 OK but puts the error in the JSON
                if data.get("errors"):
                    errors = data["errors"]
                    if isinstance(errors, dict) and "rateLimit" in errors:
                        print(f"   🛑 Rate Limit Hit (JSON). Pausing for 61 seconds to reset quota... (Attempt {attempt+1}/{retries})")
                        time.sleep(61) # 61 seconds ensures the minute rolls over safely
                        continue 
                
                return data
                
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"   🛑 HTTP 429 Too Many Requests. Pausing for 61 seconds to reset quota... (Attempt {attempt+1}/{retries})")
                time.sleep(61)
            elif e.code in [499, 500, 502, 503, 504]:
                print(f"   ⚠️ Server Error {e.code}. Pausing for 5 seconds... (Attempt {attempt+1}/{retries})")
                time.sleep(5)
            else:
                print(f"⚠️ API Fetch Failed ({endpoint}): HTTP {e.code}")
                return None
        except Exception as e:
            print(f"⚠️ API Fetch Failed ({endpoint}): {e}")
            return None
            
    print(f"❌ Max retries reached for {endpoint}. Skipping.")
    return None

def normalize_string(text):
    if not text:
        return "unknown"
    text = str(text).lower()
    text = text.replace('ø', 'o').replace('æ', 'ae').replace('œ', 'oe').replace('ß', 'ss').replace('đ', 'd')
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('utf-8')
    return text

def get_player_slug(full_name):
    slug = normalize_string(full_name)
    slug = slug.replace(".", "").replace("'", "")
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    return slug

# 🎯 THE UNIQUE SLUG ENGINE (Duplicate Prevention)
def calculate_unique_slug(player_id, player_name, collision_registry):
    """Returns a stable, unique slug. Appends the player ID only if a collision exists."""
    base_slug = get_player_slug(player_name)
    
    # If the clean slug is free, or already owned by THIS exact player ID, claim it
    if base_slug not in collision_registry or str(collision_registry[base_slug]) == str(player_id):
        collision_registry[base_slug] = player_id
        return base_slug
        
    # Name collision! Append unique API-Football ID to isolate the directories safely
    fallback_slug = f"{base_slug}-{player_id}"
    collision_registry[fallback_slug] = player_id
    return fallback_slug

def get_team_slug(full_name):
    slug = normalize_string(full_name)
    slug = slug.replace(".", "").replace("'", "")
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    return slug

def get_league_slug(league_name):
    slug = normalize_string(league_name)
    slug = slug.replace(".", "").replace("'", "")
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    if "premier-league" in slug and "english" not in slug:
        slug = "english-" + slug
    return slug

def get_single_next_match(team_id, team_name):
    """Fetches the next match for a single team and returns (UTC_Datetime, HTML_String)."""
    if not team_id or not team_name or str(team_name) in ["N/A", "Unknown", "None"]:
        return None, None
        
    if team_id not in TEAM_NEXT_MATCH_CACHE:
        data = fetch_api(f"fixtures?team={team_id}&next=1")
        if data and data.get("response"):
            match = data["response"][0]
            date_iso = match["fixture"]["date"]
            
            try:
                dt_utc = datetime.fromisoformat(date_iso)
                dt_est = dt_utc.astimezone(zoneinfo.ZoneInfo("America/New_York"))
                date_str = dt_est.strftime("%A, %b %d - %I:%M %p EST")
            except:
                dt_utc = datetime.now(timezone.utc) + timedelta(days=365) 
                date_str = "Upcoming"
                
            home_team = match["teams"]["home"]["name"]
            away_team = match["teams"]["away"]["name"]
            
            if str(match["teams"]["home"]["id"]) == str(team_id):
                opp_name = away_team
                prefix = "vs"
            else:
                opp_name = home_team
                prefix = "@"
                
            opp_slug = get_team_slug(opp_name)
            team_slug = get_team_slug(team_name)
            
            html_string = f'<a href="/lineups/{team_slug}/" class="seo-link fw-bold text-dark">{team_name}</a> {prefix} <a href="/lineups/{opp_slug}/" class="seo-link fw-bold text-dark">{opp_name}</a> <span class="text-muted font-monospace mx-1">|</span> <span class="badge bg-dark text-white fw-bold px-2 py-1" style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">{date_str}</span>'
            TEAM_NEXT_MATCH_CACHE[team_id] = (dt_utc, html_string)
        else:
            TEAM_NEXT_MATCH_CACHE[team_id] = (None, f'<a href="/lineups/{get_team_slug(team_name)}/" class="seo-link fw-bold text-dark">{team_name}</a> Match Center <span class="badge bg-dark text-white fw-bold px-2 py-1" style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">Scheduled</span>')
            
    return TEAM_NEXT_MATCH_CACHE[team_id]

def get_smart_next_match(club_id, club_name, nat_id, nat_name):
    """Compares club and national team schedules and returns the chronologically closest match."""
    club_dt, club_html = get_single_next_match(club_id, club_name)
    nat_dt, nat_html = get_single_next_match(nat_id, nat_name)
    
    if club_dt and nat_dt:
        return nat_html if nat_dt < club_dt else club_html
    elif club_html:
        return club_html
    elif nat_html:
        return nat_html
    else:
        safe_name = club_name if club_name and str(club_name) not in ["N/A", "Unknown", "None"] else "Club"
        safe_slug = get_team_slug(safe_name) if safe_name != "Club" else "unknown"
        return f'<a href="/lineups/{safe_slug}/" class="seo-link fw-bold text-dark">{safe_name}</a> Match Center <span class="badge bg-dark text-white fw-bold px-2 py-1" style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">Scheduled</span>'

def generate_player_sitemap(database):
    print("🗺️ Generating sitemap-players.xml...")
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    ET.register_namespace('', "http://www.sitemaps.org/schemas/sitemap/0.9")
    urlset = ET.Element('urlset', xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    
    for p_id, p_data in sorted(database.items(), key=lambda x: x[1]['slug']):
        url = ET.SubElement(urlset, 'url')
        ET.SubElement(url, 'loc').text = f"https://futbolstartingeleven.com/players/{p_data['slug']}/"
        ET.SubElement(url, 'lastmod').text = today_str
        ET.SubElement(url, 'changefreq').text = "daily"
        ET.SubElement(url, 'priority').text = "0.6"
        
    raw_xml = ET.tostring(urlset, 'utf-8')
    parsed_xml = minidom.parseString(raw_xml)
    pretty_xml = "\n".join([line for line in parsed_xml.toprettyxml(indent="  ").splitlines() if line.strip()])
    
    with open(SITEMAP_PATH, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
    print(f"✅ sitemap-players.xml saved with {len(database)} player profile links.")

def parse_stats(stats_list, player_rating="N/A"):
    """Groups statistics by Competition AND Team Name."""
    enriched = {"total": {}, "competitions": {}}
    if not stats_list: return enriched
    for stat in stats_list:
        comp_name = stat.get("league", {}).get("name", "Unknown")
        team_name = stat.get("team", {}).get("name", "Unknown")
        g = stat.get("games", {}).get("appearences", 0) or 0
        if g == 0: continue
        
        key = f"{comp_name}|{team_name}"
        
        enriched["competitions"][key] = {
            "comp_name": comp_name, "team_name": team_name,
            "games": g, "minutes": stat.get("games", {}).get("minutes", 0),
            "goals": stat.get("goals", {}).get("total", 0) or 0, "assists": stat.get("goals", {}).get("assists", 0) or 0,
            "saves": stat.get("goals", {}).get("saves", 0) or 0, "shots_on": stat.get("shots", {}).get("on", 0) or 0,
            "key_passes": stat.get("passes", {}).get("key", 0) or 0, "pass_acc": stat.get("passes", {}).get("accuracy", 0) or 0,
            "tackles": stat.get("tackles", {}).get("total", 0) or 0, "interceptions": stat.get("tackles", {}).get("interceptions", 0) or 0,
            "yellow_cards": stat.get("cards", {}).get("yellow", 0) or 0, "red_cards": stat.get("cards", {}).get("red", 0) or 0,
            "rating": stat.get("games", {}).get("rating", "N/A")
        }
        
    t_games = sum(s["games"] for s in enriched["competitions"].values())
    t_goals = sum(s["goals"] for s in enriched["competitions"].values())
    t_assists = sum(s["assists"] for s in enriched["competitions"].values())
    
    total_pass_sum = sum((s["pass_acc"] * s["games"]) for s in enriched["competitions"].values() if s["pass_acc"])
    t_pass_acc = round(total_pass_sum / t_games) if t_games > 0 else 0
    
    enriched["total"] = {"games": t_games, "goals": t_goals, "assists": t_assists, "pass_acc": t_pass_acc, "rating": player_rating}
    return enriched

def build_competition_rows(season_stats, year="2026"):
    comps = season_stats.get("competitions", {})
    if not comps:
        return f'<tr><td colspan="10" class="text-center text-muted fst-italic py-3">No competitive data available for the {year} season yet.</td></tr>'
    
    rows = ""
    for key, stats in comps.items():
        comp_name = stats["comp_name"]
        team_name = stats["team_name"]
        comp_slug = get_league_slug(comp_name)
        
        games = stats.get("games", 0)
        minutes = stats.get("minutes", 0) or stats.get("min", 0)
        goals = stats.get("goals", 0)
        assists = stats.get("assists", 0)
        shots_on = stats.get("shots_on", 0)
        pass_acc = stats.get("pass_acc", 0)
        key_passes = stats.get("key_passes", 0)
        drb_or_saves = stats.get("saves", 0) if stats.get("saves", 0) > 0 else f"{stats.get('tackles', 0)} ({stats.get('interceptions', 0)})"
        yellow = stats.get("yellow_cards", 0)
        red = stats.get("red_cards", 0)
        
        rows += f"""<tr>
            <td><a href="/leagues/{comp_slug}/" class="seo-link fw-bold text-dark">{comp_name} <span class="text-muted fw-normal">({team_name})</span></a></td>
            <td class="text-center">{games}</td>
            <td class="text-center">{minutes:,}</td>
            <td class="text-center text-success fw-bold">{goals}</td>
            <td class="text-center fw-bold">{assists}</td>
            <td class="text-center">{shots_on}</td>
            <td class="text-center">{pass_acc}%</td>
            <td class="text-center">{key_passes}</td>
            <td class="text-center">{drb_or_saves}</td>
            <td class="text-center">{yellow} / {red}</td>
        </tr>"""
    return rows

def build_gamelog_rows(recent_games):
    if not recent_games:
        return '<tr><td colspan="8" class="text-center text-muted fst-italic py-3">No recent game log data. Waiting for match appearance.</td></tr>'
    
    rows = ""
    for match in recent_games:
        date = match.get("date", "Unknown")
        opp_name = match.get("opponent_name", "TBD")
        opp_slug = get_team_slug(opp_name)
        venue_prefix = "vs" if match.get("is_home", True) else "@"
        
        res_char = match.get("result", "D")
        res_score = match.get("score_line", "0-0")
        res_class = "text-success" if res_char == "W" else "text-danger" if res_char == "L" else "text-muted"
        
        rows += f"""<tr>
            <td class="text-start" style="padding: 8px 12px;">{date}</td>
            <td class="text-start" style="padding: 8px;">
                {venue_prefix} <a href="/lineups/{opp_slug}/" class="seo-link fw-bold text-dark">{opp_name}</a>
            </td>
            <td class="{res_class} fw-bold" style="padding: 8px;">{res_char} {res_score}</td>
            <td style="padding: 8px;">{match.get('minutes', 0)}'</td>
            <td class="text-success fw-bold" style="padding: 8px;">{match.get('goals', 0)}</td>
            <td class="fw-bold" style="padding: 8px;">{match.get('assists', 0)}</td>
            <td style="padding: 8px;">{match.get('rating', 'N/A')}</td>
        </tr>"""
    return rows

def write_initial_html_file(p_id, p_data):
    player_folder = os.path.join(PLAYERS_DIR, p_data['slug'])
    os.makedirs(player_folder, exist_ok=True)
    
    stats_2026 = p_data.get("stats_2026", {})
    stats_2025 = p_data.get("stats_2025", {})
    total_stats = stats_2026.get("total", {})
    
    gls = total_stats.get("goals", 0)
    ast = total_stats.get("assists", 0)
    rating = total_stats.get("rating", "N/A")
    
    comp_rows_2026 = build_competition_rows(stats_2026, "2026")
    comp_rows_2025 = build_competition_rows(stats_2025, "2025")
    gamelog_rows_html = build_gamelog_rows(p_data.get("recent_games", []))
    
    next_match_text = get_smart_next_match(
        p_data.get("team_id"), p_data.get("team_name"), 
        p_data.get("national_team_id"), p_data.get("national_team_name")
    )
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    
    <title>Is {p_data['name']} Starting Today? Lineup & Stats | Futbol Starting Eleven</title>
    <meta name="description" content="Is {p_data['name']} starting today? Get live matchday lineup status, real-time performance stats, and season overview metrics for {p_data['name']} ({p_data['team_name']}).">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://futbolstartingeleven.com/players/{p_data['slug']}/">

    <meta property="og:site_name" content="Futbol Starting Eleven">
    <meta property="og:type" content="profile">
    <meta property="og:title" content="Is {p_data['name']} Starting Today? Lineup & Stats | Futbol Starting Eleven">
    <meta property="og:description" content="Live starting lineups, form ratings, and seasonal breakdown for {p_data['name']} at {p_data['team_name']}.">
    <meta property="og:url" content="https://futbolstartingeleven.com/players/{p_data['slug']}/">
    <meta property="og:image" content="https://futbolstartingeleven.com/social-share1.png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">

    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:domain" content="futbolstartingeleven.com">
    <meta name="twitter:title" content="{p_data['name']} - {p_data['team_name']} Matchday Profile">
    <meta name="twitter:description" content="Track live performance matrix, formation maps, and stats for {p_data['name']} on Futbol Starting Eleven.">
    <meta name="twitter:image" content="https://futbolstartingeleven.com/social-share1.png">

    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    
    <style>
        body {{ background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow-x: hidden; }}
        .header-brand {{ font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; font-style: italic; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }}
        .header-brand a {{ color: inherit; }}
        .header-brand span {{ text-shadow: none !important; background: linear-gradient(to bottom, #20c997 0%, #198754 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; filter: drop-shadow(0 0 12px rgba(32, 201, 151, 0.6)); }}
        .profile-sidebar-card {{ background: #fff; border: 1px solid #dee2e6; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); padding: 24px; text-align: center; }}
        .player-avatar-wrapper {{ position: relative; width: 110px; height: 110px; margin: 0 auto 15px auto; }}
        .player-avatar {{ width: 100%; height: 100%; object-fit: cover; border-radius: 50%; border: 4px solid #20c997; background-color: #f8f9fa; }}
        .team-badge-sub {{ position: absolute; bottom: -2px; right: -2px; width: 35px; height: 35px; background: #fff; border-radius: 50%; padding: 3px; border: 1px solid #dee2e6; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .sidebar-player-name {{ font-size: 1.4rem; font-weight: 800; color: #212529; margin-bottom: 2px; }}
        .sidebar-player-meta {{ font-size: 0.8rem; font-weight: 700; color: #6c757d; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 20px; }}
        .seo-link {{ color: inherit; text-decoration: none; transition: color 0.15s ease-in-out; }}
        .sidebar-player-meta .seo-link:hover {{ color: #20c997; }}
        .table tbody td .seo-link:hover {{ color: #198754; }}
        .info-card {{ background: #fff; border: 1px solid #dee2e6; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.03); padding: 20px; margin-bottom: 24px; }}
        .info-card h3 {{ font-size: 1rem; font-weight: 800; color: #212529; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #f1f3f5; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-row {{ display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #f8f9fa; }}
        .stat-row:last-child {{ border-bottom: none; }}
        .stat-label {{ color: #6c757d; font-size: 0.85rem; font-weight: 600; }}
        .stat-value {{ color: #212529; font-size: 0.9rem; font-weight: 700; text-align: right; }}
        .table-responsive {{ border-radius: 8px; overflow-x: auto; border: 1px solid #dee2e6; width: 100%; }}
        .table thead th {{ background-color: #212529; color: #fff; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; font-weight: 700; border: none; padding: 12px; white-space: nowrap; }}
        .table tbody td {{ font-size: 0.85rem; font-weight: 600; color: #495057; padding: 12px; vertical-align: middle; border-bottom: 1px solid #f1f3f5; white-space: nowrap; }}
        .table tbody tr:last-child td {{ border-bottom: none; }}
        .table tbody tr:hover {{ background-color: #f8f9fa; }}
        .comp-logo {{ width: 20px; height: 20px; margin-right: 8px; vertical-align: text-bottom; }}
        .big-stat-box {{ background: #f8f9fa; border-radius: 8px; padding: 12px; text-align: center; border: 1px solid #e9ecef; }}
        .big-stat-value {{ font-size: 1.6rem; font-weight: 900; color: #198754; line-height: 1; }}
        .big-stat-label {{ font-size: 0.7rem; font-weight: 700; color: #6c757d; text-transform: uppercase; margin-top: 5px; letter-spacing: 0.5px; }}
        @keyframes pulse-green {{ 0% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0.7); }} 70% {{ transform: scale(1); box-shadow: 0 0 0 6px rgba(32, 201, 151, 0); }} 100% {{ transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0); }} }}
        .live-dot {{ display: inline-block; width: 8px; height: 8px; background-color: #20c997; border-radius: 50%; margin-right: 6px; margin-bottom: 1px; animation: pulse-green 2s infinite; }}
        @media (max-width: 576px) {{ .header-brand {{ font-size: 1.5rem; }} }}
    </style>
</head>
<body>

    <nav class="navbar sticky-top shadow-sm pt-2 pb-2 mb-4" style="background-color: #212529; z-index: 1050;">
        <div class="container d-flex justify-content-between align-items-center flex-wrap">
            <div class="header-brand"><a href="/" class="text-decoration-none">Futbol Starting <span>Eleven</span></a></div>
            <div class="d-flex align-items-center gap-2"><a href="/lineups/{get_team_slug(p_data['team_name'])}/" class="btn btn-sm btn-outline-light fw-bold" style="font-size:0.75rem;">← Back to {p_data['team_name']}</a></div>
        </div>
    </nav>

    <div class="container mb-5">
        <div class="row g-4">
            <div class="col-lg-4">
                <div class="profile-sidebar-card">
                    <div class="player-avatar-wrapper">
                        <img src="{p_data['photo']}" alt="{p_data['name']}" class="player-avatar">
                    </div>
                    <div class="sidebar-player-name">{p_data['name']}</div>
                    <div class="sidebar-player-meta"><a href="/lineups/{get_team_slug(p_data['team_name'])}/" class="seo-link fw-bold" id="val-team">{p_data['team_name']}</a> • <span id="val-position">{p_data['position']}</span></div>
                    <hr style="border-color: #dee2e6; opacity: 1; margin: 15px 0;">
                    <div class="text-start">
                        <div class="stat-row"><span class="stat-label">Nationality</span><span class="stat-value">{p_data.get('nationality', 'N/A')}</span></div>
                        <div class="stat-row"><span class="stat-label">National Team</span><span class="stat-value" id="val-national-team">{p_data.get('national_team_name', 'N/A')}</span></div>
                        <div class="stat-row"><span class="stat-label">Age</span><span class="stat-value" id="val-age">{p_data.get('age', 'N/A')}</span></div>
                        <div class="stat-row"><span class="stat-label">Form Rating</span><span class="stat-value text-success" id="val-rating">{rating}</span></div>
                    </div>
                </div>
            </div>

            <div class="col-lg-8">
                <div id="live-match-widget" class="info-card border-dark" style="border-left: 5px solid #212529; margin-bottom: 20px;">
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                        <div class="d-flex align-items-center"><span class="fw-bold text-dark" style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px;">Upcoming Matchup</span></div>
                        <div class="stat-value text-end" style="font-size: 0.9rem;">
                            {next_match_text}
                        </div>
                    </div>
                </div>

                <div class="info-card">
                    <h3>2026 Season Overview</h3>
                    <div class="row g-3">
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value" id="val-overview-matches">{total_stats.get('games', 0)}</div><div class="big-stat-label">Matches</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value" id="val-overview-goals">{gls}</div><div class="big-stat-label">Goals</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value" id="val-overview-assists">{ast}</div><div class="big-stat-label">Assists</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value" id="val-overview-pass">{total_stats.get('pass_acc', 0)}%</div><div class="big-stat-label">Pass Acc</div></div></div>
                    </div>
                </div>

                <div class="info-card">
                    <h3>2026 Performance by Competition</h3>
                    <div class="table-responsive">
                        <table class="table table-borderless mb-0">
                            <thead>
                                <tr>
                                    <th>Competition</th>
                                    <th class="text-center">MP</th>
                                    <th class="text-center">Min</th>
                                    <th class="text-center">Gls</th>
                                    <th class="text-center">Ast</th>
                                    <th class="text-center">Sh (On)</th>
                                    <th class="text-center">Pass Acc</th>
                                    <th class="text-center">Key P</th>
                                    <th class="text-center">Tkl(Int) / Sav</th>
                                    <th class="text-center">Yel/Red</th>
                                </tr>
                            </thead>
                            <tbody>
                                {comp_rows_2026}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="info-card">
                    <h3>2025 Performance by Competition</h3>
                    <div class="table-responsive">
                        <table class="table table-borderless mb-0">
                            <thead>
                                <tr>
                                    <th>Competition</th>
                                    <th class="text-center">MP</th>
                                    <th class="text-center">Min</th>
                                    <th class="text-center">Gls</th>
                                    <th class="text-center">Ast</th>
                                    <th class="text-center">Sh (On)</th>
                                    <th class="text-center">Pass Acc</th>
                                    <th class="text-center">Key P</th>
                                    <th class="text-center">Tkl(Int) / Sav</th>
                                    <th class="text-center">Yel/Red</th>
                                </tr>
                            </thead>
                            <tbody>
                                {comp_rows_2025}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="info-card">
                    <h3>Recent Matches (Last 10 Games)</h3>
                    <div class="table-responsive">
                        <table class="table table-sm table-borderless mb-0 text-center" style="font-size: 0.8rem;">
                            <thead>
                                <tr style="background-color: #f8f9fa; border-bottom: 1px solid #dee2e6;">
                                    <th class="text-start" style="padding: 8px 12px; color: #6c757d;">Date</th>
                                    <th class="text-start" style="padding: 8px; color: #6c757d;">Opponent</th>
                                    <th style="padding: 8px; color: #6c757d;">Result</th>
                                    <th style="padding: 8px; color: #6c757d;">Min</th>
                                    <th style="padding: 8px; color: #6c757d;">Gls</th>
                                    <th style="padding: 8px; color: #6c757d;">Ast</th>
                                    <th style="padding: 8px; color: #6c757d;">Rating</th>
                                </tr>
                            </thead>
                            <tbody>
                                {gamelog_rows_html}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        window.TARGET_PLAYER_ID = {p_id};
        window.TARGET_TEAM_NAME = "{p_data['team_name']}";
    </script>
    <script src="/js/player-live.js"></script>
</body>
</html>"""
    with open(os.path.join(player_folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

def update_player_html(player_slug, updates):
    filepath = os.path.join(PLAYERS_DIR, player_slug, "index.html")
    if not os.path.exists(filepath):
        return

    with open(filepath, "r", encoding="utf-8") as f:
        html = f.read()

    single_value_mappings = {
        "val-team": updates.get("team_name"),
        "val-national-team": updates.get("national_team_name"),
        "val-age": updates.get("age"),
        "val-position": updates.get("position"),
        "val-rating": updates.get("rating"),
        "val-overview-matches": str(updates.get("overview_matches")) if updates.get("overview_matches") is not None else None,
        "val-overview-goals": str(updates.get("overview_goals")) if updates.get("overview_goals") is not None else None,
        "val-overview-assists": str(updates.get("overview_assists")) if updates.get("overview_assists") is not None else None,
        "val-overview-pass": str(updates.get("overview_pass")) + "%" if updates.get("overview_pass") is not None else None
    }

    for tag_id, new_val in single_value_mappings.items():
        if new_val is not None:
            html = re.sub(
                rf'(id="{tag_id}"[^>]*>).*?(</)', 
                rf'\g<1>{new_val}\g<2>', 
                html
            )

    if updates.get("rows_2026"):
        html = re.sub(
            r'<!-- START 2026 ROWS -->.*?<!-- END 2026 ROWS -->', 
            f'<!-- START 2026 ROWS -->\n{updates["rows_2026"]}\n<!-- END 2026 ROWS -->', 
            html, 
            flags=re.DOTALL
        )

    if updates.get("rows_gamelog"):
        html = re.sub(
            r'<!-- START GAMELOG ROWS -->.*?<!-- END GAMELOG ROWS -->', 
            f'<!-- START GAMELOG ROWS -->\n{updates["rows_gamelog"]}\n<!-- END GAMELOG ROWS -->', 
            html, 
            flags=re.DOTALL
        )
        
    if updates.get("next_match"):
        html = re.sub(
            r'(<div id="live-match-widget".*?<div class="stat-value text-end"[^>]*>).*?(</div>\s*</div>\s*</div>)',
            rf'\g<1>\n                            {updates["next_match"]}\n                        \g<2>',
            html,
            flags=re.DOTALL
        )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

def bootstrap_universe():
    print("🛸 DATABASE NOT FOUND! Entering Initial 2026 Roster Bootstrap...")
    database = {}
    
    # 🎯 STEP 1: Initialize local tracking dict for unique slug resolution
    collision_registry = {}
    
    for league_id in TOP_LEAGUE_IDS:
        print(f"📥 Extracting 2026 and 2025 rosters for League {league_id}...")
        
        season_data = {2026: {}, 2025: {}}
        
        for season in [2026, 2025]:
            page = 1
            total_pages = 1
            while page <= total_pages:
                data = fetch_api(f"players?league={league_id}&season={season}&page={page}")
                if not data or not data.get("response"): break
                total_pages = data.get("paging", {}).get("total", 1)
                
                for item in data["response"]:
                    p_id = str(item["player"]["id"])
                    season_data[season][p_id] = item
                page += 1

        all_players = set(season_data[2026].keys()).union(set(season_data[2025].keys()))
        
        for p_id in all_players:
            item_2026 = season_data[2026].get(p_id, {})
            item_2025 = season_data[2025].get(p_id, {})
            
            stats_list_2026 = item_2026.get("statistics", [])
            stats_list_2025 = item_2025.get("statistics", [])
            
            if p_id in database: 
                if database[p_id].get("national_team_name", "N/A") == "N/A":
                    for stat in (stats_list_2026 + stats_list_2025):
                        if stat.get("league", {}).get("id") in INT_LEAGUE_IDS:
                            database[p_id]["national_team_id"] = stat.get("team", {}).get("id")
                            database[p_id]["national_team_name"] = stat.get("team", {}).get("name", "N/A")
                            break
                            
                def integrate_stats(season_key, raw_stats_list):
                    if not raw_stats_list: return
                    new_parsed = parse_stats(raw_stats_list, database[p_id].get("rating", "N/A"))
                    
                    for comp_key, comp_data in new_parsed.get("competitions", {}).items():
                        database[p_id][season_key]["competitions"][comp_key] = comp_data
                        
                    comps = database[p_id][season_key]["competitions"]
                    t_games = sum(s.get("games", 0) for s in comps.values())
                    t_goals = sum(s.get("goals", 0) for s in comps.values())
                    t_assists = sum(s.get("assists", 0) for s in comps.values())
                    t_pass_sum = sum((s.get("pass_acc", 0) * s.get("games", 0)) for s in comps.values())
                    
                    database[p_id][season_key]["total"].update({
                        "games": t_games,
                        "goals": t_goals,
                        "assists": t_assists,
                        "pass_acc": round(t_pass_sum / t_games) if t_games > 0 else 0
                    })

                integrate_stats("stats_2026", stats_list_2026)
                integrate_stats("stats_2025", stats_list_2025)
                continue
            
            player = item_2026.get("player") or item_2025.get("player")
            if not player: continue
            
            first_name = player.get("firstname", "")
            last_name = player.get("lastname", "")
            full_name = f"{first_name} {last_name}".strip()
            
            if not full_name:
                full_name = player.get("name", "Unknown")
            if not full_name or full_name == "Unknown": continue
            
            if not stats_list_2026 and not stats_list_2025: continue
                
            club_stat = None
            nat_stat = None
            
            for stat in (stats_list_2026 + stats_list_2025):
                l_id = stat.get("league", {}).get("id")
                league_type = stat.get("league", {}).get("type", "").lower() 
                
                if l_id in INT_LEAGUE_IDS:
                    if not nat_stat: nat_stat = stat
                elif league_type in ["league", "cup"]:
                    if not club_stat: club_stat = stat
                    
            if not club_stat:
                club_stat = stats_list_2026[0] if stats_list_2026 else stats_list_2025[0]
                
            team_name = club_stat.get("team", {}).get("name", "Unknown")
            team_id = club_stat.get("team", {}).get("id")
            
            national_team_name = nat_stat.get("team", {}).get("name", "N/A") if nat_stat else "N/A"
            national_team_id = nat_stat.get("team", {}).get("id") if nat_stat else None
            
            # 🎯 STEP 2: Use collision manager during fresh bootstrap mapping
            assigned_slug = calculate_unique_slug(p_id, full_name, collision_registry)
            
            database[p_id] = {
                "name": full_name,
                "slug": assigned_slug,
                "team_name": team_name,
                "team_id": team_id,
                "national_team_name": national_team_name,
                "national_team_id": national_team_id,
                "position": club_stat.get("games", {}).get("position", "Midfielder"),
                "photo": player.get("photo", ""),
                "age": player.get("age", "N/A"),
                "nationality": player.get("nationality", "N/A"),
                "stats_2026": parse_stats(stats_list_2026, player.get("rating", "N/A")),
                "stats_2025": parse_stats(stats_list_2025, item_2025.get("player", {}).get("rating", "N/A")),
                "recent_games": []
            }
            
    with open(DATABASE_PATH, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4)
        
    print(f"🎉 Bootstrap Completed! Indexed {len(database)} players.")
    return database

def process_nightly_maintenance(database):
    print("⚙️ Running Automated Nightly Maintenance Mode...")
    
    # 🎯 STEP 3: Pre-build collision registry from current database to protect SEO
    collision_registry = {}
    for existing_id, existing_data in database.items():
        if "slug" in existing_data:
            collision_registry[existing_data["slug"]] = existing_id
            
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_file = os.path.join(DATA_DIR, f"games_{yesterday_str}.json")
    
    if not os.path.exists(yesterday_file):
        print(f"ℹ️ Yesterday's match log file matches_{yesterday_str}.json does not exist.")
        return
        
    with open(yesterday_file, "r", encoding="utf-8") as f:
        matches = json.load(f)
        
    for match in matches:
        status_short = match.get("fixture", {}).get("status", {}).get("short", "NS")
        if status_short not in ["FT", "AET", "PEN"]: continue
        
        match_league_id = match.get("league", {}).get("id")
        is_international = match_league_id in INT_LEAGUE_IDS
            
        for side in ["homeLineup", "awayLineup"]:
            lineup_data = match.get(side)
            if not lineup_data: continue
                
            is_home = (side == "homeLineup")
            opp_name = match["teams"]["away"]["name"] if is_home else match["teams"]["home"]["name"]
            score_line = f"{match['goals']['home']}-{match['goals']['away']}"
            res_char = "W" if (match["goals"]["home"] > match["goals"]["away"] and is_home) or (match["goals"]["away"] > match["goals"]["home"] and not is_home) else "L" if match["goals"]["home"] != match["goals"]["away"] else "D"

            team_id = lineup_data.get("team", {}).get("id")
            team_name = lineup_data.get("team", {}).get("name", "Unknown")

            for group in ["startXI", "substitutes"]:
                for slot in lineup_data.get(group, []):
                    player_obj = slot.get("player", {})
                    p_id = str(player_obj.get("id"))
                    live_stats = player_obj.get("live_stats", {})
                    
                    if not p_id or p_id == "None" or not live_stats or live_stats.get("rating") == "N/A":
                        continue
                        
                    fresh_api_data = fetch_api(f"players?id={p_id}&season=2026")
                    
                    full_name = player_obj.get("name", "Unknown")
                    player_api_rating = live_stats.get("rating", "N/A")
                    season_stats_snapshot = {}
                    
                    if fresh_api_data and fresh_api_data.get("response"):
                        p_data_api = fresh_api_data["response"][0]
                        api_player = p_data_api.get("player", {})
                        
                        first_name = api_player.get("firstname", "")
                        last_name = api_player.get("lastname", "")
                        if first_name or last_name:
                            full_name = f"{first_name} {last_name}".strip()
                        elif api_player.get("name"):
                            full_name = api_player.get("name")
                            
                        stats_list_2026 = p_data_api.get("statistics", [])
                        player_api_rating = api_player.get("rating", live_stats.get("rating", "N/A"))
                        
                        season_stats_snapshot = parse_stats(stats_list_2026, player_api_rating)
                        player_obj["age"] = api_player.get("age", player_obj.get("age"))
                        player_obj["nationality"] = api_player.get("nationality", player_obj.get("nationality"))
                        player_obj["photo"] = api_player.get("photo", player_obj.get("photo"))
                        
                    if p_id not in database:
                        print(f"      🆕 New Player Discovered: {full_name} (ID: {p_id})")
                        
                        # 🎯 STEP 4: Resolve name collision safely for late discovered players
                        assigned_slug = calculate_unique_slug(p_id, full_name, collision_registry)
                        
                        database[p_id] = {
                            "name": full_name, 
                            "slug": assigned_slug,
                            "team_name": team_name if not is_international else "Unknown",
                            "team_id": team_id if not is_international else None,
                            "national_team_name": team_name if is_international else "N/A",
                            "national_team_id": team_id if is_international else None,
                            "position": player_obj.get("pos", "Midfielder"), 
                            "photo": player_obj.get("photo", ""),
                            "age": player_obj.get("age", "N/A"), 
                            "nationality": player_obj.get("nationality", "N/A"),
                            "stats_2026": {"total": {}, "competitions": {}}, 
                            "stats_2025": {"total": {}, "competitions": {}},
                            "recent_games": []
                        }
                        write_initial_html_file(p_id, database[p_id])
                    
                    if is_international:
                        if str(database[p_id].get("national_team_id")) != str(team_id):
                            database[p_id]["national_team_id"] = team_id
                            database[p_id]["national_team_name"] = team_name
                    else:
                        if str(database[p_id].get("team_id")) != str(team_id):
                            database[p_id]["team_id"] = team_id
                            database[p_id]["team_name"] = team_name
                    
                    match_log_entry = {
                        "date": yesterday_str, "opponent_name": opp_name, "is_home": is_home,
                        "result": res_char, "score_line": score_line,
                        "minutes": live_stats.get("minutes", 90), "goals": live_stats.get("goals", 0),
                        "assists": live_stats.get("assists", 0), "rating": live_stats.get("rating", "6.5")
                    }
                    database[p_id]["recent_games"].insert(0, match_log_entry)
                    if len(database[p_id]["recent_games"]) > 10: database[p_id]["recent_games"].pop()
                    
                    updates = {
                        "rows_gamelog": build_gamelog_rows(database[p_id]["recent_games"]),
                        "rating": player_api_rating,
                        "team_name": database[p_id]["team_name"],
                        "national_team_name": database[p_id]["national_team_name"]
                    }

                    if not is_international:
                        updates["age"] = player_obj.get("age")
                        updates["position"] = player_obj.get("pos")

                    if season_stats_snapshot:
                        total = season_stats_snapshot.get("total", {})
                        updates.update({
                            "overview_matches": total.get("games", 0),
                            "overview_goals": total.get("goals", 0),
                            "overview_assists": total.get("assists", 0),
                            "overview_pass": total.get("pass_acc", 0),
                            "rows_2026": build_competition_rows(season_stats_snapshot, "2026")
                        })
                        
                    update_player_html(database[p_id]["slug"], updates)

    print("   📅 Updating Next Match schedules for active teams...")
    active_teams = {}
    for match in matches:
        if match.get("fixture", {}).get("status", {}).get("short") in ["FT", "AET", "PEN"]:
            active_teams[str(match["teams"]["home"]["id"])] = match["teams"]["home"]["name"]
            active_teams[str(match["teams"]["away"]["id"])] = match["teams"]["away"]["name"]

    for t_id, t_name in active_teams.items():
        if t_id in TEAM_NEXT_MATCH_CACHE:
            del TEAM_NEXT_MATCH_CACHE[t_id]
        
        for p_id, p_data in database.items():
            if str(p_data.get("team_id")) == str(t_id) or str(p_data.get("national_team_id")) == str(t_id):
                smart_next_match = get_smart_next_match(
                    p_data.get("team_id"), p_data.get("team_name"), 
                    p_data.get("national_team_id"), p_data.get("national_team_name")
                )
                update_player_html(p_data["slug"], {"next_match": smart_next_match})

    with open(DATABASE_PATH, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4)
        
    print("✅ Maintenance complete. Static HTML files updated in place.")

def main():
    if not os.path.exists(DATABASE_PATH):
        database = bootstrap_universe()
        print("📁 Dumping initial batch static pages...")
        for p_id, p_data in database.items():
            write_initial_html_file(p_id, p_data)
    else:
        with open(DATABASE_PATH, "r", encoding="utf-8") as f:
            database = json.load(f)
        process_nightly_maintenance(database)
        
    generate_player_sitemap(database)

if __name__ == "__main__":
    main()

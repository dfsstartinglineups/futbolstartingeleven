import os
import re
import json
import urllib.request
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta, timezone

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

# 41 Supported Leagues from your core stack
TOP_LEAGUE_IDS = [
    39, 40, 140, 135, 78, 61, 88, 94, 203, 144, 179, 119, # Europe
    253, 262, 71, 128, 239, # Americas
    307, 98, 188, 292, # World
    2, 3, 848, 13, 11, 16, 528, 45, 48, 143, 137, 81, # Cups
    1, 4, 9, 5, 531, 10, # International
    254 # Women (NWSL)
]

def fetch_api(endpoint):
    req = urllib.request.Request(f"{API_HOST}/{endpoint}")
    req.add_header("x-apisports-key", API_KEY)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"⚠️ API Fetch Failed ({endpoint}): {e}")
        return None

def get_player_slug(full_name):
    slug = full_name.lower().replace(".", "").replace("'", "")
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    return slug

def get_team_slug(full_name):
    slug = full_name.lower().replace(".", "").replace("'", "")
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    return slug

def get_league_slug(league_name):
    slug = league_name.lower().replace(".", "").replace("'", "")
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    if "premier-league" in slug and "english" not in slug:
        slug = "english-" + slug
    return slug

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

def build_competition_rows(season_stats):
    rows = ""
    comps = season_stats.get("competitions", {})
    if not comps:
        return '<tr><td colspan="10" class="text-center text-muted">No competitive data available for this player.</td></tr>'
    
    for comp_name, stats in comps.items():
        comp_slug = get_league_slug(comp_name)
        games = stats.get("games", 0)
        minutes = stats.get("minutes", 0) or stats.get("min", 0)
        goals = stats.get("goals", 0)
        assists = stats.get("assists", 0)
        
        # Positional layout metric handling
        shots_on = stats.get("shots_on", 0)
        pass_acc = stats.get("pass_acc", 0)
        key_passes = stats.get("key_passes", 0)
        drb_or_saves = stats.get("saves", 0) if stats.get("saves", 0) > 0 else f"{stats.get('tackles', 0)} ({stats.get('interceptions', 0)})"
        
        yellow = stats.get("yellow_cards", 0)
        red = stats.get("red_cards", 0)
        rating = stats.get("rating", "N/A")
        
        rating_class = "text-success fw-bold" if rating != "N/A" and float(rating) >= 7.0 else ""
        
        rows += f"""<tr>
            <td><a href="/leagues/{comp_slug}/" class="seo-link fw-bold text-dark">{comp_name}</a></td>
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
        return '<tr><td colspan="8" class="text-center text-muted">No recent game log data. Waiting for match appearance.</td></tr>'
    
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

def write_html_file(p_data):
    player_folder = os.path.join(PLAYERS_DIR, p_data['slug'])
    os.makedirs(player_folder, exist_ok=True)
    
    stats_2026 = p_data.get("stats_2026", {})
    total_stats = stats_2026.get("total", {})
    
    # Extract structural metrics
    gls = total_stats.get("goals", 0)
    ast = total_stats.get("assists", 0)
    rating = total_stats.get("rating", "N/A")
    
    comp_rows_html = build_competition_rows(stats_2026)
    gamelog_rows_html = build_gamelog_rows(p_data.get("recent_games", []))
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    
    <!-- 1. CONVERSATIONAL SEO META TAGS -->
    <title>Is {p_data['name']} Starting Today? Lineup & Stats | Futbol Starting Eleven</title>
    <meta name="description" content="Is {p_data['name']} starting today? Get live matchday lineup status, real-time performance stats, and season overview metrics for {p_data['name']} ({p_data['team_name']}).">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://futbolstartingeleven.com/players/{p_data['slug']}/">

    <!-- 2. OPEN GRAPH META TAGS -->
    <meta property="og:site_name" content="Futbol Starting Eleven">
    <meta property="og:type" content="profile">
    <meta property="og:title" content="Is {p_data['name']} Starting Today? Lineup & Stats | Futbol Starting Eleven">
    <meta property="og:description" content="Live starting lineups, form ratings, and seasonal breakdown for {p_data['name']} at {p_data['team_name']}.">
    <meta property="og:url" content="https://futbolstartingeleven.com/players/{p_data['slug']}/">
    <meta property="og:image" content="https://futbolstartingeleven.com/social-share1.png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">

    <!-- 3. X / TWITTER CARD META TAGS -->
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
                    <div class="sidebar-player-meta"><a href="/lineups/{get_team_slug(p_data['team_name'])}/" class="seo-link fw-bold">{p_data['team_name']}</a> • {p_data['position']}</div>
                    <hr style="border-color: #dee2e6; opacity: 1; margin: 15px 0;">
                    <div class="text-start">
                        <div class="stat-row"><span class="stat-label">Age</span><span class="stat-value">{p_data.get('age', 'N/A')}</span></div>
                        <div class="stat-row"><span class="stat-label">Nationality</span><span class="stat-value">{p_data.get('nationality', 'N/A')}</span></div>
                        <div class="stat-row"><span class="stat-label">Form Rating</span><span class="stat-value text-success">{rating}</span></div>
                    </div>
                </div>
            </div>

            <div class="col-lg-8">
                <!-- CLIENT SIDE REAL-TIME RUNTIME OVERWRITES TARGETED CONTAINER -->
                <div id="live-match-widget" class="info-card border-dark" style="border-left: 5px solid #212529; margin-bottom: 20px;">
                    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
                        <div class="d-flex align-items-center"><span class="fw-bold text-dark" style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px;">Upcoming Matchup</span></div>
                        <div class="stat-value text-end" style="font-size: 0.9rem;">
                            <a href="/lineups/{get_team_slug(p_data['team_name'])}/" class="seo-link fw-bold text-dark">{p_data['team_name']}</a> Match Center <span class="badge bg-dark text-white fw-bold px-2 py-1" style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">Scheduled</span>
                        </div>
                    </div>
                </div>

                <div class="info-card">
                    <h3>2026 Season Overview</h3>
                    <div class="row g-3">
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{total_stats.get('games', 0)}</div><div class="big-stat-label">Matches</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{gls}</div><div class="big-stat-label">Goals</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{ast}</div><div class="big-stat-label">Assists</div></div></div>
                        <div class="col-6 col-sm-3"><div class="big-stat-box"><div class="big-stat-value">{total_stats.get('pass_acc', 0)}%</div><div class="big-stat-label">Pass Acc</div></div></div>
                    </div>
                </div>

                <div class="info-card">
                    <h3>Performance by Competition</h3>
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
                            <tbody>{comp_rows_html}</tbody>
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
                            <tbody>{gamelog_rows_html}</tbody>
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
</body>
</html>"""
    with open(os.path.join(player_folder, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)

def bootstrap_universe():
    print("🛸 DATABASE NOT FOUND! Entering Initial 2026 Roster Bootstrap...")
    database = {}
    
    # Iterate through each defined league
    for league_id in TOP_LEAGUE_IDS:
        print(f"📥 Extracting rosters for League {league_id}...")
        page = 1
        total_pages = 1
        
        while page <= total_pages:
            data = fetch_api(f"players?league={league_id}&season=2026&page={page}")
            if not data or not data.get("response"):
                break
                
            total_pages = data.get("paging", {}).get("total", 1)
            
            for item in data["response"]:
                player = item["player"]
                p_id = str(player["id"])
                
                if not player.get("name") or p_id in database:
                    continue
                    
                stats_list = item.get("statistics", [])
                if not stats_list:
                    continue
                    
                main_stat = stats_list[0]
                team_name = main_stat.get("team", {}).get("name", "Unknown")
                
                # Format core stats object
                enriched_stats = {"total": {}, "competitions": {}}
                # Minimal translation mapping matching your JIT layout framework
                for stat in stats_list:
                    comp_name = stat.get("league", {}).get("name", "Unknown")
                    g = stat.get("games", {}).get("appearences", 0) or 0
                    if g == 0: continue
                    
                    enriched_stats["competitions"][comp_name] = {
                        "games": g,
                        "minutes": stat.get("games", {}).get("minutes", 0),
                        "goals": stat.get("goals", {}).get("total", 0) or 0,
                        "assists": stat.get("goals", {}).get("assists", 0) or 0,
                        "saves": stat.get("goals", {}).get("saves", 0) or 0,
                        "shots_on": stat.get("shots", {}).get("on", 0) or 0,
                        "key_passes": stat.get("passes", {}).get("key", 0) or 0,
                        "pass_acc": stat.get("passes", {}).get("accuracy", 0) or 0,
                        "tackles": stat.get("tackles", {}).get("total", 0) or 0,
                        "interceptions": stat.get("tackles", {}).get("interceptions", 0) or 0,
                        "yellow_cards": stat.get("cards", {}).get("yellow", 0) or 0,
                        "red_cards": stat.get("cards", {}).get("red", 0) or 0,
                        "rating": stat.get("games", {}).get("rating", "N/A")
                    }
                
                # Combine totals
                t_games, t_goals, t_assists = 0, 0, 0
                for c, s in enriched_stats["competitions"].items():
                    t_games += s["games"]
                    t_goals += s["goals"]
                    t_assists += s["assists"]
                enriched_stats["total"] = {"games": t_games, "goals": t_goals, "assists": t_assists, "rating": player.get("rating", "N/A")}

                database[p_id] = {
                    "name": player["name"],
                    "slug": get_player_slug(player["name"]),
                    "team_name": team_name,
                    "position": main_stat.get("games", {}).get("position", "Midfielder"),
                    "photo": player.get("photo", ""),
                    "age": player.get("age", "N/A"),
                    "nationality": player.get("nationality", "N/A"),
                    "stats_2026": enriched_stats,
                    "recent_games": []
                }
            page += 1
            
    with open(DATABASE_PATH, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4)
        
    print(f"🎉 Bootstrap Completed! Indexed {len(database)} players.")
    return database

def process_nightly_maintenance(database):
    print("⚙️ Running Automated Nightly Maintenance Mode...")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_file = os.path.join(DATA_DIR, f"games_{yesterday_str}.json")
    
    if not os.path.exists(yesterday_file):
        print(f"ℹ️ Yesterday's match log file matches_{yesterday_str}.json does not exist. Skipping pipeline queue scan.")
        return
        
    with open(yesterday_file, "r", encoding="utf-8") as f:
        matches = json.load(f)
        
    updated_players = set()
    
    for match in matches:
        status_short = match.get("fixture", {}).get("status", {}).get("short", "NS")
        if status_short not in ["FT", "AET", "PEN"]:
            continue
            
        fixture_id = match["fixture"]["id"]
        print(f"   📊 Processing box scores for Fixture {fixture_id}...")
        
        # Pull player stats directly from the finalized JSON structure
        for side in ["homeLineup", "awayLineup"]:
            lineup_data = match.get(side)
            if not lineup_data:
                continue
                
            team_name = lineup_data.get("team", {}).get("name", "Unknown")
            is_home = (side == "homeLineup")
            opp_name = match["teams"]["away"]["name"] if is_home else match["teams"]["home"]["name"]
            score_line = f"{match['goals']['home']}-{match['goals']['away']}"
            
            # Determine W/D/L status
            res_char = "D"
            if match["goals"]["home"] > match["goals"]["away"]:
                res_char = "W" if is_home else "L"
            elif match["goals"]["away"] > match["goals"]["home"]:
                res_char = "L" if is_home else "W"

            for group in ["startXI", "substitutes"]:
                for slot in lineup_data.get(group, []):
                    player_obj = slot.get("player", {})
                    p_id = str(player_obj.get("id"))
                    
                    if not p_id or p_id == "None":
                        continue
                        
                    live_stats = player_obj.get("live_stats", {})
                    # If they didn't play a single minute, skip log allocation
                    if not live_stats or live_stats.get("rating") == "N/A":
                        continue
                        
                    # Discover unknown players on the fly
                    if p_id not in database:
                        print(f"      🆕 New Player Discovered: {player_obj.get('name')} (ID: {p_id})")
                        database[p_id] = {
                            "name": player_obj.get("name"),
                            "slug": get_player_slug(player_obj.get("name")),
                            "team_name": team_name,
                            "position": player_obj.get("pos", "Midfielder"),
                            "photo": player_obj.get("photo", ""),
                            "age": player_obj.get("age", "N/A"),
                            "nationality": player_obj.get("nationality", "N/A"),
                            "stats_2026": {"total": {}, "competitions": {}},
                            "recent_games": []
                        }
                    
                    # Prepend match stats to rolling queue
                    match_log_entry = {
                        "date": yesterday_str,
                        "opponent_name": opp_name,
                        "is_home": is_home,
                        "result": res_char,
                        "score_line": score_line,
                        "minutes": live_stats.get("minutes", 90),
                        "goals": live_stats.get("goals", 0),
                        "assists": live_stats.get("assists", 0),
                        "rating": live_stats.get("rating", "6.5")
                    }
                    
                    database[p_id]["recent_games"].insert(0, match_log_entry)
                    # Shift tail index out if capacity exceeded
                    if len(database[p_id]["recent_games"]) > 10:
                        database[p_id]["recent_games"].pop()
                        
                    updated_players.add(p_id)
                    
    # Rewrite only pages that were actively involved in yesterday's fixtures
    for p_id in updated_players:
        write_html_file(database[p_id])
        
    with open(DATABASE_PATH, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=4)
        
    print(f"✅ Maintenance complete. Updated {len(updated_players)} profile pages.")

def main():
    if not os.path.exists(DATABASE_PATH):
        database = bootstrap_universe()
        print("📁 Dumping initial batch static pages...")
        for p_id, p_data in database.items():
            write_html_file(p_data)
    else:
        with open(DATABASE_PATH, "r", encoding="utf-8") as f:
            database = json.load(f)
        process_nightly_maintenance(database)
        
    generate_player_sitemap(database)

if __name__ == "__main__":
    main()

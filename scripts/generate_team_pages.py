import os
import re
import json
import unicodedata
import requests
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom

# --- CONFIGURATION ---
API_HOST = "https://v3.football.api-sports.io"
API_KEY = os.environ.get("FOOTBALL_API_KEY", "YOUR_API_KEY_HERE")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.join(SCRIPT_DIR, '..')
LINEUPS_DIR = os.path.join(ROOT_DIR, 'lineups')

# 41 Supported Leagues
TOP_LEAGUE_IDS = [
    39, 40, 140, 135, 78, 61, 88, 94, 203, 144, 179, 119, # Europe
    253, 262, 71, 128, 239, # Americas
    307, 98, 188, 292, # World
    2, 3, 848, 13, 11, 16, 528, 45, 48, 143, 137, 81, # Cups
    1, 4, 9, 5, 531, 10, # International
    254 # Women (NWSL)
]

os.makedirs(LINEUPS_DIR, exist_ok=True)

def fetch_api(endpoint):
    url = f"{API_HOST}/{endpoint}"
    headers = {"x-apisports-key": API_KEY}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"⚠️ API Fetch Failed ({endpoint}): {e}")
        return None

def get_team_slug(full_name):
    slug = full_name.lower()
    
    # Normalize accents/special characters (e.g., Shkodër -> shkoder)
    slug = unicodedata.normalize('NFKD', slug).encode('ascii', 'ignore').decode('utf-8')
    
    # Strip basic punctuation
    slug = slug.replace(".", "").replace("'", "")
    
    # Replace any remaining spaces or non-alphanumerics with a clean hyphen
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    
    return slug

def format_date(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string)
        return dt.strftime("%B %d, %Y")
    except:
        return "Upcoming"

def is_youth_team(team_name):
    pattern = r'\bU-?\d{2}\b'
    if re.search(pattern, team_name, re.IGNORECASE):
        return True
    if "youth" in team_name.lower() or "reserves" in team_name.lower():
        return True
    return False

def generate_team_sitemap(slugs):
    print("🗺️ Generating sitemap-teams.xml...")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    sitemap_path = os.path.join(ROOT_DIR, "sitemap-teams.xml")
    
    ET.register_namespace('', "http://www.sitemaps.org/schemas/sitemap/0.9")
    urlset = ET.Element('urlset', xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    
    for slug in sorted(slugs):
        url = ET.SubElement(urlset, 'url')
        ET.SubElement(url, 'loc').text = f"https://futbolstartingeleven.com/lineups/{slug}/"
        ET.SubElement(url, 'lastmod').text = today_str
        ET.SubElement(url, 'changefreq').text = "daily"
        ET.SubElement(url, 'priority').text = "0.8"
        
    raw_xml = ET.tostring(urlset, 'utf-8')
    parsed_xml = minidom.parseString(raw_xml)
    pretty_xml = "\n".join([line for line in parsed_xml.toprettyxml(indent="  ").splitlines() if line.strip()])
    
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(pretty_xml)
        
    print(f"✅ sitemap-teams.xml saved with {len(slugs)} URLs.")

def generate_team_pages():
    print("🚀 Starting Team Page Generator...")
    
    seen_slugs = set()
    current_year = datetime.now().year
    
    for league_id in TOP_LEAGUE_IDS:
        print(f"\nFetching teams for League ID {league_id}...")
        
        teams_data = fetch_api(f"teams?league={league_id}&season={current_year}")
        
        if not teams_data or not teams_data.get("response"):
            teams_data = fetch_api(f"teams?league={league_id}&season={current_year - 1}")
            
        if not teams_data or not teams_data.get("response"):
            print(f"⚠️ No teams found for League {league_id}. Skipping.")
            continue
            
        for item in teams_data["response"]:
            team = item["team"]
            team_id = team["id"]
            team_name = team["name"]
            
            if is_youth_team(team_name):
                continue
                
            team_logo = team["logo"]
            team_slug = get_team_slug(team_name)
            
            if team_slug in seen_slugs:
                continue
            seen_slugs.add(team_slug)
            
            next_match_data = fetch_api(f"fixtures?team={team_id}&next=1")
            
            next_opponent = "TBD"
            next_date = "Upcoming Match"
            competition = "TBD"
            
            if next_match_data and next_match_data.get("response"):
                match = next_match_data["response"][0]
                home_team = match["teams"]["home"]["name"]
                away_team = match["teams"]["away"]["name"]
                competition = match["league"]["name"]
                next_date = format_date(match["fixture"]["date"])
                
                if home_team == team_name:
                    next_opponent = f"vs {away_team}"
                else:
                    next_opponent = f"@ {home_team}"
            
            print(f"   ✅ Generating /lineups/{team_slug}/")
            
            team_folder = os.path.join(LINEUPS_DIR, team_slug)
            os.makedirs(team_folder, exist_ok=True)
            
            html_content = build_html(team_id, team_name, team_logo, team_slug, next_opponent, next_date, competition)
            
            with open(os.path.join(team_folder, "index.html"), "w", encoding="utf-8") as f:
                f.write(html_content)

    print(f"\n🎉 Finished! Generated {len(seen_slugs)} unique team lineup pages.")
    generate_team_sitemap(seen_slugs)

def build_html(team_id, team_name, team_logo, team_slug, next_opponent, next_date, competition):
    page_title = f"{team_name} Starting Lineup Today | Futbol Starting Eleven"
    page_desc = f"Get the official {team_name} starting lineup, live match stats, and tactical formation. Next match: {team_name} {next_opponent} in {competition} on {next_date}."
    page_url = f"https://futbolstartingeleven.com/lineups/{team_slug}/"
    social_image = "https://futbolstartingeleven.com/social-share1.png"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    
    <!-- SEO META TAGS -->
    <title>{page_title}</title>
    <meta name="description" content="{page_desc}">
    <meta name="keywords" content="{team_name} lineup, {team_name} starting 11, {team_name} formation, {team_name} next match, {team_name} {next_opponent}, soccer lineups, tactical board">
    <link rel="canonical" href="{page_url}" />
    
    <!-- OPEN GRAPH & TWITTER CARDS -->
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Futbol Starting Eleven">
    <meta property="og:url" content="{page_url}">
    <meta property="og:title" content="{page_title}">
    <meta property="og:description" content="{page_desc}">
    <meta property="og:image" content="{social_image}">
    
    <meta name="twitter:card" content="summary">
    <meta name="twitter:domain" content="futbolstartingeleven.com">
    <meta name="twitter:url" content="{page_url}">
    <meta name="twitter:title" content="{page_title}">
    <meta name="twitter:description" content="{page_desc}">
    <meta name="twitter:image" content="{social_image}">
    
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://www.gstatic.com/firebasejs/8.10.1/firebase-app.js"></script>
    <script src="https://www.gstatic.com/firebasejs/8.10.1/firebase-database.js"></script>
    
    <style>
        body {{ background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow-x: hidden; }}
        
        .header-brand {{ font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; font-style: italic; text-shadow: 0 2px 4px rgba(0,0,0,0.5); }}
        .header-brand a {{ color: inherit; }}
        .header-brand span {{ text-shadow: none !important; background: linear-gradient(to bottom, #20c997 0%, #198754 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; filter: drop-shadow(0 0 12px rgba(32, 201, 151, 0.6)); }}

        .pitch-wrapper {{ width: 100%; max-width: 650px; margin: 0 auto; position: relative; overflow: hidden; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.15); }}

        #capture-area {{ width: 1080px; height: 1200px; background: radial-gradient(circle at center, #1a2235 0%, #080a0f 100%); position: absolute; top: 0; left: 0; display: flex; flex-direction: column; align-items: center; transform-origin: top left; }}

        #header {{ width: 100%; padding: 10px 40px 5px 40px; display: flex; flex-direction: row; justify-content: center; align-items: center; gap: 25px; z-index: 10; box-sizing: border-box; background: linear-gradient(to bottom, rgba(0,0,0,0.9) 0%, rgba(0,0,0,0) 100%); }}
        .team-logo {{ width: 85px; height: 85px; object-fit: contain; filter: drop-shadow(0 6px 15px rgba(0,0,0,0.6)); }}
        .header-text {{ display: flex; flex-direction: column; align-items: flex-start; }}
        .team-name {{ font-size: 42px; font-weight: 900; text-transform: uppercase; letter-spacing: 2px; margin: 0; line-height: 1; color: white;}}
        .formation {{ font-size: 22px; font-weight: bold; color: #20c997; margin-top: 6px; letter-spacing: 1px; }}

        #scene {{ width: 100%; height: 1080px; position: absolute; bottom: 15px; display: flex; justify-content: center; align-items: flex-end; }}
        #pitch {{ width: 980px; height: 1060px; background: repeating-linear-gradient(0deg, #1e4d2b, #1e4d2b 80px, #1a4224 80px, #1a4224 160px); position: relative; border: 5px solid rgba(255,255,255,0.6); border-top: 8px solid rgba(255,255,255,0.8); box-shadow: 0 10px 30px rgba(0,0,0,0.8); border-radius: 4px; }}
        
        .pitch-line {{ position: absolute; border: 3px solid rgba(255,255,255,0.5); z-index: 2; }}
        .center-circle-half {{ width: 280px; height: 140px; border: 4px solid rgba(255,255,255,0.6); border-top: none; border-radius: 0 0 140px 140px; position: absolute; top: 0; left: 50%; transform: translateX(-50%); z-index: 2; }}
        .penalty-box-bottom {{ width: 500px; height: 180px; bottom: 0; left: 50%; transform: translateX(-50%); border-bottom: none; }}
        .six-yard-bottom {{ width: 250px; height: 70px; bottom: 0; left: 50%; transform: translateX(-50%); border-bottom: none; position: absolute; border: 3px solid rgba(255,255,255,0.5); z-index: 2;}}
        .penalty-arc-bottom {{ width: 180px; height: 100px; bottom: 180px; left: 50%; transform: translateX(-50%); border: 3px solid rgba(255,255,255,0.5); border-bottom: none; border-radius: 90px 90px 0 0; position: absolute; border-bottom-color: transparent; z-index: 2;}}

        .watermark {{ position: absolute; width: 700px; height: 700px; object-fit: contain; opacity: 0.15; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 1; pointer-events: none; }}

        .player-node {{ position: absolute; width: 160px; display: flex; flex-direction: column; align-items: center; transform: translate(-50%, -50%); transition: all 0.5s ease; }}
        .player-photo-container {{ width: 120px; height: 120px; border-radius: 50%; border: 5px solid var(--node-color, #ffffff); background-color: #2b3035; box-shadow: 0 8px 16px rgba(0,0,0,0.8); z-index: 3; overflow: hidden; display: flex; justify-content: center; align-items: center; position: relative; }}
        .player-photo {{ width: 100%; height: 100%; object-fit: cover; }}
        .fallback-initials {{ font-size: 40px; font-weight: bold; color: #adb5bd; }}
        .player-number {{ position: absolute; top: -4px; right: 4px; background-color: #111; color: white; border: 3px solid var(--node-color, #ffffff); width: 32px; height: 32px; border-radius: 50%; display: flex; justify-content: center; align-items: center; font-size: 16px; font-weight: 900; z-index: 4; box-shadow: 0 2px 5px rgba(0,0,0,0.5); }}
        .player-nameplate {{ margin-top: -12px; background: rgba(0, 0, 0, 0.95); border: 1px solid rgba(255,255,255,0.4); padding: 4px 10px; border-radius: 8px; font-size: 20px; font-weight: 900; color: white; text-transform: uppercase; letter-spacing: 0.5px; z-index: 4; white-space: nowrap; box-shadow: 0 4px 8px rgba(0,0,0,0.7); }}

        @media (max-width: 576px) {{ .header-brand {{ font-size: 1.5rem; }} }}
    </style>
</head>
<body>

    <nav class="navbar sticky-top shadow-sm pt-2 pb-2 mb-2" style="background-color: #212529; z-index: 1050;">
        <div class="container d-flex justify-content-between align-items-center flex-wrap">
            <div class="header-brand">
                <a href="/" class="text-decoration-none">Futbol Starting <span>Eleven</span></a>
            </div>
            <div class="d-flex align-items-center gap-2">
                <a href="/" class="btn btn-sm btn-outline-light fw-bold" style="font-size:0.75rem;">← Back to Matches</a>
            </div>
        </div>
    </nav>

    <div class="container mb-2">
        <div class="text-center mb-2 mt-0">
            <h2 class="h5 fw-bold text-dark m-0">{team_name} Starting Lineup & Tactics</h2>
        </div>

        <div class="pitch-wrapper" id="pitch-wrapper">
            <div id="capture-area">
                
                <div id="header">
                    <img id="team-logo" class="team-logo" src="{team_logo}" alt="{team_name} Logo">
                    <div class="header-text">
                        <h1 id="team-name" class="team-name">{team_name}</h1>
                        <div id="team-formation" class="formation">Next Match: {next_opponent} • {next_date}</div>
                    </div>
                </div>

                <div id="scene">
                    <div id="pitch">
                        <img id="team-watermark" class="watermark" src="{team_logo}" alt="Watermark">
                        <div class="center-circle-half"></div>
                        <div class="pitch-line penalty-box-bottom"></div>
                        <div class="six-yard-bottom"></div>
                        <div class="penalty-arc-bottom"></div>
                        
                        <div id="players-container">
                            <div class="position-absolute top-50 start-50 translate-middle text-center text-white" style="z-index: 10;">
                                <h3 class="fw-bold" style="text-shadow: 0 2px 4px rgba(0,0,0,0.8);">Awaiting Live Lineup Data</h3>
                                <p class="text-light" style="text-shadow: 0 2px 4px rgba(0,0,0,0.8);">The tactical board will populate as soon as lineups are released.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        window.TARGET_TEAM_ID = {team_id};
        window.TARGET_TEAM_NAME = "{team_name}";
        
        function resizePitch() {{
            const wrapper = document.getElementById('pitch-wrapper');
            const pitch = document.getElementById('capture-area');
            
            const maxWidth = wrapper.clientWidth;
            const wrapperTopOffset = wrapper.getBoundingClientRect().top;
            const safeTop = wrapperTopOffset > 0 ? wrapperTopOffset : 100;
            const maxHeight = window.innerHeight - safeTop - 20; 
            
            const scaleWidth = maxWidth / 1080;
            const scaleHeight = maxHeight / 1200; 
            
            const finalScale = Math.min(scaleWidth, scaleHeight);
            
            pitch.style.transform = `scale(${{finalScale}})`;
            wrapper.style.width = `${{1080 * finalScale}}px`;
            wrapper.style.height = `${{1200 * finalScale}}px`; 
        }}

        window.addEventListener('resize', resizePitch);
        window.addEventListener('DOMContentLoaded', resizePitch);
    </script>
    
    <script src="../../js/team_lineups.js"></script>

</body>
</html>"""

if __name__ == "__main__":
    generate_team_pages()

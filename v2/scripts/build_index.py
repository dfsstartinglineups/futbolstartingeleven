import os
import re
import requests
from datetime import datetime, timedelta
import pytz
from jinja2 import Template

# 1. NO DICTIONARY. Just a flat list of ESPN league codes you want to fetch.
# You can add 50+ leagues here without ever worrying about mapping them.
ESPN_LEAGUES = [
    "eng.1", 
    "esp.1", 
    "ita.1", 
    "uefa.champions", 
    "usa.1"
]

# The complete HTML, CSS, and JS injected as a single Jinja2 string
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Futbol Starting Eleven | Live Soccer Starting Lineups & Scores</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        .header-brand { font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; font-style: italic; }
        .header-brand span { color: #20c997; }
        .nav-btn { font-size: 0.85rem; font-weight: 700; border-radius: 20px; }
    </style>
</head>
<body>

<nav class="navbar sticky-top shadow-sm pt-2 pb-2 mb-0" style="background-color: #212529;">
    <div class="container d-flex justify-content-center">
        <div class="header-brand">
            Futbol Starting <span>Eleven</span>
        </div>
    </div>
</nav>

<!-- Dynamic Navigation Menu -->
<div class="container mt-4 mb-3 text-center" id="day-navigation">
    <button class="btn btn-outline-dark mx-1 px-4 py-1 nav-btn" data-target="yesterday">Yesterday</button>
    <button class="btn btn-dark mx-1 px-4 py-1 nav-btn active" data-target="today">Today</button>
    <button class="btn btn-outline-dark mx-1 px-4 py-1 nav-btn" data-target="tomorrow">Tomorrow</button>
</div>

<div class="container pb-5">
    
    <!-- YESTERDAY PARTITION -->
    <div id="view-yesterday" class="day-partition d-none">
        <div class="row justify-content-center">
            <div class="col-12 col-md-8">
                {% for game in yesterday_games %}
                    <div class="card shadow-sm border-0 mb-2 p-3">
                        <div class="text-muted" style="font-size: 0.75rem;">{{ game.dynamic_league_name }}</div>
                        <div class="fw-bold">{{ game.name }}</div>
                    </div>
                {% else %}
                    <div class="text-center text-muted mt-4">No priority matches scheduled.</div>
                {% endfor %}
            </div>
        </div>
    </div>

    <!-- TODAY PARTITION (Visible by Default) -->
    <div id="view-today" class="day-partition">
        <h6 class="text-center text-muted mb-3 fw-bold">{{ current_date_display }}</h6>
        <div class="row justify-content-center">
            <div class="col-12 col-md-8">
                {% for game in today_games %}
                    <div class="card shadow-sm border-0 mb-2 p-3">
                        <!-- Notice how it uses the dynamically mapped names -->
                        <div class="text-muted text-uppercase fw-bold" style="font-size: 0.70rem;">
                            <a href="/leagues/{{ game.dynamic_league_slug }}/" class="text-decoration-none text-muted">
                                {{ game.dynamic_league_name }}
                            </a>
                        </div>
                        <div class="fw-bold">{{ game.name }}</div>
                    </div>
                {% else %}
                    <div class="text-center text-muted mt-4">No priority matches scheduled for today.</div>
                {% endfor %}
            </div>
        </div>
    </div>

    <!-- TOMORROW PARTITION -->
    <div id="view-tomorrow" class="day-partition d-none">
        <div class="row justify-content-center">
            <div class="col-12 col-md-8">
                {% for game in tomorrow_games %}
                    <div class="card shadow-sm border-0 mb-2 p-3">
                        <div class="text-muted" style="font-size: 0.75rem;">{{ game.dynamic_league_name }}</div>
                        <div class="fw-bold">{{ game.name }}</div>
                    </div>
                {% else %}
                    <div class="text-center text-muted mt-4">No priority matches scheduled.</div>
                {% endfor %}
            </div>
        </div>
    </div>

</div>

<!-- Inline JavaScript for UI Toggles -->
<script>
    document.addEventListener('DOMContentLoaded', () => {
        const navButtons = document.querySelectorAll('.nav-btn');
        const partitions = document.querySelectorAll('.day-partition');

        navButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetView = e.target.getAttribute('data-target');

                partitions.forEach(p => p.classList.add('d-none'));
                document.getElementById('view-' + targetView).classList.remove('d-none');

                navButtons.forEach(b => {
                    b.classList.remove('btn-dark', 'active');
                    b.classList.add('btn-outline-dark');
                });
                e.target.classList.remove('btn-outline-dark');
                e.target.classList.add('btn-dark', 'active');
            });
        });
    });
</script>
</body>
</html>
"""

def create_slug(name):
    """The Python port of your frontend slugifier logic."""
    if not name:
        return ""
    slug = name.lower().replace('/', '-')
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')

def get_match_dates():
    """Calculates Yesterday, Today, and Tomorrow using a 3:00 AM EST cutoff."""
    est = pytz.timezone('America/New_York')
    now = datetime.now(est)
    
    if now.hour < 3:
        now -= timedelta(days=1)
        
    return {
        "yesterday": (now - timedelta(days=1)).strftime('%Y%m%d'),
        "today": now.strftime('%Y%m%d'),
        "tomorrow": (now + timedelta(days=1)).strftime('%Y%m%d'),
        "display_date": now.strftime('%A, %b %d')
    }

def fetch_espn_scores(date_str):
    """Fetches the scoreboard and dynamically grabs the league names."""
    daily_matches = []
    
    for espn_slug in ESPN_LEAGUES:
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{espn_slug}/scoreboard?dates={date_str}"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                
                # 2. Dynamically grab ESPN's display name for this league
                if 'leagues' in data and len(data['leagues']) > 0:
                    league_name = data['leagues'][0]['name']
                    
                    # 3. Create the clean folder URL automatically
                    clean_slug = create_slug(league_name)
                    
                    if 'events' in data:
                        for event in data['events']:
                            # Inject our dynamic properties directly into the event object
                            event['dynamic_league_slug'] = clean_slug
                            event['dynamic_league_name'] = league_name
                            daily_matches.append(event)
        except Exception as e:
            print(f"Error fetching {espn_slug} for {date_str}: {e}")
            
    return daily_matches

def generate_v2_index():
    """Main function to pull data, render the template string, and write the file."""
    print("Fetching dynamic data from ESPN...")
    dates = get_match_dates()
    
    match_data = {
        "yesterday": fetch_espn_scores(dates["yesterday"]),
        "today": fetch_espn_scores(dates["today"]),
        "tomorrow": fetch_espn_scores(dates["tomorrow"])
    }
    
    template = Template(HTML_TEMPLATE)
    output_html = template.render(
        yesterday_games=match_data["yesterday"],
        today_games=match_data["today"],
        tomorrow_games=match_data["tomorrow"],
        current_date_display=dates["display_date"]
    )
    
    os.makedirs('v2', exist_ok=True)
    file_path = 'v2/index.html'
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(output_html)
    
    print(f"Successfully compiled static frontend to {file_path}")

if __name__ == "__main__":
    generate_v2_index()

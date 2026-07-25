import os
import re
import json
import requests
from datetime import datetime, timedelta
import pytz
from jinja2 import Template

def create_slug(name):
    """Generates clean URL slugs directly from ESPN league display names."""
    if not name:
        return ""
    slug = name.lower()
    slug = re.sub(r'[\/]', '-', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')

def get_3day_dates():
    """Calculates Yesterday, Today, and Tomorrow using a strict 3:00 AM EST cutoff."""
    est = pytz.timezone('America/New_York')
    now = datetime.now(est)
    
    # 3:00 AM EST Cutoff Shift
    if now.hour < 3:
        now -= timedelta(days=1)
        
    y_dt = now - timedelta(days=1)
    t_dt = now
    tm_dt = now + timedelta(days=1)
    
    return {
        "dates": {
            "yesterday": y_dt.strftime('%Y%m%d'),
            "today": t_dt.strftime('%Y%m%d'),
            "tomorrow": tm_dt.strftime('%Y%m%d')
        },
        "display": {
            "yesterday": y_dt.strftime('%a, %b %d'),
            "today": t_dt.strftime('%a, %b %d'),
            "tomorrow": tm_dt.strftime('%a, %b %d')
        }
    }

def fetch_espn_scores_for_date(date_str):
    """Fetches ALL soccer matches from ESPN across all leagues for a specific date."""
    # CRITICAL: limit=500 prevents ESPN from capping the payload at 25/50 matches
    urls = [
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}&limit=500",
        f"https://site.api.espn.com/apis/site/v2/sports/soccer/scoreboard?dates={date_str}&limit=500"
    ]
    
    raw_events = []
    headers = {'User-Agent': 'Mozilla/5.0'}

    for url in urls:
        try:
            res = requests.get(url, headers=headers, timeout=12)
            if res.status_code == 200:
                data = res.json()
                events = data.get('events', [])
                if events:
                    raw_events = events
                    break
        except Exception as e:
            print(f"⚠️ Warning fetching endpoint {url}: {e}")

    matches = []
    for event in raw_events:
        try:
            competitions = event.get('competitions', [])
            if not competitions:
                continue

            comp = competitions[0]
            competitors = comp.get('competitors', [])
            
            home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
            away = next((c for c in competitors if c.get('homeAway') == 'away'), None)

            if not home or not away:
                continue

            # Robust multi-path extraction for ESPN league display name
            league_obj = (
                event.get('league') or 
                comp.get('league') or 
                (event.get('leagues', [{}])[0] if event.get('leagues') else {})
            )
            league_name = (
                league_obj.get('name') or 
                league_obj.get('displayName') or 
                league_obj.get('midsizeName') or 
                "Soccer"
            )
            league_slug = create_slug(league_name)

            status_type = event.get('status', {}).get('type', {})
            status_short = status_type.get('shortDetail', 'NS')
            elapsed = event.get('status', {}).get('period', 0)

            # Extract Goals, Cards, and Substitutions
            events_list = []
            for detail in comp.get('details', []):
                det_text = detail.get('type', {}).get('text', '')
                team_id = detail.get('team', {}).get('id', '')
                clock = detail.get('clock', {}).get('displayValue', "0'")
                participants = detail.get('participants', [])
                p_name = participants[0].get('athlete', {}).get('displayName', 'Unknown') if participants else 'Unknown'

                events_list.append({
                    "time": clock.replace("'", ""),
                    "team_id": team_id,
                    "type": "Goal" if "Goal" in det_text else ("subst" if "Substitution" in det_text else "Card"),
                    "detail": det_text,
                    "player": p_name
                })

            # Extract Betting Odds
            odds_data = {"home": "TBD", "draw": "TBD", "away": "TBD"}
            if comp.get('odds'):
                raw_odds = comp['odds'][0]
                odds_data["home"] = str(raw_odds.get('homeTeamOdds', {}).get('summary', '-'))
                odds_data["draw"] = str(raw_odds.get('drawOdds', {}).get('summary', '-'))
                odds_data["away"] = str(raw_odds.get('awayTeamOdds', {}).get('summary', '-'))

            # Extract Starting XI Rosters
            home_lineup = {"formation": home.get('form', '4-3-3'), "startXI": []}
            away_lineup = {"formation": away.get('form', '4-3-3'), "startXI": []}

            for athlete in home.get('roster', []):
                home_lineup["startXI"].append({
                    "player": {
                        "id": athlete.get('athlete', {}).get('id', ''),
                        "name": athlete.get('athlete', {}).get('displayName', ''),
                        "pos": athlete.get('position', {}).get('abbreviation', 'M'),
                        "number": athlete.get('jersey', ''),
                        "photo": athlete.get('athlete', {}).get('headshot', {}).get('href', '')
                    }
                })

            for athlete in away.get('roster', []):
                away_lineup["startXI"].append({
                    "player": {
                        "id": athlete.get('athlete', {}).get('id', ''),
                        "name": athlete.get('athlete', {}).get('displayName', ''),
                        "pos": athlete.get('position', {}).get('abbreviation', 'M'),
                        "number": athlete.get('jersey', ''),
                        "photo": athlete.get('athlete', {}).get('headshot', {}).get('href', '')
                    }
                })

            matches.append({
                "fixture": {
                    "id": event['id'],
                    "date": event['date'],
                    "status": {"short": status_short, "elapsed": elapsed}
                },
                "league": {
                    "name": league_name,
                    "slug": league_slug
                },
                "teams": {
                    "home": {
                        "id": home['team']['id'],
                        "name": home['team']['displayName'],
                        "logo": home['team'].get('logo', ''),
                        "rank": home.get('curatedRank', {}).get('current', '')
                    },
                    "away": {
                        "id": away['team']['id'],
                        "name": away['team']['displayName'],
                        "logo": away['team'].get('logo', ''),
                        "rank": away.get('curatedRank', {}).get('current', '')
                    }
                },
                "goals": {
                    "home": home.get('score', 0),
                    "away": away.get('score', 0)
                },
                "homeLineup": home_lineup if home_lineup["startXI"] else None,
                "awayLineup": away_lineup if away_lineup["startXI"] else None,
                "events": events_list,
                "odds": odds_data
            })
        except Exception as e:
            print(f"⚠️ Error parsing match {event.get('id', 'unknown')}: {e}")

    return matches

# Complete Version 1 HTML, CSS, and JS Skeleton embedded directly
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#212529">
    <title>Futbol Starting Eleven | Live Soccer Starting Lineups, Scores & Odds</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    
    <style>
        body { background-color: #f1f3f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
        
        .header-brand { 
            font-weight: 900; letter-spacing: -1px; font-size: 2rem; color: #fff; 
            font-style: italic; text-shadow: 0 2px 4px rgba(0,0,0,0.5); 
        }
        .header-brand a { color: inherit; }
        .header-brand span { 
            text-shadow: none !important;
            background: linear-gradient(to bottom, #20c997 0%, #198754 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text; filter: drop-shadow(0 0 12px rgba(32, 201, 151, 0.6));
        }

        .day-tab-btn {
            font-size: 0.85rem; font-weight: 700; border-radius: 20px; padding: 6px 18px; transition: all 0.2s;
        }
        
        .lineup-card { 
            background: #fff; border: 1px solid #dee2e6; border-radius: 12px; 
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 12px; overflow: hidden;
        }

        .team-logo { width: 45px; height: 45px; object-fit: contain; filter: drop-shadow(0px 2px 2px rgba(0,0,0,0.1)); }
        
        .batting-order { padding-left: 0; list-style-type: none; margin-bottom: 0; }
        .batting-order li {
            padding: 6px 12px; font-size: 0.85rem; border-bottom: 1px solid #f1f3f5;
            display: flex; justify-content: space-between; align-items: center;
        }
        .batting-order li:last-child { border-bottom: none; }
        .batter-name { font-weight: 600; color: #495057; }

        #team-search { 
            color: #ffffff !important; color-scheme: dark; width: 45px;
            transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            background-color: #343a40; border: 1px solid #495057; cursor: pointer;
        }
        #team-search:focus { 
            width: 160px; background-color: #495057 !important; border-color: #20c997 !important; 
            box-shadow: 0 0 0 0.2rem rgba(32, 201, 151, 0.25) !important; cursor: text;
        }

        .live-dot {
            display: inline-block; width: 7px; height: 7px; background-color: #fff;
            border-radius: 50%; margin-right: 5px; margin-bottom: 1px; animation: pulse-green 2s infinite;
        }
        @keyframes pulse-green {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(32, 201, 151, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0); }
        }
    </style>
</head>
<body>

<nav class="navbar sticky-top shadow-sm pt-2 pb-2 mb-0" style="background-color: #212529; z-index: 1050;">
    <div class="container d-flex justify-content-between align-items-center">
        <div class="header-brand">
            <a href="/" class="text-decoration-none">Futbol Starting <span>Eleven</span></a>
        </div>
        <div class="d-flex align-items-center gap-2">
            <input type="text" id="team-search" class="form-control form-control-sm" placeholder="🔍 Search...">
        </div>
    </div>
</nav>

<div class="container mt-3 mb-2 text-center">
    <h1 class="h5 fw-bold text-dark mb-1">Futbol Starting Eleven: Live Soccer Starting Lineups, Scores & Odds</h1>
    <p class="text-muted mb-2" style="font-size: 0.85rem;">Real-time starting XIs, match injuries, goalscorers, and betting odds for global football.</p>
    
    <!-- 3-Day Window Navigation Buttons -->
    <div class="d-flex justify-content-center gap-2 my-3" id="day-selector">
        <button class="btn btn-outline-dark day-tab-btn" data-day="yesterday">
            Yesterday<br><small style="font-size: 0.65rem;">{{ display_dates.yesterday }}</small>
        </button>
        <button class="btn btn-dark day-tab-btn active" data-day="today">
            Today<br><small style="font-size: 0.65rem;">{{ display_dates.today }}</small>
        </button>
        <button class="btn btn-outline-dark day-tab-btn" data-day="tomorrow">
            Tomorrow<br><small style="font-size: 0.65rem;">{{ display_dates.tomorrow }}</small>
        </button>
    </div>

    <div class="text-center mt-2">
        <button id="toggle-all-cards" class="btn btn-sm btn-dark text-white shadow-sm px-3 py-1 me-2" style="font-size: 0.70rem; font-weight: 700; border-radius: 20px;">
            🔽 COMPACT SCOREBOARD
        </button>
        <button id="toggle-all-lineups" class="btn btn-sm btn-dark text-white shadow-sm px-3 py-1 d-none" style="font-size: 0.70rem; font-weight: 700; border-radius: 20px;">
            🔼 COLLAPSE ALL LINEUPS
        </button>
    </div>
</div>

<div class="container pb-5">
    <div id="games-container" class="row justify-content-center"></div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

<script>
    // Embedded Data Payload
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

    function getTimeBadgeHtml(data) {
        const status = data.fixture.status.short;
        if (['FT', 'AET', 'PEN'].includes(status)) {
            return `<span class="badge bg-dark text-white border px-2 py-1">FT</span>`;
        } else if (status === 'HT') {
            return `<span class="badge bg-success text-white border px-2 py-1"><span class="live-dot"></span>HT</span>`;
        } else if (!['NS', 'TBD'].includes(status)) {
            return `<span class="badge bg-success text-white border px-2 py-1"><span class="live-dot"></span>LIVE</span>`;
        }
        return `<span class="badge bg-white text-dark border px-2 py-1">${status}</span>`;
    }

    function buildLineupList(lineupData) {
        if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) {
            return `<div class="p-3 text-center text-muted small fst-italic">Lineup pending...</div>`;
        }
        const formationHeader = `<div class="w-100 text-center py-1 fw-bold text-white bg-success" style="font-size: 0.65rem;">✅ ${lineupData.formation || '4-3-3'}</div>`;
        const listItems = lineupData.startXI.map(slot => {
            const p = slot.player;
            const originalName = p.name || 'Unknown';
            const displaySafeName = shortenPlayerName(originalName);
            const photoHtml = p.photo ? `<img src="${p.photo}" style="width: 22px; height: 22px; border-radius: 50%; object-fit: cover;" class="me-2">` : `<div style="width:22px; height:22px; border-radius:50%; background:#e9ecef;" class="me-2 d-inline-block"></div>`;
            return `
                <li class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="font-size: 0.8rem;">
                    <span class="text-muted fw-bold me-2" style="font-size: 0.65rem; width: 12px;">${p.pos || 'M'}</span>
                    ${photoHtml}
                    <span class="batter-name text-dark text-truncate">${displaySafeName}</span>
                    <span class="ms-auto text-muted" style="font-size: 0.65rem;">#${p.number || ''}</span>
                </li>`;
        }).join('');
        return `${formationHeader}<ul class="batting-order w-100 m-0 p-0">${listItems}</ul>`;
    }

    function createGameCard(data) {
        const gameCard = document.createElement('div');
        gameCard.className = 'col-md-6 col-lg-6 col-xl-4 mb-3';
        const home = data.teams.home;
        const away = data.teams.away;
        const fixId = data.fixture.id;

        const homeScore = data.goals ? data.goals.home : 0;
        const awayScore = data.goals ? data.goals.away : 0;

        const fullHtml = `
            <div class="p-2 pb-1" style="background-color: #fcfcfc;">
                <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom" style="cursor: pointer;" onclick="toggleSingleCard('${fixId}')">
                    <div class="pe-2">${getTimeBadgeHtml(data)}</div>
                    <div class="text-muted fw-bold text-uppercase text-end ms-auto text-truncate" style="font-size: 0.70rem;">
                        ${data.league.name}
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center px-1 py-1 w-100">
                    <div class="text-center" style="width: 35%;">
                        <img src="${home.logo}" alt="${home.name}" class="team-logo mb-1">
                        <div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">${home.name}</div>
                    </div>
                    <div class="text-center fw-bold text-dark" style="font-size: 1.2rem; width: 30%;">
                        ${homeScore} - ${awayScore}
                    </div>
                    <div class="text-center" style="width: 35%;">
                        <img src="${away.logo}" alt="${away.name}" class="team-logo mb-1">
                        <div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">${away.name}</div>
                    </div>
                </div>
            </div>
            <div class="collapse ${globalLineupsExpanded ? 'show' : ''} lineup-container" id="lineup-collapse-${fixId}">
                <div class="row g-0 bg-white border-top">
                    <div class="col-6 border-end">${buildLineupList(data.homeLineup)}</div>
                    <div class="col-6">${buildLineupList(data.awayLineup)}</div>
                </div>
            </div>`;

        const ribbonHtml = `
            <div class="row g-0 align-items-center py-2 px-2" style="cursor: pointer;" onclick="toggleSingleCard('${fixId}')">
                <div class="col-3 text-center border-end pe-1">
                    ${getTimeBadgeHtml(data)}
                    <div class="text-muted fw-bold text-truncate" style="font-size: 0.6rem;">${data.league.name}</div>
                </div>
                <div class="col-9 ps-2">
                    <div class="d-flex justify-content-between align-items-center">
                        <span class="fw-bold text-truncate" style="font-size: 0.8rem;"><img src="${home.logo}" width="14" class="me-1">${home.name}</span>
                        <span class="fw-bold">${homeScore}</span>
                    </div>
                    <div class="d-flex justify-content-between align-items-center mt-1">
                        <span class="fw-bold text-truncate" style="font-size: 0.8rem;"><img src="${away.logo}" width="14" class="me-1">${away.name}</span>
                        <span class="fw-bold">${awayScore}</span>
                    </div>
                </div>
            </div>`;

        gameCard.innerHTML = `
            <div class="lineup-card shadow-sm" id="card-${fixId}">
                <div class="ribbon-view ${globalScoreboardMode ? '' : 'd-none'}" id="ribbon-${fixId}">${ribbonHtml}</div>
                <div class="full-view ${globalScoreboardMode ? 'd-none' : ''}" id="full-${fixId}">${fullHtml}</div>
            </div>`;
        return gameCard;
    }

    window.toggleSingleCard = function(fixId) {
        const ribbon = document.getElementById(`ribbon-${fixId}`);
        const full = document.getElementById(`full-${fixId}`);
        if (ribbon && full) {
            ribbon.classList.toggle('d-none');
            full.classList.toggle('d-none');
        }
    };

    function renderGames() {
        const container = document.getElementById('games-container');
        container.innerHTML = '';
        const searchInput = document.getElementById('team-search');
        const searchText = searchInput ? searchInput.value.toLowerCase() : '';
        const dayMatches = STATIC_MATCHES[ACTIVE_DAY] || [];

        let filtered = dayMatches.filter(m => {
            const matchStr = (m.teams.home.name + " " + m.teams.away.name + " " + m.league.name).toLowerCase();
            return matchStr.includes(searchText);
        });

        if (filtered.length === 0) {
            container.innerHTML = `
                <div class="col-12 text-center mt-5">
                    <div class="card p-4 shadow-sm border-0">
                        <div class="h4 text-muted">🏟️ No matches found.</div>
                        <p class="text-muted">Pick another date tab above.</p>
                    </div>
                </div>`;
            return;
        }

        filtered.forEach(item => container.appendChild(createGameCard(item)));
    }

    document.addEventListener('DOMContentLoaded', () => {
        renderGames();

        // 3-Day Navigation Event Listeners
        document.querySelectorAll('.day-tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.day-tab-btn').forEach(b => {
                    b.classList.remove('btn-dark', 'active');
                    b.classList.add('btn-outline-dark');
                });
                const targetBtn = e.target.closest('.day-tab-btn');
                targetBtn.classList.remove('btn-outline-dark');
                targetBtn.classList.add('btn-dark', 'active');

                ACTIVE_DAY = targetBtn.getAttribute('data-day');
                renderGames();
            });
        });

        // Search Filter Listener
        const searchInput = document.getElementById('team-search');
        if (searchInput) searchInput.addEventListener('input', renderGames);

        // Scoreboard Display Mode Toggle
        const toggleScoreboardBtn = document.getElementById('toggle-all-cards');
        const toggleAllBtn = document.getElementById('toggle-all-lineups');

        if (toggleScoreboardBtn) {
            toggleScoreboardBtn.addEventListener('click', () => {
                globalScoreboardMode = !globalScoreboardMode;
                toggleScoreboardBtn.innerHTML = globalScoreboardMode ? '🔼 EXPAND ALL CARDS' : '🔽 COMPACT SCOREBOARD';
                
                document.querySelectorAll('.ribbon-view').forEach(el => el.classList.toggle('d-none', !globalScoreboardMode));
                document.querySelectorAll('.full-view').forEach(el => el.classList.toggle('d-none', globalScoreboardMode));
                if (toggleAllBtn) toggleAllBtn.classList.toggle('d-none', globalScoreboardMode);
            });
        }
    });
</script>
</body>
</html>
"""

def generate_v2_index():
    """Main build execution."""
    print("⏳ Calculating 3-day dates with 3:00 AM EST cutoff...")
    day_info = get_3day_dates()
    
    print("🚀 Fetching all ESPN soccer scores for Yesterday, Today, and Tomorrow...")
    matches_by_day = {
        "yesterday": fetch_espn_scores_for_date(day_info["dates"]["yesterday"]),
        "today": fetch_espn_scores_for_date(day_info["dates"]["today"]),
        "tomorrow": fetch_espn_scores_for_date(day_info["dates"]["tomorrow"])
    }
    
    print(f"✅ Yesterday ({day_info['dates']['yesterday']}): {len(matches_by_day['yesterday'])} matches")
    print(f"✅ Today ({day_info['dates']['today']}):     {len(matches_by_day['today'])} matches")
    print(f"✅ Tomorrow ({day_info['dates']['tomorrow']}):  {len(matches_by_day['tomorrow'])} matches")
    
    template = Template(HTML_TEMPLATE)
    output_html = template.render(
        matches_json=json.dumps(matches_by_day),
        display_dates=day_info["display"]
    )
    
    os.makedirs('v2', exist_ok=True)
    file_path = 'v2/index.html'
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(output_html)
    
    print(f"🎉 Successfully built static frontend at {file_path}")

if __name__ == "__main__":
    generate_v2_index()

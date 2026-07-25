import os
import re
import json
import requests
from datetime import datetime, timedelta
import pytz
from jinja2 import Template

def create_slug(name):
    """Generates clean URL slugs dynamically from ESPN league names."""
    if not name:
        return ""
    slug = name.lower()
    slug = re.sub(r'[\/]', '-', slug)
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s-]+', '-', slug)
    return slug.strip('-')

def get_3day_dates():
    """Calculates Yesterday, Today, and Tomorrow using a 3:00 AM EST cutoff."""
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

def should_fetch_summary(event):
    """
    Performance Guard: Only fetches summary endpoint if:
    1. Match is Live ('in')
    2. Match is Finished ('post')
    3. Match starts within 60 minutes
    """
    status_obj = event.get('status', {})
    status_type = status_obj.get('type', {})
    state = status_type.get('state', 'pre')

    if state in ['in', 'post']:
        return True

    if state == 'pre':
        event_date_str = event.get('date')
        if event_date_str:
            try:
                event_dt = datetime.fromisoformat(event_date_str.replace('Z', '+00:00'))
                now_utc = datetime.now(pytz.utc)
                minutes_until_kickoff = (event_dt - now_utc).total_seconds() / 60.0
                if minutes_until_kickoff <= 60:
                    return True
            except Exception:
                pass

    return False

def parse_espn_summary(event_id):
    """Deep dives into ESPN's match summary using verified schema paths."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/summary?event={event_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    summary_data = {
        "team_stats": None,
        "homeLineup": None,
        "awayLineup": None,
        "events": [],
        "odds": {"home": "-", "draw": "-", "away": "-", "total": "-", "over": "-", "under": "-"},
        "injuries": {"home": [], "away": []}
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code != 200:
            return summary_data
        
        data = res.json()
        
        # 1. Parse Team Statistics (boxscore -> teams -> statistics)
        boxscore = data.get('boxscore', {})
        teams_box = boxscore.get('teams', [])
        if len(teams_box) == 2:
            def extract_stat_dict(stats_list):
                if not isinstance(stats_list, list):
                    return {}
                return {s.get('name'): s.get('displayValue', '0') for s in stats_list if isinstance(s, dict)}

            # Align home vs away based on homeAway key or array index
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

        # 2. Parse Rosters / Lineups (rosters -> roster)
        rosters = data.get('rosters', [])
        if isinstance(rosters, list) and len(rosters) >= 2:
            for r_data in rosters:
                home_away = r_data.get('homeAway', 'home')
                key = "homeLineup" if home_away == 'home' else "awayLineup"
                
                formation = r_data.get('formation', '4-3-3')
                start_xi, subs = [], []
                
                player_entries = r_data.get('roster', [])
                if isinstance(player_entries, list):
                    for entry in player_entries:
                        ath = entry.get('athlete', {})
                        pos_abbr = entry.get('position', {}).get('abbreviation', 'M')
                        
                        player_obj = {
                            "id": str(ath.get('id', '')),
                            "name": ath.get('displayName', 'Unknown'),
                            "pos": pos_abbr,
                            "number": str(entry.get('jersey', '')),
                            "photo": ath.get('headshot', {}).get('href', '') if isinstance(ath.get('headshot'), dict) else ''
                        }
                        
                        if entry.get('starter', False):
                            start_xi.append({"player": player_obj, "sub_history": []})
                        else:
                            subs.append({"player": player_obj})

                if start_xi:
                    summary_data[key] = {
                        "formation": formation,
                        "startXI": start_xi,
                        "substitutes": subs
                    }

        # 3. Parse Timeline Events (keyEvents)
        key_events = data.get('keyEvents', [])
        if isinstance(key_events, list):
            for ev in key_events:
                ev_text = ev.get('type', {}).get('text', '')
                clock_text = ev.get('clock', {}).get('displayValue', "0'")
                team_id = str(ev.get('team', {}).get('id', ''))
                
                participants = ev.get('participants', [])
                p_name = participants[0].get('athlete', {}).get('displayName', '') if len(participants) > 0 else ''
                p_out = participants[1].get('athlete', {}).get('displayName', '') if len(participants) > 1 else ''

                ev_type = "Goal" if "Goal" in ev_text else ("subst" if "Substitution" in ev_text or "Sub" in ev_text else "Card")

                summary_data["events"].append({
                    "time": clock_text.replace("'", ""),
                    "team_id": team_id,
                    "type": ev_type,
                    "detail": ev_text,
                    "player": p_name,
                    "player_out": p_out if ev_type == "subst" else None,
                    "assist": p_out if ev_type == "Goal" else None
                })

        # 4. Parse Betting Odds (pickcenter / odds)
        pickcenter = data.get('pickcenter', []) or data.get('odds', [])
        if isinstance(pickcenter, list) and len(pickcenter) > 0:
            odds_item = pickcenter[0]
            
            # Moneyline parsing
            h_ml = odds_item.get('homeTeamOdds', {}).get('moneyLine')
            a_ml = odds_item.get('awayTeamOdds', {}).get('moneyLine')
            d_ml = odds_item.get('drawOdds', {}).get('moneyLine')
            
            # Over/Under total line
            ou_line = odds_item.get('overUnder', odds_item.get('total', {}).get('displayName', '-'))

            summary_data["odds"] = {
                "home": f"+{h_ml}" if h_ml and int(h_ml) > 0 else str(h_ml or '-'),
                "draw": f"+{d_ml}" if d_ml and int(d_ml) > 0 else str(d_ml or '-'),
                "away": f"+{a_ml}" if a_ml and int(a_ml) > 0 else str(a_ml or '-'),
                "total": str(ou_line),
                "over": str(odds_item.get('overOdds', '-')),
                "under": str(odds_item.get('underOdds', '-'))
            }

    except Exception as e:
        print(f"⚠️ Summary fetch note for match {event_id}: {e}")
        
    return summary_data

def fetch_espn_scores_for_date(date_str):
    """Queries ESPN's master daily schedule endpoint for a specific date."""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates={date_str}&limit=500"
    headers = {'User-Agent': 'Mozilla/5.0'}
    raw_events = []

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            raw_events = res.json().get('events', [])
    except Exception as e:
        print(f"⚠️ Schedule query error for {date_str}: {e}")

    if not raw_events:
        try:
            res = requests.get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/scoreboard?dates={date_str}&limit=500", headers=headers, timeout=10)
            if res.status_code == 200:
                raw_events = res.json().get('events', [])
        except Exception:
            pass

    matches = []
    summary_calls = 0
    print(f"--> Processing {len(raw_events)} matches from schedule for date {date_str}...")

    for event in raw_events:
        try:
            event_id = str(event['id'])
            competitions = event.get('competitions', [])
            if not competitions:
                continue

            comp = competitions[0]
            competitors = comp.get('competitors', [])
            
            home = next((c for c in competitors if c.get('homeAway') == 'home'), None)
            away = next((c for c in competitors if c.get('homeAway') == 'away'), None)

            if not home or not away:
                continue

            league_obj = event.get('league') or comp.get('league') or (event.get('leagues', [{}])[0] if event.get('leagues') else {})
            league_name = league_obj.get('name') or league_obj.get('displayName') or league_obj.get('midsizeName') or "Soccer"
            league_slug = create_slug(league_name)

            status_obj = event.get('status', {})
            status_type = status_obj.get('type', {})
            state = status_type.get('state', 'pre')
            short_detail = status_type.get('shortDetail', '')

            if state == 'pre':
                status_short = 'NS'
            elif state == 'post':
                status_short = 'FT'
            else:
                status_short = short_detail if short_detail else 'LIVE'

            elapsed = status_obj.get('period', 0)

            # SMART FETCH: Deep dive summary only when match is live, finished, or starting soon
            if should_fetch_summary(event):
                summary = parse_espn_summary(event_id)
                summary_calls += 1
            else:
                summary = {
                    "team_stats": None,
                    "homeLineup": None,
                    "awayLineup": None,
                    "events": [],
                    "odds": {"home": "-", "draw": "-", "away": "-"},
                    "injuries": {"home": [], "away": []}
                }

            matches.append({
                "fixture": {
                    "id": event_id,
                    "date": event['date'],
                    "status": {"short": status_short, "elapsed": elapsed}
                },
                "league": {
                    "id": event_id,
                    "name": league_name,
                    "slug": league_slug
                },
                "teams": {
                    "home": {
                        "id": str(home['team']['id']),
                        "name": home['team']['displayName'],
                        "logo": home['team'].get('logo', ''),
                        "rank": home.get('curatedRank', {}).get('current', '')
                    },
                    "away": {
                        "id": str(away['team']['id']),
                        "name": away['team']['displayName'],
                        "logo": away['team'].get('logo', ''),
                        "rank": away.get('curatedRank', {}).get('current', '')
                    }
                },
                "goals": {
                    "home": int(home.get('score', 0)),
                    "away": int(away.get('score', 0))
                },
                "team_stats": summary["team_stats"],
                "homeLineup": summary["homeLineup"],
                "awayLineup": summary["awayLineup"],
                "events": summary["events"],
                "odds": summary["odds"],
                "injuries": summary["injuries"],
                "isFallback": summary["homeLineup"] is None
            })
        except Exception as e:
            print(f"⚠️ Error parsing match item {event.get('id', 'unknown')}: {e}")

    print(f"    └─ Deep summary calls made: {summary_calls}/{len(raw_events)}")
    return matches

# Complete V1 UI Template
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
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 16px; overflow: hidden;
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

        .stat-bar-container {
            display: flex; width: 100%; height: 14px; background-color: #e9ecef;
            border-radius: 4px; overflow: hidden; margin-top: 2px;
        }
        .stat-bar-segment {
            display: flex; align-items: center; justify-content: center;
            font-size: 0.60rem; font-weight: 800; padding: 0 4px; transition: width 0.5s ease-in-out;
        }
        .stat-label-tiny {
            font-size: 0.55rem; text-transform: uppercase; font-weight: 700; color: #6c757d; margin-top: 4px;
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
        const dateObj = new Date(data.fixture.date);
        
        const timeString = dateObj.toLocaleTimeString([], {hour: 'numeric', minute:'2-digit'}).replace(' ', '');
        const matchTime = `${dateObj.toLocaleDateString([], {weekday: 'short'})} ${timeString}`;

        const isFinished = ['FT', 'AET', 'PEN'].includes(status);
        const isPreGame = ['NS', 'TBD'].includes(status);
        const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);

        if (isDelayed) {
            return `<span class="badge bg-danger text-white border px-2 py-1" style="font-size: 0.75rem;">${status}</span>`;
        } else if (isFinished) {
            return `<span class="badge bg-dark text-white border px-2 py-1" style="font-size: 0.75rem;">FT</span>`;
        } else if (!isPreGame) {
            let displayMin = data.fixture.status.elapsed || 'LIVE';
            if (status === 'HT') displayMin = 'HT';
            return `<span class="badge bg-success text-white border px-2 py-1" style="font-size: 0.75rem;"><span class="live-dot"></span>${displayMin}'</span>`;
        } else {
            return `<span class="badge bg-white text-dark border px-1 py-1" style="font-size: 0.65rem; white-space: nowrap;">${matchTime}</span>`;
        }
    }

    function getCenterColumnHtml(data) {
        const status = data.fixture.status.short;
        const isPreGame = ['NS', 'TBD'].includes(status);
        const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);
        const showScore = !isPreGame && !isDelayed;

        if (!showScore || !data.team_stats) {
            const scoreText = showScore ? `${data.goals?.home ?? 0} - ${data.goals?.away ?? 0}` : `vs`;
            return `<div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">${scoreText}</div>`;
        }

        const tStats = data.team_stats;
        const buildBar = (label, hVal, aVal, isPercentage = false) => {
            const total = hVal + aVal;
            let hPct = 50, aPct = 50;
            if (total > 0) {
                hPct = (hVal / total) * 100;
                aPct = (aVal / total) * 100;
            }
            const displayH = isPercentage ? `${hVal}%` : hVal;
            const displayA = isPercentage ? `${aVal}%` : aVal;

            return `
                <div class="text-center w-100 px-1">
                    <div class="stat-label-tiny">${label}</div>
                    <div class="stat-bar-container">
                        <div class="stat-bar-segment text-white" style="width: ${hPct}%; background-color: #0d6efd;">${displayH}</div>
                        <div class="stat-bar-segment text-white" style="width: ${aPct}%; background-color: #dc3545;">${displayA}</div>
                    </div>
                </div>`;
        };

        return `
            <div class="fw-bold text-dark mx-2 mb-1" style="font-size: 1.1rem; line-height: 1;">${data.goals?.home ?? 0} - ${data.goals?.away ?? 0}</div>
            ${buildBar("Possession", tStats.home?.possession ?? 0, tStats.away?.possession ?? 0, true)}
            ${buildBar("Total Shots", tStats.home?.total_shots ?? 0, tStats.away?.total_shots ?? 0)}
            ${buildBar("Corners", tStats.home?.corners ?? 0, tStats.away?.corners ?? 0)}`;
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
                    <a href="/leagues/${data.league.slug}/" class="text-decoration-none text-muted fw-bold text-uppercase text-end ms-auto text-truncate" style="font-size: 0.70rem;">
                        ${data.league.name}
                    </a>
                </div>
                <div class="d-flex justify-content-between align-items-center px-1 py-1 w-100">
                    <div class="text-center" style="width: 30%;">
                        <img src="${home.logo}" alt="${home.name}" class="team-logo mb-1">
                        <div class="fw-bold text-dark text-truncate" style="font-size: 0.8rem;">${home.name}</div>
                    </div>
                    <div class="text-center d-flex flex-column align-items-center justify-content-center" style="width: 40%;">
                        ${getCenterColumnHtml(data)}
                    </div>
                    <div class="text-center" style="width: 30%;">
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
                        <div class="h4 text-muted">🏟️ No matches scheduled for this partition.</div>
                        <p class="text-muted">Select another day button above.</p>
                    </div>
                </div>`;
            return;
        }

        filtered.forEach(item => container.appendChild(createGameCard(item)));
    }

    document.addEventListener('DOMContentLoaded', () => {
        renderGames();

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

        const searchInput = document.getElementById('team-search');
        if (searchInput) searchInput.addEventListener('input', renderGames);

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
    print("⏳ Calculating 3-day window using 3:00 AM EST cutoff...")
    day_info = get_3day_dates()
    
    print("🚀 Fetching daily match schedules from ESPN...")
    matches_by_day = {
        "yesterday": fetch_espn_scores_for_date(day_info["dates"]["yesterday"]),
        "today": fetch_espn_scores_for_date(day_info["dates"]["today"]),
        "tomorrow": fetch_espn_scores_for_date(day_info["dates"]["tomorrow"])
    }
    
    print(f"\n📊 Match Fetch Summary:")
    print(f"  ├─ Yesterday ({day_info['dates']['yesterday']}): {len(matches_by_day['yesterday'])} matches")
    print(f"  ├─ Today     ({day_info['dates']['today']}):     {len(matches_by_day['today'])} matches")
    print(f"  └─ Tomorrow  ({day_info['dates']['tomorrow']}):  {len(matches_by_day['tomorrow'])} matches")
    
    template = Template(HTML_TEMPLATE)
    output_html = template.render(
        matches_json=json.dumps(matches_by_day),
        display_dates=day_info["display"]
    )
    
    os.makedirs('v2', exist_ok=True)
    file_path = 'v2/index.html'
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(output_html)
    
    print(f"\n🎉 Successfully compiled static index at {file_path}")

if __name__ == "__main__":
    generate_v2_index()

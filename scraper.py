import os
import json
import urllib.request
from datetime import datetime, timedelta

# FotMob League IDs
TOP_LEAGUES = [47, 87, 55, 54, 53, 42, 130] # EPL, La Liga, Serie A, Bundes, Ligue 1, UCL, MLS

def fetch_data(url):
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return None

def process_date(target_date):
    date_str = target_date.strftime("%Y%m%d")
    save_str = target_date.strftime("%Y-%m-%d")
    print(f"--- Fetching schedule for {save_str} ---")
    
    # 1. Fetch the daily schedule
    schedule_data = fetch_data(f"https://www.fotmob.com/api/matches?date={date_str}")
    if not schedule_data or "leagues" not in schedule_data:
        return

    all_game_data = []

    # 2. Filter for our specific leagues
    for league in schedule_data["leagues"]:
        if league["primaryId"] in TOP_LEAGUES:
            for match in league["matches"]:
                match_id = match["id"]
                print(f"Fetching Match ID {match_id} ({match['home']['name']} vs {match['away']['name']})...")
                
                # 3. Fetch the deep match details (Lineups, Formations)
                details = fetch_data(f"https://www.fotmob.com/api/matchDetails?matchId={match_id}")
                
                home_lineup, away_lineup = None, None
                
                if details and "content" in details and "lineup" in details["content"]:
                    lineup_data = details["content"]["lineup"]
                    if "lineup" in lineup_data:
                        # FotMob stores them in an array: [0] is Home, [1] is Away
                        home_lineup = lineup_data["lineup"][0] if len(lineup_data["lineup"]) > 0 else None
                        away_lineup = lineup_data["lineup"][1] if len(lineup_data["lineup"]) > 1 else None

                all_game_data.append({
                    "id": match_id,
                    "league": {"id": league["primaryId"], "name": league["name"]},
                    "time": match["status"]["utcTime"],
                    "status": match["status"],
                    "home": match["home"],
                    "away": match["away"],
                    "homeLineup": home_lineup,
                    "awayLineup": away_lineup
                })

    # 4. Save to a date-specific file
    os.makedirs("data", exist_ok=True)
    with open(f"data/games_{save_str}.json", "w") as f:
        json.dump(all_game_data, f)
    print(f"Saved {len(all_game_data)} games to data/games_{save_str}.json\n")

def main():
    today = datetime.now()
    dates_to_fetch = [
        today - timedelta(days=1), # Yesterday
        today,                     # Today
        today + timedelta(days=1)  # Tomorrow
    ]
    
    for d in dates_to_fetch:
        process_date(d)

if __name__ == "__main__":
    main()

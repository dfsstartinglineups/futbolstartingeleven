import os
from datetime import datetime, timedelta

BASE_URL = "https://futbolstartingeleven.com"

# The exact 41 keys from your script.js LEAGUE_GROUPS
LEAGUES = [
    "top", "epl", "championship", "laliga", "seriea", "bundesliga", "ligue1", 
    "eredivisie", "portugal", "turkey", "belgium", "scotland", "denmark", 
    "mls", "ligamx", "brazil", "argentina", "colombia", "saudi", "japan", 
    "australia", "k1", "ucl", "europa", "conference", "libertadores", 
    "sudamericana", "concacaf", "leaguescup", "facup", "eflcup", "copadelrey", 
    "coppaitalia", "dfbpokal", "worldcup", "euros", "copaamerica", "uefanations", 
    "concacafnations", "wsl", "nwsl"
]

def generate_sitemap():
    print("Generating sitemap.xml...")
    today = datetime.now()
    today_str = today.strftime("%Y-%m-%d")
    
    # Create a rolling window: 7 days in the past, Today, and 3 days in the future
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(-7, 4)]
    
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # 1. Add the main homepage (Highest Priority)
    xml.append(f'  <url>\n    <loc>{BASE_URL}/</loc>\n    <lastmod>{today_str}</lastmod>\n    <changefreq>always</changefreq>\n    <priority>1.0</priority>\n  </url>')
    
    # 2. Loop through every league and every date in the window
    for league in LEAGUES:
        for date_str in dates:
            
            # --- THE CANONICAL URL FIX ---
            # If the date is today, drop the date parameter to match our frontend logic!
            if date_str == today_str:
                url = f"{BASE_URL}/?league={league}"
                priority = "0.9"
            else:
                url = f"{BASE_URL}/?league={league}&amp;date={date_str}"
                priority = "0.7"
            
            xml.append(f'  <url>\n    <loc>{url}</loc>\n    <lastmod>{today_str}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>{priority}</priority>\n  </url>')
            
    xml.append('</urlset>')
    
    # Save the file to the root directory
    with open("sitemap.xml", "w") as f:
        f.write("\n".join(xml))
        
    print(f"Successfully generated sitemap.xml with {len(LEAGUES) * len(dates) + 1} URLs!")

if __name__ == "__main__":
    generate_sitemap()

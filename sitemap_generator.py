import os
from datetime import datetime, timedelta

BASE_URL = "https://futbolstartingeleven.com"

# The exact keys from your script.js LEAGUE_GROUPS
LEAGUES = [
    "top", "epl", "facup", "laliga", "mls", "ucl", 
    "championship", "seriea", "bundesliga", "ligue1", "eredivisie", "portugal",
    "ligamx", "brazil", "argentina", "libertadores",
    "saudi", "japan"
]

def generate_sitemap():
    print("Generating SEO sitemap.xml...")
    today = datetime.now()
    
    # Create a rolling window: 7 days in the past, Today, and 3 days in the future
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(-7, 4)]
    
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    # 1. Add the main homepage (Highest Priority)
    xml.append(f'  <url>\n    <loc>{BASE_URL}/</loc>\n    <changefreq>always</changefreq>\n    <priority>1.0</priority>\n  </url>')
    
    # 2. Loop through every league and every date in the window
    for league in LEAGUES:
        for date_str in dates:
            # We must escape the '&' symbol as '&amp;' for valid XML
            url = f"{BASE_URL}/?league={league}&amp;date={date_str}"
            
            # If the date is today, give it a higher priority
            priority = "0.9" if date_str == today.strftime("%Y-%m-%d") else "0.7"
            
            xml.append(f'  <url>\n    <loc>{url}</loc>\n    <changefreq>daily</changefreq>\n    <priority>{priority}</priority>\n  </url>')
            
    xml.append('</urlset>')
    
    # Save the file to the root directory
    with open("sitemap.xml", "w") as f:
        f.write("\n".join(xml))
        
    print(f"Successfully generated sitemap.xml with {len(LEAGUES) * len(dates) + 1} URLs!")

if __name__ == "__main__":
    generate_sitemap()

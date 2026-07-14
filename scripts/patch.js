import os

# Set exact boundary to ONLY target the players directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLAYERS_DIR = os.path.join(SCRIPT_DIR, '..', 'players')

print("⚡ Injecting live widget JavaScript into existing player pages...")
count = 0

for root, dirs, files in os.walk(PLAYERS_DIR):
    for file in files:
        if file == "index.html":
            filepath = os.path.join(root, file)
            
            with open(filepath, "r", encoding="utf-8") as f:
                html = f.read()
            
            # Idempotent check: only inject if it's not already there
            if "/js/player-live.js" not in html:
                # Surgically swap the closing body tag
                html = html.replace("</body>", '    <script src="/js/player-live.js"></script>\n</body>')
                
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(html)
                count += 1

print(f"✅ Done! Successfully patched {count} HTML files.")

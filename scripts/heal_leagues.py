import json
import os
import re
import shutil
import unicodedata
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

SITE_PAGES_FILE = 'data/site_pages.json'
LEAGUES_DIR = 'leagues'
CORE_LEAGUES_URL = "https://sports.core.api.espn.com/v2/sports/soccer/leagues?limit=1000"

GARBAGE_PATTERNS = [
    r',',                        # Comma group splits
    r'-group-[a-z0-9]+',         # Group tags
    r'-stage-[a-z0-9]+',         # Stage tags
    r'-round-[a-z0-9]+',         # Round tags
    r'-knockout-',               # Knockout tags
    r'-qualifying-(second|first|third)-'
]

LEGACY_DUPLICATES = {
    "argentine-lpf",
    "brazil-serie-a",
    "brazil-serie-b",
    "chilean-primera",
    "paraguayan-primera",
    "salvadoran-primera"
}

def normalize_text(text):
    if not text: return ""
    nfkd_form = unicodedata.normalize('NFD', text)
    return "".join([c for c in nfkd_form if unicodedata.category(c) != 'Mn']).lower().strip()

def fetch_single_league_detail(ref_url):
    try:
        res = requests.get(ref_url, timeout=5)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

def build_hydrated_core_index():
    print("🔄 Hydrating Master Core API Directory (Parallel Threads)...")
    index = {
        "name_map": {
            "club friendly": "club.friendly",
            "international friendly": "fifa.friendly",
            "friendly": "club.friendly",
            "men's international friendly": "fifa.friendly",
            "asean champ": "aff.championship",
            "asean championship": "aff.championship"
        }
    }
    try:
        master_res = requests.get(CORE_LEAGUES_URL, timeout=10).json()
        ref_urls = [item['$ref'] for item in master_res.get('items', []) if '$ref' in item]
        
        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = {executor.submit(fetch_single_league_detail, url): url for url in ref_urls}
            for future in as_completed(futures):
                data = future.result()
                if not data: continue
                slug = data.get('slug')
                name = data.get('name')
                short_name = data.get('shortName')
                abbrev = data.get('abbreviation')
                
                if slug:
                    if name: index["name_map"][normalize_text(name)] = slug
                    if short_name: index["name_map"][normalize_text(short_name)] = slug
                    if abbrev: index["name_map"][normalize_text(abbrev)] = slug
        print(f"✅ Hydrated {len(index['name_map'])} Core API league variations.\n")
    except Exception as e:
        print(f"⚠️ Core API hydration failed: {e}\n")
    return index

def clean_and_repair_site_pages():
    if not os.path.exists(SITE_PAGES_FILE):
        print(f"❌ File {SITE_PAGES_FILE} not found.")
        return

    with open(SITE_PAGES_FILE, 'r', encoding='utf-8') as f:
        pages = json.load(f)

    core_index = build_hydrated_core_index()

    purged_count = 0
    folders_deleted = 0
    healed_pills = 0
    cleaned_pages = {}

    print("🧹 Cleaning site_pages.json...")

    for slug, data in pages.items():
        name = data.get('name', '')
        
        # 1. Check for garbage orphan or legacy duplicate
        is_garbage = any(re.search(p, slug, re.IGNORECASE) or re.search(p, name, re.IGNORECASE) for p in GARBAGE_PATTERNS)
        if is_garbage or slug in LEGACY_DUPLICATES:
            purged_count += 1
            print(f"  🗑️ Purging: '{slug}' ({name})")
            
            league_folder = os.path.join(LEAGUES_DIR, slug)
            if os.path.exists(league_folder):
                try:
                    shutil.rmtree(league_folder)
                    folders_deleted += 1
                    print(f"     └─ Deleted directory: {league_folder}")
                except Exception as e:
                    print(f"     └─ ⚠️ Failed to delete folder {league_folder}: {e}")
            continue

        # 2. Auto-heal missing pills
        if not data.get('pill') or data.get('pill') == 'global':
            norm_name = normalize_text(name)
            resolved_pill = (
                core_index['name_map'].get(norm_name) or
                core_index['name_map'].get(slug.replace('-', ' '))
            )
            if resolved_pill:
                data['pill'] = resolved_pill
                healed_pills += 1
                print(f"  ✅ Healed Pill: '{slug}' ➔ '{resolved_pill}'")

        cleaned_pages[slug] = data

    with open(SITE_PAGES_FILE, 'w', encoding='utf-8') as f:
        json.dump(cleaned_pages, f, indent=2, ensure_ascii=False)

    print("\n==================================================")
    print("✨ CLEANUP & REPAIR SUMMARY")
    print("==================================================")
    print(f"Initial Entries:      {len(pages)}")
    print(f"Purged Orphans/Dupes: {purged_count}")
    print(f"Folders Purged:       {folders_deleted}")
    print(f"Pills Auto-Healed:    {healed_pills}")
    print(f"Clean Entries Left:   {len(cleaned_pages)}")
    print("==================================================")

if __name__ == "__main__":
    clean_and_repair_site_pages()

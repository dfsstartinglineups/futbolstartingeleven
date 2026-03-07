// ==========================================
// CONFIGURATION
// ==========================================
const DEFAULT_DATE = new Date().toLocaleDateString('en-CA');
let ALL_GAMES_DATA = []; 

const X_SVG_PATH = "M12.6.75h2.454l-5.36 6.142L16 15.25h-4.937l-3.867-5.07-4.425 5.07H.316l5.733-6.57L0 .75h5.063l3.495 4.633L12.601.75Zm-.86 13.028h1.36L4.323 2.145H2.865l8.875 11.633Z";

// Updated with FotMob's internal League IDs
const SUPPORTED_LEAGUES = {
    "top": { id: "top", name: "Top Matches" },
    "epl": { id: 47, name: "Premier League" },
    "laliga": { id: 87, name: "La Liga" },
    "mls": { id: 130, name: "MLS" },
    "seriea": { id: 55, name: "Serie A" },
    "bundesliga": { id: 54, name: "Bundesliga" },
    "ligue1": { id: 53, name: "Ligue 1" },
    "ucl": { id: 42, name: "Champions League" }
};

// ==========================================
// 1. INITIALIZATION & ROUTING
// ==========================================
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        league: params.get('league') || 'top',
        date: params.get('date') || DEFAULT_DATE
    };
}

function updateSEO(leagueKey, dateStr) {
    const leagueName = SUPPORTED_LEAGUES[leagueKey]?.name || "Top Matches";
    const dateObj = new Date(dateStr + 'T00:00:00');
    const formattedDate = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    
    document.title = `${leagueName} Starting Lineups for ${formattedDate} | FutbolStartingEleven`;
    document.getElementById('seo-h1').innerText = `Daily ${leagueName} Starting Lineups & Formations`;
}

function renderLeagueMenu(activeLeague) {
    const menu = document.getElementById('league-menu');
    menu.innerHTML = '';
    
    Object.keys(SUPPORTED_LEAGUES).forEach(key => {
        const a = document.createElement('a');
        a.href = `?league=${key}`;
        a.className = `league-pill ${key === activeLeague ? 'active' : ''}`;
        a.textContent = SUPPORTED_LEAGUES[key].name;
        menu.appendChild(a);
    });
}

// ==========================================
// 2. MAIN APP LOGIC 
// ==========================================
async function init() {
    const params = getUrlParams();
    updateSEO(params.league, params.date);
    renderLeagueMenu(params.league);
    
    const container = document.getElementById('games-container');
    const datePicker = document.getElementById('date-picker');
    if (datePicker) datePicker.value = params.date;

    container.innerHTML = `
        <div class="col-12 text-center mt-5 pt-5">
            <div class="spinner-border text-success" role="status"></div>
            <p class="mt-3 text-muted fw-bold">Loading Pitch Data...</p>
        </div>`;
    
    ALL_GAMES_DATA = [];
    
    try {
        // Fetch the specific date file created by our FotMob Scraper
        const res = await fetch(`data/games_${params.date}.json?v=` + new Date().getTime());
        if (!res.ok) throw new Error("No data file found for this date.");
        
        let matches = await res.json();

        // Filter based on selected league
        if (params.league !== 'top') {
            const targetId = SUPPORTED_LEAGUES[params.league].id;
            matches = matches.filter(m => m.league.id === targetId);
        }

        if (matches.length === 0) {
            container.innerHTML = `<div class="col-12 text-center mt-5"><div class="alert alert-light border shadow-sm py-4"><h5 class="text-muted mb-0">No matches scheduled for this league on this date.</h5></div></div>`;
            return;
        }

        ALL_GAMES_DATA = matches;
        renderGames();

    } catch (error) {
        container.innerHTML = `<div class="col-12 text-center mt-5"><div class="alert alert-danger">Waiting for automated data update... or no matches scheduled.</div></div>`;
    }
}

// ==========================================
// 3. RENDERING ENGINE
// ==========================================
function renderGames() {
    const container = document.getElementById('games-container');
    container.innerHTML = '';

    const searchInput = document.getElementById('team-search');
    const searchText = searchInput ? searchInput.value.toLowerCase() : '';

    let filteredGames = ALL_GAMES_DATA.filter(item => {
        const matchString = (item.home.name + " " + item.away.name).toLowerCase();
        return matchString.includes(searchText);
    });

    filteredGames.sort((a, b) => new Date(a.time) - new Date(b.time));
    filteredGames.forEach(item => container.appendChild(createGameCard(item)));
}

function createGameCard(data) {
    const gameCard = document.createElement('div');
    gameCard.className = 'col-md-6 col-lg-6 col-xl-4 mb-2';

    const home = data.home;
    const away = data.away;
    const matchTime = new Date(data.time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    
    // FotMob Status: finished, ongoing, notStarted
    const isLive = data.status.ongoing;
    const isFinished = data.status.finished;
    const isCancelled = data.status.cancelled;

    let timeBadge = `<span class="badge bg-white text-dark shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${matchTime}</span>`;
    if (isLive) timeBadge = `<span class="badge bg-success text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem; animation: pulse 2s infinite;">LIVE</span>`;
    else if (isFinished) timeBadge = `<span class="badge bg-dark text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">FT</span>`;
    else if (isCancelled) timeBadge = `<span class="badge bg-danger text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">CANC</span>`;

    const buildLineupList = (lineupData) => {
        if (!lineupData || !lineupData.optaLineup) {
            return `<div class="p-4 text-center text-muted small fw-bold">Lineup pending...</div>`;
        }

        const formationHeader = `<div class="w-100 text-center py-1 fw-bold text-white" style="font-size: 0.65rem; background-color: #198754; border-bottom: 1px solid #146c43; letter-spacing: 0.5px;">✅ ${lineupData.teamData.formation} FORMATION</div>`;
        
        // FotMob structures lineup in rows (Keeper, Def, Mid, Fwd)
        let players = [];
        if (lineupData.optaLineup && lineupData.optaLineup.players) {
            lineupData.optaLineup.players.forEach(row => {
                row.forEach(p => players.push(p));
            });
        }

        const listItems = players.map(player => {
            const role = player.role || "M"; // Keeper, Defender, Midfielder, Attacker
            let shortPos = role.charAt(0);
            if (role === "Attacker") shortPos = "F";
            if (role === "Keeper") shortPos = "G";

            let posColor = shortPos === 'G' ? "#dc3545" : shortPos === 'D' ? "#0d6efd" : shortPos === 'M' ? "#20c997" : "#ffc107";
            
            return `
                <li class="d-flex w-100 px-2 py-1 border-bottom">
                    <span class="text-muted fw-bold d-inline-block text-start" style="font-size: 0.7rem; width: 25px; color: ${posColor} !important;">${shortPos}</span>
                    <span class="batter-name fw-bold text-dark text-truncate" style="font-size: 0.85rem;" title="${player.name.fullName}">${player.name.fullName}</span>
                    <span class="ms-auto text-muted" style="font-size: 0.65rem;">#${player.shirt}</span>
                </li>`;
        }).join('');
        return `${formationHeader}<ul class="batting-order w-100 m-0 p-0" style="list-style-type: none;">${listItems}</ul>`;
    };

    const homeLineupHtml = buildLineupList(data.homeLineup);
    const awayLineupHtml = buildLineupList(data.awayLineup);

    // Score extraction
    let scoreHtml = `<div class="text-muted mx-2" style="font-size: 0.8rem;">vs</div>`;
    if (isLive || isFinished) {
        // FotMob status string format: "2 - 1"
        const scoreStr = data.status.scoreStr || "0 - 0";
        scoreHtml = `<div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">${scoreStr}</div>`;
    }

    gameCard.innerHTML = `
        <div class="lineup-card shadow-sm" style="margin-bottom: 8px;">
            <div class="p-2 pb-1" style="background-color: #fcfcfc;">
                <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom border-light">
                    <div style="flex: 0 0 auto;" class="pe-2">${timeBadge}</div>
                    <div class="text-muted fw-bold text-uppercase text-end ms-auto text-truncate" style="font-size: 0.70rem;">
                        ${data.league.name}
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center px-1 pt-1 pb-2">
                    <div class="text-center" style="width: 40%;"> 
                        <img src="https://images.fotmob.com/image_resources/logo/teamlogo/${home.id}.png" alt="${home.name}" class="team-logo mb-1" onerror="this.src=''">
                        <div class="fw-bold lh-1 text-dark text-truncate" style="font-size: 0.9rem;">${home.name}</div>
                    </div>
                    <div class="text-center d-flex flex-column align-items-center justify-content-center" style="width: 20%;">${scoreHtml}</div>
                    <div class="text-center" style="width: 40%;"> 
                        <img src="https://images.fotmob.com/image_resources/logo/teamlogo/${away.id}.png" alt="${away.name}" class="team-logo mb-1" onerror="this.src=''">
                        <div class="fw-bold lh-1 text-dark text-truncate" style="font-size: 0.9rem;">${away.name}</div>
                    </div>
                </div>
            </div>
            <div class="bg-light border-top border-bottom text-center py-1">
                <span class="fw-bold text-muted" style="font-size: 0.7rem;">STARTING XI</span>
            </div>
            <div class="row g-0 bg-white">
                <div class="col-6 border-end">${homeLineupHtml}</div>
                <div class="col-6">${awayLineupHtml}</div>
            </div>
        </div>`;
    
    return gameCard;
}

// ==========================================
// 4. EVENT LISTENERS
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    init();

    const searchInput = document.getElementById('team-search');
    if (searchInput) searchInput.addEventListener('input', renderGames);

    const datePicker = document.getElementById('date-picker');
    if (datePicker) {
        datePicker.addEventListener('change', (e) => {
            if (e.target.value) { 
                e.target.blur();
                const params = getUrlParams();
                window.location.href = `?league=${params.league}&date=${e.target.value}`;
            }
        });
    }
});

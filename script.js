// ==========================================
// CONFIGURATION
// ==========================================
const DEFAULT_DATE = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
let ALL_GAMES_DATA = []; 

const X_SVG_PATH = "M12.6.75h2.454l-5.36 6.142L16 15.25h-4.937l-3.867-5.07-4.425 5.07H.316l5.733-6.57L0 .75h5.063l3.495 4.633L12.601.75Zm-.86 13.028h1.36L4.323 2.145H2.865l8.875 11.633Z";

const LEAGUE_GROUPS = {
    "priority": [
        { key: "top", id: "top", name: "Top Matches" },
        { key: "epl", id: 39, name: "Premier League" },
        { key: "facup", id: 45, name: "FA Cup" }, 
        { key: "laliga", id: 140, name: "La Liga" },
        { key: "mls", id: 253, name: "MLS" },
        { key: "ucl", id: 2, name: "Champions League" }
    ],
    "Europe": [
        { key: "championship", id: 40, name: "Championship" },
        { key: "seriea", id: 135, name: "Serie A" },
        { key: "bundesliga", id: 78, name: "Bundesliga" },
        { key: "ligue1", id: 61, name: "Ligue 1" },
        { key: "eredivisie", id: 72, name: "Eredivisie" },
        { key: "portugal", id: 94, name: "Primeira Liga" }
    ],
    "Americas": [
        { key: "ligamx", id: 262, name: "Liga MX" },
        { key: "brazil", id: 71, name: "Brasileirão" },
        { key: "argentina", id: 128, name: "Liga Profesional" },
        { key: "libertadores", id: 13, name: "Copa Libertadores" }
    ],
    "World": [
        { key: "saudi", id: 307, name: "Saudi Pro League" },
        { key: "japan", id: 98, name: "J1 League" }
    ]
};

const SUPPORTED_LEAGUES = {};
Object.values(LEAGUE_GROUPS).flat().forEach(l => SUPPORTED_LEAGUES[l.key] = l);

const LEAGUE_MAP_ESPN = {
    39: "eng.1", 40: "eng.2", 45: "eng.fa", 140: "esp.1", 135: "ita.1", 78: "ger.1", 
    61: "fra.1", 72: "ned.1", 94: "por.1", 2: "uefa.champions", 253: "usa.1", 
    262: "mex.1", 71: "bra.1", 128: "arg.1", 13: "conmebol.libertadores", 307: "ksa.1", 98: "jpn.1"            
};

// ==========================================
// 1. UI HELPER MODULES (For Initial Render & Silent Sync)
// ==========================================
function getTimeBadgeHtml(data) {
    const status = data.fixture.status.short;
    const dateObj = new Date(data.fixture.date);
    const matchTime = dateObj.toLocaleDateString([], {weekday: 'short'}) + ' ' + dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

    const isFinished = ['FT', 'AET', 'PEN'].includes(status);
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);

    if (isDelayed) return `<span class="badge bg-danger text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${status}</span>`;
    if (!isPreGame && !isFinished && !data.isFallback) return `<span class="badge bg-success text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${data.fixture.status.elapsed}'</span>`;
    if (isFinished) return `<span class="badge bg-dark text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">FT</span>`;
    return `<span class="badge bg-white text-dark shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${matchTime}</span>`;
}

function getScoreHtml(data) {
    const status = data.fixture.status.short;
    const isFinished = ['FT', 'AET', 'PEN'].includes(status);
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);
    const showScore = !isPreGame && !isDelayed && !data.isFallback;

    return showScore 
        ? `<div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">${data.goals.home} - ${data.goals.away}</div>` 
        : `<div class="text-muted mx-2" style="font-size: 0.8rem;">vs</div>`;
}

function getEventsHtml(data) {
    if (!data.events || data.events.length === 0) return '';
    const homeEvents = data.events.filter(e => e.team_id === data.teams.home.id);
    const awayEvents = data.events.filter(e => e.team_id === data.teams.away.id);
    
    const formatEvents = (evs) => evs.map(e => {
        let icon = e.type === 'Goal' ? '⚽' : '🟥';
        return `<span class="d-inline-block me-1">${icon} <span class="text-dark fw-bold">${e.player}</span> ${e.time}'</span>`;
    }).join(' ');

    return `
    <div class="w-100 px-2 pt-1 mt-1 border-top" 
         style="font-size: 0.65rem; cursor: pointer; transition: background-color 0.2s;" 
         onclick="const cols = this.querySelectorAll('.event-col'); cols.forEach(c => c.classList.toggle('text-truncate'));"
         onmouseover="this.style.backgroundColor='#f8f9fa'" 
         onmouseout="this.style.backgroundColor='transparent'"
         title="Click to expand/collapse goals and cards">
        <div class="d-flex justify-content-between text-muted w-100">
            <div class="event-col text-start pe-1 text-truncate" style="flex: 1; min-width: 0;">${formatEvents(homeEvents)}</div>
            <div class="event-col text-end ps-1 text-truncate" style="flex: 1; min-width: 0;">${formatEvents(awayEvents)}</div>
        </div>
    </div>`;
}

function getOddsHtml(data) {
    if (!data.odds || (data.odds.home === "TBD" && data.odds.over === "TBD")) return '';
    const h = data.odds.home !== "TBD" ? data.odds.home : "-";
    const d = data.odds.draw !== "TBD" ? data.odds.draw : "-";
    const a = data.odds.away !== "TBD" ? data.odds.away : "-";
    const t = data.odds.total !== "TBD" ? data.odds.total : "-";
    const o = data.odds.over !== "TBD" ? data.odds.over : "-";
    const u = data.odds.under !== "TBD" ? data.odds.under : "-";

    return `
    <div class="d-flex justify-content-between text-center bg-white border-top border-bottom py-1" style="font-size: 0.70rem;">
        <div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">1 (HOME)</div><div class="fw-bold text-dark">${h}</div></div>
        <div class="w-25 border-start border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">X (DRAW)</div><div class="fw-bold text-dark">${d}</div></div>
        <div class="w-25 border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">2 (AWAY)</div><div class="fw-bold text-dark">${a}</div></div>
        <div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">O/U ${t}</div><div class="fw-bold text-dark"><span class="text-success">O</span> ${o} &nbsp;<span class="text-danger">U</span> ${u}</div></div>
    </div>`;
}

function getInjuriesHtml(data) {
    if (!data.injuries || (data.injuries.home.length === 0 && data.injuries.away.length === 0)) return '';
    const hInj = data.injuries.home.join(', ') || 'None';
    const aInj = data.injuries.away.join(', ') || 'None';
    
    return `
    <div class="border-bottom px-2 py-1 text-center" 
         style="font-size: 0.65rem; background-color: #fff5f5; color: #dc3545; cursor: pointer; transition: background-color 0.2s;" 
         onclick="this.querySelector('.injury-text').classList.toggle('text-truncate');" 
         onmouseover="this.style.backgroundColor='#ffebeb'" 
         onmouseout="this.style.backgroundColor='#fff5f5'" 
         title="Click to expand/collapse injuries">
        <div class="injury-text text-truncate user-select-none px-1">
            <strong>🤕 OUT:</strong> <span class="text-dark"><b>H:</b> ${hInj} | <b>A:</b> ${aInj}</span>
        </div>
    </div>`;
}

// ==========================================
// 2. DATA FETCHING & ROUTING
// ==========================================
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return { league: params.get('league') || 'top', date: params.get('date') || DEFAULT_DATE };
}

function updateSEO(leagueKey, dateStr) {
    const leagueName = SUPPORTED_LEAGUES[leagueKey]?.name || "Top Matches";
    const dateObj = new Date(dateStr + 'T12:00:00'); 
    const formattedDate = dateObj.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    document.title = `Live ${leagueName} Soccer Lineups, Scores & Odds | FutbolStartingEleven`;
    document.getElementById('seo-h1').innerText = `Live ${leagueName} Soccer Starting Lineups, Live Scores, Injuries, and Match Odds for ${formattedDate}`;
}

function renderLeagueMenu(activeLeague, currentDate) {
    const menu = document.getElementById('league-menu');
    menu.innerHTML = '';
    
    LEAGUE_GROUPS["priority"].forEach(league => {
        const a = document.createElement('a');
        a.href = `?league=${league.key}&date=${currentDate}`;
        a.className = `league-pill ${league.key === activeLeague ? 'active' : ''}`;
        a.textContent = league.name;
        menu.appendChild(a);
    });

    ['Europe', 'Americas', 'World'].forEach(region => {
        if (LEAGUE_GROUPS[region].length === 0) return; 
        const isActiveRegion = LEAGUE_GROUPS[region].some(l => l.key === activeLeague);
        const dropdownDiv = document.createElement('div');
        dropdownDiv.className = 'dropdown d-inline-block';
        dropdownDiv.innerHTML = `
            <button class="dropdown-toggle league-pill ${isActiveRegion ? 'active' : ''}" type="button" data-bs-toggle="dropdown" aria-expanded="false" style="border: none; background: transparent; color: ${isActiveRegion ? '#20c997' : '#adb5bd'};">
                ${region}
            </button>
            <ul class="dropdown-menu dropdown-menu-dark shadow" style="background-color: #343a40; border-color: #495057;">
                ${LEAGUE_GROUPS[region].map(league => `
                    <li><a class="dropdown-item ${league.key === activeLeague ? 'text-success fw-bold' : 'text-light'}" href="?league=${league.key}&date=${currentDate}">${league.name}</a></li>
                `).join('')}
            </ul>`;
        menu.appendChild(dropdownDiv);
    });
}

async function fetchMatchesData(params) {
    try {
        const localRes = await fetch(`data/games_${params.date}.json?v=` + new Date().getTime());
        if (localRes.ok) {
            let matches = await localRes.json();
            if (params.league !== 'top') {
                const targetId = SUPPORTED_LEAGUES[params.league].id;
                matches = matches.filter(m => m.league.id === targetId);
            }
            return matches;
        }

        const espnDate = params.date.replace(/-/g, '');
        let espnUrl = params.league === 'top' 
            ? `https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard?dates=${espnDate}`
            : `https://site.api.espn.com/apis/site/v2/sports/soccer/${LEAGUE_MAP_ESPN[SUPPORTED_LEAGUES[params.league].id]}/scoreboard?dates=${espnDate}`;

        const espnRes = await fetch(espnUrl);
        const espnData = await espnRes.json();

        if (!espnData.events || espnData.events.length === 0) return [];

        let mapped = espnData.events.map(e => {
            const comp = e.competitions[0];
            const home = comp.competitors.find(c => c.homeAway === 'home');
            const away = comp.competitors.find(c => c.homeAway === 'away');
            return {
                fixture: { id: e.id, date: e.date, status: { short: e.status.type.shortDetail, elapsed: e.status.period } },
                league: { name: espnData.leagues[0].name },
                teams: {
                    home: { id: home.team.id, name: home.team.displayName, logo: home.team.logo },
                    away: { id: away.team.id, name: away.team.displayName, logo: away.team.logo }
                },
                goals: { home: home.score, away: away.score },
                homeLineup: null, awayLineup: null, isFallback: true 
            };
        });

        return mapped.filter(item => {
            const gameDateEST = new Date(item.fixture.date).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
            return gameDateEST === params.date;
        });
    } catch (e) { return null; }
}

// ==========================================
// 3. SILENT SYNC ENGINE (The Magic)
// ==========================================
async function updateLiveGames() {
    const params = getUrlParams();
    const newData = await fetchMatchesData(params);
    if (!newData) return; // Skip tick if fetch fails

    // If game count changes (e.g. game added/removed), we must re-render the whole grid
    if (newData.length !== ALL_GAMES_DATA.length) {
        ALL_GAMES_DATA = newData;
        renderGames();
        return;
    }

    ALL_GAMES_DATA = newData;
    
    // Surgically inject HTML changes into DOM only if they differ
    newData.forEach(match => {
        const fixId = match.fixture.id;
        const timeEl = document.getElementById(`time-${fixId}`);
        const scoreEl = document.getElementById(`score-${fixId}`);
        const eventsEl = document.getElementById(`events-${fixId}`);
        const oddsEl = document.getElementById(`odds-${fixId}`);
        const injuriesEl = document.getElementById(`injuries-${fixId}`);
        
        if (timeEl && scoreEl && eventsEl && oddsEl && injuriesEl) {
            const newTimeHtml = getTimeBadgeHtml(match);
            const newScoreHtml = getScoreHtml(match);
            const newEventsHtml = getEventsHtml(match);
            const newOddsHtml = getOddsHtml(match);
            const newInjuriesHtml = getInjuriesHtml(match);
            
            if (timeEl.innerHTML !== newTimeHtml) timeEl.innerHTML = newTimeHtml;
            if (scoreEl.innerHTML !== newScoreHtml) scoreEl.innerHTML = newScoreHtml;
            if (eventsEl.innerHTML !== newEventsHtml) eventsEl.innerHTML = newEventsHtml;
            if (oddsEl.innerHTML !== newOddsHtml) oddsEl.innerHTML = newOddsHtml;
            if (injuriesEl.innerHTML !== newInjuriesHtml) injuriesEl.innerHTML = newInjuriesHtml;
        }
    });
}

// ==========================================
// 4. MAIN APP LOGIC 
// ==========================================
async function init() {
    const params = getUrlParams();
    updateSEO(params.league, params.date);
    renderLeagueMenu(params.league, params.date);
    
    const container = document.getElementById('games-container');
    const datePicker = document.getElementById('date-picker');
    if (datePicker) datePicker.value = params.date;

    container.innerHTML = `<div class="col-12 text-center mt-5 pt-5"><div class="spinner-border text-success" role="status"></div><p class="mt-3 text-muted fw-bold">Loading Pitch Data...</p></div>`;
    
    ALL_GAMES_DATA = await fetchMatchesData(params);

    if (!ALL_GAMES_DATA || ALL_GAMES_DATA.length === 0) {
        container.innerHTML = `<div class="col-12 text-center mt-5"><div class="alert alert-light border shadow-sm py-4"><h5 class="text-muted mb-0">No matches found for ${params.date}.</h5></div></div>`;
        return;
    }

    renderGames();
    
    // Start Silent Sync Engine (Refresh every 60 seconds)
    setInterval(updateLiveGames, 60000); 
}

function renderGames() {
    const container = document.getElementById('games-container');
    container.innerHTML = '';
    const searchInput = document.getElementById('team-search');
    const searchText = searchInput ? searchInput.value.toLowerCase() : '';

    let filteredGames = ALL_GAMES_DATA.filter(item => {
        const matchString = (item.teams.home.name + " " + item.teams.away.name).toLowerCase();
        return matchString.includes(searchText);
    });

    filteredGames.sort((a, b) => {
        const isFinishedA = ['FT', 'AET', 'PEN'].includes(a.fixture.status.short);
        const isFinishedB = ['FT', 'AET', 'PEN'].includes(b.fixture.status.short);
        if (isFinishedA && !isFinishedB) return 1;
        if (!isFinishedA && isFinishedB) return -1;
        return new Date(a.fixture.date) - new Date(b.fixture.date);
    });

    filteredGames.forEach(item => container.appendChild(createGameCard(item)));
}

function createGameCard(data) {
    const gameCard = document.createElement('div');
    gameCard.className = 'col-md-6 col-lg-6 col-xl-4 mb-2';

    const home = data.teams.home;
    const away = data.teams.away;
    const fixId = data.fixture.id;

    const homeRank = home.rank ? `<span class="text-muted" style="font-size: 0.70rem;">[${home.rank}]</span> ` : '';
    const awayRank = away.rank ? ` <span class="text-muted" style="font-size: 0.70rem;">[${away.rank}]</span>` : '';

    const buildLineupList = (lineupData) => {
        if (data.isFallback) return `<div class="p-4 text-center text-muted small fst-italic">Formations & lineups available on match day</div>`;
        if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) return `<div class="p-4 text-center text-muted small fw-bold">Lineup pending...</div>`;
        
        const formationHeader = `<div class="w-100 text-center py-1 fw-bold text-white" style="font-size: 0.65rem; background-color: #198754; border-bottom: 1px solid #146c43;">✅ ${lineupData.formation} FORMATION</div>`;
        const listItems = lineupData.startXI.map(p => {
            const player = p.player;
            let posColor = player.pos === 'G' ? "#dc3545" : player.pos === 'D' ? "#0d6efd" : player.pos === 'M' ? "#20c997" : "#ffc107";
            return `
                <li class="d-flex w-100 px-2 py-1 border-bottom">
                    <span class="text-muted fw-bold d-inline-block text-start" style="font-size: 0.7rem; width: 25px; color: ${posColor} !important;">${player.pos}</span>
                    <span class="batter-name fw-bold text-dark text-truncate" style="font-size: 0.85rem;" title="${player.name}">${player.name}</span>
                    <span class="ms-auto text-muted" style="font-size: 0.65rem;">#${player.number}</span>
                </li>`;
        }).join('');
        return `${formationHeader}<ul class="batting-order w-100 m-0 p-0" style="list-style-type: none;">${listItems}</ul>`;
    };

    gameCard.innerHTML = `
        <div class="lineup-card shadow-sm" style="margin-bottom: 8px;" id="card-${fixId}">
            <div class="p-2 pb-1" style="background-color: #fcfcfc;">
                <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom border-light">
                    <div id="time-${fixId}" style="flex: 0 0 auto;" class="pe-2">${getTimeBadgeHtml(data)}</div>
                    <div class="text-muted fw-bold text-uppercase text-end ms-auto text-truncate" style="font-size: 0.70rem;">
                        ${data.league.name}
                    </div>
                </div>
                <div class="d-flex justify-content-between align-items-center px-1 pt-1 pb-1">
                    <div class="text-center" style="width: 38%;"> 
                        <img src="${home.logo}" alt="${home.name}" class="team-logo mb-1">
                        <div class="fw-bold lh-1 text-dark text-truncate" style="font-size: 0.9rem;">${homeRank}${home.name}</div>
                    </div>
                    <div id="score-${fixId}" class="text-center d-flex flex-column align-items-center justify-content-center" style="width: 24%;">
                        ${getScoreHtml(data)}
                    </div>
                    <div class="text-center" style="width: 38%;"> 
                        <img src="${away.logo}" alt="${away.name}" class="team-logo mb-1">
                        <div class="fw-bold lh-1 text-dark text-truncate" style="font-size: 0.9rem;">${away.name}${awayRank}</div>
                    </div>
                </div>
                <div id="events-${fixId}" class="w-100">${getEventsHtml(data)}</div>
            </div>
            <div id="odds-${fixId}" class="w-100">${getOddsHtml(data)}</div>
            <div id="injuries-${fixId}" class="w-100">${getInjuriesHtml(data)}</div>
            
            <div class="bg-light border-bottom text-center py-1">
                <span class="fw-bold text-muted" style="font-size: 0.7rem;">STARTING XI</span>
            </div>
            <div class="row g-0 bg-white">
                <div class="col-6 border-end">${buildLineupList(data.homeLineup)}</div>
                <div class="col-6">${buildLineupList(data.awayLineup)}</div>
            </div>
        </div>`;
    
    return gameCard;
}

document.addEventListener('DOMContentLoaded', () => {
    init();
    const datePicker = document.getElementById('date-picker');
    if (datePicker) {
        datePicker.addEventListener('change', (e) => {
            if (e.target.value) { window.location.href = `?league=${getUrlParams().league}&date=${e.target.value}`; }
        });
    }
    const searchInput = document.getElementById('team-search');
    if (searchInput) searchInput.addEventListener('input', renderGames);
});

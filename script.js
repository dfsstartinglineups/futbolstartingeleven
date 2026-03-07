// ==========================================
// CONFIGURATION
// ==========================================
const DEFAULT_DATE = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
let ALL_GAMES_DATA = []; 

let savedLineupState = localStorage.getItem('futbolLineupsExpanded');
let globalLineupsExpanded = savedLineupState !== null ? savedLineupState === 'true' : true; 

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
// 1. UI HELPERS
// ==========================================
function getTimeBadgeHtml(data) {
    const status = data.fixture.status.short;
    const dateObj = new Date(data.fixture.date);
    const matchTime = dateObj.toLocaleDateString([], {weekday: 'short'}) + ' ' + dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    const isFinished = ['FT', 'AET', 'PEN'].includes(status);
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);

    if (isDelayed) return `<span class="badge bg-danger text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${status}</span>`;
    if (!isPreGame && !isFinished && !data.isFallback) {
        let displayMin = data.fixture.status.elapsed;
        if (status === 'ET') displayMin += 15;
        if (status === 'BT') displayMin = 'ET HT';
        else if (status === 'P') displayMin = 'PEN';
        else displayMin = `${displayMin}'`;
        return `<span class="badge bg-success text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;"><span class="live-dot"></span>${displayMin}</span>`;
    }
    if (isFinished) return `<span class="badge bg-dark text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">FT</span>`;
    return `<span class="badge bg-white text-dark shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${matchTime}</span>`;
}

function getScoreHtml(data) {
    const isPreGame = ['NS', 'TBD'].includes(data.fixture.status.short);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(data.fixture.status.short);
    if (!isPreGame && !isDelayed && !data.isFallback) {
        return `<div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">${data.goals.home} - ${data.goals.away}</div>`;
    }
    return `<div class="text-muted mx-2" style="font-size: 0.8rem;">vs</div>`;
}

function getEventsHtml(data) {
    if (!data.events || data.events.length === 0) return '';
    const formatEvents = (evs, teamName) => evs.map(e => {
        let icon = e.type === 'Goal' ? '⚽' : '🟥';
        let pName = (e.player && e.player !== "null") ? e.player : teamName;
        return `<span class="d-inline-block me-1">${icon} <span class="text-dark fw-bold">${pName}</span> ${e.time}'</span>`;
    }).join(' ');

    return `<div class="w-100 px-2 pt-1 mt-1 border-top" style="font-size: 0.65rem;">
        <div class="d-flex justify-content-between text-muted w-100">
            <div class="event-col text-start pe-1 text-truncate" style="flex: 1;">${formatEvents(data.events.filter(e => e.team_id === data.teams.home.id), data.teams.home.name)}</div>
            <div class="event-col text-end ps-1 text-truncate" style="flex: 1;">${formatEvents(data.events.filter(e => e.team_id === data.teams.away.id), data.teams.away.name)}</div>
        </div>
    </div>`;
}

function getOddsHtml(data) {
    if (!data.odds || (data.odds.home === "TBD")) return '';
    return `<div class="d-flex justify-content-between text-center bg-white border-top border-bottom py-1" style="font-size: 0.70rem;">
        <div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">1</div><div class="fw-bold">${data.odds.home}</div></div>
        <div class="w-25 border-start border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">X</div><div class="fw-bold">${data.odds.draw}</div></div>
        <div class="w-25 border-end"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">2</div><div class="fw-bold">${data.odds.away}</div></div>
        <div class="w-25"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700;">O/U</div><div class="fw-bold">${data.odds.over || '-'}</div></div>
    </div>`;
}

function getInjuriesHtml(data) {
    if (!data.injuries || (data.injuries.home.length === 0 && data.injuries.away.length === 0)) return '';
    return `<div class="border-bottom px-2 py-1 text-center" style="font-size: 0.65rem; background-color: #fff5f5; color: #dc3545;">
        <div class="injury-text text-truncate"><strong>🤕 OUT:</strong> H: ${data.injuries.home.join(', ') || 'None'} | A: ${data.injuries.away.join(', ') || 'None'}</div>
    </div>`;
}

// ==========================================
// 2. DATA & ROUTING
// ==========================================
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return { league: params.get('league') || 'top', date: params.get('date') || DEFAULT_DATE };
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
        const regionLeagues = LEAGUE_GROUPS[region];
        if (!regionLeagues || regionLeagues.length === 0) return; 
        const isActiveRegion = regionLeagues.some(l => l.key === activeLeague);
        const dropdownDiv = document.createElement('div');
        dropdownDiv.className = 'dropdown d-inline-block flex-shrink-0';
        dropdownDiv.innerHTML = `
            <button class="dropdown-toggle league-pill ${isActiveRegion ? 'active' : ''}" type="button" data-bs-toggle="dropdown" aria-expanded="false" style="border: none; background: transparent;">${region}</button>
            <ul class="dropdown-menu dropdown-menu-dark shadow">
                ${regionLeagues.map(l => `<li><a class="dropdown-item ${l.key === activeLeague ? 'text-success' : 'text-light'}" href="?league=${l.key}&date=${currentDate}">${l.name}</a></li>`).join('')}
            </ul>`;
        menu.appendChild(dropdownDiv);
    });

    // Auto-scroll to active league
    setTimeout(() => {
        const active = menu.querySelector('.active');
        if (active) menu.scrollLeft = active.offsetLeft - 20;
    }, 100);
}

async function fetchMatchesData(params) {
    try {
        const res = await fetch(`data/games_${params.date}.json?v=` + new Date().getTime());
        if (res.ok) {
            let data = await res.json();
            if (params.league !== 'top') data = data.filter(m => m.league.id === SUPPORTED_LEAGUES[params.league].id);
            return data;
        }
    } catch (e) { return null; }
}

async function updateLiveGames() {
    const params = getUrlParams();
    const newData = await fetchMatchesData(params);
    if (!newData || newData.length !== ALL_GAMES_DATA.length) {
        if(newData) { ALL_GAMES_DATA = newData; renderGames(); }
        return;
    }
    ALL_GAMES_DATA = newData;
    newData.forEach(match => {
        const fixId = match.fixture.id;
        const scoreEl = document.getElementById(`score-${fixId}`);
        if (scoreEl) {
            const newScore = getScoreHtml(match).trim();
            if (scoreEl.innerHTML.trim() !== newScore) {
                scoreEl.innerHTML = newScore;
                scoreEl.classList.add('flash-green');
                setTimeout(() => scoreEl.classList.remove('flash-green'), 4000);
            }
        }
    });
}

// ==========================================
// 4. MAIN INIT
// ==========================================
async function init() {
    const params = getUrlParams();
    renderLeagueMenu(params.league, params.date);
    const datePicker = document.getElementById('date-picker');
    if (datePicker) datePicker.value = params.date;

    ALL_GAMES_DATA = await fetchMatchesData(params);
    if (!ALL_GAMES_DATA || ALL_GAMES_DATA.length === 0) {
        document.getElementById('games-container').innerHTML = `<div class="col-12 text-center mt-5">No matches found.</div>`;
        return;
    }
    renderGames();
    setInterval(updateLiveGames, 60000); 
}

function renderGames() {
    const container = document.getElementById('games-container');
    container.innerHTML = '';
    const search = document.getElementById('team-search').value.toLowerCase();
    
    ALL_GAMES_DATA.filter(m => (m.teams.home.name + m.teams.away.name).toLowerCase().includes(search))
    .forEach(m => container.appendChild(createGameCard(m)));
}

function createGameCard(data) {
    const card = document.createElement('div');
    card.className = 'col-md-6 col-lg-6 col-xl-4 mb-2';
    const fixId = data.fixture.id;
    
    const buildList = (lineup) => {
        if (!lineup || !lineup.startXI) return '<div class="p-4 text-center small">Pending...</div>';
        return `<div class="w-100 text-center py-1 fw-bold text-white small" style="background-color: #198754;">${lineup.formation}</div>
        <ul class="batting-order small">${lineup.startXI.map(p => `<li class="d-flex px-2 py-1 border-bottom"><span>${p.player.pos}</span><span class="batter-name ms-2">${p.player.name}</span></li>`).join('')}</ul>`;
    };

    card.innerHTML = `<div class="lineup-card shadow-sm">
        <div class="p-2 pb-1 bg-light">
            <div class="d-flex justify-content-between border-bottom pb-1 mb-2">
                <div id="time-${fixId}">${getTimeBadgeHtml(data)}</div>
                <div class="small fw-bold text-muted">${data.league.name}</div>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <div class="text-center w-25"><img src="${data.teams.home.logo}" class="team-logo"><div class="fw-bold small">${data.teams.home.name}</div></div>
                <div id="score-${fixId}" class="text-center">${getScoreHtml(data)}</div>
                <div class="text-center w-25"><img src="${data.teams.away.logo}" class="team-logo"><div class="fw-bold small">${data.teams.away.name}</div></div>
            </div>
            ${getEventsHtml(data)}
        </div>
        ${getOddsHtml(data)}
        ${getInjuriesHtml(data)}
        <div class="bg-light border-bottom text-center py-1" data-bs-toggle="collapse" data-bs-target="#lineup-${fixId}" style="cursor:pointer">STARTING XI ▼</div>
        <div class="collapse ${globalLineupsExpanded ? 'show' : ''} lineup-container" id="lineup-${fixId}">
            <div class="row g-0"><div class="col-6 border-end">${buildList(data.homeLineup)}</div><div class="col-6">${buildList(data.awayLineup)}</div></div>
        </div>
    </div>`;
    return card;
}

document.addEventListener('DOMContentLoaded', () => {
    init();
    document.getElementById('team-search').addEventListener('input', renderGames);
    document.getElementById('date-picker').addEventListener('change', (e) => window.location.href = `?league=${getUrlParams().league}&date=${e.target.value}`);
    document.getElementById('toggle-all-lineups').addEventListener('click', function() {
        globalLineupsExpanded = !globalLineupsExpanded;
        localStorage.setItem('futbolLineupsExpanded', globalLineupsExpanded);
        this.innerHTML = globalLineupsExpanded ? '🔼 COLLAPSE ALL LINEUPS' : '🔽 EXPAND ALL LINEUPS';
        document.querySelectorAll('.lineup-container').forEach(c => globalLineupsExpanded ? c.classList.add('show') : c.classList.remove('show'));
    });
});

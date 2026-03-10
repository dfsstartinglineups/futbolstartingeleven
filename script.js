// ==========================================
// CONFIGURATION
// ==========================================
const DEFAULT_DATE = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
let ALL_GAMES_DATA = []; 

// Check local storage for the user's saved preference
let savedLineupState = localStorage.getItem('futbolLineupsExpanded');
let globalLineupsExpanded = savedLineupState !== null ? savedLineupState === 'true' : true; 

const X_SVG_PATH = "M12.6.75h2.454l-5.36 6.142L16 15.25h-4.937l-3.867-5.07-4.425 5.07H.316l5.733-6.57L0 .75h5.063l3.495 4.633L12.601.75Zm-.86 13.028h1.36L4.323 2.145H2.865l8.875 11.633Z";

const LEAGUE_GROUPS = {
    "priority": [
        { key: "top", id: "top", name: "Top Matches" },
        { key: "epl", id: 39, name: "Premier League" },
        { key: "laliga", id: 140, name: "La Liga" },
        { key: "seriea", id: 135, name: "Serie A" },
        { key: "bundesliga", id: 78, name: "Bundesliga" },
        { key: "ligue1", id: 61, name: "Ligue 1" }
    ],
    "champions": [
        { key: "ucl", id: 2, name: "Champions League" },
        { key: "uel", id: 3, name: "Europa League" },
        { key: "uecl", id: 848, name: "Conference League" }
    ],
    "americas": [
        { key: "mls", id: 253, name: "MLS" },
        { key: "ligamx", id: 262, name: "Liga MX" },
        { key: "brazil", id: 71, name: "Brasileirão" },
        { key: "argentina", id: 128, name: "Primera División" }
    ],
    "international": [
        { key: "worldcup", id: 1, name: "World Cup" },
        { key: "euro", id: 4, name: "Euro" },
        { key: "copa", id: 9, name: "Copa America" }
    ]
};

// ==========================================
// 1. URL & FILTER STATE MANAGEMENT
// ==========================================
function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return {
        date: params.get('date') || DEFAULT_DATE,
        league: params.get('league') || 'top' 
    };
}

function updateUrlParams(date, league) {
    const newUrl = `${window.location.pathname}?league=${league}&date=${date}`;
    window.history.pushState({ path: newUrl }, '', newUrl);
}

// ==========================================
// 2. MAIN APP LOGIC 
// ==========================================

function populateLeagueFilter() {
    const filterContainer = document.getElementById('league-filter-container');
    if (!filterContainer) return;

    let html = '<ul class="nav nav-pills nav-fill flex-nowrap" style="overflow-x: auto; -webkit-overflow-scrolling: touch; padding-bottom: 5px;">';
    
    // Flatten all groups into a single horizontal scrollable list
    Object.values(LEAGUE_GROUPS).forEach(group => {
        group.forEach(l => {
            html += `
                <li class="nav-item me-1">
                    <button class="nav-link border btn-sm text-nowrap league-btn" data-league="${l.key}" style="border-radius: 20px; font-weight: 600; font-size: 0.8rem; padding: 0.25rem 0.75rem; color: #495057; background-color: #f8f9fa;">
                        ${l.name}
                    </button>
                </li>
            `;
        });
    });
    
    html += '</ul>';
    filterContainer.innerHTML = html;

    // Attach click events to the new buttons
    document.querySelectorAll('.league-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.league-btn').forEach(b => {
                b.style.backgroundColor = '#f8f9fa';
                b.style.color = '#495057';
                b.style.borderColor = '#dee2e6';
            });
            
            const selectedBtn = e.target;
            selectedBtn.style.backgroundColor = '#212529'; // Dark active state
            selectedBtn.style.color = '#fff';
            selectedBtn.style.borderColor = '#212529';
            
            const selectedLeague = selectedBtn.getAttribute('data-league');
            const dateStr = document.getElementById('date-picker').value || DEFAULT_DATE;
            
            updateUrlParams(dateStr, selectedLeague);
            renderGames();
        });
    });
}

function selectActiveLeagueButton(leagueKey) {
    document.querySelectorAll('.league-btn').forEach(b => {
        if (b.getAttribute('data-league') === leagueKey) {
            b.style.backgroundColor = '#212529';
            b.style.color = '#fff';
            b.style.borderColor = '#212529';
            // Auto-scroll the horizontal list to show the active button
            b.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
        } else {
            b.style.backgroundColor = '#f8f9fa';
            b.style.color = '#495057';
            b.style.borderColor = '#dee2e6';
        }
    });
}

function getActiveLeagueIds() {
    const currentLeagueKey = getUrlParams().league;
    
    // "top" shows all top 5 European leagues + UCL
    if (currentLeagueKey === 'top') {
        return [39, 140, 135, 78, 61, 2];
    }
    
    // Otherwise find the specific league ID
    for (const group in LEAGUE_GROUPS) {
        for (const l of LEAGUE_GROUPS[group]) {
            if (l.key === currentLeagueKey) {
                return [l.id];
            }
        }
    }
    return [39]; // Default fallback
}

// ==========================================
// CARD HIGHLIGHT ENGINE
// ==========================================
function triggerCardHighlight(targetCard, type) {
    if (!targetCard) return;
    
    const innerHeader = targetCard.querySelector('.p-2.pb-1');
    let borderColor, boxShadowColor, headerBgColor;

    if (type === 'goal' || type === 'hash') { // Futbol Green
        borderColor = '#20c997';
        boxShadowColor = 'rgba(32, 201, 151, 0.8)';
        headerBgColor = '#d1e7dd';
    } else if (type === 'red_card') { // Futbol Red
        borderColor = '#dc3545';
        boxShadowColor = 'rgba(220, 53, 69, 0.8)';
        headerBgColor = '#f8d7da';
    } else if (type === 'yellow_card') { // Yellow Card
        borderColor = '#ffc107';
        boxShadowColor = 'rgba(255, 193, 7, 0.8)';
        headerBgColor = '#fff3cd';
    }
    
    targetCard.style.transition = 'all 0.4s ease-out';
    targetCard.style.transform = 'scale(1.02)';
    targetCard.style.setProperty('border', `3px solid ${borderColor}`, 'important');
    targetCard.style.setProperty('box-shadow', `0 0 25px ${boxShadowColor}`, 'important');
    targetCard.style.position = 'relative'; 
    targetCard.style.zIndex = '10';
    
    if (innerHeader) {
        innerHeader.classList.remove('bg-light');
        innerHeader.style.transition = 'background-color 0.4s ease-out';
        innerHeader.style.backgroundColor = headerBgColor; 
    }
    
    setTimeout(() => {
        targetCard.style.transform = 'scale(1)';
        targetCard.style.removeProperty('border'); 
        targetCard.style.setProperty('box-shadow', '0 2px 4px rgba(0,0,0,0.05)', 'important');
        targetCard.style.zIndex = '1';
        
        if (innerHeader) {
            innerHeader.style.backgroundColor = '';
            innerHeader.classList.add('bg-light');
        }
    }, 4000); 
}

async function init(dateToFetch) {
    if (window.updateSEO) window.updateSEO(dateToFetch);
    const container = document.getElementById('games-container');
    const datePicker = document.getElementById('date-picker');
    if (datePicker) datePicker.value = dateToFetch;

    // Build the horizontal nav
    populateLeagueFilter();
    selectActiveLeagueButton(getUrlParams().league);

    if (container) {
        container.innerHTML = `
            <div class="col-12 text-center mt-5 pt-5">
                <div class="spinner-border" style="color: #20c997;" role="status"></div>
                <p class="mt-3 text-muted fw-bold">Loading Global Fixtures...</p>
            </div>`;
    }
    
    try {
        const response = await fetch(`data/games_${dateToFetch}.json?v=` + new Date().getTime());
        if (!response.ok) throw new Error("No data found");
        ALL_GAMES_DATA = await response.json();
        
        renderGames();
        handleHashNavigation();
        startPolling(dateToFetch);
        
    } catch (error) {
        console.error("Init error:", error);
        if (container) container.innerHTML = `<div class="col-12 text-center mt-5"><div class="alert alert-light border text-muted py-4">No fixtures found for ${dateToFetch}. Try another date.</div></div>`;
    }
}

function handleHashNavigation() {
    if (window.location.hash) {
        setTimeout(() => {
            const targetCard = document.querySelector(window.location.hash);
            if (targetCard) {
                targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                triggerCardHighlight(targetCard, 'hash'); // Reuses the new highlight engine
            }
        }, 600); 
    }
}

function renderGames() {
    const container = document.getElementById('games-container');
    if (!container) return;
    container.innerHTML = '';
    
    const searchText = document.getElementById('team-search')?.value.toLowerCase() || '';
    const activeLeagueIds = getActiveLeagueIds();
    
    let filteredGames = ALL_GAMES_DATA.filter(item => {
        const matchSearch = (item.teams.home.name + " " + item.teams.away.name).toLowerCase().includes(searchText);
        const matchLeague = activeLeagueIds.includes(item.league.id);
        return matchSearch && matchLeague;
    });
    
    // Group games by League
    const gamesByLeague = {};
    filteredGames.forEach(game => {
        const lName = game.league.name;
        if (!gamesByLeague[lName]) gamesByLeague[lName] = { logo: game.league.logo, matches: [] };
        gamesByLeague[lName].matches.push(game);
    });
    
    if (Object.keys(gamesByLeague).length === 0) {
        container.innerHTML = `<div class="col-12 text-center mt-5 text-muted">No matches match your filter criteria.</div>`;
        return;
    }
    
    // Render leagues and their games
    for (const [leagueName, leagueData] of Object.entries(gamesByLeague)) {
        // Sort matches: Live first, then by time
        leagueData.matches.sort((a, b) => {
            const aLive = ["1H", "HT", "2H", "ET", "P"].includes(a.fixture.status.short);
            const bLive = ["1H", "HT", "2H", "ET", "P"].includes(b.fixture.status.short);
            if (aLive && !bLive) return -1;
            if (!aLive && bLive) return 1;
            return a.fixture.timestamp - b.fixture.timestamp;
        });

        // League Header
        const header = document.createElement('div');
        header.className = 'col-12 mt-4 mb-2 d-flex align-items-center';
        header.innerHTML = `
            <img src="${leagueData.logo}" alt="${leagueName}" style="width: 24px; height: 24px; object-fit: contain; margin-right: 8px;">
            <h5 class="fw-bold m-0" style="color: #212529;">${leagueName}</h5>
            <div style="flex-grow: 1; height: 1px; background-color: #dee2e6; margin-left: 15px;"></div>
        `;
        container.appendChild(header);

        // Games Grid
        const grid = document.createElement('div');
        grid.className = 'row g-3 w-100 m-0';
        leagueData.matches.forEach(item => grid.appendChild(createGameCard(item)));
        container.appendChild(grid);
    }
}

function shortenPlayerName(fullName) {
    if (!fullName) return '';
    const parts = fullName.split(' ');
    if (parts.length === 1) return parts[0];
    
    // Special handling for Brazilian/Portuguese single names often returned as full strings
    // but typically we just want the initial + last name for UI brevity
    return `${parts[0].charAt(0)}. ${parts[parts.length - 1]}`;
}

function createGameCard(data) {
    const gameCard = document.createElement('div');
    gameCard.className = 'col-md-6 col-lg-6 col-xl-4 mb-2';
    
    const statusShort = data.fixture.status.short;
    const isLive = ["1H", "HT", "2H", "ET", "P"].includes(statusShort);
    const isFinished = ["FT", "AET", "PEN"].includes(statusShort);
    
    let statusBadgeColor = "bg-dark";
    let statusText = new Date(data.fixture.date).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    
    if (isLive) {
        statusBadgeColor = "bg-danger";
        statusText = statusShort === "HT" ? "HT" : `${data.fixture.status.elapsed}'`;
        statusText += ` <span class="spinner-grow spinner-grow-sm align-middle" style="width: 0.5rem; height: 0.5rem;" role="status"></span>`;
    } else if (isFinished) {
        statusBadgeColor = "bg-secondary";
        statusText = "FT";
    }

    let latestEvent = '';
    if (!isFinished && data.events && data.events.length > 0) {
        const lastEv = data.events[data.events.length - 1]; 
        const currentMinute = data.fixture.status.elapsed || 0;
        const eventMinute = parseInt(lastEv.time) || 0;
        
        // Show banner if the event happened in the last 5 minutes of game time
        if (currentMinute - eventMinute <= 5) {
            let icon = '🟥';
            if (lastEv.type === 'Goal') {
                icon = '⚽';
            } else if (lastEv.detail && lastEv.detail.includes('Yellow')) {
                icon = lastEv.detail.includes('Red') || lastEv.detail.includes('Second') ? '🟨🟥' : '🟨';
            }
            const isHomeTeam = lastEv.team_id === data.teams.home.id;
            const teamName = isHomeTeam ? data.teams.home.name : data.teams.away.name;
            const teamLogo = isHomeTeam ? data.teams.home.logo : data.teams.away.logo; 
            const playerName = (lastEv.player && lastEv.player !== "null") ? lastEv.player : teamName;
            
            latestEvent = `<span class="ms-2 text-success fw-bold text-truncate" style="font-size: 0.70rem; max-width: 150px; display: inline-block; vertical-align: middle;">
                ${icon} <img src="${teamLogo}" alt="${teamName}" style="width: 14px; height: 14px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> ${playerName} (${lastEv.time}')
            </span>`;
        }
    }

    const homeRank = data.teams.home.rank ? `<span class="badge bg-secondary rounded-pill me-1" style="font-size:0.55rem; padding: 2px 4px;">${data.teams.home.rank}</span>` : '';
    const awayRank = data.teams.away.rank ? `<span class="badge bg-secondary rounded-pill me-1" style="font-size:0.55rem; padding: 2px 4px;">${data.teams.away.rank}</span>` : '';

    const buildLineupList = (lineupObj, teamId) => {
        if (!lineupObj || !lineupObj.startXI) {
            return `<div class="p-3 text-center text-muted small fw-bold" style="font-style: italic;">Lineup pending...</div>`;
        }
        
        let headerHtml = `<div class="text-center py-1 fw-bold text-white" style="font-size: 0.6rem; background-color: #20c997; letter-spacing: 0.5px;">✅ OFFICIAL <span style="font-size: 0.55rem; opacity: 0.8;">(${lineupObj.formation})</span></div>`;
        
        const items = lineupObj.startXI.map((slot) => {
            const p = slot.player;
            const posClass = p.pos === 'G' ? 'bg-warning text-dark' : 'bg-light text-muted border';
            
            const stats = p.season_stats ? p.season_stats.total : null;
            let statsHtml = '';
            let isInjured = false;
            
            if (data.injuries) {
                const teamInjs = teamId === data.teams.home.id ? data.injuries.home : data.injuries.away;
                if (teamInjs && teamInjs.includes(p.name)) isInjured = true;
            }

            if (stats) {
                let primaryStat = p.pos === 'G' ? `${stats.games} Apps` : (p.pos === 'D' ? `${stats.assists}A | ${stats.yellow_cards}🟨` : `${stats.goals}G | ${stats.assists}A`);
                let ratingColor = stats.rating >= 7.0 ? '#198754' : (stats.rating >= 6.5 ? '#6c757d' : '#dc3545');
                let ratingDisplay = stats.rating !== "N/A" ? `<span class="badge rounded-pill" style="background-color: ${ratingColor}; font-size: 0.55rem;">${stats.rating}</span>` : '';
                
                statsHtml = `
                <div class="w-100 d-flex justify-content-between align-items-center mt-1" style="font-size: 0.60rem; color: #adb5bd;">
                    <span>${primaryStat}</span>
                    ${ratingDisplay}
                </div>`;
            }
            
            const pDataAttr = encodeURIComponent(JSON.stringify(p));

            return `
            <li class="px-2 py-1 border-bottom d-flex flex-column" style="cursor: pointer;" onclick="showPlayerModal('${pDataAttr}')">
                <div class="d-flex w-100 justify-content-start align-items-center">
                    <span class="badge ${posClass} me-2 text-center" style="font-size: 0.65rem; width: 22px;">${p.pos}</span>
                    <span class="fw-bold text-truncate ${isInjured ? 'text-danger text-decoration-line-through' : 'text-dark'}" style="font-size: 0.8rem; max-width: 80%;">${p.name}</span>
                </div>
                ${statsHtml}
            </li>`;
        }).join('');
        
        return `${headerHtml}<ul class="list-unstyled m-0">${items}</ul>`;
    };

    const buildEventsHtml = () => {
        if (!data.events || data.events.length === 0) return '';
        const homeEvents = data.events.filter(e => e.team_id === data.teams.home.id);
        const awayEvents = data.events.filter(e => e.team_id === data.teams.away.id);
        
        const formatSingleEvent = (e, teamName) => {
            let icon = '🟥';
            if (e.type === 'Goal') {
                icon = '⚽';
            } else if (e.detail && e.detail.includes('Yellow')) {
                icon = e.detail.includes('Red') || e.detail.includes('Second') ? '🟨🟥' : '🟨';
            }
            let playerName = (e.player && e.player !== "null") ? shortenPlayerName(e.player) : teamName;
            return `${icon} <span class="text-dark fw-bold">${playerName}</span> ${e.time}'`;
        };

        const renderEventSide = (evs, teamName, isHome) => {
            if (evs.length === 0) return '';
            
            // Reverse array so the most recent event is at the top/index 0
            const reversedEvs = [...evs].reverse();

            if (reversedEvs.length === 1) {
                return `<div class="text-truncate">${formatSingleEvent(reversedEvs[0], teamName)}</div>`;
            }

            // Collapsed view shows just the most recent event
            const firstEvent = formatSingleEvent(reversedEvs[0], teamName);
            
            // Expanded view stacks all events vertically descending
            const allEvents = reversedEvs.map(e => `<div class="text-truncate" style="margin-bottom: 2px;">${formatSingleEvent(e, teamName)}</div>`).join('');

            return `
                <div class="event-collapsed">
                    <div class="text-truncate">${firstEvent} <span class="badge bg-light border text-muted" style="font-size: 0.5rem;">+${reversedEvs.length - 1}</span></div>
                </div>
                <div class="event-expanded" style="display: none;">
                    ${allEvents}
                </div>
            `;
        };

        return `
            <div class="row g-0 px-2 py-1 align-items-start" style="font-size: 0.70rem; color: #495057;">
                <div class="col-5 text-end pe-2" style="border-right: 1px solid #dee2e6;">${renderEventSide(homeEvents, data.teams.home.name, true)}</div>
                <div class="col-2 text-center text-muted fw-bold" style="font-size: 0.65rem; cursor: pointer;" onclick="toggleEvents(this)">
                    <span class="event-toggle-btn text-primary">Details <i class="fas fa-chevron-down"></i></span>
                </div>
                <div class="col-5 ps-2">${renderEventSide(awayEvents, data.teams.away.name, false)}</div>
            </div>
        `;
    };

    const homeLineupHtml = buildLineupList(data.homeLineup, data.teams.home.id);
    const awayLineupHtml = buildLineupList(data.awayLineup, data.teams.away.id);
    const eventsHtml = buildEventsHtml();
    
    // Odds handling
    let oddsHtml = '';
    if (!isLive && !isFinished && data.odds) {
        oddsHtml = `
        <div class="d-flex justify-content-between px-2 py-1 bg-light border-bottom" style="font-size: 0.65rem;">
            <div class="text-muted fw-bold">ODDS</div>
            <div class="d-flex gap-2 fw-bold text-dark">
                <span>${data.teams.home.short || 'H'}: <span class="text-primary">${data.odds.home}</span></span>
                <span>D: <span class="text-primary">${data.odds.draw}</span></span>
                <span>${data.teams.away.short || 'A'}: <span class="text-primary">${data.odds.away}</span></span>
                <span class="border-start ps-2">O/U ${data.odds.total}: <span class="text-primary">${data.odds.over}</span></span>
            </div>
        </div>`;
    }

    const showClass = globalLineupsExpanded ? 'show' : '';

    gameCard.innerHTML = `
        <div class="lineup-card shadow-sm border rounded bg-white overflow-hidden" id="card-${data.fixture.id}">
            <div class="p-2 pb-1 border-bottom bg-light">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <div class="d-flex align-items-center">
                        <span class="badge ${statusBadgeColor} text-white px-2 py-1" style="font-size: 0.70rem;">${statusText}</span>
                        ${latestEvent}
                    </div>
                </div>
            </div>
            ${oddsHtml}
            <div class="p-2 d-flex align-items-center justify-content-between text-center bg-white pb-2">
                <div style="width: 40%;" class="d-flex flex-column align-items-center">
                    <img src="${data.teams.home.logo}" style="width: 45px; height: 45px; object-fit: contain; margin-bottom: 5px;">
                    <div class="fw-bold text-dark lh-1" style="font-size: 0.85rem; letter-spacing: -0.3px;">${homeRank}${data.teams.home.name}</div>
                    <div class="text-muted mt-1" style="font-size: 0.65rem;">${data.teams.home.record || '0-0-0'}</div>
                </div>
                
                <div style="width: 20%;" class="d-flex flex-column align-items-center justify-content-center">
                     <div class="fw-bold text-dark" style="font-size: 1.8rem; letter-spacing: -1px; line-height: 1;">
                        ${data.goals.home !== null ? data.goals.home : '-'} : ${data.goals.away !== null ? data.goals.away : '-'}
                     </div>
                </div>
                
                <div style="width: 40%;" class="d-flex flex-column align-items-center">
                    <img src="${data.teams.away.logo}" style="width: 45px; height: 45px; object-fit: contain; margin-bottom: 5px;">
                    <div class="fw-bold text-dark lh-1" style="font-size: 0.85rem; letter-spacing: -0.3px;">${awayRank}${data.teams.away.name}</div>
                    <div class="text-muted mt-1" style="font-size: 0.65rem;">${data.teams.away.record || '0-0-0'}</div>
                </div>
            </div>
            
            ${eventsHtml ? `<div class="border-top bg-light pb-1">${eventsHtml}</div>` : ''}
            
            <div class="collapse ${showClass} lineup-container border-top">
                <div class="row g-0">
                    <div class="col-6 border-end">${homeLineupHtml}</div>
                    <div class="col-6">${awayLineupHtml}</div>
                </div>
            </div>
        </div>`;
        
    return gameCard;
}

window.toggleEvents = function(element) {
    const row = element.closest('.row');
    const collapsedView = row.querySelectorAll('.event-collapsed');
    const expandedView = row.querySelectorAll('.event-expanded');
    const icon = element.querySelector('i');
    
    const isExpanded = icon.classList.contains('fa-chevron-up');
    
    if (isExpanded) {
        collapsedView.forEach(el => el.style.display = 'block');
        expandedView.forEach(el => el.style.display = 'none');
        icon.classList.replace('fa-chevron-up', 'fa-chevron-down');
    } else {
        collapsedView.forEach(el => el.style.display = 'none');
        expandedView.forEach(el => el.style.display = 'block');
        icon.classList.replace('fa-chevron-down', 'fa-chevron-up');
    }
};

window.showPlayerModal = function(playerDataStr) {
    try {
        const p = JSON.parse(decodeURIComponent(playerDataStr));
        
        document.getElementById('modal-player-name').textContent = p.name || 'Unknown Player';
        document.getElementById('modal-player-bio').textContent = `${p.pos || 'Flex'} • ${p.age || '?'} yrs • ${p.nationality || 'Unknown'}`;
        
        const photoEl = document.getElementById('modal-player-photo');
        const initialsEl = document.getElementById('modal-player-initials');
        
        if (p.photo) {
            photoEl.src = p.photo;
            photoEl.style.display = 'block';
            initialsEl.style.display = 'none';
        } else {
            photoEl.style.display = 'none';
            initialsEl.textContent = p.name ? p.name.substring(0,2).toUpperCase() : '?';
            initialsEl.style.display = 'flex';
        }
        
        const statsContainer = document.getElementById('modal-player-stats-container');
        statsContainer.innerHTML = '';
        
        if (p.season_stats && p.season_stats.competitions) {
            for (const [league, stats] of Object.entries(p.season_stats.competitions)) {
                let ratingColor = stats.rating >= 7.0 ? '#20c997' : (stats.rating >= 6.5 ? '#6c757d' : '#dc3545');
                
                statsContainer.innerHTML += `
                    <div class="col-12 text-start border-bottom py-2">
                        <div class="fw-bold text-dark mb-1" style="font-size: 0.85rem;">${league}</div>
                        <div class="d-flex justify-content-between" style="font-size: 0.75rem; color: #495057;">
                            <span>${stats.games} Apps</span>
                            <span>${stats.goals}G | ${stats.assists}A</span>
                            <span>${stats.yellow_cards}🟨 | ${stats.red_cards}🟥</span>
                            <span class="badge rounded-pill" style="background-color: ${ratingColor};">${stats.rating}</span>
                        </div>
                    </div>
                `;
            }
        } else {
            statsContainer.innerHTML = '<div class="col-12 text-muted py-3">No season statistics available.</div>';
        }
        
        const modal = new bootstrap.Modal(document.getElementById('playerStatsModal'));
        modal.show();
    } catch(e) {
        console.error("Error showing player modal", e);
    }
};

// ==========================================
// LIVE POLLING ENGINE
// ==========================================
let pollingInterval;

function startPolling(dateStr) {
    if (pollingInterval) clearInterval(pollingInterval);
    
    const isToday = dateStr === new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
    if (!isToday) return; 

    pollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`data/games_${dateStr}.json?v=` + new Date().getTime());
            if (!response.ok) return;
            
            const newGamesData = await response.json();
            let needsRender = false;

            newGamesData.forEach(match => {
                const oldMatch = ALL_GAMES_DATA.find(g => g.fixture.id === match.fixture.id);
                if (oldMatch) {
                    const statusChanged = oldMatch.fixture.status.short !== match.fixture.status.short;
                    const goalsChanged = oldMatch.goals.home !== match.goals.home || oldMatch.goals.away !== match.goals.away;
                    const lineupsEmerged = !oldMatch.homeLineup && match.homeLineup;
                    const oddsUpdated = JSON.stringify(oldMatch.odds) !== JSON.stringify(match.odds);
                    
                    const oldLen = oldMatch.events ? oldMatch.events.length : 0;
                    const newLen = match.events ? match.events.length : 0;
                    const eventAdded = newLen > oldLen;

                    if (statusChanged || goalsChanged || lineupsEmerged || eventAdded || oddsUpdated) {
                        needsRender = true;
                        
                        // Fire the beautiful CSS highlight engine if a goal/card was just added
                        if (eventAdded) {
                            setTimeout(() => {
                                const cardEl = document.getElementById(`card-${match.fixture.id}`);
                                const latestEvent = match.events[newLen - 1]; 
                                
                                if (latestEvent.type === 'Goal') {
                                    triggerCardHighlight(cardEl, 'goal');
                                } else if (latestEvent.type === 'Card' && latestEvent.detail) {
                                    if (latestEvent.detail.includes('Second') || latestEvent.detail.includes('Yellow / Red')) {
                                        triggerCardHighlight(cardEl, 'yellow_card');
                                        setTimeout(() => {
                                            triggerCardHighlight(cardEl, 'red_card');
                                        }, 4500); 
                                    } else if (latestEvent.detail.includes('Red')) {
                                        triggerCardHighlight(cardEl, 'red_card');
                                    } else if (latestEvent.detail.includes('Yellow')) {
                                        triggerCardHighlight(cardEl, 'yellow_card');
                                    }
                                }
                            }, 500); 
                        }
                    }
                }
            });

            if (needsRender) {
                ALL_GAMES_DATA = newGamesData;
                const activeLeagueIds = getActiveLeagueIds();
                const container = document.getElementById('games-container');
                const scrollPos = window.scrollY;
                
                renderGames();
                
                window.scrollTo(0, scrollPos);
            }
        } catch (e) {
            console.log("Polling check failed, will retry...", e);
        }
    }, 60000); 
}

// ==========================================
// EVENT LISTENERS
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    init(getUrlParams().date);
    
    function checkOverflows() {
        document.querySelectorAll('.league-btn').forEach(btn => {
            if (btn.scrollWidth > btn.clientWidth) {
                btn.classList.remove('text-truncate');
                btn.style.whiteSpace = 'normal';
            }
        });
    }

    window.addEventListener('resize', () => {
        clearTimeout(window.resizeTimer);
        window.resizeTimer = setTimeout(() => {
            requestAnimationFrame(checkOverflows);
        }, 150);
    });

    const datePicker = document.getElementById('date-picker');
    if (datePicker) {
        datePicker.addEventListener('change', (e) => {
            if (e.target.value) { window.location.href = `?league=${getUrlParams().league}&date=${e.target.value}`; }
        });
    }
    
    const searchInput = document.getElementById('team-search');
    if (searchInput) searchInput.addEventListener('input', renderGames);

    const toggleAllBtn = document.getElementById('toggle-all-lineups');
    if (toggleAllBtn) {
        toggleAllBtn.innerHTML = globalLineupsExpanded ? '🔼 COLLAPSE ALL LINEUPS' : '🔽 EXPAND ALL LINEUPS';
        
        toggleAllBtn.addEventListener('click', () => {
            globalLineupsExpanded = !globalLineupsExpanded;
            localStorage.setItem('futbolLineupsExpanded', globalLineupsExpanded);
            toggleAllBtn.innerHTML = globalLineupsExpanded ? '🔼 COLLAPSE ALL LINEUPS' : '🔽 EXPAND ALL LINEUPS';
            
            const lineupContainers = document.querySelectorAll('.lineup-container');
            lineupContainers.forEach(container => {
                if (globalLineupsExpanded) {
                    container.classList.add('show');
                } else {
                    container.classList.remove('show');
                }
            });
        });
    }
});

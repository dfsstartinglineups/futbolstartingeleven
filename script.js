// ==========================================
// CONFIGURATION
// ==========================================
const DEFAULT_DATE = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
let ALL_GAMES_DATA = []; 

// Check local storage for the user's saved preferences
let savedLineupState = localStorage.getItem('futbolLineupsExpanded');
let globalLineupsExpanded = savedLineupState !== null ? savedLineupState === 'true' : true; 

let savedScoreboardState = localStorage.getItem('futbolScoreboardMode');
let globalScoreboardMode = savedScoreboardState !== null ? savedScoreboardState === 'true' : false; 

const X_SVG_PATH = "M12.6.75h2.454l-5.36 6.142L16 15.25h-4.937l-3.867-5.07-4.425 5.07H.316l5.733-6.57L0 .75h5.063l3.495 4.633L12.601.75Zm-.86 13.028h1.36L4.323 2.145H2.865l8.875 11.633Z";

// ... (LEAGUE_GROUPS, SUPPORTED_LEAGUES, LEAGUE_MAP_ESPN, toggleExpand, checkOverflows, shortenPlayerName, openPlayerModal ALL REMAIN EXACTLY THE SAME) ...

const LEAGUE_GROUPS = {
    "priority": [
        { key: "top", id: "top", name: "Top Matches" },
        { key: "epl", id: 39, name: "Premier League" },
        { key: "laliga", id: 140, name: "La Liga" },
        { key: "seriea", id: 135, name: "Serie A" }
    ],
    "Europe": [
        { key: "ucl", id: 2, name: "Champions League" },
        { key: "europa", id: 3, name: "Europa League" },
        { key: "facup", id: 45, name: "FA Cup" },
        { key: "championship", id: 40, name: "Championship" },
        { key: "bundesliga", id: 78, name: "Bundesliga" },
        { key: "ligue1", id: 61, name: "Ligue 1" },
        { key: "eredivisie", id: 88, name: "Eredivisie" },
        { key: "portugal", id: 94, name: "Primeira Liga" },
        { key: "conference", id: 848, name: "Conference League" }
    ],
    "Americas": [
        { key: "mls", id: 253, name: "MLS" },
        { key: "ligamx", id: 262, name: "Liga MX" },
        { key: "brazil", id: 71, name: "Brasileirão" },
        { key: "argentina", id: 128, name: "Liga Profesional" },
        { key: "libertadores", id: 13, name: "Copa Libertadores" },
        { key: "concacaf", id: 16, name: "Champions Cup" }
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
    61: "fra.1", 72: "ned.1", 94: "por.1", 2: "uefa.champions", 3: "uefa.europa", 253: "usa.1", 
    262: "mex.1", 71: "bra.1", 128: "arg.1", 13: "conmebol.libertadores", 307: "ksa.1", 98: "jpn.1",
    848: "uefa.conf"
};

window.toggleExpand = function(el) {
    const isExpanded = el.classList.toggle('is-expanded');
    const targets = el.querySelectorAll('.truncate-target');
    const indicator = el.querySelector('.overflow-indicator');
    
    targets.forEach(t => {
        if (isExpanded) {
            t.classList.remove('text-truncate');
            t.style.whiteSpace = 'normal'; 
            t.style.textOverflow = ''; 
        } else {
            t.classList.add('text-truncate');
            t.style.whiteSpace = ''; 
        }
    });
    
    if (indicator) {
        indicator.innerHTML = isExpanded ? '▲' : '▼';
    }

    if (!isExpanded) {
        checkOverflows(); 
    }
};

window.checkOverflows = function() {
    document.querySelectorAll('.expandable-section').forEach(section => {
        const targets = section.querySelectorAll('.truncate-target');
        const indicator = section.querySelector('.overflow-indicator');
        if (!indicator) return;

        if (section.classList.contains('is-expanded')) {
            indicator.classList.remove('d-none');
            targets.forEach(t => t.style.textOverflow = ''); 
            return;
        }

        let hasOverflow = false;
        targets.forEach(t => {
            if (t.scrollWidth > t.clientWidth + 1) {
                hasOverflow = true;
            }
        });

        if (hasOverflow) {
            indicator.classList.remove('d-none');
            targets.forEach(t => {
                t.style.textOverflow = 'clip';
            });
        } else {
            indicator.classList.add('d-none');
            targets.forEach(t => {
                t.style.textOverflow = '';
            });
        }
    });
};

function shortenPlayerName(fullName) {
    if (!fullName) return "Unknown";
    const parts = fullName.split(' ');
    if (parts.length === 1) return fullName;
    const initial = parts[0].charAt(0).toUpperCase() + '.';
    const lastName = parts.slice(1).join(' ');
    return `${initial} ${lastName}`;
}

window.openPlayerModal = function(el) {
    const playerDataStr = el.getAttribute('data-player');
    if (!playerDataStr) return;
    
    const p = JSON.parse(decodeURIComponent(playerDataStr));
    
    const nameEl = document.getElementById('modal-player-name');
    const bioEl = document.getElementById('modal-player-bio');
    const photoEl = document.getElementById('modal-player-photo');
    const initialsEl = document.getElementById('modal-player-initials');
    const statsContainer = document.getElementById('modal-player-stats-container');
    const noStatsEl = document.getElementById('modal-no-stats');

    nameEl.textContent = p.name || 'Unknown Player';
    
    const pos = p.pos || '?';
    const age = p.age ? `${p.age}y` : 'Age N/A';
    const nat = p.nationality || 'N/A';
    bioEl.innerHTML = `<span class="fw-bold text-dark">${pos}</span> &nbsp;•&nbsp; ${age} &nbsp;•&nbsp; ${nat}`;

    if (p.photo && p.photo.includes("http")) {
        photoEl.src = p.photo;
        photoEl.style.display = 'block';
        initialsEl.style.display = 'none';
    } else {
        photoEl.style.display = 'none';
        initialsEl.textContent = p.name ? p.name.charAt(0).toUpperCase() : '?';
        initialsEl.style.display = 'flex';
    }

    statsContainer.innerHTML = '';
    
    if (p.season_stats) {
        const isNested = p.season_stats.total !== undefined;
        const mainStats = isNested ? p.season_stats.total : p.season_stats;
        
        if (mainStats.games > 0) {
            noStatsEl.classList.add('d-none');
            
            const goals = mainStats.goals || 0;
            const assists = mainStats.assists || 0;
            const saves = mainStats.saves || 0;
            const conceded = mainStats.conceded || 0;
            const shotsOn = mainStats.shots_on || 0;
            const keyPasses = mainStats.key_passes || 0;
            const passAcc = mainStats.pass_acc ? `${mainStats.pass_acc}%` : "-";
            const tackles = mainStats.tackles || 0;
            const ints = mainStats.interceptions || 0;
            const yel = mainStats.yellow_cards || 0;
            const rat = mainStats.rating || "-";

            let stats = [];
            
            if (pos === 'G') {
                stats = [
                    { label: "Matches", val: mainStats.games, color: "text-dark" },
                    { label: "Saves", val: saves, color: "text-success" },
                    { label: "Conceded", val: conceded, color: "text-danger" },
                    { label: "Pass Acc", val: passAcc, color: "text-primary" },
                    { label: "Yellows", val: yel, color: "text-warning" },
                    { label: "Rating", val: rat, color: "text-info" }
                ];
            } else if (pos === 'D') {
                stats = [
                    { label: "Matches", val: mainStats.games, color: "text-dark" },
                    { label: "Tackles", val: tackles, color: "text-success" },
                    { label: "Intercepts", val: ints, color: "text-primary" },
                    { label: "Pass Acc", val: passAcc, color: "text-dark" },
                    { label: "Yellows", val: yel, color: "text-warning" },
                    { label: "Rating", val: rat, color: "text-info" }
                ];
            } else if (pos === 'M') {
                stats = [
                    { label: "Matches", val: mainStats.games, color: "text-dark" },
                    { label: "Goals", val: goals, color: "text-success" },
                    { label: "Assists", val: assists, color: "text-primary" },
                    { label: "Key Passes", val: keyPasses, color: "text-dark" },
                    { label: "Pass Acc", val: passAcc, color: "text-dark" },
                    { label: "Rating", val: rat, color: "text-info" }
                ];
            } else { 
                stats = [
                    { label: "Matches", val: mainStats.games, color: "text-dark" },
                    { label: "Goals", val: goals, color: "text-success" },
                    { label: "Assists", val: assists, color: "text-primary" },
                    { label: "Shots (On)", val: shotsOn, color: "text-dark" },
                    { label: "Yellows", val: yel, color: "text-warning" },
                    { label: "Rating", val: rat, color: "text-info" }
                ];
            }

            let gridHtml = '';
            stats.forEach(s => {
                gridHtml += `
                    <div class="col-4 mb-2">
                        <div class="border rounded bg-light p-2 h-100">
                            <div class="text-muted" style="font-size: 0.65rem; text-transform: uppercase; font-weight: 700; letter-spacing: 0.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${s.label}</div>
                            <div class="fw-bold ${s.color}" style="font-size: 1.1rem;">${s.val}</div>
                        </div>
                    </div>
                `;
            });
            statsContainer.innerHTML = gridHtml;

            if (isNested && p.season_stats.competitions) {
                let breakdownHtml = `<div class="mt-2 text-start w-100 px-1">
                                        <div class="text-muted mb-1 border-bottom pb-1" style="font-size: 0.7rem; font-weight: 700; text-transform: uppercase;">Competition Breakdown</div>`;
                
                for (const [compName, compStats] of Object.entries(p.season_stats.competitions)) {
                    if (compStats.games > 0) { 
                        
                        let compDisplay = "";
                        if (pos === 'G') {
                            compDisplay = `<b>${compStats.games}</b>M &nbsp; <b>${compStats.saves || 0}</b>SV &nbsp; <b>${compStats.conceded || 0}</b>GC`;
                        } else if (pos === 'D') {
                            compDisplay = `<b>${compStats.games}</b>M &nbsp; <b>${compStats.tackles || 0}</b>TK &nbsp; <b>${compStats.interceptions || 0}</b>IN`;
                        } else if (pos === 'M') {
                            compDisplay = `<b>${compStats.games}</b>M &nbsp; <b>${compStats.goals || 0}</b>G &nbsp; <b>${compStats.key_passes || 0}</b>KP`;
                        } else {
                            compDisplay = `<b>${compStats.games}</b>M &nbsp; <b>${compStats.goals || 0}</b>G &nbsp; <b>${compStats.assists || 0}</b>A`;
                        }

                        breakdownHtml += `
                        <div class="d-flex justify-content-between align-items-center py-1" style="font-size: 0.75rem; border-bottom: 1px dashed #f1f3f5;">
                            <span class="fw-bold text-dark text-truncate pe-2" style="max-width: 55%;">${compName}</span>
                            <span class="text-muted text-end" style="font-size: 0.70rem;">
                                ${compDisplay}
                            </span>
                        </div>`;
                    }
                }
                breakdownHtml += `</div>`;
                statsContainer.innerHTML += breakdownHtml;
            }
            
        } else {
            noStatsEl.classList.remove('d-none');
        }
    } else {
        noStatsEl.classList.remove('d-none');
    }

    const modal = new bootstrap.Modal(document.getElementById('playerProfileModal'));
    modal.show();
};


// ==========================================
// NEW: SPLIT HTML BUILDERS (Time & Event decoupled)
// ==========================================
function getTimeBadgeHtml(data) {
    const status = data.fixture.status.short;
    const dateObj = new Date(data.fixture.date);
    const matchTime = dateObj.toLocaleDateString([], {weekday: 'short'}) + ' ' + dateObj.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

    const isFinished = ['FT', 'AET', 'PEN'].includes(status);
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);

    let badge = '';

    if (isDelayed) {
        badge = `<span class="badge bg-danger text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${status}</span>`;
    } else if (!isPreGame && !isFinished && !data.isFallback) {
        let displayMin = data.fixture.status.elapsed;
        let extraMin = data.fixture.status.extra;

        if (status === 'ET') {
            const maxEventTime = data.events ? Math.max(0, ...data.events.map(e => parseInt(e.time) || 0)) : 0;
            if (displayMin < 105 && maxEventTime >= 105) { displayMin += 15; } 
            else if (displayMin < 105 && (new Date() - dateObj) > (135 * 60 * 1000)) { displayMin += 15; }
        }
        
        if (status === 'HT') displayMin = 'HT';
        else if (status === 'BT') displayMin = 'ET HT';
        else if (status === 'P') displayMin = 'PEN';
        else {
            if (extraMin) {
                displayMin = `${displayMin}+${extraMin}'`; 
            } else {
                displayMin = `${displayMin}'`; 
            }
        }
        
        badge = `<span class="badge bg-success text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;"><span class="live-dot"></span>${displayMin}</span>`;
    } else if (isFinished) {
        badge = `<span class="badge bg-dark text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">FT</span>`;
    } else {
        badge = `<span class="badge bg-white text-dark shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${matchTime}</span>`;
    }
    return badge;
}

function getLatestEventHtml(data, isRibbon = false) {
    const status = data.fixture.status.short;
    const isFinished = ['FT', 'AET', 'PEN'].includes(status);
    
    if (data.events && data.events.length > 0) {
        const lastEv = data.events[data.events.length - 1]; 
        const currentMinute = data.fixture.status.elapsed || 0;
        const eventMinute = parseInt(lastEv.time) || 0;
        
        // Ribbon always shows the last event. Full View only shows if within 5 mins.
        if (!isRibbon && isFinished) return '';
        if (!isRibbon && (currentMinute - eventMinute > 5)) return '';

        const isHomeTeam = lastEv.team_id === data.teams.home.id;
        const teamName = isHomeTeam ? data.teams.home.name : data.teams.away.name;
        const teamLogo = isHomeTeam ? data.teams.home.logo : data.teams.away.logo; 
        
        if (lastEv.type === 'subst') {
            let pIn = (lastEv.player && lastEv.player !== "null") ? shortenPlayerName(lastEv.player) : 'Unknown';
            let pOut = (lastEv.player_out && lastEv.player_out !== "null") ? shortenPlayerName(lastEv.player_out) : 'Unknown';
            
            if (isRibbon) {
                // NEW: Wrap text up to 2 lines before truncating
                return `<div class="text-dark fw-bold text-start w-100 ps-2" style="font-size: 0.65rem; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; white-space: normal;">
                            ${lastEv.time}' <img src="${teamLogo}" alt="${teamName}" style="width: 12px; height: 12px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> <span class="text-success">${pIn}</span> 🔄 <span class="text-muted">${pOut}</span>
                        </div>`;
            } else {
                return `<div class="ms-2 text-dark fw-bold" style="font-size: 0.65rem; display: inline-flex; flex-direction: column; justify-content: center; vertical-align: middle; line-height: 1.15;">
                            <span class="text-truncate" style="max-width: 160px;">🔄 <img src="${teamLogo}" alt="${teamName}" style="width: 12px; height: 12px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> ${lastEv.time}' ${pIn} IN</span>
                            <span class="text-truncate text-muted" style="max-width: 160px; padding-left: 18px;">${pOut} OUT</span>
                        </div>`;
            }
        } else {
            let icon = '🟥';
            if (lastEv.type === 'Goal') { icon = '⚽'; } 
            else if (lastEv.detail && lastEv.detail.includes('Yellow')) {
                icon = lastEv.detail.includes('Red') || lastEv.detail.includes('Second') ? '🟨🟥' : '🟨';
            }
            const playerName = (lastEv.player && lastEv.player !== "null") ? shortenPlayerName(lastEv.player) : teamName;
            const textColor = lastEv.type === 'Goal' ? 'text-success' : (icon === '🟨' ? 'text-warning' : 'text-danger');
            
            if (isRibbon) {
                // NEW: Wrap text up to 2 lines before truncating
                return `<div class="${textColor} fw-bold text-start w-100 ps-2" style="font-size: 0.65rem; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; white-space: normal;">
                            ${icon} <img src="${teamLogo}" alt="${teamName}" style="width: 12px; height: 12px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> ${playerName} <span class="text-muted" style="font-size: 0.6rem;">(${lastEv.time}')</span>
                        </div>`;
            } else {
                return `<span class="ms-2 ${textColor} fw-bold text-truncate" style="font-size: 0.70rem; max-width: 150px; display: inline-block; vertical-align: middle;">
                            ${icon} <img src="${teamLogo}" alt="${teamName}" style="width: 14px; height: 14px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> ${playerName} (${lastEv.time}')
                        </span>`;
            }
        }
    }
    return isRibbon ? `<span class="text-muted" style="font-size: 0.6rem; font-style: italic;">No Events</span>` : '';
}

// ==========================================
// NEW: RIBBON HTML BUILDER
// ==========================================
function getRibbonHtml(data) {
    const home = data.teams.home;
    const away = data.teams.away;
    const status = data.fixture.status.short;
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);
    
    const homeScore = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals.home ?? 0) : '-';
    const awayScore = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals.away ?? 0) : '-';

    return `
    <div class="row g-0 align-items-center py-2" style="transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='#f8f9fa'" onmouseout="this.style.backgroundColor='transparent'">
        <div class="col-3 text-center d-flex justify-content-center align-items-center border-end pe-1">
            ${getTimeBadgeHtml(data)}
        </div>
        <div class="col-5 px-2">
            <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 80%;"><img src="${home.logo}" width="14" height="14" class="me-1" style="object-fit:contain;">${home.name}</span>
                <span class="fw-bold text-dark" style="font-size: 0.85rem;">${homeScore}</span>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: 80%;"><img src="${away.logo}" width="14" height="14" class="me-1" style="object-fit:contain;">${away.name}</span>
                <span class="fw-bold text-dark" style="font-size: 0.85rem;">${awayScore}</span>
            </div>
        </div>
        <div class="col-4 text-center border-start d-flex justify-content-center align-items-center">
            ${getLatestEventHtml(data, true)}
        </div>
    </div>`;
}

// ... (getScoreHtml, getEventsHtml, getOddsHtml, getInjuriesHtml ALL REMAIN EXACTLY THE SAME) ...

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
    
    const formatSingleEvent = (e, teamName) => {
        if (e.type === 'subst') {
            let pIn = (e.player && e.player !== "null") ? shortenPlayerName(e.player) : 'Unknown';
            let pOut = (e.player_out && e.player_out !== "null") ? shortenPlayerName(e.player_out) : 'Unknown';
            return `
                <div style="line-height: 1.2; margin-bottom: 2px;">
                    🔄 ${e.time}' <span class="text-dark fw-bold">${pIn}</span> IN<br>
                    <span class="text-muted">🔄 ${e.time}' ${pOut} OUT</span>
                </div>
            `;
        }

        let icon = '🟥';
        if (e.type === 'Goal') { icon = '⚽'; } 
        else if (e.detail && e.detail.includes('Yellow')) {
            icon = e.detail.includes('Red') || e.detail.includes('Second') ? '🟨🟥' : '🟨';
        }
        let playerName = (e.player && e.player !== "null") ? shortenPlayerName(e.player) : teamName;
        return `${icon} <span class="text-dark fw-bold">${playerName}</span> ${e.time}'`;
    };

    const renderEventSide = (evs, teamName, isHome) => {
        if (evs.length === 0) return '';
        const reversedEvs = [...evs].reverse();

        if (reversedEvs.length === 1) {
            return `<div class="text-truncate">${formatSingleEvent(reversedEvs[0], teamName)}</div>`;
        }

        const firstEvent = formatSingleEvent(reversedEvs[0], teamName);
        const allEvents = reversedEvs.map(e => `<div class="text-truncate" style="margin-bottom: 2px;">${formatSingleEvent(e, teamName)}</div>`).join('');

        return `
            <div class="event-collapsed d-flex align-items-center ${isHome ? 'justify-content-start' : 'justify-content-end'}">
                <div class="text-truncate">${firstEvent}</div>
                <div class="text-secondary ms-1" style="font-size: 0.6rem; flex-shrink: 0;">▼</div>
            </div>
            <div class="event-expanded d-none">
                ${allEvents}
                <div class="text-secondary" style="font-size: 0.6rem; line-height: 1;">▲</div>
            </div>
        `;
    };

    return `
    <div class="w-100 px-2 pt-1 mt-1 border-top d-flex justify-content-between text-muted" 
         style="font-size: 0.65rem; cursor: pointer; transition: background-color 0.2s;" 
         onclick="const isExp = this.classList.toggle('is-expanded'); this.querySelectorAll('.event-collapsed').forEach(el => el.classList.toggle('d-none', isExp)); this.querySelectorAll('.event-expanded').forEach(el => el.classList.toggle('d-none', !isExp));"
         onmouseover="this.style.backgroundColor='#f8f9fa'" 
         onmouseout="this.style.backgroundColor='transparent'"
         title="Click to expand/collapse goals and cards">
        <div class="text-start pe-1" style="flex: 1; min-width: 0;">${renderEventSide(homeEvents, data.teams.home.name, true)}</div>
        <div class="text-end ps-1" style="flex: 1; min-width: 0;">${renderEventSide(awayEvents, data.teams.away.name, false)}</div>
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
    
    const cleanHomeInj = data.injuries.home.map(n => shortenPlayerName(n));
    const cleanAwayInj = data.injuries.away.map(n => shortenPlayerName(n));
    
    const hInj = cleanHomeInj.join(', ') || 'None';
    const aInj = cleanAwayInj.join(', ') || 'None';
    
    return `
    <div class="border-bottom px-2 py-1 expandable-section position-relative d-flex justify-content-center align-items-center" 
         style="font-size: 0.65rem; background-color: #fff5f5; color: #dc3545; cursor: pointer; transition: background-color 0.2s;" 
         onclick="toggleExpand(this)" 
         onmouseover="this.style.backgroundColor='#ffebeb'" 
         onmouseout="this.style.backgroundColor='#fff5f5'" 
         title="Click to expand/collapse injuries">
        <div class="injury-text text-truncate truncate-target user-select-none" style="max-width: 92%; min-width: 0;">
            <strong>🤕 OUT:</strong> <span class="text-dark"><b>H:</b> ${hInj} | <b>A:</b> ${aInj}</span>
        </div>
        <div class="overflow-indicator d-none position-absolute text-danger" style="right: 12px; font-size: 0.6rem; pointer-events: none;">▼</div>
    </div>`;
}

function getUrlParams() {
    const params = new URLSearchParams(window.location.search);
    return { league: params.get('league') || 'top', date: params.get('date') || DEFAULT_DATE };
}

// ... (renderLeagueMenu and fetchMatchesData REMAIN EXACTLY THE SAME) ...

function renderLeagueMenu(activeLeague, currentDate) {
    const desktopMenu = document.getElementById('league-menu-desktop');
    const mobileMenu = document.getElementById('league-menu-mobile');
    
    if (!desktopMenu || !mobileMenu) return;

    desktopMenu.innerHTML = '';
    mobileMenu.innerHTML = '';
    
    LEAGUE_GROUPS["priority"].forEach(league => {
        const a = document.createElement('a');
        a.href = `?league=${league.key}&date=${currentDate}`;
        a.className = `league-pill ${league.key === activeLeague ? 'active' : ''}`;
        a.textContent = league.name;
        desktopMenu.appendChild(a);
    });

    ['Europe', 'Americas', 'World'].forEach(region => {
        const regionLeagues = LEAGUE_GROUPS[region];
        if (!regionLeagues || regionLeagues.length === 0) return; 
        const isActiveRegion = regionLeagues.some(l => l.key === activeLeague);
        const dropdownDiv = document.createElement('div');
        dropdownDiv.className = 'dropdown d-inline-block flex-shrink-0';
        dropdownDiv.innerHTML = `
            <button class="dropdown-toggle league-pill ${isActiveRegion ? 'active' : ''}" type="button" data-bs-toggle="dropdown" aria-expanded="false" style="border: none; background: transparent; color: ${isActiveRegion ? '#20c997' : '#adb5bd'};">
                ${region}
            </button>
            <ul class="dropdown-menu dropdown-menu-dark shadow" style="background-color: #343a40; border-color: #495057;">
                ${regionLeagues.map(league => `
                    <li><a class="dropdown-item ${league.key === activeLeague ? 'text-success fw-bold' : 'text-light'}" href="?league=${league.key}&date=${currentDate}">${league.name}</a></li>
                `).join('')}
            </ul>`;
        desktopMenu.appendChild(dropdownDiv);
    });

    const topLinks = LEAGUE_GROUPS["priority"];

    const mobileNames = {
        "Top Matches": "TOP",
        "Premier League": "EPL",
        "La Liga": "La Liga",
        "Serie A": "Serie A"
    };

    topLinks.forEach(league => {
        const a = document.createElement('a');
        a.href = `?league=${league.key}&date=${currentDate}`;
        a.className = `league-pill ${league.key === activeLeague ? 'active' : ''}`;
        a.textContent = mobileNames[league.name] || league.name;
        mobileMenu.appendChild(a);
    });

    const isMoreActive = !topLinks.some(l => l.key === activeLeague);

    let dropdownHtml = `
        <div class="dropdown d-inline-block">
            <button class="league-pill dropdown-toggle ${isMoreActive ? 'active' : ''}" type="button" data-bs-toggle="dropdown" aria-expanded="false" style="border: none; background: transparent; color: ${isMoreActive ? '#20c997' : '#adb5bd'}; padding-right: 0;">
                More
            </button>
            <ul class="dropdown-menu dropdown-menu-dark dropdown-menu-end shadow" style="background-color: #343a40; border-color: #495057; max-height: 65vh; overflow-y: auto;">
    `;

    ['Europe', 'Americas', 'World'].forEach((region, idx) => {
        if (idx !== 0) {
            dropdownHtml += `<li><hr class="dropdown-divider border-secondary"></li>`;
        }
        dropdownHtml += `<li><h6 class="dropdown-header pb-0" style="color: #adb5bd; font-weight: 700; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.5px;">${region}</h6></li>`;
        LEAGUE_GROUPS[region].forEach(league => {
            dropdownHtml += `<li><a class="dropdown-item ${league.key === activeLeague ? 'text-success fw-bold' : 'text-light'}" href="?league=${league.key}&date=${currentDate}">${league.name}</a></li>`;
        });
    });

    dropdownHtml += `</ul></div>`;
    mobileMenu.insertAdjacentHTML('beforeend', dropdownHtml);
}

async function fetchMatchesData(params) {
    try {
        const localRes = await fetch(`data/games_${params.date}.json?v=` + new Date().getTime(), {
            cache: 'no-store',
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        });
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

function triggerCardHighlight(targetCard, type) {
    if (!targetCard) return;
    
    const innerHeader = targetCard.querySelector('.p-2.pb-1');
    let borderColor, boxShadowColor, headerBgColor;

    if (type === 'goal' || type === 'hash') { 
        borderColor = '#20c997';
        boxShadowColor = 'rgba(32, 201, 151, 0.8)';
        headerBgColor = '#d1e7dd';
    } else if (type === 'red_card') { 
        borderColor = '#dc3545';
        boxShadowColor = 'rgba(220, 53, 69, 0.8)';
        headerBgColor = '#f8d7da';
    } else if (type === 'yellow_card') { 
        borderColor = '#ffc107';
        boxShadowColor = 'rgba(255, 193, 7, 0.8)';
        headerBgColor = '#fff3cd';
    } else if (type === 'subst') { 
        borderColor = '#212529'; 
        boxShadowColor = 'rgba(33, 37, 41, 0.6)'; 
        headerBgColor = '#e9ecef'; 
    }

    targetCard.style.transition = 'all 0.4s ease-out';
    targetCard.style.transform = 'scale(1.02)';
    targetCard.style.setProperty('border', `3px solid ${borderColor}`, 'important');
    targetCard.style.setProperty('box-shadow', `0 0 25px ${boxShadowColor}`, 'important');
    targetCard.style.position = 'relative'; 
    targetCard.style.zIndex = '10';
    
    if (innerHeader) {
        innerHeader.style.transition = 'background-color 0.4s ease-out';
        innerHeader.style.backgroundColor = headerBgColor; 
    }
    
    setTimeout(() => {
        targetCard.style.transform = 'scale(1)';
        targetCard.style.removeProperty('border'); 
        targetCard.style.setProperty('box-shadow', '0 2px 4px rgba(0,0,0,0.05)', 'important');
        targetCard.style.zIndex = '1';
        
        if (innerHeader) {
            innerHeader.style.backgroundColor = '#fcfcfc'; 
        }
    }, 4000); 
}

// ==========================================
// NEW: DUAL-VIEW TOGGLE LOGIC
// ==========================================
window.toggleSingleCard = function(fixId) {
    const ribbon = document.getElementById(`ribbon-${fixId}`);
    const full = document.getElementById(`full-${fixId}`);
    if (ribbon && full) {
        ribbon.classList.toggle('d-none');
        full.classList.toggle('d-none');
    }
};

// ==========================================
// UPDATED SILENT SYNC ENGINE (Syncs Both Views)
// ==========================================
async function updateLiveGames() {
    const params = getUrlParams();
    const newData = await fetchMatchesData(params);
    if (!newData) return; 

    if (newData.length !== ALL_GAMES_DATA.length) {
        ALL_GAMES_DATA = newData;
        renderGames();
        return;
    }

    const oldData = [...ALL_GAMES_DATA]; 
    ALL_GAMES_DATA = newData;
    
    newData.forEach(match => {
        const fixId = match.fixture.id;
        const oldMatch = oldData.find(m => m.fixture.id === fixId);
        
        // Target specific containers inside the Full View
        const timeEl = document.getElementById(`time-${fixId}`);
        const scoreEl = document.getElementById(`score-${fixId}`);
        const eventsEl = document.getElementById(`events-${fixId}`);
        const oddsEl = document.getElementById(`odds-${fixId}`);
        const injuriesEl = document.getElementById(`injuries-${fixId}`);
        
        if (timeEl && scoreEl && eventsEl && oddsEl && injuriesEl) {
            // FULL VIEW UPDATES
            const newTimeHtml = (getTimeBadgeHtml(match) + ' ' + getLatestEventHtml(match)).trim();
            const newScoreHtml = getScoreHtml(match).trim();
            const newEventsHtml = getEventsHtml(match).trim();
            const newOddsHtml = getOddsHtml(match).trim();
            const newInjuriesHtml = getInjuriesHtml(match).trim();
            
            if (timeEl.innerHTML.trim() !== newTimeHtml) timeEl.innerHTML = newTimeHtml;
            
            if (scoreEl.innerHTML.trim() !== newScoreHtml) {
                scoreEl.innerHTML = newScoreHtml;
                scoreEl.classList.remove('flash-green');
                void scoreEl.offsetWidth; 
                scoreEl.classList.add('flash-green');
            }
            
            const eventsWasExpanded = eventsEl.querySelector('.is-expanded') !== null;
            if (eventsEl.innerHTML.trim() !== newEventsHtml) {
                eventsEl.innerHTML = newEventsHtml;
                if (eventsWasExpanded) {
                    const toggleSection = eventsEl.querySelector('.border-top');
                    if (toggleSection) {
                        toggleSection.classList.add('is-expanded');
                        toggleSection.querySelectorAll('.event-collapsed').forEach(el => el.classList.add('d-none'));
                        toggleSection.querySelectorAll('.event-expanded').forEach(el => el.classList.remove('d-none'));
                    }
                }
            }
            
            if (oddsEl.innerHTML.trim() !== newOddsHtml) oddsEl.innerHTML = newOddsHtml;

            const injuriesWasExpanded = injuriesEl.querySelector('.is-expanded') !== null;
            if (injuriesEl.innerHTML.trim() !== newInjuriesHtml) {
                injuriesEl.innerHTML = newInjuriesHtml;
                if (injuriesWasExpanded) {
                    const toggleSection = injuriesEl.querySelector('.expandable-section');
                    if (toggleSection) toggleExpand(toggleSection);
                }
            }
        }
        
        // RIBBON VIEW UPDATE (Completely redraws if data changes)
        const ribbonEl = document.getElementById(`ribbon-${fixId}`);
        if (ribbonEl) {
            const newRibbonHtml = getRibbonHtml(match).trim();
            if (ribbonEl.innerHTML.trim() !== newRibbonHtml) ribbonEl.innerHTML = newRibbonHtml;
        }

        const bannerEl = document.getElementById(`lineup-banner-text-${fixId}`);
        if (bannerEl) {
            const liveStatus = match.fixture.status.short;
            let newBannerText = "STARTING XI";
            if (['FT', 'AET', 'PEN'].includes(liveStatus)) newBannerText = "FINAL XI";
            else if (!['NS', 'TBD'].includes(liveStatus)) newBannerText = "LIVE XI";
            
            const newBannerHtml = `${newBannerText} <span style="font-size: 0.6rem;">▼</span>`;
            if (bannerEl.innerHTML.trim() !== newBannerHtml) bannerEl.innerHTML = newBannerHtml;
        }
        
        if (oldMatch) {
            const oldEvLen = oldMatch.events ? oldMatch.events.length : 0;
            const newEvLen = match.events ? match.events.length : 0;
            
            if (newEvLen > oldEvLen) {
                const latestEvent = match.events[newEvLen - 1];
                if (latestEvent.type === 'subst') {
                    const lineupContainer = document.getElementById(`lineup-collapse-${fixId}`);
                    if (lineupContainer) {
                        const rowEl = lineupContainer.querySelector('.row.g-0.bg-white');
                        if (rowEl) {
                            const getLineupHtml = (lineupData, gameData) => {
                                if (gameData.isFallback) return `<div class="p-4 text-center text-muted small fst-italic">Formations & lineups available on match day</div>`;
                                if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) return `<div class="p-4 text-center text-muted small fw-bold">Lineup pending...</div>`;
                                
                                const statusShort = gameData.fixture.status.short;
                                const isPreGame = ['NS', 'TBD'].includes(statusShort);
                                const formationHeader = `<div class="w-100 text-center py-1 fw-bold text-white" style="font-size: 0.65rem; background-color: #198754; border-bottom: 1px solid #146c43;">✅ ${lineupData.formation}</div>`;
                                
                                let currentXI = [...lineupData.startXI];
                                if (!isPreGame && gameData.events && gameData.events.length > 0) {
                                    const teamId = lineupData.team.id;
                                    const subs = gameData.events.filter(e => e.type === 'subst' && e.team_id === teamId);
                                    subs.forEach(subEvent => {
                                        const outIndex = currentXI.findIndex(p => p.player.id === subEvent.player_out_id || p.player.name === subEvent.player_out);
                                        if (outIndex !== -1) {
                                            const subPlayer = lineupData.substitutes.find(p => p.player.id === subEvent.player_id || p.player.name === subEvent.player);
                                            if (subPlayer) {
                                                currentXI[outIndex] = { ...subPlayer, player: { ...subPlayer.player, pos: currentXI[outIndex].player.pos, isSubbedIn: true, subMinute: subEvent.time } };
                                            }
                                        }
                                    });
                                }
                                
                                const listItems = currentXI.map(p => {
                                    const safePos = p.player.pos || '-';
                                    const originalName = p.player.name || 'Unknown';
                                    const displaySafeName = shortenPlayerName(originalName);
                                    const safeNum = p.player.number || '';
                                    const photoUrl = p.player.photo || '';
                                    const encodedPlayer = encodeURIComponent(JSON.stringify(p.player));
                                    let posColor = safePos === 'G' ? "#dc3545" : safePos === 'D' ? "#0d6efd" : safePos === 'M' ? "#20c997" : "#ffc107";
                                    
                                    const photoHtml = photoUrl && photoUrl.includes("http") 
                                        ? `<img src="${photoUrl}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover; border: 1px solid #dee2e6;">`
                                        : `<div style="width: 24px; height: 24px; border-radius: 50%; background-color: #f1f3f5; color: #adb5bd; display: flex; align-items: center; justify-content: center; font-size: 0.6rem; font-weight: bold; border: 1px solid #dee2e6;">${originalName.charAt(0).toUpperCase()}</div>`;

                                    const subIndicator = p.player.isSubbedIn ? `<span class="ms-1 text-secondary" style="font-size: 0.65rem;">🔄 ${p.player.subMinute}'</span>` : '';

                                    return `
                                        <li class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="cursor: pointer; transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='#f8f9fa'" onmouseout="this.style.backgroundColor='transparent'" data-player="${encodedPlayer}" onclick="openPlayerModal(this)">
                                            <span class="text-muted fw-bold d-inline-block text-start me-1" style="font-size: 0.7rem; width: 15px; color: ${posColor} !important;">${safePos}</span>
                                            <div class="me-2">${photoHtml}</div>
                                            <span class="batter-name fw-bold text-dark text-truncate" style="font-size: 0.85rem;" title="${originalName}">${displaySafeName}${subIndicator}</span>
                                            <span class="ms-auto text-muted" style="font-size: 0.65rem;">#${safeNum}</span>
                                        </li>`;
                                }).join('');
                                return `${formationHeader}<ul class="batting-order w-100 m-0 p-0" style="list-style-type: none;">${listItems}</ul>`;
                            };

                            rowEl.innerHTML = `
                                <div class="col-6 border-end">${getLineupHtml(match.homeLineup, match)}</div>
                                <div class="col-6">${getLineupHtml(match.awayLineup, match)}</div>
                            `;
                        }
                    }
                }
            }
        }
        if (oldMatch) {
            const oldLen = oldMatch.events ? oldMatch.events.length : 0;
            const newLen = match.events ? match.events.length : 0;
            
            if (newLen > oldLen) {
                const latestEvent = match.events[newLen - 1]; 
                const cardEl = document.getElementById(`card-${fixId}`);
                
                if (cardEl && latestEvent) {
                    if (latestEvent.type === 'Goal') {
                        triggerCardHighlight(cardEl, 'goal');
                    } else if (latestEvent.type === 'Card' && latestEvent.detail) {
                        if (latestEvent.detail.includes('Second') || latestEvent.detail.includes('Yellow / Red')) {
                            triggerCardHighlight(cardEl, 'yellow_card');
                            setTimeout(() => { triggerCardHighlight(cardEl, 'red_card'); }, 4500); 
                        } else if (latestEvent.detail.includes('Red')) {
                            triggerCardHighlight(cardEl, 'red_card');
                        } else if (latestEvent.detail.includes('Yellow')) {
                            triggerCardHighlight(cardEl, 'yellow_card');
                        }
                    } else if (latestEvent.type === 'subst') {
                        triggerCardHighlight(cardEl, 'subst');
                    }
                }
            }
        }
    });

    requestAnimationFrame(() => requestAnimationFrame(checkOverflows));
}

function handleHashNavigation() {
    if (window.location.hash) {
        setTimeout(() => {
            const targetCard = document.querySelector(window.location.hash);
            if (targetCard) {
                targetCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                triggerCardHighlight(targetCard, 'hash'); 
            }
        }, 600); 
    }
}

async function init() {
    const params = getUrlParams();
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
    handleHashNavigation(); 
    setInterval(updateLiveGames, 30000); 
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
    
    requestAnimationFrame(() => requestAnimationFrame(checkOverflows));
}

// ==========================================
// NEW: DUAL-VIEW CARD BUILDER
// ==========================================
function createGameCard(data) {
    const gameCard = document.createElement('div');
    gameCard.className = 'col-md-6 col-lg-6 col-xl-4 mb-2';

    const home = data.teams.home;
    const away = data.teams.away;
    const fixId = data.fixture.id;

    const homeRank = home.rank ? `<span class="text-muted" style="font-size: 0.70rem;">[${home.rank}]</span> ` : '';
    const awayRank = away.rank ? `<span class="text-muted" style="font-size: 0.70rem;">[${away.rank}]</span> ` : '';

    const homeRecord = home.record ? `<div class="text-muted fw-normal" style="font-size: 0.65rem; margin-top: 2px;">(${home.record})</div>` : '';
    const awayRecord = away.record ? `<div class="text-muted fw-normal" style="font-size: 0.65rem; margin-top: 2px;">(${away.record})</div>` : '';

    const buildLineupList = (lineupData) => {
        if (data.isFallback) return `<div class="p-4 text-center text-muted small fst-italic">Formations & lineups available on match day</div>`;
        if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) return `<div class="p-4 text-center text-muted small fw-bold">Lineup pending...</div>`;
        
        const status = data.fixture.status.short;
        const isPreGame = ['NS', 'TBD'].includes(status);
        
        const formationHeader = `<div class="w-100 text-center py-1 fw-bold text-white" style="font-size: 0.65rem; background-color: #198754; border-bottom: 1px solid #146c43;">✅ ${lineupData.formation}</div>`;
        
        let currentXI = [...lineupData.startXI];
        
        if (!isPreGame && data.events && data.events.length > 0) {
            const teamId = lineupData.team.id;
            const subs = data.events.filter(e => e.type === 'subst' && e.team_id === teamId);
            
            subs.forEach(subEvent => {
                const outIndex = currentXI.findIndex(p => p.player.id === subEvent.player_out_id || p.player.name === subEvent.player_out);
                if (outIndex !== -1) {
                    const subPlayer = lineupData.substitutes.find(p => p.player.id === subEvent.player_id || p.player.name === subEvent.player);
                    if (subPlayer) {
                        currentXI[outIndex] = {
                            ...subPlayer,
                            player: {
                                ...subPlayer.player,
                                pos: currentXI[outIndex].player.pos, 
                                isSubbedIn: true,
                                subMinute: subEvent.time
                            }
                        };
                    }
                }
            });
        }
        
        const listItems = currentXI.map(p => {
            const safePos = p.player.pos || '-';
            const originalName = p.player.name || 'Unknown';
            const displaySafeName = shortenPlayerName(originalName);
            const safeNum = p.player.number || '';
            const photoUrl = p.player.photo || '';
            
            const encodedPlayer = encodeURIComponent(JSON.stringify(p.player));
            let posColor = safePos === 'G' ? "#dc3545" : safePos === 'D' ? "#0d6efd" : safePos === 'M' ? "#20c997" : "#ffc107";
            
            const photoHtml = photoUrl && photoUrl.includes("http") 
                ? `<img src="${photoUrl}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover; border: 1px solid #dee2e6;">`
                : `<div style="width: 24px; height: 24px; border-radius: 50%; background-color: #f1f3f5; color: #adb5bd; display: flex; align-items: center; justify-content: center; font-size: 0.6rem; font-weight: bold; border: 1px solid #dee2e6;">${originalName.charAt(0).toUpperCase()}</div>`;

            const subIndicator = p.player.isSubbedIn 
                ? `<span class="ms-1 text-secondary" style="font-size: 0.65rem;">🔄 ${p.player.subMinute}'</span>` 
                : '';

            return `
                <li class="d-flex align-items-center w-100 px-2 py-1 border-bottom" style="cursor: pointer; transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='#f8f9fa'" onmouseout="this.style.backgroundColor='transparent'" data-player="${encodedPlayer}" onclick="openPlayerModal(this)">
                    <span class="text-muted fw-bold d-inline-block text-start me-1" style="font-size: 0.7rem; width: 15px; color: ${posColor} !important;">${safePos}</span>
                    <div class="me-2">${photoHtml}</div>
                    <span class="batter-name fw-bold text-dark text-truncate" style="font-size: 0.85rem;" title="${originalName}">
                        ${displaySafeName}${subIndicator}
                    </span>
                    <span class="ms-auto text-muted" style="font-size: 0.65rem;">#${safeNum}</span>
                </li>`;
        }).join('');
        return `${formationHeader}<ul class="batting-order w-100 m-0 p-0" style="list-style-type: none;">${listItems}</ul>`;
    };

    const statusShort = data.fixture.status.short;
    let topBannerText = "STARTING XI";
    if (['FT', 'AET', 'PEN'].includes(statusShort)) topBannerText = "FINAL XI";
    else if (!['NS', 'TBD'].includes(statusShort)) topBannerText = "LIVE XI";
    
    // FULL VIEW HTML (The original card)
    const fullHtml = `
        <div class="p-2 pb-1" style="background-color: #fcfcfc;">
            <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom border-light" style="cursor: pointer;" onclick="toggleSingleCard(${fixId})" title="Click to collapse">
                <div id="time-${fixId}" style="flex: 0 0 auto;" class="pe-2">${getTimeBadgeHtml(data)} ${getLatestEventHtml(data)}</div>
                <div class="text-muted fw-bold text-uppercase text-end ms-auto text-truncate" style="font-size: 0.70rem;">
                    ${data.league.name}
                </div>
            </div>
            <div class="d-flex justify-content-between align-items-center px-1 pt-1 pb-1">
                <div class="text-center" style="width: 38%;"> 
                    <img src="${home.logo}" alt="${home.name}" class="team-logo mb-1">
                    <div class="fw-bold text-dark text-truncate" style="font-size: 0.9rem;" title="${home.name}">${homeRank}${home.name}</div>
                    ${homeRecord}
                </div>
                <div id="score-${fixId}" class="text-center d-flex flex-column align-items-center justify-content-center" style="width: 24%;">
                    ${getScoreHtml(data)}
                </div>
                <div class="text-center" style="width: 38%;"> 
                    <img src="${away.logo}" alt="${away.name}" class="team-logo mb-1">
                    <div class="fw-bold text-dark text-truncate" style="font-size: 0.9rem;" title="${away.name}">${awayRank}${away.name}</div>
                    ${awayRecord}
                </div>
            </div>
            <div id="events-${fixId}" class="w-100">${getEventsHtml(data)}</div>
        </div>
        <div id="odds-${fixId}" class="w-100">${getOddsHtml(data)}</div>
        <div id="injuries-${fixId}" class="w-100">${getInjuriesHtml(data)}</div>
        
        <div class="bg-light border-bottom text-center py-1" data-bs-toggle="collapse" data-bs-target="#lineup-collapse-${fixId}" style="cursor: pointer; transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='#e9ecef'" onmouseout="this.style.backgroundColor='#f8f9fa'" title="Click to expand/collapse lineup">
            <span id="lineup-banner-text-${fixId}" class="fw-bold text-muted" style="font-size: 0.7rem;">${topBannerText} <span style="font-size: 0.6rem;">▼</span></span>
        </div>
        <div class="collapse ${globalLineupsExpanded ? 'show' : ''} lineup-container" id="lineup-collapse-${fixId}">
            <div class="row g-0 bg-white">
                <div class="col-6 border-end">${buildLineupList(data.homeLineup)}</div>
                <div class="col-6">${buildLineupList(data.awayLineup)}</div>
            </div>
        </div>
    `;

    gameCard.innerHTML = `
        <div class="lineup-card shadow-sm position-relative overflow-hidden" style="margin-bottom: 8px; background: #fff;" id="card-${fixId}">
            <div class="ribbon-view ${globalScoreboardMode ? '' : 'd-none'}" id="ribbon-${fixId}" onclick="toggleSingleCard(${fixId})" title="Click to expand card">
                ${getRibbonHtml(data)}
            </div>
            
            <div class="full-view ${globalScoreboardMode ? 'd-none' : ''}" id="full-${fixId}">
                ${fullHtml}
            </div>
        </div>`;
    
    return gameCard;
}

// ==========================================
// EVENT LISTENERS
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    init();
    
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

    // --- NEW: SCOREBOARD TOGGLE LISTENER ---
    const toggleScoreboardBtn = document.getElementById('toggle-all-cards');
    if (toggleScoreboardBtn) {
        toggleScoreboardBtn.innerHTML = globalScoreboardMode ? '🔼 EXPAND ALL CARDS' : '🔽 COMPACT SCOREBOARD';
        
        toggleScoreboardBtn.addEventListener('click', () => {
            globalScoreboardMode = !globalScoreboardMode;
            localStorage.setItem('futbolScoreboardMode', globalScoreboardMode);
            toggleScoreboardBtn.innerHTML = globalScoreboardMode ? '🔼 EXPAND ALL CARDS' : '🔽 COMPACT SCOREBOARD';
            
            const allRibbons = document.querySelectorAll('.ribbon-view');
            const allFulls = document.querySelectorAll('.full-view');
            
            if (globalScoreboardMode) {
                allRibbons.forEach(el => el.classList.remove('d-none'));
                allFulls.forEach(el => el.classList.add('d-none'));
            } else {
                allRibbons.forEach(el => el.classList.add('d-none'));
                allFulls.forEach(el => el.classList.remove('d-none'));
            }
            
            checkOverflows();
        });
    }
});

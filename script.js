// ==========================================
// FIREBASE INITIALIZATION
// ==========================================
const firebaseConfig = {
    databaseURL: "https://nbastartingfive-8b420-default-rtdb.firebaseio.com/"
};
if (!firebase.apps.length) {
    firebase.initializeApp(firebaseConfig);
}
const db = firebase.database();

// ==========================================
// CONFIGURATION & SAFE MERGE LOGIC
// ==========================================
const DEFAULT_DATE = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
let PLAYER_DATABASE = null;

// Lightweight client-side slugifier that mirrors your Python pipeline safely
// Lightweight client-side slugifier that mirrors your Python pipeline safely
function getTeamSlug(teamName) {
    if (!teamName) return "";
    return teamName
        .toLowerCase()
        .normalize("NFD") // Splits accents from characters
        .replace(/[\u0300-\u036f]/g, "") // Removes the accents
        .replace(/\//g, "-") // <-- THE TRUE FIX: Converts forward slashes into hyphens first!
        .replace(/[^a-z0-9\s-]/g, "") // Strips remaining special symbols
        .replace(/\s+/g, "-") // Collapses spaces to hyphens
        .replace(/-+/g, "-") // Normalizes double hyphens
        .replace(/^-+|-+$/g, "") // Trims leading/trailing hyphens cleanly
        .trim();
}

let ALL_GAMES_DATA = []; 

let savedLineupState = localStorage.getItem('futbolLineupsExpanded');
let globalLineupsExpanded = savedLineupState !== null ? savedLineupState === 'true' : true; 

let savedScoreboardState = localStorage.getItem('futbolScoreboardMode');
let globalScoreboardMode = savedScoreboardState !== null ? savedScoreboardState === 'true' : true;

const X_SVG_PATH = "M12.6.75h2.454l-5.36 6.142L16 15.25h-4.937l-3.867-5.07-4.425 5.07H.316l5.733-6.57L0 .75h5.063l3.495 4.633L12.601.75Zm-.86 13.028h1.36L4.323 2.145H2.865l8.875 11.633Z";

// --- THE TRUE FIX: Trust the Live Engine, Shield the FT Glitch ---
function mergeFirebaseIntoJSON(jsonMatch, fbMatch) {
    if (!jsonMatch) return fbMatch;

    // Deep copy the old match so we can safely update it
    let merged = JSON.parse(JSON.stringify(jsonMatch));

    // 1. Sync Core Match Data from Firebase
    if (fbMatch.goals) merged.goals = fbMatch.goals;
    if (fbMatch.fixture && fbMatch.fixture.status) merged.fixture.status = fbMatch.fixture.status;
    if (fbMatch.events && fbMatch.events.length > 0) merged.events = fbMatch.events;
    if (fbMatch.team_stats && fbMatch.team_stats.home) merged.team_stats = fbMatch.team_stats;

    // 2. THE LINEUP FIX: Take the mutated arrays directly from the Python Live Engine.
    // The Live Engine already processed the subs and mapped the live_stats. We just accept it.
    // SHIELD: If Firebase sends an empty array (the FT API glitch), we ignore it and keep the 90th-minute memory.
    if (fbMatch.homeLineup && Array.isArray(fbMatch.homeLineup.startXI) && fbMatch.homeLineup.startXI.length > 0) {
        merged.homeLineup = fbMatch.homeLineup;
    }
    if (fbMatch.awayLineup && Array.isArray(fbMatch.awayLineup.startXI) && fbMatch.awayLineup.startXI.length > 0) {
        merged.awayLineup = fbMatch.awayLineup;
    }

    // 3. Static Data Protection & Aggregates
    merged.first_leg_goals = fbMatch.first_leg_goals || jsonMatch.first_leg_goals;
    if (fbMatch.odds && fbMatch.odds.home !== "TBD") merged.odds = fbMatch.odds;
    if (fbMatch.injuries && (fbMatch.injuries.home?.length > 0 || fbMatch.injuries.away?.length > 0)) {
        merged.injuries = fbMatch.injuries;
    }

    return merged;
}

const LEAGUE_GROUPS = {
    "priority": [
        { key: "top", id: "top", name: "Top Matches" },
        { key: "english-premier-league", id: 39, name: "Premier League" },
        { key: "la-liga", id: 140, name: "La Liga" },
        { key: "serie-a", id: 135, name: "Serie A" }
    ],
    "Europe": [
        { key: "english-premier-league", id: 39, name: "Premier League" },
        { key: "efl-championship", id: 40, name: "Championship" },
        { key: "la-liga", id: 140, name: "La Liga" },
        { key: "serie-a", id: 135, name: "Serie A" },
        { key: "bundesliga", id: 78, name: "Bundesliga" },
        { key: "ligue-1", id: 61, name: "Ligue 1" },
        { key: "eredivisie", id: 88, name: "Eredivisie" },
        { key: "primeira-liga", id: 94, name: "Primeira Liga" },
        { key: "super-lig", id: 203, name: "Süper Lig" },
        { key: "belgian-pro-league", id: 144, name: "Pro League" },
        { key: "scottish-premiership", id: 179, name: "Premiership" },
        { key: "danish-superliga", id: 119, name: "Superliga" }
    ],
    "Americas": [
        { key: "mls", id: 253, name: "MLS" },
        { key: "liga-mx", id: 262, name: "Liga MX" },
        { key: "brasileirao-serie-a", id: 71, name: "Brasileirão" },
        { key: "argentine-liga-profesional", id: 128, name: "Liga Profesional" },
        { key: "colombian-primera-a", id: 239, name: "Primera A" }
    ],
    "World": [
        { key: "saudi-pro-league", id: 307, name: "Saudi Pro League" },
        { key: "j1-league", id: 98, name: "J1 League" },
        { key: "a-league", id: 188, name: "A-League" },
        { key: "k-league-1", id: 292, name: "K League 1" }
    ],
    "Cups": [
        { key: "uefa-champions-league", id: 2, name: "Champions League" },
        { key: "uefa-europa-league", id: 3, name: "Europa League" },
        { key: "uefa-conference-league", id: 848, name: "Conference League" },
        { key: "copa-libertadores", id: 13, name: "Copa Libertadores" },
        { key: "copa-sudamericana", id: 11, name: "Copa Sudamericana" },
        { key: "concacaf-champions-cup", id: 16, name: "Champions Cup" },
        { key: "leagues-cup", id: 528, name: "Leagues Cup" },
        { key: "fa-cup", id: 45, name: "FA Cup" },
        { key: "efl-cup", id: 48, name: "EFL Cup" },
        { key: "copa-del-rey", id: 143, name: "Copa del Rey" },
        { key: "coppa-italia", id: 137, name: "Coppa Italia" },
        { key: "dfb-pokal", id: 81, name: "DFB-Pokal" }
    ],
    "International": [
        { key: "fifa-world-cup", id: 1, name: "World Cup" },
        { key: "international-friendlies", id: 10, name: "Friendlies" },
        { key: "uefa-euro", id: 4, name: "Euro Championship" },
        { key: "copa-america", id: 9, name: "Copa America" },
        { key: "uefa-nations-league", id: 5, name: "UEFA Nations League" },
        { key: "concacaf-nations-league", id: 531, name: "CONCACAF Nations League" }
    ],
    "Women": [
        { key: "womens-super-league", id: 44, name: "Women's Super League" },
        { key: "nwsl", id: 254, name: "NWSL" }
    ]
};

const SUPPORTED_LEAGUES = {};
Object.values(LEAGUE_GROUPS).flat().forEach(l => SUPPORTED_LEAGUES[l.key] = l);

const LEAGUE_ABBREV = {
    39: "EPL", 40: "CHAMP", 140: "LIGA", 135: "SER A", 78: "BUND", 61: "L1", 88: "ERED", 94: "PRIM",
    2: "UCL", 3: "UEL", 848: "UECL", 13: "LIB", 11: "SUD", 16: "CCC", 528: "LCUP", 1: "WC", 4: "EURO", 9: "COPA", 5: "UNL", 531: "CNL", 10: "INTL",
    253: "MLS", 262: "LMX", 71: "BSA", 128: "LPF", 239: "FPC",
    45: "FA", 48: "EFL", 143: "CDR", 137: "COPPA", 81: "DFB",
    307: "SPL", 98: "J1", 203: "TSL", 144: "JPL", 179: "SPFL", 119: "SUP", 188: "ALM", 292: "K1",
    44: "WSL", 254: "NWSL"
};

const LEAGUE_MAP_ESPN = {
    39: "eng.1", 40: "eng.2", 140: "esp.1", 61: "fra.1", 135: "ita.1", 78: "ger.1",
    2: "uefa.champions", 3: "uefa.europa", 848: "uefa.europa.conf",
    262: "mex.1", 253: "usa.1", 71: "bra.1", 128: "arg.1", 528: "conmebol.leagues.cup", 13: "conmebol.libertadores", 16: "concacaf.champions",
    1: "fifa.world", 4: "uefa.euro", 9: "conmebol.america",
    45: "eng.fa", 48: "eng.league_cup",
    307: "ksa.1", 94: "por.1", 88: "ned.1", 98: "jpn.1",
    203: "tur.1", 144: "bel.1", 179: "sco.1", 119: "den.1", 239: "col.1", 188: "aus.1", 292: "kor.1",
    11: "conmebol.sudamericana", 143: "esp.copa_del_rey", 137: "ita.coppa_italia", 81: "ger.dfb_pokal", 
    5: "uefa.nations", 531: "concacaf.nations", 44: "eng.w.1", 254: "usa.nwsl", 10: "fifa.friendly"
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
    if (indicator) indicator.innerHTML = isExpanded ? '▲' : '▼';
    if (!isExpanded) checkOverflows(); 
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
            if (t.scrollWidth > t.clientWidth + 1) hasOverflow = true;
        });

        if (hasOverflow) {
            indicator.classList.remove('d-none');
            targets.forEach(t => t.style.textOverflow = 'clip');
        } else {
            indicator.classList.add('d-none');
            targets.forEach(t => t.style.textOverflow = '');
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

function getContrastColor(hexColor) {
    if (!hexColor) return '#ffffff';
    hexColor = hexColor.replace('#', '');
    const r = parseInt(hexColor.substr(0, 2), 16);
    const g = parseInt(hexColor.substr(2, 2), 16);
    const b = parseInt(hexColor.substr(4, 2), 16);
    const yiq = ((r * 299) + (g * 587) + (b * 114)) / 1000;
    return (yiq >= 128) ? '#000000' : '#ffffff';
}

function colorDistance(hex1, hex2) {
    if (!hex1 || !hex2) return 100;
    const getRgb = (hex) => {
        let h = hex.replace('#', '');
        if (h.length === 3) h = h.split('').map(x => x + x).join('');
        return { r: parseInt(h.substr(0, 2), 16), g: parseInt(h.substr(2, 2), 16), b: parseInt(h.substr(4, 2), 16) };
    };
    const c1 = getRgb(hex1), c2 = getRgb(hex2);
    return Math.sqrt(Math.pow(c1.r - c2.r, 2) + Math.pow(c1.g - c2.g, 2) + Math.pow(c1.b - c2.b, 2));
}

function getLeagueKey(leagueId) {
    for (const [key, leagueObj] of Object.entries(SUPPORTED_LEAGUES)) {
        if (leagueObj.id === leagueId) return key;
    }
    return 'top'; 
}


function getTimeBadgeHtml(data) {
    const status = data.fixture.status.short;
    const dateObj = new Date(data.fixture.date);
    
    const timeString = dateObj.toLocaleTimeString([], {hour: 'numeric', minute:'2-digit'}).replace(' ', '');
    const matchTime = `${dateObj.toLocaleDateString([], {weekday: 'short'})} ${timeString}`;

    const isFinished = ['FT', 'AET', 'PEN'].includes(status);
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);

    const minsSinceKickoff = (new Date() - dateObj) / (1000 * 60);
    const isStuck = isPreGame && (minsSinceKickoff > 5);

    let badge = '';

    if (isDelayed) {
        badge = `<span class="badge bg-danger text-white shadow-sm border px-2 py-1" style="font-size: 0.75rem;">${status}</span>`;
    } else if (status === 'INT') {
        badge = `<span class="badge bg-warning text-dark shadow-sm border px-2 py-1" style="font-size: 0.75rem;" title="Match Interrupted">INT</span>`;
    } else if (isStuck) {
        badge = `<span class="badge bg-warning text-dark shadow-sm border px-2 py-1" style="font-size: 0.70rem;" title="Delayed or awaiting kickoff">DEL</span>`;
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
        badge = `<span class="badge bg-white text-dark shadow-sm border px-1 py-1" style="font-size: 0.65rem; white-space: nowrap;">${matchTime}</span>`;
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
        
        if (!isRibbon && isFinished) return '';
        if (!isRibbon && (currentMinute - eventMinute > 5)) return '';

        const isHomeTeam = lastEv.team_id === data.teams.home.id;
        const teamName = isHomeTeam ? data.teams.home.name : data.teams.away.name;
        const teamLogo = isHomeTeam ? data.teams.home.logo : data.teams.away.logo; 
        
        if (lastEv.type === 'subst') {
            let pOut = (lastEv.player && lastEv.player !== "null") ? shortenPlayerName(lastEv.player) : 'Unknown';
            let pIn = (lastEv.player_out && lastEv.player_out !== "null") ? shortenPlayerName(lastEv.player_out) : 'Unknown';
            
            if (isRibbon) {
                return `<div class="text-dark fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3; overflow: hidden; height: 100%;">
                            <div class="text-truncate" style="margin-bottom: 2px;">🔄 <img src="${teamLogo}" alt="${teamName}" style="width: 12px; height: 12px; object-fit: contain; margin-bottom: 2px; margin-left: 2px; margin-right: 2px;"> ${lastEv.time}'</div>
                            <div class="text-truncate" style="margin-bottom: 1px;">🟢 <span class="text-success">${pIn}</span></div>
                            <div class="text-muted text-truncate">🔴 ${pOut}</div>
                        </div>`;
            } else {
                return `<div class="ms-2 text-dark fw-bold" style="font-size: 0.65rem; display: inline-flex; flex-direction: column; justify-content: center; vertical-align: middle; line-height: 1.15;">
                            <span class="text-truncate" style="max-width: 160px;">🔄 <img src="${teamLogo}" alt="${teamName}" style="width: 12px; height: 12px; object-fit: contain; margin-bottom: 2px; margin-left: 2px; margin-right: 2px;"> ${lastEv.time}' 🟢 ${pIn}</span>
                            <span class="text-truncate text-muted" style="max-width: 160px; padding-left: 18px;">🔴 ${pOut}</span>
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
                let assistHtml = '';
                if (lastEv.type === 'Goal' && lastEv.assist && lastEv.assist !== "null") {
                    assistHtml = `<div class="text-muted text-truncate" style="margin-top: 1px;">👟 ${shortenPlayerName(lastEv.assist)}</div>`;
                }

                return `<div class="${textColor} fw-bold text-start w-100 ps-2 d-flex flex-column justify-content-center" style="font-size: 0.6rem; line-height: 1.3; overflow: hidden; height: 100%;">
                            <div class="text-truncate" style="margin-bottom: 2px;"><img src="${teamLogo}" alt="${teamName}" style="width: 12px; height: 12px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> ${lastEv.time}'</div>
                            <div class="text-truncate" style="margin-bottom: ${assistHtml ? '0' : '2px'};">${icon} ${playerName}</div>
                            ${assistHtml}
                        </div>`;
             } else {
                if (lastEv.type === 'Goal' && lastEv.assist && lastEv.assist !== "null") {
                    let assistHtml = `<span class="text-truncate text-muted fw-normal" style="max-width: 160px; font-size: 0.60rem; padding-left: 20px;">👟 ${shortenPlayerName(lastEv.assist)}</span>`;
                    
                    return `<div class="ms-2 ${textColor} fw-bold" style="font-size: 0.65rem; display: inline-flex; flex-direction: column; justify-content: center; vertical-align: middle; line-height: 1.15;">
                                <span class="text-truncate" style="max-width: 160px;">${icon} ${lastEv.time}' <img src="${teamLogo}" alt="${teamName}" style="width: 12px; height: 12px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> ${playerName}</span>
                                ${assistHtml}
                            </div>`;
                }

                return `<span class="ms-2 ${textColor} fw-bold text-truncate" style="font-size: 0.70rem; max-width: 150px; display: inline-block; vertical-align: middle;">
                            ${icon} ${lastEv.time}' <img src="${teamLogo}" alt="${teamName}" style="width: 14px; height: 14px; object-fit: contain; margin-bottom: 2px; margin-right: 2px;"> ${playerName}
                        </span>`;
            }
        }
    }
    
    return isRibbon ? `<div class="text-muted text-start w-100 ps-2 d-flex align-items-center" style="font-size: 0.6rem; font-style: italic; height: 100%;">No Events</div>` : '';
}

function getRibbonHtml(data) {
    const home = data.teams.home;
    const away = data.teams.away;
    const status = data.fixture.status.short;
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);
    
    const homeScore = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals?.home ?? 0) : '-';
    const awayScore = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals?.away ?? 0) : '-';

    const leagueCompact = LEAGUE_ABBREV[data.league.id] || data.league.name;
    const flagHtml = data.league.flag 
        ? `<img src="${data.league.flag}" style="width: 18px; height: 13px; object-fit: cover; border-radius: 2px; border: 1px solid #dee2e6; margin-right: 4px; vertical-align: middle;">` 
        : `<span style="font-size: 0.75rem; margin-right: 4px; vertical-align: middle;">🏆</span>`;
    
    const params = getUrlParams();
    const lKey = getLeagueKey(data.league.id);
    const dQuery = params.date === DEFAULT_DATE ? '' : `?date=${params.date}`;
    const leagueHref = lKey === 'top' ? `/${dQuery}` : `/leagues/${lKey}/${dQuery}`;

    let hAggDisplay = '';
    let aAggDisplay = '';
    let nameMaxWidth = '88%'; 

    if (data.first_leg_goals) {
        const currentHomeGoals = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals?.home ?? 0) : 0;
        const currentAwayGoals = (!isPreGame && !isDelayed && !data.isFallback) ? (data.goals?.away ?? 0) : 0;

        const hAgg = currentHomeGoals + (data.first_leg_goals[home.id] ?? 0);
        const aAgg = currentAwayGoals + (data.first_leg_goals[away.id] ?? 0);
        
        hAggDisplay = `<span class="text-muted ms-1" style="font-size: 0.65rem; font-weight: 500;">(${hAgg})</span>`;
        aAggDisplay = `<span class="text-muted ms-1" style="font-size: 0.65rem; font-weight: 500;">(${aAgg})</span>`;
        
        nameMaxWidth = '70%'; 
    }

    return `
    <div class="row g-0 align-items-center py-2" style="transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='#f8f9fa'" onmouseout="this.style.backgroundColor='transparent'">
        <div class="col-3 text-center d-flex flex-column justify-content-center align-items-center border-end pe-1 ps-1">
            <div style="margin-bottom: 3px;">${getTimeBadgeHtml(data)}</div>
            <a href="${leagueHref}" onclick="event.stopPropagation();" class="text-decoration-none text-muted fw-bold text-truncate w-100 px-1 d-inline-block" style="font-size: 0.65rem; letter-spacing: 0.5px; text-transform: uppercase;" title="View all ${data.league.name} matches" onmouseover="this.classList.remove('text-muted'); this.classList.add('text-success');" onmouseout="this.classList.add('text-muted'); this.classList.remove('text-success');">
                ${flagHtml}${leagueCompact}
            </a>
        </div>
        <div class="col-5 px-2">
            <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: ${nameMaxWidth};">
                    <a href="/lineups/${getTeamSlug(home.name)}/" onclick="event.stopPropagation();" class="text-decoration-none text-dark" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'">
                        <img src="${home.logo}" width="14" height="14" class="me-1" style="object-fit:contain;">${home.name}
                    </a>
                </span>
                <div class="text-end" style="min-width: fit-content; white-space: nowrap;">
                    <span class="fw-bold text-dark" style="font-size: 0.85rem;">${homeScore}</span>${hAggDisplay}
                </div>
            </div>
            <div class="d-flex justify-content-between align-items-center">
                <span class="text-truncate fw-bold" style="font-size: 0.8rem; max-width: ${nameMaxWidth};">
                    <a href="/lineups/${getTeamSlug(away.name)}/" onclick="event.stopPropagation();" class="text-decoration-none text-dark" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'">
                        <img src="${away.logo}" width="14" height="14" class="me-1" style="object-fit:contain;">${away.name}
                    </a>
                </span>
                <div class="text-end" style="min-width: fit-content; white-space: nowrap;">
                    <span class="fw-bold text-dark" style="font-size: 0.85rem;">${awayScore}</span>${aAggDisplay}
                </div>
            </div>
        </div>
        <div class="col-4 text-center border-start d-flex justify-content-center align-items-center">
            ${getLatestEventHtml(data, true)}
        </div>
    </div>`;
}

function getCenterColumnHtml(data) {
    const status = data.fixture.status.short;
    const isPreGame = ['NS', 'TBD'].includes(status);
    const isDelayed = ['PST', 'CANC', 'ABD'].includes(status);
    const showScore = !isPreGame && !isDelayed && !data.isFallback;

    let aggDisplay = '';
    if (data.first_leg_goals) {
        const currentHomeGoals = showScore ? (data.goals?.home ?? 0) : 0;
        const currentAwayGoals = showScore ? (data.goals?.away ?? 0) : 0;
        const hAgg = currentHomeGoals + (data.first_leg_goals[data.teams.home.id] ?? 0);
        const aAgg = currentAwayGoals + (data.first_leg_goals[data.teams.away.id] ?? 0);
        
        aggDisplay = `<div class="text-muted fw-bold" style="font-size: 0.65rem; letter-spacing: 0.5px; margin-top: -2px;">(Agg: ${hAgg}-${aAgg})</div>`;
    }

    if (!showScore || !data.team_stats) {
        const scoreText = showScore ? `${data.goals?.home ?? 0} - ${data.goals?.away ?? 0}` : `vs`;
        return `
            <div class="d-flex flex-column align-items-center justify-content-center w-100">
                <div class="fw-bold text-dark mx-2" style="font-size: 1.2rem;">${scoreText}</div>
                ${aggDisplay}
            </div>`;
    }

    const tStats = data.team_stats;
    let hColor = data.homeLineup?.team?.colors?.player?.primary ? `#${data.homeLineup.team.colors.player.primary}` : '#0d6efd';
    let aColor = data.awayLineup?.team?.colors?.player?.primary ? `#${data.awayLineup.team.colors.player.primary}` : '#dc3545';
    
    if (colorDistance(hColor, aColor) < 60) {
        aColor = '#343a40'; 
    }

    const hText = getContrastColor(hColor);
    const aText = getContrastColor(aColor);
    const textShadowH = hText === '#ffffff' ? 'text-shadow: 0px 1px 2px rgba(0,0,0,0.6);' : '';
    const textShadowA = aText === '#ffffff' ? 'text-shadow: 0px 1px 2px rgba(0,0,0,0.6);' : '';

    const buildBar = (label, hVal, aVal, isPercentage = false) => {
        const total = hVal + aVal;
        let hPct = 50, aPct = 50, activeHColor = hColor, activeAColor = aColor;

        if (total > 0) {
            hPct = (hVal / total) * 100;
            aPct = (aVal / total) * 100;
        } else {
            activeHColor = '#adb5bd'; activeAColor = '#adb5bd';
        }
        
        let borderH = getContrastColor(activeHColor) === '#000000' ? 'border: 1px solid #ced4da;' : '';
        let borderA = getContrastColor(activeAColor) === '#000000' ? 'border: 1px solid #ced4da;' : '';

        const displayH = isPercentage ? `${hVal}%` : hVal;
        const displayA = isPercentage ? `${aVal}%` : aVal;

        return `
            <div class="text-center w-100 px-1">
                <div class="stat-label-tiny">${label}</div>
                <div class="stat-bar-container">
                    <div class="stat-bar-segment" style="width: ${hPct}%; background-color: ${activeHColor}; color: ${hText}; font-weight: 500; ${textShadowH} ${borderH}">
                        ${displayH}
                    </div>
                    <div class="stat-bar-segment" style="width: ${aPct}%; background-color: ${activeAColor}; color: ${aText}; font-weight: 500; ${textShadowA} ${borderA}">
                        ${displayA}
                    </div>
                </div>
            </div>
        `;
    };

    const cardsHome = `🟨 ${tStats.home?.yellow_cards ?? 0} 🟥 ${tStats.home?.red_cards ?? 0}`;
    const cardsAway = `🟨 ${tStats.away?.yellow_cards ?? 0} 🟥 ${tStats.away?.red_cards ?? 0}`;

    return `
        <div class="d-flex flex-column align-items-center justify-content-center w-100 mb-1">
            <div class="fw-bold text-dark mx-2" style="font-size: 1.1rem; line-height: 1;">${data.goals?.home ?? 0} - ${data.goals?.away ?? 0}</div>
            ${aggDisplay}
        </div>
        ${buildBar("Possession", tStats.home?.possession ?? 0, tStats.away?.possession ?? 0, true)}
        ${buildBar("Total Shots", tStats.home?.total_shots ?? 0, tStats.away?.total_shots ?? 0, false)}
        ${buildBar("Shots on Target", tStats.home?.shots_on_target ?? 0, tStats.away?.shots_on_target ?? 0, false)}
        ${buildBar("Corners", tStats.home?.corners ?? 0, tStats.away?.corners ?? 0, false)}
        
        <div class="text-center w-100 px-1 mt-1">
            <div class="stat-label-tiny" style="margin-bottom: 0px;">Cards</div>
            <div class="d-flex justify-content-between text-muted" style="font-size: 0.65rem; font-weight: 700;">
                <span>${cardsHome}</span>
                <span>${cardsAway}</span>
            </div>
        </div>
    `;
}

function getEventsHtml(data) {
    if (!data.events || data.events.length === 0) return '';
    const homeEvents = data.events.filter(e => e.team_id === data.teams.home.id);
    const awayEvents = data.events.filter(e => e.team_id === data.teams.away.id);
    
    const formatSingleEvent = (e, teamName) => {
        if (e.type === 'subst') {
            let pOut = (e.player && e.player !== "null") ? shortenPlayerName(e.player) : 'Unknown';
            let pIn = (e.player_out && e.player_out !== "null") ? shortenPlayerName(e.player_out) : 'Unknown';
            return `
                <div class="d-flex align-items-start" style="line-height: 1.1; margin-bottom: 2px;">
                    <div class="text-secondary fw-bold pe-1" style="width: 35px; text-align: right; flex-shrink: 0; font-size: 0.6rem; margin-top: 1px;">${e.time}'</div>
                    <div style="width: 18px; text-align: center; flex-shrink: 0;" class="me-1">🔄</div>
                    <div class="text-truncate" style="min-width: 0;">
                        <span class="text-dark fw-bold">${pIn}</span> IN<br>
                        <span class="text-muted" style="font-size: 0.6rem;">(${pOut} OUT)</span>
                    </div>
                </div>
            `;
        }

        let icon = '🟥';
        if (e.type === 'Goal') { icon = '⚽'; } 
        else if (e.detail && e.detail.includes('Yellow')) {
            icon = e.detail.includes('Red') || e.detail.includes('Second') ? '🟨🟥' : '🟨';
        }
        let playerName = (e.player && e.player !== "null") ? shortenPlayerName(e.player) : teamName;
        
        let assistHtml = '';
        if (e.type === 'Goal' && e.assist && e.assist !== "null") {
            assistHtml = `<br><span class="text-muted fw-normal" style="font-size: 0.55rem;">👟 ${shortenPlayerName(e.assist)}</span>`;
        }
        
        return `
            <div class="d-flex align-items-start" style="line-height: 1.1; margin-bottom: 2px;">
                <div class="text-secondary fw-bold pe-1" style="width: 35px; text-align: right; flex-shrink: 0; font-size: 0.6rem; margin-top: 1px;">${e.time}'</div>
                <div style="width: 18px; text-align: center; flex-shrink: 0;" class="me-1">${icon}</div>
                <div class="text-truncate" style="min-width: 0;">
                    <span class="text-dark fw-bold">${playerName}</span>${assistHtml}
                </div>
            </div>
        `;
    };

    const homeReversed = [...homeEvents].reverse();
    const awayReversed = [...awayEvents].reverse();

    const firstHome = homeReversed.length > 0 ? formatSingleEvent(homeReversed[0], data.teams.home.name) : '';
    const firstAway = awayReversed.length > 0 ? formatSingleEvent(awayReversed[0], data.teams.away.name) : '';

    const allHome = homeReversed.map(e => formatSingleEvent(e, data.teams.home.name)).join('');
    const allAway = awayReversed.map(e => formatSingleEvent(e, data.teams.away.name)).join('');

    const needsCollapse = Math.max(homeReversed.length, awayReversed.length) > 1;

    return `
    <div class="w-100 px-2 pt-1 mt-1 border-top text-muted" 
         style="font-size: 0.65rem; cursor: pointer; transition: background-color 0.2s; margin-bottom: -6px;" 
         onclick="if(${needsCollapse}) { const isExp = this.classList.toggle('is-expanded'); this.querySelector('.event-collapsed').classList.toggle('d-none', isExp); this.querySelector('.event-expanded').classList.toggle('d-none', !isExp); }"
         onmouseover="this.style.backgroundColor='#f8f9fa'" 
         onmouseout="this.style.backgroundColor='transparent'"
         title="${needsCollapse ? 'Click to expand/collapse goals and cards' : ''}">
        
        <div class="event-collapsed">
            <div class="d-flex justify-content-between">
                <div class="text-start" style="flex: 1; min-width: 0; padding-right: 4px;">${firstHome}</div>
                <div class="text-start" style="flex: 1; min-width: 0; padding-left: 4px;">${firstAway}</div>
            </div>
            ${needsCollapse ? `<div class="text-center text-secondary w-100" style="font-size: 0.65rem; line-height: 0.5; margin-top: -4px; padding-bottom: 6px;">▼</div>` : ''}
        </div>
        
        <div class="event-expanded d-none">
            <div class="d-flex justify-content-between">
                <div class="text-start" style="flex: 1; min-width: 0; padding-right: 4px;">${allHome}</div>
                <div class="text-start" style="flex: 1; min-width: 0; padding-left: 4px;">${allAway}</div>
            </div>
            <div class="text-center text-secondary w-100" style="font-size: 0.65rem; line-height: 0.5; margin-top: -4px; padding-bottom: 6px;">▲</div>
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
    const homeInjuries = (data.injuries && data.injuries.home) ? data.injuries.home : [];
    const awayInjuries = (data.injuries && data.injuries.away) ? data.injuries.away : [];
    
    if (homeInjuries.length === 0 && awayInjuries.length === 0) {
        return '';
    }
    
    // --- FIX: Wrap the mapped arrays in [...new Set()] to wipe out duplicates ---
    const cleanHomeInj = [...new Set(homeInjuries.map(n => shortenPlayerName(n)))];
    const cleanAwayInj = [...new Set(awayInjuries.map(n => shortenPlayerName(n)))];
    
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
    // 🎯 If the HTML gave us a hardcoded slug (because we are in a /leagues/ folder), use it!
    const activeLeague = window.ACTIVE_LEAGUE_SLUG || params.get('league') || 'top';
    return { league: activeLeague, date: params.get('date') || DEFAULT_DATE };
}

function renderLeagueMenu(activeLeague, currentDate) {
    const desktopMenu = document.getElementById('league-menu-desktop');
    const mobileMenu = document.getElementById('league-menu-mobile');
    
    if (!desktopMenu || !mobileMenu) return;

    desktopMenu.innerHTML = '';
    mobileMenu.innerHTML = '';

    const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
    // Switch from '&date=' to '?date=' since there are no longer other parameters
    const dateQuery = currentDate === todayStr ? '' : `?date=${currentDate}`;
    
    LEAGUE_GROUPS["priority"].forEach(league => {
        const a = document.createElement('a');
        // 🎯 Route directly to the physical folder
        const baseHref = league.key === 'top' ? '/' : `/leagues/${league.key}/`;
        a.href = `${baseHref}${dateQuery}`;
        a.className = `league-pill ${league.key === activeLeague ? 'active' : ''}`;
        a.textContent = league.name;
        desktopMenu.appendChild(a);
    });

    ['Europe', 'Americas', 'World', 'Cups', 'International', 'Women'].forEach(region => {
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
                ${regionLeagues.map(league => {
                    const baseHref = league.key === 'top' ? '/' : `/leagues/${league.key}/`;
                    return `<li><a class="dropdown-item ${league.key === activeLeague ? 'text-success fw-bold' : 'text-light'}" href="${baseHref}${dateQuery}">${league.name}</a></li>`;
                }).join('')}
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
        const baseHref = league.key === 'top' ? '/' : `/leagues/${league.key}/`;
        a.href = `${baseHref}${dateQuery}`;
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

    ['Europe', 'Americas', 'World', 'Cups', 'International', 'Women'].forEach((region, idx) => {
        if (idx !== 0) {
            dropdownHtml += `<li><hr class="dropdown-divider border-secondary"></li>`;
        }
        dropdownHtml += `<li><h6 class="dropdown-header pb-0" style="color: #adb5bd; font-weight: 700; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.5px;">${region}</h6></li>`;
        LEAGUE_GROUPS[region].forEach(league => {
            const baseHref = league.key === 'top' ? '/' : `/leagues/${league.key}/`;
            dropdownHtml += `<li><a class="dropdown-item ${league.key === activeLeague ? 'text-success fw-bold' : 'text-light'}" href="${baseHref}${dateQuery}">${league.name}</a></li>`;
        });
    });

    dropdownHtml += `</ul></div>`;
    mobileMenu.insertAdjacentHTML('beforeend', dropdownHtml);
}

async function fetchMatchesData(params) {
    try {
        const localRes = await fetch(`/data/games_${params.date}.json?v=` + new Date().getTime(), {
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

window.toggleSingleCard = function(fixId) {
    const ribbon = document.getElementById(`ribbon-${fixId}`);
    const full = document.getElementById(`full-${fixId}`);
    if (ribbon && full) {
        ribbon.classList.toggle('d-none');
        full.classList.toggle('d-none');
    }
};

window.switchLineupTab = function(fixId, tabName) {
    const xiTab = document.getElementById(`tab-xi-${fixId}`);
    const statsTab = document.getElementById(`tab-stats-${fixId}`);
    const xiView = document.getElementById(`view-xi-${fixId}`);
    const statsView = document.getElementById(`view-stats-${fixId}`);
    const collapseEl = document.getElementById(`lineup-collapse-${fixId}`);

    if (!xiTab || !statsTab || !xiView || !statsView || !collapseEl) return;

    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(collapseEl, { toggle: false });
    const isCurrentlyExpanded = collapseEl.classList.contains('show');
    const clickedActiveTab = (tabName === 'xi' && xiTab.classList.contains('active')) || 
                             (tabName === 'stats' && statsTab.classList.contains('active'));

    if (clickedActiveTab) {
        isCurrentlyExpanded ? bsCollapse.hide() : bsCollapse.show();
        return;
    }

    if (tabName === 'xi') {
        xiTab.classList.add('active');
        statsTab.classList.remove('active');
        xiView.classList.remove('d-none');
        statsView.classList.add('d-none');
    } else {
        statsTab.classList.add('active');
        xiTab.classList.remove('active');
        statsView.classList.remove('d-none');
        xiView.classList.add('d-none');
    }

    bsCollapse.show();
    checkOverflows();
};

function handleHashNavigation() {
    if (window.location.hash) {
        setTimeout(() => {
            const hash = window.location.hash;
            let fixId = null;
            let isGoalEvent = false;

            if (hash.startsWith('#lineup-')) {
                fixId = hash.replace('#lineup-', '');
            } else if (hash.startsWith('#card-')) {
                fixId = hash.replace('#card-', ''); 
            } else if (hash.startsWith('#goal-')) {
                fixId = hash.replace('#goal-', '');
                isGoalEvent = true;
            } else {
                return; 
            }

            const targetCard = document.getElementById(`card-${fixId}`);

            if (targetCard) {
                globalScoreboardMode = true;
                const toggleScoreboardBtn = document.getElementById('toggle-all-cards');
                if (toggleScoreboardBtn) toggleScoreboardBtn.innerHTML = '🔼 EXPAND ALL CARDS';
                
                const toggleAllBtn = document.getElementById('toggle-all-lineups');
                if (toggleAllBtn) toggleAllBtn.classList.add('d-none'); 
                
                document.querySelectorAll('.ribbon-view').forEach(el => el.classList.remove('d-none'));
                document.querySelectorAll('.full-view').forEach(el => el.classList.add('d-none'));

                if (!isGoalEvent) {
                    const targetRibbon = document.getElementById(`ribbon-${fixId}`);
                    const targetFull = document.getElementById(`full-${fixId}`);
                    if (targetRibbon && targetFull) {
                        targetRibbon.classList.add('d-none');
                        targetFull.classList.remove('d-none');
                    }

                    const targetLineup = document.getElementById(`lineup-collapse-${fixId}`);
                    if (targetLineup) {
                        targetLineup.classList.add('show');
                    }
                }

                const headerOffset = 120; 
                const elementPosition = targetCard.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
                
                window.scrollTo({
                     top: offsetPosition,
                     behavior: "smooth"
                });

                triggerCardHighlight(targetCard, 'hash'); 
                checkOverflows();
            }
        }, 600); 
    }
}

let isFirstLoad = true; 

async function init() {
    const params = getUrlParams();
    renderLeagueMenu(params.league, params.date);
    
    const container = document.getElementById('games-container');
    const datePicker = document.getElementById('date-picker');
    if (datePicker) datePicker.value = params.date;

    container.innerHTML = `<div class="col-12 text-center mt-5 pt-5"><div class="spinner-border text-success" role="status"></div><p class="mt-3 text-muted fw-bold">Loading Pitch Data...</p></div>`;
    
    // --- FETCH PLAYER DATABASE ONCE ON INITIALIZATION ---
    try {
        if (!PLAYER_DATABASE) {
            const dbRes = await fetch('/data/player_database.json');
            if (dbRes.ok) {
                PLAYER_DATABASE = await dbRes.json();
                console.log("📂 Player Database loaded safely into memory.");
            }
        }
    } catch (dbErr) {
        console.error("Error loading player database:", dbErr);
    }

    const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
    
    const yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    const yesterdayStr = yesterdayDate.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });

    // --- NEW: Add Tomorrow to handle late-night crossover viewing ---
    const tomorrowDate = new Date();
    tomorrowDate.setDate(tomorrowDate.getDate() + 1);
    const tomorrowStr = tomorrowDate.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });

    ALL_GAMES_DATA = await fetchMatchesData(params);
    if (!ALL_GAMES_DATA) ALL_GAMES_DATA = [];

    // Remove spinner immediately after local JSON is loaded
    if (ALL_GAMES_DATA.length > 0 || params.date !== todayStr) {
        renderGames();
        handleHashNavigation();
    }

    // --- FIX: Allow Firebase to listen on Today, Yesterday, AND Tomorrow ---
    if (params.date === todayStr || params.date === yesterdayStr || params.date === tomorrowStr) {
        console.log("📡 Connecting to Firebase Realtime Stream...");
        const liveRef = db.ref('futbol_live_games');
        
        liveRef.on('value', (snapshot) => {
            const incomingData = snapshot.val();
            
            if (incomingData) {
                let liveGamesArray = Object.values(incomingData);
                
                if (params.date === todayStr) {
                    liveGamesArray = liveGamesArray.filter(g => {
                        // FIX: Convert raw UTC to EST before comparing
                        const gDateEST = new Date(g.fixture.date).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
                        const isActiveYesterday = (gDateEST === yesterdayStr && !['FT', 'AET', 'PEN'].includes(g.fixture.status.short));
                        const isCrossoverTomorrow = (gDateEST === tomorrowStr);
                        
                        // We must accept Today, active Yesterday games, AND incoming crossover games
                        return gDateEST === todayStr || isActiveYesterday || isCrossoverTomorrow;
                    });
                } else if (params.date === yesterdayStr) {
                    liveGamesArray = liveGamesArray.filter(g => {
                        // FIX: Convert raw UTC to EST before comparing
                        const gDateEST = new Date(g.fixture.date).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
                        return gDateEST === yesterdayStr;
                    });
                } else if (params.date === tomorrowStr) {
                    liveGamesArray = liveGamesArray.filter(g => {
                        // FIX: Convert raw UTC to EST before comparing
                        const gDateEST = new Date(g.fixture.date).toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
                        return gDateEST === tomorrowStr;
                    });
                }

                // --- THE RESTORED LEAGUE FILTER ---
                if (params.league !== 'top') {
                    const targetId = SUPPORTED_LEAGUES[params.league].id;
                    liveGamesArray = liveGamesArray.filter(g => g.league.id === targetId);
                }

                console.log("⚡ Firebase Update Received!", liveGamesArray.length, "relevant games active.");

                let needsFullRender = isFirstLoad;

                liveGamesArray.forEach(liveGame => {
                    const index = ALL_GAMES_DATA.findIndex(g => g.fixture.id === liveGame.fixture.id);
                    if (index === -1) {
                        needsFullRender = true; 
                    }
                });
                
                if (needsFullRender) {
                    liveGamesArray.forEach(liveGame => {
                        const index = ALL_GAMES_DATA.findIndex(g => g.fixture.id === liveGame.fixture.id);
                        if (index !== -1) {
                            let oldMatch = ALL_GAMES_DATA[index];
                            
                            // SHIELD: Prevent API Glitch from clearing arrays at Full Time
                            if (!liveGame.homeLineup || !liveGame.homeLineup.startXI || liveGame.homeLineup.startXI.length === 0) liveGame.homeLineup = oldMatch.homeLineup;
                            if (!liveGame.awayLineup || !liveGame.awayLineup.startXI || liveGame.awayLineup.startXI.length === 0) liveGame.awayLineup = oldMatch.awayLineup;
                            if (!liveGame.team_stats) liveGame.team_stats = oldMatch.team_stats;
                            if (!liveGame.events || liveGame.events.length === 0) liveGame.events = oldMatch.events;
                            liveGame.first_leg_goals = liveGame.first_leg_goals || oldMatch.first_leg_goals;

                            ALL_GAMES_DATA[index] = liveGame; 
                        } else {
                            ALL_GAMES_DATA.unshift(liveGame); 
                        }
                    });
                    renderGames();
                    handleHashNavigation(); 
                    isFirstLoad = false;
                } else {
                    syncLiveDOM(liveGamesArray);
                }
            } else {
                console.log("💤 Firebase is empty. Relying on baseline JSON.");
                if (isFirstLoad) {
                    renderGames();
                    handleHashNavigation();
                    isFirstLoad = false;
                }
            }
        });
    } 
    else {
        console.log(`Rendering static archive for ${params.date}...`);
        renderGames();
        handleHashNavigation();
    }
}

function syncLiveDOM(liveGamesArray) {
    liveGamesArray.forEach(match => {
        const fixId = match.fixture.id;
        
        const oldMatchIndex = ALL_GAMES_DATA.findIndex(m => m.fixture.id === fixId);
        let oldMatch = null;

        if (oldMatchIndex !== -1) {
            oldMatch = ALL_GAMES_DATA[oldMatchIndex];
            
            // SHIELD: Prevent API Glitch from clearing arrays at Full Time
            if (!match.homeLineup || !match.homeLineup.startXI || match.homeLineup.startXI.length === 0) match.homeLineup = oldMatch.homeLineup;
            if (!match.awayLineup || !match.awayLineup.startXI || match.awayLineup.startXI.length === 0) match.awayLineup = oldMatch.awayLineup;
            if (!match.team_stats) match.team_stats = oldMatch.team_stats;
            if (!match.events || match.events.length === 0) match.events = oldMatch.events;
            match.first_leg_goals = match.first_leg_goals || oldMatch.first_leg_goals;

            ALL_GAMES_DATA[oldMatchIndex] = match; 
        } else {
            ALL_GAMES_DATA.push(match);
        }
        
        const timeEl = document.getElementById(`time-${fixId}`);
        const scoreEl = document.getElementById(`score-${fixId}`);
        const eventsEl = document.getElementById(`events-${fixId}`);
        const oddsEl = document.getElementById(`odds-${fixId}`);
        const injuriesEl = document.getElementById(`injuries-${fixId}`);
        
        if (timeEl && scoreEl && eventsEl && oddsEl && injuriesEl) {
            
            if (oldMatch && !oldMatch.team_stats && match.team_stats) {
                const hCol = scoreEl.previousElementSibling;
                const aCol = scoreEl.nextElementSibling;
                if (hCol && aCol) {
                    hCol.style.width = '25%'; aCol.style.width = '25%'; scoreEl.style.width = '50%';
                    const hImg = hCol.querySelector('img'); const aImg = aCol.querySelector('img');
                    if (hImg) { hImg.style.width = '35px'; hImg.style.height = '35px'; }
                    if (aImg) { aImg.style.width = '35px'; aImg.style.height = '35px'; }
                    const hName = hCol.querySelector('.fw-bold.text-truncate');
                    const aName = aCol.querySelector('.fw-bold.text-truncate');
                    if (hName) hName.style.fontSize = '0.75rem';
                    if (aName) aName.style.fontSize = '0.75rem';
                }
            }

            const newTimeHtml = (getTimeBadgeHtml(match) + ' ' + getLatestEventHtml(match)).trim();
            const newCenterHtml = getCenterColumnHtml(match).trim();
            const newEventsHtml = getEventsHtml(match).trim();
            const newOddsHtml = getOddsHtml(match).trim();
            const newInjuriesHtml = getInjuriesHtml(match).trim();
            
            if (timeEl.innerHTML.trim() !== newTimeHtml) timeEl.innerHTML = newTimeHtml;
            if (scoreEl.innerHTML.trim() !== newCenterHtml) scoreEl.innerHTML = newCenterHtml;
            
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
        
        const ribbonEl = document.getElementById(`ribbon-${fixId}`);
        if (ribbonEl) {
            const newRibbonHtml = getRibbonHtml(match).trim();
            if (ribbonEl.innerHTML.trim() !== newRibbonHtml) ribbonEl.innerHTML = newRibbonHtml;
        }
        
        if (oldMatch) {
            const oldEvLen = oldMatch.events ? oldMatch.events.length : 0;
            const newEvLen = match.events ? match.events.length : 0;
            
            if (newEvLen > oldEvLen) {
                const latestEvent = match.events[newEvLen - 1]; 
                const cardEl = document.getElementById(`card-${fixId}`);
                if (cardEl && latestEvent) {
                    if (latestEvent.type === 'Goal') { triggerCardHighlight(cardEl, 'goal'); } 
                    else if (latestEvent.type === 'Card' && latestEvent.detail) {
                        if (latestEvent.detail.includes('Second') || latestEvent.detail.includes('Yellow / Red')) {
                            triggerCardHighlight(cardEl, 'yellow_card');
                            setTimeout(() => { triggerCardHighlight(cardEl, 'red_card'); }, 4500); 
                        } else if (latestEvent.detail.includes('Red')) { triggerCardHighlight(cardEl, 'red_card'); } 
                        else if (latestEvent.detail.includes('Yellow')) { triggerCardHighlight(cardEl, 'yellow_card'); }
                    } else if (latestEvent.type === 'subst') { triggerCardHighlight(cardEl, 'subst'); }
                }
            }

            const viewXiEl = document.getElementById(`view-xi-${fixId}`);
            if (viewXiEl) {
                const newXiHtml = `<div class="row g-0 bg-white"><div class="col-6 border-end">${buildLineupList(match.homeLineup, match)}</div><div class="col-6">${buildLineupList(match.awayLineup, match)}</div></div>`;
                if (viewXiEl.innerHTML.trim() !== newXiHtml.trim()) viewXiEl.innerHTML = newXiHtml;
            }

            const viewStatsEl = document.getElementById(`view-stats-${fixId}`);
            if (viewStatsEl) {
                let hColor = match.homeLineup?.team?.colors?.player?.primary ? `#${match.homeLineup.team.colors.player.primary}` : '#0d6efd';
                let aColor = match.awayLineup?.team?.colors?.player?.primary ? `#${match.awayLineup.team.colors.player.primary}` : '#dc3545';
                if (colorDistance(hColor, aColor) < 60) aColor = '#343a40';

                const newStatsHtml = `<div class="row g-0 bg-white"><div class="col-6 border-end">${buildLiveStatsGrid(match.homeLineup, hColor)}</div><div class="col-6">${buildLiveStatsGrid(match.awayLineup, aColor)}</div></div>`;
                if (viewStatsEl.innerHTML.trim() !== newStatsHtml.trim()) viewStatsEl.innerHTML = newStatsHtml;
            }

            const wasPreGame = ['NS', 'TBD'].includes(oldMatch.fixture.status.short);
            const isNowLive = !['NS', 'TBD'].includes(match.fixture.status.short);
            const isFinished = ['FT', 'AET', 'PEN'].includes(match.fixture.status.short);

            const xiTab = document.getElementById(`tab-xi-${fixId}`);
            const statsTab = document.getElementById(`tab-stats-${fixId}`);
            
            if (xiTab) xiTab.textContent = isFinished ? "FINAL XI" : "STARTING XI";
            if (statsTab) statsTab.textContent = isFinished ? "FINAL STATS" : "LIVE STATS";

            if (match.team_stats && statsTab) {
                const wasHidden = statsTab.classList.contains('d-none');
                if (wasHidden) statsTab.classList.remove('d-none');
                if (wasHidden || (wasPreGame && isNowLive)) switchLineupTab(fixId, 'stats');
            }
        }
    });

    requestAnimationFrame(() => requestAnimationFrame(checkOverflows));
}

async function fallbackToStaticJSON(params) {
    ALL_GAMES_DATA = await fetchMatchesData(params);
    if (!ALL_GAMES_DATA) {
        ALL_GAMES_DATA = [];
    }
    renderGames();
    handleHashNavigation();
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
        const deadStatuses = ['FT', 'AET', 'PEN', 'PST', 'CANC', 'ABD'];
        
        const isFinishedA = deadStatuses.includes(a.fixture.status.short);
        const isFinishedB = deadStatuses.includes(b.fixture.status.short);
        
        if (isFinishedA && !isFinishedB) return 1;
        if (!isFinishedA && isFinishedB) return -1;
        
        return new Date(a.fixture.date) - new Date(b.fixture.date);
    });

    
    if (filteredGames.length === 0) {
        const params = getUrlParams();
        const isLeagueFiltered = params.league && params.league !== 'top';
        
        let leagueName = "Global Football";
        if (isLeagueFiltered) {
            for (const region in LEAGUE_GROUPS) {
                const found = LEAGUE_GROUPS[region].find(l => l.key === params.league);
                if (found) { leagueName = found.name; break; }
            }
        }

        const titleMsg = `${leagueName} Live Hub`;
        const bodyMsg = `The fixture list is currently clear for <strong>${params.date}</strong>. When ${leagueName} clubs are in action, this dashboard automatically updates in real-time.`;

        const actionBtn = `<a href="/" class="btn btn-dark mt-2 fw-bold shadow-sm px-4 py-2" style="border-radius: 20px;">View Active Global Matches</a>`;

        container.innerHTML = `
            <div class="col-12 col-md-8 mx-auto mt-4 mb-5">
                <div class="card shadow-sm border text-start py-4 px-4" style="background-color: #fff; border-radius: 12px; border-color: #dee2e6 !important;">
                    <div class="d-flex align-items-center border-bottom pb-3 mb-3">
                        <div style="font-size: 2.5rem; margin-right: 15px;">🏟️</div>
                        <h2 class="h4 fw-bold text-dark mb-0">${titleMsg}</h2>
                    </div>
                    
                    <p class="text-dark mb-4" style="font-size: 0.95rem; line-height: 1.5;">${bodyMsg}</p>
                    
                    <h3 class="h6 fw-bold text-dark mb-3">What to expect on matchday:</h3>
                    <div class="row text-muted mb-3" style="font-size: 0.9rem;">
                        <div class="col-sm-6 mb-3">📋 <strong>Confirmed Starting XIs:</strong> Formations and starters updated right before kickoff.</div>
                        <div class="col-sm-6 mb-3">⚡ <strong>Live Match Events:</strong> Real-time goals, cards, and substitutions.</div>
                        <div class="col-sm-6 mb-3">📊 <strong>Live Team Stats:</strong> Possession, shots on target, and corner tracking.</div>
                        <div class="col-sm-6 mb-3">📈 <strong>Live Odds:</strong> Up-to-the-minute moneyline and totals.</div>
                    </div>
                    
                    <div class="text-center pt-3">
                        ${actionBtn}
                    </div>
                </div>
            </div>`;
        return; 
    }

    filteredGames.forEach(item => container.appendChild(createGameCard(item)));
    
    requestAnimationFrame(() => requestAnimationFrame(checkOverflows));
}

function buildLiveStatsGrid(lineupData, teamColorHex) {
    if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) return `<div class="p-4 text-center text-muted small fw-bold">Awaiting live stats...</div>`;

    const groups = {
        'F': { title: 'FWD', stats: ['G', 'A', 'SOT', 'SH'], keys: ['goals', 'assists', 'shots_on_target', 'total_shots'] },
        'M': { title: 'MID', stats: ['G', 'A', 'KP', 'TK'], keys: ['goals', 'assists', 'key_passes', 'tackles'] },
        'D': { title: 'DEF', stats: ['G', 'A', 'TK', 'IN'], keys: ['goals', 'assists', 'tackles', 'interceptions'] },
        'G': { title: 'GK',  stats: ['SV', 'GC', 'PA', 'YC'], keys: ['saves', 'conceded', 'passes', 'yellow_cards'] }
    };

    const groupedPlayers = { 'F': [], 'M': [], 'D': [], 'G': [] };
    let flatPlayers = [];

    lineupData.startXI.forEach(slot => {
        flatPlayers.push({ ...slot.player, _isSubbedOut: false });
        if (slot.sub_history) {
            slot.sub_history.forEach(h => flatPlayers.push({ ...h, _isSubbedOut: true }));
        }
    });

    if (lineupData.substitutes) {
        lineupData.substitutes.forEach(sub => {
            if (sub.player.live_stats && Object.values(sub.player.live_stats).some(v => v !== 0 && v !== "N/A" && v !== "0")) {
                if (!flatPlayers.find(p => p.id === sub.player.id)) {
                    flatPlayers.push({ ...sub.player, _isSubbedIn: true, _isSubbedOut: false });
                }
            }
        });
    }

    flatPlayers.forEach(p => groupedPlayers[p.pos || 'M'].push(p));

    let html = '';
    let tColor = teamColorHex ? `#${teamColorHex.replace('#', '')}` : '#6c757d';

    if (getContrastColor(tColor) === '#000000') {
        tColor = '#495057';
    }

    ['F', 'M', 'D', 'G'].forEach(posKey => {
        const players = groupedPlayers[posKey];
        if (players.length === 0) return;

        const gConf = groups[posKey];

        html += `
            <div class="d-flex w-100 px-2 py-1 align-items-center" style="background-color: #f1f3f5; font-size: 0.6rem; font-weight: 600; color: #495057; border-bottom: 1px solid #dee2e6;">
                <div style="flex: 1; text-align: left; color: ${tColor};">${gConf.title}</div>
                <div style="width: 14px; text-align: center;">${gConf.stats[0]}</div>
                <div style="width: 14px; text-align: center;">${gConf.stats[1]}</div>
                <div style="width: 26px; text-align: center;">${gConf.stats[2]}</div>
                <div style="width: 22px; text-align: center;">${gConf.stats[3]}</div>
            </div>
        `;

        players.forEach(p => {
            const lStats = p.live_stats || {};
            const name = shortenPlayerName(p.name || 'Unknown');
            
            
            const v1 = lStats[gConf.keys[0]] || 0;
            const v2 = lStats[gConf.keys[1]] || 0;
            const v3 = lStats[gConf.keys[2]] || 0;
            const v4 = lStats[gConf.keys[3]] || 0;

            let prefix = '';
            if (p.isSubbedIn || p._isSubbedIn) prefix = `<span class="text-primary fw-bold" style="position: absolute; top: 1px; left: 0; font-size: 0.50rem;">↻</span>`;
            if (p._isSubbedOut) prefix = `<span class="text-success fw-bold" style="position: absolute; top: 1px; left: 0; font-size: 0.50rem;">▲</span>`;

            // Inject link if the player exists inside our memory registry database
            let liveNameContentHtml = `<span class="position-relative d-inline-block text-truncate" style="padding-left: 10px; max-width: 100%; vertical-align: middle;">${prefix}${name}</span>`;
            
            if (PLAYER_DATABASE && PLAYER_DATABASE[p.id]) {
                const pSlug = PLAYER_DATABASE[p.id].slug;
                liveNameContentHtml = `
                    <a href="/players/${pSlug}/" class="text-decoration-none d-inline-block text-truncate position-relative" style="padding-left: 10px; max-width: 100%; vertical-align: middle;" onclick="event.stopPropagation();">
                        ${prefix}<span class="fw-bold text-dark" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'">${name}</span>
                    </a>`;
            }

            html += `
                <div class="d-flex align-items-center w-100 px-2 py-1 border-bottom user-select-none player-stat-row" style="font-size: 0.70rem; transition: background-color 0.2s;" onmouseover="this.style.backgroundColor='#f8f9fa'" onmouseout="this.style.backgroundColor='transparent'">
                    <div class="text-start d-flex align-items-center" style="flex: 1; min-width: 0;">
                        ${liveNameContentHtml}
                    </div>
                    <div class="text-muted" style="width: 14px; text-align: center; font-weight: 600;">${v1}</div>
                    <div class="text-muted" style="width: 14px; text-align: center; font-weight: 600;">${v2}</div>
                    <div class="text-muted" style="width: 26px; text-align: center; font-weight: 600;">${v3}</div>
                    <div class="text-muted" style="width: 22px; text-align: center; font-weight: 600;">${v4}</div>
                </div>
            `;
        });
    });

    return html;
}

function buildLineupList(lineupData, gameData) {
    if (gameData.isFallback) return `<div class="p-4 text-center text-muted small fst-italic">Formations & lineups available on match day</div>`;
    if (!lineupData || !lineupData.startXI || lineupData.startXI.length === 0) return `<div class="p-4 text-center text-muted small fw-bold">Lineup pending...</div>`;
    
    const formationHeader = `<div class="w-100 text-center py-1 fw-bold text-white" style="font-size: 0.65rem; background-color: #198754; border-bottom: 1px solid #146c43;">✅ ${lineupData.formation}</div>`;
    
    const listItems = lineupData.startXI.map(slot => {
        const renderRow = (p, isSubbedOut) => {
            const safePos = p.pos || '-';
            const originalName = p.name || 'Unknown';
            const displaySafeName = shortenPlayerName(originalName);
            const safeNum = p.number || '';
            
            // 🎯 THE FIX: Try the match feed first, but fallback to the master database if missing
            let photoUrl = p.photo || '';
            if ((!photoUrl || !photoUrl.includes("http")) && PLAYER_DATABASE && PLAYER_DATABASE[p.id]) {
                // Checks for 'photo' or 'photo_url' depending on your JSON key structure
                photoUrl = PLAYER_DATABASE[p.id].photo || PLAYER_DATABASE[p.id].photo_url || '';
            }
            
            let posColor = safePos === 'G' ? "#dc3545" : safePos === 'D' ? "#0d6efd" : safePos === 'M' ? "#20c997" : "#ffc107";
            
            const photoHtml = photoUrl && photoUrl.includes("http") 
                ? `<img src="${photoUrl}" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover; border: 1px solid #dee2e6;">`
                : `<div style="width: 24px; height: 24px; border-radius: 50%; background-color: #f1f3f5; color: #adb5bd; display: flex; align-items: center; justify-content: center; font-size: 0.6rem; font-weight: bold; border: 1px solid #dee2e6;">${originalName.charAt(0).toUpperCase()}</div>`;

            let prefix = '';
            if (p.isSubbedIn) prefix = `<span class="text-primary fw-bold" style="position: absolute; top: 1px; left: 0; font-size: 0.50rem;" title="Subbed in at ${p.subMinute}'">↻</span>`;
            if (isSubbedOut) prefix = `<span class="text-success fw-bold" style="position: absolute; top: 1px; left: 0; font-size: 0.50rem;" title="Subbed out at ${p.subMinute}'">▲</span>`;

            // Look up player database entry safely using a direct ID query
            let nameContentHtml = `<span class="batter-name fw-bold text-dark text-truncate position-relative d-inline-block" style="font-size: 0.85rem; padding-left: 10px; max-width: 100%; vertical-align: middle;" title="${originalName}">${prefix}${displaySafeName}</span>`;
            
            if (PLAYER_DATABASE && PLAYER_DATABASE[p.id]) {
                const pSlug = PLAYER_DATABASE[p.id].slug;
                nameContentHtml = `
                    <a href="/players/${pSlug}/" class="text-decoration-none d-inline-block text-truncate position-relative" style="padding-left: 10px; max-width: 100%; vertical-align: middle;" onclick="event.stopPropagation();">
                        ${prefix}<span class="batter-name fw-bold text-dark" style="font-size: 0.85rem;" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'" title="${originalName}">${displaySafeName}</span>
                    </a>`;
            }

            const rowStyle = isSubbedOut ? `font-style: italic; opacity: 0.75; background-color: #fcfcfc; border-bottom: 1px dashed #dee2e6;` : `transition: background-color 0.2s; border-bottom: 1px solid #f1f3f5;`;
            const hoverAttr = isSubbedOut ? `` : `onmouseover="this.style.backgroundColor='#f8f9fa'" onmouseout="this.style.backgroundColor='transparent'"`;

            return `
                <li class="d-flex align-items-center w-100 px-2 py-1 user-select-none" style="${rowStyle}" ${hoverAttr}>
                    <span class="text-muted fw-bold d-inline-block text-start me-1" style="font-size: 0.7rem; width: 15px; color: ${posColor} !important;">${safePos}</span>
                    <div class="me-2">${photoHtml}</div>
                    ${nameContentHtml}
                    <span class="ms-auto text-muted" style="font-size: 0.65rem;">#${safeNum}</span>
                </li>`;
        };

        let html = renderRow(slot.player, false);
        if (slot.sub_history && slot.sub_history.length > 0) {
            slot.sub_history.forEach(hPlayer => {
                html += renderRow(hPlayer, true);
            });
        }
        return html;

    }).join('');
    return `${formationHeader}<ul class="batting-order w-100 m-0 p-0" style="list-style-type: none;">${listItems}</ul>`;
}

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
    
    const statusShort = data.fixture.status.short;
    const isPreGame = ['NS', 'TBD'].includes(statusShort);
    const isFinished = ['FT', 'AET', 'PEN'].includes(statusShort);
    const params = getUrlParams();
    const lKey = getLeagueKey(data.league.id);
    const dQuery = params.date === DEFAULT_DATE ? '' : `?date=${params.date}`;
    const leagueHref = lKey === 'top' ? `/${dQuery}` : `/leagues/${lKey}/${dQuery}`;

    const xiTabText = isFinished ? "FINAL XI" : "STARTING XI";
    const statsTabText = isFinished ? "FINAL STATS" : "LIVE STATS";

    const hColor = data.homeLineup?.team?.colors?.player?.primary;
    const aColor = data.awayLineup?.team?.colors?.player?.primary;

    const fullHtml = `
        <div class="p-2 pb-1" style="background-color: #fcfcfc;">
            <div class="d-flex align-items-center mb-2 w-100 pb-1 border-bottom border-light" style="cursor: pointer;" onclick="toggleSingleCard(${fixId})" title="Click to collapse">
                <div id="time-${fixId}" style="flex: 0 0 auto;" class="pe-2">${getTimeBadgeHtml(data)} ${getLatestEventHtml(data)}</div>
                <a href="${leagueHref}" onclick="event.stopPropagation();" class="text-decoration-none text-muted fw-bold text-uppercase text-end ms-auto text-truncate" style="font-size: 0.70rem;" title="View all ${data.league.name} matches" onmouseover="this.classList.remove('text-muted'); this.classList.add('text-success');" onmouseout="this.classList.add('text-muted'); this.classList.remove('text-success');">
                    ${data.league.name}
                </a>
            </div>
            <div class="d-flex justify-content-between align-items-center px-1 pt-1 pb-1 w-100">
                <div class="text-center transition-width" style="width: ${data.team_stats ? '25%' : '41%'}; flex-shrink: 0;"> 
                    <a href="/lineups/${getTeamSlug(home.name)}/" class="text-decoration-none" style="color: inherit;">
                        <img src="${home.logo}" alt="${home.name}" class="team-logo mb-1" style="width: ${data.team_stats ? '35px' : '55px'}; height: ${data.team_stats ? '35px' : '55px'}; transition: all 0.3s ease;">
                        <div class="fw-bold text-dark text-truncate w-100" style="font-size: ${data.team_stats ? '0.75rem' : '0.9rem'}; transition: font-size 0.3s ease;" title="${home.name}" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'">${homeRank}${home.name}</div>
                    </a>
                    ${homeRecord}
                </div>
                
                <div id="score-${fixId}" class="text-center d-flex flex-column align-items-center justify-content-center transition-width mx-2" style="width: ${data.team_stats ? '50%' : '18%'}; min-width: 0;">
                    ${getCenterColumnHtml(data)}
                </div>
                
                <div class="text-center transition-width" style="width: ${data.team_stats ? '25%' : '41%'}; flex-shrink: 0;"> 
                    <a href="/lineups/${getTeamSlug(away.name)}/" class="text-decoration-none" style="color: inherit;">
                        <img src="${away.logo}" alt="${away.name}" class="team-logo mb-1" style="width: ${data.team_stats ? '35px' : '55px'}; height: ${data.team_stats ? '35px' : '55px'}; transition: all 0.3s ease;">
                        <div class="fw-bold text-dark text-truncate w-100" style="font-size: ${data.team_stats ? '0.75rem' : '0.9rem'}; transition: font-size 0.3s ease;" title="${away.name}" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'">${awayRank}${away.name}</div>
                    </a>
                    ${awayRecord}
                </div>
            </div>
            <div id="events-${fixId}" class="w-100">${getEventsHtml(data)}</div>
        </div>
        <div id="odds-${fixId}" class="w-100">${getOddsHtml(data)}</div>
        <div id="injuries-${fixId}" class="w-100">${getInjuriesHtml(data)}</div>
        
        <div class="bg-light border-bottom d-flex justify-content-center align-items-center px-2 py-1" style="background-color: #f8f9fa;">
            <div class="d-flex gap-4 w-100">
                <div class="lineup-tab ${(!data.team_stats || isPreGame) ? 'active' : ''}" 
                     id="tab-xi-${fixId}" 
                     onclick="switchLineupTab(${fixId}, 'xi')"
                     style="flex: 1; text-align: center;">
                    ${xiTabText}
                </div>
                <div class="lineup-tab ${(data.team_stats && !isPreGame) ? 'active' : ''} ${!data.team_stats ? 'd-none' : ''}" 
                     id="tab-stats-${fixId}" 
                     onclick="switchLineupTab(${fixId}, 'stats')"
                     style="flex: 1; text-align: center;">
                    ${statsTabText}
                </div>
            </div>
        </div>
        
        <div class="collapse ${globalLineupsExpanded ? 'show' : ''} lineup-container" id="lineup-collapse-${fixId}">
            
            <div id="view-xi-${fixId}" class="${(data.team_stats && !isPreGame) ? 'd-none' : ''}">
                <div class="row g-0 bg-white">
                    <div class="col-6 border-end">${buildLineupList(data.homeLineup, data)}</div>
                    <div class="col-6">${buildLineupList(data.awayLineup, data)}</div>
                </div>
            </div>
            
            <div id="view-stats-${fixId}" class="${(!data.team_stats || isPreGame) ? 'd-none' : ''}">
                <div class="row g-0 bg-white">
                    <div class="col-6 border-end">${buildLiveStatsGrid(data.homeLineup, hColor)}</div>
                    <div class="col-6">${buildLiveStatsGrid(data.awayLineup, aColor)}</div>
                </div>
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
        if (globalScoreboardMode) toggleAllBtn.classList.add('d-none'); 
        
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
                if (toggleAllBtn) toggleAllBtn.classList.add('d-none'); 
            } else {
                allRibbons.forEach(el => el.classList.add('d-none'));
                allFulls.forEach(el => el.classList.remove('d-none'));
                if (toggleAllBtn) toggleAllBtn.classList.remove('d-none'); 
            }
            
            checkOverflows();
        });
    }
});

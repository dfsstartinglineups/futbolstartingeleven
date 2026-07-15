document.addEventListener("DOMContentLoaded", () => {
    const playerId = window.TARGET_PLAYER_ID;
    const teamName = window.TARGET_TEAM_NAME;
    
    if (!playerId) return;

    // ==========================================
    // FIREBASE CONFIGURATION (Matches Main Site)
    // ==========================================
    const firebaseConfig = {
        databaseURL: "https://nbastartingfive-8b420-default-rtdb.firebaseio.com/"
    };

    // ==========================================
    // DYNAMIC SDK LOADER
    // ==========================================
    function loadFirebaseSDK() {
        return new Promise((resolve, reject) => {
            if (window.firebase) return resolve(); // Already loaded
            
            const scriptApp = document.createElement("script");
            scriptApp.src = "https://www.gstatic.com/firebasejs/10.8.0/firebase-app-compat.js";
            scriptApp.onload = () => {
                const scriptDB = document.createElement("script");
                scriptDB.src = "https://www.gstatic.com/firebasejs/10.8.0/firebase-database-compat.js";
                scriptDB.onload = resolve;
                scriptDB.onerror = reject;
                document.head.appendChild(scriptDB);
            };
            scriptApp.onerror = reject;
            document.head.appendChild(scriptApp);
        });
    }

    // ==========================================
    // HELPERS & SAFE MERGE LOGIC
    // ==========================================
    function getTeamSlug(tName) {
        if (!tName) return "";
        return tName
            .toLowerCase()
            .normalize("NFD") 
            .replace(/[\u0300-\u036f]/g, "") 
            .replace(/\//g, "-") // <-- THE FIX: Converts forward slashes into hyphens first
            .replace(/[^a-z0-9\s-]/g, "") 
            .replace(/\s+/g, "-") 
            .replace(/-+/g, "-") 
            .replace(/^-+|-+$/g, "") // Trims leading/trailing hyphens cleanly
            .trim();
    }

    function mergeFirebaseIntoJSON(jsonMatch, fbMatch) {
        if (!jsonMatch) return fbMatch;

        let merged = JSON.parse(JSON.stringify(jsonMatch));

        if (fbMatch.goals) merged.goals = fbMatch.goals;
        if (fbMatch.fixture && fbMatch.fixture.status) merged.fixture.status = fbMatch.fixture.status;
        if (fbMatch.events && fbMatch.events.length > 0) merged.events = fbMatch.events;
        if (fbMatch.team_stats && fbMatch.team_stats.home) merged.team_stats = fbMatch.team_stats;

        if (fbMatch.homeLineup && Array.isArray(fbMatch.homeLineup.startXI) && fbMatch.homeLineup.startXI.length > 0) {
            merged.homeLineup = fbMatch.homeLineup;
        }
        if (fbMatch.awayLineup && Array.isArray(fbMatch.awayLineup.startXI) && fbMatch.awayLineup.startXI.length > 0) {
            merged.awayLineup = fbMatch.awayLineup;
        }

        merged.first_leg_goals = fbMatch.first_leg_goals || jsonMatch.first_leg_goals;
        if (fbMatch.odds && fbMatch.odds.home !== "TBD") merged.odds = fbMatch.odds;
        if (fbMatch.injuries && (fbMatch.injuries.home?.length > 0 || fbMatch.injuries.away?.length > 0)) {
            merged.injuries = fbMatch.injuries;
        }

        return merged;
    }

    // Inject CSS for the live pulsing green dot
    if (!document.getElementById('live-pulse-style')) {
        const style = document.createElement('style');
        style.id = 'live-pulse-style';
        style.innerHTML = `
            @keyframes livePulse {
                0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0.7); }
                70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(32, 201, 151, 0); }
                100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(32, 201, 151, 0); }
            }
        `;
        document.head.appendChild(style);
    }

    // 🎯 THE FIX: Correctly maps original starters vs. incoming substitutes
    function findPlayerInMatch(match, targetId) {
        let playerObj = null;
        let status = 'not_in_squad'; 
        let teamSide = null; 

        function checkLineup(lineup, sideName) {
            if (!lineup) return;
            
            if (lineup.startXI) {
                for (const slot of lineup.startXI) {
                    
                    // 1. Are they the original starter occupying this slot?
                    if (slot.player && slot.player.id == targetId) {
                        playerObj = slot.player;
                        teamSide = sideName;
                        
                        // If someone is in sub_history for this slot, the starter was taken OFF the pitch
                        if (slot.sub_history && slot.sub_history.length > 0) {
                            status = 'subbed_out';
                        } else {
                            status = 'on_pitch';
                        }
                        return;
                    }

                    // 2. Are they the substitute who came ON to the pitch?
                    if (slot.sub_history) {
                        const subIn = slot.sub_history.find(h => h.id == targetId);
                        if (subIn) {
                            playerObj = subIn;
                            teamSide = sideName;
                            // The substitute who replaced the starter is currently ON the pitch
                            status = 'on_pitch';
                            return;
                        }
                    }
                }
            }
            
            // 3. Are they sitting on the bench unused?
            if (lineup.substitutes) {
                const benchSlot = lineup.substitutes.find(slot => slot.player.id == targetId);
                if (benchSlot) {
                    playerObj = benchSlot.player;
                    teamSide = sideName;
                    status = 'bench';
                    return;
                }
            }
        }

        checkLineup(match.homeLineup, 'home');
        if (!playerObj) checkLineup(match.awayLineup, 'away');

        return { playerObj, status, teamSide };
    }

    // ==========================================
    // MAIN LIVE CONTROLLER
    // ==========================================
    async function init() {
        try {
            // Get today's date in EST to pull today's fixture card baseline
            const today = new Date().toLocaleString("en-US", { timeZone: "America/New_York" });
            const dateObj = new Date(today);
            const dateString = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}-${String(dateObj.getDate()).padStart(2, '0')}`;

            const localRes = await fetch(`/data/games_${dateString}.json`);
            if (!localRes.ok) return; // Silent exit (no games today)

            const games = await localRes.json();
            if (!Array.isArray(games)) return;

            let targetGame = null;

            // Step 1: Find if today's games contain our team or our player's active lineup
            for (const game of games) {
                const homeName = game.teams.home.name;
                const awayName = game.teams.away.name;

                if (homeName === teamName || awayName === teamName) {
                    targetGame = game;
                }

                const { playerObj } = findPlayerInMatch(game, playerId);
                if (playerObj) {
                    targetGame = game;
                    break; // Exact game locked in, stop searching
                }
            }

            // Step 2: If the player is scheduled for today, establish dynamic live stream!
            if (targetGame) {
                await loadFirebaseSDK();

                if (!firebase.apps.length) {
                    firebase.initializeApp(firebaseConfig);
                }
                const db = firebase.database();
                const liveRef = db.ref('futbol_live_games');

                liveRef.on('value', (snapshot) => {
                    const incomingData = snapshot.val();
                    let liveGame = null;

                    if (incomingData) {
                        // Extract by Direct Fixture ID index or via Array scan
                        liveGame = incomingData[targetGame.fixture.id];
                        if (!liveGame) {
                            liveGame = Object.values(incomingData).find(g => g.fixture?.id === targetGame.fixture.id);
                        }
                    }

                    // Merge dynamic real-time data on top of static local baseline safely
                    const finalGameData = liveGame ? mergeFirebaseIntoJSON(targetGame, liveGame) : targetGame;
                    renderWidget(finalGameData);
                });
            }

        } catch (e) {
            console.error("FSE Live Tracker Error:", e);
        }
    }

    function renderWidget(game) {
        const widget = document.getElementById('live-match-widget');
        if (!widget) return;

        const status = game.fixture.status.short;
        const elapsed = game.fixture.status.elapsed;
        const homeScore = game.goals?.home ?? 0;
        const awayScore = game.goals?.away ?? 0;

        const isFinished = ['FT', 'AET', 'PEN'].includes(status);
        const isPreGame = ['NS', 'TBD'].includes(status);
        
        let headerText = "Today's Match";
        let headerClass = "text-dark";
        let liveIndicator = "";

        // Parse timing state
        if (!isPreGame && !isFinished) {
            let displayMin = status === 'HT' ? 'HT' : `${elapsed}'`;
            headerText = `LIVE: ${displayMin}`;
            headerClass = "text-success";
            liveIndicator = `<span class="live-dot" style="height: 10px; width: 10px; background-color: #20c997; border-radius: 50%; display: inline-block; margin-right: 8px; animation: livePulse 1.5s infinite;"></span>`;
        } else if (isFinished) {
            headerText = "Match Finished";
        } else {
            const dateObj = new Date(game.fixture.date);
            const timeString = dateObj.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).replace(' ', '');
            headerText = `${dateObj.toLocaleDateString([], { weekday: 'short' })} ${timeString}`;
        }

        // Determine Lineup Status & extract current Match Stats
        const { playerObj, status: lineupStatus, teamSide } = findPlayerInMatch(game, playerId);
        
        // Determine active team for the lineup link dynamically
        let activeTeamName = teamName; // Fallback to global club team
        if (teamSide && game.teams[teamSide]) {
            activeTeamName = game.teams[teamSide].name; // Perfect match: we know exactly which team they are on
        } else {
            // If they aren't in the lineup yet, check if the global team matched home or away
            if (game.teams.home.name === teamName) activeTeamName = game.teams.home.name;
            else if (game.teams.away.name === teamName) activeTeamName = game.teams.away.name;
        }
        
        const targetTeamSlug = getTeamSlug(activeTeamName);

        let hasLineupsAnnounced = (game.homeLineup?.startXI?.length > 0) || (game.awayLineup?.startXI?.length > 0);
        let finalStatus = lineupStatus;
        if (lineupStatus === 'not_in_squad' && !hasLineupsAnnounced) {
            finalStatus = 'pending';
        }

        let badgeClass = "bg-secondary";
        let badgeText = "Lineup Pending";

        if (finalStatus === 'on_pitch') {
            badgeClass = "bg-success";
            badgeText = isPreGame ? "In the Starting XI" : "On Field";
        } else if (finalStatus === 'subbed_out') {
            badgeClass = "bg-secondary text-white";
            badgeText = "Off Field";
        } else if (finalStatus === 'bench') {
            badgeClass = "bg-warning text-dark";
            badgeText = "Bench";
        } else if (finalStatus === 'not_in_squad') {
            badgeClass = "bg-danger";
            badgeText = "Not in Squad";
        }

        let playerStatsHtml = "";
        if (playerObj) {
            const ls = playerObj.live_stats || {};
            const posKey = playerObj.pos || 'M';
            const rating = ls.rating || playerObj.rating || "-";
            const mins = ls.minutes || 0;
            
            // Mirrors the positional logic from the main index dashboard
            const groups = {
                'F': { stats: ['G', 'A', 'SOT', 'SH'], keys: ['goals', 'assists', 'shots_on_target', 'total_shots'] },
                'M': { stats: ['G', 'A', 'KP', 'TK'], keys: ['goals', 'assists', 'key_passes', 'tackles'] },
                'D': { stats: ['G', 'A', 'TK', 'IN'], keys: ['goals', 'assists', 'tackles', 'interceptions'] },
                'G': { stats: ['SV', 'GC', 'PA', 'YC'], keys: ['saves', 'conceded', 'passes', 'yellow_cards'] }
            };
            
            const gConf = groups[posKey] || groups['M'];
            
            const v1 = ls[gConf.keys[0]] || 0;
            const v2 = ls[gConf.keys[1]] || 0;
            const v3 = ls[gConf.keys[2]] || 0;
            const v4 = ls[gConf.keys[3]] || 0;

            playerStatsHtml = `
                <div class="mt-2 d-flex justify-content-end">
                    <div class="d-flex align-items-center bg-light border rounded px-3 py-1 gap-3 shadow-sm">
                        <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">MIN</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">${mins}'</div></div>
                        <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">${gConf.stats[0]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">${v1}</div></div>
                        <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">${gConf.stats[1]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">${v2}</div></div>
                        <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">${gConf.stats[2]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">${v3}</div></div>
                        <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">${gConf.stats[3]}</div><div class="fw-bold text-dark" style="font-size: 0.85rem;">${v4}</div></div>
                        <div class="border-start" style="height: 20px;"></div>
                        <div class="text-center"><div class="text-muted" style="font-size: 0.55rem; font-weight: 700; letter-spacing: 0.5px;">RTG</div><div class="fw-bold text-success" style="font-size: 0.85rem;">${rating}</div></div>
                    </div>
                </div>
            `;
        }

        const scoreHtml = isPreGame 
            ? `<span class="mx-2 text-muted">vs</span>` 
            : `<span class="mx-3 fw-bold text-dark" style="font-size: 1.3rem;">${homeScore} - ${awayScore}</span>`;

        // Pre-calculate slugs for the scoreboard links
        const homeTeamSlug = getTeamSlug(game.teams.home.name);
        const awayTeamSlug = getTeamSlug(game.teams.away.name);

        // Render live interface mapping
        // ... (Keep the exact same code above that sets badgeClass, badgeText, playerStatsHtml, etc.)

    // Render live interface mapping into the main widget
    widget.innerHTML = `
        <div class="d-flex align-items-center justify-content-between flex-wrap gap-3" style="width: 100%;">
            <div class="d-flex flex-column align-items-start">
                <span class="fw-bold ${headerClass} mb-1" style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center;">
                    ${liveIndicator} ${headerText}
                </span>
                <div class="d-flex align-items-center" style="font-size: 1rem; font-weight: 700;">
                    <a href="/lineups/${homeTeamSlug}/" class="text-decoration-none text-dark" style="color: inherit;" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'">
                        <img src="${game.teams.home.logo}" width="18" height="18" class="me-1" style="object-fit:contain;">
                        ${game.teams.home.name} 
                    </a>
                    ${scoreHtml} 
                    <a href="/lineups/${awayTeamSlug}/" class="text-decoration-none text-dark" style="color: inherit;" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='inherit'">
                        <img src="${game.teams.away.logo}" width="18" height="18" class="me-1" style="object-fit:contain;">
                        ${game.teams.away.name}
                    </a>
                </div>
            </div>
            <div class="text-end">
                <div class="d-flex justify-content-end align-items-center gap-2">
                    <span class="badge ${badgeClass}">${badgeText}</span>
                    <a href="/lineups/${targetTeamSlug}/" class="text-decoration-none fw-bold" style="font-size: 0.7rem; color: #6c757d; transition: color 0.2s;" onmouseover="this.style.color='#20c997'" onmouseout="this.style.color='#6c757d'">View Lineup &rarr;</a>
                </div>
                ${playerStatsHtml}
            </div>
        </div>
    `;

    // 🎯 THE MOBILE HERO FIX: Target existing HTML without needing a rebuild
    const metaZone = document.querySelector('.sidebar-player-meta');
    
    // Check if we found the zone AND make sure we haven't already added the badge 
    if (metaZone && !document.getElementById('dynamic-hero-badge')) {
        const badgeDiv = document.createElement('div');
        badgeDiv.id = 'dynamic-hero-badge'; 
        badgeDiv.className = "mt-3 d-flex justify-content-center align-items-center gap-2";
        
        badgeDiv.innerHTML = `
            <span class="badge ${badgeClass} py-2 px-3 fw-bold shadow-sm" style="font-size: 0.85rem; border-radius: 6px;">
                ${badgeText.toUpperCase()}
            </span>
        `;
        
        // Append it directly to the bottom of the meta block
        metaZone.appendChild(badgeDiv);
        
    } else if (document.getElementById('dynamic-hero-badge')) {
        // If Firebase pushes a live update, just update the existing badge
        document.getElementById('dynamic-hero-badge').innerHTML = `
            <span class="badge ${badgeClass} py-2 px-3 fw-bold shadow-sm" style="font-size: 0.85rem; border-radius: 6px;">
                ${badgeText.toUpperCase()}
            </span>
        `;
    }

    if (liveIndicator !== "") {
        widget.style.borderLeft = "5px solid #20c997";
        widget.style.paddingLeft = "15px";
    } else {
        widget.style.removeProperty('border-left');
        widget.style.removeProperty('padding-left');
    }
}

    init();
});

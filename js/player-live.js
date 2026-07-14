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
    // SAFE MERGE LOGIC (Shields FT API Glitch)
    // ==========================================
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

    // Helper to scan starting XIs and substitutes for our player ID
    function findPlayerInMatch(match, targetId) {
        let playerObj = null;
        let status = 'not_in_squad'; // starting, bench, not_in_squad

        if (match.homeLineup) {
            const starter = match.homeLineup.startXI?.find(slot => slot.player.id == targetId);
            if (starter) {
                playerObj = starter.player;
                status = 'starting';
            } else {
                const sub = match.homeLineup.substitutes?.find(slot => slot.player.id == targetId);
                if (sub) {
                    playerObj = sub.player;
                    status = 'bench';
                }
            }
            // Safely parse mutated Python Live Engine arrays if subbed out
            if (!playerObj && match.homeLineup.startXI) {
                for (const slot of match.homeLineup.startXI) {
                    if (slot.sub_history) {
                        const subbedPlayer = slot.sub_history.find(h => h.id == targetId);
                        if (subbedPlayer) {
                            playerObj = subbedPlayer;
                            status = 'starting';
                            break;
                        }
                    }
                }
            }
        }

        if (!playerObj && match.awayLineup) {
            const starter = match.awayLineup.startXI?.find(slot => slot.player.id == targetId);
            if (starter) {
                playerObj = starter.player;
                status = 'starting';
            } else {
                const sub = match.awayLineup.substitutes?.find(slot => slot.player.id == targetId);
                if (sub) {
                    playerObj = sub.player;
                    status = 'bench';
                }
            }
            if (!playerObj && match.awayLineup.startXI) {
                for (const slot of match.awayLineup.startXI) {
                    if (slot.sub_history) {
                        const subbedPlayer = slot.sub_history.find(h => h.id == targetId);
                        if (subbedPlayer) {
                            playerObj = subbedPlayer;
                            status = 'starting';
                            break;
                        }
                    }
                }
            }
        }

        return { playerObj, status };
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
        const { playerObj, status: lineupStatus } = findPlayerInMatch(game, playerId);
        
        let hasLineupsAnnounced = (game.homeLineup?.startXI?.length > 0) || (game.awayLineup?.startXI?.length > 0);
        let finalStatus = lineupStatus;
        if (lineupStatus === 'not_in_squad' && !hasLineupsAnnounced) {
            finalStatus = 'pending';
        }

        let badgeClass = "bg-secondary";
        let badgeText = "Lineup Pending";

        if (finalStatus === 'starting') {
            badgeClass = "bg-success";
            badgeText = "Starting XI";
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

        // Render live interface mapping
        widget.innerHTML = `
            <div class="d-flex align-items-center justify-content-between flex-wrap gap-3" style="width: 100%;">
                <div class="d-flex flex-column align-items-start">
                    <span class="fw-bold ${headerClass} mb-1" style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.5px; display: flex; align-items: center;">
                        ${liveIndicator} ${headerText}
                    </span>
                    <div class="d-flex align-items-center" style="font-size: 1rem; font-weight: 700;">
                        <img src="${game.teams.home.logo}" width="18" height="18" class="me-1" style="object-fit:contain;">
                        ${game.teams.home.name} 
                        ${scoreHtml} 
                        <img src="${game.teams.away.logo}" width="18" height="18" class="me-1" style="object-fit:contain;">
                        ${game.teams.away.name}
                    </div>
                </div>
                <div class="text-end">
                    <span class="badge ${badgeClass}">${badgeText}</span>
                    ${playerStatsHtml}
                </div>
            </div>
        `;

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

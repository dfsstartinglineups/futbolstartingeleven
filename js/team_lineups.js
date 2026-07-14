let PLAYER_DATABASE = null;

document.addEventListener("DOMContentLoaded", async () => {
    const teamId = window.TARGET_TEAM_ID;
    if (!teamId) return;

    // 1. Get today's date in EST/EDT (YYYY-MM-DD) to match the Python scraper's logic
    const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
    
    // 2. Fetch both the daily games AND the player database using absolute root paths
    const dataUrl = `/data/games_${todayStr}.json`;
    const dbUrl = `/data/player_database.json`;

    try {
        // Fetch both files simultaneously for maximum speed
        const [gamesRes, dbRes] = await Promise.all([
            fetch(dataUrl),
            fetch(dbUrl)
        ]);

        if (dbRes.ok) {
            PLAYER_DATABASE = await dbRes.json();
        }

        if (!gamesRes.ok) throw new Error("No schedule file for today.");
        const games = await gamesRes.json();

        // 3. Find if our target team is playing today
        const match = games.find(g => 
            g.teams.home.id === teamId || g.teams.away.id === teamId
        );

        if (!match) {
            console.log(`Team ID ${teamId} is not playing today. Keeping placeholder.`);
            return; 
        }

        // 4. Determine if they are home or away, and grab their lineup
        const isHome = match.teams.home.id === teamId;
        const lineupData = isHome ? match.homeLineup : match.awayLineup;

        // 5. If the lineup is officially out (and shielded from the FT empty array glitch), render it!
        if (lineupData && Array.isArray(lineupData.startXI) && lineupData.startXI.length > 0) {
            renderTacticalBoard(lineupData);
        } else {
            console.log("Match found, but official starting XI is not published yet.");
        }

    } catch (err) {
        console.log("Awaiting match data:", err.message);
    }
});

// ==========================================
// TACTICAL BOARD RENDERING ENGINE
// ==========================================
function renderTacticalBoard(lineupData) {
    const container = document.getElementById('players-container');
    
    // Clear the "Awaiting Live Lineup Data" placeholder
    container.innerHTML = '';

    // Extract Team Hex Color (Fallback to white if missing)
    let teamColor = '#ffffff';
    if (lineupData.team && lineupData.team.colors && lineupData.team.colors.player && lineupData.team.colors.player.primary) {
        teamColor = `#${lineupData.team.colors.player.primary}`;
    }

    // Parse the formation (e.g., "4-3-3" or "4-2-3-1") and slice the players into rows
    const formationStr = lineupData.formation || "4-4-2"; 
    
    // 🎯 NEW: Inject the formation badge at the top of the pitch
    const formationBadgeHtml = `<div style="position: absolute; top: 15px; left: 50%; transform: translateX(-50%); background-color: rgba(0, 0, 0, 0.65); color: #fff; font-size: 0.85rem; font-weight: 700; padding: 4px 14px; border-radius: 20px; z-index: 1000; letter-spacing: 1px; border: 1px solid rgba(255,255,255,0.2); backdrop-filter: blur(2px);">FORMATION: ${formationStr}</div>`;
    container.insertAdjacentHTML('beforeend', formationBadgeHtml);

    const rows = sliceArrayByFormation(formationStr, lineupData.startXI);
    
    const numRows = rows.length;
    const yPositions = getYPositions(numRows); 

    // Draw each row
    rows.forEach((rowPlayers, rowIndex) => {
        if (!rowPlayers || rowPlayers.length === 0) return;
        
        const yPos = yPositions[rowIndex];
        const numPlayers = rowPlayers.length;
        const xPositions = getXPositions(numPlayers); 
        
        // Z-index ensures players lower on the pitch overlap players above them if screen gets squished
        const baseZIndex = 100 - rowIndex;

        rowPlayers.forEach((slot, colIndex) => {
            const p = slot.player;
            const xPos = xPositions[colIndex];

            // Clean up long names so they don't break the CSS plates
            let displayName = p.name;
            if (displayName.length > 16) {
                // Try to grab just the last name if it's super long (e.g. "Matheus Oliveira" -> "Oliveira")
                const parts = displayName.split(" ");
                displayName = parts.length > 1 ? parts[parts.length - 1] : displayName.substring(0, 14) + '...';
            }

            // 🎯 THE PHOTO FIX: Try live match image first, fallback to player database if empty
            let finalPhotoUrl = p.photo || '';
            if ((!finalPhotoUrl || !finalPhotoUrl.includes("http")) && PLAYER_DATABASE && PLAYER_DATABASE[p.id]) {
                // Adjust to match whatever property key name you use in player_database.json (e.g., .photo or .photo_url)
                finalPhotoUrl = PLAYER_DATABASE[p.id].photo || PLAYER_DATABASE[p.id].photo_url || '';
            }

            // Build the final player photo node element safely
            let photoHtml = `<div class="fallback-initials">${p.name.charAt(0).toUpperCase()}</div>`;
            if (finalPhotoUrl && finalPhotoUrl.includes("http")) {
                photoHtml = `<img src="${finalPhotoUrl}" class="player-photo" crossorigin="anonymous" alt="${p.name}">`;
            }

            // Sub Badge Logic (Adds a tiny green sub icon if the player was subbed in)
            let subBadgeHtml = '';
            if (p.isSubbedIn) {
                subBadgeHtml = `<div style="position: absolute; bottom: -5px; right: -5px; background: #198754; color: white; font-size: 10px; font-weight: bold; padding: 2px 4px; border-radius: 4px; border: 2px solid #000; z-index: 5;">↻ ${p.subMinute}'</div>`;
            }

            // 🎯 THE NEW DYNAMIC LINK INTEGRATION (Wraps entire Node Contents)
            let innerNodeHtml = `
                <div class="player-number">${p.number || ''}</div>
                <div class="player-photo-container">
                    ${photoHtml}
                    ${subBadgeHtml}
                </div>
                <div class="player-nameplate" style="transition: color 0.2s;">${displayName}</div>
            `;

            // If the player exists in the DB, wrap everything in an anchor tag
            if (PLAYER_DATABASE && PLAYER_DATABASE[p.id]) {
                const pSlug = PLAYER_DATABASE[p.id].slug;
                innerNodeHtml = `
                    <a href="/players/${pSlug}/" style="text-decoration: none; color: inherit; display: flex; flex-direction: column; align-items: center; cursor: pointer; width: 100%;" 
                       onmouseover="this.querySelector('.player-nameplate').style.color='#20c997'" 
                       onmouseout="this.querySelector('.player-nameplate').style.color=''">
                        ${innerNodeHtml}
                    </a>
                `;
            }

            // Construct the final Node HTML
            const nodeHtml = `
                <div class="player-node" style="left: ${xPos}%; top: ${yPos}%; z-index: ${baseZIndex}; --node-color: ${teamColor};">
                    ${innerNodeHtml}
                </div>
            `;
            
            container.insertAdjacentHTML('beforeend', nodeHtml);
        });
    });
}

// ==========================================
// GEOMETRY & MATH HELPERS
// ==========================================

// Slices the flat array of 11 players into rows based on the formation string
function sliceArrayByFormation(formationStr, startXI) {
    const parts = formationStr.split('-').map(Number);
    const rows = [];
    
    // Row 0 is ALWAYS the Goalkeeper
    rows.push([startXI[0]]); 
    
    let currentIndex = 1;
    for (let i = 0; i < parts.length; i++) {
        const count = parts[i];
        rows.push(startXI.slice(currentIndex, currentIndex + count));
        currentIndex += count;
    }
    return rows;
}

// Distributes the rows vertically from bottom (GK) to top (Strikers)
function getYPositions(numRows) {
    const bottomStart = 88; // GK sits at 88% down the pitch
    const topEnd = 14;      // Strikers sit at 14% down the pitch
    const step = (bottomStart - topEnd) / Math.max(1, numRows - 1);
    
    return Array.from({length: numRows}, (_, i) => bottomStart - (step * i));
}

// Distributes players evenly across the horizontal X-axis for a given row
function getXPositions(numPlayers) {
    if (numPlayers === 1) return [50];
    if (numPlayers === 2) return [32, 68]; 
    if (numPlayers === 3) return [20, 50, 80];
    if (numPlayers === 4) return [14, 38, 62, 86];
    if (numPlayers === 5) return [10, 30, 50, 70, 90];
    
    // Fallback math for weird formations (e.g., 6 midfielders)
    let positions = [];
    let step = 80 / (numPlayers - 1);
    for(let i = 0; i < numPlayers; i++) {
        positions.push(10 + (step * i));
    }
    return positions;
}

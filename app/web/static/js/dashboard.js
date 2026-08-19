// ═══════════════════════════════════════════════════════════════
// Odds Divergence Monitor — Real-Time Dashboard v2
// Premium UX: Filters, Toasts, Score Flash, Mute, Relative Time
// ═══════════════════════════════════════════════════════════════

// ── DOM References ──
const statusBadge = document.getElementById('conn-status');
const liveContainer = document.getElementById('live-matches-container');
const alertsContainer = document.getElementById('alerts-container');
const audioAlert = document.getElementById('alert-sound');
const targetLinkInput = document.getElementById('target-link');
const addLinkBtn = document.getElementById('add-link-btn');
const monitoredLinksList = document.getElementById('monitored-links-list');
const toastContainer = document.getElementById('toast-container');
const muteBtn = document.getElementById('mute-btn');
const muteIcon = document.getElementById('mute-icon');
const clearAlertsBtn = document.getElementById('clear-alerts-btn');
const alertBadge = document.getElementById('alert-badge');
const collapseLinksBtn = document.getElementById('collapse-links-btn');
const collapseIcon = document.getElementById('collapse-icon');
const linksPanelBody = document.getElementById('links-panel-body');
const toggleLinksPanel = document.getElementById('toggle-links-panel');

// ── Stat elements ──
const statBet365 = document.getElementById('stat-bet365');
const statBetburger = document.getElementById('stat-betburger');
const statBetano = document.getElementById('stat-betano');
const statPaired = document.getElementById('stat-paired');
const statAlertCount = document.getElementById('stat-alert-count');
const statClock = document.getElementById('stat-clock');

// ── State ──
let socket = null;
let alertHistory = [];
let currentFilter = 'all';
let isMuted = localStorage.getItem('odds_muted') === 'true';
let previousScores = {}; // { matchId: { bet365: {set,game,pts}, betburger: {set,game,pts} } }
let lastMatches = [];
const MAX_ALERTS = 50;
const MAX_TOASTS = 4;
const TOAST_DURATION = 6000;

// ── Sport Emoji Map ──
const SPORT_EMOJI = {
    tennis: '🎾', basketball: '🏀', tabletennis: '🏓', volleyball: '🏐',
    badminton: '🏸', icehockey: '🏒', soccer: '⚽', handball: '🤾',
    baseball: '⚾', esports: '🎮', cricket: '🏏', futsal: '⚽',
    beach_volley: '🏐', darts: '🎯', snooker: '🎱', unknown: '🏅',
};

function getSportEmoji(sport) {
    return SPORT_EMOJI[sport] || SPORT_EMOJI.unknown;
}

// ════════════════════════════════════════════
// MUTE TOGGLE
// ════════════════════════════════════════════
function updateMuteUI() {
    muteIcon.textContent = isMuted ? '🔇' : '🔔';
    muteBtn.classList.toggle('muted', isMuted);
}
updateMuteUI();

muteBtn.addEventListener('click', () => {
    isMuted = !isMuted;
    localStorage.setItem('odds_muted', isMuted);
    updateMuteUI();
});

// ════════════════════════════════════════════
// COLLAPSIBLE LINKS PANEL
// ════════════════════════════════════════════
let linksExpanded = false;

toggleLinksPanel.addEventListener('click', () => {
    linksExpanded = !linksExpanded;
    linksPanelBody.classList.toggle('collapsed', !linksExpanded);
    collapseIcon.textContent = linksExpanded ? '▴' : '▾';
});

// ════════════════════════════════════════════
// CONFIG (BETBURGER) PANEL
// ════════════════════════════════════════════
const toggleConfigPanel = document.getElementById('toggle-config-panel');
const configPanelBody = document.getElementById('config-panel-body');
const collapseConfigIcon = document.getElementById('collapse-config-icon');
const saveConfigBtn = document.getElementById('save-config-btn');
const bbEmailInput = document.getElementById('bb-email');
const bbPasswordInput = document.getElementById('bb-password');

let configExpanded = false;

toggleConfigPanel.addEventListener('click', () => {
    configExpanded = !configExpanded;
    configPanelBody.classList.toggle('collapsed', !configExpanded);
    collapseConfigIcon.textContent = configExpanded ? '▴' : '▾';
});

saveConfigBtn.addEventListener('click', async () => {
    const email = bbEmailInput.value.trim();
    const password = bbPasswordInput.value.trim();
    
    // We allow empty to "clear" the login
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const result = await response.json();
        if (result.status === 'ok') {
            showToast("Configuração Salva!", "As credenciais foram atualizadas. Reinicie o servidor no terminal para aplicá-las.", "info");
        }
    } catch (e) {
        console.error('Error saving config:', e);
        showToast("Erro", "Não foi possível salvar as configurações.", "error");
    }
});

// ════════════════════════════════════════════
// CONFIG (TELEGRAM) PANEL
// ════════════════════════════════════════════
const toggleTelegramPanel = document.getElementById('toggle-telegram-panel');
const telegramPanelBody = document.getElementById('telegram-panel-body');
const collapseTelegramIcon = document.getElementById('collapse-telegram-icon');
const saveTelegramBtn = document.getElementById('save-telegram-btn');
const tgTokenInput = document.getElementById('tg-token');
const tgChatIdInput = document.getElementById('tg-chat-id');

let telegramExpanded = false;

toggleTelegramPanel.addEventListener('click', () => {
    telegramExpanded = !telegramExpanded;
    telegramPanelBody.classList.toggle('collapsed', !telegramExpanded);
    collapseTelegramIcon.textContent = telegramExpanded ? '▴' : '▾';
});

saveTelegramBtn.addEventListener('click', async () => {
    const token = tgTokenInput.value.trim();
    const chat_id = tgChatIdInput.value.trim();
    
    try {
        const response = await fetch('/api/config/telegram', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token, chat_id })
        });
        const result = await response.json();
        if (result.status === 'ok') {
            showToast("Configuração Telegram Salva!", "Os dados do Telegram foram salvos com sucesso.", "info");
        } else {
            showToast("Erro", result.message || "Não foi possível salvar.", "error");
        }
    } catch (e) {
        console.error('Error saving telegram config:', e);
        showToast("Erro", "Não foi possível conectar à API.", "error");
    }
});

// ── Scraper Toggles Handler ──
const toggleScrapersPanel = document.getElementById('toggle-scrapers-panel');
const scrapersPanelBody = document.getElementById('scrapers-panel-body');
const collapseScrapersIcon = document.getElementById('collapse-scrapers-icon');
const saveScrapersBtn = document.getElementById('save-scrapers-btn');
const toggleBet365 = document.getElementById('toggle-bet365');
const toggleBetburger = document.getElementById('toggle-betburger');
const toggleBetano = document.getElementById('toggle-betano');
const freezeThresholdInput = document.getElementById('freeze-threshold-input');

let scrapersExpanded = true;

if (toggleScrapersPanel) {
    toggleScrapersPanel.addEventListener('click', () => {
        scrapersExpanded = !scrapersExpanded;
        scrapersPanelBody.classList.toggle('collapsed', !scrapersExpanded);
        collapseScrapersIcon.textContent = scrapersExpanded ? '▴' : '▾';
    });
}

if (saveScrapersBtn) {
    saveScrapersBtn.addEventListener('click', async () => {
        const enable_bet365 = toggleBet365.checked;
        const enable_betburger = toggleBetburger.checked;
        const enable_betano = toggleBetano.checked;
        const freeze_threshold_seconds = parseFloat(freezeThresholdInput ? freezeThresholdInput.value : 5.0) || 5.0;
        
        try {
            const response = await fetch('/api/config/scrapers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enable_bet365, enable_betburger, enable_betano, freeze_threshold_seconds })
            });
            const result = await response.json();
            if (result.status === 'ok') {
                showToast("Configuração Salva!", `Fontes salvas. Atraso mínimo: ${freeze_threshold_seconds}s.`, "info");
            } else {
                showToast("Erro", result.message || "Não foi possível salvar.", "error");
            }
        } catch (e) {
            console.error('Error saving scrapers config:', e);
            showToast("Erro", "Não foi possível conectar à API.", "error");
        }
    });
}

// Fetch current config on load
async function loadCurrentConfig() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        if (data.email) {
            bbEmailInput.value = data.email;
            bbPasswordInput.value = "********"; // placeholder
        }
        if (data.telegram_token) {
            tgTokenInput.value = data.telegram_token;
        }
        if (data.telegram_chat_id) {
            tgChatIdInput.value = data.telegram_chat_id;
        }
        if (data.enable_bet365 !== undefined && toggleBet365) toggleBet365.checked = data.enable_bet365;
        if (data.enable_betburger !== undefined && toggleBetburger) toggleBetburger.checked = data.enable_betburger;
        if (data.enable_betano !== undefined && toggleBetano) toggleBetano.checked = data.enable_betano;
        if (data.freeze_threshold_seconds !== undefined && freezeThresholdInput) freezeThresholdInput.value = data.freeze_threshold_seconds;
    } catch (e) {
        console.log("Could not load current config", e);
    }
}
loadCurrentConfig();

// ════════════════════════════════════════════
// FILTER SYSTEM
// ════════════════════════════════════════════
document.querySelectorAll('.filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
        document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        currentFilter = pill.dataset.filter;
        renderLiveMatches(lastMatches);
    });
});

// ════════════════════════════════════════════
// LINK MANAGEMENT
// ════════════════════════════════════════════
addLinkBtn.addEventListener('click', async () => {
    const url = targetLinkInput.value.trim();
    if (!url) return;
    try {
        const response = await fetch('/add-link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const result = await response.json();
        if (result.status === 'ok') {
            targetLinkInput.value = '';
            renderMonitoredLinks(result.links);
        }
    } catch (e) {
        console.error('Error adding link:', e);
    }
});

targetLinkInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') addLinkBtn.click();
});

async function removeLink(url) {
    try {
        const response = await fetch('/remove-link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const result = await response.json();
        if (result.status === 'ok') renderMonitoredLinks(result.links);
    } catch (e) {
        console.error('Error removing link:', e);
    }
}

// Make removeLink available globally for onclick handlers
window.removeLink = removeLink;

function renderMonitoredLinks(links) {
    if (!links || links.length === 0) {
        monitoredLinksList.innerHTML = '<span class="dim-text">Nenhum link personalizado adicionado.</span>';
        return;
    }
    monitoredLinksList.innerHTML = links.map(link => `
        <span class="link-badge">
            🔗 <a href="${link}" target="_blank" class="link-text">${link.substring(0, 50)}${link.length > 50 ? '...' : ''}</a>
            <button class="remove-link-btn" onclick="removeLink('${link.replace(/'/g, "\\'")}')">×</button>
        </span>
    `).join('');
}

async function loadMonitoredLinks() {
    try {
        const res = await fetch('/links');
        const data = await res.json();
        renderMonitoredLinks(data.links);
    } catch(e) {}
}
loadMonitoredLinks();

// ════════════════════════════════════════════
// WEBSOCKET CONNECTION
// ════════════════════════════════════════════
function connectWS() {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws`;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        statusBadge.innerHTML = '<span class="status-dot"></span> Conectado';
        statusBadge.className = 'status-badge status-online';
    };

    socket.onclose = () => {
        statusBadge.innerHTML = '<span class="status-dot"></span> Reconectando...';
        statusBadge.className = 'status-badge status-offline';
        setTimeout(connectWS, 3000);
    };

    socket.onerror = () => {
        statusBadge.innerHTML = '<span class="status-dot"></span> Erro';
        statusBadge.className = 'status-badge status-offline';
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'update') {
            lastMatches = data.matches || [];
            renderLiveMatches(lastMatches);
            if (data.stats) updateStats(data.stats);
            // Keep open alerts' scores in sync with live match feed (no freeze)
            syncAlertsFromMatches(lastMatches);
        } else if (data.type === 'alerts') {
            triggerAlerts(data.alerts || []);
        }
    };
}

/** Parse "H:A" → [h,a] */
function parsePair(s) {
    if (!s || s === '-' || s === '—') return [0, 0];
    const p = String(s).replace('-', ':').split(':');
    if (p.length < 2) return [0, 0];
    return [parseInt(p[0], 10) || 0, parseInt(p[1], 10) || 0];
}

/** Current set points unusable (0:0 / missing) — never treat as real delay. */
function isZeroedGame(src) {
    if (!src) return true;
    const [h, a] = parsePair(src.game_score);
    return h === 0 && a === 0;
}

/**
 * True if `other` is strictly ahead of Bet365 (Bet365 delayed).
 * Mirrors backend DivergenceDetector._is_source_ahead (simplified for UI).
 */
function isSourceAheadOfBet365(b365, other) {
    if (!b365 || !other) return false;
    if (other.game_score === '-' || other.set_score === '-') return false;
    // Zeroed scores are scrape noise / set-start — not a tradable delay
    if (isZeroedGame(b365) || isZeroedGame(other)) return false;

    const [bsH, bsA] = parsePair(b365.set_score);
    const [osH, osA] = parsePair(other.set_score);
    const [bgH, bgA] = parsePair(b365.game_score);
    const [ogH, ogA] = parsePair(other.game_score);
    const bSets = bsH + bsA;
    const oSets = osH + osA;
    const bGames = bgH + bgA;
    const oGames = ogH + ogA;
    const bMax = Math.max(bgH, bgA);
    const oMax = Math.max(ogH, ogA);

    // Other stuck on finished set, B365 already reset → B365 not delayed
    if (oSets === bSets && oMax >= 10 && bGames <= 3) return false;

    // Both still showing finished-set points with set-counter desync → not real delay
    if (oSets === bSets + 1 && oMax >= 10 && bMax >= 10 && Math.abs(oGames - bGames) <= 2) {
        return false;
    }

    // B365 finished set, other already on next set with low score → real delay
    if (oSets > bSets && bMax >= 10 && oGames <= 5) return true;

    // Other further in sets (only if not both mid/high same finished-looking scores)
    if (oSets > bSets) {
        if (oMax >= 10 && bMax >= 10 && Math.abs(oGames - bGames) <= 2) return false;
        return true;
    }
    if (oSets < bSets) return false;
    // Same sets: need more points in current set
    if (oGames > bGames) return true;
    return false;
}

/** Recompute leading houses from live source objects. */
function computeLeadingHouses(sources) {
    if (!sources || !sources.bet365) return [];
    const leading = [];
    if (sources.betburger && isSourceAheadOfBet365(sources.bet365, sources.betburger)) {
        leading.push('BetBurger');
    }
    if (sources.betano && isSourceAheadOfBet365(sources.bet365, sources.betano)) {
        leading.push('Betano');
    }
    return leading;
}

/**
 * Alert is only valid with 3 non-zero sources and BOTH secondaries ahead.
 * Mirrors backend strict rules so the UI never shows stale "à frente".
 */
function isAlertStillValidFromSources(sources) {
    if (!sources || !sources.bet365 || !sources.betburger || !sources.betano) return false;
    if (isZeroedGame(sources.bet365) || isZeroedGame(sources.betburger) || isZeroedGame(sources.betano)) {
        return false;
    }
    const leading = computeLeadingHouses(sources);
    return leading.includes('BetBurger') && leading.includes('Betano');
}

/** Parse "6:5 | Set 2" display string for zero check (fallback when no live match). */
function displayScoreIsZeroed(scoreStr) {
    if (!scoreStr || scoreStr === 'não encontrado') return true;
    const m = String(scoreStr).match(/^(\d+)\s*:\s*(\d+)/);
    if (!m) return true;
    return parseInt(m[1], 10) === 0 && parseInt(m[2], 10) === 0;
}

/** Format live source scores like the detector: "5:7 | Set 3" */
function formatScoreNow(src) {
    if (!src || (src.game_score === undefined && src.set_score === undefined)) {
        return 'não encontrado';
    }
    const game = String(src.game_score || '').trim();
    const sets = String(src.set_score || '').trim();
    if (!game && !sets) return 'não encontrado';
    const m = sets.match(/^(\d+):(\d+)$/);
    if (m) {
        const total = parseInt(m[1], 10) + parseInt(m[2], 10);
        const period = `Set ${total + 1}`;
        const main = game && game !== '0' && game !== '-' ? game : sets;
        return `${main} | ${period}`;
    }
    if (game && sets && sets !== '0:0' && sets !== '0' && sets !== '-') {
        return `${game} | ${sets}`;
    }
    return game || sets || 'não encontrado';
}

/** Push fresh scores from match list into alertHistory every cycle.
 *  CRITICAL: drop cards when live scores no longer form a real 3-way delay
 *  (prevents "0:0 | Set 4" with stale "à frente: BetBurger, Betano").
 */
function syncAlertsFromMatches(matches) {
    if (!alertHistory.length) return;
    const byId = new Map((matches || []).map(m => [m.id, m]));
    let changed = false;
    const kept = [];

    alertHistory.forEach(alert => {
        const key = alert.match_id || alert.id;
        const m = byId.get(key);

        if (m && m.sources) {
            const s = m.sources;
            const b365 = formatScoreNow(s.bet365);
            const burger = formatScoreNow(s.betburger);
            const betano = formatScoreNow(s.betano);
            if (s.bet365 && alert.bet365_score !== b365) { alert.bet365_score = b365; changed = true; }
            if (s.betburger && alert.betburger_score !== burger) { alert.betburger_score = burger; changed = true; }
            if (s.betano && alert.betano_score !== betano) { alert.betano_score = betano; changed = true; }

            // Always recompute leading from LIVE sources (never keep stale list)
            const leading = computeLeadingHouses(s);
            const prevLead = (alert.leading_houses || []).join(',');
            alert.leading_houses = leading;
            if (prevLead !== leading.join(',')) changed = true;

            if (m.bet365_link) alert.bet365_link = m.bet365_link;
            if (m.betburger_link) alert.betburger_link = m.betburger_link;
            if (m.betano_link) alert.betano_link = m.betano_link;

            // Resolved / invalid → remove immediately (no 5-min zombie card)
            if (!isAlertStillValidFromSources(s)) {
                changed = true;
                return; // drop
            }
            kept.push(alert);
            return;
        }

        // No live match row: drop if display scores are zeroed or equal (can't be a real delay)
        const z365 = displayScoreIsZeroed(alert.bet365_score);
        const zBB = displayScoreIsZeroed(alert.betburger_score);
        const zBt = displayScoreIsZeroed(alert.betano_score);
        if (z365 || zBB || zBt) {
            changed = true;
            return;
        }
        if (
            alert.bet365_score &&
            alert.bet365_score === alert.betburger_score &&
            alert.bet365_score === alert.betano_score
        ) {
            changed = true;
            return;
        }
        // Keep only briefly if match disappeared mid-alert
        if ((Date.now() - (alert._lastServerAt || alert._receivedAt || 0)) < 30000) {
            kept.push(alert);
        } else {
            changed = true;
        }
    });

    if (kept.length !== alertHistory.length) {
        alertHistory = kept;
        changed = true;
    }
    if (changed) {
        renderAlerts();
        updateAlertBadge();
    }
}

// ════════════════════════════════════════════
// STATS
// ════════════════════════════════════════════
function animateValue(el, newVal) {
    const current = el.textContent;
    if (current !== String(newVal)) {
        el.textContent = newVal;
        el.classList.add('flash');
        setTimeout(() => el.classList.remove('flash'), 600);
    }
}

function updateStats(stats) {
    const pairedCount = lastMatches.filter(m => {
        const s = m.sources || {};
        const count = (s.bet365 ? 1 : 0) + ((s['1xbet'] || s.betburger) ? 1 : 0) + (s.betano ? 1 : 0) + (s.novibet ? 1 : 0);
        return count >= 2;
    }).length;

    animateValue(statBet365, stats.bet365_count || 0);
    animateValue(statBetburger, stats.betburger_count || 0);
    animateValue(statBetano, stats.betano_count || 0);
    animateValue(statPaired, pairedCount);
    animateValue(statAlertCount, alertHistory.length);
    statClock.textContent = stats.timestamp || '--:--';
}

// ════════════════════════════════════════════
// LIVE MATCHES
// ════════════════════════════════════════════
function renderLiveMatches(matches) {
    if (!matches || matches.length === 0) {
        liveContainer.innerHTML = `
            <div class="placeholder-state">
                <div class="placeholder-icon">📡</div>
                <p>Aguardando dados reais dos scrapers...</p>
            </div>`;
        document.getElementById('filter-count').textContent = '';
        return;
    }

    // Classify each match
    const classified = matches.map(match => {
        const hasBet365 = !!match.sources.bet365;
        const hasBurger = !!match.sources.betburger;
        const hasBetano = !!match.sources.betano;
        const countSources = (hasBet365 ? 1 : 0) + (hasBurger ? 1 : 0) + (hasBetano ? 1 : 0);
        const isPaired = countSources >= 2;

        // STRICT: "divergent" = Bet365 atrasada (outra casa à frente), nunca B365 na frente/igual
        let isDivergent = false;
        if (isPaired && hasBet365) {
            const b365 = match.sources.bet365;
            const burger = match.sources.betburger;
            const betano = match.sources.betano;
            if (burger && isSourceAheadOfBet365(b365, burger)) isDivergent = true;
            if (betano && isSourceAheadOfBet365(b365, betano)) isDivergent = true;
        }

        return { ...match, isPaired, isDivergent, tier: isDivergent ? 0 : (isPaired ? 1 : 2) };
    });

    // Apply filter
    let filtered = classified;
    if (currentFilter === 'paired') filtered = classified.filter(m => m.isPaired);
    else if (currentFilter === 'divergent') filtered = classified.filter(m => m.isDivergent);

    // Update filter count
    const countEl = document.getElementById('filter-count');
    if (currentFilter !== 'all') {
        countEl.textContent = `Mostrando ${filtered.length} de ${matches.length}`;
    } else {
        countEl.textContent = `${matches.length} partidas`;
    }

    // Sort: divergent first, then paired, then solo
    filtered.sort((a, b) => a.tier - b.tier);

    // Group by sport
    const grouped = {};
    filtered.forEach(match => {
        const sport = match.sport || 'unknown';
        if (!grouped[sport]) grouped[sport] = [];
        grouped[sport].push(match);
    });

    // Sort sport groups: groups with divergent matches first
    const sortedSports = Object.entries(grouped).sort((a, b) => {
        const aHasDivergent = a[1].some(m => m.isDivergent);
        const bHasDivergent = b[1].some(m => m.isDivergent);
        if (aHasDivergent && !bHasDivergent) return -1;
        if (!aHasDivergent && bHasDivergent) return 1;
        return 0;
    });

    let html = '';
    for (const [sport, sportMatches] of sortedSports) {
        const emoji = getSportEmoji(sport);
        const divergentCount = sportMatches.filter(m => m.isDivergent).length;
        const divergentBadge = divergentCount > 0
            ? ` <span style="color: var(--accent-red); font-size: 10px;">⚡${divergentCount}</span>`
            : '';

        html += `<div class="sport-group">
            <div class="sport-header">${emoji} ${sport.toUpperCase()} <span class="match-count">(${sportMatches.length})</span>${divergentBadge}</div>`;

        sportMatches.forEach(match => {
            html += renderMatchCard(match);
        });
        html += '</div>';
    }

    liveContainer.innerHTML = html;

    // Apply score flash for changed scores
    applyScoreFlash(filtered);
}

function renderMatchCard(match) {
    const bet365 = match.sources.bet365 || { set_score: '-', game_score: '-', point_score: '-' };
    const burger = match.sources.betburger || { set_score: '-', game_score: '-', point_score: '-' };
    const betano = match.sources.betano || { set_score: '-', game_score: '-', point_score: '-' };

    const bet365Url = match.bet365_link || '#';
    const betburgerUrl = match.betburger_link || '#';
    const betanoUrl = match.betano_link || '#';
    const emoji = getSportEmoji(match.sport);

    const surebetPerc = burger.surebet_percentage ? parseFloat(burger.surebet_percentage) : 0;
    let percentageBadge = '';
    if (surebetPerc > 0) {
        percentageBadge = `<span class="surebet-badge">🔥 ${surebetPerc}%</span>`;
    }

    // Determine tier class
    let tierClass = 'match-solo';
    if (match.isDivergent) tierClass = 'match-divergent';
    else if (match.isPaired) tierClass = 'match-paired';

    // Solo match — compact view
    if (!match.isPaired) {
        const mainSource = match.sources.bet365 ? bet365 : (match.sources.betano ? betano : burger);
        const mainUrl = bet365Url !== '#' ? bet365Url : (betanoUrl !== '#' ? betanoUrl : betburgerUrl);
        const mainLabel = match.sources.bet365 ? 'B365' : (match.sources.betano ? 'BET' : 'BB');

        return `
            <div class="match-item match-solo" data-match-id="${match.id}">
                <div class="match-header">
                    <span class="match-name">${emoji} ${match.name}</span>
                    <span class="match-solo-score">
                        ${mainSource.set_score !== '0' && mainSource.set_score !== '-' ? mainSource.set_score + ' · ' : ''}${mainSource.game_score}
                    </span>
                    <div class="match-actions">
                        ${mainUrl !== '#' ? `<a href="${mainUrl}" target="_blank" class="action-btn bet365-btn">${mainLabel} ↗</a>` : ''}
                        ${betanoUrl !== '#' && mainLabel !== 'BET' ? `<a href="${betanoUrl}" target="_blank" class="action-btn" style="background:#ff5000; color:#fff;">BET ↗</a>` : ''}
                    </div>
                </div>
            </div>`;
    }

    // Paired / Divergent — full view
    const behindClass = match.isDivergent ? 'score-behind' : '';
    const aheadClass = match.isDivergent ? 'score-ahead' : '';

    return `
        <div class="match-item ${tierClass}" data-match-id="${match.id}">
            <div class="match-header">
                <span class="match-name">${emoji} ${match.name} ${percentageBadge}</span>
                <div class="match-actions">
                    ${bet365Url !== '#' ? `<a href="${bet365Url}" target="_blank" class="action-btn bet365-btn">B365 ↗</a><button class="action-btn" onclick="navigator.clipboard.writeText('${bet365Url}'); showToast('Copiado', 'Link copiado!', 'info')" title="Copiar Link Bet365">📋</button>` : '<span class="action-disabled">B365</span>'}
                    ${betburgerUrl !== '#' ? `<a href="${betburgerUrl}" target="_blank" class="action-btn betburger-btn">BB ↗</a>` : '<span class="action-disabled">BB</span>'}
                    ${betanoUrl !== '#' ? `<a href="${betanoUrl}" target="_blank" class="action-btn" style="background:#ff5000; color:#fff;">BET ↗</a>` : ''}
                </div>
            </div>
            <div class="scores-comparison" style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
                <div class="source-score ${behindClass}">
                    <div class="source-name" style="color: #27ae60; font-weight: bold;">BET365</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${match.id}_b365_set">${bet365.set_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${match.id}_b365_game">${bet365.game_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Pts</span> <strong data-score-key="${match.id}_b365_pts">${bet365.point_score}</strong>
                    </div>
                </div>
                <div class="source-score ${aheadClass}">
                    <div class="source-name" style="color: #2980b9; font-weight: bold;">BETBURGER</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${match.id}_bb_set">${burger.set_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${match.id}_bb_game">${burger.game_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Pts</span> <strong data-score-key="${match.id}_bb_pts">${burger.point_score}</strong>
                    </div>
                </div>
                <div class="source-score ${aheadClass}" style="border-left: 3px solid #ff5000;">
                    <div class="source-name" style="color: #ff5000; font-weight: bold;">BETANO</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${match.id}_betano_set">${betano.set_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${match.id}_betano_game">${betano.game_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Pts</span> <strong data-score-key="${match.id}_betano_pts">${betano.point_score}</strong>
                    </div>
                </div>
            </div>
        </div>`;
}

// ════════════════════════════════════════════
// SCORE FLASH — detect changes
// ════════════════════════════════════════════
function applyScoreFlash(matches) {
    const newScores = {};

    matches.forEach(match => {
        if (!match.isPaired) return;
        const b365 = match.sources.bet365 || {};
        const burger = match.sources.betburger || {};

        const key = match.id;
        newScores[key] = {
            b365_set: b365.set_score, b365_game: b365.game_score, b365_pts: b365.point_score,
            bb_set: burger.set_score, bb_game: burger.game_score, bb_pts: burger.point_score,
        };

        const prev = previousScores[key];
        if (prev) {
            for (const field of ['b365_set', 'b365_game', 'b365_pts', 'bb_set', 'bb_game', 'bb_pts']) {
                if (prev[field] !== newScores[key][field]) {
                    const scoreKey = `${key}_${field}`;
                    const el = document.querySelector(`[data-score-key="${scoreKey}"]`);
                    if (el) {
                        el.classList.remove('score-flash');
                        void el.offsetWidth; // Force reflow
                        el.classList.add('score-flash');
                    }
                }
            }
        }
    });

    previousScores = newScores;
}

// ════════════════════════════════════════════
// ALERTS
// ════════════════════════════════════════════
function triggerAlerts(activeAlerts) {
    if (!activeAlerts) activeAlerts = [];
    const now = Date.now();
    // Keep card only while STILL a valid active divergence (server + local checks).
    // Do NOT keep 5-min zombies with equal/zero scores and stale "à frente".
    const RESOLVED_GRACE_MS = 20 * 1000;

    const existingMap = new Map();
    alertHistory.forEach(a => existingMap.set(a.match_id || a.id, a));

    let hasNew = false;
    const activeKeys = new Set();

    activeAlerts.forEach(alert => {
        // Client-side reject: zeros or incomplete leading
        const scoresZero =
            displayScoreIsZeroed(alert.bet365_score) ||
            displayScoreIsZeroed(alert.betburger_score) ||
            displayScoreIsZeroed(alert.betano_score);
        const lead = alert.leading_houses || [];
        if (scoresZero || !lead.includes('BetBurger') || !lead.includes('Betano')) {
            return; // ignore invalid server payload
        }

        const key = alert.match_id || alert.id;
        activeKeys.add(key);
        if (alert.league && /principal|partida/i.test(alert.league) && alert.league.length < 48) {
            alert.league = '';
        }
        const existing = existingMap.get(key);
        if (existing) {
            existing.bet365_score = alert.bet365_score;
            existing.betburger_score = alert.betburger_score;
            existing.betano_score = alert.betano_score;
            existing.novibet_score = alert.novibet_score || existing.novibet_score;
            if (alert.league) existing.league = alert.league;
            existing.leading_houses = alert.leading_houses || [];
            existing.is_update = true;
            existing._lastServerAt = now;
            existing._active = true;
            existing.bet365_link = alert.bet365_link || existing.bet365_link;
            existing.betburger_link = alert.betburger_link || existing.betburger_link;
            existing.betano_link = alert.betano_link || existing.betano_link;
            existingMap.set(key, existing);
            if (alert.notify && alert.scores_changed && !isMuted) {
                showToast(alert);
                hasNew = true;
            }
        } else {
            alert._receivedAt = now;
            alert._lastServerAt = now;
            alert._active = true;
            alert.is_update = false;
            existingMap.set(key, alert);
            if (alert.notify !== false) {
                hasNew = true;
                showToast(alert);
            }
        }
    });

    // Keep only: still on server active list, OR <20s grace after last active tick
    const updatedHistory = Array.from(existingMap.values()).filter(alert => {
        const key = alert.match_id || alert.id;
        if (activeKeys.has(key)) return true;
        // Resolved: drop after short grace (do not keep 5 min of false "à frente")
        const last = alert._lastServerAt || alert._receivedAt || 0;
        return (now - last) < RESOLVED_GRACE_MS;
    });

    updatedHistory.sort((a, b) => (b._receivedAt || 0) - (a._receivedAt || 0));
    alertHistory = updatedHistory;

    if (hasNew && !isMuted) {
        try {
            audioAlert.currentTime = 0;
            audioAlert.play();
        } catch (e) {
            console.log('Audio play blocked by browser autoplay policy.');
        }
    }

    renderAlerts();
    updateAlertBadge();
}

function renderAlerts() {
    if (alertHistory.length === 0) {
        alertsContainer.innerHTML = `
            <div class="placeholder-state">
                <div class="placeholder-icon">🛡️</div>
                <p>Nenhuma divergência detectada.</p>
            </div>`;
        return;
    }

    alertsContainer.innerHTML = alertHistory.map(alert => {
        const priority = alert.priority || 'HIGH';
        const prioClass = priority === 'GOLDEN' ? 'priority-golden' :
                         priority === 'CRITICAL' ? 'priority-critical' :
                         priority === 'HIGH' ? 'priority-high' : 'priority-medium';

        const bet365Url = alert.bet365_link || '#';
        const betburgerUrl = alert.betburger_link || '#';
        const matchName = (alert.match_name || alert.name || 'Partida Desconhecida')
            .replace(/\s+vs\s+/gi, ' x ');
        // Never invent league — only show if scraped
        const league = (alert.league || '').trim();
        const leagueLine = league ? `🏆 ${league}\n` : '';
        const emoji = getSportEmoji(alert.sport);
        const relTime = alert._receivedAt ? getRelativeTime(alert._receivedAt) : (alert.timestamp || '');
        const title = alert.is_update ? '🔄 ATUALIZAÇÃO DA DIVERGÊNCIA' : '🚨 NOVA DIVERGÊNCIA DETECTADA';
        const b365Now = alert.bet365_score || 'não encontrado';
        const betanoNow = alert.betano_score || 'não encontrado';
        const novibetNow = alert.novibet_score || 'não encontrado';
        const burgerNow = alert.betburger_score || 'não encontrado';
        const leading = (alert.leading_houses && alert.leading_houses.length)
            ? alert.leading_houses.join(', ')
            : '';
        const leadingLine = leading ? `\n🔺 À frente da casa alvo: ${leading}` : '';

        // Exact format requested by user — real values only
        return `
            <div class="alert-item ${prioClass}">
                <div class="alert-header">
                    <span>${title}</span>
                    <span class="alert-timestamp">${relTime}</span>
                </div>
                <div class="alert-match-name" style="line-height:1.55; white-space:pre-line; font-size:13px;">
🎯 ENTRADA PARA BET365
${leagueLine}${emoji} ${matchName}

Bet365 agora: ${b365Now}
Betano agora: ${betanoNow}
Novibet agora: ${novibetNow}
BetBurger agora: ${burgerNow}
${leadingLine}
                </div>
                <div class="alert-actions">
                    ${renderBet365OpenButton(alert)}
                    ${betburgerUrl !== '#' && betburgerUrl ? `<a href="${betburgerUrl}" target="_blank" class="action-btn betburger-btn" style="margin-left:8px;">BetBurger ↗</a>` : ''}
                    ${isValidBetanoEventLink(alert.betano_link) ? `<a href="${alert.betano_link}" target="_blank" rel="noopener" class="action-btn" style="background:#ff5000; color:#fff; margin-left:8px;">Betano ↗</a>` : ''}
                </div>
            </div>`;
    }).join('');
}

/** True if URL has a real Bet365 event id (EV…), not just #/IP/B92 listing */
function isValidBet365EventLink(url) {
    if (!url || typeof url !== 'string') return false;
    return /EV\d{6,}/i.test(url);
}

function renderBet365OpenButton(alert) {
    const name = (alert.match_name || alert.name || '').replace(/'/g, "\\'");
    const id = (alert.match_id || '').replace(/'/g, "\\'");
    const url = alert.bet365_link || '';
    // Always open via API so we click the correct fixture in the Bet365 Chrome
    return `<button type="button" class="alert-cta-bet365" onclick="openBet365Match('${id}','${name}')" style="cursor:pointer;border:none;">⚡ ABRIR BET365</button>` +
        (isValidBet365EventLink(url)
            ? `<button type="button" class="action-btn betburger-btn" onclick="navigator.clipboard.writeText('${url.replace(/'/g, "\\'")}');" style="margin-left:8px;">📋 COPIAR</button>`
            : `<button type="button" class="action-btn betburger-btn" onclick="navigator.clipboard.writeText('${name}');" style="margin-left:8px;" title="Copia o nome do jogo">📋 NOME</button>`);
}

async function openBet365Match(matchId, matchName) {
    try {
        const res = await fetch('/api/open-bet365', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ match_id: matchId || '', match_name: matchName || '' })
        });
        const data = await res.json();
        if (data.status === 'ok' && data.mode === 'external' && data.url) {
            window.open(data.url, '_blank');
            return;
        }
        if (data.status === 'ok') {
            // Focused in scraper Chrome — brief feedback
            if (typeof showToast === 'function') {
                try { showToast({ match_name: matchName, sport: 'tabletennis', priority: 'HIGH', betburger_score: 'Chrome Bet365', bet365_score: 'focado' }); } catch (e) {}
            }
            console.log('[Bet365]', data.message || 'Aberto no Chrome do scraper');
            return;
        }
        // Fallback: open TT listing so user can pick manually
        const listing = data.listing_url || 'https://www.bet365.bet.br/#/IP/B92';
        window.open(listing, '_blank');
        console.warn('[Bet365] open failed:', data.message);
    } catch (e) {
        console.error(e);
        window.open('https://www.bet365.bet.br/#/IP/B92', '_blank');
    }
}

/** Only allow Betano event deep links (…/live/slug/12345/), never hub/sport pages */
function isValidBetanoEventLink(url) {
    if (!url || typeof url !== 'string') return false;
    try {
        const u = new URL(url, 'https://www.betano.bet.br');
        if (!/betano\.bet\.br$/i.test(u.hostname.replace(/^www\./, 'www.')) && !/betano\.bet\.br$/i.test(u.hostname)) {
            // allow www.betano.bet.br
            if (!u.hostname.includes('betano.bet.br')) return false;
        }
        return /\/live\/.+\/\d{5,}\/?$/i.test(u.pathname) || /\/\d{5,}\/?$/i.test(u.pathname);
    } catch (e) {
        return false;
    }
}

function updateAlertBadge() {
    if (alertHistory.length > 0) {
        alertBadge.textContent = alertHistory.length;
        alertBadge.classList.remove('hidden');
    } else {
        alertBadge.classList.add('hidden');
    }
    animateValue(statAlertCount, alertHistory.length);
}

// Clear alerts
clearAlertsBtn.addEventListener('click', () => {
    alertHistory = [];
    renderAlerts();
    updateAlertBadge();
});

// ════════════════════════════════════════════
// TOAST NOTIFICATIONS
// ════════════════════════════════════════════
function showToast(alert) {
    // Limit max toasts
    const currentToasts = toastContainer.querySelectorAll('.toast:not(.toast-out)');
    if (currentToasts.length >= MAX_TOASTS) {
        const oldest = currentToasts[currentToasts.length - 1];
        dismissToast(oldest);
    }

    const emoji = getSportEmoji(alert.sport);
    const matchName = alert.match_name || alert.name || 'Partida';
    const priority = alert.priority || 'HIGH';

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `
        <div class="toast-title">⚡ ${priority} — ${alert.sport ? alert.sport.toUpperCase() : 'DIVERGÊNCIA'}</div>
        <div class="toast-body">${emoji} ${matchName}</div>
        <div class="toast-sub">BB: ${alert.betburger_score || '-'} vs B365: ${alert.bet365_score || '-'}${alert.freeze_seconds > 0 ? ' · 🧊 ' + alert.freeze_seconds + 's' : ''}</div>
    `;

    toast.addEventListener('click', () => dismissToast(toast));
    toastContainer.prepend(toast);

    // Auto-dismiss after duration
    setTimeout(() => dismissToast(toast), TOAST_DURATION);
}

function dismissToast(toast) {
    if (!toast || toast.classList.contains('toast-out')) return;
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 350);
}

// ════════════════════════════════════════════
// RELATIVE TIME
// ════════════════════════════════════════════
function getRelativeTime(timestamp) {
    const diff = Math.floor((Date.now() - timestamp) / 1000);
    if (diff < 5) return 'agora mesmo';
    if (diff < 60) return `há ${diff}s`;
    if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `há ${Math.floor(diff / 3600)}h`;
    return `há ${Math.floor(diff / 86400)}d`;
}

// Update relative times every 30 seconds
setInterval(() => {
    if (alertHistory.length > 0) renderAlerts();
}, 30000);

// ════════════════════════════════════════════
// PICTURE-IN-PICTURE (FLOAT WINDOW)
// ════════════════════════════════════════════
if (window.electronAPI) {
    const pipBtn = document.getElementById('pip-btn');
    const pipIcon = document.getElementById('pip-icon');
    
    if (pipBtn) {
        pipBtn.addEventListener('click', () => {
            window.electronAPI.togglePiP();
        });
    }
    
    window.electronAPI.onPiPStatus((isPiP) => {
        if (isPiP) {
            document.body.classList.add('pip-mode');
            if (pipBtn) pipBtn.title = "Voltar ao Modo Normal";
            if (pipIcon) pipIcon.textContent = "🗗";
        } else {
            document.body.classList.remove('pip-mode');
            if (pipBtn) pipBtn.title = "Modo Compacto / Suspenso";
            if (pipIcon) pipIcon.textContent = "🗖";
        }
        // Redesenha para ajustar qualquer detalhe específico
        if (alertHistory.length > 0) renderAlerts();
    });
} else {
    // Esconde o botão se não estiver rodando no Electron
    const pipBtn = document.getElementById('pip-btn');
    if (pipBtn) pipBtn.style.display = 'none';
}

// ════════════════════════════════════════════
// INITIAL CONNECTION
// ════════════════════════════════════════════
connectWS();

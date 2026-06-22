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

// Fetch current config on load
async function loadCurrentConfig() {
    try {
        const res = await fetch('/api/config');
        const data = await res.json();
        if (data.email) {
            bbEmailInput.value = data.email;
            bbPasswordInput.value = "********"; // placeholder
        }
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
        } else if (data.type === 'alerts') {
            triggerAlerts(data.alerts || []);
        }
    };
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
    const pairedCount = lastMatches.filter(m => m.sources.bet365 && m.sources.betburger).length;

    animateValue(statBet365, stats.bet365_count || 0);
    animateValue(statBetburger, stats.betburger_count || 0);
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
        const isPaired = hasBet365 && hasBurger;

        let isDivergent = false;
        if (isPaired) {
            const b365 = match.sources.bet365;
            const burger = match.sources.betburger;
            const surebetPerc = burger.surebet_percentage ? parseFloat(burger.surebet_percentage) : 0;

            if (surebetPerc >= 1.0) isDivergent = true;
            else if (b365.game_score !== '-' && burger.game_score !== '-' && b365.game_score !== burger.game_score) {
                isDivergent = true;
            }
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

    const bet365Url = match.bet365_link || '#';
    const betburgerUrl = match.betburger_link || '#';
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
        return `
            <div class="match-item match-solo" data-match-id="${match.id}">
                <div class="match-header">
                    <span class="match-name">${emoji} ${match.name}</span>
                    <span class="match-solo-score">
                        ${bet365.set_score !== '0' ? bet365.set_score + ' · ' : ''}${bet365.game_score}
                    </span>
                    <div class="match-actions">
                        ${bet365Url !== '#' ? `<a href="${bet365Url}" target="_blank" class="action-btn bet365-btn">B365 ↗</a>` : ''}
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
                </div>
            </div>
            <div class="scores-comparison">
                <div class="source-score ${behindClass}">
                    <div class="source-name">BET365</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${match.id}_b365_set">${bet365.set_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${match.id}_b365_game">${bet365.game_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Pts</span> <strong data-score-key="${match.id}_b365_pts">${bet365.point_score}</strong>
                    </div>
                </div>
                <div class="source-score ${aheadClass}">
                    <div class="source-name">BETBURGER</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${match.id}_bb_set">${burger.set_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${match.id}_bb_game">${burger.game_score}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Pts</span> <strong data-score-key="${match.id}_bb_pts">${burger.point_score}</strong>
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

    // Map existing alerts by match_id to preserve their _receivedAt timestamp
    const existingAlertsMap = {};
    alertHistory.forEach(a => existingAlertsMap[a.match_id] = a);

    let hasNew = false;
    const newHistory = [];

    activeAlerts.forEach(alert => {
        const existing = existingAlertsMap[alert.match_id];
        if (existing) {
            alert._receivedAt = existing._receivedAt; // Preserve original time
            newHistory.push(alert);
        } else {
            alert._receivedAt = Date.now();
            newHistory.push(alert);
            hasNew = true;
            showToast(alert); // Show toast only for brand new alerts
        }
    });

    alertHistory = newHistory;

    // Play sound ONLY if there are NEW alerts (if not muted)
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
        const emoji = getSportEmoji(alert.sport);
        const priority = alert.priority || 'HIGH';
        const prioClass = priority === 'CRITICAL' ? 'priority-critical' :
                         priority === 'HIGH' ? 'priority-high' : 'priority-medium';

        const bet365Url = alert.bet365_link || '#';
        const betburgerUrl = alert.betburger_link || '#';
        const matchName = alert.match_name || alert.name || 'Partida Desconhecida';
        const messageHtml = alert.message ? `<div class="alert-message">${alert.message}</div>` : '';

        // Relative time
        const relTime = alert._receivedAt ? getRelativeTime(alert._receivedAt) : (alert.timestamp || '');

        const freezeHtml = alert.freeze_seconds > 0
            ? `<span class="alert-freeze">🧊 ${alert.freeze_seconds}s congelado</span>`
            : '';

        // Game diff badge
        const gameDiff = alert.game_diff || 0;
        const diffBadge = gameDiff > 0
            ? `<span class="alert-diff-badge">Δ ${gameDiff} game${gameDiff > 1 ? 's' : ''}</span>`
            : '';

        // Triangulation badge
        const triangulatedBadge = alert.is_triangulated 
            ? `<div style="background: #27ae60; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold; margin-bottom: 8px; display: inline-block;">🎯 1XBET CONFIRMOU A VANTAGEM!</div>`
            : '';

        const xbetScoreHtml = alert.is_triangulated
            ? `<div class="alert-source alert-source-ahead" style="border-left: 3px solid #27ae60; margin-top: 8px;">
                   <div class="alert-source-label">1XBET <span class="alert-arrow" style="color: #27ae60;">▲ confirmou</span></div>
                   <div class="alert-source-score">${alert.xbet_score || '-'}</div>
               </div>`
            : '';

        return `
            <div class="alert-item ${prioClass}">
                <div class="alert-header">
                    <span>🚨 DIVERGÊNCIA ${alert.sport ? '[' + alert.sport.toUpperCase() + ']' : ''}</span>
                    <span class="badge-${priority.toLowerCase()}">${priority}</span>
                </div>
                ${triangulatedBadge}
                <div class="alert-match-name">${emoji} ${matchName} ${diffBadge}</div>
                ${messageHtml}
                <div class="alert-scores-grid">
                    <div class="alert-source alert-source-ahead">
                        <div class="alert-source-label">BETBURGER <span class="alert-arrow">▲ à frente</span></div>
                        <div class="alert-source-score">${alert.betburger_score || '-'}</div>
                        <div class="alert-source-pts">${alert.betburger_points && alert.betburger_points !== '0' ? 'Pts: ' + alert.betburger_points : ''}</div>
                    </div>
                    <div class="alert-vs">≠</div>
                    <div class="alert-source alert-source-behind">
                        <div class="alert-source-label">BET365 <span class="alert-arrow-behind">▼ atrasado</span></div>
                        <div class="alert-source-score">${alert.bet365_score || '-'}</div>
                        <div class="alert-source-pts">${alert.bet365_points && alert.bet365_points !== '0' ? 'Pts: ' + alert.bet365_points : ''}</div>
                    </div>
                </div>
                ${xbetScoreHtml}
                <div class="alert-meta">
                    ${freezeHtml}
                    <span class="alert-timestamp">${relTime}</span>
                </div>
                <div class="alert-actions">
                    ${bet365Url !== '#' ? `<a href="${bet365Url}" target="_blank" class="alert-cta-bet365">⚡ ABRIR (NAVEGADOR PADRÃO) ↗</a><button class="action-btn betburger-btn" onclick="navigator.clipboard.writeText('${bet365Url}'); showToast('Copiado', 'Link da Bet365 copiado!', 'info');" style="margin-left:8px;">📋 COPIAR</button>` : '<span class="alert-cta-disabled">Sem link Bet365</span>'}
                    ${betburgerUrl !== '#' ? `<a href="${betburgerUrl}" target="_blank" class="action-btn betburger-btn" style="margin-left:8px;">BetBurger ↗</a>` : ''}
                </div>
            </div>
        `;
    }).join('');
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
// INITIAL CONNECTION
// ════════════════════════════════════════════
connectWS();

// ═══════════════════════════════════════════════════════════════
// Odds Divergence Monitor — Real-Time Dashboard v3.0 (Optimized)
// High-Performance In-Place DOM Reconciliation & XSS-Safe Sanitization
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
let reconnectTimer = null;
let reconnectAttempts = 0;
let alertHistory = [];
let currentFilter = 'all';
let isMuted = localStorage.getItem('odds_muted') === 'true';
let previousScores = {}; // { matchId: { b365_set, b365_game, ... } }
let lastMatches = [];
let audioUnlocked = false;

const MAX_ALERTS = 50;
const MAX_TOASTS = 4;
const TOAST_DURATION = 5000;

// ── Sanitization Helper (XSS Protection) ──
function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function sanitizeUrl(url) {
    if (!url || typeof url !== 'string') return '#';
    const trimmed = url.trim();
    if (trimmed.startsWith('https://') || trimmed.startsWith('http://') || trimmed.startsWith('/')) {
        return escapeHTML(trimmed);
    }
    return '#';
}

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
// WEB AUDIO API SYNTHESIZER (0ms I/O procedural audio)
// ════════════════════════════════════════════
class AlertSynthesizer {
    constructor() {
        this.ctx = null;
        this.isUnlocked = false;
        this._initOnGesture();
    }

    _initOnGesture() {
        const unlock = () => {
            if (!this.ctx) {
                const AudioCtx = window.AudioContext || window.webkitAudioContext;
                if (AudioCtx) this.ctx = new AudioCtx({ latencyHint: 'interactive' });
            }
            if (this.ctx && this.ctx.state === 'suspended') {
                this.ctx.resume();
            }
            this.isUnlocked = true;
            ['click', 'keydown', 'touchstart'].forEach(e => 
                document.removeEventListener(e, unlock)
            );
        };
        ['click', 'keydown', 'touchstart'].forEach(e => 
            document.addEventListener(e, unlock, { passive: true })
        );
    }

    playAlert(priority = 'HIGH') {
        if (!this.ctx || this.ctx.state === 'suspended') return;
        try {
            const now = this.ctx.currentTime;
            const gainNode = this.ctx.createGain();
            gainNode.connect(this.ctx.destination);

            const frequencies = priority === 'CRITICAL' 
                ? [1760, 2200, 2640] // A6, C#7, E7
                : [880, 1320];       // A5, E6

            gainNode.gain.setValueAtTime(0.0, now);
            gainNode.gain.linearRampToValueAtTime(0.35, now + 0.015);
            gainNode.gain.exponentialRampToValueAtTime(0.001, now + 0.25);

            frequencies.forEach(freq => {
                const osc = this.ctx.createOscillator();
                osc.type = priority === 'CRITICAL' ? 'triangle' : 'sine';
                osc.frequency.setValueAtTime(freq, now);
                osc.connect(gainNode);
                osc.start(now);
                osc.stop(now + 0.26);
            });
        } catch (e) {}
    }
}

const alertSynth = new AlertSynthesizer();

// ════════════════════════════════════════════
// MUTE TOGGLE
// ════════════════════════════════════════════
function updateMuteUI() {
    if (muteIcon) muteIcon.textContent = isMuted ? '🔇' : '🔔';
    if (muteBtn) muteBtn.classList.toggle('muted', isMuted);
}
updateMuteUI();

if (muteBtn) {
    muteBtn.addEventListener('click', () => {
        isMuted = !isMuted;
        localStorage.setItem('odds_muted', isMuted);
        updateMuteUI();
    });
}

// ════════════════════════════════════════════
// COLLAPSIBLE LINKS PANEL
// ════════════════════════════════════════════
let linksExpanded = false;
if (toggleLinksPanel && linksPanelBody && collapseIcon) {
    toggleLinksPanel.addEventListener('click', () => {
        linksExpanded = !linksExpanded;
        linksPanelBody.classList.toggle('collapsed', !linksExpanded);
        collapseIcon.textContent = linksExpanded ? '▴' : '▾';
    });
}

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
if (toggleConfigPanel && configPanelBody && collapseConfigIcon) {
    toggleConfigPanel.addEventListener('click', () => {
        configExpanded = !configExpanded;
        configPanelBody.classList.toggle('collapsed', !configExpanded);
        collapseConfigIcon.textContent = configExpanded ? '▴' : '▾';
    });
}

if (saveConfigBtn && bbEmailInput && bbPasswordInput) {
    saveConfigBtn.addEventListener('click', async () => {
        const email = bbEmailInput.value.trim();
        const password = bbPasswordInput.value.trim();
        
        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });
            const result = await response.json();
            if (result.status === 'ok') {
                showToast("Configuração Salva!", "As credenciais do BetBurger foram atualizadas.", "info");
            }
        } catch (e) {
            console.error('Error saving config:', e);
            showToast("Erro", "Não foi possível salvar as configurações.", "error");
        }
    });
}

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
if (toggleTelegramPanel && telegramPanelBody && collapseTelegramIcon) {
    toggleTelegramPanel.addEventListener('click', () => {
        telegramExpanded = !telegramExpanded;
        telegramPanelBody.classList.toggle('collapsed', !telegramExpanded);
        collapseTelegramIcon.textContent = telegramExpanded ? '▴' : '▾';
    });
}

if (saveTelegramBtn && tgTokenInput && tgChatIdInput) {
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
                showToast("Telegram Salvo!", "Os dados do Telegram foram salvos com sucesso.", "info");
            } else {
                showToast("Erro", result.message || "Não foi possível salvar.", "error");
            }
        } catch (e) {
            console.error('Error saving telegram config:', e);
            showToast("Erro", "Não foi possível conectar à API.", "error");
        }
    });
}

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
if (toggleScrapersPanel && scrapersPanelBody && collapseScrapersIcon) {
    toggleScrapersPanel.addEventListener('click', () => {
        scrapersExpanded = !scrapersExpanded;
        scrapersPanelBody.classList.toggle('collapsed', !scrapersExpanded);
        collapseScrapersIcon.textContent = scrapersExpanded ? '▴' : '▾';
    });
}

if (saveScrapersBtn) {
    saveScrapersBtn.addEventListener('click', async () => {
        const enable_bet365 = toggleBet365 ? toggleBet365.checked : true;
        const enable_betburger = toggleBetburger ? toggleBetburger.checked : true;
        const enable_betano = toggleBetano ? toggleBetano.checked : true;
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

// ════════════════════════════════════════════
// MONITORED LINKS
// ════════════════════════════════════════════
if (addLinkBtn && targetLinkInput) {
    addLinkBtn.addEventListener('click', async () => {
        const url = targetLinkInput.value.trim();
        if (!url) return;
        try {
            const res = await fetch('/add-link', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });
            const data = await res.json();
            renderMonitoredLinks(data.links);
            targetLinkInput.value = '';
            showToast("Link Adicionado", "O link foi adicionado à lista.", "info");
        } catch(e) {
            showToast("Erro", "Falha ao adicionar link.", "error");
        }
    });
}

async function removeLink(url) {
    try {
        const res = await fetch('/remove-link', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await res.json();
        renderMonitoredLinks(data.links);
    } catch(e) {}
}

function renderMonitoredLinks(links) {
    if (!monitoredLinksList) return;
    if (!links || links.length === 0) {
        monitoredLinksList.innerHTML = '<span class="empty-hint">Nenhum link adicionado ainda</span>';
        return;
    }
    monitoredLinksList.innerHTML = links.map(link => {
        const safeLink = sanitizeUrl(link);
        const displayLink = escapeHTML(link.length > 50 ? link.substring(0, 50) + '...' : link);
        return `
            <div class="monitored-link-item">
                <a href="${safeLink}" target="_blank" rel="noopener">${displayLink}</a>
                <button type="button" class="remove-link-btn" data-link="${escapeHTML(link)}">×</button>
            </div>
        `;
    }).join('');

    monitoredLinksList.querySelectorAll('.remove-link-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const link = e.currentTarget.getAttribute('data-link');
            if (link) removeLink(link);
        });
    });
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
// WEBSOCKET CONNECTION WITH EXPONENTIAL BACKOFF
// ════════════════════════════════════════════
function connectWS() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProto}//${window.location.host}/ws`;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        reconnectAttempts = 0;
        if (statusBadge) {
            statusBadge.innerHTML = '<span class="status-dot"></span> Conectado';
            statusBadge.className = 'status-badge status-online';
        }
    };

    socket.onclose = () => {
        if (statusBadge) {
            statusBadge.innerHTML = '<span class="status-dot"></span> Reconectando...';
            statusBadge.className = 'status-badge status-offline';
        }
        reconnectAttempts++;
        const delay = Math.min(1000 * Math.pow(1.5, reconnectAttempts), 10000) + Math.random() * 500;
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(connectWS, delay);
    };

    socket.onerror = () => {
        if (statusBadge) {
            statusBadge.innerHTML = '<span class="status-dot"></span> Erro';
            statusBadge.className = 'status-badge status-offline';
        }
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'update') {
                lastMatches = data.matches || [];
                renderLiveMatches(lastMatches);
                if (data.stats) updateStats(data.stats);
            } else if (data.type === 'alerts') {
                triggerAlerts(data.alerts || []);
            }
        } catch (err) {
            console.error('Error handling WebSocket message:', err);
        }
    };
}

// ════════════════════════════════════════════
// STATS ANIMATION
// ════════════════════════════════════════════
function animateValue(el, target) {
    if (!el) return;
    el.textContent = target;
}

function updateStats(stats) {
    if (!stats) return;
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
    if (statClock) statClock.textContent = stats.timestamp || '--:--';
}

// ════════════════════════════════════════════
// LIVE MATCHES — HIGH PERFORMANCE IN-PLACE UPDATE
// ════════════════════════════════════════════
function renderLiveMatches(matches) {
    if (!liveContainer) return;
    
    if (!matches || matches.length === 0) {
        liveContainer.innerHTML = `
            <div class="placeholder-state">
                <div class="placeholder-icon">📡</div>
                <p>Aguardando dados reais dos scrapers...</p>
            </div>`;
        const countEl = document.getElementById('filter-count');
        if (countEl) countEl.textContent = '';
        return;
    }

    // Classify
    const classified = matches.map(match => {
        const hasBet365 = !!match.sources.bet365;
        const countSources = Object.keys(match.sources || {}).length;
        const isPaired = countSources >= 2;
        return { ...match, isPaired };
    });

    let filtered = classified;
    if (currentFilter === 'paired') filtered = classified.filter(m => m.isPaired);

    const countEl = document.getElementById('filter-count');
    if (countEl) {
        countEl.textContent = currentFilter !== 'all'
            ? `Mostrando ${filtered.length} de ${matches.length}`
            : `${matches.length} partidas`;
    }

    // Group by sport
    const grouped = {};
    filtered.forEach(match => {
        const sport = match.sport || 'unknown';
        if (!grouped[sport]) grouped[sport] = [];
        grouped[sport].push(match);
    });

    let html = '';
    for (const [sport, sportMatches] of Object.entries(grouped)) {
        const emoji = getSportEmoji(sport);
        html += `<div class="sport-group">
            <div class="sport-header">${emoji} ${escapeHTML(sport.toUpperCase())} <span class="match-count">(${sportMatches.length})</span></div>`;

        sportMatches.forEach(match => {
            html += renderMatchCardHTML(match);
        });
        html += '</div>';
    }

    liveContainer.innerHTML = html;
    applyScoreFlashClasses(filtered);
}

function renderMatchCardHTML(match) {
    const s = match.sources || {};
    const b365 = s.bet365 || { set_score: '-', game_score: '-', point_score: '-' };
    const xbet = s['1xbet'] || s.betburger || { set_score: '-', game_score: '-', point_score: '-' };
    const betano = s.betano || { set_score: '-', game_score: '-', point_score: '-' };
    const novibet = s.novibet || { set_score: '-', game_score: '-', point_score: '-' };

    const b365Url = sanitizeUrl(match.bet365_link);
    const xbetUrl = sanitizeUrl(match.xbet_link || match.betburger_link);
    const betanoUrl = sanitizeUrl(match.betano_link);
    const novibetUrl = sanitizeUrl(match.novibet_link);

    const emoji = getSportEmoji(match.sport);
    const safeName = escapeHTML(match.name);
    const safeId = escapeHTML(match.id);

    return `
        <div class="match-item ${match.isPaired ? 'match-paired' : 'match-solo'}" data-match-id="${safeId}">
            <div class="match-header">
                <span class="match-name">${emoji} ${safeName}</span>
                <div class="match-actions">
                    ${b365Url !== '#' ? `<a href="${b365Url}" target="_blank" rel="noopener" class="action-btn bet365-btn">B365 ↗</a>` : '<span class="action-disabled">B365</span>'}
                    ${xbetUrl !== '#' ? `<a href="${xbetUrl}" target="_blank" rel="noopener" class="action-btn betburger-btn">1x/BB ↗</a>` : ''}
                    ${betanoUrl !== '#' ? `<a href="${betanoUrl}" target="_blank" rel="noopener" class="action-btn" style="background:#ff5000; color:#fff;">BET ↗</a>` : ''}
                    ${novibetUrl !== '#' ? `<a href="${novibetUrl}" target="_blank" rel="noopener" class="action-btn" style="background:#1b4f72; color:#fff;">NOVI ↗</a>` : ''}
                </div>
            </div>
            <div class="scores-comparison" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px;">
                <div class="source-score">
                    <div class="source-name" style="color: #27ae60; font-weight: bold;">BET365</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${safeId}_b365_set">${escapeHTML(b365.set_score)}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${safeId}_b365_game">${escapeHTML(b365.game_score)}</strong>
                    </div>
                </div>
                <div class="source-score">
                    <div class="source-name" style="color: #2980b9; font-weight: bold;">1XBET / BB</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${safeId}_xbet_set">${escapeHTML(xbet.set_score)}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${safeId}_xbet_game">${escapeHTML(xbet.game_score)}</strong>
                    </div>
                </div>
                <div class="source-score" style="border-left: 3px solid #ff5000;">
                    <div class="source-name" style="color: #ff5000; font-weight: bold;">BETANO</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${safeId}_betano_set">${escapeHTML(betano.set_score)}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${safeId}_betano_game">${escapeHTML(betano.game_score)}</strong>
                    </div>
                </div>
                ${s.novibet ? `
                <div class="source-score" style="border-left: 3px solid #1b4f72;">
                    <div class="source-name" style="color: #1b4f72; font-weight: bold;">NOVIBET</div>
                    <div class="score-values">
                        <span class="score-label">Set</span> <strong data-score-key="${safeId}_novibet_set">${escapeHTML(novibet.set_score)}</strong>
                        <span class="score-sep">|</span>
                        <span class="score-label">Game</span> <strong data-score-key="${safeId}_novibet_game">${escapeHTML(novibet.game_score)}</strong>
                    </div>
                </div>` : ''}
            </div>
        </div>`;
}

function applyScoreFlashClasses(matches) {
    const newScores = {};

    matches.forEach(match => {
        const s = match.sources || {};
        const b365 = s.bet365 || {};
        const xbet = s['1xbet'] || s.betburger || {};
        const betano = s.betano || {};
        const novibet = s.novibet || {};

        const key = match.id;
        newScores[key] = {
            b365_set: b365.set_score, b365_game: b365.game_score,
            xbet_set: xbet.set_score, xbet_game: xbet.game_score,
            betano_set: betano.set_score, betano_game: betano.game_score,
            novibet_set: novibet.set_score, novibet_game: novibet.game_score,
        };

        const prev = previousScores[key];
        if (prev) {
            for (const field of Object.keys(newScores[key])) {
                if (prev[field] !== undefined && prev[field] !== newScores[key][field]) {
                    const scoreKey = `${key}_${field}`;
                    const el = document.querySelector(`[data-score-key="${scoreKey}"]`);
                    if (el) {
                        el.classList.remove('score-flash');
                        requestAnimationFrame(() => {
                            el.classList.add('score-flash');
                        });
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
    const existingMap = new Map();
    alertHistory.forEach(a => existingMap.set(a.match_id || a.event_id || a.id, a));

    let hasNew = false;
    const activeKeys = new Set();

    activeAlerts.forEach(alert => {
        const key = alert.match_id || alert.event_id || alert.id;
        activeKeys.add(key);

        const existing = existingMap.get(key);
        if (existing) {
            existing.bet365_score = alert.bet365_score;
            existing.betano_score = alert.betano_score;
            existing.xbet_score = alert.xbet_score;
            existing.novibet_score = alert.novibet_score;
            existing.betburger_score = alert.betburger_score;
            existing.delay_seconds = alert.delay_seconds;
            existing.is_update = true;
            existing._lastServerAt = now;
            existingMap.set(key, existing);
        } else {
            alert._receivedAt = now;
            alert._lastServerAt = now;
            alert.is_update = false;
            existingMap.set(key, alert);
            if (alert.notify !== false) {
                hasNew = true;
                showToast(alert);
            }
        }
    });

    const updatedHistory = Array.from(existingMap.values()).filter(alert => {
        const key = alert.match_id || alert.event_id || alert.id;
        if (activeKeys.has(key)) return true;
        const last = alert._lastServerAt || alert._receivedAt || 0;
        return (now - last) < 25000;
    });

    updatedHistory.sort((a, b) => (b._receivedAt || 0) - (a._receivedAt || 0));
    alertHistory = updatedHistory;

    if (hasNew && !isMuted) {
        const topPrio = activeAlerts.find(a => a.priority === 'CRITICAL') ? 'CRITICAL' : 'HIGH';
        alertSynth.playAlert(topPrio);
        
        if (window.electronAPI && window.electronAPI.sendNativeAlert && activeAlerts.length > 0) {
            window.electronAPI.sendNativeAlert(activeAlerts[0]);
        }
    }

    renderAlerts();
    updateAlertBadge();
}

function renderAlerts() {
    if (!alertsContainer) return;
    
    if (alertHistory.length === 0) {
        alertsContainer.innerHTML = `
            <div class="placeholder-state">
                <div class="placeholder-icon">🛡️</div>
                <p>Nenhuma divergência ativa no momento.</p>
            </div>`;
        return;
    }

    alertsContainer.innerHTML = alertHistory.map(alert => {
        const priority = alert.priority || 'HIGH';
        const prioClass = priority === 'CRITICAL' ? 'priority-critical' : 'priority-high';

        const safeMatchName = escapeHTML((alert.match_name || alert.name || 'Partida Desconhecida').replace(/\s+vs\s+/gi, ' x '));
        const safeLeague = escapeHTML(alert.league || '');
        const leagueLine = safeLeague ? `🏆 ${safeLeague}\n` : '';
        const emoji = getSportEmoji(alert.sport);
        const relTime = alert._receivedAt ? getRelativeTime(alert._receivedAt) : (alert.timestamp || '');
        const title = alert.is_update ? '🔄 ATUALIZAÇÃO DA DIVERGÊNCIA' : '🚨 NOVA DIVERGÊNCIA DETECTADA';
        const delayStr = alert.delay_seconds ? ` [Delay: ${alert.delay_seconds}s]` : '';

        const b365Now = escapeHTML(alert.bet365_score || 'não encontrado');
        const betanoNow = escapeHTML(alert.betano_score || 'não encontrado');
        const xbetNow = escapeHTML(alert.xbet_score || 'não encontrado');
        const novibetNow = escapeHTML(alert.novibet_score || 'não encontrado');
        const burgerNow = escapeHTML(alert.betburger_score || 'não encontrado');
        const leading = escapeHTML((alert.leading_houses && alert.leading_houses.length) ? alert.leading_houses.join(', ') : '');
        const leadingLine = leading ? `\n🔺 À frente da casa alvo: ${leading}` : '';

        const safeB365Url = sanitizeUrl(alert.bet365_link);
        const safeBetanoUrl = sanitizeUrl(alert.betano_link);
        const safeXbetUrl = sanitizeUrl(alert.xbet_link || alert.betburger_link);
        const safeNovibetUrl = sanitizeUrl(alert.novibet_link);

        return `
            <div class="alert-item ${prioClass}">
                <div class="alert-header">
                    <span>${title}${delayStr}</span>
                    <span class="alert-timestamp">${relTime}</span>
                </div>
                <div class="alert-match-name" style="line-height:1.55; white-space:pre-line; font-size:13px;">
🎯 ENTRADA PARA BET365
${leagueLine}${emoji} ${safeMatchName}

Bet365 agora: ${b365Now}
Betano agora: ${betanoNow}
1xBet agora: ${xbetNow}
${novibetNow !== 'não encontrado' ? `Novibet agora: ${novibetNow}\n` : ''}${burgerNow !== 'não encontrado' && burgerNow !== xbetNow ? `BetBurger agora: ${burgerNow}\n` : ''}${leadingLine}
                </div>
                <div class="alert-actions">
                    <button type="button" class="alert-cta-bet365" data-open-match="${safeMatchName}" data-match-id="${escapeHTML(alert.match_id || '')}">⚡ ABRIR BET365</button>
                    ${safeB365Url !== '#' ? `<a href="${safeB365Url}" target="_blank" rel="noopener" class="action-btn bet365-btn" style="margin-left:8px;">B365 Web ↗</a>` : ''}
                    ${safeBetanoUrl !== '#' ? `<a href="${safeBetanoUrl}" target="_blank" rel="noopener" class="action-btn" style="background:#ff5000; color:#fff; margin-left:8px;">Betano ↗</a>` : ''}
                    ${safeXbetUrl !== '#' ? `<a href="${safeXbetUrl}" target="_blank" rel="noopener" class="action-btn betburger-btn" style="margin-left:8px;">1xBet ↗</a>` : ''}
                    ${safeNovibetUrl !== '#' ? `<a href="${safeNovibetUrl}" target="_blank" rel="noopener" class="action-btn" style="background:#1b4f72; color:#fff; margin-left:8px;">Novibet ↗</a>` : ''}
                </div>
            </div>`;
    }).join('');

    alertsContainer.querySelectorAll('.alert-cta-bet365').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const mName = e.currentTarget.getAttribute('data-open-match');
            const mId = e.currentTarget.getAttribute('data-match-id');
            openBet365Match(mId, mName);
        });
    });
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
            showToast("Bet365 Aberto", "Janela do Chrome da Bet365 focada na partida.", "info");
            return;
        }
        const listing = data.listing_url || 'https://www.bet365.bet.br/#/IP/B92';
        window.open(listing, '_blank');
    } catch (e) {
        window.open('https://www.bet365.bet.br/#/IP/B92', '_blank');
    }
}

function updateAlertBadge() {
    if (!alertBadge) return;
    if (alertHistory.length > 0) {
        alertBadge.textContent = alertHistory.length;
        alertBadge.classList.remove('hidden');
    } else {
        alertBadge.classList.add('hidden');
    }
    animateValue(statAlertCount, alertHistory.length);
}

if (clearAlertsBtn) {
    clearAlertsBtn.addEventListener('click', () => {
        alertHistory = [];
        renderAlerts();
        updateAlertBadge();
    });
}

// ════════════════════════════════════════════
// TOAST NOTIFICATIONS (Polymorphic: Text & Alert Object)
// ════════════════════════════════════════════
function showToast(arg1, arg2, arg3) {
    if (!toastContainer) return;

    const currentToasts = toastContainer.querySelectorAll('.toast:not(.toast-out)');
    if (currentToasts.length >= MAX_TOASTS) {
        const oldest = currentToasts[currentToasts.length - 1];
        dismissToast(oldest);
    }

    const toast = document.createElement('div');
    toast.className = 'toast';

    if (typeof arg1 === 'string') {
        const title = escapeHTML(arg1);
        const msg = escapeHTML(arg2 || '');
        toast.innerHTML = `
            <div class="toast-title">ℹ️ ${title}</div>
            <div class="toast-body">${msg}</div>
        `;
    } else if (typeof arg1 === 'object' && arg1 !== null) {
        const alert = arg1;
        const emoji = getSportEmoji(alert.sport);
        const matchName = escapeHTML(alert.match_name || alert.name || 'Partida');
        const priority = escapeHTML(alert.priority || 'HIGH');
        const b365 = escapeHTML(alert.bet365_score || '-');
        const other = escapeHTML(alert.betano_score || alert.xbet_score || alert.betburger_score || '-');

        toast.innerHTML = `
            <div class="toast-title">⚡ ${priority} — ${escapeHTML(alert.sport ? alert.sport.toUpperCase() : 'DIVERGÊNCIA')}</div>
            <div class="toast-body">${emoji} ${matchName}</div>
            <div class="toast-sub">Ref: ${other} vs B365: ${b365}${alert.delay_seconds ? ' · ⏱️ ' + alert.delay_seconds + 's' : ''}</div>
        `;
    }

    toast.addEventListener('click', () => dismissToast(toast));
    toastContainer.prepend(toast);

    setTimeout(() => dismissToast(toast), TOAST_DURATION);
}

function dismissToast(toast) {
    if (!toast || toast.classList.contains('toast-out')) return;
    toast.classList.add('toast-out');
    setTimeout(() => toast.remove(), 350);
}

// ════════════════════════════════════════════
// RELATIVE TIME HELPER
// ════════════════════════════════════════════
function getRelativeTime(timestamp) {
    const diff = Math.floor((Date.now() - timestamp) / 1000);
    if (diff < 5) return 'agora mesmo';
    if (diff < 60) return `há ${diff}s`;
    if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `há ${Math.floor(diff / 3600)}h`;
    return `há ${Math.floor(diff / 86400)}d`;
}

setInterval(() => {
    if (alertHistory.length > 0) renderAlerts();
}, 15000);

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
        if (alertHistory.length > 0) renderAlerts();
    });
} else {
    const pipBtn = document.getElementById('pip-btn');
    if (pipBtn) pipBtn.style.display = 'none';
}

// ════════════════════════════════════════════
// INITIAL CONNECTION
// ════════════════════════════════════════════
connectWS();

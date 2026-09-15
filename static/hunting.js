// Hunting page — states, per-state Regulations/Dates sub-tabs, per-game-type calendar.
// Deliberately standalone (doesn't load the shared app.js): small local copies of the sidebar/
// user-menu toggles below, matching the pattern already used by ammo-detail.html.

function openSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.remove('hidden');
    Object.assign(sidebar.style, { position: 'fixed', top: '0', left: '0', bottom: '0', display: 'flex', zIndex: '40' });
    document.getElementById('sidebar-overlay').classList.remove('hidden');
}
function closeSidebar() {
    if (window.innerWidth >= 1024) return;
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.add('hidden');
    sidebar.style.cssText = '';
    document.getElementById('sidebar-overlay').classList.add('hidden');
}
function toggleUserMenu(id) {
    id = id || 'user-menu';
    const menu = document.getElementById(id);
    const arrow = document.getElementById(id + '-arrow');
    if (!menu) return;
    const isOpen = !menu.classList.contains('hidden');
    menu.classList.toggle('hidden');
    if (arrow) arrow.style.transform = isOpen ? '' : 'rotate(180deg)';
}
['desktop-user-menu', 'mobile-user-menu'].forEach(id => {
    const menu = document.getElementById(id);
    if (!menu) return;
    document.addEventListener('click', e => {
        if (!menu.classList.contains('hidden') && !menu.parentElement.contains(e.target)) {
            menu.classList.add('hidden');
            const arrow = document.getElementById(id + '-arrow');
            if (arrow) arrow.style.transform = '';
        }
    });
});

let huntingStates = [];
let currentStateId = null;
let currentSubTab = 'regulations';
let huntingGameTypes = [];
let currentRegGameType = null;   // null = General (statewide) notes
let currentDatesGameType = null;
let huntingSeasonEntriesCache = [];
let huntingCalYear = new Date().getFullYear();
let huntingCalMonth = new Date().getMonth();

window.onload = () => { fetchHuntingStates(); };

async function fetchHuntingStates() {
    const res = await fetch('/hunting/states');
    huntingStates = await res.json();
    if (huntingStates.length === 0) {
        document.getElementById('hunting-empty').classList.remove('hidden');
        document.getElementById('hunting-content').classList.add('hidden');
        return;
    }
    document.getElementById('hunting-empty').classList.add('hidden');
    document.getElementById('hunting-content').classList.remove('hidden');
    renderStateTabs();
    if (!currentStateId || !huntingStates.find(s => s.id === currentStateId)) {
        selectState(huntingStates[0].id);
    }
}

function renderStateTabs() {
    const wrap = document.getElementById('hunting-state-tabs');
    wrap.innerHTML = huntingStates.map(s => `
        <button onclick="selectState(${s.id})"
            class="px-3 py-1.5 rounded-lg text-sm font-bold cursor-pointer transition ${s.id === currentStateId ? 'bg-orange-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}">
            ${s.abbreviation ? s.abbreviation + ' — ' : ''}${s.name}
        </button>
    `).join('') + `
        <button onclick="removeCurrentState()" title="Remove this state" class="px-2.5 py-1.5 rounded-lg text-sm text-red-400 hover:bg-red-900/30 cursor-pointer">🗑️</button>
    `;
}

async function removeCurrentState() {
    if (!currentStateId) return;
    const state = huntingStates.find(s => s.id === currentStateId);
    if (!state || !confirm(`Remove ${state.name} and all its season/regulation data?`)) return;
    await fetch(`/hunting/states/${currentStateId}`, { method: 'DELETE' });
    currentStateId = null;
    await fetchHuntingStates();
}

async function selectState(id) {
    currentStateId = id;
    renderStateTabs();
    const res = await fetch(`/hunting/states/${id}/game-types`);
    huntingGameTypes = await res.json();
    currentRegGameType = null;
    currentDatesGameType = huntingGameTypes[0] || null;
    renderGameTypeTabs();
    if (currentSubTab === 'regulations') loadRegulations(); else loadDates();
}

function switchHuntingSubTab(tab) {
    currentSubTab = tab;
    document.getElementById('hunting-pane-regulations').classList.toggle('hidden', tab !== 'regulations');
    document.getElementById('hunting-pane-dates').classList.toggle('hidden', tab !== 'dates');
    const active = 'px-3 py-1 rounded bg-gray-800 text-orange-400 cursor-pointer';
    const inactive = 'px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer';
    document.getElementById('hunting-subtab-btn-regulations').className = tab === 'regulations' ? active : inactive;
    document.getElementById('hunting-subtab-btn-dates').className = tab === 'dates' ? active : inactive;
    if (tab === 'regulations') loadRegulations(); else loadDates();
}

function renderGameTypeTabs() {
    const regWrap = document.getElementById('hunting-reg-gametype-tabs');
    const datesWrap = document.getElementById('hunting-dates-gametype-tabs');
    const pill = (label, active, onclick) =>
        `<button onclick="${onclick}" class="px-2.5 py-1 rounded-full cursor-pointer transition ${active ? 'bg-orange-600 text-white' : 'bg-gray-800 text-gray-300 hover:bg-gray-700'}">${label}</button>`;

    regWrap.innerHTML =
        pill('General', currentRegGameType === null, `selectRegGameType(null)`) +
        huntingGameTypes.map(g => pill(g, currentRegGameType === g, `selectRegGameType('${g}')`)).join('');

    datesWrap.innerHTML = huntingGameTypes.map(g => pill(g, currentDatesGameType === g, `selectDatesGameType('${g}')`)).join('');
}

function selectRegGameType(g) {
    currentRegGameType = g;
    renderGameTypeTabs();
    loadRegulations();
}

function selectDatesGameType(g) {
    currentDatesGameType = g;
    renderGameTypeTabs();
    loadDates();
}

async function loadRegulations() {
    if (!currentStateId) return;
    const url = currentRegGameType
        ? `/hunting/states/${currentStateId}/regulations?game_type=${encodeURIComponent(currentRegGameType)}`
        : `/hunting/states/${currentStateId}/regulations`;
    const res = await fetch(url);
    const notes = await res.json();
    const list = document.getElementById('hunting-reg-list');
    document.getElementById('hunting-reg-empty').classList.toggle('hidden', notes.length > 0);
    list.innerHTML = notes.map(n => `
        <div class="bg-gray-800 rounded-lg border border-gray-700 shadow-xl p-4">
            <h3 class="text-sm font-bold text-orange-400 mb-1.5">${n.title}</h3>
            <p class="text-sm text-gray-300 whitespace-pre-line leading-relaxed">${n.body}</p>
        </div>
    `).join('');
}

async function loadDates() {
    if (!currentStateId || !currentDatesGameType) {
        huntingSeasonEntriesCache = [];
        document.getElementById('hunting-cal-wrap').classList.add('hidden');
        document.getElementById('hunting-dates-empty').classList.remove('hidden');
        return;
    }
    const res = await fetch(`/hunting/states/${currentStateId}/seasons?game_type=${encodeURIComponent(currentDatesGameType)}`);
    huntingSeasonEntriesCache = await res.json();
    const hasAny = huntingSeasonEntriesCache.length > 0;
    document.getElementById('hunting-dates-empty').classList.toggle('hidden', hasAny);
    document.getElementById('hunting-cal-wrap').classList.toggle('hidden', !hasAny);
    if (hasAny) {
        // Jump to the first entry's start month so landing on the page shows something,
        // rather than an empty "today" month with no seasons active.
        const today = new Date();
        const todayInRange = huntingSeasonEntriesCache.some(e => _entryAppliesOn(e, today));
        if (!todayInRange) {
            const first = _huntingDateToLocalNoon(huntingSeasonEntriesCache[0].start_date);
            huntingCalYear = first.getFullYear();
            huntingCalMonth = first.getMonth();
        } else {
            huntingCalYear = today.getFullYear();
            huntingCalMonth = today.getMonth();
        }
        renderCalendar();
    }
}

function huntingCalNav(delta) {
    huntingCalMonth += delta;
    if (huntingCalMonth < 0) { huntingCalMonth = 11; huntingCalYear--; }
    if (huntingCalMonth > 11) { huntingCalMonth = 0; huntingCalYear++; }
    renderCalendar();
}

function _huntingDateToLocalNoon(iso) {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d, 12, 0, 0);
}

function _entryAppliesOn(e, dateObj) {
    const start = _huntingDateToLocalNoon(e.start_date);
    const end = _huntingDateToLocalNoon(e.end_date);
    if (dateObj < start || dateObj > end) return false;
    if (!e.weekday_filter) return true;
    const dayName = dateObj.toLocaleDateString('en-US', { weekday: 'long' });
    if (e.weekday_filter.startsWith('!')) return dayName !== e.weekday_filter.slice(1);
    return dayName === e.weekday_filter;
}

function _entryCellLabel(e) {
    return e.weapon || e.species || e.season_label;
}

let huntingCalDayEntries = {};

function renderCalendar() {
    const grid = document.getElementById('hunting-cal-grid');
    const label = document.getElementById('hunting-cal-label');
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    label.textContent = `${monthNames[huntingCalMonth]} ${huntingCalYear}`;

    const startWeekday = new Date(huntingCalYear, huntingCalMonth, 1).getDay();
    const daysInMonth = new Date(huntingCalYear, huntingCalMonth + 1, 0).getDate();

    huntingCalDayEntries = {};
    let html = '';
    for (let i = 0; i < startWeekday; i++) html += '<div></div>';
    for (let day = 1; day <= daysInMonth; day++) {
        const dateObj = new Date(huntingCalYear, huntingCalMonth, day, 12, 0, 0);
        const dayEntries = huntingSeasonEntriesCache.filter(e => _entryAppliesOn(e, dateObj));
        huntingCalDayEntries[day] = dayEntries;
        const hasEntries = dayEntries.length > 0;
        html += `<div onclick="showHuntingDayDetail(${day})"
                class="min-h-[68px] rounded border p-1 text-[10px] cursor-pointer transition ${hasEntries ? 'border-orange-800/50 bg-orange-950/20 hover:bg-orange-950/40' : 'border-gray-800 bg-gray-900/40'}">
            <div class="text-gray-400 font-bold mb-0.5">${day}</div>
            ${dayEntries.map(e => `<div class="text-orange-300 leading-tight truncate">${_entryCellLabel(e)}</div>`).join('')}
        </div>`;
    }
    grid.innerHTML = html;

    let detail = document.getElementById('hunting-day-detail');
    if (!detail) {
        detail = document.createElement('div');
        detail.id = 'hunting-day-detail';
        detail.className = 'hidden mt-3 bg-gray-900 rounded-lg border border-gray-700 p-3 space-y-2';
        document.getElementById('hunting-cal-wrap').appendChild(detail);
    }
    detail.classList.add('hidden');
}

function showHuntingDayDetail(day) {
    const entries = huntingCalDayEntries[day] || [];
    const detail = document.getElementById('hunting-day-detail');
    const monthNames = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    if (entries.length === 0) {
        detail.innerHTML = `<div class="text-sm text-gray-500">Nothing legal for ${currentDatesGameType} on ${monthNames[huntingCalMonth]} ${day}.</div>`;
    } else {
        detail.innerHTML = `<div class="text-xs font-bold text-gray-400 uppercase mb-1">${monthNames[huntingCalMonth]} ${day}, ${huntingCalYear}</div>` +
            entries.map(e => `
                <div class="border-t border-gray-800 pt-2 first:border-0 first:pt-0">
                    <div class="text-sm font-bold text-orange-400">${[e.weapon, e.species].filter(Boolean).join(' — ') || e.season_label}</div>
                    <div class="text-xs text-gray-400">${e.season_label}${e.zone_or_area ? ' · ' + e.zone_or_area : ''}</div>
                    ${e.bag_limit ? `<div class="text-xs text-gray-300 mt-1">Bag limit: ${e.bag_limit}</div>` : ''}
                    ${e.notes ? `<div class="text-xs text-gray-500 mt-1">${e.notes}</div>` : ''}
                </div>
            `).join('');
    }
    detail.classList.remove('hidden');
}

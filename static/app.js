// =============================================================================
// app.js — Guns & Reloading v1.0
// =============================================================================
// SECTION MAP
//   1.  Canvas / range-session state          (~L10)
//   2.  UI state trackers                     (~L25)
//   3.  Toast, mobile menu, collection filter (~L49)
//   4.  Photo replacement & sell modal        (~L96)
//   5.  Form helpers & datalist               (~L183)
//   6.  Lookup data & scope select            (~L252)
//   7.  Tab & pane switching                  (~L308)
//   8.  Inventory loaders (catalog, TC, scopes, ammo, components) (~L370)
//   9.  Component cards & grouped renders     (~L526)
//  10.  Component CRUD (qty update, delete)   (~L671)
//  11.  Scope mount editor                    (~L770)
//  12.  Add-form category/ammo-type switching (~L930)
//  13.  Threshold settings panel              (~L964)
//  14.  Range session / canvas engine         (~L1006)
//  15.  Crop modal                            (~L1215)
//  16.  Form submit handlers                  (~L1784)
//  17.  Preferences & init                    (~L2200)
// =============================================================================

const canvas = document.getElementById('target-canvas');
const ctx = canvas ? canvas.getContext('2d') : null;
let imgElement = new Image();

let groups = []; 
let currentGroupShots = []; 
let state = "idle"; 
let calibrationPoints = [];
let pixelsPerInch = null;

let liveBoxDims = { w: 300, h: 150 };

let liveBoxPos = { x: 0, y: 0, customized: false };
let isDraggingBox = false;
let isDraggingLabelIdx = null;
let dragOffset = { x: 0, y: 0 };
let isMultiTouch = false;
let touchStartClientPos = null;
let touchHandled = false;

// Crop modal state
let pendingGroupData = null;
let cropRect = { x: 0, y: 0, w: 0, h: 0 };
let cropDisplayScale = 1;
let cropDragState = { active: false, mode: null, startX: 0, startY: 0, origRect: null };

// UI Pipeline Filters state trackers
let currentCollectionFilter = "active"; // "active" or "sold"
let activeItemIdForSaleLog = null;
let activeItemTypeForSaleLog = "firearm"; // "firearm" or "tc-receiver"
let activeItemIdForPictureReplacement = null;
let currentInventoryTab = "platforms";
let currentAmmoFilter = "factory";
let currentPlatformTab = "general"; // "general", "shotgun", "handgun", or "tc"
function currentFrameType() {
    return { general: 'Rifle', shotgun: 'Shotgun', handgun: 'Pistol' }[currentPlatformTab] || 'Rifle';
}
let currentComponentFilter = "powders"; // "powders", "primers", "bullets", "casings"
let currentComponentMode = "reloading"; // "reloading" or "muzzleloader"
let currentAmmoCategoryFilter = null; // active category for factory view
let currentAmmoCaliberFilter = null;  // active caliber filter (all tabs)
let currentPlatformSort = "brand";
let currentOpticSort = "brand";
let currentSearchQuery = "";

function applyInventorySearch() {
    const el = document.getElementById('inventory-search');
    currentSearchQuery = (el ? el.value : '').toLowerCase().trim();
    if (currentInventoryTab === 'platforms') {
        if (currentPlatformTab === 'tc') loadTCInventory();
        else loadCatalog();
    } else if (currentInventoryTab === 'optics') loadScopeInventory();
    else if (currentInventoryTab === 'ammo') loadAmmoInventory(currentAmmoFilter);
    else if (currentInventoryTab === 'components') loadComponentInventory(currentComponentFilter);
}

function matchesSearch(item) {
    if (!currentSearchQuery) return true;
    const fields = [item.brand, item.model, item.caliber, item.line_or_powder, item.bullet_type,
                    item.serial_number, item.name, item.magnification, item.product_line].filter(Boolean);
    const text = fields.join(' ').toLowerCase();
    return text.includes(currentSearchQuery);
}

// ── Photo widget (multi-select + primary toggle) ──────────────────────────────
const _pw = {}; // widget state: widgetId -> { files: File[], primary: 0 }

function handlePhotoWidget(wid) {
    const input = document.getElementById(`${wid}-input`);
    const files = Array.from(input.files).slice(0, 2);
    _pw[wid] = { files, primary: 0 };
    _renderPW(wid);
}

function _renderPW(wid) {
    const container = document.getElementById(`${wid}-preview`);
    if (!container) return;
    const w = _pw[wid];
    if (!w || w.files.length === 0) { container.innerHTML = ''; container.classList.add('hidden'); return; }
    container.classList.remove('hidden');
    container.innerHTML = w.files.map((file, idx) => {
        const url = URL.createObjectURL(file);
        const isPri = idx === w.primary;
        return `<div class="relative cursor-pointer select-none" onclick="_setPWPrimary('${wid}',${idx})">
            <img src="${url}" class="h-20 w-28 object-contain rounded bg-gray-950 border-2 transition ${isPri ? 'border-amber-500' : 'border-gray-600'}">
            <div class="absolute top-0.5 right-0.5 text-xs">${isPri ? '⭐' : '○'}</div>
            <p class="text-[9px] text-center mt-0.5 ${isPri ? 'text-amber-400 font-bold' : 'text-gray-500'}">${isPri ? 'PRIMARY' : 'tap to set'}</p>
        </div>`;
    }).join('');
}

function _setPWPrimary(wid, idx) {
    if (_pw[wid]) { _pw[wid].primary = idx; _renderPW(wid); }
}

function _getPWFiles(wid) {
    const w = _pw[wid];
    if (!w || w.files.length === 0) return { f1: null, f2: null };
    return { f1: w.files[w.primary] || null, f2: w.files.find((_, i) => i !== w.primary) || null };
}

function _resetPW(wid) {
    _pw[wid] = { files: [], primary: 0 };
    const el = document.getElementById(`${wid}-input`); if (el) el.value = '';
    const cam = document.getElementById(`${wid}-cam`); if (cam) cam.value = '';
    const pr = document.getElementById(`${wid}-preview`); if (pr) { pr.innerHTML = ''; pr.classList.add('hidden'); }
}

function handlePWCamera(wid) {
    const cam = document.getElementById(`${wid}-cam`);
    const file = cam?.files[0];
    if (!file) return;
    const existing = (_pw[wid]?.files) || [];
    _pw[wid] = { files: [...existing, file].slice(0, 2), primary: _pw[wid]?.primary || 0 };
    _renderPW(wid);
    cam.value = '';
}

function _camToInput(camId, targetId) {
    const cam = document.getElementById(camId);
    const file = cam?.files[0];
    if (!file) return;
    const dt = new DataTransfer();
    dt.items.add(file);
    const target = document.getElementById(targetId);
    if (target) target.files = dt.files;
    cam.value = '';
}

// ── Custom Autocomplete ───────────────────────────────────────────────────────
let _acDropdown = null;

function initCustomAC() {
    document.querySelectorAll('input[data-ac]').forEach(input => {
        const dlId = input.getAttribute('data-ac');
        const wrap = input.parentElement;
        if (getComputedStyle(wrap).position === 'static') wrap.style.position = 'relative';

        const drop = document.createElement('div');
        drop.className = 'hidden absolute left-0 right-0 z-50 bg-gray-800 border border-gray-600 rounded-b shadow-xl max-h-44 overflow-y-auto';
        drop.style.top = '100%';
        wrap.appendChild(drop);

        function getVals() {
            const dl = document.getElementById(dlId);
            return dl ? Array.from(dl.options).map(o => o.value).filter(Boolean) : [];
        }
        function render(q) {
            const all = getVals();
            const filtered = (q ? all.filter(v => v.toLowerCase().includes(q.toLowerCase())) : all).slice(0, 10);
            if (!filtered.length) { close(); return; }
            drop.innerHTML = filtered.map(v =>
                `<div class="px-3 py-2 cursor-pointer hover:bg-gray-700 active:bg-gray-600 text-sm text-white border-b border-gray-700/50 last:border-0"
                      data-val="${escHtml(v)}">${escHtml(v)}</div>`
            ).join('');
            drop.classList.remove('hidden');
            if (_acDropdown && _acDropdown !== drop) _acDropdown.classList.add('hidden');
            _acDropdown = drop;
        }
        function close() {
            drop.classList.add('hidden');
            if (_acDropdown === drop) _acDropdown = null;
        }

        input.addEventListener('input', () => render(input.value));
        input.addEventListener('focus', () => render(input.value));
        input.addEventListener('blur',  () => setTimeout(close, 160));
        drop.addEventListener('mousedown', e => {
            const val = e.target.closest('[data-val]')?.getAttribute('data-val');
            if (val) { input.value = val; input.dispatchEvent(new Event('input')); close(); }
        });
        drop.addEventListener('touchend', e => {
            const val = e.target.closest('[data-val]')?.getAttribute('data-val');
            if (val) { input.value = val; input.dispatchEvent(new Event('input')); close(); }
        });
    });

    document.addEventListener('click', e => {
        if (_acDropdown && !_acDropdown.contains(e.target)) {
            _acDropdown.classList.add('hidden');
            _acDropdown = null;
        }
    });
}

let lookupTables = {
    firearm_brands: [],
    firearm_models: [],
    optics: [],
    furniture: [],
    ammo_brands: [],
    calibers: [],
    powders: [],
    primers: [],
    bullets: [],
    brass: []
};

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `p-4 rounded-lg shadow-xl text-xs font-bold tracking-wide border transition-all duration-300 transform translate-y-2 opacity-0 flex items-center space-x-2 pointer-events-auto max-w-sm ${
        type === 'error' 
        ? 'bg-red-950/90 text-red-400 border-red-800' 
        : 'bg-gray-850/95 text-emerald-400 border-emerald-800'
    }`;
    
    toast.innerHTML = `<span>${type === 'error' ? '⚠️' : '✅'}</span><span>${message}</span>`;
    container.appendChild(toast);
    
    setTimeout(() => toast.classList.remove('opacity-0', 'translate-y-2'), 50);
    setTimeout(() => {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

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

function toggleUserMenu() {
    const menu = document.getElementById('user-menu');
    const arrow = document.getElementById('user-menu-arrow');
    const isOpen = !menu.classList.contains('hidden');
    menu.classList.toggle('hidden');
    if (arrow) arrow.style.transform = isOpen ? '' : 'rotate(180deg)';
}

// Vault Filtering Controllers
function setCollectionFilter(mode) {
    currentCollectionFilter = mode || (currentCollectionFilter === 'sold' ? 'active' : 'sold');
    const btnActive = document.getElementById('btn-filter-active');
    const btnSold = document.getElementById('btn-filter-sold');
    const onCls = "px-3 py-1 rounded bg-gray-800 text-emerald-400 cursor-pointer";
    const offCls = "px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer";
    if (btnActive) btnActive.className = currentCollectionFilter === 'active' ? onCls : offCls;
    if (btnSold) btnSold.className = currentCollectionFilter === 'sold' ? onCls : offCls;
    if (currentPlatformTab === 'tc') loadTCInventory();
    else loadCatalog();
}

// Picture Swap Trigger
function triggerPictureReplacement(itemId) {
    activeItemIdForPictureReplacement = itemId;
    const replacer = document.getElementById('global-picture-replacer');
    if (replacer) replacer.click();
}

async function processPictureReplacement(inputElement) {
    const file = inputElement.files[0];
    if (!file || !activeItemIdForPictureReplacement) return;

    const formData = new FormData();
    formData.append('image_1', file);

    try {
        const response = await fetch(`/firearms/${activeItemIdForPictureReplacement}/update-photo/`, {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            showToast("Vault record profile image modified successfully.");
            loadCatalog();
        } else {
            const fakeUrl = URL.createObjectURL(file);
            localStorage.setItem(`local_img_${activeItemIdForPictureReplacement}`, fakeUrl);
            showToast("Profile image applied locally.");
            loadCatalog();
        }
    } catch(e) {
        const fakeUrl = URL.createObjectURL(file);
        localStorage.setItem(`local_img_${activeItemIdForPictureReplacement}`, fakeUrl);
        showToast("Applied image update profile locally.", "success");
        loadCatalog();
    }
    inputElement.value = "";
}

// Sale Modal Controller Interfaces
function openSellModal(itemId, currentTitle, itemType = 'firearm') {
    activeItemIdForSaleLog = itemId;
    activeItemTypeForSaleLog = itemType;
    const titleEl = document.getElementById('sell-modal-item-title');
    const priceEl = document.getElementById('modal-sold-price');
    const modalEl = document.getElementById('sell-modal');

    if (titleEl) titleEl.innerText = currentTitle;
    if (priceEl) priceEl.value = "";
    if (modalEl) modalEl.classList.remove('hidden');
}

function closeSellModal() {
    const modalEl = document.getElementById('sell-modal');
    if (modalEl) modalEl.classList.add('hidden');
    activeItemIdForSaleLog = null;
}

async function submitAssetSale() {
    const soldPrice = parseFloat(document.getElementById('modal-sold-price').value);
    if (isNaN(soldPrice) || soldPrice < 0) {
        showToast("Please check parameters. Input a valid sold valuation.", "error");
        return;
    }

    const endpoint = activeItemTypeForSaleLog === 'tc-receiver'
        ? `/tc-receivers/${activeItemIdForSaleLog}/mark-sold/`
        : activeItemTypeForSaleLog === 'tc-barrel'
        ? `/tc-barrels/${activeItemIdForSaleLog}/mark-sold/`
        : `/firearms/${activeItemIdForSaleLog}/mark-sold/`;

    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_sold: true, price_sold: soldPrice })
        });

        if (response.ok) {
            showToast("Asset status moved to Sold Registry.");
            closeSellModal();
            if (activeItemTypeForSaleLog === 'tc-receiver' || activeItemTypeForSaleLog === 'tc-barrel') loadTCInventory();
            else loadCatalog();
        } else {
            showToast("Failed to log sale. Server returned an error.", "error");
        }
    } catch(err) {
        showToast("Failed to log sale. Check your connection and try again.", "error");
    }
}

async function trashItem(type, id, name) {
    if (!confirm(`Move "${name}" to trash?\n\nIt will be hidden from inventory and can be restored later from Admin › Trash.`)) return;
    const urlMap = {
        firearm: `/firearms/${id}/trash`,
        'tc-receiver': `/tc-receivers/${id}/trash`,
        'tc-barrel': `/tc-barrels/${id}/trash`,
        scope: `/scopes/${id}/trash`,
    };
    try {
        const res = await fetch(urlMap[type], { method: 'POST' });
        if (res.ok) {
            showToast(`"${name}" moved to trash.`);
            if (type === 'tc-receiver' || type === 'tc-barrel') loadTCInventory();
            else if (type === 'scope') loadScopeInventory();
            else loadCatalog();
        } else {
            showToast('Failed to move to trash.', 'error');
        }
    } catch {
        showToast('Network error.', 'error');
    }
}

function handleBrandOrModelChange() {
    const brandEl = document.getElementById('rifle-brand-input') || document.getElementById('rifle-brand-select');
    const modelEl = document.getElementById('rifle-model-input') || document.getElementById('rifle-model-select');
    if (!brandEl || !modelEl) return;

    const brandVal = brandEl.value.trim().toLowerCase();
    const modelVal = modelEl.value.trim().toLowerCase();
    const barrelOption = document.getElementById('tc-barrel-only-option');
    const extPanel = document.getElementById('tc-modular-extension');
    const frameSelect = document.getElementById('rifle-frame-select');
    
    const opticContainer = document.getElementById('optic-dropdown-container');
    const furnitureContainer = document.getElementById('furniture-dropdown-container');

    const isTC = (brandVal === "thompson/center" || brandVal === "thompson center" || brandVal === "tc");
    const isModularModel = (modelVal === "encore" || modelVal === "contender");

    if (barrelOption && frameSelect) {
        if (isTC && isModularModel) {
            barrelOption.classList.remove('hidden');
        } else {
            barrelOption.classList.add('hidden');
            if (frameSelect.value === "Barrel Only") frameSelect.value = "Rifle";
        }
    }

    if (frameSelect) {
        // 🌟 FIXED LOGIC: Only show the modular matrix extension if it's explicitly a "Barrel Only" framework type
        if (frameSelect.value === "Barrel Only") {
            if (opticContainer) opticContainer.classList.add('hidden');
            if (furnitureContainer) furnitureContainer.classList.add('hidden');
            if (extPanel && isTC) extPanel.classList.remove('hidden');
        } else {
            if (opticContainer) opticContainer.classList.remove('hidden');
            if (furnitureContainer) furnitureContainer.classList.remove('hidden');
            if (extPanel) extPanel.classList.add('hidden'); // 👈 Force hidden for standard rifles/pistols
        }
    }
}

function handleFrameTypeChange() { handleBrandOrModelChange(); }

function toggleScopeInputState() {
    const toggleEl = document.getElementById('tc-scope-installed-toggle');
    if (!toggleEl) return;
    const toggle = toggleEl.value;
    const scopeBox = document.getElementById('tc-scope-specification-box');
    const scopeInput = document.getElementById('tc-scope-name-input');

    if (!scopeBox || !scopeInput) return;

    if (toggle === "Yes") {
        scopeBox.classList.remove('opacity-40');
        const label = scopeBox.querySelector('label');
        if (label) label.className = "block text-xs text-amber-400 mb-1";
        scopeInput.removeAttribute('disabled');
        scopeInput.setAttribute('required', 'required');
        scopeInput.className = "w-full bg-gray-700 border border-gray-600 rounded p-2 text-sm text-white focus:outline-none focus:border-amber-500";
    } else {
        scopeBox.classList.add('opacity-40');
        const label = scopeBox.querySelector('label');
        if (label) label.className = "block text-xs text-gray-200 font-semibold mb-1";
        scopeInput.setAttribute('disabled', 'disabled');
        scopeInput.removeAttribute('required');
        scopeInput.value = "";
        scopeInput.className = "w-full bg-gray-750 border border-gray-650 rounded p-2 text-sm text-white focus:outline-none";
    }
}

let _hlBullets = [];
let _hlCasings = [];

async function populateHandloadDropdowns() {
    try {
        const [powderRes, primerRes, bulletRes, casingRes] = await Promise.all([
            fetch('/components/powders/', { cache: 'no-store' }),
            fetch('/components/primers/', { cache: 'no-store' }),
            fetch('/components/bullets/', { cache: 'no-store' }),
            fetch('/components/casings/', { cache: 'no-store' }),
        ]);
        const powders = powderRes.ok ? await powderRes.json() : [];
        const primers = primerRes.ok ? await primerRes.json() : [];
        const bullets = bulletRes.ok ? await bulletRes.json() : [];
        const casings = casingRes.ok ? await casingRes.json() : [];
        _hlBullets = bullets;
        _hlCasings = casings;

        const calSel = document.getElementById('hl-caliber');
        if (calSel) {
            // Use casing calibers (cartridge names like "270 Winchester", not bullet diameters like ".277")
            const calibers = [...new Set(casings.map(c => c.caliber).filter(Boolean))].sort();
            calSel.innerHTML = `<option value="">— Select caliber —</option>` +
                calibers.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
        }

        const powSel = document.getElementById('hl-powder');
        if (powSel) {
            powSel.innerHTML = `<option value="">— Select powder —</option>` +
                powders.filter(p => !p.is_muzzleloader).map(p => {
                    const label = `${p.brand} ${p.name}`.trim();
                    const qty = `${parseFloat(p.weight_lbs || 0).toFixed(1)} lbs`;
                    return `<option value="${escHtml(label)}" data-id="${p.id}">${escHtml(label)} (${qty})</option>`;
                }).join('');
        }

        const priSel = document.getElementById('hl-primer');
        if (priSel) {
            priSel.innerHTML = `<option value="">— Select primer (optional) —</option>` +
                primers.filter(p => !p.is_muzzleloader).map(p => {
                    const label = `${p.brand} ${p.model || ''}`.trim();
                    return `<option value="${escHtml(label)}" data-id="${p.id}">${escHtml(label)} (${(p.quantity || 0).toLocaleString()} ct)</option>`;
                }).join('');
        }

        const bulSel = document.getElementById('hl-bullet');
        if (bulSel) bulSel.innerHTML = _buildBulletOptionsHTML(bullets, calSel ? calSel.value : null);

        const casSel = document.getElementById('hl-casing');
        if (casSel) casSel.innerHTML = _buildCasingOptionsHTML(casings, calSel ? calSel.value : null);
    } catch (err) { console.error('populateHandloadDropdowns error:', err); }
}

// Cartridge name (as used by casings, e.g. "6.5 Creedmoor") -> bullet bore diameter (as
// used by bullets, e.g. ".264"). Ballistics naming is inconsistent — some cartridges are
// named for their actual bore diameter (".308 Winchester"), others for a historical/
// marketing number ("270 Winchester" is really a .277" bore) or a metric bullet diameter
// ("6.5 Creedmoor" is .264") — there's no way to derive one from the other algorithmically,
// hence this lookup table. Extend it as new calibers get added to inventory.
const CARTRIDGE_BORE_DIAMETER = {
    '17 hornet': '.172', '17 hmr': '.172', '17 remington': '.172', '17 wsm': '.172',
    '204 ruger': '.204',
    '221 fireball': '.224', '222 remington': '.224', '223 remington': '.224', '5.56 nato': '.224',
    '22-250 remington': '.224', '220 swift': '.224', '224 valkyrie': '.224', '22 nosler': '.224',
    '225 winchester': '.224',
    '243 winchester': '.243', '6mm remington': '.243', '6mm creedmoor': '.243', '6mm arc': '.243',
    '243 wssm': '.243', '6mm prc': '.243', '244 remington': '.243',
    '25-06 remington': '.257', '257 roberts': '.257', '25 wssm': '.257', '257 weatherby magnum': '.257',
    '6.5 creedmoor': '.264', '6.5x55': '.264', '6.5x55 swedish': '.264', '260 remington': '.264',
    '6.5-284 norma': '.264', '6.5 prc': '.264', '6.5 grendel': '.264', '264 winchester magnum': '.264',
    '6.5x47 lapua': '.264', '6.5 weatherby rpm': '.264', '6.5 rem magnum': '.264',
    '270 winchester': '.277', '270 wsm': '.277', '270 weatherby magnum': '.277', '6.8 western': '.277',
    '7mm-08 remington': '.284', '7mm remington magnum': '.284', '280 remington': '.284', '7mm prc': '.284',
    '28 nosler': '.284', '7mm weatherby magnum': '.284', '7mm stw': '.284', '7mm saum': '.284',
    '275 rigby': '.284', '280 ackley improved': '.284',
    '30-06 springfield': '.308', '308 winchester': '.308', '300 winchester magnum': '.308',
    '300 wsm': '.308', '300 prc': '.308', '300 remington ultra magnum': '.308', '300 weatherby magnum': '.308',
    '30-30 winchester': '.308', '300 blackout': '.308', '300 aac blackout': '.308',
    '300 norma magnum': '.308', '30 nosler': '.308', '308 marlin express': '.308', '7.62x51': '.308',
    '8mm mauser': '.323', '8x57 mauser': '.323', '8mm remington magnum': '.323',
    '338 winchester magnum': '.338', '338 lapua magnum': '.338', '338-06': '.338', '338 federal': '.338',
    '33 nosler': '.338', '338 rcm': '.338', '338 win mag': '.338',
    '35 whelen': '.358', '358 winchester': '.358', '35 remington': '.358',
    '375 hh magnum': '.375', '375 ruger': '.375', '375 weatherby magnum': '.375',
    '416 rigby': '.416', '416 remington magnum': '.416',
    '45-70 government': '.458', '458 winchester magnum': '.458', '458 lott': '.458',
    '50 bmg': '.510', '50 beowulf': '.500',
    '9mm luger': '.355', '9x19': '.355', '9mm': '.355',
    '357 magnum': '.357', '357 sig': '.357', '38 special': '.357',
    '40 sw': '.400', '10mm auto': '.400',
    '45 acp': '.451', '45 colt': '.451',
    '44 magnum': '.429', '44 special': '.429', '444 marlin': '.429',
};

function _normalizeCartridgeName(s) {
    return String(s || '').toLowerCase().replace(/[^a-z0-9. ]/g, '').replace(/\s+/g, ' ').trim();
}

function _boreDiameterForCartridge(cartridgeName) {
    return CARTRIDGE_BORE_DIAMETER[_normalizeCartridgeName(cartridgeName)] || null;
}

function _normalizeBoreDiameter(s) {
    const t = String(s || '').trim().toLowerCase();
    const m = t.match(/^0?\.?(\d{3})$/);
    return m ? `.${m[1]}` : t;
}

// Bullets are catalogued by bore diameter (".264") while `cartridgeCaliber` is a cartridge
// name ("6.5 Creedmoor") — filter through CARTRIDGE_BORE_DIAMETER. If the cartridge isn't in
// the table, or nothing matches, fall back to showing every bullet rather than a dead end.
function _buildBulletOptionsHTML(bullets, cartridgeCaliber) {
    let list = bullets.filter(b => !b.is_muzzleloader);
    const bore = cartridgeCaliber ? _boreDiameterForCartridge(cartridgeCaliber) : null;
    if (bore) {
        const filtered = list.filter(b => _normalizeBoreDiameter(b.caliber) === bore);
        if (filtered.length) list = filtered;
    }
    if (!list.length) return `<option value="">No bullets in stock</option>`;
    return `<option value="">— Select bullet —</option>` + list.map(b => {
        const label = `${b.brand} ${b.product_line || ''} ${b.caliber} ${b.weight_gr}gr ${b.bullet_type || ''}`.replace(/\s+/g,' ').trim();
        return `<option value="${escHtml(label)}" data-id="${b.id}">${escHtml(label)} (${(b.quantity||0).toLocaleString()} ct)</option>`;
    }).join('');
}

// Casing caliber is the same cartridge-name convention as the caliber selector itself, so
// this is a plain exact match — no diameter mapping needed.
function _buildCasingOptionsHTML(casings, cartridgeCaliber) {
    let list = casings;
    if (cartridgeCaliber) {
        const filtered = casings.filter(c => c.caliber === cartridgeCaliber);
        if (filtered.length) list = filtered;
    }
    return `<option value="">— Select casing (optional) —</option>` +
        list.map(c => {
            const label = `${c.brand} ${c.caliber}`.trim();
            const cond = c.times_fired === 0 ? 'New' : `${c.times_fired}x fired`;
            return `<option value="${escHtml(c.brand)}" data-id="${c.id}">${escHtml(label)} — ${cond} (${(c.quantity||0).toLocaleString()} ct)</option>`;
        }).join('');
}

function filterHandloadBullets() {
    const cal = document.getElementById('hl-caliber')?.value;
    const bulSel = document.getElementById('hl-bullet');
    const casSel = document.getElementById('hl-casing');
    if (bulSel) bulSel.innerHTML = _buildBulletOptionsHTML(_hlBullets, cal);
    if (casSel) casSel.innerHTML = _buildCasingOptionsHTML(_hlCasings, cal);
}

function filterLadderBullets() {
    const cal = document.getElementById('lt-caliber')?.value;
    const bulSel = document.getElementById('lt-bullet');
    const casSel = document.getElementById('lt-casing');
    if (bulSel) bulSel.innerHTML = _buildBulletOptionsHTML(_ladderBullets, cal);
    if (casSel) casSel.innerHTML = _buildCasingOptionsHTML(_ladderCasings, cal);
    renderLadderPlatformOptions();
}

function autofillBulletData(sel) {
    const label = sel.value;
    if (!label) return;
    const opt = sel.querySelector(`option[value="${CSS.escape(label)}"]`);
    const id = opt ? parseInt(opt.dataset.id) : null;
    const b = id ? _hlBullets.find(x => x.id === id) : null;
    if (!b) return;
    const wt = document.getElementById('hl-bullet-weight');
    const bc = document.getElementById('hl-bullet-bc');
    if (wt && b.weight_gr) wt.value = b.weight_gr;
    if (bc && b.bc_g1) bc.value = b.bc_g1;
}

async function fetchInitialLookupData() {
    try {
        const res = await fetch('/lookups/');
        if (!res.ok) return;
        const data = await res.json();
        // Populate datalists
        Object.entries(data).forEach(([cat, values]) => {
            const id = 'dl-' + cat.replace(/_/g, '-');
            const dl = document.getElementById(id);
            if (dl) dl.innerHTML = values.map(v => `<option value="${escHtml(v)}">`).join('');
        });
        // Also populate handload-powder/primer/bullet/brass from inventory names
        if (data.powder_name) {
            const dl = document.getElementById('dl-handload-powder');
            if (dl) dl.innerHTML = data.powder_name.map(v => `<option value="${escHtml(v)}">`).join('');
        }
        if (data.primer_brand) {
            const dl = document.getElementById('dl-handload-primer');
            if (dl) dl.innerHTML = data.primer_brand.map(v => `<option value="${escHtml(v)}">`).join('');
        }
        if (data.bullet_brand) {
            const dl = document.getElementById('dl-handload-bullet');
            if (dl) dl.innerHTML = data.bullet_brand.map(v => `<option value="${escHtml(v)}">`).join('');
        }
        if (data.casing_brand) {
            const dl = document.getElementById('dl-handload-brass');
            if (dl) dl.innerHTML = data.casing_brand.map(v => `<option value="${escHtml(v)}">`).join('');
        }
        // Update the scope select in the firearm form
        populateScopeSelect();
    } catch (err) { console.error('fetchInitialLookupData error:', err); }
}

function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function saveLookupValue(category, value) {
    if (!value || !value.trim()) return;
    const fd = new FormData();
    fd.set('value', value.trim());
    try { await fetch(`/lookups/${category}`, { method: 'POST', body: fd }); } catch(_) {}
}

async function populateScopeSelect() {
    const sel = document.getElementById('rifle-optic-select');
    if (!sel) return;
    try {
        const res = await fetch('/scopes/');
        if (!res.ok) return;
        const scopes = await res.json();
        sel.innerHTML = '<option value="None">None (Iron Sights)</option>' +
            scopes.map(s => `<option value="${s.id}">${s.brand} ${s.model}</option>`).join('');
    } catch(_) {}
}

function switchTab(tabId) {
    if (tabId === 'catalog-tab') { window.location.href = '/inventory'; return; }
    ['landing-tab', 'measure-tab', 'add-tab', 'ladder-tab'].forEach(id => {
        document.getElementById(id)?.classList.add('hidden');
    });

    const target = document.getElementById(tabId);
    if (target) target.classList.remove('hidden');

    if (tabId === 'measure-tab') setupMeasureDropdowns();
    if (tabId === 'ladder-tab') showLadderListView();
}

function switchInventoryTab(tab) {
    currentInventoryTab = tab;
    // 'handloads' is now a sub-filter under ammo, not a top-level tab
    if (tab === 'handloads') { switchInventoryTab('ammo'); switchAmmoFilter('handload'); return; }
    const tabs = ['platforms', 'optics', 'ammo', 'components'];
    tabs.forEach(t => {
        document.getElementById(`inv-pane-${t}`)?.classList.add('hidden');
        const btn = document.getElementById(`inv-btn-${t}`);
        if (btn) btn.className = "px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer";
    });
    document.getElementById(`inv-pane-${tab}`)?.classList.remove('hidden');
    const activeBtn = document.getElementById(`inv-btn-${tab}`);
    if (activeBtn) activeBtn.className = "px-3 py-1 rounded bg-gray-800 text-amber-500 cursor-pointer";

    if (tab === 'platforms')   switchPlatformTab(currentPlatformTab);
    if (tab === 'optics')      loadScopes();
    if (tab === 'ammo')        loadAmmoInventory(currentAmmoFilter);
    if (tab === 'components')  loadComponentInventory(currentComponentFilter);
}

function switchPlatformTab(tab) {
    currentPlatformTab = tab;
    const genPane = document.getElementById('plat-pane-general');
    const tcPane  = document.getElementById('plat-pane-tc');
    const filter  = document.getElementById('plat-collection-filter');
    const firearmTabs = ['general', 'shotgun', 'handgun'];

    firearmTabs.forEach(t => {
        const btn = document.getElementById(`plat-btn-${t}`);
        if (btn) btn.className = "px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer";
    });
    const tcBtn = document.getElementById('plat-btn-tc');

    const mainAddBtn = document.getElementById('plat-main-add-btn');
    if (tab === 'tc') {
        genPane?.classList.add('hidden');
        tcPane?.classList.remove('hidden');
        if (tcBtn) tcBtn.className = "px-3 py-1 rounded bg-gray-800 text-amber-500 cursor-pointer";
        if (mainAddBtn) mainAddBtn.classList.add('hidden');
        loadTCInventory();
    } else {
        genPane?.classList.remove('hidden');
        tcPane?.classList.add('hidden');
        if (tcBtn) tcBtn.className = "px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer";
        if (mainAddBtn) mainAddBtn.classList.remove('hidden');
        const activeBtn = document.getElementById(`plat-btn-${tab}`);
        if (activeBtn) activeBtn.className = "px-3 py-1 rounded bg-gray-800 text-amber-500 cursor-pointer";
        loadCatalog(currentFrameType());
    }
}

async function loadTCInventory() {
    const recContainer = document.getElementById('tc-receivers-container');
    const barContainer = document.getElementById('tc-barrels-container');
    if (!recContainer || !barContainer) return;

    try {
        const [recRes, barRes] = await Promise.all([fetch('/tc-receivers/'), fetch('/tc-barrels/')]);
        const allReceivers = recRes.ok ? await recRes.json() : [];
        const barrels      = barRes.ok ? await barRes.json() : [];
        const receivers    = allReceivers.filter(r => currentCollectionFilter === 'sold' ? r.is_sold : !r.is_sold).filter(matchesSearch);

        const filteredBarrels = barrels.filter(matchesSearch);
        const total = receivers.length + filteredBarrels.length;
        document.getElementById('inventory-count').innerText = `${total} TC Item${total !== 1 ? 's' : ''} Registered`;

        if (receivers.length === 0) {
            recContainer.innerHTML = '<p class="text-gray-500 italic text-sm col-span-3">No receivers registered.</p>';
        } else {
            recContainer.innerHTML = receivers.map(r => {
                const soldBadge = r.is_sold
                    ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-red-950 text-red-400 border border-red-800">SOLD</span>`
                    : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-400 border border-amber-800">RECEIVER</span>`;
                const gallery = makePhotoGallery(`rec-${r.id}`, '🛠️', r.image_path, r.image_path_2, 'cover');
                return `
                <div class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-xl flex flex-col">
                    ${gallery}
                    <div class="p-3 flex flex-col flex-1 gap-2">
                        <div class="flex justify-between items-center">${soldBadge}
                            <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-gray-900 text-gray-300 border border-gray-700">${r.platform}</span>
                        </div>
                        <p class="text-sm font-bold text-white">${r.platform} Receiver</p>
                        <p class="text-xs text-gray-400">S/N: <span class="text-gray-200 font-mono">${r.serial_number || '—'}</span></p>
                        <!-- Inline edit -->
                        <div id="rcedit-${r.id}" class="hidden border-t border-gray-600 pt-2 space-y-2">
                            <p class="text-xs font-bold text-amber-400 uppercase tracking-wide">Edit Receiver</p>
                            <select id="rcedit-plat-${r.id}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                                <option ${r.platform==='Encore'?'selected':''}>Encore</option>
                                <option ${r.platform==='Contender'?'selected':''}>Contender</option>
                            </select>
                            <input id="rcedit-sn-${r.id}" value="${r.serial_number||''}" placeholder="Serial number" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                            <input id="rcedit-notes-${r.id}" value="${r.notes||''}" placeholder="Notes" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                            <input type="number" step="0.01" id="rcedit-price-${r.id}" value="${r.price_paid||0}" placeholder="Price" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                            <p class="text-xs text-gray-200 font-semibold">Replace photos (optional)</p>
                            <input type="file" id="rcedit-p1-${r.id}" accept="image/*" class="w-full text-[10px] text-gray-400 file:bg-gray-700 file:text-amber-400 file:py-1 file:px-2 file:rounded file:border-0 cursor-pointer">
                            <input type="file" id="rcedit-p2-${r.id}" accept="image/*" class="w-full text-[10px] text-gray-400 file:bg-gray-700 file:text-amber-400 file:py-1 file:px-2 file:rounded file:border-0 cursor-pointer">
                            <div class="flex gap-2">
                                <button onclick="saveTCReceiverEdit(${r.id})" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold py-1.5 rounded transition cursor-pointer">Save</button>
                                <button onclick="document.getElementById('rcedit-${r.id}').classList.add('hidden')" class="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold py-1.5 rounded transition cursor-pointer">Cancel</button>
                            </div>
                        </div>
                        <div class="flex gap-2 mt-auto pt-1">
                            <button onclick="document.getElementById('rcedit-${r.id}').classList.toggle('hidden')"
                                class="flex-1 px-2 py-1.5 bg-amber-700 hover:bg-amber-600 text-white text-xs font-bold rounded transition cursor-pointer">✏️ Edit</button>
                            ${r.is_sold
                                ? `<span class="px-2 py-1.5 text-xs text-red-400 font-mono">Sold $${parseFloat(r.price_sold||0).toFixed(2)}</span>`
                                : `<button onclick="openSellModal(${r.id},'${r.platform} Receiver','tc-receiver')" class="px-2 py-1.5 bg-gray-700 hover:bg-emerald-800 text-gray-300 hover:text-white text-xs font-bold rounded transition cursor-pointer">$ Sell</button>`}
                            <button onclick="trashItem('tc-receiver',${r.id},'${r.platform} Receiver')" class="px-2 py-1.5 bg-gray-700 hover:bg-red-900 text-gray-400 hover:text-red-300 text-xs font-bold rounded transition cursor-pointer" title="Move to trash">🗑️</button>
                        </div>
                        <div class="flex justify-end">
                            <span class="text-xs text-gray-500 font-mono">$${parseFloat(r.price_paid || 0).toFixed(2)}</span>
                        </div>
                    </div>
                </div>`;
            }).join('');
        }

        if (filteredBarrels.length === 0) {
            barContainer.innerHTML = '<p class="text-gray-500 italic text-sm col-span-3">No barrels registered.</p>';
        } else {
            barContainer.innerHTML = filteredBarrels.map(b => {
                const gallery = makePhotoGallery(`bar-${b.id}`, '🎯', b.image_path, b.image_path_2, 'cover');
                const flags = [b.is_threaded && 'Threaded', b.has_muzzle_brake && 'Brake'].filter(Boolean).join(' · ');
                const barrelLabel = `${b.tc_platform} ${b.caliber}`;
                const barrelSoldBtn = b.is_sold
                    ? `<span class="text-xs text-red-400 font-mono">Sold $${parseFloat(b.price_sold||0).toFixed(2)}</span>`
                    : `<button onclick="event.stopPropagation();openSellModal(${b.id},'${barrelLabel.replace(/'/g,"\\'")}','tc-barrel')" class="px-2 py-1 bg-gray-700 hover:bg-emerald-800 text-gray-300 hover:text-white text-xs font-bold rounded transition cursor-pointer">$ Sell</button>`;
                return `
                <div class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-xl flex flex-col hover:border-blue-400/60 transition cursor-pointer" onclick="window.location.href='tc-barrel-detail.html?id=${b.id}'">
                    ${gallery}
                    <div class="p-3 flex flex-col flex-1 gap-2">
                        <div class="flex justify-between items-center">
                            <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-950 text-blue-400 border border-blue-800">BARREL</span>
                            <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-950 text-amber-400 border border-amber-800">${b.caliber}</span>
                        </div>
                        <p class="text-sm font-bold text-white">${b.tc_platform} · ${b.caliber}</p>
                        <div class="text-xs text-gray-400 space-y-0.5">
                            ${b.barrel_length  ? `<p>Length: <span class="text-gray-200">${b.barrel_length}</span></p>` : ''}
                            ${b.twist_rate     ? `<p>Twist: <span class="text-gray-200 font-mono">${b.twist_rate}</span></p>` : ''}
                            ${b.hardware_color ? `<p>Finish: <span class="text-gray-200">${b.hardware_color}</span></p>` : ''}
                            ${flags ? `<p class="text-gray-500">${flags}</p>` : ''}
                        </div>
                        <div class="flex items-center gap-2 mt-auto pt-1 border-t border-gray-700">
                            ${barrelSoldBtn}
                            <div class="flex-1"></div>
                            <span class="text-xs text-gray-500 font-mono">$${parseFloat(b.price_paid || 0).toFixed(2)}</span>
                            <button onclick="event.stopPropagation();trashItem('tc-barrel',${b.id},'${barrelLabel.replace(/'/g,"\\'")}');" class="px-2 py-1 bg-gray-700 hover:bg-red-900 text-gray-400 hover:text-red-300 text-xs font-bold rounded transition cursor-pointer" title="Move to trash">🗑️</button>
                        </div>
                    </div>
                </div>`;
            }).join('');
        }
    } catch(err) {
        recContainer.innerHTML = '<p class="text-red-400 italic text-sm col-span-3">Failed to load TC inventory.</p>';
    }
}

function switchAddForm(formId) {
    document.querySelectorAll('.add-platform-form').forEach(f => f.classList.add('hidden'));
    document.getElementById({
        'add-general': 'firearm-form',
        'add-shotgun': 'shotgun-form',
        'add-handgun': 'handgun-form',
        'add-tc-receiver': 'tc-receiver-form',
        'add-tc-barrel': 'tc-barrel-form',
        'add-scope': 'add-scope-form',
    }[formId])?.classList.remove('hidden');

    const btnMap = { 'add-general': 'btn-add-general', 'add-shotgun': 'btn-add-shotgun', 'add-handgun': 'btn-add-handgun', 'add-tc-receiver': 'btn-add-tc-receiver', 'add-tc-barrel': 'btn-add-tc-barrel', 'add-scope': 'btn-add-scope' };
    Object.entries(btnMap).forEach(([key, btnId]) => {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        btn.className = key === formId
            ? "px-3 py-1.5 text-xs font-bold rounded bg-amber-600 text-white cursor-pointer"
            : "px-3 py-1.5 text-xs font-bold rounded text-gray-200 hover:text-white cursor-pointer";
    });
}

function switchAmmoFilter(type) {
    currentAmmoFilter = type;
    currentAmmoCaliberFilter = null;
    const inactive = "px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer";
    const factBtn = document.getElementById('ammo-btn-factory');
    const muzzBtn = document.getElementById('ammo-btn-muzzleloader');
    const handBtn = document.getElementById('ammo-btn-handload');
    if (factBtn) factBtn.className = type === 'factory'
        ? "px-3 py-1 rounded bg-gray-800 text-blue-400 cursor-pointer" : inactive;
    if (muzzBtn) muzzBtn.className = type === 'muzzleloader'
        ? "px-3 py-1 rounded bg-gray-800 text-yellow-500 cursor-pointer" : inactive;
    if (handBtn) handBtn.className = type === 'handload'
        ? "px-3 py-1 rounded bg-gray-800 text-amber-400 cursor-pointer" : inactive;
    loadAmmoInventory(type);
}

function switchAmmoCategory(cat) {
    currentAmmoCategoryFilter = cat;
    currentAmmoCaliberFilter = null;
    loadAmmoInventory('factory');
}

function switchAmmoCaliber(cal) {
    currentAmmoCaliberFilter = cal || null;
    loadAmmoInventory(currentAmmoFilter);
}

function switchComponentFilter(type) {
    currentComponentFilter = type;
    ['powders', 'primers', 'bullets', 'casings'].forEach(t => {
        const btn = document.getElementById(`comp-btn-${t}`);
        if (!btn) return;
        if (t === 'casings' && currentComponentMode === 'muzzleloader') return;
        btn.className = t === type
            ? "px-3 py-1 rounded bg-gray-800 text-emerald-400 cursor-pointer"
            : "px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer";
    });
    loadComponentInventory(type);
}

function switchComponentMode(mode) {
    currentComponentMode = mode;
    ['reloading', 'muzzleloader'].forEach(m => {
        const btn = document.getElementById(`comp-mode-${m}`);
        if (!btn) return;
        btn.className = m === mode
            ? "px-3 py-1 rounded bg-gray-800 text-amber-500 cursor-pointer"
            : "px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer";
    });
    const casingsBtn = document.getElementById('comp-btn-casings');
    if (casingsBtn) casingsBtn.classList.toggle('hidden', mode === 'muzzleloader');
    if (mode === 'muzzleloader' && currentComponentFilter === 'casings') {
        switchComponentFilter('powders');
    } else {
        loadComponentInventory(currentComponentFilter);
    }
}

async function loadComponentInventory(type) {
    const container = document.getElementById('components-container');
    if (!container) return;
    container.innerHTML = '<p class="text-gray-400 italic text-sm">Loading...</p>';
    refreshLowStockBanner();
    const isMuzzleloaderMode = currentComponentMode === 'muzzleloader';
    const mlParam = isMuzzleloaderMode ? '?muzzleloader=1' : '';
    try {
        const [res, settingsRes] = await Promise.all([
            fetch(`/components/${type}/${mlParam}`, { cache: 'no-store' }),
            fetch('/settings/', { cache: 'no-store' }),
        ]);
        let items = res.ok ? await res.json() : [];
        if (!isMuzzleloaderMode) items = items.filter(i => !i.is_muzzleloader);
        items = items.filter(matchesSearch);
        const settings = settingsRes.ok ? await settingsRes.json() : {};
        const thresholds = {
            primers: parseFloat(settings.low_stock_primers ?? 200),
            bullets: parseFloat(settings.low_stock_bullets ?? 100),
            casings: parseFloat(settings.low_stock_casings ?? 50),
        };
        const label = {powders:'Powder',primers:'Primer',bullets:'Bullet',casings:'Casing'}[type] || type;
        document.getElementById('inventory-count').innerText = `${items.length} ${label} Item${items.length !== 1 ? 's' : ''}`;
        if (items.length === 0) {
            container.innerHTML = `<p class="text-gray-500 italic text-sm">No ${type} logged yet. Use Add Inventory → Components.</p>`;
            return;
        }
        if (type === 'powders')  container.innerHTML = `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">${items.map(renderPowderCard).join('')}</div>`;
        if (type === 'primers')  container.innerHTML = `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">${items.map(p => renderPrimerCard(p, thresholds.primers)).join('')}</div>`;
        if (type === 'bullets')  renderBulletsGrouped(items, container, thresholds.bullets);
        if (type === 'casings')  container.innerHTML = `<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">${items.map(c => renderCasingCard(c, thresholds.casings)).join('')}</div>`;
    } catch(err) {
        container.innerHTML = '<p class="text-red-400 italic text-sm">Failed to load components.</p>';
    }
}

async function refreshLowStockBanner() {
    const banner = document.getElementById('low-stock-banner');
    const list = document.getElementById('low-stock-list');
    if (!banner || !list) return;
    try {
        const res = await fetch('/components/low-stock/');
        const items = res.ok ? await res.json() : [];
        if (items.length === 0) { banner.classList.add('hidden'); return; }
        const colors = { powder: 'bg-emerald-900/60 text-emerald-300 border-emerald-700', primer: 'bg-orange-900/60 text-orange-300 border-orange-700', bullet: 'bg-blue-900/60 text-blue-300 border-blue-700', casing: 'bg-purple-900/60 text-purple-300 border-purple-700' };
        list.innerHTML = items.map(i => `<span class="px-2 py-1 rounded border text-xs font-mono ${colors[i.type] || 'bg-gray-800 text-gray-300 border-gray-600'}">${i.label}: ${i.value}</span>`).join('');
        banner.classList.remove('hidden');
    } catch(_) {}
}

function makePhotoGallery(uid, emoji, img1, img2, fit = 'contain') {
    if (!img1 && !img2) {
        return `<div class="w-full h-48 bg-gray-950 flex items-center justify-center text-5xl">${emoji}</div>`;
    }
    const photos = [img1, img2].filter(Boolean);
    if (photos.length === 1) {
        return `<div class="w-full h-48 bg-gray-950 overflow-hidden"><img src="${photos[0]}" class="w-full h-full object-${fit}"></div>`;
    }
    return `
    <div class="w-full h-48 bg-gray-950 overflow-hidden relative group/gal" data-uid="${uid}" data-photos='${JSON.stringify(photos)}' data-idx="0"
         ontouchstart="_gTouchStart(event)" ontouchend="_gTouchEnd(event,'${uid}')">
        <img id="gimg-${uid}" src="${photos[0]}" class="w-full h-full object-${fit}">
        <button onclick="event.stopPropagation(); galleryNav('${uid}',-1)"
            class="absolute left-1 top-1/2 -translate-y-1/2 w-7 h-7 bg-black/50 hover:bg-black/80 rounded-full text-white text-sm flex items-center justify-center cursor-pointer opacity-0 group-hover/gal:opacity-100 transition-opacity">&lsaquo;</button>
        <button onclick="event.stopPropagation(); galleryNav('${uid}',1)"
            class="absolute right-1 top-1/2 -translate-y-1/2 w-7 h-7 bg-black/50 hover:bg-black/80 rounded-full text-white text-sm flex items-center justify-center cursor-pointer opacity-0 group-hover/gal:opacity-100 transition-opacity">&rsaquo;</button>
        <div class="absolute bottom-2 right-2 flex gap-1.5">
            <span id="gdot-${uid}-0" class="w-2 h-2 rounded-full bg-white shadow border border-gray-400"></span>
            <span id="gdot-${uid}-1" class="w-2 h-2 rounded-full bg-white/40 shadow border border-gray-400"></span>
        </div>
    </div>`;
}

let _gTouchX = 0;
function _gTouchStart(e) { _gTouchX = e.touches[0].clientX; }
function _gTouchEnd(e, uid) {
    const dx = e.changedTouches[0].clientX - _gTouchX;
    if (Math.abs(dx) > 40) { galleryNav(uid, dx < 0 ? 1 : -1); }
}

function galleryNav(uid, dir) {
    const wrap = document.querySelector(`[data-uid="${uid}"]`);
    if (!wrap) return;
    const photos = JSON.parse(wrap.dataset.photos);
    let idx = parseInt(wrap.dataset.idx) + dir;
    if (idx < 0) idx = photos.length - 1;
    if (idx >= photos.length) idx = 0;
    wrap.dataset.idx = idx;
    const img = document.getElementById(`gimg-${uid}`);
    if (img) img.src = photos[idx];
    photos.forEach((_, i) => {
        const d = document.getElementById(`gdot-${uid}-${i}`);
        if (d) { d.classList.toggle('bg-white', i === idx); d.classList.toggle('bg-white/40', i !== idx); }
    });
}

function gallerySw(uid, src, idx) {
    const img = document.getElementById(`gimg-${uid}`);
    if (img) img.src = src;
    const wrap = document.querySelector(`[data-uid="${uid}"]`);
    if (wrap) wrap.dataset.idx = idx;
    [0,1].forEach(i => {
        const d = document.getElementById(`gdot-${uid}-${i}`);
        if (d) { d.classList.toggle('bg-white', i === idx); d.classList.toggle('bg-white/40', i !== idx); }
    });
}

function renderPowderCard(p) {
    const gallery = makePhotoGallery(`pow-${p.id}`, '🧪', p.image_path, p.image_path_2);
    return `
    <div class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-lg hover:border-emerald-500/50 transition">
        ${gallery}
        <div class="p-4 space-y-3">
            <div class="flex justify-between items-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">POWDER</span>
                <div class="flex items-center gap-2">
                    <button onclick="document.getElementById('cedit-pow-${p.id}').classList.toggle('hidden')" class="text-gray-500 hover:text-emerald-400 text-xs cursor-pointer" title="Edit">✏️</button>
                    <button onclick="deleteComponent('powders',${p.id})" class="text-gray-600 hover:text-red-400 text-xs cursor-pointer">✕</button>
                </div>
            </div>
            <!-- inline edit panel -->
            <div id="cedit-pow-${p.id}" class="hidden bg-gray-900/80 rounded-lg p-3 space-y-2 border border-emerald-800/40">
                <p class="text-[10px] font-bold uppercase tracking-wider text-emerald-400 mb-1">Edit Powder</p>
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Brand</label>
                        <input id="cef-pow-${p.id}-brand" type="text" value="${escHtml(p.brand||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-emerald-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Name / Model</label>
                        <input id="cef-pow-${p.id}-name" type="text" value="${escHtml(p.name||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-emerald-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Qty on Hand</label>
                        <input id="cef-pow-${p.id}-weight_lbs" type="number" step="any" min="0" value="${p.weight_lbs??0}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-emerald-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Price Paid ($)</label>
                        <input id="cef-pow-${p.id}-price_paid" type="number" step="0.01" min="0" value="${p.price_paid||0}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-emerald-500">
                    </div>
                    <div class="col-span-2 flex items-center gap-2 pt-1">
                        <input id="cef-pow-${p.id}-pellet_mode" type="checkbox" ${p.pellet_mode ? 'checked' : ''} class="accent-blue-400 cursor-pointer">
                        <label for="cef-pow-${p.id}-pellet_mode" class="text-[10px] text-gray-300 cursor-pointer">Count mode (qty) — pellets / firesticks</label>
                    </div>
                    <div class="col-span-2">
                        <label class="text-xs text-gray-200 font-semibold">Notes</label>
                        <input id="cef-pow-${p.id}-notes" type="text" value="${escHtml(p.notes||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-emerald-500">
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="document.getElementById('cedit-pow-${p.id}').classList.add('hidden')" class="flex-1 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold rounded cursor-pointer">Cancel</button>
                    <button onclick="saveCompEdit('powders','pow',${p.id},['brand','name','weight_lbs','pellet_mode','price_paid','notes'])" class="flex-1 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-bold rounded cursor-pointer">Save Changes</button>
                </div>
            </div>
            <div class="flex justify-between items-center gap-2">
                <p class="text-base font-bold text-white">${p.brand} ${p.name}</p>
                <span class="text-xs text-gray-400 font-mono whitespace-nowrap">$${parseFloat(p.price_paid||0).toFixed(2)}</span>
            </div>
            <div class="bg-gray-900/60 rounded-lg p-3 text-center">
                <p class="text-2xl font-bold font-mono text-emerald-400">${p.weight_lbs ?? 0} <span class="text-sm text-gray-400">${p.pellet_mode ? 'qty' : 'lbs'}</span></p>
                <p class="text-xs text-gray-200 font-semibold uppercase tracking-wider mt-0.5">On Hand</p>
            </div>
            <div class="border-t border-gray-700 pt-2 space-y-1">
                ${p.notes ? `<p class="text-xs text-gray-500 italic">${p.notes}</p>` : ''}
            </div>
            <div class="flex gap-2">
                <input type="number" step="${p.pellet_mode ? '1' : '0.01'}" placeholder="${p.pellet_mode ? 'Update qty' : 'Update lbs'}" id="qty-powder-${p.id}"
                    class="flex-1 bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                <button onclick="updateComponentQty('powders',${p.id},'weight_lbs')" class="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-bold rounded cursor-pointer">Save</button>
            </div>
            <div class="border-t border-gray-700 pt-2">
                <div class="flex items-center justify-between gap-1">
                    <button onclick="toggleCompMuzzleloader('powders',${p.id},${!!p.is_muzzleloader})"
                        class="text-[10px] font-bold px-2 py-0.5 rounded border cursor-pointer transition ${p.is_muzzleloader ? 'bg-amber-900/60 text-amber-400 border-amber-700 hover:bg-amber-900/40' : 'bg-gray-700/40 text-gray-500 border-gray-700 hover:text-amber-400'}">
                        🏹 ${p.is_muzzleloader ? 'Muzzleloader ✓' : 'Muzzleloader'}
                    </button>
                    <button onclick="togglePowderPelletMode(${p.id},${!!p.pellet_mode})"
                        class="text-[10px] font-bold px-2 py-0.5 rounded border cursor-pointer transition ${p.pellet_mode ? 'bg-blue-900/60 text-blue-300 border-blue-700 hover:bg-blue-900/40' : 'bg-gray-700/40 text-gray-500 border-gray-700 hover:text-blue-300'}">
                        # ${p.pellet_mode ? 'Count ✓' : 'Count'}
                    </button>
                    <button onclick="document.getElementById('comp-photos-pow-${p.id}').classList.toggle('hidden')" class="text-xs text-gray-200 font-semibold hover:text-gray-300 cursor-pointer ml-auto">📷 Photos</button>
                </div>
                <div id="comp-photos-pow-${p.id}" class="hidden mt-2 space-y-2">
                    ${p.image_path && p.image_path_2 ? `<button onclick="swapCompPhotos('powders',${p.id})" class="text-[10px] text-amber-500 hover:text-amber-400 cursor-pointer">⭐ Make Photo 2 the Primary</button>` : ''}
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-xs text-gray-200 font-semibold">Replace Photo 1</label>
                            <div class="flex gap-1 mt-0.5">
                                <button type="button" onclick="document.getElementById('cpow1-cam-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">📷</button>
                                <button type="button" onclick="document.getElementById('cpow1-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">🖼</button>
                            </div>
                            <input type="file" id="cpow1-${p.id}" accept="image/*" class="hidden">
                            <input type="file" capture="environment" accept="image/*" id="cpow1-cam-${p.id}" onchange="_camToInput('cpow1-cam-${p.id}','cpow1-${p.id}')" class="hidden">
                        </div>
                        <div>
                            <label class="text-xs text-gray-200 font-semibold">Replace Photo 2</label>
                            <div class="flex gap-1 mt-0.5">
                                <button type="button" onclick="document.getElementById('cpow2-cam-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">📷</button>
                                <button type="button" onclick="document.getElementById('cpow2-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">🖼</button>
                            </div>
                            <input type="file" id="cpow2-${p.id}" accept="image/*" class="hidden">
                            <input type="file" capture="environment" accept="image/*" id="cpow2-cam-${p.id}" onchange="_camToInput('cpow2-cam-${p.id}','cpow2-${p.id}')" class="hidden">
                        </div>
                    </div>
                    <button onclick="uploadCompPhotos('powders','pow',${p.id})" class="w-full text-[10px] bg-gray-700 hover:bg-gray-600 text-gray-300 py-1 rounded cursor-pointer">Save Photos</button>
                </div>
            </div>
        </div>
    </div>`;
}

function renderPrimerCard(p, lowThreshold = 200) {
    const low = p.quantity < lowThreshold;
    const qtyColor = low ? 'text-red-400' : 'text-orange-400';
    const gallery = makePhotoGallery(`pri-${p.id}`, '🔥', p.image_path, p.image_path_2);
    return `
    <div class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-lg hover:border-orange-500/50 transition">
        ${gallery}
        <div class="p-4 space-y-3">
            <div class="flex justify-between items-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-orange-950 text-orange-400 border border-orange-800">PRIMER</span>
                <div class="flex items-center gap-2">
                    <button onclick="document.getElementById('cedit-pri-${p.id}').classList.toggle('hidden')" class="text-gray-500 hover:text-orange-400 text-xs cursor-pointer" title="Edit">✏️</button>
                    <button onclick="deleteComponent('primers',${p.id})" class="text-gray-600 hover:text-red-400 text-xs cursor-pointer">✕</button>
                </div>
            </div>
            <!-- inline edit panel -->
            <div id="cedit-pri-${p.id}" class="hidden bg-gray-900/80 rounded-lg p-3 space-y-2 border border-orange-800/40">
                <p class="text-[10px] font-bold uppercase tracking-wider text-orange-400 mb-1">Edit Primer</p>
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Brand</label>
                        <input id="cef-pri-${p.id}-brand" type="text" value="${escHtml(p.brand||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-orange-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Model / Number</label>
                        <input id="cef-pri-${p.id}-model" type="text" value="${escHtml(p.model||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-orange-500">
                    </div>
                    <div class="col-span-2">
                        <label class="text-xs text-gray-200 font-semibold">Primer Type</label>
                        <input id="cef-pri-${p.id}-primer_type" type="text" value="${escHtml(p.primer_type||'')}" placeholder="e.g. Large Rifle, Small Pistol..." class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-orange-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Price Paid ($)</label>
                        <input id="cef-pri-${p.id}-price_paid" type="number" step="0.01" min="0" value="${p.price_paid||0}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-orange-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Notes</label>
                        <input id="cef-pri-${p.id}-notes" type="text" value="${escHtml(p.notes||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-orange-500">
                    </div>
                    <div class="col-span-2 flex items-center gap-2 pt-1">
                        <input id="cef-pri-${p.id}-is_muzzleloader" type="checkbox" ${p.is_muzzleloader ? 'checked' : ''} class="accent-amber-400 cursor-pointer">
                        <label for="cef-pri-${p.id}-is_muzzleloader" class="text-[10px] text-gray-300 cursor-pointer">🏹 Muzzleloader primer</label>
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="document.getElementById('cedit-pri-${p.id}').classList.add('hidden')" class="flex-1 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold rounded cursor-pointer">Cancel</button>
                    <button onclick="saveCompEdit('primers','pri',${p.id},['brand','model','primer_type','price_paid','notes','is_muzzleloader'])" class="flex-1 py-1.5 bg-orange-700 hover:bg-orange-600 text-white text-xs font-bold rounded cursor-pointer">Save Changes</button>
                </div>
            </div>
            <div class="flex justify-between items-center gap-2">
                <div>
                    <p class="text-base font-bold text-white">${p.brand}</p>
                    <p class="text-sm text-orange-400">${p.primer_type}</p>
                </div>
                <span class="text-xs text-gray-400 font-mono whitespace-nowrap">$${parseFloat(p.price_paid||0).toFixed(2)}</span>
            </div>
            <div class="bg-gray-900/60 rounded-lg p-3 text-center">
                <p class="text-2xl font-bold font-mono ${qtyColor}">${(p.quantity??0).toLocaleString()} <span class="text-sm text-gray-400">count</span></p>
                <p class="text-xs text-gray-200 font-semibold uppercase tracking-wider mt-0.5">${low ? '⚠️ Low Stock' : 'On Hand'}</p>
            </div>
            <div class="border-t border-gray-700 pt-2 space-y-1">
                ${p.notes ? `<p class="text-xs text-gray-500 italic">${p.notes}</p>` : ''}
            </div>
            <div class="flex gap-2">
                <input type="number" placeholder="Update count" id="qty-primer-${p.id}"
                    class="flex-1 bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                <button onclick="updateComponentQty('primers',${p.id},'quantity')" class="px-3 py-1.5 bg-orange-700 hover:bg-orange-600 text-white text-xs font-bold rounded cursor-pointer">Save</button>
            </div>
            <div class="border-t border-gray-700 pt-2">
                <div class="flex items-center justify-between">
                    <button onclick="toggleCompMuzzleloader('primers',${p.id},${!!p.is_muzzleloader})"
                        class="text-[10px] font-bold px-2 py-0.5 rounded border cursor-pointer transition ${p.is_muzzleloader ? 'bg-amber-900/60 text-amber-400 border-amber-700 hover:bg-amber-900/40' : 'bg-gray-700/40 text-gray-500 border-gray-700 hover:text-amber-400'}">
                        🏹 ${p.is_muzzleloader ? 'Muzzleloader ✓' : 'Muzzleloader'}
                    </button>
                    <button onclick="document.getElementById('comp-photos-pri-${p.id}').classList.toggle('hidden')" class="text-xs text-gray-200 font-semibold hover:text-gray-300 cursor-pointer">📷 Photos</button>
                </div>
                <div id="comp-photos-pri-${p.id}" class="hidden mt-2 space-y-2">
                    ${p.image_path && p.image_path_2 ? `<button onclick="swapCompPhotos('primers',${p.id})" class="text-[10px] text-amber-500 hover:text-amber-400 cursor-pointer">⭐ Make Photo 2 the Primary</button>` : ''}
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-xs text-gray-200 font-semibold">Replace Photo 1</label>
                            <div class="flex gap-1 mt-0.5">
                                <button type="button" onclick="document.getElementById('cpri1-cam-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">📷</button>
                                <button type="button" onclick="document.getElementById('cpri1-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">🖼</button>
                            </div>
                            <input type="file" id="cpri1-${p.id}" accept="image/*" class="hidden">
                            <input type="file" capture="environment" accept="image/*" id="cpri1-cam-${p.id}" onchange="_camToInput('cpri1-cam-${p.id}','cpri1-${p.id}')" class="hidden">
                        </div>
                        <div>
                            <label class="text-xs text-gray-200 font-semibold">Replace Photo 2</label>
                            <div class="flex gap-1 mt-0.5">
                                <button type="button" onclick="document.getElementById('cpri2-cam-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">📷</button>
                                <button type="button" onclick="document.getElementById('cpri2-${p.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">🖼</button>
                            </div>
                            <input type="file" id="cpri2-${p.id}" accept="image/*" class="hidden">
                            <input type="file" capture="environment" accept="image/*" id="cpri2-cam-${p.id}" onchange="_camToInput('cpri2-cam-${p.id}','cpri2-${p.id}')" class="hidden">
                        </div>
                    </div>
                    <button onclick="uploadCompPhotos('primers','pri',${p.id})" class="w-full text-[10px] bg-gray-700 hover:bg-gray-600 text-gray-300 py-1 rounded cursor-pointer">Save Photos</button>
                </div>
            </div>
        </div>
    </div>`;
}

function renderBulletCard(b, lowThreshold = 100) {
    const low = b.quantity < lowThreshold;
    const qtyColor = low ? 'text-red-400' : 'text-blue-400';
    const bcInfo = b.bc_g1 ? `G1: ${b.bc_g1}` : (b.bc_g7 ? `G7: ${b.bc_g7}` : '');
    const gallery = makePhotoGallery(`bul-${b.id}`, '🎯', b.image_path, b.image_path_2);
    return `
    <div class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-lg hover:border-blue-500/50 transition cursor-pointer" onclick="window.location.href='bullet-detail.html?id=${b.id}'">
        ${gallery}
        <div class="p-3 space-y-2">
            <div class="flex justify-between items-center">
                <div class="flex items-center gap-1">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-950 text-blue-400 border border-blue-800">BULLET</span>
                    ${b.load_data_count ? `<span class="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">LOAD DATA</span>` : ''}
                </div>
                <span class="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-950 text-amber-400 border border-amber-800">${b.weight_gr}gr</span>
            </div>
            <div class="flex justify-between items-start gap-2">
                <div>
                    <p class="text-sm font-bold text-white">${b.brand}${b.product_line ? ' · '+b.product_line : ''}</p>
                    ${b.bullet_type ? `<p class="text-[11px] text-gray-400">${b.bullet_type}</p>` : ''}
                </div>
                <span class="text-xs text-gray-400 font-mono whitespace-nowrap">$${parseFloat(b.price_paid||0).toFixed(2)}</span>
            </div>
            <div class="flex justify-between items-center">
                <span class="text-sm font-bold font-mono ${qtyColor}">${(b.quantity??0).toLocaleString()} <span class="text-[10px] text-gray-500">ct</span></span>
                ${low ? '<span class="text-[10px] text-red-400 font-bold">LOW STOCK</span>' : ''}
            </div>
        </div>
    </div>`;
}

function renderCasingCard(c, lowThreshold = 50) {
    const low = c.quantity < lowThreshold;
    const qtyColor = low ? 'text-red-400' : 'text-purple-400';
    const conditionBadge = c.times_fired === 0
        ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">NEW</span>`
        : `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-400 border border-amber-800">${c.times_fired}x FIRED</span>`;
    const gallery = makePhotoGallery(`cas-${c.id}`, '💊', c.image_path, c.image_path_2);
    return `
    <div class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-lg hover:border-purple-500/50 transition">
        ${gallery}
        <div class="p-4 space-y-3">
            <div class="flex justify-between items-center">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-950 text-purple-400 border border-purple-800">CASING</span>
                <div class="flex items-center gap-2">
                    <button onclick="document.getElementById('cedit-cas-${c.id}').classList.toggle('hidden')" class="text-gray-500 hover:text-purple-400 text-xs cursor-pointer" title="Edit">✏️</button>
                    <button onclick="deleteComponent('casings',${c.id})" class="text-gray-600 hover:text-red-400 text-xs cursor-pointer">✕</button>
                </div>
            </div>
            <!-- inline edit panel -->
            <div id="cedit-cas-${c.id}" class="hidden bg-gray-900/80 rounded-lg p-3 space-y-2 border border-purple-800/40">
                <p class="text-[10px] font-bold uppercase tracking-wider text-purple-400 mb-1">Edit Casing</p>
                <div class="grid grid-cols-2 gap-2">
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Brand</label>
                        <input id="cef-cas-${c.id}-brand" type="text" value="${escHtml(c.brand||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-purple-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Caliber</label>
                        <input id="cef-cas-${c.id}-caliber" type="text" value="${escHtml(c.caliber||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-purple-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Times Fired</label>
                        <input id="cef-cas-${c.id}-times_fired" type="number" step="1" min="0" value="${c.times_fired??0}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-purple-500">
                    </div>
                    <div>
                        <label class="text-xs text-gray-200 font-semibold">Price Paid ($)</label>
                        <input id="cef-cas-${c.id}-price_paid" type="number" step="0.01" min="0" value="${c.price_paid||0}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-purple-500">
                    </div>
                    <div class="col-span-2">
                        <label class="text-xs text-gray-200 font-semibold">Notes</label>
                        <input id="cef-cas-${c.id}-notes" type="text" value="${escHtml(c.notes||'')}" class="w-full bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-purple-500">
                    </div>
                </div>
                <div class="flex gap-2">
                    <button onclick="document.getElementById('cedit-cas-${c.id}').classList.add('hidden')" class="flex-1 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold rounded cursor-pointer">Cancel</button>
                    <button onclick="saveCompEdit('casings','cas',${c.id},['brand','caliber','times_fired','price_paid','notes'])" class="flex-1 py-1.5 bg-purple-700 hover:bg-purple-600 text-white text-xs font-bold rounded cursor-pointer">Save Changes</button>
                </div>
            </div>
            <div class="flex justify-between items-start gap-2">
                <div>
                    <p class="text-base font-bold text-white">${c.brand}</p>
                    <div class="flex items-center gap-2 mt-1">
                        <p class="text-sm text-purple-400">${c.caliber}</p>
                        ${conditionBadge}
                    </div>
                </div>
                <span class="text-xs text-gray-400 font-mono whitespace-nowrap">$${parseFloat(c.price_paid||0).toFixed(2)}</span>
            </div>
            <div class="bg-gray-900/60 rounded-lg p-3 text-center">
                <p class="text-2xl font-bold font-mono ${qtyColor}">${(c.quantity??0).toLocaleString()} <span class="text-sm text-gray-400">count</span></p>
                <p class="text-xs text-gray-200 font-semibold uppercase tracking-wider mt-0.5">${low ? '⚠️ Low Stock' : 'On Hand'}</p>
            </div>
            <div class="border-t border-gray-700 pt-2 space-y-1">
                ${c.notes ? `<p class="text-xs text-gray-500 italic">${c.notes}</p>` : ''}
            </div>
            <div class="flex gap-2">
                <input type="number" placeholder="Update count" id="qty-casing-${c.id}"
                    class="flex-1 bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                <button onclick="updateComponentQty('casings',${c.id},'quantity')" class="px-3 py-1.5 bg-purple-700 hover:bg-purple-600 text-white text-xs font-bold rounded cursor-pointer">Save</button>
            </div>
            <div class="border-t border-gray-700 pt-2">
                <button onclick="document.getElementById('comp-photos-cas-${c.id}').classList.toggle('hidden')" class="text-xs text-gray-200 font-semibold hover:text-gray-300 cursor-pointer">📷 Manage Photos</button>
                <div id="comp-photos-cas-${c.id}" class="hidden mt-2 space-y-2">
                    ${c.image_path && c.image_path_2 ? `<button onclick="swapCompPhotos('casings',${c.id})" class="text-[10px] text-amber-500 hover:text-amber-400 cursor-pointer">⭐ Make Photo 2 the Primary</button>` : ''}
                    <div class="grid grid-cols-2 gap-2">
                        <div>
                            <label class="text-xs text-gray-200 font-semibold">Replace Photo 1</label>
                            <div class="flex gap-1 mt-0.5">
                                <button type="button" onclick="document.getElementById('ccas1-cam-${c.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">📷</button>
                                <button type="button" onclick="document.getElementById('ccas1-${c.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">🖼</button>
                            </div>
                            <input type="file" id="ccas1-${c.id}" accept="image/*" class="hidden">
                            <input type="file" capture="environment" accept="image/*" id="ccas1-cam-${c.id}" onchange="_camToInput('ccas1-cam-${c.id}','ccas1-${c.id}')" class="hidden">
                        </div>
                        <div>
                            <label class="text-xs text-gray-200 font-semibold">Replace Photo 2</label>
                            <div class="flex gap-1 mt-0.5">
                                <button type="button" onclick="document.getElementById('ccas2-cam-${c.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">📷</button>
                                <button type="button" onclick="document.getElementById('ccas2-${c.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-0.5 rounded cursor-pointer">🖼</button>
                            </div>
                            <input type="file" id="ccas2-${c.id}" accept="image/*" class="hidden">
                            <input type="file" capture="environment" accept="image/*" id="ccas2-cam-${c.id}" onchange="_camToInput('ccas2-cam-${c.id}','ccas2-${c.id}')" class="hidden">
                        </div>
                    </div>
                    <button onclick="uploadCompPhotos('casings','cas',${c.id})" class="w-full text-[10px] bg-gray-700 hover:bg-gray-600 text-gray-300 py-1 rounded cursor-pointer">Save Photos</button>
                </div>
            </div>
        </div>
    </div>`;
}

function renderBulletsGrouped(bullets, container, lowThreshold = 100) {
    const groups = {};
    bullets.forEach(b => {
        const cal = b.caliber || 'Unknown';
        if (!groups[cal]) groups[cal] = [];
        groups[cal].push(b);
    });
    container.innerHTML = Object.entries(groups).sort(([a],[b]) => a.localeCompare(b)).map(([cal, items]) => `
        <div class="mb-8">
            <div class="flex items-center gap-3 mb-3">
                <span class="text-xs font-bold uppercase tracking-wider text-amber-500 font-mono">${cal}</span>
                <span class="text-xs text-gray-200 font-semibold">${items.length} variant${items.length !== 1 ? 's' : ''}</span>
                <div class="flex-1 border-t border-gray-700/60"></div>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                ${items.map(b => renderBulletCard(b, lowThreshold)).join('')}
            </div>
        </div>`
    ).join('');
}

async function saveTCReceiverEdit(id) {
    try {
        await fetch(`/tc-receivers/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                platform: document.getElementById(`rcedit-plat-${id}`)?.value,
                serial_number: document.getElementById(`rcedit-sn-${id}`)?.value.trim(),
                notes: document.getElementById(`rcedit-notes-${id}`)?.value.trim(),
                price_paid: parseFloat(document.getElementById(`rcedit-price-${id}`)?.value) || 0,
            }),
        });
        for (const slot of [1, 2]) {
            const file = document.getElementById(`rcedit-p${slot}-${id}`)?.files[0];
            if (file) {
                const fd = new FormData();
                fd.append('image', file);
                fd.append('slot', String(slot));
                await fetch(`/tc-receivers/${id}/update-photo/`, { method: 'POST', body: fd });
            }
        }
        showToast('Receiver updated.');
        loadTCInventory();
    } catch { showToast('Failed to save receiver.', 'error'); }
}


function openQuickAdd(section) {
    switchTab('add-tab');
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (section === 'platforms') {
        const formMap = { general: 'add-general', shotgun: 'add-shotgun', handgun: 'add-handgun', tc: 'add-tc-receiver' };
        switchFormCategory('cat-platforms');
        switchAddForm(formMap[currentPlatformTab] || 'add-general');
    } else if (section === 'optics') {
        switchFormCategory('cat-platforms');
        switchAddForm('add-scope');
    } else if (section === 'ammo') {
        switchFormCategory('cat-ammunition');
        toggleAmmoType(currentAmmoFilter === 'handload' ? 'handloads' : 'factory');
    } else if (section === 'components') {
        const formMap = { powders: 'add-powder', primers: 'add-primer', bullets: 'add-bullet-comp', casings: 'add-casing' };
        switchFormCategory('cat-components');
        switchAddComponent(formMap[currentComponentFilter] || 'add-powder');
    }
}

async function saveScopeEdit(scopeId) {
    const brand = document.getElementById(`sedit-brand-${scopeId}`)?.value.trim();
    const model = document.getElementById(`sedit-model-${scopeId}`)?.value.trim();
    const magnification = document.getElementById(`sedit-mag-${scopeId}`)?.value.trim();
    const units = document.getElementById(`sedit-units-${scopeId}`)?.value;
    const price_paid = parseFloat(document.getElementById(`sedit-price-${scopeId}`)?.value) || 0;
    const quantity = parseInt(document.getElementById(`sedit-qty-${scopeId}`)?.value) || 1;
    try {
        await fetch(`/scopes/${scopeId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brand, model, magnification, units, price_paid, quantity }),
        });
        showToast('Scope updated.');
        loadScopes();
    } catch { showToast('Failed to save scope.', 'error'); }
}

async function swapCompPhotos(type, id) {
    try {
        await fetch(`/components/${type}/${id}/swap-photos/`, { method: 'POST' });
        showToast('Primary photo updated.');
        const reloadMap = { powders: 'powders', primers: 'primers', bullets: 'bullets', casings: 'casings' };
        if (reloadMap[type]) switchComponentFilter(reloadMap[type]);
    } catch { showToast('Failed to swap photos.', 'error'); }
}

async function uploadCompPhotos(type, prefix, id) {
    try {
        for (const slot of [1, 2]) {
            const file = document.getElementById(`c${prefix}${slot}-${id}`)?.files[0];
            if (file) {
                const fd = new FormData();
                fd.append('image', file);
                fd.append('slot', String(slot));
                await fetch(`/components/${type}/${id}/update-photo/`, { method: 'POST', body: fd });
            }
        }
        showToast('Photos saved.');
        switchComponentFilter(type);
    } catch { showToast('Failed to upload photos.', 'error'); }
}

async function updateComponentQty(type, id, field) {
    const inputId = `qty-${type.slice(0,-1)}-${id}`;
    const input = document.getElementById(inputId);
    if (!input || input.value === '') return;
    const val = field === 'quantity' ? parseInt(input.value) : parseFloat(input.value);
    try {
        const res = await fetch(`/components/${type}/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: val })
        });
        if (res.ok) { showToast('Updated.'); loadComponentInventory(type); }
        else showToast('Update failed.', 'error');
    } catch(_) { showToast('Error updating.', 'error'); }
}

async function deleteComponent(type, id) {
    if (!confirm('Delete this component record?')) return;
    try {
        const res = await fetch(`/components/${type}/${id}`, { method: 'DELETE' });
        if (res.ok) { showToast('Deleted.'); loadComponentInventory(type); }
        else showToast('Delete failed.', 'error');
    } catch(_) { showToast('Error deleting.', 'error'); }
}

async function toggleCompMuzzleloader(type, id, current) {
    try {
        const res = await fetch(`/components/${type}/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_muzzleloader: !current }),
        });
        if (res.ok) {
            showToast(!current ? 'Marked as muzzleloader.' : 'Removed muzzleloader tag.');
            loadComponentInventory(currentComponentFilter);
        } else showToast('Failed to update.', 'error');
    } catch(_) { showToast('Error updating.', 'error'); }
}

async function saveCompEdit(type, shortType, id, fields) {
    const payload = {};
    fields.forEach(field => {
        const el = document.getElementById(`cef-${shortType}-${id}-${field}`);
        if (!el) return;
        if (el.type === 'checkbox') {
            payload[field] = el.checked;
        } else if (el.type === 'number') {
            const v = parseFloat(el.value);
            payload[field] = isNaN(v) ? null : v;
        } else {
            payload[field] = el.value.trim() || null;
        }
    });
    try {
        const res = await fetch(`/components/${type}/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (res.ok) {
            showToast('Saved.');
            currentComponentFilter = type;
            loadComponentInventory(type);
        } else showToast('Save failed.', 'error');
    } catch(_) { showToast('Error saving.', 'error'); }
}

async function togglePowderPelletMode(id, current) {
    try {
        const res = await fetch(`/components/powders/${id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pellet_mode: !current }),
        });
        if (res.ok) {
            showToast(!current ? 'Switched to count (qty) mode.' : 'Switched to weight (lbs) mode.');
            loadComponentInventory(currentComponentFilter);
        } else showToast('Failed to update.', 'error');
    } catch(_) { showToast('Error updating.', 'error'); }
}

async function loadScopes() {
    const container = document.getElementById('scopes-container');
    if (!container) return;
    container.innerHTML = '<p class="text-gray-400 col-span-3 italic text-sm">Loading optics...</p>';

    try {
        const res = await fetch('/scopes/');
        const raw = res.ok ? await res.json() : [];
        const scopes = applySortFn(raw.filter(matchesSearch), currentOpticSort);
        document.getElementById('inventory-count').innerText = `${scopes.length} Optic${scopes.length !== 1 ? 's' : ''} Registered`;

        if (scopes.length === 0) {
            container.innerHTML = '<p class="text-gray-500 col-span-3 italic text-sm">No optics registered. Add one via the Add Inventory form.</p>';
            return;
        }
        container.innerHTML = scopes.map(renderScopeCard).join('');
    } catch(err) {
        container.innerHTML = '<p class="text-red-400 col-span-3 italic text-sm">Failed to load optics.</p>';
    }
}

function renderScopeCard(s) {
    const gallery = makePhotoGallery(`scp-${s.id}`, '🔭', s.image_path, s.image_path_2);
    const qty = s.quantity || 1;
    const mounts = s.mounts || [];
    const mountCount = mounts.length;
    const slotsLeft = qty - mountCount;
    const photoCount = (s.image_path ? 1 : 0) + (s.image_path_2 ? 1 : 0);
    const firstMount = mounts[0] || null;

    const qtyBadge = qty > 1
        ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950 text-amber-400 border border-amber-800">QTY: ${qty}</span>`
        : '';

    // Mounts section
    let mountsHtml;
    if (qty === 1) {
        const mountLabel = firstMount
            ? `<span class="text-emerald-400 font-medium">${firstMount.label}</span>`
            : `<span class="text-gray-500 italic">Unmounted</span>`;
        mountsHtml = `<p class="text-xs text-gray-400">📍 ${mountLabel}</p>`;
    } else {
        const mountItems = mounts.map(m => `
            <div class="flex items-center justify-between gap-1">
                <span class="text-xs text-emerald-400 truncate min-w-0">📍 ${m.label}</span>
                <button onclick="removeScopeMount(${s.id},'${m.type}',${m.id})"
                    class="shrink-0 text-[10px] px-1.5 py-0.5 bg-gray-700 hover:bg-red-900 text-gray-400 hover:text-red-300 rounded cursor-pointer transition" title="Uninstall">✕</button>
            </div>`).join('');
        const openSlots = slotsLeft > 0
            ? `<p class="text-xs text-gray-600 italic">${slotsLeft} open slot${slotsLeft > 1 ? 's' : ''}</p>` : '';
        mountsHtml = `<div class="space-y-1">
            <p class="text-xs text-gray-200 font-semibold font-mono">${mountCount}/${qty} installed</p>
            ${mountItems}${openSlots}
        </div>`;
    }

    // Action buttons
    const changeMountBtn = qty === 1 ? `
        <button onclick="openScopeMountEditor(${s.id})"
            class="flex-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold rounded transition cursor-pointer">
            ${firstMount ? '🔄 Change Mount' : '📍 Mount Scope'}
        </button>` : '';
    const addInstallBtn = (qty > 1 && slotsLeft > 0) ? `
        <button id="scope-add-install-btn-${s.id}" onclick="openAddScopeMount(${s.id})"
            class="flex-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold rounded transition cursor-pointer">
            📍 Add Install
        </button>` : '';

    // Add-mount editor (for multi-qty scopes)
    const addMountEditor = qty > 1 ? `
        <div id="scope-add-mount-editor-${s.id}" class="hidden border-t border-gray-600 pt-3 space-y-2">
            <p class="text-xs text-gray-400 font-medium">Install on platform:</p>
            <select id="scope-add-mount-sel-${s.id}" class="w-full bg-gray-700 border border-gray-600 rounded p-2 text-xs text-white focus:outline-none">
                <option value="">Loading…</option>
            </select>
            <div class="flex gap-2">
                <button onclick="saveAddScopeMount(${s.id})" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold py-1.5 rounded transition cursor-pointer">Install</button>
                <button onclick="closeAddScopeMount(${s.id})" class="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold py-1.5 rounded transition cursor-pointer">Cancel</button>
            </div>
        </div>` : '';

    return `
    <div id="scope-card-${s.id}"
        data-mount-type="${firstMount ? firstMount.type : ''}"
        data-mount-id="${firstMount ? firstMount.id : ''}"
        class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-xl">
        <div onclick="window.location.href='scope-detail.html?id=${s.id}'" class="cursor-pointer">${gallery}</div>
        <div class="p-4 space-y-2">
            <div class="flex justify-between items-center">
                <div class="flex items-center gap-1">
                    <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-950 text-blue-400 border border-blue-800">OPTIC</span>
                    ${qtyBadge}
                </div>
                <div class="flex items-center gap-1">
                    <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-gray-900 text-gray-300 border border-gray-700">${s.units || 'MOA'}</span>
                    <button onclick="toggleScopeEditPanel(${s.id})" title="Edit scope" class="p-1 rounded bg-gray-700 hover:bg-amber-600 text-gray-400 hover:text-white transition cursor-pointer">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z"/></svg>
                    </button>
                    <button onclick="toggleScopePhotoPanel(${s.id})" title="Update photos" class="p-1 rounded bg-gray-700 hover:bg-blue-600 text-gray-400 hover:text-white transition cursor-pointer text-sm leading-none">📷</button>
                </div>
            </div>
            <div class="flex justify-between items-start gap-2">
                <div>
                    <h3 class="text-base font-bold text-white">${s.brand || '—'}</h3>
                    <p class="text-sm text-amber-500">${s.model || '—'}</p>
                    ${s.magnification ? `<p class="text-xs text-blue-300 font-mono">${s.magnification}</p>` : ''}
                </div>
                <div class="text-right shrink-0">
                    <span class="text-xs text-gray-400 font-mono">$${parseFloat(s.price_paid || 0).toFixed(2)}</span>
                    <p class="text-[10px] mt-0.5">${firstMount ? `📍 <a href="${firstMount.type === 'firearm' ? 'firearm-detail.html' : 'tc-barrel-detail.html'}?id=${firstMount.id}" onclick="event.stopPropagation()" class="text-emerald-400 hover:text-emerald-300 font-medium hover:underline">${firstMount.label}</a>` : `📍 <span class="text-gray-500 italic">Unmounted</span>`}</p>
                </div>
            </div>
            <!-- Edit panel (hidden) -->
            <div id="scope-edit-panel-${s.id}" class="hidden border-t border-gray-600 pt-3 space-y-2">
                <input id="sedit-brand-${s.id}" value="${(s.brand||'').replace(/"/g,'&quot;')}" placeholder="Brand" class="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none">
                <input id="sedit-model-${s.id}" value="${(s.model||'').replace(/"/g,'&quot;')}" placeholder="Model" class="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none">
                <input id="sedit-mag-${s.id}" value="${(s.magnification||'').replace(/"/g,'&quot;')}" placeholder="Magnification (e.g. 3-9x40)" class="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none">
                <div class="flex gap-2">
                    <select id="sedit-units-${s.id}" class="flex-1 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none">
                        <option value="MOA" ${(s.units||'MOA')==='MOA'?'selected':''}>MOA</option>
                        <option value="MRAD" ${s.units==='MRAD'?'selected':''}>MRAD</option>
                    </select>
                    <div class="flex items-center flex-1 bg-gray-700 border border-gray-600 rounded px-2 py-1 gap-1">
                        <span class="text-xs text-gray-400">$</span>
                        <input id="sedit-price-${s.id}" type="number" step="0.01" value="${s.price_paid||0}" placeholder="Price" class="flex-1 bg-transparent text-xs text-white focus:outline-none min-w-0">
                    </div>
                </div>
                <div class="flex gap-2 items-center">
                    <label class="text-xs text-gray-200 font-semibold whitespace-nowrap">Qty owned:</label>
                    <input id="sedit-qty-${s.id}" type="number" min="1" value="${qty}" class="w-20 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-white focus:outline-none">
                </div>
                <div class="flex gap-2">
                    <button onclick="saveScopeEdit(${s.id})" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold py-1.5 rounded transition cursor-pointer">Save</button>
                    <button onclick="toggleScopeEditPanel(${s.id})" class="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold py-1.5 rounded transition cursor-pointer">Cancel</button>
                </div>
            </div>
            <!-- Photo panel (hidden) -->
            <div id="scope-photo-panel-${s.id}" class="hidden border-t border-gray-600 pt-2 space-y-1.5">
                <div class="flex gap-2 items-center">
                    <div class="flex gap-1.5 flex-1">
                        <button type="button" onclick="document.getElementById('sedit-photo-cam-${s.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-1 rounded cursor-pointer">📷 Camera</button>
                        <button type="button" onclick="document.getElementById('sedit-photo-${s.id}').click()" class="flex-1 text-[9px] bg-gray-700 hover:bg-gray-600 text-gray-300 border border-gray-600 py-1 rounded cursor-pointer">🖼 Gallery</button>
                    </div>
                    <button onclick="saveScopePhoto(${s.id}, ${photoCount})" class="px-2 py-1 bg-blue-800 hover:bg-blue-700 text-white text-[10px] font-bold rounded cursor-pointer transition">Upload</button>
                </div>
                <input type="file" id="sedit-photo-${s.id}" accept="image/*" class="hidden">
                <input type="file" capture="environment" accept="image/*" id="sedit-photo-cam-${s.id}" onchange="_camToInput('sedit-photo-cam-${s.id}','sedit-photo-${s.id}')" class="hidden">
                ${s.image_path && s.image_path_2 ? `<button onclick="swapScopePhotos(${s.id})" class="w-full py-1 bg-amber-800 hover:bg-amber-700 text-white text-[10px] font-bold rounded transition cursor-pointer">⭐ Make Primary</button>` : ''}
            </div>
            ${addMountEditor}
            <!-- Mount editor for qty=1 (hidden until user clicks) -->
            <div id="scope-editor-${s.id}" class="hidden border-t border-gray-600 pt-3 space-y-2">
                <div class="flex gap-2 items-center flex-wrap">
                    <select id="scope-installed-${s.id}" onchange="toggleScopeMountSelect(${s.id})"
                        class="bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none">
                        <option value="yes" ${firstMount ? 'selected' : ''}>Installed</option>
                        <option value="no" ${!firstMount ? 'selected' : ''}>Unmounted</option>
                    </select>
                    <select id="scope-mount-select-${s.id}"
                        class="flex-1 min-w-0 bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none ${!firstMount ? 'hidden' : ''}">
                        <option value="">Loading…</option>
                    </select>
                </div>
                <div class="flex gap-2">
                    <button onclick="saveScopeMount(${s.id})" class="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold py-1.5 rounded transition cursor-pointer">Save</button>
                    <button onclick="closeScopeMountEditor(${s.id})" class="px-3 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs font-bold py-1.5 rounded transition cursor-pointer">Cancel</button>
                </div>
            </div>
            ${addInstallBtn ? `<div class="flex gap-2 mt-1">${addInstallBtn}</div>` : ''}
        </div>
    </div>`;
}

function toggleScopeEditPanel(id) {
    document.getElementById(`scope-edit-panel-${id}`)?.classList.toggle('hidden');
}

function toggleScopePhotoPanel(id) {
    document.getElementById(`scope-photo-panel-${id}`)?.classList.toggle('hidden');
}

async function saveScopePhoto(scopeId, currentPhotoCount) {
    const input = document.getElementById(`sedit-photo-${scopeId}`);
    const file = input?.files[0];
    if (!file) { showToast('Select a photo first.', 'warn'); return; }
    const slot = currentPhotoCount < 2 ? currentPhotoCount + 1 : 1;
    const fd = new FormData();
    fd.append('image', file);
    fd.append('slot', String(slot));
    await fetch(`/scopes/${scopeId}/update-photo/`, { method: 'POST', body: fd });
    showToast('Scope photo updated.');
    loadScopes();
}

async function swapScopePhotos(scopeId) {
    try {
        await fetch(`/scopes/${scopeId}/swap-photos/`, { method: 'POST' });
        showToast('Primary photo updated.');
        loadScopes();
    } catch { showToast('Failed to swap photos.', 'error'); }
}

async function openScopeMountEditor(scopeId) {
    const editor = document.getElementById(`scope-editor-${scopeId}`);
    const select = document.getElementById(`scope-mount-select-${scopeId}`);
    const installedSel = document.getElementById(`scope-installed-${scopeId}`);
    if (!editor || !select) return;

    editor.classList.remove('hidden');

    // Fetch available mounts
    try {
        const res = await fetch(`/available-mounts/?for_scope_id=${scopeId}`);
        if (!res.ok) return;
        const data = await res.json();

        let opts = `<option value="">-- Select Platform --</option>`;
        if (data.firearms.length > 0) {
            opts += `<optgroup label="── Rifles ──">` +
                data.firearms.map(f => `<option value="firearm:${f.id}">${f.label}</option>`).join('') +
                `</optgroup>`;
        }
        if (data.tc_barrels.length > 0) {
            opts += `<optgroup label="── TC Barrels ──">` +
                data.tc_barrels.map(b => `<option value="barrel:${b.id}">${b.label}</option>`).join('') +
                `</optgroup>`;
        }
        select.innerHTML = opts;

        // Pre-select current mount
        const card = document.getElementById(`scope-card-${scopeId}`);
        if (card) {
            const mountType = installedSel.value === 'yes' ? card.dataset.mountType : null;
            const mountId   = card.dataset.mountId;
            if (mountType && mountId) {
                const val = `${mountType}:${mountId}`;
                for (const opt of select.options) {
                    if (opt.value === val) { opt.selected = true; break; }
                }
            }
        }
    } catch(_) {}
}

function toggleScopeMountSelect(scopeId) {
    const sel = document.getElementById(`scope-installed-${scopeId}`);
    const mountSel = document.getElementById(`scope-mount-select-${scopeId}`);
    if (!sel || !mountSel) return;
    if (sel.value === 'yes') {
        mountSel.classList.remove('hidden');
    } else {
        mountSel.classList.add('hidden');
    }
}

async function saveScopeMount(scopeId) {
    const installedSel = document.getElementById(`scope-installed-${scopeId}`);
    const mountSel     = document.getElementById(`scope-mount-select-${scopeId}`);
    if (!installedSel) return;

    let mount_type = null;
    let mount_id   = null;

    if (installedSel.value === 'yes' && mountSel && mountSel.value) {
        const [type, id] = mountSel.value.split(':');
        mount_type = type;
        mount_id   = parseInt(id);
    }

    try {
        const res = await fetch(`/scopes/${scopeId}/mount`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mount_type, mount_id })
        });
        if (res.ok) {
            showToast('Scope mount updated.');
            loadScopes();
        } else {
            showToast('Failed to update mount.', 'error');
        }
    } catch(_) { showToast('Error saving mount.', 'error'); }
}

function closeScopeMountEditor(scopeId) {
    document.getElementById(`scope-editor-${scopeId}`)?.classList.add('hidden');
}

async function openAddScopeMount(scopeId) {
    const editor = document.getElementById(`scope-add-mount-editor-${scopeId}`);
    const select = document.getElementById(`scope-add-mount-sel-${scopeId}`);
    if (!editor || !select) return;
    editor.classList.remove('hidden');
    document.getElementById(`scope-add-install-btn-${scopeId}`)?.classList.add('hidden');
    try {
        const res = await fetch(`/available-mounts/?for_scope_id=${scopeId}`);
        if (!res.ok) return;
        const data = await res.json();
        let opts = `<option value="">-- Select Platform --</option>`;
        if (data.firearms.length > 0) {
            opts += `<optgroup label="── Rifles ──">` +
                data.firearms.map(f => `<option value="firearm:${f.id}">${f.label}</option>`).join('') +
                `</optgroup>`;
        }
        if (data.tc_barrels.length > 0) {
            opts += `<optgroup label="── TC Barrels ──">` +
                data.tc_barrels.map(b => `<option value="barrel:${b.id}">${b.label}</option>`).join('') +
                `</optgroup>`;
        }
        select.innerHTML = opts;
    } catch(_) {}
}

function closeAddScopeMount(scopeId) {
    document.getElementById(`scope-add-mount-editor-${scopeId}`)?.classList.add('hidden');
    document.getElementById(`scope-add-install-btn-${scopeId}`)?.classList.remove('hidden');
}

async function saveAddScopeMount(scopeId) {
    const select = document.getElementById(`scope-add-mount-sel-${scopeId}`);
    if (!select || !select.value) { showToast('Select a platform first.', 'warn'); return; }
    const [type, id] = select.value.split(':');
    try {
        const res = await fetch(`/scopes/${scopeId}/add-mount`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mount_type: type, mount_id: parseInt(id) }),
        });
        if (res.ok) { showToast('Scope installed.'); loadScopes(); }
        else { const e = await res.json(); showToast(e.detail || 'Failed to install.', 'error'); }
    } catch(_) { showToast('Error installing scope.', 'error'); }
}

async function removeScopeMount(scopeId, mountType, mountId) {
    if (!confirm('Uninstall this scope from the platform?')) return;
    try {
        const res = await fetch(`/scopes/${scopeId}/remove-mount`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mount_type: mountType, mount_id: mountId }),
        });
        if (res.ok) { showToast('Scope uninstalled.'); loadScopes(); }
        else showToast('Failed to uninstall.', 'error');
    } catch(_) { showToast('Error removing mount.', 'error'); }
}

async function loadAmmoInventory(type) {
    const containerId = 'ammo-container';
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '<p class="text-gray-400 italic text-sm">Loading ammunition...</p>';

    try {
        const fetchList = [fetch('/ammo/', { cache: 'no-store' })];
        if (type === 'muzzleloader') {
            fetchList.push(
                fetch('/components/powders/?muzzleloader=1', { cache: 'no-store' }),
                fetch('/components/bullets/?muzzleloader=1', { cache: 'no-store' }),
                fetch('/components/primers/?muzzleloader=1', { cache: 'no-store' }),
            );
        }
        const [ammoRes, mlPowRes, mlBulRes, mlPriRes] = await Promise.all(fetchList);
        const all = ammoRes.ok ? await ammoRes.json() : [];
        const mlPowders = mlPowRes?.ok ? await mlPowRes.json() : [];
        const mlBullets = mlBulRes?.ok ? await mlBulRes.json() : [];
        const mlPrimers = mlPriRes?.ok ? await mlPriRes.json() : [];

        let filtered;
        if (type === 'handload') {
            filtered = all.filter(a => a.is_handload);
        } else if (type === 'muzzleloader') {
            filtered = all.filter(a => a.ammo_category === 'muzzleloader');
        } else {
            filtered = all.filter(a => !a.is_handload && a.ammo_category !== 'muzzleloader');
        }
        filtered = filtered.filter(matchesSearch);

        document.getElementById('inventory-count').innerText = `${filtered.length} Load${filtered.length !== 1 ? 's' : ''} Registered`;

        // Group by category → caliber
        const CAT_ORDER = ['centerfire', 'handgun', 'rimfire', 'shotgun', 'shotgun_slug', 'muzzleloader'];
        const CAT_LABELS = { centerfire: 'Centerfire · Rifle', handgun: 'Handgun · Pistol', rimfire: 'Rimfire', shotgun: 'Shotgun', shotgun_slug: 'Shotgun Slug', muzzleloader: 'Muzzleloader' };
        const CAT_COLORS = { centerfire: 'text-blue-400', handgun: 'text-purple-400', rimfire: 'text-emerald-400', shotgun: 'text-orange-400', shotgun_slug: 'text-red-400', muzzleloader: 'text-yellow-600' };
        const catGroups = {};
        filtered.forEach(a => {
            const cat = a.ammo_category || 'centerfire';
            if (!catGroups[cat]) catGroups[cat] = {};
            const cal = a.caliber || 'Unknown Caliber';
            if (!catGroups[cat][cal]) catGroups[cat][cal] = [];
            catGroups[cat][cal].push(a);
        });

        const catsToRender = CAT_ORDER.filter(c => catGroups[c]);
        const hasMlComp = mlPowders.length + mlBullets.length + mlPrimers.length > 0;

        if (catsToRender.length === 0 && !hasMlComp) {
            const emptyMsg = type === 'handload' ? 'handload recipes' : type === 'muzzleloader' ? 'muzzleloader loads' : 'factory loads';
            container.innerHTML = `<p class="text-gray-500 italic text-sm">No ${emptyMsg} registered.</p>`;
            return;
        }

        const catFilterRow = document.getElementById('ammo-cat-filter-row');
        const calFilterRow = document.getElementById('ammo-cal-filter-row');

        function buildCaliberRow(sourceItems) {
            if (!calFilterRow) return;
            const cals = [...new Set(sourceItems.map(a => a.caliber).filter(Boolean))].sort((a,b) => a.localeCompare(b));
            if (cals.length > 1) {
                // Keep current caliber if valid, otherwise default to null (All)
                if (currentAmmoCaliberFilter && !cals.includes(currentAmmoCaliberFilter)) {
                    currentAmmoCaliberFilter = null;
                }
                calFilterRow.classList.remove('hidden');
                const allCls = !currentAmmoCaliberFilter
                    ? 'px-2.5 py-1 rounded text-[11px] font-bold bg-gray-600 text-white cursor-pointer transition'
                    : 'px-2.5 py-1 rounded text-[11px] font-bold bg-gray-800 text-gray-400 hover:text-white border border-gray-700 cursor-pointer transition';
                calFilterRow.innerHTML = `<button onclick="switchAmmoCaliber(null)" class="${allCls}">All</button>` +
                    cals.map(cal => {
                        const isActive = cal === currentAmmoCaliberFilter;
                        const cls = isActive
                            ? 'px-2.5 py-1 rounded text-[11px] font-bold bg-amber-700 text-white cursor-pointer transition'
                            : 'px-2.5 py-1 rounded text-[11px] font-bold bg-gray-800 text-gray-400 hover:text-white border border-gray-700 cursor-pointer transition';
                        return `<button onclick="switchAmmoCaliber('${cal.replace(/'/g,"\\'")}')" class="${cls}">${escHtml(cal)}</button>`;
                    }).join('');
            } else {
                calFilterRow.classList.add('hidden');
                currentAmmoCaliberFilter = null;
            }
        }

        if (type === 'factory') {
            // Reset category selection if the current one has no data
            if (!currentAmmoCategoryFilter || !catGroups[currentAmmoCategoryFilter]) {
                currentAmmoCategoryFilter = catsToRender[0] || null;
            }
            // Build category filter buttons
            if (catFilterRow) {
                catFilterRow.classList.remove('hidden');
                catFilterRow.innerHTML = catsToRender.map(cat => {
                    const isActive = cat === currentAmmoCategoryFilter;
                    const cls = isActive
                        ? `px-3 py-1 rounded bg-gray-800 ${CAT_COLORS[cat]} cursor-pointer text-xs font-bold`
                        : 'px-3 py-1 rounded text-gray-200 hover:text-white cursor-pointer text-xs font-bold';
                    const count = Object.values(catGroups[cat]).flat().length;
                    return `<button id="ammo-cat-btn-${cat}" onclick="switchAmmoCategory('${cat}')" class="${cls}">${CAT_LABELS[cat]} <span class="opacity-60 font-normal">${count}</span></button>`;
                }).join('');
            }
            // Build caliber row from active category only
            const activeCatGroups = catGroups[currentAmmoCategoryFilter] || {};
            const activeCatItems = Object.values(activeCatGroups).flat();
            buildCaliberRow(activeCatItems);
            // Render: if caliber selected, show only that caliber; otherwise show all in category
            const renderGroups = currentAmmoCaliberFilter
                ? (activeCatGroups[currentAmmoCaliberFilter] ? { [currentAmmoCaliberFilter]: activeCatGroups[currentAmmoCaliberFilter] } : {})
                : activeCatGroups;
            const calHtml = Object.entries(renderGroups).sort(([a],[b]) => a.localeCompare(b)).map(([cal, loads]) => `
                <div class="mb-4">
                    <div class="flex items-center gap-2 mb-2">
                        <span class="text-[10px] font-bold uppercase tracking-wider text-blue-400/80 font-mono">${escHtml(cal)}</span>
                        <div class="flex-1 border-t border-gray-700/40"></div>
                    </div>
                    <div class="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">${loads.map(renderAmmoTile).join('')}</div>
                </div>`).join('');
            container.innerHTML = calHtml || `<p class="text-gray-500 italic text-sm">No factory loads in this category.</p>`;
        } else {
            if (catFilterRow) catFilterRow.classList.add('hidden');
            // Build caliber row from this tab's items, then apply filter
            buildCaliberRow(filtered);
            if (currentAmmoCaliberFilter) filtered = filtered.filter(a => a.caliber === currentAmmoCaliberFilter);
            // Handloads: full cards with caliber sub-groups; muzzleloader: tiles
            if (type === 'handload') {
                const calGroups = {};
                filtered.forEach(a => {
                    const cal = a.caliber || 'Unknown Caliber';
                    if (!calGroups[cal]) calGroups[cal] = [];
                    calGroups[cal].push(a);
                });
                const calHtml = Object.entries(calGroups).sort(([a],[b]) => a.localeCompare(b)).map(([cal, loads]) => `
                    <div class="mb-6">
                        <div class="flex items-center gap-3 mb-3">
                            <span class="text-xs font-bold uppercase tracking-wider text-amber-500 font-mono">${cal}</span>
                            <span class="text-xs text-gray-200 font-semibold">${loads.length} load${loads.length !== 1 ? 's' : ''}</span>
                            <div class="flex-1 border-t border-gray-700/60"></div>
                        </div>
                        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
                            ${loads.map(renderAmmoCard).join('')}
                        </div>
                    </div>`).join('');
                container.innerHTML = calHtml || `<p class="text-gray-500 italic text-sm">No handload recipes registered.</p>`;
            } else {
                // muzzleloader — same grouped layout as factory + components section below
                const calGroups = {};
                filtered.forEach(a => {
                    const cal = a.caliber || 'Unknown Caliber';
                    if (!calGroups[cal]) calGroups[cal] = [];
                    calGroups[cal].push(a);
                });
                const calHtml = Object.entries(calGroups).sort(([a],[b]) => a.localeCompare(b)).map(([cal, loads]) => `
                    <div class="mb-4">
                        <div class="flex items-center gap-2 mb-2">
                            <span class="text-[10px] font-bold uppercase tracking-wider text-yellow-500/80 font-mono">${escHtml(cal)}</span>
                            <div class="flex-1 border-t border-gray-700/40"></div>
                        </div>
                        <div class="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">${loads.map(renderAmmoTile).join('')}</div>
                    </div>`).join('');
                const mlSectionHtml = renderMuzzleloaderComponentsSection(mlPowders, mlBullets, mlPrimers);
                container.innerHTML = (calHtml || '') + mlSectionHtml;
            }
        }
    } catch(err) {
        container.innerHTML = '<p class="text-red-400 italic text-sm">Failed to load ammunition.</p>';
    }
}

function renderMuzzleloaderComponentsSection(powders, bullets, primers) {
    if (!powders.length && !bullets.length && !primers.length) return '';
    const addLink = `<a href="/?tab=add-tab&cat=components" class="text-xs text-gray-200 font-semibold hover:text-amber-400 transition cursor-pointer">+ Add Components</a>`;
    let html = `<div class="mt-4 border-t border-gray-700/50 pt-4">
        <div class="flex items-center gap-3 mb-3">
            <span class="text-xs font-bold uppercase tracking-wider text-gray-400">⚙️ Components On Hand</span>
            <div class="flex-1 border-t border-gray-700/40"></div>
            ${addLink}
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">`;

    // Propellant column
    html += `<div class="bg-gray-900/60 rounded-lg p-3">
        <p class="text-[10px] font-bold uppercase tracking-wider text-emerald-400 mb-2">🧪 Propellant</p>`;
    if (powders.length) {
        html += powders.map(p => `<div class="flex justify-between items-center py-1 border-b border-gray-800 last:border-0">
            <span class="text-xs text-white">${escHtml(p.brand)} ${escHtml(p.name)}</span>
            <span class="text-xs font-mono text-emerald-400 ml-2 whitespace-nowrap">${p.weight_lbs ?? 0}${p.pellet_mode ? ' qty' : ' lbs'}</span>
        </div>`).join('');
    } else {
        html += `<p class="text-xs text-gray-600 italic">None logged</p>`;
    }
    html += `</div>`;

    // Bullets/Sabots column
    html += `<div class="bg-gray-900/60 rounded-lg p-3">
        <p class="text-[10px] font-bold uppercase tracking-wider text-blue-400 mb-2">🎯 Projectiles / Sabots</p>`;
    if (bullets.length) {
        html += bullets.map(b => `<div class="flex justify-between items-center py-1 border-b border-gray-800 last:border-0">
            <span class="text-xs text-white">${escHtml(b.brand)}${b.product_line ? ' ' + escHtml(b.product_line) : ''} <span class="text-gray-500">${b.weight_gr}gr</span></span>
            <span class="text-xs font-mono text-blue-400 ml-2 whitespace-nowrap">${(b.quantity ?? 0).toLocaleString()}</span>
        </div>`).join('');
    } else {
        html += `<p class="text-xs text-gray-600 italic">None logged</p>`;
    }
    html += `</div>`;

    // Primers column
    html += `<div class="bg-gray-900/60 rounded-lg p-3">
        <p class="text-[10px] font-bold uppercase tracking-wider text-orange-400 mb-2">🔥 Primers (Shotshell)</p>`;
    if (primers.length) {
        html += primers.map(p => `<div class="flex justify-between items-center py-1 border-b border-gray-800 last:border-0">
            <span class="text-xs text-white">${escHtml(p.brand)}${p.model ? ' ' + escHtml(p.model) : ''}</span>
            <span class="text-xs font-mono text-orange-400 ml-2 whitespace-nowrap">${(p.quantity ?? 0).toLocaleString()}</span>
        </div>`).join('');
    } else {
        html += `<p class="text-xs text-gray-600 italic">None logged</p>`;
    }
    html += `</div>`;

    html += `</div></div>`;
    return html;
}

function renderAmmoTile(ammo) {
    const sealed = ammo.qty_sealed || 0;
    const open = ammo.qty_open || 0;
    const rpb = ammo.rounds_per_box || 20;
    const total = sealed * rpb + open;
    const countColor = total > 0 ? 'text-blue-400' : 'text-gray-600';
    const imgHtml = ammo.image_path
        ? `<img src="${ammo.image_path}" class="w-full h-full object-contain">`
        : `<span class="text-3xl">📦</span>`;
    const boxLabel = sealed ? `${sealed}bx` : '';
    const breakdownHtml = boxLabel
        ? `<span class="block text-[11px] text-gray-300 font-mono leading-tight">${boxLabel}</span>`
        : '';
    return `
    <div onclick="window.location.href='ammo-detail.html?id=${ammo.id}&filter=${currentAmmoFilter}${currentAmmoCaliberFilter ? '&cal='+encodeURIComponent(currentAmmoCaliberFilter) : ''}'"
         class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden hover:border-amber-500/60 transition cursor-pointer shadow-lg">
        <div class="aspect-square bg-gray-950 flex items-center justify-center overflow-hidden">
            ${imgHtml}
        </div>
        <div class="bg-gray-900/80 text-center py-1.5 px-1">
            <span class="text-xs font-bold font-mono ${countColor}">${total} rds</span>
            ${breakdownHtml}
        </div>
    </div>`;
}

function renderAmmoCard(ammo) {
    const isHandload = ammo.is_handload;
    const isShotgun = ammo.ammo_category === 'shotgun' || ammo.ammo_category === 'shotgun_slug';
    const badgeCls = isHandload
        ? 'bg-emerald-950 text-emerald-400 border-emerald-800'
        : 'bg-blue-950 text-blue-400 border-blue-800';
    const badgeLabel = isHandload ? 'HANDLOAD' : 'FACTORY';
    const line = ammo.line_or_powder || '';

    // Handload: no photo — show recipe data
    if (isHandload) {
        const rows = [];
        if (ammo.bullet_type)   rows.push(['Bullet',  ammo.bullet_type]);
        if (line)               rows.push(['Powder',  line]);
        if (ammo.charge_weight) rows.push(['Charge',  `${ammo.charge_weight} gr`]);
        if (ammo.coal)          rows.push(['COAL',    `${ammo.coal}"`]);
        const qty = (ammo.qty_sealed || 0) * (ammo.rounds_per_box || 20) + (ammo.qty_open || 0);
        return `
        <div onclick="window.location.href='ammo-detail.html?id=${ammo.id}&filter=${currentAmmoFilter}${currentAmmoCaliberFilter ? '&cal='+encodeURIComponent(currentAmmoCaliberFilter) : ''}'"
             class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden hover:border-emerald-500/60 transition cursor-pointer shadow-lg">
            <div class="p-3 space-y-2">
                <div class="flex justify-between items-center">
                    <h3 class="text-base font-bold text-white leading-tight">${ammo.brand || '—'}</h3>
                    <button onclick="event.stopPropagation();deleteAmmoEntry(${ammo.id},'${escHtml(ammo.brand||'this load')}')" class="text-gray-600 hover:text-red-400 text-xs cursor-pointer shrink-0 ml-2" title="Delete">✕</button>
                </div>
                <div class="space-y-1 border-t border-gray-700/60 pt-2">
                    ${rows.map(([k,v]) => `<div class="flex justify-between text-xs"><span class="text-gray-500">${k}</span><span class="text-gray-200 font-mono font-semibold">${escHtml(String(v))}</span></div>`).join('')}
                </div>
                ${qty > 0 ? `<div class="text-center pt-1 border-t border-gray-700/60"><span class="text-base font-bold font-mono text-emerald-400">${qty}</span><span class="text-xs text-gray-500 ml-1">rds</span></div>` : ''}
            </div>
        </div>`;
    }

    // Factory / other: keep photo
    const gallery = makePhotoGallery(`ammo-${ammo.id}`, '📦', ammo.image_path, ammo.image_path_2);

    let detail = '';
    if (line) detail += `<p class="text-[11px] text-gray-400">Line: <span class="text-gray-200">${line}</span></p>`;
    if (isShotgun && ammo.shell_size) detail += `<p class="text-[11px] text-gray-400">Shell: <span class="text-gray-200 font-mono">${ammo.shell_size}"</span></p>`;

    const sealed = ammo.qty_sealed || 0;
    const open = ammo.qty_open || 0;
    const rpb = ammo.rounds_per_box || 20;
    const price = ammo.price_paid || 0;
    const total = sealed * rpb + open;
    let stockLine = '';
    if (total > 0) {
        const boxLabel = sealed ? `${sealed} box${sealed !== 1 ? 'es' : ''}` : '';
        stockLine = `<div class="bg-gray-900/60 rounded p-2 text-center mt-1">
            <p class="text-sm font-bold font-mono text-blue-400">${total} <span class="text-xs text-gray-400">rds</span></p>
            <p class="text-xs text-gray-200 font-semibold">${boxLabel}${price ? ` · $${price.toFixed(2)}/box` : ''}</p>
        </div>`;
    }

    return `
    <div onclick="window.location.href='ammo-detail.html?id=${ammo.id}&filter=${currentAmmoFilter}${currentAmmoCaliberFilter ? '&cal='+encodeURIComponent(currentAmmoCaliberFilter) : ''}'"
         class="bg-gray-800 border border-gray-700 rounded-lg overflow-hidden hover:border-amber-500/60 transition cursor-pointer shadow-lg">
        ${gallery}
        <div class="p-4 space-y-2">
            <div class="flex justify-between items-start">
                <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${badgeCls}">${badgeLabel}</span>
                <div class="flex items-center gap-2">
                    ${isShotgun
                        ? (ammo.shell_size ? `<span class="text-xs font-mono font-bold text-orange-400">${ammo.shell_size}"</span>` : '')
                        : `<span class="text-xs font-mono font-bold text-amber-400">${ammo.bullet_weight ? ammo.bullet_weight + 'gr' : ''}</span>`}
                    <button onclick="event.stopPropagation();deleteAmmoEntry(${ammo.id},'${escHtml(ammo.brand||'this load')}')" class="text-gray-600 hover:text-red-400 text-xs cursor-pointer" title="Delete">✕</button>
                </div>
            </div>
            <div>
                <h3 class="text-sm font-bold text-white leading-tight">${ammo.brand || '—'}</h3>
                <p class="text-[11px] text-gray-400">${ammo.bullet_type || '—'}</p>
            </div>
            ${detail ? `<div class="border-t border-gray-700/60 pt-2 space-y-0.5">${detail}</div>` : ''}
            ${stockLine}
        </div>
    </div>`;
}

async function deleteAmmoEntry(id, name) {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
        const res = await fetch(`/ammo/${id}`, { method: 'DELETE' });
        if (res.ok) {
            showToast('Load deleted.');
            loadAmmoInventory(currentAmmoFilter);
        } else {
            const body = await res.json();
            showToast(body.detail || 'Cannot delete this load.', 'error');
        }
    } catch { showToast('Error deleting.', 'error'); }
}

function applySortFn(arr, sort) {
    return [...arr].sort((a, b) => {
        if (sort === 'caliber') return (a.caliber || '').localeCompare(b.caliber || '');
        if (sort === 'price_asc') return (a.price_paid || 0) - (b.price_paid || 0);
        if (sort === 'price_desc') return (b.price_paid || 0) - (a.price_paid || 0);
        return (a.brand || '').localeCompare(b.brand || '');
    });
}

function setPlatformSort(val) {
    currentPlatformSort = val;
    loadCatalog();
}

function setOpticSort(val) {
    currentOpticSort = val;
    loadScopes();
}

function switchFormCategory(targetCat) {
    const panes = { 'cat-platforms': 'pane-platforms', 'cat-ammunition': 'pane-ammunition', 'cat-components': 'pane-components' };
    const btns  = { 'cat-platforms': 'btn-cat-platforms', 'cat-ammunition': 'btn-cat-ammunition', 'cat-components': 'btn-cat-components' };
    Object.entries(panes).forEach(([cat, paneId]) => {
        const pane = document.getElementById(paneId);
        const btn  = document.getElementById(btns[cat]);
        if (cat === targetCat) {
            pane?.classList.remove('hidden');
            if (btn) btn.className = "px-4 py-1.5 text-xs font-bold rounded bg-amber-600 text-white cursor-pointer";
        } else {
            pane?.classList.add('hidden');
            if (btn) btn.className = "px-4 py-1.5 text-xs font-bold rounded text-gray-200 hover:text-white cursor-pointer";
        }
    });
}

function toggleAmmoType(type) {
    document.querySelectorAll('.ammo-variant-form').forEach(form => form.classList.add('hidden'));
    const factForm = document.getElementById('ammo-factory-form');
    const handForm = document.getElementById('ammo-handload-form');
    const btnFact = document.getElementById('btn-ammo-factory');
    const btnHand = document.getElementById('btn-ammo-handloads');

    if (type === 'factory') {
        if (factForm) factForm.classList.remove('hidden');
        if (btnFact) btnFact.className = "px-3 py-1 text-xs font-bold rounded bg-blue-600 text-white cursor-pointer";
        if (btnHand) btnHand.className = "px-3 py-1 text-xs font-bold rounded text-gray-200 bg-gray-950 hover:text-white cursor-pointer";
    } else {
        if (handForm) handForm.classList.remove('hidden');
        if (btnFact) btnFact.className = "px-3 py-1 text-xs font-bold rounded text-gray-200 bg-gray-950 hover:text-white cursor-pointer";
        if (btnHand) btnHand.className = "px-3 py-1 text-xs font-bold rounded bg-emerald-600 text-white cursor-pointer";
        populateHandloadDropdowns();
    }
}

function _toggleFactoryAmmoFields(cat) {
    const isShotgun = cat === 'shotgun' || cat === 'shotgun_slug';
    ['ammo-factory-bullet-type-row', 'ammo-factory-weight-row', 'ammo-factory-bc-row'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('hidden', isShotgun);
    });
    const shellRow = document.getElementById('ammo-factory-shell-row');
    if (shellRow) shellRow.classList.toggle('hidden', !isShotgun);
    const shotRow = document.getElementById('ammo-factory-shot-row');
    if (shotRow) shotRow.classList.toggle('hidden', !isShotgun);
    // manage required
    const wtInput = document.getElementById('ammo-factory-weight');
    const btInput = document.getElementById('ammo-factory-bullet-type');
    if (wtInput) wtInput.required = !isShotgun;
    if (btInput) btInput.required = !isShotgun;
    // update bullet type placeholder to match category
    if (btInput) {
        const ph = { centerfire: 'e.g., FMJ, SP, HPBT, ELD-M', handgun: 'e.g., FMJ, JHP, FP', rimfire: 'e.g., HP, LRN, FMJ', shotgun: 'e.g., 00 Buck, #6 Shot', shotgun_slug: 'e.g., Foster, Sabot', muzzleloader: 'e.g., Conical, Sabot, Round Ball' };
        btInput.placeholder = ph[cat] || 'e.g., Soft Point, ELD-M';
    }
}

function _togglePowderMuzzleloaderFields(isMuzzleloader) {
    const modeRow = document.getElementById('pw-pellet-mode-row');
    if (modeRow) modeRow.classList.toggle('hidden', !isMuzzleloader);
    if (!isMuzzleloader) {
        // reset to lbs mode when unchecking muzzleloader
        _setPowderMode('lbs');
        const radio = document.querySelector('input[name="pw-mode-radio"][value="lbs"]');
        if (radio) radio.checked = true;
    }
}

function _setPowderMode(mode) {
    const isPellet = mode === 'qty';
    document.getElementById('pw-pellet-mode-hidden').value = isPellet ? 'true' : 'false';
    ['pw-container-size-col', 'pw-container-count-col'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('hidden', isPellet);
    });
    const directCol = document.getElementById('pw-direct-weight-col');
    if (directCol) directCol.classList.toggle('hidden', !isPellet);
}

// ── Threshold Settings Panel ───────────────────────────────────────────────────

async function toggleThresholdSettings() {
    const panel = document.getElementById('threshold-panel');
    const icon  = document.getElementById('threshold-toggle-icon');
    const isHidden = panel.classList.contains('hidden');
    panel.classList.toggle('hidden');
    icon.textContent = isHidden ? '▼' : '▶';
    if (isHidden) await loadThresholds();
}

async function loadThresholds() {
    try {
        const res = await fetch('/settings/');
        if (!res.ok) return;
        const s = await res.json();
        const f = v => document.getElementById(v);
        if (f('thresh-powder'))  f('thresh-powder').value  = s.low_stock_powder_lbs ?? 0.5;
        if (f('thresh-primers')) f('thresh-primers').value = s.low_stock_primers    ?? 200;
        if (f('thresh-bullets')) f('thresh-bullets').value = s.low_stock_bullets    ?? 100;
        if (f('thresh-casings')) f('thresh-casings').value = s.low_stock_casings    ?? 50;
    } catch(_) {}
}

async function saveThresholds() {
    const payload = {
        low_stock_powder_lbs: document.getElementById('thresh-powder')?.value  || '0.5',
        low_stock_primers:    document.getElementById('thresh-primers')?.value || '200',
        low_stock_bullets:    document.getElementById('thresh-bullets')?.value || '100',
        low_stock_casings:    document.getElementById('thresh-casings')?.value || '50',
    };
    try {
        const res = await fetch('/settings/', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) { showToast('Alert thresholds saved.'); refreshLowStockBanner(); }
        else showToast('Failed to save thresholds.', 'error');
    } catch(_) { showToast('Error saving thresholds.', 'error'); }
}

// Builds <optgroup>-organized gun options (rifles/shotguns/handguns/TC barrels) shared
// by any picker that needs to choose "which firearm was this for" — TC barrel options are
// tagged data-type="tc" since their <option value> IS a real barrel id already, while
function _levenshtein(a, b) {
    const m = a.length, n = b.length;
    if (m === 0) return n;
    if (n === 0) return m;
    let prev = Array.from({ length: n + 1 }, (_, i) => i);
    for (let i = 1; i <= m; i++) {
        const cur = [i];
        for (let j = 1; j <= n; j++) {
            const cost = a[i - 1] === b[j - 1] ? 0 : 1;
            cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
        }
        prev = cur;
    }
    return prev[n];
}

function _normalizeCaliberText(s) {
    return String(s || '').toLowerCase().trim().replace(/\s+/g, ' ');
}

// Firearm barrel calibers and casing calibers are both free text, typed independently — real
// inventories end up with typos ("Creedmore" vs "Creedmoor") and stray whitespace between the
// two, so an exact string match misses real matches. Allow a small edit-distance as a safety
// net (capped tight enough that unrelated cartridges, e.g. "6.5 Grendel" vs "6.5 Creedmoor",
// never collide).
function _calibersMatch(a, b) {
    const na = _normalizeCaliberText(a), nb = _normalizeCaliberText(b);
    if (!na || !nb) return false;
    if (na === nb) return true;
    if (Math.abs(na.length - nb.length) > 2) return false;
    return _levenshtein(na, nb) <= 2;
}

// regular firearm options carry a firearm id that still needs resolveBarrelIdFromGunSelect().
// cartridgeCaliber is optional — when given, restricts to guns/TC barrels chambered in that
// caliber (tolerant match — see _calibersMatch). Falls back to showing everything if the
// filter would leave zero options, same fallback pattern as bullets.
function _buildGunOptionsHTML(items, tcBarrels, placeholder, cartridgeCaliber) {
    let gunItems = items, tcItems = tcBarrels;
    if (cartridgeCaliber) {
        const filteredGuns = items.filter(g => _calibersMatch(g.caliber, cartridgeCaliber));
        const filteredTc = tcBarrels.filter(b => _calibersMatch(b.caliber, cartridgeCaliber));
        if (filteredGuns.length || filteredTc.length) { gunItems = filteredGuns; tcItems = filteredTc; }
    }
    const rifles   = gunItems.filter(g => g.frame_type !== 'Shotgun' && g.frame_type !== 'Pistol');
    const shotguns = gunItems.filter(g => g.frame_type === 'Shotgun');
    const handguns = gunItems.filter(g => g.frame_type === 'Pistol');

    let html = `<option value="">${placeholder}</option>`;
    if (rifles.length > 0) {
        html += `<optgroup label="── Rifles ──">` +
            rifles.map(g => `<option value="${g.id}">${g.brand} ${g.model}</option>`).join('') +
            `</optgroup>`;
    }
    if (shotguns.length > 0) {
        html += `<optgroup label="── Shotguns ──">` +
            shotguns.map(g => `<option value="${g.id}">${g.brand} ${g.model}</option>`).join('') +
            `</optgroup>`;
    }
    if (handguns.length > 0) {
        html += `<optgroup label="── Handguns ──">` +
            handguns.map(g => `<option value="${g.id}">${g.brand} ${g.model}</option>`).join('') +
            `</optgroup>`;
    }
    if (tcItems.length > 0) {
        html += `<optgroup label="── Thompson Center Barrels ──">` +
            tcItems.map(b => `<option value="${b.id}" data-type="tc">${b.tc_platform} ${b.caliber}</option>`).join('') +
            `</optgroup>`;
    }
    return html;
}

// Resolves a gun <select>'s current selection to a real barrels.id — TC options already
// carry a barrel id; regular firearms need an async lookup for their first barrel.
async function resolveBarrelIdFromGunSelect(selectEl) {
    if (!selectEl || !selectEl.value) return null;
    const opt = selectEl.options[selectEl.selectedIndex];
    if (opt && opt.dataset.type === 'tc') return parseInt(selectEl.value);
    try {
        const res = await fetch(`/firearms/${selectEl.value}`);
        if (res.ok) {
            const data = await res.json();
            return (data.barrels && data.barrels.length > 0) ? data.barrels[0].id : null;
        }
    } catch (_) {}
    return null;
}

async function setupMeasureDropdowns() {
    const gunSelect = document.getElementById('select-gun');
    const ammoSelect = document.getElementById('select-ammo');
    if (!gunSelect || !ammoSelect) return;

    const dateInput = document.getElementById('session-date');
    if (dateInput && !dateInput.value) {
        dateInput.value = new Date().toISOString().split('T')[0];
    }
    try {
        const [gunsRes, tcRes, ammoRes] = await Promise.all([
            fetch('/catalog/'), fetch('/tc-barrels/'), fetch('/ammo/')
        ]);
        const items    = gunsRes.ok ? await gunsRes.json() : [];
        const tcBarrels = tcRes.ok  ? await tcRes.json()   : [];
        const ammoItems = ammoRes.ok ? await ammoRes.json() : [];

        gunSelect.innerHTML = _buildGunOptionsHTML(items, tcBarrels, '-- Select Platform --');

        if (ammoItems.length > 0) {
            const _ammoLabel = a => {
                const isSg = a.ammo_category === 'shotgun' || a.ammo_category === 'shotgun_slug';
                if (isSg) return `${a.brand}${a.caliber ? ' ' + a.caliber : ''}${a.shell_size ? ' ' + a.shell_size + '"' : ''} (Shotgun)`;
                return `${a.brand}${a.bullet_weight ? ' (' + a.bullet_weight + 'gr)' : ''}`;
            };
            ammoSelect.innerHTML = `<option value="">-- Select Load Profile --</option>` +
                ammoItems.map(a => `<option value="${a.id}">${_ammoLabel(a)}</option>`).join('');
        }
    } catch(e) {}
}

const targetUpload = document.getElementById('target-upload');
if (targetUpload) {
    targetUpload.addEventListener('change', function(e) {
        const file = e.target.files[0]; if (!file) return;
        const reader = new FileReader();
        reader.onload = function(event) {
            imgElement.onload = function() {
                canvas.width = imgElement.naturalWidth; canvas.height = imgElement.naturalHeight;
                state = "calibrating"; calibrationPoints = []; currentGroupShots = []; groups = []; pixelsPerInch = null; resetDragState();
                
                const banner = document.getElementById('status-banner');
                const calBox = document.getElementById('calibration-box');
                const envBox = document.getElementById('session-environment');
                const metaBox = document.getElementById('group-metadata');
                const liveRes = document.getElementById('live-result');
                const dlBtn = document.getElementById('download-btn');
                const saveBtn = document.getElementById('db-save-session-btn');
                
                if (banner) {
                    banner.classList.remove('hidden');
                    banner.innerText = "Step 1: Click TWO points on target grid matching reference scale line intersection.";
                }
                if (calBox) calBox.classList.add('hidden');
                if (envBox) envBox.classList.remove('hidden');
                if (metaBox) metaBox.classList.add('hidden');
                if (liveRes) liveRes.classList.add('hidden');
                if (dlBtn) dlBtn.classList.add('hidden');
                if (saveBtn) saveBtn.classList.add('hidden');
                
                updateSidebarList(); redrawCanvas();
            };
            imgElement.src = event.target.result;
        };
        reader.readAsDataURL(file);
    });
}

function resetDragState() { liveBoxPos = { x: 0, y: 0, customized: false }; isDraggingBox = false; isDraggingLabelIdx = null; }
function getCanvasCoords(e) {
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width; const scaleY = canvas.height / rect.height;
    let clientX, clientY;
    if (e.touches && e.touches.length > 0) {
        clientX = e.touches[0].clientX; clientY = e.touches[0].clientY;
    } else if (e.changedTouches && e.changedTouches.length > 0) {
        // touchend has an empty e.touches; use changedTouches for the released finger position
        clientX = e.changedTouches[0].clientX; clientY = e.changedTouches[0].clientY;
    } else {
        clientX = e.clientX; clientY = e.clientY;
    }
    return { x: (clientX - rect.left) * scaleX, y: (clientY - rect.top) * scaleY };
}

if (canvas) {
    canvas.addEventListener('mousedown', handleStart);
    canvas.addEventListener('touchstart', handleStart, { passive: false });
    canvas.addEventListener('mousemove', handleMove);
    canvas.addEventListener('touchmove', handleMove, { passive: false });
    canvas.addEventListener('mouseup', handleEnd);
    canvas.addEventListener('touchend', handleEnd);
}

function handleStart(e) {
    if (state === "idle") return;
    if (e.touches && e.touches.length > 1) { isMultiTouch = true; return; }
    if (e.touches) {
        // New touch gesture starting — clear the flag so touch path runs fresh.
        touchHandled = false;
    } else if (touchHandled) {
        // Synthetic mousedown fired by the browser after touchend — skip it.
        return;
    }
    isMultiTouch = false;
    touchStartClientPos = e.touches ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : null;
    const coords = getCanvasCoords(e);
    if (state === "measuring") {
        if (coords.x >= liveBoxPos.x && coords.x <= liveBoxPos.x + liveBoxDims.w && coords.y >= liveBoxPos.y && coords.y <= liveBoxPos.y + liveBoxDims.h) {
            isDraggingBox = true; dragOffset.x = coords.x - liveBoxPos.x; dragOffset.y = coords.y - liveBoxPos.y; return;
        }
    }
}
function handleMove(e) {
    if (state === "idle") return;
    if (e.touches && e.touches.length > 1) { isMultiTouch = true; }
    const coords = getCanvasCoords(e);
    if (isDraggingBox) { e.preventDefault(); liveBoxPos.x = coords.x - dragOffset.x; liveBoxPos.y = coords.y - dragOffset.y; liveBoxPos.customized = true; redrawCanvas(); }
}
function handleEnd(e) {
    if (state === "idle") return;
    if (e.changedTouches) {
        // touchend: mark that touch is handling this gesture so the synthetic mouseup is ignored.
        touchHandled = true;
    } else if (touchHandled) {
        // Synthetic mouseup fired by the browser after touchend — skip it.
        touchHandled = false;
        return;
    }
    const wasMultiTouch = isMultiTouch;
    if (e.touches && e.touches.length === 0) { isMultiTouch = false; }
    if (wasMultiTouch) { isDraggingBox = false; touchStartClientPos = null; return; }
    if (isDraggingBox) { isDraggingBox = false; return; }
    if (touchStartClientPos && e.changedTouches) {
        const dx = e.changedTouches[0].clientX - touchStartClientPos.x;
        const dy = e.changedTouches[0].clientY - touchStartClientPos.y;
        touchStartClientPos = null;
        if (Math.sqrt(dx * dx + dy * dy) > 10) return;
    }
    touchStartClientPos = null;
    const coords = getCanvasCoords(e);
    if (state === "calibrating") {
        if (calibrationPoints.length < 2) calibrationPoints.push({ x: coords.x, y: coords.y });
        redrawCanvas();
        if (calibrationPoints.length === 2) {
            const calBox = document.getElementById('calibration-box');
            const banner = document.getElementById('status-banner');
            if (calBox) calBox.classList.remove('hidden');
            if (banner) banner.innerText = "Input exact physical scale dimension width (Inches) and click Lock Calibration.";
        }
    } else if (state === "measuring") {
        const sNum = currentGroupShots.length + 1;
        const vIn = prompt(`Enter Velocity (fps) for Shot #${sNum} (Optional):`);
        let velocity = vIn && !isNaN(parseFloat(vIn)) ? parseFloat(vIn) : null;
        currentGroupShots.push({ x: coords.x, y: coords.y, velocity: velocity });
        if (currentGroupShots.length >= 2) updateLiveResults();
        redrawCanvas();
    }
}

function lockCalibration() {
    const refInches = document.getElementById('ref-inches');
    if (!refInches) return;
    const inches = parseFloat(refInches.value);
    if (calibrationPoints.length < 2 || isNaN(inches) || inches <= 0) return;
    pixelsPerInch = Math.sqrt(Math.pow(calibrationPoints[1].x - calibrationPoints[0].x, 2) + Math.pow(calibrationPoints[1].y - calibrationPoints[0].y, 2)) / inches;
    state = "measuring";
    
    const calBox = document.getElementById('calibration-box');
    const metaBox = document.getElementById('group-metadata');
    if (calBox) calBox.classList.add('hidden');
    if (metaBox) metaBox.classList.remove('hidden');
}

function resetCalibration() {
    calibrationPoints = [];
    pixelsPerInch = null;
    currentGroupShots = [];
    state = "calibrating";
    const calBox = document.getElementById('calibration-box');
    const metaBox = document.getElementById('group-metadata');
    const banner = document.getElementById('status-banner');
    const liveRes = document.getElementById('live-result');
    if (calBox) calBox.classList.add('hidden');
    if (metaBox) metaBox.classList.add('hidden');
    if (liveRes) liveRes.classList.add('hidden');
    if (banner) banner.innerText = "Step 1: Click TWO points on target grid matching reference scale line intersection.";
    redrawCanvas();
}

function updateLiveResults() {
    if (currentGroupShots.length < 2 || !pixelsPerInch) return;
    const liveRes = document.getElementById('live-result');
    if (liveRes) {
        liveRes.classList.remove('hidden');
        liveRes.innerText = `Current Span: ${(findMaxDistance(currentGroupShots) / pixelsPerInch).toFixed(3)}"`;
    }
}

function findMaxDistance(pts) {
    let maxDist = 0;
    for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
            const d = Math.sqrt(Math.pow(pts[j].x - pts[i].x, 2) + Math.pow(pts[j].y - pts[i].y, 2));
            if (d > maxDist) maxDist = d;
        }
    }
    return maxDist;
}

function saveCurrentGroup() {
    if (currentGroupShots.length < 2) {
        showToast("Need at least 2 shots to save a group.", "error");
        return;
    }
    const gunSelect = document.getElementById('select-gun');
    const ammoSelect = document.getElementById('select-ammo');
    if (!gunSelect || !gunSelect.value) {
        showToast("Please select a Firearm before saving.", "error");
        return;
    }
    if (!ammoSelect || !ammoSelect.value) {
        showToast("Please select a Load Profile before saving.", "error");
        return;
    }

    const size = (findMaxDistance(currentGroupShots) / pixelsPerInch).toFixed(3);
    const groupData = {
        shots: [...currentGroupShots],
        size,
        gunText: gunSelect.options[gunSelect.selectedIndex].text,
        ammoText: ammoSelect.options[ammoSelect.selectedIndex].text,
        boxX: liveBoxPos.x,
        boxY: liveBoxPos.y,
        chrono: null,
        dateText: "",
        tempText: "",
        cropRect: null
    };

    if (imgElement.src && imgElement.naturalWidth > 0) {
        openCropModal(groupData);
    } else {
        commitGroupToList(groupData);
    }
}

function commitGroupToList(groupData) {
    groups.push(groupData);
    currentGroupShots = [];
    const liveRes = document.getElementById('live-result');
    if (liveRes) liveRes.classList.add('hidden');
    resetDragState();
    updateSidebarList();
    redrawCanvas();
    showToast(`Group ${groups.length} saved — ${groupData.size}"`);
}

function openCropModal(groupData) {
    pendingGroupData = groupData;
    const cropCanvas = document.getElementById('crop-canvas');

    const MAX_W = 820, MAX_H = 520;
    cropDisplayScale = Math.min(MAX_W / canvas.width, MAX_H / canvas.height, 1);
    cropCanvas.width = Math.round(canvas.width * cropDisplayScale);
    cropCanvas.height = Math.round(canvas.height * cropDisplayScale);

    // Pre-select a crop region around the shot bounding box + padding
    const shots = groupData.shots;
    const PAD = 200;
    const minX = Math.max(0, Math.min(...shots.map(s => s.x)) - PAD);
    const minY = Math.max(0, Math.min(...shots.map(s => s.y)) - PAD);
    const maxX = Math.min(canvas.width,  Math.max(...shots.map(s => s.x)) + PAD);
    const maxY = Math.min(canvas.height, Math.max(...shots.map(s => s.y)) + PAD);
    cropRect = { x: minX, y: minY, w: maxX - minX, h: maxY - minY };

    drawCropOverlay();
    document.getElementById('crop-modal').classList.remove('hidden');

    cropCanvas.onmousedown  = cropHandleStart;
    cropCanvas.onmousemove  = cropHandleMove;
    cropCanvas.onmouseup    = cropHandleEnd;
    cropCanvas.onmouseleave = cropHandleEnd;
    cropCanvas.ontouchstart = (e) => { e.preventDefault(); cropHandleStart(e.touches[0]); };
    cropCanvas.ontouchmove  = (e) => { e.preventDefault(); cropHandleMove(e.touches[0]); };
    cropCanvas.ontouchend   = cropHandleEnd;
}

function drawCropOverlay() {
    const cropCanvas = document.getElementById('crop-canvas');
    const cropCtx = cropCanvas.getContext('2d');
    const s = cropDisplayScale;

    cropCtx.clearRect(0, 0, cropCanvas.width, cropCanvas.height);
    cropCtx.drawImage(imgElement, 0, 0, cropCanvas.width, cropCanvas.height);

    // Shot dots for reference
    if (pendingGroupData) {
        pendingGroupData.shots.forEach((p, i) => {
            pendingGroupData.shots.forEach((q, j) => {
                if (j <= i) return;
                cropCtx.strokeStyle = '#ef4444';
                cropCtx.lineWidth = Math.max(2, 4 * s);
                cropCtx.beginPath();
                cropCtx.moveTo(p.x * s, p.y * s);
                cropCtx.lineTo(q.x * s, q.y * s);
                cropCtx.stroke();
            });
            cropCtx.fillStyle = '#ef4444';
            cropCtx.beginPath();
            cropCtx.arc(p.x * s, p.y * s, Math.max(4, 7 * s), 0, Math.PI * 2);
            cropCtx.fill();
        });
    }

    const rx = cropRect.x * s, ry = cropRect.y * s;
    const rw = cropRect.w * s, rh = cropRect.h * s;

    // Dark vignette outside crop region
    cropCtx.fillStyle = 'rgba(0,0,0,0.62)';
    cropCtx.fillRect(0, 0, cropCanvas.width, ry);
    cropCtx.fillRect(0, ry + rh, cropCanvas.width, cropCanvas.height - ry - rh);
    cropCtx.fillRect(0, ry, rx, rh);
    cropCtx.fillRect(rx + rw, ry, cropCanvas.width - rx - rw, rh);

    // Crop border
    cropCtx.strokeStyle = '#f59e0b';
    cropCtx.lineWidth = 2;
    cropCtx.strokeRect(rx, ry, rw, rh);

    // Rule-of-thirds grid
    cropCtx.strokeStyle = 'rgba(255,255,255,0.18)';
    cropCtx.lineWidth = 0.5;
    cropCtx.beginPath();
    cropCtx.moveTo(rx + rw/3, ry);    cropCtx.lineTo(rx + rw/3, ry + rh);
    cropCtx.moveTo(rx + 2*rw/3, ry); cropCtx.lineTo(rx + 2*rw/3, ry + rh);
    cropCtx.moveTo(rx, ry + rh/3);   cropCtx.lineTo(rx + rw, ry + rh/3);
    cropCtx.moveTo(rx, ry + 2*rh/3); cropCtx.lineTo(rx + rw, ry + 2*rh/3);
    cropCtx.stroke();

    // Corner handles
    const HS = 9;
    cropCtx.fillStyle = '#f59e0b';
    [[rx, ry], [rx + rw, ry], [rx, ry + rh], [rx + rw, ry + rh]].forEach(([hx, hy]) => {
        cropCtx.fillRect(hx - HS/2, hy - HS/2, HS, HS);
    });
}

function getCropCanvasPos(e) {
    const cropCanvas = document.getElementById('crop-canvas');
    const rect = cropCanvas.getBoundingClientRect();
    const sx = cropCanvas.width / rect.width;
    const sy = cropCanvas.height / rect.height;
    return { x: (e.clientX - rect.left) * sx, y: (e.clientY - rect.top) * sy };
}

function getCropHitMode(dx, dy) {
    const s = cropDisplayScale;
    const rx = cropRect.x * s, ry = cropRect.y * s;
    const rw = cropRect.w * s, rh = cropRect.h * s;
    const HIT = 12;
    if (Math.abs(dx - rx) <= HIT && Math.abs(dy - ry) <= HIT)           return 'nw';
    if (Math.abs(dx - (rx+rw)) <= HIT && Math.abs(dy - ry) <= HIT)      return 'ne';
    if (Math.abs(dx - rx) <= HIT && Math.abs(dy - (ry+rh)) <= HIT)      return 'sw';
    if (Math.abs(dx - (rx+rw)) <= HIT && Math.abs(dy - (ry+rh)) <= HIT) return 'se';
    if (dx >= rx && dx <= rx+rw && dy >= ry && dy <= ry+rh)              return 'move';
    return 'draw';
}

function cropHandleStart(e) {
    const { x: dx, y: dy } = getCropCanvasPos(e);
    cropDragState = { active: true, mode: getCropHitMode(dx, dy), startX: dx, startY: dy, origRect: { ...cropRect } };
}

function cropHandleMove(e) {
    if (!cropDragState.active) return;
    const { x: dx, y: dy } = getCropCanvasPos(e);
    const s = cropDisplayScale;
    const W = canvas.width, H = canvas.height;
    const orig = cropDragState.origRect;
    const dxC = (dx - cropDragState.startX) / s;
    const dyC = (dy - cropDragState.startY) / s;

    if (cropDragState.mode === 'move') {
        cropRect.x = Math.max(0, Math.min(W - orig.w, orig.x + dxC));
        cropRect.y = Math.max(0, Math.min(H - orig.h, orig.y + dyC));
    } else if (cropDragState.mode === 'draw') {
        const cx = dx / s, cy = dy / s;
        const sx = cropDragState.startX / s, sy = cropDragState.startY / s;
        cropRect.x = Math.max(0, Math.min(cx, sx));
        cropRect.y = Math.max(0, Math.min(cy, sy));
        cropRect.w = Math.min(Math.abs(cx - sx), W - cropRect.x);
        cropRect.h = Math.min(Math.abs(cy - sy), H - cropRect.y);
    } else {
        let nx = orig.x, ny = orig.y, nw = orig.w, nh = orig.h;
        if (cropDragState.mode === 'nw') { nx = orig.x + dxC; ny = orig.y + dyC; nw = orig.w - dxC; nh = orig.h - dyC; }
        if (cropDragState.mode === 'ne') { ny = orig.y + dyC; nw = orig.w + dxC; nh = orig.h - dyC; }
        if (cropDragState.mode === 'sw') { nx = orig.x + dxC; nw = orig.w - dxC; nh = orig.h + dyC; }
        if (cropDragState.mode === 'se') { nw = orig.w + dxC; nh = orig.h + dyC; }
        if (nw > 30 && nh > 30) {
            cropRect.x = Math.max(0, nx); cropRect.y = Math.max(0, ny);
            cropRect.w = Math.min(nw, W - cropRect.x); cropRect.h = Math.min(nh, H - cropRect.y);
        }
    }
    drawCropOverlay();
}

function cropHandleEnd() { cropDragState.active = false; }

function cropConfirm() {
    if (pendingGroupData) {
        pendingGroupData.cropRect = cropRect.w > 0 && cropRect.h > 0 ? { ...cropRect } : null;
        commitGroupToList(pendingGroupData);
        pendingGroupData = null;
    }
    closeCropModal();
}

function cropSaveFullImage() {
    if (pendingGroupData) {
        pendingGroupData.cropRect = null;
        commitGroupToList(pendingGroupData);
        pendingGroupData = null;
    }
    closeCropModal();
}

function closeCropModal() {
    document.getElementById('crop-modal').classList.add('hidden');
    const cropCanvas = document.getElementById('crop-canvas');
    cropCanvas.onmousedown = cropCanvas.onmousemove = cropCanvas.onmouseup = cropCanvas.onmouseleave = null;
    cropCanvas.ontouchstart = cropCanvas.ontouchmove = cropCanvas.ontouchend = null;
}

function redrawCanvas() {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (imgElement.src) ctx.drawImage(imgElement, 0, 0);

    // Draw saved groups with their overlay boxes
    groups.forEach(g => {
        drawConnections(g.shots, '#ef4444', 6);
        drawStatsBox(g.shots, g.size, g.boxX, g.boxY, g.ammoText, g.gunText);
    });

    // Draw current in-progress shots
    if (currentGroupShots.length > 0) {
        drawConnections(currentGroupShots, '#3b82f6', 6);
        if (currentGroupShots.length >= 2 && pixelsPerInch) {
            const size = (findMaxDistance(currentGroupShots) / pixelsPerInch).toFixed(3);
            const gunSel  = document.getElementById('select-gun');
            const ammoSel = document.getElementById('select-ammo');
            const livePlatform = gunSel?.selectedIndex  > 0 ? gunSel.options[gunSel.selectedIndex].text   : '';
            const liveLoad     = ammoSel?.selectedIndex > 0 ? ammoSel.options[ammoSel.selectedIndex].text : '';
            drawStatsBox(currentGroupShots, size, liveBoxPos.x, liveBoxPos.y, liveLoad, livePlatform);
        }
    }

    // Draw calibration points as blue dots with a line between them
    if (calibrationPoints.length > 0) {
        const s = canvasScale();
        ctx.fillStyle = '#3b82f6';
        ctx.strokeStyle = '#3b82f6';
        ctx.lineWidth = 3 * s;
        calibrationPoints.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, 10 * s, 0, Math.PI * 2);
            ctx.fill();
        });
        if (calibrationPoints.length === 2) {
            ctx.beginPath();
            ctx.setLineDash([10 * s, 6 * s]);
            ctx.moveTo(calibrationPoints[0].x, calibrationPoints[0].y);
            ctx.lineTo(calibrationPoints[1].x, calibrationPoints[1].y);
            ctx.stroke();
            ctx.setLineDash([]);
        }
    }
}

function drawStatsBox(shots, sizeInches, boxX, boxY, loadLabel, platformLabel) {
    if (!shots || shots.length < 2) return;

    const velocities = shots.map(s => s.velocity).filter(v => v !== null);
    const hasChrono = velocities.length > 0;

    const trunc = (s, n) => s && s.length > n ? s.slice(0, n - 1) + '…' : (s || '');
    const loadStr = trunc(loadLabel, 34);
    const platStr = trunc(platformLabel, 34);

    const s = canvasScale();
    const fs = (n) => `${Math.round(n * s)}px`;

    // Build lines: [text, font, color, lineAdvance]
    const lines = [
        [`GROUP: ${sizeInches}"`, `bold ${fs(24)} monospace`, '#f59e0b', 32 * s],
    ];
    if (loadStr) lines.push([loadStr, `bold ${fs(17)} monospace`, '#a3e635', 23 * s]);
    if (platStr) lines.push([platStr, `${fs(16)} monospace`,      '#60a5fa', 22 * s]);
    lines.push([`${shots.length} shots`, `${fs(17)} monospace`, '#9ca3af', 23 * s]);

    if (hasChrono) {
        const avg = Math.round(velocities.reduce((a, b) => a + b, 0) / velocities.length);
        const es  = Math.max(...velocities) - Math.min(...velocities);
        const sd  = velocities.length > 1
            ? Math.sqrt(velocities.reduce((a, v) => a + Math.pow(v - avg, 2), 0) / (velocities.length - 1)).toFixed(1)
            : 0;
        lines.push([`AVG: ${avg} fps`,             `bold ${fs(20)} monospace`, '#60a5fa', 28 * s]);
        lines.push([`ES: ${es}  SD: ${sd}`,         `${fs(17)} monospace`,     '#9ca3af', 23 * s]);
    }

    // Measure widest line to set box width
    const HPAD = 20 * s, VTOP = 16 * s, VBOT = 14 * s;
    let maxW = 0;
    lines.forEach(([text, font]) => {
        ctx.font = font;
        maxW = Math.max(maxW, ctx.measureText(text).width);
    });
    const BOX_W = Math.ceil(maxW) + HPAD * 2;
    const BOX_H = VTOP + lines.reduce((sum, [,,, adv]) => sum + adv, 0) + VBOT;

    liveBoxDims.w = BOX_W;
    liveBoxDims.h = BOX_H;

    // Auto-position near centroid if not customized
    if (!liveBoxPos.customized && boxX === 0 && boxY === 0) {
        const cx = shots.reduce((a, s) => a + s.x, 0) / shots.length;
        const cy = shots.reduce((a, s) => a + s.y, 0) / shots.length;
        boxX = Math.min(cx + 20, canvas.width - BOX_W - 10);
        boxY = Math.max(cy - BOX_H / 2, 10);
        liveBoxPos.x = boxX;
        liveBoxPos.y = boxY;
    }

    // Draw background
    ctx.fillStyle = 'rgba(10, 10, 20, 0.88)';
    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 3 * s;
    ctx.beginPath();
    ctx.roundRect(boxX, boxY, BOX_W, BOX_H, 8 * s);
    ctx.fill();
    ctx.stroke();

    // Draw each line
    const px = boxX + HPAD;
    let py = boxY + VTOP;
    lines.forEach(([text, font, color, advance]) => {
        ctx.font = font;
        ctx.fillStyle = color;
        // offset baseline by approx ascent (80% of font size)
        const size = parseInt(font.match(/(\d+)px/)[1]);
        py += size * 0.82;
        ctx.fillText(text, px, py);
        py += advance - size * 0.82;
    });
}

function canvasScale() { return Math.max(1, canvas.width / 800); }

function drawConnections(shots, color, width) {
    if (!ctx) return;
    const s = canvasScale();
    ctx.strokeStyle = color; ctx.lineWidth = width * s;
    for (let i = 0; i < shots.length; i++) {
        for (let j = i + 1; j < shots.length; j++) {
            ctx.beginPath(); ctx.moveTo(shots[i].x, shots[i].y); ctx.lineTo(shots[j].x, shots[j].y); ctx.stroke();
        }
    }
    shots.forEach(p => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(p.x, p.y, 8 * s, 0, Math.PI * 2); ctx.fill(); });
}

function deleteGroup(idx) {
    groups.splice(idx, 1);
    updateSidebarList();
    redrawCanvas();
}

function updateSidebarList() {
    const list = document.getElementById('session-groups-list');
    const saveBtn  = document.getElementById('db-save-session-btn');
    const dlBtn    = document.getElementById('download-btn');
    const shareBtn = document.getElementById('share-btn');
    if (!list) return;

    if (groups.length === 0) {
        list.innerHTML = `<p class="text-xs text-gray-500 italic">No groups recorded in this session yet.</p>`;
        if (saveBtn)  saveBtn.classList.add('hidden');
        if (dlBtn)    dlBtn.classList.add('hidden');
        if (shareBtn) shareBtn.classList.add('hidden');
        return;
    }

    list.innerHTML = groups.map((g, idx) => {
        const velocities = g.shots.map(s => s.velocity).filter(v => v !== null);
        const avgVel = velocities.length > 0
            ? Math.round(velocities.reduce((a, b) => a + b, 0) / velocities.length)
            : null;
        const velLine = avgVel !== null
            ? `<span class="text-blue-400 font-mono">${avgVel} fps avg</span> · <span class="text-gray-500">${velocities.length} shots</span>`
            : `<span class="text-gray-500">${g.shots.length} shots · no chrono</span>`;

        return `
        <div class="bg-gray-900 border border-gray-700 rounded-lg p-3 space-y-1.5">
            <div class="flex justify-between items-start">
                <span class="text-[10px] font-bold uppercase tracking-wider text-amber-500">Group ${idx + 1}</span>
                <button onclick="deleteGroup(${idx})"
                    class="text-red-500 hover:text-red-400 text-[10px] font-bold cursor-pointer leading-none">✕ Remove</button>
            </div>
            <p class="text-xs font-bold text-white truncate">${g.gunText}</p>
            <p class="text-[11px] text-gray-400 truncate">${g.ammoText}</p>
            <div class="flex justify-between items-center pt-1 border-t border-gray-750">
                <span class="text-emerald-400 font-mono font-bold text-sm">${g.size}&quot;</span>
                <span class="text-[11px]">${velLine}</span>
            </div>
        </div>`;
    }).join('');

    if (saveBtn)  saveBtn.classList.remove('hidden');
    if (dlBtn)    dlBtn.classList.remove('hidden');
    if (shareBtn) shareBtn.classList.remove('hidden');
}
function saveForShare() {
    if (!canvas || groups.length === 0) return;

    const FOOTER_H = 60;
    const off = document.createElement('canvas');
    off.width  = canvas.width;
    off.height = canvas.height + FOOTER_H;
    const octx = off.getContext('2d');

    // Main annotated canvas (already has all stats boxes drawn)
    octx.drawImage(canvas, 0, 0);

    // Footer banner
    octx.fillStyle = '#050508';
    octx.fillRect(0, canvas.height, canvas.width, FOOTER_H);

    // Amber top edge
    octx.strokeStyle = '#f59e0b';
    octx.lineWidth = 2;
    octx.beginPath();
    octx.moveTo(0, canvas.height + 1);
    octx.lineTo(canvas.width, canvas.height + 1);
    octx.stroke();

    const dateStr = new Date().toISOString().slice(0, 10);
    const groupSummary = groups.map((g, i) => `G${i + 1}: ${g.size}"`).join('   ');
    const gunLabel = groups[0]?.gunText || '';

    const fontSize = Math.max(14, Math.min(22, Math.round(canvas.width / 55)));
    const midY = canvas.height + FOOTER_H / 2 + fontSize * 0.38;

    octx.font = `bold ${fontSize}px monospace`;
    octx.fillStyle = '#f59e0b';
    octx.textAlign = 'left';
    octx.fillText('🎯 ' + groupSummary, 20, midY);

    octx.font = `${Math.round(fontSize * 0.82)}px monospace`;
    octx.fillStyle = '#6b7280';
    octx.textAlign = 'right';
    octx.fillText((gunLabel ? gunLabel + '  ·  ' : '') + dateStr, canvas.width - 20, midY);
    octx.textAlign = 'left';

    const link = document.createElement('a');
    link.download = `range_session_${dateStr}.png`;
    link.href = off.toDataURL('image/png');
    link.click();
}
function downloadAnnotatedTarget() {
    if (!canvas || groups.length === 0) return;

    // Work on an offscreen copy so we don't dirty the live canvas
    const offscreen = document.createElement('canvas');
    offscreen.width = canvas.width;
    offscreen.height = canvas.height;
    const octx = offscreen.getContext('2d');

    // 1. Draw the base image
    octx.drawImage(imgElement, 0, 0);

    // 2. Re-draw all saved group lines & dots
    groups.forEach(g => {
        octx.strokeStyle = '#ef4444';
        octx.lineWidth = 6;
        for (let i = 0; i < g.shots.length; i++) {
            for (let j = i + 1; j < g.shots.length; j++) {
                octx.beginPath();
                octx.moveTo(g.shots[i].x, g.shots[i].y);
                octx.lineTo(g.shots[j].x, g.shots[j].y);
                octx.stroke();
            }
        }
        g.shots.forEach(p => {
            octx.fillStyle = '#ef4444';
            octx.beginPath();
            octx.arc(p.x, p.y, 8, 0, Math.PI * 2);
            octx.fill();
        });
    });

    // 3. Draw a stats legend box in the top-left corner
    const PAD = 18, LINE = 22, BOX_W = 340;
    const labelLines = groups.map((g, idx) => {
        const velocities = g.shots.map(s => s.velocity).filter(v => v !== null);
        const avgVel = velocities.length > 0
            ? Math.round(velocities.reduce((a, b) => a + b, 0) / velocities.length)
            : null;
        const velStr = avgVel !== null ? `  ${avgVel} fps avg` : '';
        return `G${idx + 1}: ${g.size}"  ·  ${g.gunText}${velStr}`;
    });

    const BOX_H = PAD * 2 + LINE * (labelLines.length + 1);
    octx.fillStyle = 'rgba(10, 10, 20, 0.82)';
    octx.strokeStyle = '#f59e0b';
    octx.lineWidth = 2;
    octx.beginPath();
    octx.roundRect(PAD, PAD, BOX_W, BOX_H, 8);
    octx.fill();
    octx.stroke();

    octx.font = 'bold 16px monospace';
    octx.fillStyle = '#f59e0b';
    octx.fillText('SESSION RESULTS', PAD + 14, PAD + LINE);

    octx.font = '14px monospace';
    octx.fillStyle = '#e5e7eb';
    labelLines.forEach((line, i) => {
        octx.fillText(line, PAD + 14, PAD + LINE * (i + 2));
    });

    // 4. Trigger download
    const link = document.createElement('a');
    const dateStr = new Date().toISOString().slice(0, 10);
    link.download = `target_session_${dateStr}.png`;
    link.href = offscreen.toDataURL('image/png');
    link.click();
}
async function commitSessionToDatabase() {
    if (groups.length === 0) return;

    const dateInput = document.getElementById('session-date');
    const sessionDate = dateInput ? dateInput.value : new Date().toISOString().split('T')[0];

    const gunSelect = document.getElementById('select-gun');
    const ammoSelect = document.getElementById('select-ammo');

    const defaultGunId = gunSelect ? gunSelect.value : null;
    const defaultAmmoId = ammoSelect ? ammoSelect.value : null;

    if (!defaultGunId || !defaultAmmoId) {
        showToast("Please select a Firearm and Load Profile before saving to DB.", "error");
        return;
    }

    const saveBtn = document.getElementById('db-save-session-btn');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.innerText = "Uploading…"; }

    const barrelId = await resolveBarrelIdFromGunSelect(gunSelect);

    if (!barrelId) {
        showToast("Could not resolve barrel for selected platform.", "error");
        if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = "🚀 Upload Data to Homelab DB"; }
        return;
    }

    let successCount = 0;
    let failCount = 0;

    for (const g of groups) {
        const velocities = g.shots.map(s => s.velocity).filter(v => v !== null);
        const velocitiesCsv = velocities.length > 0 ? velocities.join(',') : '';

        // Build per-group image blob, respecting saved crop region
        let groupBlob = null;
        if (imgElement.src && imgElement.naturalWidth > 0) {
            if (g.cropRect && g.cropRect.w > 0 && g.cropRect.h > 0) {
                const off = document.createElement('canvas');
                off.width  = Math.round(g.cropRect.w);
                off.height = Math.round(g.cropRect.h);
                off.getContext('2d').drawImage(
                    canvas,
                    g.cropRect.x, g.cropRect.y, g.cropRect.w, g.cropRect.h,
                    0, 0, off.width, off.height
                );
                groupBlob = await new Promise(resolve => off.toBlob(resolve, 'image/jpeg', 0.88));
            } else {
                groupBlob = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.88));
            }
        }

        const formData = new FormData();
        formData.append('barrel_id', barrelId);
        formData.append('ammo_id', defaultAmmoId);
        formData.append('date', sessionDate);
        formData.append('velocities_csv', velocitiesCsv);
        formData.append('rounds_fired', String(g.shots.length));
        formData.append('group_size', g.size);
        if (groupBlob) formData.append('target_image', groupBlob, 'target.jpg');

        try {
            const res = await fetch('/performance-log/', { method: 'POST', body: formData });
            if (res.ok) { successCount++; } else { failCount++; }
        } catch (_) { failCount++; }
    }

    if (saveBtn) { saveBtn.disabled = false; saveBtn.innerText = "🚀 Upload Data to Homelab DB"; }

    if (failCount === 0) {
        showToast(`${successCount} group${successCount > 1 ? 's' : ''} committed to database.`);
        groups = [];
        updateSidebarList();
        redrawCanvas();
    } else {
        showToast(`${successCount} saved, ${failCount} failed. Check console for details.`, "error");
    }
}
function resetCanvas() { calibrationPoints = []; currentGroupShots = []; groups = []; pixelsPerInch = null; state = imgElement.src ? "calibrating" : "idle"; redrawCanvas(); }

async function loadCatalog(frameType = currentFrameType()) {
    const container = document.getElementById('catalog-container');
    if (!container) return;
    const url = `/catalog/?frame_type=${encodeURIComponent(frameType)}`;
    let all;
    try {
        const response = await fetch(url);
        if (!response.ok) { container.innerHTML = '<p class="text-red-400 italic text-sm">Failed to load catalog.</p>'; return; }
        all = await response.json();
    } catch(err) {
        container.innerHTML = '<p class="text-red-400 italic text-sm">Failed to load catalog.</p>';
        return;
    }
    const filtered = all.filter(g => currentCollectionFilter === 'sold' ? g.is_sold : !g.is_sold).filter(matchesSearch);
    const inventory = applySortFn(filtered, currentPlatformSort);

    document.getElementById('inventory-count').innerText = `${inventory.length} Platform${inventory.length !== 1 ? 's' : ''} Logged`;
    container.innerHTML = '';

    inventory.forEach(gun => {
        const content = document.createElement('div');
        content.className = "bg-gray-800 border border-gray-700 rounded-lg overflow-hidden shadow-xl hover:border-amber-500/50 transition";
        
        let statusLabelMarkup = gun.is_sold 
            ? `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-red-950 text-red-400 border border-red-800">SOLD HISTORY ARCHIVE</span>`
            : `<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-950 text-blue-400 border border-blue-800">${gun.frame_type || 'Rifle'}</span>`;
        
        // Fix: Properly map the image and caliber from your DB fields
        const targetSrc = gun.image_path_1 || "/static/images/placeholder.jpg";
        const caliberDisplay = gun.caliber || (gun.frame_type === "Barrel Only" ? "Modular Frame" : "Multi-Caliber Base");

        const detailPage = gun.frame_type === 'Shotgun' ? 'shotgun-detail.html' : gun.frame_type === 'Pistol' ? 'handgun-detail.html' : 'firearm-detail.html';
        const gunLabel = `${gun.brand} ${gun.model}`;
        const soldBtnMarkup = gun.is_sold
            ? `<span class="text-xs text-red-400 font-mono">Sold $${parseFloat(gun.price_sold || 0).toFixed(2)}</span>`
            : `<button onclick="openSellModal(${gun.id},'${gunLabel.replace(/'/g,"\\'")}','firearm')" class="px-2 py-1 bg-gray-700 hover:bg-emerald-800 text-gray-300 hover:text-white text-xs font-bold rounded transition cursor-pointer">$ Sell</button>`;
        const gunFit = gun.frame_type === 'Pistol' ? 'contain' : 'cover';
        const gunGallery = makePhotoGallery(`gun-${gun.id}`, '🔫', gun.image_path_1, gun.image_path_2, gunFit);
        content.innerHTML = `
            <div onclick="window.location.href='${detailPage}?id=${gun.id}'" class="cursor-pointer">
                ${gunGallery}
            </div>
            <div class="p-4 space-y-3">
                <div class="flex justify-between items-center">
                    ${statusLabelMarkup}
                    <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-950 text-amber-400 border border-amber-800">${caliberDisplay}</span>
                </div>
                <div class="flex justify-between items-center gap-2 cursor-pointer hover:text-amber-400 transition" onclick="window.location.href='${detailPage}?id=${gun.id}'">
                    <h3 class="text-base font-bold text-white tracking-tight">${gunLabel}</h3>
                    <span class="text-xs text-gray-400 font-mono whitespace-nowrap">$${parseFloat(gun.price_paid || 0).toFixed(2)}</span>
                </div>
                ${gun.serial_number ? `<p class="text-xs text-gray-200 font-semibold font-mono">S/N: ${gun.serial_number}</p>` : ''}
                <div class="flex gap-2 pt-1 border-t border-gray-700">
                    ${soldBtnMarkup}
                    <div class="flex-1"></div>
                    <button onclick="trashItem('firearm',${gun.id},'${gunLabel.replace(/'/g,"\\'")}'); event.stopPropagation();" class="px-2 py-1 bg-gray-700 hover:bg-red-900 text-gray-400 hover:text-red-300 text-xs font-bold rounded transition cursor-pointer" title="Move to trash">🗑️</button>
                </div>
            </div>
        `;
        container.appendChild(content);
    });
}

function _submitBtn(form) { return form ? form.querySelector('[type=submit]') : null; }
function _setBusy(form, busy) {
    const btn = _submitBtn(form);
    if (!btn) return;
    if (busy) {
        btn._origText = btn.textContent;
        btn.disabled = true;
        btn.textContent = '⏳ Saving...';
        btn.style.opacity = '0.6';
        btn.style.cursor = 'not-allowed';
    } else {
        btn.disabled = false;
        btn.textContent = btn._origText || btn.textContent;
        btn.style.opacity = '';
        btn.style.cursor = '';
    }
}

const firearmForm = document.getElementById('firearm-form');
if (firearmForm) {
    firearmForm.addEventListener('submit', async (e) => {
        e.preventDefault(); _setBusy(firearmForm, true); const formData = new FormData(e.target);
        try {
            const response = await fetch('/firearms/', { method: 'POST', body: formData });
            if (response.ok) {
                const fd = formData;
                await Promise.all([
                    saveLookupValue('firearm_brand', fd.get('brand')),
                    saveLookupValue('firearm_model', fd.get('model')),
                    saveLookupValue('caliber',       fd.get('caliber')),
                ]);
                e.target.reset(); const ext = document.getElementById('tc-modular-extension'); if (ext) ext.classList.add('hidden');
                showToast('Hardware logged successfully.'); await fetchInitialLookupData(); switchTab('catalog-tab');
            } else {
                showToast('Asset data accepted locally for offline caching.', 'success');
                e.target.reset(); switchTab('catalog-tab');
            }
        } catch (err) { e.target.reset(); switchTab('catalog-tab'); }
    });
}

const shotgunForm = document.getElementById('shotgun-form');
if (shotgunForm) {
    shotgunForm.addEventListener('submit', async (e) => {
        e.preventDefault(); _setBusy(shotgunForm, true); const formData = new FormData(e.target);
        try {
            const response = await fetch('/firearms/', { method: 'POST', body: formData });
            if (response.ok) {
                const fd = formData;
                await Promise.all([
                    saveLookupValue('firearm_brand', fd.get('brand')),
                    saveLookupValue('firearm_model', fd.get('model')),
                ]);
                e.target.reset(); showToast('Shotgun logged successfully.'); switchTab('catalog-tab');
            } else { _setBusy(shotgunForm, false); showToast('Failed to save shotgun.', 'error'); }
        } catch (err) { _setBusy(shotgunForm, false); showToast('Failed to save shotgun.', 'error'); }
    });
}

const handgunForm = document.getElementById('handgun-form');
if (handgunForm) {
    handgunForm.addEventListener('submit', async (e) => {
        e.preventDefault(); _setBusy(handgunForm, true); const formData = new FormData(e.target);
        try {
            const response = await fetch('/firearms/', { method: 'POST', body: formData });
            if (response.ok) {
                const fd = formData;
                await Promise.all([
                    saveLookupValue('firearm_brand', fd.get('brand')),
                    saveLookupValue('firearm_model', fd.get('model')),
                    saveLookupValue('caliber',       fd.get('caliber')),
                ]);
                e.target.reset(); showToast('Handgun logged successfully.'); switchTab('catalog-tab');
            } else { _setBusy(handgunForm, false); showToast('Failed to save handgun.', 'error'); }
        } catch (err) { _setBusy(handgunForm, false); showToast('Failed to save handgun.', 'error'); }
    });
}

const factoryAmmoForm = document.getElementById('ammo-factory-form');
if (factoryAmmoForm) {
    factoryAmmoForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(factoryAmmoForm, true);
        const formData = new FormData(e.target);
        const { f1: af1, f2: af2 } = _getPWFiles('pw-ammo-factory');
        if (af1) formData.set('image', af1, af1.name);
        if (af2) formData.set('image_2', af2, af2.name);
        if (_lastScannedUpc) { formData.set('upc', _lastScannedUpc); _lastScannedUpc = null; }
        try {
            const response = await fetch('/ammo/', { method: 'POST', body: formData });
            if (response.ok) {
                await Promise.all([
                    saveLookupValue('ammo_brand', formData.get('brand')),
                    saveLookupValue('caliber',    formData.get('caliber')),
                ]);
                e.target.reset(); _resetPW('pw-ammo-factory'); _showPendingUpc(null);
                _setBusy(factoryAmmoForm, false);
                showToast('Factory load registered.');
            } else {
                _setBusy(factoryAmmoForm, false);
                showToast('Failed to save ammo load.', 'error');
            }
        } catch (err) {
            _setBusy(factoryAmmoForm, false);
            showToast('Error saving ammo load.', 'error');
        }
    });
}

const handloadForm = document.getElementById('ammo-handload-form');
if (handloadForm) {
    handloadForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(handloadForm, true);
        const formData = new FormData(e.target);
        formData.set('is_handload', 'true');
        // Auto-wire deduction IDs from the main dropdowns
        const _getId = id => { const s = document.getElementById(id); const o = s?.options[s.selectedIndex]; return o?.dataset?.id || ''; };
        formData.set('deduct_powder_id',  _getId('hl-powder'));
        formData.set('deduct_primer_id',  _getId('hl-primer'));
        formData.set('deduct_bullet_id',  _getId('hl-bullet'));
        formData.set('deduct_casing_id',  _getId('hl-casing'));
        const { f1: af1, f2: af2 } = _getPWFiles('pw-ammo-handload');
        if (af1) formData.set('image', af1, af1.name);
        if (af2) formData.set('image_2', af2, af2.name);
        try {
            const response = await fetch('/ammo/', { method: 'POST', body: formData });
            if (!response.ok) { _setBusy(handloadForm, false); showToast('Failed to save handload recipe.', 'error'); return; }

            await Promise.all([
                saveLookupValue('caliber',          formData.get('caliber')),
                saveLookupValue('handload_powder',  formData.get('powder_id')),
                saveLookupValue('handload_primer',  formData.get('primer_id')),
                saveLookupValue('handload_bullet',  formData.get('bullet_id')),
                saveLookupValue('handload_brass',   formData.get('brass_brand')),
            ]);

            // Run component deduction if the section was filled out
            const rounds = parseInt(formData.get('rounds_loaded'));
            const powderCharge = parseFloat(formData.get('powder_charge'));
            const powderId = formData.get('deduct_powder_id');
            const primerId = formData.get('deduct_primer_id');
            const bulletId = formData.get('deduct_bullet_id');
            const casingId = formData.get('deduct_casing_id');

            const hasDeduction = rounds > 0 && (powderId || primerId || bulletId || casingId);
            if (hasDeduction) {
                const payload = {
                    rounds_loaded: rounds,
                    powder_charge_gr: powderCharge || null,
                    powder_inv_id: powderId ? parseInt(powderId) : null,
                    primer_inv_id: primerId ? parseInt(primerId) : null,
                    bullet_inv_id: bulletId ? parseInt(bulletId) : null,
                    casing_inv_id: casingId ? parseInt(casingId) : null,
                };
                const dRes = await fetch('/components/deduct/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                if (dRes.ok) {
                    const { warnings } = await dRes.json();
                    warnings.forEach(w => showToast(w, 'error'));
                }
            }

            e.target.reset(); _resetPW('pw-ammo-handload');
            // Collapse deduct section and reset toggle
            const ds = document.getElementById('deduct-section');
            const di = document.getElementById('deduct-toggle-icon');
            if (ds) ds.classList.add('hidden');
            if (di) di.textContent = '▶';
            _setBusy(handloadForm, false);
            showToast('Handload committed.' + (hasDeduction ? ` Inventory updated for ${rounds} rounds.` : ''));
        } catch (err) {
            _setBusy(handloadForm, false);
            showToast('Error saving handload recipe.', 'error');
        }
    });
}

const tcReceiverForm = document.getElementById('tc-receiver-form');
if (tcReceiverForm) {
    tcReceiverForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(tcReceiverForm, true);
        const formData = new FormData(e.target);
        try {
            const res = await fetch('/tc-receivers/', { method: 'POST', body: formData });
            if (res.ok) {
                e.target.reset();
                showToast('TC Receiver registered.');
                window.location.href = '/inventory?inv=platforms&platform=tc';
            } else {
                _setBusy(tcReceiverForm, false);
                showToast('Failed to register TC Receiver.', 'error');
            }
        } catch (err) { _setBusy(tcReceiverForm, false); showToast('Error saving TC Receiver.', 'error'); }
    });
}

const tcBarrelForm = document.getElementById('tc-barrel-form');
if (tcBarrelForm) {
    tcBarrelForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(tcBarrelForm, true);
        const formData = new FormData(e.target);
        // Convert string "true"/"false" booleans from select elements
        formData.set('is_threaded', formData.get('is_threaded') === 'true');
        formData.set('has_muzzle_brake', formData.get('has_muzzle_brake') === 'true');
        try {
            const res = await fetch('/tc-barrels/', { method: 'POST', body: formData });
            if (res.ok) {
                e.target.reset();
                showToast('TC Barrel registered.');
                window.location.href = '/inventory?inv=platforms&platform=tc';
            } else {
                _setBusy(tcBarrelForm, false);
                showToast('Failed to register TC Barrel.', 'error');
            }
        } catch (err) { _setBusy(tcBarrelForm, false); showToast('Error saving TC Barrel.', 'error'); }
    });
}

async function toggleScopeAddMount() {
    const sel = document.getElementById('scope-add-installed');
    const mountSel = document.getElementById('scope-add-mount-select');
    if (!sel || !mountSel) return;

    if (sel.value === 'yes') {
        mountSel.classList.remove('hidden');
        if (mountSel.options.length <= 1) {
            // Lazy-load available mounts (no scope yet, so no for_scope_id filter needed)
            try {
                const res = await fetch('/available-mounts/');
                const data = res.ok ? await res.json() : { firearms: [], tc_barrels: [] };
                let opts = `<option value="">-- Select Platform --</option>`;
                if (data.firearms.length > 0) {
                    opts += `<optgroup label="── Rifles ──">` +
                        data.firearms.map(f => `<option value="firearm:${f.id}">${f.label}</option>`).join('') +
                        `</optgroup>`;
                }
                if (data.tc_barrels.length > 0) {
                    opts += `<optgroup label="── TC Barrels ──">` +
                        data.tc_barrels.map(b => `<option value="barrel:${b.id}">${b.label}</option>`).join('') +
                        `</optgroup>`;
                }
                mountSel.innerHTML = opts;
            } catch(_) {}
        }
    } else {
        mountSel.classList.add('hidden');
    }
}

const addScopeForm = document.getElementById('add-scope-form');
if (addScopeForm) {
    addScopeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(addScopeForm, true);
        const formData = new FormData(e.target);
        const installedSel = document.getElementById('scope-add-installed');
        const mountSel     = document.getElementById('scope-add-mount-select');

        try {
            const res = await fetch('/scopes/', { method: 'POST', body: formData });
            if (!res.ok) { _setBusy(addScopeForm, false); showToast('Failed to register scope.', 'error'); return; }
            const scope = await res.json();
            await Promise.all([
                saveLookupValue('scope_brand', formData.get('brand')),
                saveLookupValue('scope_model', formData.get('model')),
            ]);

            // Mount immediately if the user chose a platform
            if (installedSel?.value === 'yes' && mountSel?.value) {
                const [type, id] = mountSel.value.split(':');
                await fetch(`/scopes/${scope.id}/mount`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mount_type: type, mount_id: parseInt(id) })
                });
            }

            e.target.reset();
            // Reset the mount UI
            if (installedSel) installedSel.value = 'no';
            if (mountSel) { mountSel.innerHTML = '<option value="">Loading platforms…</option>'; mountSel.classList.add('hidden'); }

            showToast('Scope registered.');
            window.location.href = '/inventory?inv=optics';
        } catch (err) { _setBusy(addScopeForm, false); showToast('Error saving scope.', 'error'); }
    });
}

// ── Add Inventory: switchFormCategory + Components ────────────────────────────

function switchAddComponent(formId) {
    document.querySelectorAll('.add-component-form').forEach(f => f.classList.add('hidden'));
    const formMap = { 'add-powder': 'powder-form', 'add-primer': 'primer-form', 'add-bullet-comp': 'bullet-comp-form', 'add-casing': 'casing-form' };
    document.getElementById(formMap[formId])?.classList.remove('hidden');
    const btnMap = { 'add-powder': 'btn-add-powder', 'add-primer': 'btn-add-primer', 'add-bullet-comp': 'btn-add-bullet-comp', 'add-casing': 'btn-add-casing' };
    Object.entries(btnMap).forEach(([key, btnId]) => {
        const btn = document.getElementById(btnId);
        if (!btn) return;
        btn.className = key === formId
            ? "px-3 py-1.5 text-xs font-bold rounded bg-emerald-600 text-white cursor-pointer"
            : "px-3 py-1.5 text-xs font-bold rounded text-gray-200 hover:text-white cursor-pointer";
    });
}

function toggleDeductSection() {
    const section = document.getElementById('deduct-section');
    const icon = document.getElementById('deduct-toggle-icon');
    const isHidden = section.classList.contains('hidden');
    section.classList.toggle('hidden');
    icon.textContent = isHidden ? '▼' : '▶';
    if (isHidden) loadDeductionDropdowns();
}

async function loadDeductionDropdowns() {
    const [powders, primers, bullets, casings] = await Promise.all([
        fetch('/components/powders/').then(r => r.ok ? r.json() : []),
        fetch('/components/primers/').then(r => r.ok ? r.json() : []),
        fetch('/components/bullets/').then(r => r.ok ? r.json() : []),
        fetch('/components/casings/').then(r => r.ok ? r.json() : []),
    ]);

    const pSel = document.getElementById('deduct-powder-select');
    const prSel = document.getElementById('deduct-primer-select');
    const bSel = document.getElementById('deduct-bullet-select');
    const cSel = document.getElementById('deduct-casing-select');

    if (pSel) {
        pSel.innerHTML = '<option value="">— Skip powder deduction —</option>' +
            powders.map(p => `<option value="${p.id}">${p.brand} ${p.name} (${p.weight_lbs}${p.pellet_mode ? ' qty' : ' lbs'})</option>`).join('');
    }
    if (prSel) {
        prSel.innerHTML = '<option value="">— Skip primer deduction —</option>' +
            primers.map(p => `<option value="${p.id}">${p.brand} ${p.primer_type} (${p.quantity} ct)</option>`).join('');
    }
    if (bSel) {
        bSel.innerHTML = '<option value="">— Skip bullet deduction —</option>' +
            bullets.map(b => `<option value="${b.id}">${b.brand} ${b.caliber} ${b.weight_gr}gr (${b.quantity} ct)</option>`).join('');
    }
    if (cSel) {
        cSel.innerHTML = '<option value="">— Skip casing deduction —</option>' +
            casings.map(c => `<option value="${c.id}">${c.brand} ${c.caliber} ${c.condition_label} (${c.quantity} ct)</option>`).join('');
    }
}

const powderForm = document.getElementById('powder-form');
if (powderForm) {
    powderForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(powderForm, true);
        const isPelletMode = document.getElementById('pw-pellet-mode-hidden')?.value === 'true';
        if (isPelletMode) {
            const directQty = parseInt(document.getElementById('pw-direct-weight')?.value || '0', 10);
            document.getElementById('pw-weight-lbs-hidden').value = directQty;
        } else {
            const containerSize = parseFloat(document.getElementById('pw-container-size')?.value || '1');
            const containerCount = parseFloat(document.getElementById('pw-container-count')?.value || '0');
            document.getElementById('pw-weight-lbs-hidden').value = (containerSize * containerCount).toFixed(2);
        }
        const fd = new FormData(e.target);
        const { f1, f2 } = _getPWFiles('pw-powder');
        if (f1) fd.set('image_1', f1, f1.name);
        if (f2) fd.set('image_2', f2, f2.name);
        if (_lastScannedUpc) { fd.set('upc', _lastScannedUpc); _lastScannedUpc = null; }
        try {
            const res = await fetch('/components/powders/', { method: 'POST', body: fd });
            if (res.ok) {
                await Promise.all([saveLookupValue('powder_brand', fd.get('brand')), saveLookupValue('powder_name', fd.get('name'))]);
                e.target.reset(); _resetPW('pw-powder'); showToast('Powder logged.'); window.location.href = '/inventory?inv=components&comp=powders';
            } else { _setBusy(powderForm, false); showToast('Failed to log powder.', 'error'); }
        } catch(_) { _setBusy(powderForm, false); showToast('Error saving powder.', 'error'); }
    });
}

const primerForm = document.getElementById('primer-form');
if (primerForm) {
    primerForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(primerForm, true);
        const fd = new FormData(e.target);
        const { f1, f2 } = _getPWFiles('pw-primer');
        if (f1) fd.set('image_1', f1, f1.name);
        if (f2) fd.set('image_2', f2, f2.name);
        if (_lastScannedUpc) { fd.set('upc', _lastScannedUpc); _lastScannedUpc = null; }
        try {
            const res = await fetch('/components/primers/', { method: 'POST', body: fd });
            if (res.ok) {
                await saveLookupValue('primer_brand', fd.get('brand'));
                e.target.reset(); _resetPW('pw-primer'); showToast('Primers logged.'); window.location.href = '/inventory?inv=components&comp=primers';
            } else { _setBusy(primerForm, false); showToast('Failed to log primers.', 'error'); }
        } catch(_) { _setBusy(primerForm, false); showToast('Error saving primers.', 'error'); }
    });
}

const bulletCompForm = document.getElementById('bullet-comp-form');
if (bulletCompForm) {
    bulletCompForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(bulletCompForm, true);
        const fd = new FormData(e.target);
        const { f1, f2 } = _getPWFiles('pw-bullet');
        if (f1) fd.set('image_1', f1, f1.name);
        if (f2) fd.set('image_2', f2, f2.name);
        if (_lastScannedUpc) { fd.set('upc', _lastScannedUpc); _lastScannedUpc = null; }
        try {
            const res = await fetch('/components/bullets/', { method: 'POST', body: fd });
            if (res.ok) {
                await Promise.all([
                    saveLookupValue('bullet_brand', fd.get('brand')),
                    saveLookupValue('bullet_product_line', fd.get('product_line')),
                    saveLookupValue('caliber', fd.get('caliber')),
                ]);
                e.target.reset(); _resetPW('pw-bullet'); showToast('Bullets logged.'); window.location.href = '/inventory?inv=components&comp=bullets';
            } else { _setBusy(bulletCompForm, false); showToast('Failed to log bullets.', 'error'); }
        } catch(_) { _setBusy(bulletCompForm, false); showToast('Error saving bullets.', 'error'); }
    });
}

const casingForm = document.getElementById('casing-form');
if (casingForm) {
    casingForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        _setBusy(casingForm, true);
        const fd = new FormData(e.target);
        const { f1, f2 } = _getPWFiles('pw-casing');
        if (f1) fd.set('image_1', f1, f1.name);
        if (f2) fd.set('image_2', f2, f2.name);
        if (_lastScannedUpc) { fd.set('upc', _lastScannedUpc); _lastScannedUpc = null; }
        try {
            const res = await fetch('/components/casings/', { method: 'POST', body: fd });
            if (res.ok) {
                await Promise.all([
                    saveLookupValue('casing_brand', fd.get('brand')),
                    saveLookupValue('caliber', fd.get('caliber')),
                ]);
                e.target.reset(); _resetPW('pw-casing'); showToast('Casings logged.'); window.location.href = '/inventory?inv=components&comp=casings';
            } else { _setBusy(casingForm, false); showToast('Failed to log casings.', 'error'); }
        } catch(_) { _setBusy(casingForm, false); showToast('Error saving casings.', 'error'); }
    });
}

async function applyPreferences() {
    try {
        const res = await fetch('/api/preferences/');
        if (!res.ok) return;
        const prefs = await res.json();
        const off = (key) => prefs[key] === 'false';
        const hide = (...ids) => ids.forEach(id => { const el = document.getElementById(id); if (el) el.classList.add('hidden'); });

        if (off('feat_shotguns'))  hide('plat-btn-shotgun', 'btn-add-shotgun');
        if (off('feat_handguns'))  hide('plat-btn-handgun', 'btn-add-handgun');
        if (off('feat_tc'))        hide('plat-btn-tc', 'btn-add-tc-receiver', 'btn-add-tc-barrel');
        if (off('feat_reloading')) hide('inv-btn-components', 'btn-cat-components');
        if (off('feat_ammo_log'))  hide('inv-btn-ammo', 'btn-cat-ammunition', 'nav-btn-measure', 'nav-btn-measure-mobile');
    } catch (_) {}
}

async function loadLandingStats() {
    const el = document.getElementById('landing-stats');
    if (!el) return;
    try {
        const [firearms, scopes, ammo, powders, primers, bullets, casings] = await Promise.all([
            fetch('/catalog/').then(r => r.json()),
            fetch('/scopes/').then(r => r.json()),
            fetch('/ammo/').then(r => r.json()),
            fetch('/components/powders/').then(r => r.json()),
            fetch('/components/primers/').then(r => r.json()),
            fetch('/components/bullets/').then(r => r.json()),
            fetch('/components/casings/').then(r => r.json()),
        ]);
        const sumPrice = arr => arr.reduce((t, x) => t + (parseFloat(x.price_paid) || 0), 0);
        const stats = [
            { icon: '🔫', value: firearms.length, spent: sumPrice(firearms), label: 'Firearms' },
            { icon: '🔭', value: scopes.length,   spent: sumPrice(scopes),   label: 'Optics' },
            { icon: '🧪', value: ammo.length,      spent: sumPrice(ammo),     label: 'Ammo' },
            { icon: '🔩', value: powders.length + primers.length + bullets.length + casings.length, spent: sumPrice(powders) + sumPrice(primers) + sumPrice(bullets) + sumPrice(casings), label: 'Components' },
        ];
        el.innerHTML = stats.map(s => `
            <div class="bg-gray-800/50 rounded-lg py-2.5 text-center">
                <div class="text-base">${s.icon}</div>
                <div class="text-sm font-black text-white">${s.value}</div>
                <div class="text-[9px] text-gray-500 uppercase tracking-wide">${s.label}</div>
                <div class="text-[10px] font-bold text-emerald-500 mt-0.5">$${s.spent.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</div>
            </div>`).join('');
    } catch (_) {}
}

// ── Barcode Scanner ────────────────────────────────────────────────────────────

let _barcodeFormTarget = null;
let _lastScannedUpc = null;
let _barcodeReader = null;
let _barcodeStream = null;
let _barcodeAnimFrame = null;

function openBarcodeScanner(formTarget) {
    _barcodeFormTarget = formTarget;
    document.getElementById('barcode-modal').classList.remove('hidden');
    document.getElementById('barcode-status').textContent = '';

    const isSecure = location.protocol === 'https:' ||
                     location.hostname === 'localhost' ||
                     location.hostname === '127.0.0.1';

    document.getElementById('barcode-video-wrap').classList.remove('hidden');
    document.getElementById('barcode-subtitle').textContent = 'Point camera at barcode — detected automatically';
    _startLiveScanner();
}

async function _startLiveScanner() {
    const video = document.getElementById('barcode-video');
    const status = document.getElementById('barcode-status');

    let permState = 'prompt';
    try {
        const ps = await navigator.permissions.query({ name: 'camera' });
        permState = ps.state;
        ps.onchange = () => {
            if (ps.state === 'granted') { status.textContent = ''; _startLiveScanner(); }
        };
    } catch (_) {}

    if (permState === 'denied') {
        document.getElementById('barcode-video-wrap').classList.add('hidden');
        status.innerHTML = '🔒 Camera access is blocked.<br>Open <strong>Chrome</strong> → ⋮ menu → Settings → Site settings → Camera → find this site → Allow. Then tap: <button onclick="_startLiveScanner()" style="background:#d97706;color:#fff;border:none;padding:4px 12px;border-radius:5px;font-size:11px;font-weight:bold;cursor:pointer;">Retry</button>';
        return;
    }

    status.textContent = permState === 'prompt' ? 'Allow camera access when prompted…' : 'Starting camera…';
    try {
        _barcodeStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1920 }, height: { ideal: 1080 } }
        });
        video.srcObject = _barcodeStream;
        await video.play();
        status.textContent = 'Camera active — point at barcode';

        // Prefer native BarcodeDetector (Android Chrome) — more reliable than ZXing
        if ('BarcodeDetector' in window) {
            const detector = new BarcodeDetector({
                formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39']
            });
            // Wait for camera to focus before scanning
            await new Promise(r => setTimeout(r, 600));
            status.textContent = 'Ready — point at barcode';
            let _lastCode = null, _hits = 0;
            const REQUIRED = 3;
            const scanFrame = async () => {
                if (!_barcodeStream) return;
                try {
                    const barcodes = await detector.detect(video);
                    if (barcodes.length > 0) {
                        const code = barcodes[0].rawValue;
                        if (code === _lastCode) {
                            _hits++;
                            status.textContent = `Confirming: ${code} (${_hits}/${REQUIRED})`;
                            if (_hits >= REQUIRED) {
                                status.textContent = `✓ ${code}`;
                                closeBarcodeScanner();
                                triggerBarcodeLookup(code);
                                return;
                            }
                        } else {
                            _lastCode = code;
                            _hits = 1;
                            status.textContent = `Detected: ${code}`;
                        }
                    } else {
                        if (_lastCode) { status.textContent = 'Ready — point at barcode'; }
                        _lastCode = null;
                        _hits = 0;
                    }
                } catch (_) {}
                _barcodeAnimFrame = requestAnimationFrame(scanFrame);
            };
            _barcodeAnimFrame = requestAnimationFrame(scanFrame);
            return;
        }

        // ZXing fallback (desktop / older browsers)
        if (typeof ZXing === 'undefined') { status.textContent = 'Scanner ready — enter barcode manually if needed'; return; }
        const hints = new Map();
        hints.set(ZXing.DecodeHintType.POSSIBLE_FORMATS, [
            ZXing.BarcodeFormat.EAN_13, ZXing.BarcodeFormat.EAN_8,
            ZXing.BarcodeFormat.UPC_A, ZXing.BarcodeFormat.UPC_E,
            ZXing.BarcodeFormat.CODE_128,
        ]);
        _barcodeReader = new ZXing.BrowserMultiFormatReader(hints);
        let _zxingLastCode = null, _zxingHits = 0;
        const cb = (result) => {
            if (!result) return;
            const code = result.getText();
            if (code === _zxingLastCode) {
                _zxingHits++;
                if (_zxingHits >= 2) { _barcodeReader.reset(); closeBarcodeScanner(); triggerBarcodeLookup(code); }
            } else {
                _zxingLastCode = code;
                _zxingHits = 1;
            }
        };
        if (typeof _barcodeReader.decodeFromVideoElementContinuously === 'function') {
            _barcodeReader.decodeFromVideoElementContinuously(video, cb);
        } else {
            _barcodeReader.decodeFromVideoElement(video, cb);
        }
    } catch (e) {
        document.getElementById('barcode-video-wrap').classList.add('hidden');
        if (e.name === 'NotAllowedError') {
            status.innerHTML = '🔒 Camera access denied.<br>Open <strong>Chrome</strong> → ⋮ menu → Settings → Site settings → Camera → find this site → Allow. Then tap: <button onclick="_startLiveScanner()" style="background:#d97706;color:#fff;border:none;padding:4px 12px;border-radius:5px;font-size:11px;font-weight:bold;cursor:pointer;">Retry</button>';
        } else {
            status.textContent = 'Camera unavailable — enter barcode manually below.';
        }
    }
}

function closeBarcodeScanner() {
    document.getElementById('barcode-modal').classList.add('hidden');
    document.getElementById('barcode-video-wrap').classList.add('hidden');
    if (_barcodeAnimFrame) { cancelAnimationFrame(_barcodeAnimFrame); _barcodeAnimFrame = null; }
    if (_barcodeReader) { try { _barcodeReader.reset(); } catch (_) {} _barcodeReader = null; }
    if (_barcodeStream) { _barcodeStream.getTracks().forEach(t => t.stop()); _barcodeStream = null; }
    document.getElementById('barcode-manual-input').value = '';
    document.getElementById('barcode-status').textContent = '';
    // Blur active element so focus doesn't return to a form field and trigger autocomplete
    document.activeElement?.blur();
}

async function _addServerImageToWidget(wid, serverPath) {
    try {
        const existing = (_pw[wid]?.files) || [];
        if (existing.length > 0) return; // don't override photos already selected
        const resp = await fetch(serverPath);
        const blob = await resp.blob();
        const file = new File([blob], 'product-image.jpg', { type: 'image/jpeg' });
        _pw[wid] = { files: [file], primary: 0 };
        _renderPW(wid);
    } catch {}
}

function openOnlineImageSearch() {
    const brand   = document.getElementById('ammo-factory-brand')?.value || '';
    const caliber = document.getElementById('ammo-factory-caliber')?.value || '';
    const model   = document.getElementById('ammo-factory-model')?.value || '';
    const query   = [brand, caliber, model, 'ammunition'].filter(Boolean).join(' ').trim();
    if (!query) { showToast('Fill in brand or caliber first', 'info'); return; }
    const panel = document.getElementById('ammo-factory-online-search');
    if (!panel) return;
    const wasHidden = panel.classList.contains('hidden');
    panel.classList.toggle('hidden');
    if (wasHidden) searchOnlineImages(query, 'pw-ammo-factory');
}

async function searchOnlineImages(query, wid) {
    const grid = document.getElementById('ammo-factory-online-grid');
    if (!grid) return;
    grid.innerHTML = '<p class="text-gray-400 text-xs col-span-4 py-2 text-center">Searching…</p>';
    try {
        const resp = await fetch(`/barcode/image-search?q=${encodeURIComponent(query)}`);
        const data = await resp.json();
        if (!data.images || !data.images.length) {
            grid.innerHTML = '<p class="text-gray-500 text-xs col-span-4 py-2 text-center">No images found.</p>';
            return;
        }
        grid.innerHTML = data.images.map(img => `
            <div onclick="selectOnlineImage('${escHtml(img.url)}','${wid}')"
                 class="cursor-pointer rounded overflow-hidden border border-gray-700 hover:border-amber-500 transition bg-gray-950">
                <img src="${escHtml(img.thumb || img.url)}" class="w-full h-16 object-contain"
                     onerror="this.closest('div').remove()" title="${escHtml(img.title || '')}">
            </div>`).join('');
    } catch {
        grid.innerHTML = '<p class="text-red-400 text-xs col-span-4 py-2 text-center">Search failed.</p>';
    }
}

async function selectOnlineImage(url, wid) {
    showToast('Downloading image…', 'info');
    try {
        const resp = await fetch('/barcode/fetch-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        if (!resp.ok) { showToast('Failed to fetch image', 'error'); return; }
        const { path } = await resp.json();
        const imgResp = await fetch(path);
        const blob = await imgResp.blob();
        const file = new File([blob], 'web-image.jpg', { type: 'image/jpeg' });
        const existing = (_pw[wid]?.files) || [];
        _pw[wid] = { files: [...existing, file].slice(0, 2), primary: _pw[wid]?.primary || 0 };
        _renderPW(wid);
        document.getElementById('ammo-factory-online-search')?.classList.add('hidden');
        showToast('Image added', 'success');
    } catch { showToast('Failed to fetch image', 'error'); }
}

function _showPendingUpc(upc) {
    const row = document.getElementById('ammo-factory-upc-row');
    const disp = document.getElementById('ammo-factory-upc-display');
    if (row && disp) { disp.value = upc || ''; row.classList.toggle('hidden', !upc); }
}

async function lookupFormUpc(formTarget, inputId) {
    const input = document.getElementById(inputId);
    const upc = (input?.value || '').trim();
    if (!upc) { showToast('Enter a UPC to look up', 'info'); return; }
    _barcodeFormTarget = formTarget;
    const btn = input?.nextElementSibling;
    if (btn) { btn._origText = btn.textContent; btn.disabled = true; btn.textContent = '⏳'; btn.style.opacity = '0.6'; }
    await triggerBarcodeLookup(upc);
    if (btn) { btn.disabled = false; btn.textContent = btn._origText; btn.style.opacity = ''; }
}

async function triggerBarcodeLookup(upc) {
    upc = (upc || '').trim();
    if (!upc) return;
    const status = document.getElementById('barcode-status');
    if (status) status.textContent = 'Looking up barcode…';
    // Populate the form's UPC input so user can see/re-trigger lookup
    if (_barcodeFormTarget) {
        const el = document.getElementById(`${_barcodeFormTarget}-upc-input`);
        if (el) el.value = upc;
    }
    try {
        const resp = await fetch(`/barcode/lookup?upc=${encodeURIComponent(upc)}`);
        if (!resp.ok) {
            _lastScannedUpc = upc;
            closeBarcodeScanner();
            if (_barcodeFormTarget === 'ammo-factory') _showPendingUpc(upc);
            const errBody = await resp.json().catch(() => ({}));
            const offline = (errBody.detail || '').includes('unavailable');
            showToast(
                offline ? 'Lookup service offline — fill in details manually' : 'UPC not found — fill in the details and save to register it',
                'info'
            );
            return;
        }
        const data = await resp.json();
        // If scanning into the add-ammo form and UPC already exists in inventory, go straight to detail
        if (_barcodeFormTarget === 'ammo-factory' && data.existing_ammo_id) {
            closeBarcodeScanner();
            window.location.href = `/ammo-detail.html?id=${data.existing_ammo_id}`;
            return;
        }
        _fillFormFromBarcode(data);
        // Sync the "Scanned UPC" display with the canonical UPC from the response
        if (_barcodeFormTarget === 'ammo-factory') _showPendingUpc(data.upc || upc);
        // Summarize from the parsed/trusted fields that actually populate the form —
        // data.title is raw external listing text and can be mislabeled for the UPC.
        showToast(`Found: ${_summarizeBarcodeData(data) || upc}`, 'success');
    } catch (e) {
        showToast('Lookup failed — check connection', 'error');
    } finally {
        closeBarcodeScanner();
    }
}

// Builds a toast summary from the parsed/trusted fields (the ones that actually land
// in the form), not the raw external title — UPC databases frequently mislabel titles.
function _summarizeBarcodeData(data) {
    const parts = [];
    if (data.brand) parts.push(data.brand);
    const line = data.product_line || data.bullet_type || data.powder_name || data.primer_model;
    if (line) parts.push(line);
    if (data.caliber) parts.push(data.caliber);
    if (data.weight_gr) parts.push(`${data.weight_gr}gr`);
    if (data.rounds_per_box) parts.push(`${data.rounds_per_box}ct`);
    return parts.length ? parts.join(' ') : (data.title || null);
}

// Maps product_type → { category, form } for auto-navigation
const _PRODUCT_TYPE_FORM = {
    'ammo':   { cat: 'cat-ammunition', form: null, fill: 'ammo-factory' },
    'bullet': { cat: 'cat-components', form: 'add-bullet-comp', fill: 'bullet-comp' },
    'powder': { cat: 'cat-components', form: 'add-powder',      fill: 'powder' },
    'primer': { cat: 'cat-components', form: 'add-primer',      fill: 'primer' },
    'casing': { cat: 'cat-components', form: 'add-casing',      fill: 'casing' },
};

function _fillFormFromBarcode(data) {
    _lastScannedUpc = data.upc || null;

    if (_barcodeFormTarget === 'ammo-factory') {
        if (data.image_path) _addServerImageToWidget('pw-ammo-factory', data.image_path);
        // Set category first so field visibility is toggled before filling values
        if (data.ammo_category) {
            const catSel = document.getElementById('ammo-factory-cat');
            if (catSel && !catSel.value) { catSel.value = data.ammo_category; _toggleFactoryAmmoFields(data.ammo_category); }
        }
        _setIfEmpty('ammo-factory-brand', data.brand);
        _setIfEmpty('ammo-factory-model', data.product_line || data.bullet_type);
        _setIfEmpty('ammo-factory-caliber', data.caliber);
        _setIfEmpty('ammo-factory-bullet-type', data.bullet_type);
        _setIfEmpty('ammo-factory-weight', data.weight_gr);
        _setIfEmpty('ammo-factory-bc', data.bc_g1);
        _setIfEmpty('ammo-factory-rpb', data.rounds_per_box);
    } else if (_barcodeFormTarget === 'bullet-comp') {
        _setIfEmpty('bullet-comp-brand', data.brand);
        _setIfEmpty('bullet-comp-product-line', data.product_line);
        _setIfEmpty('bullet-comp-caliber', data.caliber);
        _setIfEmpty('bullet-comp-weight', data.weight_gr);
        _setIfEmpty('bullet-comp-bullet-type', data.bullet_type);
        _setIfEmpty('bullet-comp-bc-g1', data.bc_g1);
        _setIfEmpty('bullet-comp-bc-g7', data.bc_g7);
    } else if (_barcodeFormTarget === 'powder') {
        _setIfEmpty('powder-brand', data.brand);
        _setIfEmpty('powder-name', data.powder_name);
    } else if (_barcodeFormTarget === 'primer') {
        _setIfEmpty('primer-brand', data.brand);
        _setIfEmpty('primer-model', data.primer_model);
        if (data.primer_type) {
            const sel = document.getElementById('primer-type');
            if (sel && !sel.value) {
                for (const opt of sel.options) {
                    if (opt.text === data.primer_type) { sel.value = opt.value; break; }
                }
            }
        }
    } else if (_barcodeFormTarget === 'casing') {
        _setIfEmpty('casing-brand', data.brand);
        _setIfEmpty('casing-caliber', data.caliber);
        _setIfEmpty('casing-quantity', data.rounds_per_box);
    }
    // Close any open autocomplete dropdown after programmatic fill
    if (_acDropdown) { _acDropdown.classList.add('hidden'); _acDropdown = null; }
}

function _setIfEmpty(id, value) {
    if (value === null || value === undefined) return;
    const el = document.getElementById(id);
    if (el && !el.value) el.value = value;
}

// ── Ladder Test ──────────────────────────────────────────────────────────────

let _ladderBullets = [];
let _ladderCasings = [];
let _ladderPlatforms = [];
let _ladderGuns = [];
let _ladderTcBarrels = [];
let _currentLadderTest = null;

async function populateLadderPlatformSelect() {
    const sel = document.getElementById('lt-platform');
    if (!sel) return;
    try {
        const [gunsRes, tcRes, platformsRes] = await Promise.all([
            fetch('/catalog/', { cache: 'no-store' }),
            fetch('/tc-barrels/', { cache: 'no-store' }),
            fetch('/test-platforms/', { cache: 'no-store' }),
        ]);
        _ladderGuns = gunsRes.ok ? await gunsRes.json() : [];
        _ladderTcBarrels = tcRes.ok ? await tcRes.json() : [];
        _ladderPlatforms = platformsRes.ok ? await platformsRes.json() : [];
        renderLadderPlatformOptions();
    } catch (err) { console.error('populateLadderPlatformSelect error:', err); }
}

// Rebuilds the platform <select> from the cached gun/TC-barrel/test-platform lists, filtered
// by the currently selected caliber. Called on initial load and again whenever lt-caliber
// changes — no re-fetch needed, just a re-render against cached data.
function renderLadderPlatformOptions() {
    const sel = document.getElementById('lt-platform');
    if (!sel) return;
    const cal = document.getElementById('lt-caliber')?.value || null;
    const prevValue = sel.value;

    let html = _buildGunOptionsHTML(_ladderGuns, _ladderTcBarrels, '— No specific platform —', cal);

    let platforms = _ladderPlatforms;
    if (cal) {
        const filtered = _ladderPlatforms.filter(p => _calibersMatch(p.caliber, cal));
        if (filtered.length) platforms = filtered;
    }
    if (platforms.length) {
        html += `<optgroup label="── Test Platforms (not in inventory) ──">` +
            platforms.map(p => `<option value="platform:${p.id}">${escHtml(p.name)}${p.caliber ? ' — ' + escHtml(p.caliber) : ''}</option>`).join('') +
            `</optgroup>`;
    }
    html += `<option value="__new__">+ Add New Test Platform…</option>`;
    sel.innerHTML = html;

    if (Array.from(sel.options).some(o => o.value === prevValue)) sel.value = prevValue;
}

function onLadderPlatformChange() {
    const sel = document.getElementById('lt-platform');
    const form = document.getElementById('lt-platform-new-form');
    if (!sel || !form) return;
    if (sel.value === '__new__') {
        form.classList.remove('hidden');
        const nameEl = document.getElementById('ltp-name');
        if (nameEl) nameEl.focus();
    } else {
        form.classList.add('hidden');
    }
}

function cancelNewLadderPlatform() {
    const form = document.getElementById('lt-platform-new-form');
    if (form) form.classList.add('hidden');
    ['ltp-name', 'ltp-barrel-length', 'ltp-barrel-twist'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    const sel = document.getElementById('lt-platform');
    if (sel && sel.value === '__new__') sel.value = '';
}

async function saveNewLadderPlatform() {
    const name = document.getElementById('ltp-name')?.value.trim();
    if (!name) { showToast('Enter a name for the test platform', 'error'); return; }
    const caliber = document.getElementById('lt-caliber')?.value || null;
    const barrelLength = document.getElementById('ltp-barrel-length')?.value.trim() || null;
    const barrelTwist = document.getElementById('ltp-barrel-twist')?.value.trim() || null;
    try {
        const res = await fetch('/test-platforms/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, caliber, barrel_length: barrelLength, barrel_twist: barrelTwist }),
        });
        if (!res.ok) { showToast('Failed to save test platform', 'error'); return; }
        const platform = await res.json();
        await populateLadderPlatformSelect();
        const sel = document.getElementById('lt-platform');
        if (sel) sel.value = `platform:${platform.id}`;
        cancelNewLadderPlatform();
        showToast('Test platform saved', 'success');
    } catch (err) { showToast('Failed to save test platform', 'error'); }
}

function showLadderListView() {
    document.getElementById('ladder-list-view')?.classList.remove('hidden');
    document.getElementById('ladder-create-view')?.classList.add('hidden');
    document.getElementById('ladder-detail-view')?.classList.add('hidden');
    document.getElementById('ladder-back-btn')?.classList.add('hidden');
    loadLadderTests();
}

function showLadderCreateForm() {
    document.getElementById('ladder-list-view')?.classList.add('hidden');
    document.getElementById('ladder-create-view')?.classList.remove('hidden');
    document.getElementById('ladder-detail-view')?.classList.add('hidden');
    document.getElementById('ladder-back-btn')?.classList.remove('hidden');
    ['lt-name', 'lt-coal', 'lt-notes', 'lt-charge-start', 'lt-charge-end', 'lt-charge-increment'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    // Defaults to the common case (one round per charge) so it's rarely something you have to
    // think about — still editable for the rare group-testing ladder that loads more per step.
    const roundsEl = document.getElementById('lt-rounds-per-step');
    if (roundsEl) roundsEl.value = '1';
    cancelNewLadderPlatform();
    populateLadderDropdowns();
    populateLadderPlatformSelect();
    updateLadderChargePreview();
}

// Mirrors _generate_charge_weights in routers/ladder.py exactly, so the count shown here always
// matches what the server will actually create.
function _computeLadderStepCount(start, end, increment) {
    let count = 0;
    let c = start;
    while (c <= end + 1e-6) {
        count++;
        c += increment;
    }
    return count;
}

// Live feedback tying the charge range to the rounds/step multiplier, so it's never silently
// unclear how many steps — and how many total rounds/components — a range will produce.
function updateLadderChargePreview() {
    const el = document.getElementById('lt-charge-preview');
    if (!el) return;
    const start = parseFloat(document.getElementById('lt-charge-start')?.value);
    const end = parseFloat(document.getElementById('lt-charge-end')?.value);
    const increment = parseFloat(document.getElementById('lt-charge-increment')?.value);
    const roundsPerStep = parseInt(document.getElementById('lt-rounds-per-step')?.value, 10);

    if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(increment)) {
        el.textContent = '';
        return;
    }
    if (increment <= 0) { el.textContent = '⚠ Increment must be greater than 0.'; return; }
    if (end < start) { el.textContent = '⚠ End charge must be ≥ start charge.'; return; }

    const stepCount = _computeLadderStepCount(start, end, increment);
    if (stepCount > 50) {
        el.textContent = `⚠ That range/increment produces ${stepCount} steps — widen the increment (max 50).`;
        return;
    }
    let text = `→ ${stepCount} step${stepCount === 1 ? '' : 's'} (${start}–${end}gr, every ${increment}gr)`;
    if (Number.isFinite(roundsPerStep) && roundsPerStep > 0) {
        text += ` × ${roundsPerStep} round${roundsPerStep === 1 ? '' : 's'}/step = ${stepCount * roundsPerStep} total rounds deducted on create.`;
    } else {
        text += ' — enter Rounds/Step (required) to see total rounds deducted.';
    }
    el.textContent = text;
}

function showLadderDetailView() {
    document.getElementById('ladder-list-view')?.classList.add('hidden');
    document.getElementById('ladder-create-view')?.classList.add('hidden');
    document.getElementById('ladder-detail-view')?.classList.remove('hidden');
    document.getElementById('ladder-back-btn')?.classList.remove('hidden');
}

async function populateLadderDropdowns() {
    try {
        const [powderRes, primerRes, bulletRes, casingRes] = await Promise.all([
            fetch('/components/powders/', { cache: 'no-store' }),
            fetch('/components/primers/', { cache: 'no-store' }),
            fetch('/components/bullets/', { cache: 'no-store' }),
            fetch('/components/casings/', { cache: 'no-store' }),
        ]);
        const powders = powderRes.ok ? await powderRes.json() : [];
        const primers = primerRes.ok ? await primerRes.json() : [];
        const bullets = bulletRes.ok ? await bulletRes.json() : [];
        const casings = casingRes.ok ? await casingRes.json() : [];
        _ladderBullets = bullets;
        _ladderCasings = casings;

        const calSel = document.getElementById('lt-caliber');
        if (calSel) {
            const calibers = [...new Set(casings.map(c => c.caliber).filter(Boolean))].sort();
            calSel.innerHTML = `<option value="">— Select caliber —</option>` +
                calibers.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join('');
        }

        const powSel = document.getElementById('lt-powder');
        if (powSel) {
            powSel.innerHTML = `<option value="">— Select powder —</option>` +
                powders.filter(p => !p.is_muzzleloader).map(p => {
                    const label = `${p.brand} ${p.name}`.trim();
                    const qty = `${parseFloat(p.weight_lbs || 0).toFixed(1)} lbs`;
                    return `<option value="${escHtml(label)}" data-id="${p.id}">${escHtml(label)} (${qty})</option>`;
                }).join('');
        }

        const priSel = document.getElementById('lt-primer');
        if (priSel) {
            priSel.innerHTML = `<option value="">— Select primer (optional) —</option>` +
                primers.filter(p => !p.is_muzzleloader).map(p => {
                    const label = `${p.brand} ${p.model || ''}`.trim();
                    return `<option value="${escHtml(label)}" data-id="${p.id}">${escHtml(label)} (${(p.quantity || 0).toLocaleString()} ct)</option>`;
                }).join('');
        }

        const bulSel = document.getElementById('lt-bullet');
        if (bulSel) bulSel.innerHTML = _buildBulletOptionsHTML(bullets, calSel ? calSel.value : null);
        const casSel = document.getElementById('lt-casing');
        if (casSel) casSel.innerHTML = _buildCasingOptionsHTML(casings, calSel ? calSel.value : null);
    } catch (err) { console.error('populateLadderDropdowns error:', err); }
}

async function loadLadderTests() {
    const container = document.getElementById('ladder-test-list');
    if (!container) return;
    try {
        const res = await fetch('/ladder-tests/', { cache: 'no-store' });
        const tests = res.ok ? await res.json() : [];
        if (!tests.length) {
            container.innerHTML = `<p class="text-xs text-gray-500 italic">No ladder tests yet — start one above.</p>`;
            return;
        }
        container.innerHTML = tests.map(t => `
            <div onclick="openLadderTest(${t.id})" class="bg-gray-800 p-4 rounded-lg border border-gray-700 hover:border-purple-500/50 shadow-xl cursor-pointer transition">
                <div class="flex justify-between items-start gap-2">
                    <h4 class="text-sm font-bold text-white">${escHtml(t.name)}</h4>
                    ${t.has_winner ? '<span class="text-[10px] bg-amber-900/60 text-amber-400 px-1.5 py-0.5 rounded font-bold shrink-0">★ WINNER SET</span>' : ''}
                </div>
                <p class="text-xs text-gray-400 mt-1">${escHtml(t.bullet_label)} · ${escHtml(t.powder_name)}</p>
                <p class="text-[11px] text-gray-500 mt-1">${t.step_count} step${t.step_count === 1 ? '' : 's'}${t.charge_min !== null ? ` · ${t.charge_min}–${t.charge_max}gr` : ''}${t.platform_label ? ` · 🔫 ${escHtml(t.platform_label)}` : ''}</p>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<p class="text-xs text-red-400 italic">Failed to load ladder tests.</p>`;
    }
}

async function resolveLadderPlatformSelection() {
    const sel = document.getElementById('lt-platform');
    if (!sel || !sel.value || sel.value === '__new__') return { barrel_id: null, platform_id: null };
    if (sel.value.startsWith('platform:')) {
        return { barrel_id: null, platform_id: parseInt(sel.value.split(':')[1]) };
    }
    const barrelId = await resolveBarrelIdFromGunSelect(sel);
    return { barrel_id: barrelId, platform_id: null };
}

async function submitNewLadderTest() {
    const name = document.getElementById('lt-name')?.value.trim();
    const caliber = document.getElementById('lt-caliber')?.value;
    const bulSel = document.getElementById('lt-bullet');
    const bulletId = bulSel?.selectedOptions[0]?.dataset.id;
    const powSel = document.getElementById('lt-powder');
    const powder = powSel?.value;
    const powderInvId = powSel?.selectedOptions[0]?.dataset.id;
    const priSel = document.getElementById('lt-primer');
    const primer = priSel?.value;
    const primerInvId = priSel?.selectedOptions[0]?.dataset.id;
    const casSel = document.getElementById('lt-casing');
    const casing = casSel?.value;
    const casingInvId = casSel?.selectedOptions[0]?.dataset.id;
    const coal = document.getElementById('lt-coal')?.value;
    const notes = document.getElementById('lt-notes')?.value;
    const chargeStart = document.getElementById('lt-charge-start')?.value;
    const chargeEnd = document.getElementById('lt-charge-end')?.value;
    const chargeIncrement = document.getElementById('lt-charge-increment')?.value;
    const roundsPerStep = document.getElementById('lt-rounds-per-step')?.value;

    if (!name || !caliber || !bulletId || !powder) {
        showToast('Name, caliber, bullet, and powder are required', 'error');
        return;
    }
    // Rounds/Step defaults to "1" (see showLadderCreateForm), so it doesn't count toward
    // "did the user start filling in a range" — only Start/End/Increment do. Otherwise the
    // default value would wrongly block "leave everything blank, add steps manually" too.
    const rangeFieldsFilled = chargeStart || chargeEnd || chargeIncrement;
    if (rangeFieldsFilled && !(chargeStart && chargeEnd && chargeIncrement)) {
        showToast('Fill in start, end, AND increment to auto-generate steps — or leave all three blank', 'error');
        return;
    }
    if (rangeFieldsFilled && !(roundsPerStep && parseInt(roundsPerStep, 10) > 0)) {
        showToast('Rounds/Step is required to auto-generate a charge ladder', 'error');
        return;
    }

    const { barrel_id, platform_id } = await resolveLadderPlatformSelection();

    try {
        const res = await fetch('/ladder-tests/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name, caliber, bullet_id: parseInt(bulletId), powder_name: powder,
                primer: primer || null, case_type: casing || null,
                coal: coal ? parseFloat(coal) : null, notes: notes || null,
                charge_start: chargeStart ? parseFloat(chargeStart) : null,
                charge_end: chargeEnd ? parseFloat(chargeEnd) : null,
                charge_increment: chargeIncrement ? parseFloat(chargeIncrement) : null,
                rounds_per_step: roundsPerStep ? parseInt(roundsPerStep) : null,
                barrel_id, platform_id,
                powder_inv_id: powderInvId ? parseInt(powderInvId) : null,
                primer_inv_id: primerInvId ? parseInt(primerInvId) : null,
                casing_inv_id: casingInvId ? parseInt(casingInvId) : null,
            }),
        });
        if (res.status === 400) {
            const err = await res.json().catch(() => ({}));
            showToast(err.detail || 'Invalid charge range', 'error');
            return;
        }
        if (!res.ok) { showToast('Failed to create ladder test', 'error'); return; }
        _currentLadderTest = await res.json();
        (_currentLadderTest.warnings || []).forEach(w => showToast(w, 'error'));
        showToast('Ladder test created', 'success');
        showLadderDetailView();
        renderLadderDetail();
    } catch (err) { showToast('Failed to create ladder test', 'error'); }
}

async function openLadderTest(id) {
    try {
        const res = await fetch(`/ladder-tests/${id}`, { cache: 'no-store' });
        if (!res.ok) { showToast('Failed to load ladder test', 'error'); return; }
        _currentLadderTest = await res.json();
        showLadderDetailView();
        renderLadderDetail();
    } catch (err) { showToast('Failed to load ladder test', 'error'); }
}

function renderLadderDetail() {
    const t = _currentLadderTest;
    if (!t) return;

    const title = document.getElementById('ladder-detail-title');
    if (title) title.textContent = t.name;

    const recipe = document.getElementById('ladder-detail-recipe');
    if (recipe) {
        const bulletLabel = t.bullet
            ? `${t.bullet.brand} ${t.bullet.product_line || ''} ${t.bullet.weight_gr}gr ${t.bullet.bullet_type || ''}`.replace(/\s+/g, ' ').trim()
            : '—';
        const parts = [t.caliber, bulletLabel, t.powder_name, t.primer, t.case_type].filter(Boolean);
        let line = parts.join(' · ') + (t.coal ? ` · COAL ${t.coal}"` : '');
        if (t.charge_start != null && t.charge_end != null && t.charge_increment != null) {
            line += ` · ${t.charge_start}–${t.charge_end}gr step ${t.charge_increment}gr`;
        }
        if (t.rounds_per_step) line += ` · ${t.rounds_per_step} rounds/step loaded`;
        if (t.platform_label) line += ` · 🔫 ${t.platform_label}`;
        recipe.textContent = line;
    }

    const chartContainer = document.getElementById('ladder-chart');
    if (chartContainer) chartContainer.innerHTML = buildLadderChartSVG(t.steps);

    const suggestBox = document.getElementById('ladder-suggested-nodes');
    if (suggestBox) suggestBox.innerHTML = _renderSuggestedNodesHTML(t.steps);

    const markedBox = document.getElementById('ladder-marked-nodes');
    if (markedBox) markedBox.innerHTML = _renderMarkedNodesHTML(t.steps);

    const rows = document.getElementById('ladder-step-rows');
    if (rows) {
        rows.innerHTML = t.steps.length
            ? t.steps.map(s => `
                <tr class="border-t border-gray-700 ${s.is_winner ? 'bg-amber-900/20' : ''}">
                    <td class="p-2 font-bold text-white">${s.charge_weight}${s.is_winner ? ' ★' : ''}</td>
                    <td class="p-2">
                        <div class="flex items-center gap-1.5">
                            <input type="text" id="step-vel-${s.id}" value="${escHtml(s.velocities || '')}" placeholder="e.g. 2750,2748,2751"
                                   onkeydown="if(event.key==='Enter'){saveLadderStepVelocities(${s.id});}"
                                   class="w-40 bg-gray-700 border border-gray-600 rounded p-1.5 text-xs text-white focus:outline-none focus:border-amber-500">
                            <button onclick="saveLadderStepVelocities(${s.id})" class="text-blue-400 hover:text-blue-300 text-xs cursor-pointer shrink-0" title="Save velocities">💾</button>
                        </div>
                    </td>
                    <td class="p-2 text-right">
                        <button onclick="deleteLadderStep(${s.id})" class="text-gray-500 hover:text-red-400 text-xs cursor-pointer">🗑️</button>
                    </td>
                </tr>
            `).join('')
            : `<tr><td colspan="3" class="p-3 text-center text-xs text-gray-500 italic">No charge steps yet — set a charge range above or add one manually.</td></tr>`;
    }
}

// Steps marked as a node by clicking a dot on the chart — surfaced here since the step table no
// longer has its own star/save column. Each gets a one-click path to load more rounds for it.
function _renderMarkedNodesHTML(steps) {
    const marked = steps.filter(s => s.is_winner);
    if (!marked.length) return '';
    return `
        <div class="bg-gray-800 p-3 rounded-lg border border-amber-700/40 shadow-xl">
            <h4 class="text-xs font-bold text-amber-400 uppercase tracking-wider mb-2">★ Marked Nodes</h4>
            <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
            ${marked.map(s => `
                <div class="bg-gray-900/40 border border-gray-700 rounded-lg p-2.5 flex items-center justify-between gap-2 text-xs text-gray-300">
                    <span><b class="text-white">${s.charge_weight}gr</b>${s.avg_velocity != null ? ` — ${s.avg_velocity} fps` : ''}</span>
                    <div class="flex items-center gap-2 shrink-0">
                        <button onclick="saveWinnerAsHandload(${s.id})" class="bg-emerald-700 hover:bg-emerald-600 text-white px-2.5 py-1 rounded text-[11px] font-bold cursor-pointer">🧪 Create More Bullets</button>
                        <button onclick="toggleLadderWinner(${s.id})" class="text-gray-500 hover:text-red-400 cursor-pointer" title="Unmark">✕</button>
                    </div>
                </div>
            `).join('')}
            </div>
        </div>`;
}

// Combines the raw velocity readings across several steps into one group and computes avg/ES/SD
// over all of them together — mirrors math_engine.calculate_shot_metrics server-side, but a
// ladder node spans several charge steps (each usually just 1 shot), so there's no single step
// to ask the backend for; this treats those shots collectively like a real group.
function _combinedShotMetrics(velocityCsvList) {
    const values = [];
    velocityCsvList.forEach(csv => {
        (csv || '').split(',').forEach(v => {
            const n = parseFloat(v.trim());
            if (!isNaN(n)) values.push(n);
        });
    });
    const n = values.length;
    if (n === 0) return null;
    const avg = values.reduce((a, b) => a + b, 0) / n;
    if (n === 1) return { avg: Math.round(avg * 10) / 10, es: 0, sd: 0, n };
    const es = Math.max(...values) - Math.min(...values);
    const variance = values.reduce((a, v) => a + (v - avg) ** 2, 0) / (n - 1);
    const sd = Math.sqrt(variance);
    return { avg: Math.round(avg * 10) / 10, es: Math.round(es * 10) / 10, sd: Math.round(sd * 10) / 10, n };
}

// Finds candidate "nodes" (flat spots in the velocity curve) by sliding a 3-point window
// across the charge/velocity data and ranking windows by how little velocity varies inside
// them — the classic manual technique reloaders use, automated. Returns up to 2 non-
// overlapping windows so a ladder with two distinct plateaus gets both flagged.
function _suggestLadderNodes(steps) {
    const pts = steps.filter(s => s.avg_velocity != null).slice().sort((a, b) => a.charge_weight - b.charge_weight);
    if (pts.length < 3) return [];
    const windows = [];
    for (let i = 0; i + 2 < pts.length; i++) {
        const w = pts.slice(i, i + 3);
        const vs = w.map(s => s.avg_velocity);
        const spread = Math.max(...vs) - Math.min(...vs);
        windows.push({ start: i, end: i + 2, points: w, spread, metrics: _combinedShotMetrics(w.map(s => s.velocities)) });
    }
    windows.sort((a, b) => a.spread - b.spread);
    const chosen = [];
    for (const w of windows) {
        if (chosen.length >= 2) break;
        const overlaps = chosen.some(c => w.start <= c.end && w.end >= c.start);
        if (!overlaps) chosen.push(w);
    }
    return chosen.sort((a, b) => a.start - b.start);
}

function _renderSuggestedNodesHTML(steps) {
    const suggestions = _suggestLadderNodes(steps);
    if (!suggestions.length) return '';
    return `
        <div class="bg-gray-800 p-3 rounded-lg border border-emerald-700/40 shadow-xl">
            <h4 class="text-xs font-bold text-emerald-400 uppercase tracking-wider mb-2">🎯 Suggested Node${suggestions.length > 1 ? 's' : ''} (flattest velocity spots)</h4>
            <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2">
            ${suggestions.map((w, idx) => {
                const mid = w.points[1];
                const m = w.metrics;
                const statsLine = m
                    ? `Avg <b class="text-white">${m.avg}</b> fps · ES ${m.es} · SD ${m.sd} <span class="text-gray-500">(${m.n} shots)</span>`
                    : '';
                return `<div class="bg-gray-900/40 border border-gray-700 rounded-lg p-2.5 flex flex-col gap-1.5 text-xs text-gray-300">
                    <div>Node ${idx + 1}: ${w.points[0].charge_weight}–${w.points[2].charge_weight}gr, centered on <b class="text-white">${mid.charge_weight}gr</b></div>
                    ${statsLine ? `<div class="text-gray-400">${statsLine}</div>` : ''}
                    <button onclick="saveWinnerAsHandload(${mid.id})" class="self-start bg-emerald-700 hover:bg-emerald-600 text-white px-2.5 py-1.5 rounded text-[11px] font-bold cursor-pointer">🧪 Create More Bullets</button>
                </div>`;
            }).join('')}
            </div>
        </div>`;
}

async function submitLadderStep() {
    const t = _currentLadderTest;
    if (!t) return;
    const chargeEl = document.getElementById('ls-charge');
    const velEl = document.getElementById('ls-velocities');
    const charge = parseFloat(chargeEl?.value);
    if (!charge) { showToast('Enter a charge weight', 'error'); return; }
    try {
        const res = await fetch(`/ladder-tests/${t.id}/steps/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ charge_weight: charge, velocities_csv: velEl?.value.trim() || null }),
        });
        if (!res.ok) { showToast('Failed to add step', 'error'); return; }
        const saved = await res.json();
        (saved.warnings || []).forEach(w => showToast(w, 'error'));
        if (chargeEl) chargeEl.value = '';
        if (velEl) velEl.value = '';
        await openLadderTest(t.id);
    } catch (err) { showToast('Failed to add step', 'error'); }
}

async function saveLadderStepVelocities(stepId) {
    const t = _currentLadderTest;
    if (!t) return;
    const input = document.getElementById(`step-vel-${stepId}`);
    const velocitiesCsv = input?.value.trim() || null;
    try {
        const res = await fetch(`/ladder-tests/${t.id}/steps/${stepId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ velocities_csv: velocitiesCsv }),
        });
        if (!res.ok) { showToast('Failed to save velocities', 'error'); return; }
        showToast('Saved', 'success');
        await openLadderTest(t.id);
    } catch (err) { showToast('Failed to save velocities', 'error'); }
}

async function deleteLadderStep(stepId) {
    const t = _currentLadderTest;
    if (!t || !confirm('Delete this charge step?')) return;
    try {
        const res = await fetch(`/ladder-tests/${t.id}/steps/${stepId}`, { method: 'DELETE' });
        if (!res.ok) { showToast('Failed to delete step', 'error'); return; }
        await openLadderTest(t.id);
    } catch (err) { showToast('Failed to delete step', 'error'); }
}

async function toggleLadderWinner(stepId) {
    const t = _currentLadderTest;
    if (!t) return;
    try {
        const res = await fetch(`/ladder-tests/${t.id}/steps/${stepId}/toggle-winner`, { method: 'POST' });
        if (!res.ok) { showToast('Failed to update winner', 'error'); return; }
        _currentLadderTest = await res.json();
        renderLadderDetail();
    } catch (err) { showToast('Failed to update winner', 'error'); }
}

async function deleteLadderTestConfirm() {
    const t = _currentLadderTest;
    if (!t || !confirm(`Delete ladder test "${t.name}" and all its steps?`)) return;
    try {
        const res = await fetch(`/ladder-tests/${t.id}`, { method: 'DELETE' });
        if (!res.ok) { showToast('Failed to delete ladder test', 'error'); return; }
        showToast('Ladder test deleted', 'success');
        showLadderListView();
    } catch (err) { showToast('Failed to delete ladder test', 'error'); }
}

function buildLadderChartSVG(steps) {
    if (!steps || !steps.length) {
        return `<p class="text-xs text-gray-500 italic">Add charge steps to see the chart.</p>`;
    }
    const withVel = steps.filter(s => s.avg_velocity != null);
    if (!withVel.length) {
        return `<p class="text-xs text-gray-500 italic">Add velocities to see the chart.</p>`;
    }
    const sorted = [...withVel].sort((a, b) => a.charge_weight - b.charge_weight);
    const W = 600, H = 260, padL = 50, padR = 20, padT = 20, padB = 36;
    const chargeMin = sorted[0].charge_weight, chargeMax = sorted[sorted.length - 1].charge_weight;
    const chargeSpan = Math.max(chargeMax - chargeMin, 0.1);
    let velMin = Math.min(...sorted.map(s => s.avg_velocity - (s.extreme_spread || 0) / 2));
    let velMax = Math.max(...sorted.map(s => s.avg_velocity + (s.extreme_spread || 0) / 2));
    if (velMin === velMax) { velMin -= 20; velMax += 20; }
    const velPad = (velMax - velMin) * 0.15;
    velMin -= velPad; velMax += velPad;

    const x = c => padL + ((c - chargeMin) / chargeSpan) * (W - padL - padR);
    const y = v => H - padB - ((v - velMin) / (velMax - velMin)) * (H - padT - padB);

    const points = sorted.map(s => `${x(s.charge_weight).toFixed(1)},${y(s.avg_velocity).toFixed(1)}`).join(' ');

    const esLines = sorted.filter(s => s.extreme_spread).map(s => {
        const xPos = x(s.charge_weight).toFixed(1);
        return `<line x1="${xPos}" y1="${y(s.avg_velocity - s.extreme_spread / 2).toFixed(1)}" x2="${xPos}" y2="${y(s.avg_velocity + s.extreme_spread / 2).toFixed(1)}" stroke="#6b7280" stroke-width="1.5" />`;
    }).join('');

    // Each point is a visible dot plus a larger invisible circle on top carrying the click
    // handler — the bigger hit target makes it usable on a phone, while the dot itself stays
    // visually small. Clicking toggles that step as a node (same as the old table star column).
    const circles = sorted.map(s => {
        const r = s.is_winner ? 6 : 4;
        const fill = s.is_winner ? '#f59e0b' : '#60a5fa';
        const cx = x(s.charge_weight).toFixed(1);
        const cy = y(s.avg_velocity).toFixed(1);
        const tip = `${s.charge_weight}gr — ${s.avg_velocity} fps${s.extreme_spread ? ` (ES ${s.extreme_spread})` : ''} — click to ${s.is_winner ? 'unmark' : 'mark'} as node`;
        return `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" style="pointer-events:none" />` +
            `<circle cx="${cx}" cy="${cy}" r="${r + 8}" fill="transparent" style="cursor:pointer" onclick="toggleLadderWinner(${s.id})"><title>${tip}</title></circle>`;
    }).join('');

    const xTicks = sorted.map(s => `<text x="${x(s.charge_weight).toFixed(1)}" y="${H - padB + 16}" font-size="10" fill="#9ca3af" text-anchor="middle">${s.charge_weight}</text>`).join('');

    const yTickCount = 4;
    const yTicks = Array.from({ length: yTickCount + 1 }, (_, i) => {
        const v = velMin + (i / yTickCount) * (velMax - velMin);
        const yPos = y(v);
        return `<line x1="${padL}" y1="${yPos.toFixed(1)}" x2="${W - padR}" y2="${yPos.toFixed(1)}" stroke="#374151" stroke-width="1" />` +
               `<text x="${padL - 8}" y="${(yPos + 3).toFixed(1)}" font-size="10" fill="#9ca3af" text-anchor="end">${Math.round(v)}</text>`;
    }).join('');

    return `<svg viewBox="0 0 ${W} ${H}" class="w-full h-auto">
        ${yTicks}
        ${esLines}
        <polyline points="${points}" fill="none" stroke="#60a5fa" stroke-width="2" />
        ${circles}
        ${xTicks}
        <text x="${W / 2}" y="${H - 4}" font-size="10" fill="#6b7280" text-anchor="middle">Charge Weight (gr)</text>
    </svg>`;
}

function saveWinnerAsHandload(stepId) {
    const t = _currentLadderTest;
    if (!t) return;
    const winner = t.steps.find(s => s.id === stepId);
    if (!winner) return;
    const handoff = {
        caliber: t.caliber,
        bullet_id: t.bullet_id,
        powder_name: t.powder_name,
        primer: t.primer,
        case_type: t.case_type,
        coal: t.coal,
        recipe_name: `${t.name} @ ${winner.charge_weight}gr`,
        powder_charge: winner.charge_weight,
    };
    sessionStorage.setItem('ladderHandoff', JSON.stringify(handoff));
    window.location.href = '/?tab=add-tab&cat=ammunition&handload=1';
}

async function applyLadderHandoff() {
    const raw = sessionStorage.getItem('ladderHandoff');
    if (!raw) return;
    sessionStorage.removeItem('ladderHandoff');
    let handoff;
    try { handoff = JSON.parse(raw); } catch (e) { return; }

    toggleAmmoType('handloads');
    await populateHandloadDropdowns();

    const calSel = document.getElementById('hl-caliber');
    if (calSel && handoff.caliber) { calSel.value = handoff.caliber; filterHandloadBullets(); }

    const bulSel = document.getElementById('hl-bullet');
    if (bulSel && handoff.bullet_id) {
        const opt = bulSel.querySelector(`option[data-id="${handoff.bullet_id}"]`);
        if (opt) { bulSel.value = opt.value; autofillBulletData(bulSel); }
    }

    const powSel = document.getElementById('hl-powder');
    if (powSel && handoff.powder_name) powSel.value = handoff.powder_name;
    const priSel = document.getElementById('hl-primer');
    if (priSel && handoff.primer) priSel.value = handoff.primer;
    const casSel = document.getElementById('hl-casing');
    if (casSel && handoff.case_type) casSel.value = handoff.case_type;

    const nameEl = document.querySelector('#ammo-handload-form input[name="recipe_name"]');
    if (nameEl && handoff.recipe_name) nameEl.value = handoff.recipe_name;
    const coalEl = document.querySelector('#ammo-handload-form input[name="coal"]');
    if (coalEl && handoff.coal != null) coalEl.value = handoff.coal;
    const chargeEl = document.querySelector('#ammo-handload-form input[name="powder_charge"]');
    if (chargeEl && handoff.powder_charge != null) chargeEl.value = handoff.powder_charge;

    showToast('Recipe pre-filled from ladder test winner', 'success');
}

window.onload = () => {
    fetchInitialLookupData(); applyPreferences(); loadLandingStats(); initCustomAC();
    const p = new URLSearchParams(location.search);
    if (p.has('tab')) switchTab(p.get('tab'));
    if (p.has('cat')) {
        switchTab('add-tab');
        const cat = p.get('cat');
        if (cat === 'optics') { switchFormCategory('cat-platforms'); switchAddForm('add-scope'); }
        else if (cat === 'tc-barrel') { switchFormCategory('cat-platforms'); switchAddForm('add-tc-barrel'); }
        else if (cat === 'tc-receiver') { switchFormCategory('cat-platforms'); switchAddForm('add-tc-receiver'); }
        else switchFormCategory('cat-' + cat);
    }
    if (p.get('handload') === '1') applyLadderHandoff();
    // Close user-menu dropdown when clicking outside
    const userMenu = document.getElementById('user-menu');
    if (userMenu) {
        document.addEventListener('click', e => {
            if (!userMenu.classList.contains('hidden') && !userMenu.parentElement.contains(e.target)) {
                userMenu.classList.add('hidden');
            }
        });
    }
};
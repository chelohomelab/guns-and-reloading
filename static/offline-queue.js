// Offline-write queue — lets a small, deliberately narrow set of actions (range-session logging,
// quick ammo rounds-used) work with zero connectivity and sync automatically once back online.
//
// Safe to queue: both target endpoints (POST /performance-log/ and POST /ammo/{id}/use-rounds/)
// compute their inventory-quantity effect as a server-side relative delta against whatever's
// currently in the DB row, never a client-supplied absolute value — so two queued writes, from
// this device or another, always compose correctly regardless of replay order. No conflict
// resolution needed. This is NOT a general-purpose offline-write mechanism — don't route other
// endpoints through this without re-checking that same delta-safety property first.
const OfflineQueue = (() => {
    const DB_NAME = 'gr-offline-queue';
    const STORE = 'writes';
    const FETCH_TIMEOUT_MS = 8000;
    const POLL_INTERVAL_MS = 20000;
    const LOCK_STALE_MS = 30000;
    const MAX_ATTEMPTS = 20;

    let dbPromise = null;
    let isFlushing = false;
    let pollTimer = null;

    function openDb() {
        if (dbPromise) return dbPromise;
        dbPromise = new Promise((resolve, reject) => {
            const req = indexedDB.open(DB_NAME, 1);
            req.onupgradeneeded = () => {
                req.result.createObjectStore(STORE, { keyPath: 'id', autoIncrement: true });
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
        return dbPromise;
    }

    async function withStore(mode, fn) {
        const db = await openDb();
        return new Promise((resolve, reject) => {
            const tx = db.transaction(STORE, mode);
            const store = tx.objectStore(STORE);
            let result;
            Promise.resolve(fn(store)).then((r) => { result = r; }).catch(reject);
            tx.oncomplete = () => resolve(result);
            tx.onerror = () => reject(tx.error);
        });
    }

    function reqToPromise(req) {
        return new Promise((resolve, reject) => {
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
        });
    }

    function fetchWithTimeout(url, opts) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
        return fetch(url, { ...opts, signal: controller.signal, credentials: 'same-origin' })
            .finally(() => clearTimeout(timer));
    }

    // Splits a FormData into plain string fields plus (at most) one Blob/File, since that's all
    // either target endpoint's payload shape needs — not a general FormData serializer.
    function splitFormData(formData) {
        const fields = {};
        let blob = null, blobField = null, blobName = null, blobType = null;
        for (const [key, value] of formData.entries()) {
            if (value instanceof Blob) {
                blob = value; blobField = key;
                blobName = value.name || 'upload.jpg';
                blobType = value.type || 'application/octet-stream';
            } else {
                fields[key] = value;
            }
        }
        return { fields, blob, blobField, blobName, blobType };
    }

    function rebuildRequest(record) {
        if (record.kind === 'json') {
            return { body: JSON.stringify(record.fields), headers: { 'Content-Type': 'application/json' } };
        }
        const fd = new FormData();
        for (const [k, v] of Object.entries(record.fields)) fd.append(k, v);
        if (record.blob) fd.append(record.blobField, record.blob, record.blobName);
        return { body: fd, headers: {} };
    }

    function labelFor(url, fields) {
        if (url.includes('/use-rounds/')) return `Used ${fields.rounds ?? '?'} rounds`;
        if (url === '/performance-log/') {
            return `Range session — ${fields.date || ''}${fields.ammo_id ? ' (ammo #' + fields.ammo_id + ')' : ''}`;
        }
        return url;
    }

    function isSafeSuccess(resp) {
        return resp.ok && !resp.redirected;
    }

    async function queueOrSend(url, { method = 'POST', body, headers } = {}) {
        const isForm = body instanceof FormData;
        const kind = isForm ? 'form' : 'json';
        const { fields, blob, blobField, blobName, blobType } = isForm
            ? splitFormData(body)
            : { fields: body || {}, blob: null, blobField: null, blobName: null, blobType: null };

        if (navigator.onLine !== false) {
            try {
                const opts = isForm
                    ? { method, body }
                    : { method, body: JSON.stringify(body), headers: { 'Content-Type': 'application/json', ...(headers || {}) } };
                const resp = await fetchWithTimeout(url, opts);
                if (isSafeSuccess(resp)) return { queued: false, response: resp };
                if (resp.status >= 400 && resp.status < 500 && !resp.redirected) {
                    return { queued: false, response: resp };
                }
                // 5xx, or a redirected/ambiguous response — fall through to enqueue.
            } catch (_) {
                // Network error or timeout — fall through to enqueue.
            }
        }

        const record = {
            url, kind, fields, blob, blobField, blobName, blobType,
            label: labelFor(url, fields),
            createdAt: new Date().toISOString(),
            attempts: 0, lastError: null, lockedAt: null, nextRetryAt: 0,
        };
        await withStore('readwrite', (store) => reqToPromise(store.add(record)));
        armPolling();
        refreshBadge();
        flush(); // best-effort immediate attempt (e.g. we were offline a moment ago and just reconnected)
        return { queued: true };
    }

    async function flush() {
        if (isFlushing) return;
        isFlushing = true;
        try {
            const all = await withStore('readonly', (store) => reqToPromise(store.getAll()));
            const now = Date.now();
            for (const record of all) {
                if (record.stuck) continue;
                if (record.lockedAt && now - record.lockedAt < LOCK_STALE_MS) continue;
                if (record.nextRetryAt && record.nextRetryAt > now) continue;
                await attemptOne(record);
            }
        } finally {
            isFlushing = false;
            refreshBadge();
            const remaining = await pendingCount();
            if (remaining === 0) disarmPolling();
        }
    }

    async function attemptOne(record) {
        await withStore('readwrite', (store) => reqToPromise(store.put({ ...record, lockedAt: Date.now() })));
        try {
            const { body, headers } = rebuildRequest(record);
            const resp = await fetchWithTimeout(record.url, { method: 'POST', body, headers });
            if (isSafeSuccess(resp)) {
                await withStore('readwrite', (store) => reqToPromise(store.delete(record.id)));
                return;
            }
            if (resp.status >= 400 && resp.status < 500 && !resp.redirected) {
                await markStuck(record, `Server rejected (HTTP ${resp.status})`);
                return;
            }
            await markRetry(record, `HTTP ${resp.status}`);
        } catch (e) {
            await markRetry(record, String(e && e.message || e));
        }
    }

    async function markRetry(record, err) {
        const attempts = record.attempts + 1;
        if (attempts >= MAX_ATTEMPTS) {
            await markStuck(record, `Giving up after ${attempts} attempts: ${err}`);
            return;
        }
        const backoffMs = Math.min(Math.pow(2, attempts) * 5000, 5 * 60 * 1000);
        await withStore('readwrite', (store) => reqToPromise(store.put({
            ...record, attempts, lastError: err, lockedAt: null, nextRetryAt: Date.now() + backoffMs,
        })));
    }

    async function markStuck(record, err) {
        await withStore('readwrite', (store) => reqToPromise(store.put({
            ...record, lastError: err, lockedAt: null, stuck: true,
        })));
    }

    async function pendingCount() {
        const all = await withStore('readonly', (store) => reqToPromise(store.getAll()));
        return all.length;
    }

    async function listPending() {
        const all = await withStore('readonly', (store) => reqToPromise(store.getAll()));
        return all.map((r) => ({ id: r.id, label: r.label, attempts: r.attempts, lastError: r.lastError, stuck: !!r.stuck }));
    }

    async function retryNow(id) {
        await withStore('readwrite', (store) => reqToPromise(store.get(id)).then((r) => {
            if (r) return store.put({ ...r, stuck: false, lockedAt: null, nextRetryAt: 0 });
        }));
        armPolling();
        flush();
    }

    async function discard(id) {
        await withStore('readwrite', (store) => reqToPromise(store.delete(id)));
        refreshBadge();
    }

    function armPolling() {
        if (pollTimer) return;
        pollTimer = setInterval(flush, POLL_INTERVAL_MS);
    }

    function disarmPolling() {
        if (!pollTimer) return;
        clearInterval(pollTimer);
        pollTimer = null;
    }

    // ── Pending-items badge (JS-injected, not duplicated template markup — only 2 pages use this) ──
    let badgeEl = null, listEl = null;

    function ensureBadgeDom() {
        if (badgeEl) return;
        badgeEl = document.createElement('div');
        badgeEl.id = 'offline-queue-badge';
        badgeEl.className = 'hidden fixed bottom-4 left-4 z-[190] bg-amber-900/95 text-amber-200 text-xs font-bold rounded-lg shadow-lg cursor-pointer select-none';
        badgeEl.innerHTML = '<div class="px-3 py-2" id="offline-queue-badge-summary"></div>';
        listEl = document.createElement('div');
        listEl.id = 'offline-queue-list';
        listEl.className = 'hidden border-t border-amber-700/60 max-h-64 overflow-y-auto text-[11px] font-normal';
        badgeEl.appendChild(listEl);
        badgeEl.querySelector('#offline-queue-badge-summary').addEventListener('click', toggleList);
        document.body.appendChild(badgeEl);
    }

    function toggleList() {
        listEl.classList.toggle('hidden');
        if (!listEl.classList.contains('hidden')) renderList();
    }

    async function renderList() {
        const items = await listPending();
        listEl.innerHTML = items.map((it) => `
            <div class="px-3 py-1.5 border-t border-amber-800/40 flex items-center justify-between gap-2">
                <div class="truncate">
                    <div class="truncate">${it.label}</div>
                    ${it.stuck ? `<div class="text-red-300 truncate">${it.lastError || 'Failed'}</div>` : ''}
                </div>
                ${it.stuck ? `
                    <div class="flex gap-1 shrink-0">
                        <button data-retry="${it.id}" class="px-1.5 py-0.5 bg-amber-700 hover:bg-amber-600 rounded cursor-pointer">Retry</button>
                        <button data-discard="${it.id}" class="px-1.5 py-0.5 bg-red-900 hover:bg-red-800 rounded cursor-pointer">Discard</button>
                    </div>` : ''}
            </div>
        `).join('');
        listEl.querySelectorAll('[data-retry]').forEach((btn) => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); retryNow(parseInt(btn.dataset.retry)).then(() => { refreshBadge(); renderList(); }); });
        });
        listEl.querySelectorAll('[data-discard]').forEach((btn) => {
            btn.addEventListener('click', (e) => { e.stopPropagation(); discard(parseInt(btn.dataset.discard)).then(renderList); });
        });
    }

    async function refreshBadge() {
        ensureBadgeDom();
        const n = await pendingCount();
        const summary = badgeEl.querySelector('#offline-queue-badge-summary');
        if (n === 0) {
            badgeEl.classList.add('hidden');
            listEl.classList.add('hidden');
        } else {
            summary.textContent = `⏳ ${n} pending sync`;
            badgeEl.classList.remove('hidden');
            if (!listEl.classList.contains('hidden')) renderList();
        }
    }

    function init() {
        ensureBadgeDom();
        window.addEventListener('online', flush);
        refreshBadge().then(async () => {
            if (await pendingCount() > 0) { armPolling(); flush(); }
        });
    }

    return { queueOrSend, pendingCount, listPending, retryNow, discard, init };
})();

window.OfflineQueue = OfflineQueue;

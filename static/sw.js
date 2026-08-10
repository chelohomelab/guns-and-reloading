// Offline read-caching service worker. Read-only: mutations (non-GET) always go straight to
// network — offline writes are a separate future step (journal/queue), not handled here.
//
// Four independent caches, each with its own eviction policy:
//   gr-static  — CDN libs (Tailwind, zxing), site images, manifest.json, app.js — cache-first,
//                never purged on login/logout since nothing here is user-specific.
//   gr-shell   — the 11 page shells reachable via normal browsing — network-first w/ cache
//                fallback, purged on every /login render.
//   gr-data    — JSON from the "user's own inventory" endpoint allowlist — network-first w/
//                cache fallback, purged on every /login render.
//   gr-images  — /static/uploads/* — cache-as-you-view only (never bulk-fetched), purged on
//                every /login render.
//
// SW_VERSION is a manual bump, mirroring the existing manually-bumped `?v=NNN` convention
// already used for app.js — bump it whenever this file's caching behavior changes.
const SW_VERSION = 'v2';
const STATIC_CACHE = `gr-static-${SW_VERSION}`;
const SHELL_CACHE = `gr-shell-${SW_VERSION}`;
const DATA_CACHE = `gr-data-${SW_VERSION}`;
const IMAGE_CACHE = `gr-images-${SW_VERSION}`;
const KNOWN_CACHES = [STATIC_CACHE, SHELL_CACHE, DATA_CACHE, IMAGE_CACHE];

const STATIC_URLS = [
  '/static/manifest.json',
  '/static/images/app-icon.png',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
  '/static/images/logo.png',
  '/static/images/background.png',
  '/static/images/phone-background.png',
];
// Fetched individually (not via cache.addAll, which is all-or-nothing) so a CDN hiccup during
// install doesn't fail the whole install.
const CROSS_ORIGIN_URLS = [
  'https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4',
  'https://unpkg.com/@zxing/library@0.20.0/umd/index.min.js',
];

// Exact-match shell routes (server ignores no query string for these).
const SHELL_EXACT = ['/', '/index.html', '/inventory', '/wishlist', '/admin/scanner'];
// The server ignores these routes' ?id=... query string entirely (client-side JS reads it) —
// one cached shell per route serves every item; per-item data comes from the JSON tier instead.
const SHELL_IGNORE_SEARCH = [
  '/ammo-detail.html',
  '/bullet-detail.html',
  '/firearm-detail.html',
  '/handgun-detail.html',
  '/shotgun-detail.html',
  '/scope-detail.html',
  '/tc-barrel-detail.html',
];

// "User's own inventory" — small, always network-first with cache fallback. Also includes
// /reload-data/loads and /reload-data/filters as a bounded on-demand exception: the backing
// table has 27,761 rows across 46 manufacturers and must NEVER be bulk-cached — network-first
// with cache-fallback already only ever caches the exact query the user actually made, so no
// extra code is needed. Do not "improve" this into a prefix/bulk match.
const DATA_PATTERNS = [
  /^\/ammo\/(\d+)?$/,
  /^\/ammo\/\d+\/purchase-log$/,
  /^\/firearms\/\d+$/,
  /^\/catalog\/$/,
  /^\/components\/(powders|primers|bullets|casings|low-stock)\/$/,
  /^\/components\/bullets\/\d+$/,
  /^\/scopes\/(\d+)?$/,
  /^\/available-mounts\/$/,
  /^\/wishlist\/$/,
  /^\/tc-receivers\/$/,
  /^\/tc-barrels\/(\d+)?$/,
  /^\/ladder-tests\/(\d+)?$/,
  /^\/test-platforms\/$/,
  /^\/performance-log\/.*$/,
  /^\/entries$/,
  /^\/api\/preferences\/$/,
  /^\/lookups\/$/,
  /^\/settings\/$/,
  /^\/reload-data\/loads$/,
  /^\/reload-data\/filters$/,
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(STATIC_CACHE);
    await cache.addAll(STATIC_URLS);
    await Promise.allSettled(
      CROSS_ORIGIN_URLS.map(async (url) => {
        try {
          const resp = await fetch(url, { mode: 'cors' });
          if (resp.ok) await cache.put(url, resp);
        } catch (_) {
          // Offline install or CDN hiccup — non-fatal, retried opportunistically on next
          // successful fetch of the same URL (won't happen automatically, but doesn't block
          // install of everything else).
        }
      })
    );
    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const names = await caches.keys();
    await Promise.all(names.filter((n) => !KNOWN_CACHES.includes(n)).map((n) => caches.delete(n)));
    await self.clients.claim();
  })());
});

async function purgeUserScopedCaches() {
  await Promise.all([caches.delete(SHELL_CACHE), caches.delete(DATA_CACHE), caches.delete(IMAGE_CACHE)]);
}

// Marks a response as served from the offline cache so page JS can optionally distinguish
// stale/cached data from a live fetch — cloning is required since Response.headers is
// otherwise immutable once constructed from a cache read.
function withOfflineHeader(resp) {
  const headers = new Headers(resp.headers);
  headers.set('X-Served-From', 'sw-cache');
  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers });
}

// AuthMiddleware 302-redirects any unauthenticated request to /login. If a session expires
// while this SW does a network-first fetch, fetch() follows that redirect transparently and
// returns a 200 HTML login page — caching that under the original request's cache key would
// silently poison the shell/data cache with login-page content. Guard against it here.
function isSafeToCache(resp) {
  return resp.ok && !resp.redirected;
}

function isStaticAsset(url) {
  return (
    STATIC_URLS.includes(url.pathname) ||
    url.pathname === '/static/app.js' ||
    CROSS_ORIGIN_URLS.includes(url.href)
  );
}

async function handleStatic(req) {
  const cached = await caches.match(req);
  if (cached) return cached;
  try {
    const resp = await fetch(req);
    if (resp.ok) (await caches.open(STATIC_CACHE)).put(req, resp.clone());
    return resp;
  } catch (e) {
    if (cached) return cached;
    throw e;
  }
}

async function handleShell(req, url) {
  const ignoreSearch = SHELL_IGNORE_SEARCH.includes(url.pathname);
  const cacheKey = ignoreSearch ? new Request(url.origin + url.pathname) : req;
  try {
    const resp = await fetch(req);
    if (isSafeToCache(resp) && new URL(resp.url).pathname !== '/login') {
      (await caches.open(SHELL_CACHE)).put(cacheKey, resp.clone());
    }
    return resp;
  } catch (e) {
    const cached = await caches.match(cacheKey, { ignoreSearch, cacheName: SHELL_CACHE });
    if (cached) return withOfflineHeader(cached);
    throw e;
  }
}

async function handleData(req) {
  try {
    const resp = await fetch(req);
    if (isSafeToCache(resp)) (await caches.open(DATA_CACHE)).put(req, resp.clone());
    return resp;
  } catch (e) {
    const cached = await caches.match(req, { cacheName: DATA_CACHE });
    if (cached) return withOfflineHeader(cached);
    throw e;
  }
}

async function handleImage(req) {
  const cached = await caches.match(req, { cacheName: IMAGE_CACHE });
  if (cached) {
    // Stale-while-revalidate: return the cached copy immediately, refresh in the background.
    fetch(req)
      .then((resp) => {
        if (resp.ok) caches.open(IMAGE_CACHE).then((c) => c.put(req, resp));
      })
      .catch(() => {});
    return cached;
  }
  const resp = await fetch(req);
  if (resp.ok) (await caches.open(IMAGE_CACHE)).put(req, resp.clone());
  return resp;
}

async function route(req, url) {
  if (url.pathname === '/login' && req.mode === 'navigate') {
    let resp;
    try {
      resp = await fetch(req);
    } finally {
      await purgeUserScopedCaches();
    }
    return resp;
  }

  if (isStaticAsset(url)) return handleStatic(req);

  if (
    req.mode === 'navigate' &&
    (SHELL_EXACT.includes(url.pathname) || SHELL_IGNORE_SEARCH.includes(url.pathname))
  ) {
    return handleShell(req, url);
  }

  if (DATA_PATTERNS.some((re) => re.test(url.pathname))) return handleData(req);

  if (url.pathname.startsWith('/static/uploads/')) return handleImage(req);

  return fetch(req);
}

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  event.respondWith(route(event.request, url));
});

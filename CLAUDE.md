# CLAUDE.md

Working notes for Claude Code in this repo — conventions, workflow, decisions and their reasons,
and gotchas that aren't visible from the code alone. This file is meant to travel with the repo
(unlike `~/.claude/projects/*/memory/`, which is per-machine and does not). If you're picking this
project up fresh, read this whole file before making changes.

## What this is

`chelohomelab/guns-and-reloading` — a self-hosted firearms inventory + reloading-data web app,
built for one user (a NJ hunter/reloader) who wanted their own tool instead of spreadsheets.
FastAPI + Jinja2 + SQLAlchemy + SQLite, no JS framework (`static/app.js` is one large vanilla-JS
file, Tailwind via CDN `<script>`). Public repo, MIT-adjacent-but-not-yet-formalized licensing (see
Decisions below).

Routers live in `routers/` (one file per feature area: `firearms`, `ammunition`, `components`,
`ladder`, `reload_data`, `scanner`, `product_import`, `upgrade`, `backup`, etc.), all registered in
`main.py`. Models in `database.py` (single file, SQLAlchemy declarative). Templates in
`templates/`, one big `static/app.js` plus a handful of standalone pages that carry their own
inline JS (`scanner.html`, formerly `hunting.html` before it was removed).

## The user

Deep firearms/reloading domain knowledge, works fast, wants implementation to move without
stopping for routine confirmations — but reviews output closely (has caught real correctness bugs
by manually cross-checking data against source PDFs/screenshots multiple times). Comfortable with
git/GitHub but delegates the mechanics. Runs several unrelated personal projects on the same
machine (see "Other projects on this machine" below) — don't assume a running process belongs to
this one without checking.

## Dev environment & workflow

- **Venv**: `.venv/` in the repo root, `uv`-managed Python 3.12. No system `pip` — install with
  `uv pip install <pkg> --python .venv/bin/python3`.
- **Dev server**: `.venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8124 --reload`.
  `--reload` is mandatory, not optional — without it, backend edits silently never load into the
  running process and you'll debug a "bug" that's actually just a stale server (this cost real
  time more than once). **Leave it running** after verifying a change so the user can check things
  live in their browser without asking for a restart. Port 8124 is this project's usual port on
  this machine, but always confirm with `ps aux | grep uvicorn` before assuming what's running
  where — see next section.
- **Verify backend changes via real HTTP against the running server, not fresh Python imports.** A
  fresh `python3 -c "import routers.x"` always reflects the latest file on disk regardless of
  whether the *server* has reloaded — it can give false confidence while the live app is still
  running old code. Pattern that works well: insert a throwaway session row directly into
  `user_sessions` via a small script, `curl` the real endpoint with that cookie, inspect the DB
  afterward, delete the session row when done. For anything spanning more than one endpoint (e.g.
  upload → parse → query), drive the *whole* chain this way rather than trusting each step in
  isolation.
- **JS verification**: no system `node`. A working binary exists at
  `/home/chelo/.vscode-server/bin/<hash>/node` (find via
  `find /home/chelo -iname node -type f`, path changes if VS Code Server updates) — use
  `node -c static/app.js` for a syntax check. For verifying a specific render function against real
  data without a full browser: stub a minimal `document.getElementById` returning a fake element
  with an `.innerHTML` string, extract the exact function(s) needed by line range, `eval()` them,
  call the function with real JSON fetched from the live server, and assert on the resulting HTML
  string. This has caught real bugs a syntax check alone wouldn't (e.g. confirming a new flag
  actually renders, not just that the file parses). A portable Node+jsdom setup has been built
  before in this project but lives in a session scratchpad — it does not persist across sessions,
  rebuild if you want real DOM behavior instead of the eval-snippet approach.
- **Run commands directly, without asking first**, for routine dev work in this project: shell
  commands, DB migrations against the dev DB, verification curls, creating/deleting test rows,
  editing and committing files locally. The user explicitly asked not to be interrupted for this
  class of action. Still use judgment for genuinely destructive/hard-to-reverse actions outside the
  agreed plan (see git workflow below for the one specific carve-out that *does* need an explicit
  go-ahead every time).

### Other projects on this machine

The user runs several unrelated apps side by side under `/home/chelo/`:
`hunting-blogging-and-cooking` (a separate app spun out of this one, see Decisions below),
`rifle-gastronomy`, `Scotch_and_Bourbon`, `vanity-edits`. **Before assuming a running `uvicorn`
process on some port is this project's server, check its `--app-dir`/cwd** — a dev server for a
different app can be running on a port you'd otherwise assume is this one's, and killing/restarting
the wrong session's server mid-work is a real mistake that's happened before. `ps aux | grep
uvicorn` shows the command line including cwd/app-dir; check before you kill anything.

## Git / release workflow

**Local commits are fine to make freely** as part of routine work. **`git push`, `gh pr create`,
and `gh pr merge` (and by extension tagging/releasing) require an explicit go-ahead from the user
each time** — this was a hard correction after a stretch of pushing/merging too liberally on short
confirmations. Don't infer "go ahead" from an unrelated reply; wait for something unambiguous about
the specific push/PR in question. If genuinely unsure whether this gate is still in force, ask
rather than assume either way.

**Once given the go-ahead, the full pattern for a change is:**

1. `git checkout -b <branch-name>` off `main`.
2. Implement, verify live (per above), commit locally (plain `git commit`, attribution line below).
3. If this release should bump the version, edit `VERSION` (`X.Y` format, no patch digit shown even
   though tags are `vX.Y.0`) and commit that **on the same branch**, before merging — version bumps
   are not their own separate PR, they ride along with the feature/fix that earns them.
4. `git push -u origin <branch-name>`.
5. `gh pr create` — title short, body has a `## Summary` (bullets) and `## Test plan` (checked
   boxes for what was actually verified), ending with the required Claude Code attribution line.
6. Check `gh pr view <n> --json state,mergeable,mergeStateStatus` is clean, then
   `gh pr merge <n> --merge --delete-branch=false` (branch is kept, not deleted, by convention here).
7. **`git fetch origin` before `git merge --ff-only origin/main`.** Skipping the fetch is a real
   trap: `git merge --ff-only` against a *stale* local `origin/main` ref silently no-ops (reports
   "already up to date" when it isn't), and a subsequent `git checkout main` will revert your
   working tree back to the pre-merge state — looking exactly like your merge got undone. Always
   fetch first, then `git log --oneline origin/main -3` to sanity-check before merging.
8. If this is a release: `git tag -a vX.Y.0 -m "vX.Y.0"`, `git push origin vX.Y.0`, then
   `gh release create vX.Y.0 --title "vX.Y — <short theme>" --notes-file <file>` with a body
   structured as `## Highlights` / `## Fixed` / `## Removed` (only the sections that apply) in
   plain, user-facing language — these notes are read by the user, not written as a changelog for
   developers.
9. Trigger the desktop installer build: `gh workflow run build-desktop.yml --ref main`, watch it
   (`gh run watch <id> --exit-status`, fine to background this and pick up the result later),
   `gh run download <id> --dir <tmp-dir>`, then `gh release upload vX.Y.0 <the 3 files>`. This
   workflow is `workflow_dispatch`-only (not tied to tag push) — it has to be triggered by hand
   every release, it does not run itself. Desktop installer status in release notes should say
   "Builds and passes CI; not yet confirmed on real hardware" unless the user has actually told you
   a specific platform was tested — don't reuse a stale "confirmed working" claim from a previous
   release's notes.

**Commit/PR attribution** (current instruction, may be updated by a future system reminder — trust
a newer one over this file if they conflict):
```
Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
```
in commit messages, and
```
🤖 Generated with [Claude Code](https://claude.com/claude-code)
```
at the end of PR/release bodies.

**Production is a separate deployment** (a Proxmox LXC, `git pull` + `systemctl restart`, own
independent SQLite DB — see `docs/installation.md`). Shipping a release does *not* ship data that
only lives in the dev DB: for reload-data manufacturers with an automated parser (Hodgdon, Nosler,
Speer, Sierra, Barnes, Vihtavuori), the PDFs need to be re-uploaded through `/admin/reload-data` on
production after the code update; for Hornady's hand-transcribed cartridges, `git pull` +
`.venv/bin/python scripts/reload_data_seeds/<file>.py` on production is the actual ship mechanism.
Always flag this "does the data actually reach production" question when a feature's value is
in the *data*, not just the code — this has been raised as a real gap before (see Hornady below).

## Established architectural conventions

- **Admin auth is a per-router copy-pasted guard, not a shared dependency**:
  `def _require_admin(request): if not getattr(request.state, "user", None) or not
  request.state.user.is_admin: raise HTTPException(403, ...)`, called at the top of each protected
  route handler. This is the existing convention throughout the codebase — don't "clean it up" into
  a shared `Depends()` uninvited; it's intentional (matches how `_require_admin` already appears
  identically in `routers/admin.py`, `routers/upgrade.py`, `routers/reload_data.py`, etc.).
- **Caliber has two completely separate domains, never cross them:**
  - *Cartridge-name domain* (`Ammo`, `Barrel`, `LoadData`, `LadderTest`, `TestPlatform`,
    `Wishlist`, `UpcCache`/`ScannerEntry` when not bullet-typed) — canonical format is the full
    name, no leading dot: `"308 Winchester"`, `"7mm Remington Magnum"`, `"22 LR"`. Route any new
    text through `normalize_caliber()` (`routers/barcode.py`) before storing.
  - *Bore-diameter domain* (`BulletInventory.caliber`, bullet-typed `UpcCache`/`ScannerEntry`
    rows) — bare bore diameter like `".308"`, `".277"`. **Never** run these through
    `normalize_caliber()`. When comparing across the two domains (e.g. matching a reload-data row's
    bullet diameter against owned bullet inventory), normalize both sides to the same format first
    (`_normalize_bore_dia()` in `routers/reload_data.py` strips a leading `0` so `"0.308"` and
    `".308"` compare equal) — a mismatched format between two tables that both happen to store "the
    same" value has caused a real false-positive "in stock" bug before.
- **"Never guess" is a load-bearing principle across this codebase**, not just a style preference —
  it was adopted after multiple real, damaging guessing bugs (BC/G1 ballistic-coefficient
  mismatches that silently attached the wrong bullet's spec to a different product; reload-data
  parsers accepting a malformed row by assuming column *position* instead of matching a real
  shape). The pattern everywhere: a line/row/field either matches an anchored, explicit shape, or
  it's rejected into a visible "couldn't parse this" list — never filled in by positional guessing,
  weight-only matching, or "there's only one candidate so it must be this one." If you're tempted
  to loosen a match to catch more cases, that's usually the wrong direction here; ask before doing
  it.
- **In-stock / cross-reference matching is exact-key only, same reasoning as above.** Reload-data's
  "in stock" badge matches brand+weight+caliber+model exactly against owned inventory; when brand+
  weight+caliber match but the model text doesn't (manufacturers abbreviate model names
  inconsistently — "HPBT-SMK" vs. a user's own "MatchKing"), the UI shows the user's own owned
  model text ("You have: MatchKing") rather than emitting a true/false guess either way. Don't
  build a model-alias table to force this into a boolean — that was considered and explicitly
  rejected in favor of surfacing the ambiguity to the user's own judgment.
- **Cache writes that might be re-run from multiple sources use `prefer_existing` /
  `source_tier`, not last-write-wins.** `upsert_upc_cache()` (`routers/barcode.py`) defaults to
  overwriting on every non-null field, but capture flows that can legitimately be re-run against
  the same record (a UPC captured from multiple retailer sites) pass `prefer_existing=True` so a
  later, worse-quality source can't clobber an earlier good value — multi-source capture is a
  merge/fill-gaps operation, never a blind replace. `source_tier` (`'site'` vs `'api'`) exists so a
  first real site capture can still fully upgrade a stale low-confidence row exactly once, then
  protect it from future downgrades. If you add another field that's "sometimes a confident scrape,
  sometimes a low-confidence guess" (like `bc_g1`'s reference-table fallback), it needs the same
  explicit tier-upgrade-clears treatment, not silent reliance on the general "null never overwrites"
  rule.
- **Nav links are duplicated across ~19 templates**, not a shared partial/include. Any change to
  the shared admin dropdown or top nav (adding/removing a link) needs to be applied to every
  template that carries it — a small Python regex script over the template files is the fastest
  reliable way to do this consistently; hand-editing one at a time is how gaps get introduced (this
  has happened: some pages went for weeks with an incomplete mobile nav before anyone noticed, see
  `git log` around "mobile-nav-consistency" for the fix and audit method).
- **Reloading Data Center: one parser per manufacturer, each genuinely different, in
  `routers/reload_data.py`.** Before writing a new manufacturer's parser: (1) check
  `page.extract_text()` character count on every page of a real sample file *first* — a
  scanned-image PDF looks identical to a real text PDF until you actually try to extract text, and
  this distinguishes which of the two build paths below applies; (2) if it has real text, build an
  anchored-regex or position-based parser (`pdfplumber`), verify against every real sample file
  with 0 rejected rows before trusting it, and re-verify the *whole* file set after every
  subsequent change, not just the one row being fixed (this project has caught multiple real
  regressions this way — a fix for one edge case has silently broken previously-correct output
  elsewhere more than once); (3) if it's scanned images with no extractable text, OCR was tried and
  explicitly rejected for this data (silent digit-recognition errors like `50.9gr`→`509gr` are
  "dangerous specifically because they still parse as a valid-looking wrong number" — the user's
  words, "no margin for error" for reload charge data) — the fallback is Claude reading the images
  directly via vision and hand-writing a checked-in, re-runnable seed script
  (`scripts/reload_data_seeds/<name>.py`, using `_common.py`'s `import_hand_transcribed()`), never
  OCR-to-database. Only add schema columns for concepts actually observed in real files, never
  speculatively — every manufacturer built so far has revealed at least one "parsed then discarded"
  field on a later pass (Nosler's BC/SD, Speer's whole spec box, Sierra's Firearm Used, Vihtavuori's
  decimal bullet weights and two-word brands) that only surfaced once someone actually used the
  data, not on first build.
- **Version numbers live in `VERSION`** (repo root, plain text, `X.Y` — no patch digit even though
  git tags are `vX.Y.0`), read at runtime by `routers/upgrade.py` for the in-app "Check for
  Updates"/"Upgrade" flow (desktop and self-hosted). Desktop builds bundle this file; the
  self-upgrade flow reads it via `git show <rev>:VERSION`.

## Decisions and why (durable ones — see `docs/` and GitHub Releases for full history)

- **Hunting Per State (season dates/regs lookup) was built, then fully removed** and migrated to a
  separate private app, "Hunting, Blogging and Cooking" (`chelohomelab/hunting-blogging-and-cooking`,
  private repo, forked from this one's framework). Reasoning: it never really fit this app's
  "inventory and reloading" scope, and the user's actual vision for it (hunt journal with
  photos/video, offline-first field logging, onX-style maps, recipes from harvested game) is a much
  bigger, genuinely different product than a lookup table bolted onto an inventory tracker. If
  you're asked to add hunting-related features here, that's very likely scope creep the user has
  already deliberately moved elsewhere — check with them before building rather than assuming.
- **Multi-platform direction (desktop app + phone PWA) — desktop is done, phone sync is
  design-only, not built.** Agreed sequencing: (1) desktop packaging — **done**, real Windows/macOS/
  Linux installers via `build-desktop.yml`; (2) PWA read-caching — **done**, `static/sw.js`; (3)
  narrow offline-write journal/queue for range/consumption logging — **partially done**; (4) widen
  phone capability later. Key unbuilt design insight if you pick this back up: classify any
  offline-capable action as *journal* (a new fact, e.g. "logged 20 rounds fired" — never conflicts,
  safe to always queue) vs. *state* (mutating an existing value, e.g. a quantity field — the only
  kind that can conflict between devices) — inventory quantities should become values *derived*
  from journal entries rather than a raw counter multiple devices edit directly, specifically to
  avoid needing real conflict-resolution logic for the highest-traffic case.
- **Licensing: free for personal/self-hosted use, commercial use (reselling, hosting as a paid
  service) needs the user's buy-in — not yet formalized.** A `LICENSE` file exists with
  "all rights reserved" as the currently-binding statement and documents this intent as
  non-binding until real legal review happens. Don't treat the stated intent as enforceable terms,
  and don't publish/change licensing language without flagging that it still needs attorney review.
- **Multi-site product importer (bookmarklet-based UPC cache seeding) covers 7 ammo retailer sites**
  (MidwayUSA, Target Sports USA, Academy, Palmetto State Armory, LuckyGunner, Sportsman's Warehouse,
  Bass Pro/Cabela's) via `routers/product_import.py`'s per-hostname parsers, plus a Google-search
  fallback that extracts a G1 ballistic coefficient from search results. **Components (bullets/
  primers/powder/brass) were deliberately left out of this** — the user was explicit about not
  extending it to components yet; don't add a components bookmarklet without them asking again.
  Chose this scraping approach over any paid UPC-database API after checking — none of the
  commercial options (UPCitemdb, Go-UPC, Barcode Lookup) offer bulk export, and all are known-weak
  on ammo/firearms coverage specifically; no dedicated reloading-component UPC database/API exists
  at all.
- **Ladder Test "draft mode"**: a `LadderTest.is_draft` boolean flag on the existing model/
  endpoints (not a separate holding table) — lets a charge ladder be planned/edited with full UI
  parity to a real one, while skipping inventory deduction until an explicit "Submit & Deduct
  Components" action. Chosen specifically so a draft isn't a second, parallel, less-capable UI.

## Known gotchas (bugs already found and fixed once — don't reintroduce)

- **A shared generic key/value settings table blindly cast to one type breaks the moment an
  unrelated feature stores a different-shaped value in it.** `_get_thresholds()`
  (`routers/components.py`) once did `{s.key: float(s.value) for s in
  db.query(models.Setting).all()}` — crashed the moment the bookmarklet importer started storing a
  non-numeric `import_token` row in the same generic `Setting` table. Fixed by scoping the query to
  the exact keys the function actually owns. If you add anything to a shared generic table, check
  what else reads that table without filtering.
- **`git merge --ff-only` without a preceding `git fetch` silently no-ops against a stale ref** —
  see the git workflow section above; this produces a very confusing "my merge just got undone"
  symptom that's actually just never having merged what you thought you merged.
- **A pre-filter regex checked *before* a fuller row-parsing regex can silently drop valid rows
  without ever recording them as rejected**, if the pre-filter itself doesn't accept the full range
  of valid input shapes. Happened with Vihtavuori reload-data rows that had a decimal bullet weight
  (`155.5`, `200.2`) — the `^\d+\s` pre-filter didn't match them at all (decimal point where
  whitespace was expected), so they vanished before reaching the `rejected_lines` list, silently
  inflating an apparent "manufacturer's data is missing rows" discrepancy that was actually a bug
  on this side. If a parser's rejected-count doesn't explain 100% of a claimed/actual row-count
  gap, suspect the pre-filter before trusting a "their data is wrong" conclusion.
- **A "first word is the brand" split assumption breaks for genuinely two-word brand names** (e.g.
  reload-data manufacturers whose bullet-maker column reads "Fox Bullets Classic Hunter" — the
  brand is "Fox Bullets", not "Fox"). Fixed with a small hand-maintained multi-word-brand list
  checked before falling back to the naive split (`_VIHTAVUORI_MULTIWORD_BRANDS` pattern in
  `routers/reload_data.py`) — same "grow a hand-maintained exceptions list as real cases surface"
  approach used elsewhere in this codebase (`_BULLET_BRAND_ABBR`, `_POWDER_BRANDS`).
- **A "unique match in a small reference table" is not evidence of a correct match** — it's only
  evidence the table is incomplete. `_lookup_bc()`'s ballistic-coefficient reference-table fallback
  (`routers/barcode.py`) returned a BC as soon as there was exactly one brand+weight entry for a
  product, before checking caliber — silently attached a completely wrong bullet's BC to a real
  product three separate times before all the fallback tiers that could match without caliber were
  removed. Apply every available discriminating field before trusting uniqueness, in this table and
  any future one like it.
- **Don't reuse a SQL cursor for a query nested inside a loop that's iterating over that same
  cursor's results** — silently corrupts the iteration and produces wrong counts that look
  plausible. Caught once during a bulk "does the DB match a fresh re-parse" sweep.

## Where things stand / what's next

See `TODO.md` for the current in-progress/future item list (keep that file's "In Progress" section
honest — it's gone stale before). Check `gh release list --limit 5` and `VERSION` for the actual
shipped state, since TODO.md and release notes can drift out of sync with reality faster than this
file will.

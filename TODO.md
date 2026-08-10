# TODO

## In Progress

### Multi-Platform Rollout (`version-1.23` branch)
Desktop packaging, PWA offline read/write caching, and LAN-only HTTPS. Core functionality is
implemented and committed on `version-1.23` — this branch is now in the testing/polish phase
before merge.

**Testing needed:**
- [ ] Windows desktop installer — trigger the GitHub Actions build
      (`.github/workflows/build-desktop.yml`), download the artifact, run the raw `.exe` directly
      (no installer wrapper yet — see dev item below)
- [ ] macOS desktop installer — needs the `BUNDLE()` spec fix below done first, then build + test
      on the Mac desktop/laptop
- [ ] Docker deployment path (general) — never tested at all, no Docker available in dev sandbox
- [ ] Docker + LAN-only HTTPS (the `caddy` sidecar in `docker-compose.yml`) — never tested
- [ ] PWA install prompt ("Add to Home Screen") on Android/iOS — just implemented, not yet tried
- [ ] iPad — HTTPS trust flow + offline read/write features; iPadOS Safari can differ slightly
      from iPhone Safari in exact menu paths
- [ ] Step 3 offline-write queue remaining checklist: multiple queued items flushing in order, the
      logout-warning dialog when something's still pending, a permanently-failed item getting
      marked "stuck" instead of retrying forever
- [ ] `scripts/dev-phone-test.ps1` (WSL2 dev helper) — written but never actually run

**Small dev work remaining:**
- [ ] Add a `BUNDLE()` block to `desktop/inventory.spec` so macOS produces a real `.app` (currently
      just a raw executable folder, not double-clickable in Finder)
- [ ] Write `desktop/windows/installer.iss` (Inno Setup) — currently a TODO placeholder in the CI
      workflow
- [ ] Write the macOS `.dmg` packaging step (create-dmg or hdiutil) — currently a TODO placeholder
- [ ] Write the Linux AppImage packaging step (appimagetool) — currently a TODO placeholder
- [ ] Rebase `version-1.23` onto current `main` before merging — it's 16 commits ahead, 6 behind as
      of this writing (main picked up the range-day fixes, gitignore fix, and tab-persistence fix
      while this branch was in progress)

### UPC Cache (local)
- [ ] Add `upc_cache` table to database (upc, product_type, brand, product_line, caliber, weight_gr,
      bullet_type, bc_g1, bc_g7, rounds_per_box, primer_type, primer_model, powder_name, image_path, updated_at)
- [ ] Update barcode lookup endpoint: check `upc_cache` first, fall back to UPC Item DB API
- [ ] Pull product image from UPC Item DB API response (`images` array) and save locally on first lookup
- [ ] Add `upc` hidden field to all add-item forms (populated when a barcode is scanned)
- [ ] On form submit, upsert final form values into `upc_cache` keyed by UPC
- [ ] Let user override cached image with their own photo

## Future

### Auto-run reload-data seed scripts during upgrade
- [ ] `/admin/upgrade/run` (routers/upgrade.py) pulls code + submodule but never executes
      `scripts/reload_data_seeds/data/*.py` — new calibers still require a manual SSH run per
      script after every upgrade
- [ ] Decide how to detect which scripts are "new" (or just re-run all, since each is idempotent)
- [ ] Decide error handling if one script fails partway through a batch
- [ ] Surface results (rows imported per caliber) in the upgrade log the UI already shows

### Unlimited Photos per Item
- [ ] Create `ItemPhoto` table (id, item_type, item_id, image_path, sort_order, created_at)
- [ ] Add generic photo management endpoints (add, delete, reorder, set primary)
- [ ] Migrate existing `image_path` / `image_path_2` columns to new table
- [ ] Update all serializers to return photos array
- [ ] Update all detail page galleries to handle N photos
- [ ] Remove hardcoded 2-photo limit from upload logic

### Public Community UPC API
- [ ] Expose `upc_cache` as a public read API endpoint
- [ ] Add a write/correction endpoint for community contributions
- [ ] Seed database by scraping manufacturer catalogs (Hornady, Federal, Winchester, Remington, etc.)
- [ ] Add rate limiting, auth, and hosting if opened to public
- [ ] Consider crowdsourced voting/moderation for data quality

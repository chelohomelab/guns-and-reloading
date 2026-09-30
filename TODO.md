# TODO

## In Progress

_Last updated 2026-09-30 — the previous "Multi-Platform Rollout (`version-1.23` branch)" section
here was stale: that branch merged long ago (PR #32) and everything it listed (Windows/macOS/Linux
desktop installers, PWA install prompts, LAN-only HTTPS, offline-write queue) has since shipped —
see `CLAUDE.md`'s Decisions section and `gh release list` for what's actually live. Keep this
section honest going forward: when a branch/item here ships, remove it instead of leaving it to
rot — check `VERSION` and recent releases against this file before trusting either blindly._

### Reloading Data Center caliber dropdown
Branch `reload-data-caliber-dropdown` — committed locally, **not yet pushed/PR'd/merged/released**.
Converts the Caliber field on every manufacturer tab (Hodgdon/Nosler/Speer/Sierra/Barnes/
Vihtavuori/Hornady/Lyman) from a free-text input + `<datalist>` autocomplete into a real `<select>`
restricted to calibers that actually have data uploaded. Already verified live against the running
dev server. Next step: push/PR/merge/release when the user gives the go-ahead (see `CLAUDE.md`'s
git workflow section — this repo gates push/PR/merge on an explicit ask each time).

### Production sync check
As of v1.26.0 (Vihtavuori added to Reloading Data Center), production has **not yet** received
this release. Once it's updated (`git pull` or `/admin/upgrade`), the 8 real Vihtavuori PDFs the
user already has (6.5 Creedmoor, 6.5 PRC, 270 Win, 7mm-08 Remington, 7mm Rem Mag, 30-06, 30-30, 308
Win) still need to be re-uploaded through `/admin/reload-data` there — that data only exists in the
dev DB, the parser code shipping via git doesn't bring the data with it.

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

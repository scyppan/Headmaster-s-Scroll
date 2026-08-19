# Canonical references in `world.json`

Large or shared records are stored once and linked by stable ID.

## Suite-wide normalization contract

This applies to every Headmaster's Scroll app and every canonical JSON file:

1. A domain object has exactly one canonical owner and one stable ID.
2. Relationships are stored as IDs or as their own relationship/event records;
   they do not copy the related object.
3. A record containing a stable ID must not also persist that object's name,
   title, description, author, image path, statistics, or other display fields.
   Readers resolve current display data through indexes and bounded caches.
4. Relationship-specific facts belong beside the relationship: dates, roles,
   quantities, ordering, per-person overrides, and provenance are valid there.
5. Runtime and campaign state are sparse overlays. Missing fields mean defaults;
   unchanged canonical records are never copied into campaign or session files.
6. Large one-owner sections may live in indexed side collections when that makes
   them independently lazy-loadable. Moving a unique blob without enabling
   targeted loading is not normalization and does not justify a migration.
7. Browser caches and local indexes may denormalize for speed, but they are
   disposable, revision-keyed, and never authoritative.
8. Every migration must support audit-only mode, verify hydrated before/after
   equivalence, create a recoverable backup, and be safe to run repeatedly.

- `events` owns complete world-event records. People keep `event_refs` and may
  keep only person-specific values in `event_overrides`.
- `books` owns complete book records and is edited only in World Builder.
  DBM supplies the spell, proficiency, recipe, and item definitions referenced
  by a book, but does not own or edit books.
- `book_readings` stores `person_id`, `book_id`, the reading date, source IDs,
  and reading-specific facts. Person names, book titles, and authors are
  resolved when displayed and are not copied into new records.
- Development-year book lists store `record_id` only. World Builder resolves
  the current title and author when it loads the selected person.
- School curriculum book assignments store only year, course, and the
  canonical World Builder `book` ID. Current titles are resolved for display.
- Book contents store typed catalog references rather than copied spell,
  proficiency, recipe, or item records.
- Reusable colored person tags live once in `person_tag_catalog`; people store
  `tag_ids`.
- Legacy import/reconciliation payloads live in `legacy_person_imports`;
  people store one `legacy_import_id`. They remain available to the relevant
  editor without inflating the basic person record.
- Campaign person state is a sparse overlay. An absent person or field means
  the documented default; only placements, wounds, inventory, visibility,
  equipment, notes, currency, battle markers, and other changed values are
  stored.
- Portraits, maps, covers, and item images remain external assets. JSON stores
  stable asset references and metadata, never encoded image data.

The compact World Builder index is disposable. It accelerates ID resolution
and selected-record loading but is never authoritative.

Use `python migrate_world_references.py` to audit the current files. Add
`--apply` only when intentionally migrating a legacy copy; applying creates
full timestamped backups before either canonical file is replaced.

The smaller follow-up normalizers use the same audit/apply convention:

- `migrate_campaign_overlays.py`
- `normalize_world_support_records.py`
- `normalize_database_references.py`

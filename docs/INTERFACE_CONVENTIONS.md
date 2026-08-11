# Headmaster's Scroll Interface Conventions

These are project-wide requirements for every current and future app.

## Selecting canonical records

Canonical data collections are large. A basic select box, combo box, or dropdown must not be used to choose a person, location, organization, item, event, spell, map, or another potentially large core-data record.

Use a separate chooser dialog that provides:

- Immediate text search across the record's useful names and stable record ID.
- A readable results list with enough context to distinguish similar records.
- A visible result count.
- Choose and Cancel actions, plus double-click selection.
- A flat, read-only field on the calling screen that shows the chosen record.

Dropdowns remain appropriate only for small fixed software enums, such as a region behavior, or a demonstrably small list already scoped by another record, such as floors within one selected building.

## Map reference canvas

Every map-authoring and map-playing surface uses a **3840 × 2960** reference canvas with a **48:37** aspect ratio. Applications may render a smaller working copy, but normalized coordinates and layout calculations must use that reference ratio.

Imported base maps are fitted into a 3840 × 2960 PNG without changing their aspect ratio. Any unused area is padded, ensuring that every stored base map and every application canvas has identical dimensions.

## Tool rails

Canvas manipulation tools belong in a thin vertical rail on the far left of the canvas. Tool rails should protect canvas space, use short labels or icons, and must not become a horizontal toolbar above the working area.

Mapper uses the following standard controls:

- `Ctrl` + mouse wheel: zoom around the cursor.
- Mouse wheel: pan vertically.
- `Alt` + mouse wheel: pan horizontally.
- `Ctrl` + `0`: fit the complete map in the canvas.
- `V`: Select tool.
- `P`: Polygon tool.

Geometry UI uses **nodes** and **lines**. A polygon closes by clicking its emphasized first node or first line, choosing **Close Poly**, pressing Enter, or double-clicking after at least three nodes.

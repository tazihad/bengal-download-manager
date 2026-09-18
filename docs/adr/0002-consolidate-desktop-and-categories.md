# 0002 Consolidate Desktop Integration and Categories Domain Module

Status: accepted

## Context
System integration calls (XDG Desktop Portals, D-Bus file manager discovery, autostart entries, and default file handlers) were historically accumulated in a 2,000-line monolithic `core.utils` module. Furthermore, file media categorization (`CATEGORY_EXTENSIONS`, `get_category_for_filename`) and temporal indicators were hosted inside `core.services.theme_service`, mixing domain categorization with UI theming.

## Decision
We establish:
1. `src/core/categories.py` as a dedicated domain module owning category definitions, file extension matching, size parsing, and relative duration formatters.
2. `src/core/desktop.py` as an integrated seam managing OS desktop capabilities (XDG Portals, D-Bus file manager, and autostart launchers).
`theme_service.py` and `utils.py` re-export these functions to preserve complete backward compatibility across existing call sites.

## Consequences
- Presentation and theming code no longer owns file category classification.
- Desktop portal interactions are isolated behind a cohesive desktop module.
- `utils.py` begins draining toward a clean deletion test.

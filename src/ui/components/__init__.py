"""
Bengal Download Manager - UI Components Package
===============================================
Decomposed UI widgets, delegates, event filters, and component controllers.
"""

from ui.components.table_view import (
    SortableTableWidgetItem,
    EmptyAreaClickFilter,
)
from ui.components.category_sidebar import (
    SidebarItemDelegate,
)
from ui.components.toolbar_manager import (
    ToolbarHoverFilter,
)

__all__ = [
    "SortableTableWidgetItem",
    "EmptyAreaClickFilter",
    "SidebarItemDelegate",
    "ToolbarHoverFilter",
]

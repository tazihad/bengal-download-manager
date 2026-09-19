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
from ui.components.data_usage_widget import (
    DataUsageWidget,
)

from ui.components.csd_titlebar import (
    CsdTitleBar,
    attach_csd,
    detach_csd,
)

__all__ = [
    "SortableTableWidgetItem",
    "EmptyAreaClickFilter",
    "SidebarItemDelegate",
    "ToolbarHoverFilter",
    "DataUsageWidget",
    "CsdTitleBar",
    "attach_csd",
    "detach_csd",
]


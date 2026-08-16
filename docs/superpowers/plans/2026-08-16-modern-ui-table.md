# Modern UI Table & Table Style Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement dynamic Table Style switching in Bengal Download Manager with an unmodified "Classic" 7-column mode and a "Modern" card-style mode featuring 2-line file cells and embedded progress bars.

**Architecture:** A presentation-layer extension keeping all underlying download table models, data roles, and worker signals intact. Introduce a custom `QStyledItemDelegate` for modern cell rendering and a `Table style` submenu under `View` in `MainWindow`.

**Tech Stack:** Python 3.13, PyQt6 (`QTableWidget`, `QStyledItemDelegate`, `QPainter`, `QActionGroup`), pytest-qt.

## Global Constraints
- Preserve existing data structures, download row logic, sorting, and worker integration completely.
- Table style selection must persist across app restarts in user config.
- Zero modifications to Classic mode appearance or behavior.

---

### Task 1: Create Modern Table Item Delegate

**Files:**
- Create: `src/ui/delegates/table_delegate.py`
- Create: `src/ui/delegates/__init__.py`
- Test: `tests/test_table_delegate.py`

**Interfaces:**
- Consumes: Qt item data roles (`Qt.ItemDataRole.DisplayRole`, `Qt.ItemDataRole.UserRole`, `Qt.ItemDataRole.DecorationRole`)
- Produces: `ModernTableDelegate` (`QStyledItemDelegate`) with customized `paint` and `sizeHint` for:
  - Column 0: 2-line title & category + icon.
  - Column 2: Status text with embedded progress bar for active downloads.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_table_delegate.py
import pytest
from PyQt6.QtCore import Qt, QRect, QModelIndex, QSize
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QStyleOptionViewItem
from ui.delegates.table_delegate import ModernTableDelegate

def test_modern_table_delegate_size_hint(qapp):
    table = QTableWidget(1, 6)
    delegate = ModernTableDelegate(table)
    opt = QStyleOptionViewItem()
    idx = table.model().index(0, 0)
    size = delegate.sizeHint(opt, idx)
    assert size.height() >= 44
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src venv/bin/pytest -v tests/test_table_delegate.py`
Expected: FAIL (ImportError / module not found)

- [ ] **Step 3: Implement ModernTableDelegate**

```python
# src/ui/delegates/table_delegate.py
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem, QStyleOptionProgressBar, QApplication
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QLinearGradient, QPen, QBrush

class ModernTableDelegate(QStyledItemDelegate):
    """Custom item delegate for the Modern table style."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.row_height = 48

    def sizeHint(self, option: QStyleOptionViewItem, index):
        size = super().sizeHint(option, index)
        return QSize(size.width(), self.row_height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw selection / hover background
        if option.state & QStyle.StateFlag.State_Selected:
            bg_color = option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.Highlight)
            painter.fillRect(option.rect, bg_color)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            hover_color = option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.Midlight)
            painter.fillRect(option.rect, hover_color)

        col = index.column()
        rect = option.rect.adjusted(8, 4, -8, -4)

        if col == 0:
            self._paint_name_cell(painter, option, index, rect)
        elif col == 2:
            self._paint_status_cell(painter, option, index, rect)
        else:
            self._paint_text_cell(painter, option, index, rect)

        painter.restore()

    def _paint_name_cell(self, painter: QPainter, option: QStyleOptionViewItem, index, rect: QRect):
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        category = index.data(Qt.ItemDataRole.UserRole + 3) or "General"

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        primary_color = QColor("#000000") if is_selected else option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.WindowText)
        sub_color = QColor("#333333") if is_selected else QColor("#888888")

        x_offset = rect.left()
        if icon:
            icon_rect = QRect(x_offset, rect.top() + (rect.height() - 24) // 2, 24, 24)
            icon.paint(painter, icon_rect)
            x_offset += 32

        # Primary filename (bold)
        font_primary = QFont(option.font)
        font_primary.setBold(True)
        font_primary.setPointSize(font_primary.pointSize())
        painter.setFont(font_primary)
        painter.setPen(primary_color)
        title_rect = QRect(x_offset, rect.top() + 2, rect.right() - x_offset, rect.height() // 2)
        metrics = painter.fontMetrics()
        elided_title = metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, title_rect.width())
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided_title)

        # Subtitle category
        font_sub = QFont(option.font)
        font_sub.setBold(False)
        font_sub.setPointSize(max(8, font_sub.pointSize() - 2))
        painter.setFont(font_sub)
        painter.setPen(sub_color)
        cat_rect = QRect(x_offset, rect.top() + rect.height() // 2, rect.right() - x_offset, rect.height() // 2 - 2)
        painter.drawText(cat_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, category)

    def _paint_status_cell(self, painter: QPainter, option: QStyleOptionViewItem, index, rect: QRect):
        status_text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        progress_val = index.data(Qt.ItemDataRole.UserRole)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # Text on top half
        text_rect = QRect(rect.left(), rect.top() + 2, rect.width(), rect.height() // 2)
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)

        if status_text in ("Complete", "Finished"):
            painter.setPen(QColor("#2ec27e"))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "Finished")
            return

        painter.setPen(QColor("#000000") if is_selected else option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.WindowText))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, status_text)

        # Mini progress bar on bottom half if progress value exists
        pct = 0.0
        if progress_val:
            try:
                pct = float(str(progress_val).replace("%", "").strip())
            except ValueError:
                pct = 0.0

        bar_rect = QRect(rect.left(), rect.top() + rect.height() // 2 + 4, rect.width(), 4)
        painter.setBrush(QColor("#252035"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_rect, 2, 2)

        if pct > 0:
            fill_width = int(bar_rect.width() * (min(100.0, pct) / 100.0))
            fill_rect = QRect(bar_rect.left(), bar_rect.top(), fill_width, bar_rect.height())
            grad = QLinearGradient(fill_rect.left(), 0, fill_rect.right(), 0)
            grad.setColorAt(0.0, QColor("#6366f1"))
            grad.setColorAt(1.0, QColor("#ec4899"))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(fill_rect, 2, 2)

    def _paint_text_cell(self, painter: QPainter, option: QStyleOptionViewItem, index, rect: QRect):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ""
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QColor("#000000") if is_selected else option.palette.color(option.palette.ColorGroup.Normal, option.palette.ColorRole.WindowText))
        font = QFont(option.font)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src venv/bin/pytest -v tests/test_table_delegate.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ui/delegates/ tests/test_table_delegate.py
git commit -m "feat(ui): add ModernTableDelegate for modern table layout"
```

---

### Task 2: Implement View -> Table Style Submenu & Table Switching in MainWindow

**Files:**
- Modify: `src/main.py`
- Test: `tests/test_table_styles.py`

**Interfaces:**
- Consumes: `ModernTableDelegate`, `QActionGroup`, `self.download_table`
- Produces: `MainWindow.set_table_style(style_name: str)`, `MainWindow.table_style` property, `View -> Table style` submenu actions.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_table_styles.py
import pytest
from main import MainWindow

def test_table_style_menu_and_switching(qapp):
    win = MainWindow(start_ipc=False)
    win.hide()
    
    assert hasattr(win, "action_table_style_classic")
    assert hasattr(win, "action_table_style_modern")
    assert win.action_table_style_classic.isCheckable()
    assert win.action_table_style_modern.isCheckable()

    # Default is classic
    assert win.table_style == "classic"
    assert win.action_table_style_classic.isChecked()

    # Switch to Modern
    win.set_table_style("modern")
    assert win.table_style == "modern"
    assert win.action_table_style_modern.isChecked()
    assert win.download_table.verticalHeader().defaultSectionSize() >= 44

    # Switch back to Classic
    win.set_table_style("classic")
    assert win.table_style == "classic"
    assert win.action_table_style_classic.isChecked()
    assert win.download_table.verticalHeader().defaultSectionSize() <= 32
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src venv/bin/pytest -v tests/test_table_styles.py`
Expected: FAIL (AttributeError: 'MainWindow' object has no attribute 'action_table_style_classic')

- [ ] **Step 3: Implement Table Style Actions and set_table_style in MainWindow**

In `src/main.py`:
- In `create_menus`:
  - Add `Table style` submenu to `view_menu`.
  - Create `self.action_table_style_classic` and `self.action_table_style_modern` within a `QActionGroup`.
  - Connect actions to `lambda checked, s="...": self.set_table_style(s) if checked else None`.
- In `MainWindow.__init__`:
  - Initialize `self.table_style = self.config.get("table_style", "classic")`.
  - Apply `self.set_table_style(self.table_style, initial=True)` on startup.
- Implement `set_table_style(self, style_name: str, initial=False)`:
  - Updates `self.table_style`.
  - Configures `download_table` item delegate (`ModernTableDelegate` or default `QStyledItemDelegate`).
  - Sets row height / section size (48px for modern, 26px for classic).
  - Updates column configurations & headers if appropriate.
  - Saves `table_style` in `self.config` and calls `self.save_config()`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src venv/bin/pytest -v tests/test_table_styles.py`
Expected: PASS

- [ ] **Step 5: Run full project test suite**

Run: `PYTHONPATH=src venv/bin/pytest -v tests/`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/main.py tests/test_table_styles.py
git commit -m "feat(ui): implement Table Style switcher in View menu with Classic and Modern modes"
```

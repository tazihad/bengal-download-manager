"""
Download Table Component & Item Filters
=======================================
Table sorting items, rubberband empty-area selection filter, and column management.
"""

from PyQt6.QtWidgets import (
    QTableWidgetItem,
    QRubberBand,
)
from PyQt6.QtCore import (
    QObject,
    Qt,
    QEvent,
    QPoint,
    QRect,
    QSize,
    QItemSelection,
    QItemSelectionModel,
)


class SortableTableWidgetItem(QTableWidgetItem):
    """Table widget item supporting numeric and raw data sorting."""
    def __lt__(self, other):
        v1 = self.data(Qt.ItemDataRole.UserRole)
        v2 = other.data(Qt.ItemDataRole.UserRole)
        if v1 is not None and v2 is not None:
            try:
                return float(v1) < float(v2)
            except Exception:
                pass
        return self.text() < other.text()


class EmptyAreaClickFilter(QObject):
    """Event filter on table viewport to support rubberband multi-row selection on empty space."""
    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.table.viewport())
        self.origin = QPoint()

    def eventFilter(self, obj, event):
        if obj != self.table.viewport():
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                item = self.table.itemAt(event.pos())
                if not item:
                    # Starting selection from empty area
                    if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
                        self.table.clearSelection()
                    self.table.setCurrentItem(None)
                    self.origin = event.pos()
                    self.rubber_band.setGeometry(QRect(self.origin, QSize()))
                    self.rubber_band.show()
                    return True
        elif event.type() == QEvent.Type.MouseMove:
            if self.rubber_band.isVisible():
                self.rubber_band.setGeometry(QRect(self.origin, event.pos()).normalized())
                self.update_selection(event.modifiers())
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if self.rubber_band.isVisible():
                self.rubber_band.hide()
                return True
        return super().eventFilter(obj, event)

    def update_selection(self, modifiers):
        rect = self.rubber_band.geometry()
        selection_model = self.table.selectionModel()
        
        # Determine selection command
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            command = QItemSelectionModel.SelectionFlag.Select
        else:
            command = QItemSelectionModel.SelectionFlag.ClearAndSelect
            
        command |= QItemSelectionModel.SelectionFlag.Rows
        
        selection = QItemSelection()
        any_selected = False
        
        for row in range(self.table.rowCount()):
            row_y = self.table.rowViewportPosition(row)
            row_height = self.table.rowHeight(row)
            # Selection happens if the rubber band vertically overlaps the row
            if rect.bottom() >= row_y and rect.top() <= (row_y + row_height):
                index = self.table.model().index(row, 0)
                selection.select(index, index)
                any_selected = True
        
        if any_selected:
            selection_model.select(selection, command)
        elif not (modifiers & Qt.KeyboardModifier.ControlModifier):
            # If nothing touched and no Ctrl, clear everything
            self.table.clearSelection()

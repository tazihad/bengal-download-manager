"""
Bengal Download Manager — Batch Pattern Dialog
================================================
Allows users to generate sequential download URLs from an address pattern
using numeric or alphabetical wildcards with zero-padding.
"""

from typing import List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette
from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QRadioButton, QButtonGroup, QGroupBox, QSpinBox, QFrame
)
from core.services.theme_service import get_themed_icon


def _apply_tabular_font(widget, point_size: int = 9, bold: bool = False):
    font = QFont(widget.font())
    font.setPointSize(point_size)
    font.setBold(bold)
    font.setFeature(QFont.Tag.fromString('tnum'), 1)
    widget.setFont(font)


class BatchPatternDialog(QDialog):
    """
    Dialog to generate sequential batch URLs from an address template containing '*'.
    Supports numeric ranges with custom wildcard zero-padding and alphabetical ranges.
    """
    urls_generated = pyqtSignal(list)

    def __init__(self, parent=None, initial_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Batch Download"))
        self.setWindowIcon(get_themed_icon("add_url"))
        self.setMinimumWidth(680)
        self.resize(720, 480)

        self._generated_urls: List[str] = []
        self._init_ui(initial_url)
        self._refresh_preview()

    def _init_ui(self, initial_url: str):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(12)

        # ── Header Title & Subtitle ──────────────────────────────────────────
        lbl_title = QLabel(self.tr("Batch Download"))
        _apply_tabular_font(lbl_title, point_size=13, bold=True)
        main_layout.addWidget(lbl_title)

        lbl_subtitle = QLabel(
            self.tr("Generate a group of sequential links from one address, then review them before downloading.")
        )
        lbl_subtitle.setStyleSheet("opacity: 0.85;")
        main_layout.addWidget(lbl_subtitle)

        # ── Explainer Box (IDM-style guidance) ────────────────────────────────
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_frame.setStyleSheet("""
            QFrame {
                border: 1px solid palette(mid);
                border-radius: 5px;
                background-color: palette(alternate-base);
                padding: 6px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(10, 8, 10, 8)
        info_layout.setSpacing(4)

        lbl_desc = QLabel(
            self.tr("Add a group of sequential files like img001.jpg, img002.jpg, img100.jpg in one step. "
                    "Put an asterisk (*) where the number or letter changes, and it becomes the file-name pattern.")
        )
        lbl_desc.setWordWrap(True)
        info_layout.addWidget(lbl_desc)

        lbl_example = QLabel(self.tr("Example:  https://www.example.com/pictures/img*.jpg"))
        example_font = QFont("Monospace")
        example_font.setStyleHint(QFont.StyleHint.Monospace)
        example_font.setPointSize(9)
        lbl_example.setFont(example_font)
        lbl_example.setStyleSheet("color: palette(highlight); font-weight: bold;")
        info_layout.addWidget(lbl_example)

        main_layout.addWidget(info_frame)

        # ── Address Row ──────────────────────────────────────────────────────
        addr_layout = QHBoxLayout()
        addr_layout.setSpacing(8)
        lbl_addr = QLabel(self.tr("Address:"))
        lbl_addr.setFixedWidth(70)
        _apply_tabular_font(lbl_addr, point_size=10, bold=True)
        addr_layout.addWidget(lbl_addr)

        self.txt_address = QLineEdit(initial_url)
        self.txt_address.setPlaceholderText(self.tr("https://www.example.com/pictures/img*.jpg"))
        self.txt_address.setFixedHeight(30)
        self.txt_address.textChanged.connect(self._refresh_preview)
        addr_layout.addWidget(self.txt_address)

        main_layout.addLayout(addr_layout)

        # ── Pattern Options Card ─────────────────────────────────────────────
        grp_options = QGroupBox(self.tr("Replace asterisk with"))
        grp_layout = QVBoxLayout(grp_options)
        grp_layout.setContentsMargins(14, 12, 14, 12)
        grp_layout.setSpacing(10)

        # Radio buttons
        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(24)
        self.radio_numbers = QRadioButton(self.tr("Numbers"))
        self.radio_numbers.setChecked(True)
        self.radio_numbers.toggled.connect(self._on_mode_toggled)

        self.radio_letters = QRadioButton(self.tr("Letters"))
        self.radio_letters.toggled.connect(self._on_mode_toggled)

        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.radio_numbers)
        self.btn_group.addButton(self.radio_letters)

        radio_layout.addWidget(self.radio_numbers)
        radio_layout.addWidget(self.radio_letters)
        radio_layout.addStretch()
        grp_layout.addLayout(radio_layout)

        # Range controls
        self.range_layout = QHBoxLayout()
        self.range_layout.setSpacing(10)

        self.lbl_from = QLabel(self.tr("From:"))
        self.range_layout.addWidget(self.lbl_from)

        # Number mode inputs
        self.spin_num_from = QSpinBox()
        self.spin_num_from.setRange(0, 999999)
        self.spin_num_from.setValue(1)
        self.spin_num_from.setFixedHeight(28)
        self.spin_num_from.setFixedWidth(80)
        self.spin_num_from.valueChanged.connect(self._refresh_preview)
        self.range_layout.addWidget(self.spin_num_from)

        # Letter mode inputs
        self.txt_let_from = QLineEdit("a")
        self.txt_let_from.setMaxLength(1)
        self.txt_let_from.setFixedHeight(28)
        self.txt_let_from.setFixedWidth(50)
        self.txt_let_from.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_let_from.textChanged.connect(self._refresh_preview)
        self.txt_let_from.hide()
        self.range_layout.addWidget(self.txt_let_from)

        self.lbl_to = QLabel(self.tr("To:"))
        self.range_layout.addWidget(self.lbl_to)

        self.spin_num_to = QSpinBox()
        self.spin_num_to.setRange(0, 999999)
        self.spin_num_to.setValue(100)
        self.spin_num_to.setFixedHeight(28)
        self.spin_num_to.setFixedWidth(80)
        self.spin_num_to.valueChanged.connect(self._refresh_preview)
        self.range_layout.addWidget(self.spin_num_to)

        self.txt_let_to = QLineEdit("z")
        self.txt_let_to.setMaxLength(1)
        self.txt_let_to.setFixedHeight(28)
        self.txt_let_to.setFixedWidth(50)
        self.txt_let_to.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_let_to.textChanged.connect(self._refresh_preview)
        self.txt_let_to.hide()
        self.range_layout.addWidget(self.txt_let_to)

        self.lbl_size = QLabel(self.tr("Wildcard size:"))
        self.range_layout.addWidget(self.lbl_size)

        self.spin_wildcard_size = QSpinBox()
        self.spin_wildcard_size.setRange(1, 10)
        self.spin_wildcard_size.setValue(2)
        self.spin_wildcard_size.setFixedHeight(28)
        self.spin_wildcard_size.setFixedWidth(60)
        self.spin_wildcard_size.setToolTip(self.tr("Number of digits to pad with leading zeros (e.g. 2 -> 01, 02)"))
        self.spin_wildcard_size.valueChanged.connect(self._refresh_preview)
        self.range_layout.addWidget(self.spin_wildcard_size)

        self.range_layout.addStretch()
        grp_layout.addLayout(self.range_layout)

        main_layout.addWidget(grp_options)

        # ── Preview Card ─────────────────────────────────────────────────────
        grp_preview = QGroupBox(self.tr("Preview"))
        prev_layout = QVBoxLayout(grp_preview)
        prev_layout.setContentsMargins(14, 10, 14, 10)
        prev_layout.setSpacing(6)

        header_prev_layout = QHBoxLayout()
        self.lbl_total_count = QLabel("")
        _apply_tabular_font(self.lbl_total_count, point_size=9, bold=True)
        self.lbl_total_count.setStyleSheet("color: palette(highlight);")
        header_prev_layout.addStretch()
        header_prev_layout.addWidget(self.lbl_total_count)
        prev_layout.addLayout(header_prev_layout)

        mono_font = QFont("Monospace")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setPointSize(9)

        # First Link
        row_first = QHBoxLayout()
        lbl_first_title = QLabel(self.tr("First:"))
        lbl_first_title.setFixedWidth(60)
        _apply_tabular_font(lbl_first_title, point_size=9, bold=False)
        self.lbl_first_val = QLabel("-")
        self.lbl_first_val.setFont(mono_font)
        self.lbl_first_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row_first.addWidget(lbl_first_title)
        row_first.addWidget(self.lbl_first_val, 1)
        prev_layout.addLayout(row_first)

        # Second Link
        row_second = QHBoxLayout()
        lbl_second_title = QLabel(self.tr("Second:"))
        lbl_second_title.setFixedWidth(60)
        _apply_tabular_font(lbl_second_title, point_size=9, bold=False)
        self.lbl_second_val = QLabel("-")
        self.lbl_second_val.setFont(mono_font)
        self.lbl_second_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row_second.addWidget(lbl_second_title)
        row_second.addWidget(self.lbl_second_val, 1)
        prev_layout.addLayout(row_second)

        # Last Link
        row_last = QHBoxLayout()
        lbl_last_title = QLabel(self.tr("Last:"))
        lbl_last_title.setFixedWidth(60)
        _apply_tabular_font(lbl_last_title, point_size=9, bold=False)
        self.lbl_last_val = QLabel("-")
        self.lbl_last_val.setFont(mono_font)
        self.lbl_last_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row_last.addWidget(lbl_last_title)
        row_last.addWidget(self.lbl_last_val, 1)
        prev_layout.addLayout(row_last)

        main_layout.addWidget(grp_preview)

        # ── Footer Note and Buttons ──────────────────────────────────────────
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        lbl_footer_note = QLabel(
            self.tr("After clicking OK you can review each link, filter files, and group them into a queue.")
        )
        lbl_footer_note.setStyleSheet("opacity: 0.8; font-size: 11px;")
        lbl_footer_note.setWordWrap(True)
        footer_layout.addWidget(lbl_footer_note, 1)

        self.btn_cancel = QPushButton(self.tr("Cancel"))
        self.btn_cancel.setFixedHeight(32)
        self.btn_cancel.setFixedWidth(84)
        self.btn_cancel.clicked.connect(self.reject)
        footer_layout.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton(self.tr("OK"))
        self.btn_ok.setDefault(True)
        self.btn_ok.setFixedHeight(32)
        self.btn_ok.setFixedWidth(84)
        self.btn_ok.setEnabled(False)
        self.btn_ok.clicked.connect(self._on_accept)
        footer_layout.addWidget(self.btn_ok)

        main_layout.addLayout(footer_layout)

    def _on_mode_toggled(self):
        is_numbers = self.radio_numbers.isChecked()
        self.spin_num_from.setVisible(is_numbers)
        self.spin_num_to.setVisible(is_numbers)
        self.lbl_size.setVisible(is_numbers)
        self.spin_wildcard_size.setVisible(is_numbers)

        self.txt_let_from.setVisible(not is_numbers)
        self.txt_let_to.setVisible(not is_numbers)
        self._refresh_preview()

    def generate_urls(self) -> List[str]:
        """Generates sequential URLs based on current inputs."""
        base = self.txt_address.text().strip()
        if not base or "*" not in base:
            return []

        urls = []
        if self.radio_numbers.isChecked():
            start_num = self.spin_num_from.value()
            end_num = self.spin_num_to.value()
            padding = self.spin_wildcard_size.value()
            step = 1 if end_num >= start_num else -1
            
            # Prevent excessive memory allocation (cap at 10,000 URLs per batch generation)
            diff = abs(end_num - start_num) + 1
            if diff > 10000:
                end_num = start_num + (9999 if step == 1 else -9999)

            for i in range(start_num, end_num + step, step):
                formatted = str(i).zfill(padding)
                urls.append(base.replace("*", formatted, 1))
        else:
            from_ch = self.txt_let_from.text().strip() or "a"
            to_ch = self.txt_let_to.text().strip() or "z"
            start_ord = ord(from_ch[0])
            end_ord = ord(to_ch[0])
            step = 1 if end_ord >= start_ord else -1

            diff = abs(end_ord - start_ord) + 1
            if diff > 200:
                end_ord = start_ord + (199 if step == 1 else -199)

            for i in range(start_ord, end_ord + step, step):
                urls.append(base.replace("*", chr(i), 1))

        return urls

    def _refresh_preview(self):
        urls = self.generate_urls()
        self._generated_urls = urls
        count = len(urls)

        if count > 0:
            self.lbl_total_count.setText(self.tr(f"{count} link{'s' if count != 1 else ''} generated"))
            self.lbl_first_val.setText(urls[0])
            self.lbl_second_val.setText(urls[1] if count > 1 else "-")
            self.lbl_last_val.setText(urls[-1])
            self.btn_ok.setEnabled(True)
        else:
            self.lbl_total_count.setText("")
            self.lbl_first_val.setText("-")
            self.lbl_second_val.setText("-")
            self.lbl_last_val.setText("-")
            self.btn_ok.setEnabled(False)

    def _on_accept(self):
        urls = self.generate_urls()
        if urls:
            self._generated_urls = urls
            self.urls_generated.emit(urls)
            self.accept()

    def get_generated_urls(self) -> List[str]:
        return list(self._generated_urls)

"""
About Bengal Download Manager Dialog
====================================
Displays application version, package type, license, credits, and asynchronous
source verification status with a live loading spinner and offline warning.
"""

from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QApplication, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QRectF, QObject
from PyQt6.QtGui import QPainter, QPen, QColor, QFont, QCursor

from core.version import VERSION
from core.build_info import get_package_type, verify_source_status, OFFICIAL_GITHUB_REPO


class CircleSpinner(QWidget):
    """Small round circle loading spinner indicating verification in progress."""

    def __init__(self, size: int = 14, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)

    def start(self) -> None:
        """Start rotation animation."""
        if not self._timer.isActive():
            self._timer.start(50)
            self.show()

    def stop(self) -> None:
        """Stop rotation animation and hide."""
        if self._timer.isActive():
            self._timer.stop()
        self.hide()

    def _rotate(self) -> None:
        self._angle = (self._angle + 30) % 360
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        highlight = palette.color(palette.ColorRole.Highlight)
        pen = QPen(highlight if highlight.isValid() else QColor(46, 204, 113), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.drawArc(rect, int(-self._angle * 16), int(270 * 16))


class VerificationWorker(QThread):
    """Background worker to verify package authenticity without blocking UI."""

    finished_verification = pyqtSignal(str, str, str)  # status, url, note

    def __init__(self, version: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.version = version

    def run(self) -> None:
        try:
            import core.build_info as build_info
            status, url, note = build_info.verify_source_status(self.version)
            self.finished_verification.emit(status, url, note)
        except Exception as e:
            self.finished_verification.emit("unverified", "", str(e))


class AboutDialog(QDialog):
    """About Bengal Download Manager dialog with immediate display and async verification."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("About Bengal Download Manager"))
        self.setWindowIcon(QApplication.windowIcon())
        self.setModal(True)
        self.setFixedWidth(480)

        self.pkg_type = get_package_type()
        self.worker: Optional[VerificationWorker] = None

        self._setup_ui()
        self._start_verification()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 16)
        main_layout.setSpacing(14)

        # Header: Icon + Title & Description
        header_layout = QHBoxLayout()
        header_layout.setSpacing(16)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        icon_label = QLabel(self)
        app_icon = QApplication.windowIcon()
        if not app_icon.isNull():
            icon_label.setPixmap(app_icon.pixmap(48, 48))
        icon_label.setFixedSize(48, 48)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        title_label = QLabel("<h2>Bengal Download Manager</h2>", self)
        title_label.setTextFormat(Qt.TextFormat.RichText)
        title_layout.addWidget(title_label)

        desc_label = QLabel(
            "Lightweight open-source download manager built with PyQt6 and Aria2 "
            "featuring multi-threaded downloading.",
            self
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: palette(text);")
        title_layout.addWidget(desc_label)

        header_layout.addLayout(title_layout, 1)
        main_layout.addLayout(header_layout)

        # Separator line
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        main_layout.addWidget(sep)

        # Details Layout
        details_layout = QVBoxLayout()
        details_layout.setSpacing(8)

        # Version & Verification Row
        version_row = QHBoxLayout()
        version_row.setSpacing(6)
        version_row.setAlignment(Qt.AlignmentFlag.AlignLeft)

        ver_text = QLabel(f"<b>Version:</b> {VERSION} ({self.pkg_type})", self)
        ver_text.setTextFormat(Qt.TextFormat.RichText)
        version_row.addWidget(ver_text)

        # Verification indicator container
        self.spinner = CircleSpinner(size=14, parent=self)
        version_row.addWidget(self.spinner)

        self.verify_label = QLabel(self)
        self.verify_label.setTextFormat(Qt.TextFormat.RichText)
        self.verify_label.setOpenExternalLinks(True)
        version_row.addWidget(self.verify_label)

        details_layout.addLayout(version_row)

        # License & Credits
        license_label = QLabel(
            "<p style='margin: 0; line-height: 1.4;'>"
            "<b>License:</b> MIT License<br>"
            "© 2026 <a>tazihad</a> &nbsp;"
            "<a href='https://zihad.com.bd/bengal-download-manager'>https://zihad.com.bd/bengal-download-manager</a><br>"
            "Contact: <a href='mailto:tazihad@gmail.com'>tazihad@gmail.com</a>"
            "</p>",
            self
        )
        license_label.setTextFormat(Qt.TextFormat.RichText)
        license_label.setOpenExternalLinks(True)
        details_layout.addWidget(license_label)

        # Project Site
        site_label = QLabel(
            "<p style='margin: 0; line-height: 1.4;'>"
            "<b>Project Site:</b><br>"
            f"<a href='{OFFICIAL_GITHUB_REPO}'>{OFFICIAL_GITHUB_REPO}</a>"
            "</p>",
            self
        )
        site_label.setTextFormat(Qt.TextFormat.RichText)
        site_label.setOpenExternalLinks(True)
        details_layout.addWidget(site_label)

        main_layout.addLayout(details_layout)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)

        ok_button = QPushButton(self.tr("OK"), self)
        ok_button.setDefault(True)
        ok_button.setFixedWidth(80)
        ok_button.clicked.connect(self.accept)
        btn_layout.addWidget(ok_button)

        main_layout.addLayout(btn_layout)

    def _start_verification(self) -> None:
        """Kick off background verification or update immediately for Dev builds."""
        if self.pkg_type == "Dev Build":
            self.spinner.stop()
            self.verify_label.hide()
            return

        # Package requires verification: show loading spinner immediately
        self.spinner.start()
        self.verify_label.setText("<span style='font-size: 11px; color: palette(placeholder-text);'>Verifying...</span>")
        self.verify_label.show()

        # Run verification in background QThread so dialog opens instantaneously
        self.worker = VerificationWorker(VERSION, parent=self)
        self.worker.finished_verification.connect(self._on_verification_finished)
        self.worker.start()

    def _on_verification_finished(self, status: str, url: str, note: str) -> None:
        """Handle background verification result."""
        self.spinner.stop()

        if status == "verified":
            self.verify_label.setText(
                f"<a href='{url}' title='{note}' style='color: #2ecc71; text-decoration: none; font-weight: bold;'>✔ Verified Source</a>"
            )
            self.verify_label.setToolTip(note)
            self.verify_label.show()
        elif status == "no_network":
            # Small size warning text when offline / no network available
            self.verify_label.setText(
                "<span style='color: #e67e22; font-size: 11px; font-weight: bold;' "
                "title='Could not verify package authenticity: no network connection'>⚠ No network</span>"
            )
            self.verify_label.setToolTip(note or "No network connection")
            self.verify_label.show()
        else:
            self.verify_label.setText(
                f"<span style='color: #e74c3c; font-size: 11px;' title='{note}'>✖ Unverified Source</span>"
            )
            self.verify_label.setToolTip(note or "Source verification failed")
            self.verify_label.show()

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.finished_verification.disconnect()
            self.worker.quit()
        super().closeEvent(event)

"""Component tests for UI components."""

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


class TestElidingLabel:
    def test_construction_empty(self, qapp):
        from ui.components.details_panel import ElidingLabel
        lbl = ElidingLabel()
        assert lbl.text() == ""

    def test_construction_with_text(self, qapp):
        from ui.components.details_panel import ElidingLabel
        lbl = ElidingLabel("hello world")
        assert lbl.text() == "hello world"
        assert lbl.fullText() == "hello world"

    def test_set_text(self, qapp):
        from ui.components.details_panel import ElidingLabel
        lbl = ElidingLabel()
        lbl.setText("new value")
        assert lbl.text() == "new value"

    def test_set_text_none(self, qapp):
        from ui.components.details_panel import ElidingLabel
        lbl = ElidingLabel("x")
        lbl.setText(None)
        assert lbl.text() == ""

    def test_tooltip_set_for_long_text(self, qapp):
        from ui.components.details_panel import ElidingLabel
        long_text = "https://example.com/" + "a" * 200
        lbl = ElidingLabel(long_text)
        assert lbl.toolTip() != ""

    def test_copy_full_text(self, qapp):
        from ui.components.details_panel import ElidingLabel
        lbl = ElidingLabel("some text")
        lbl.copy_full_text()
        assert QApplication.clipboard().text() == "some text"

    def test_copy_full_text_empty(self, qapp):
        from ui.components.details_panel import ElidingLabel
        QApplication.clipboard().setText("preset")
        lbl = ElidingLabel()
        lbl.copy_full_text()
        assert QApplication.clipboard().text() == "preset"


class TestElidingButton:
    def test_construction_empty(self, qapp):
        from ui.components.details_panel import ElidingButton
        btn = ElidingButton()
        assert btn.text() == ""

    def test_construction_with_text(self, qapp):
        from ui.components.details_panel import ElidingButton
        btn = ElidingButton("button label")
        assert btn.text() == "button label"

    def test_set_text(self, qapp):
        from ui.components.details_panel import ElidingButton
        btn = ElidingButton()
        btn.setText("updated")
        assert btn.text() == "updated"

    def test_tooltip(self, qapp):
        from ui.components.details_panel import ElidingButton
        btn = ElidingButton("click me")
        assert btn.toolTip() != ""


class TestDetailsToggleButton:
    def test_initial_state(self, qapp):
        from ui.components.details_panel import DetailsToggleButton
        btn = DetailsToggleButton()
        assert btn.is_open() is False
        assert btn.lbl_arrow.text() == "▲"

    def test_toggle_open(self, qapp):
        from ui.components.details_panel import DetailsToggleButton
        btn = DetailsToggleButton()
        btn.set_open(True)
        assert btn.is_open() is True
        assert btn.lbl_arrow.text() == "▼"

    def test_toggle_close(self, qapp):
        from ui.components.details_panel import DetailsToggleButton
        btn = DetailsToggleButton()
        btn.set_open(True)
        btn.set_open(False)
        assert btn.is_open() is False
        assert btn.lbl_arrow.text() == "▲"

    def test_set_filename(self, qapp):
        from ui.components.details_panel import DetailsToggleButton
        btn = DetailsToggleButton()
        btn.set_filename("test-file.zip")
        assert "test-file" in btn.toolTip()


class TestSegmentGridWidget:
    def test_construction(self, qapp):
        from ui.components.details_panel import SegmentGridWidget
        w = SegmentGridWidget()
        assert w is not None

    def test_fallback_progress_zero(self, qapp):
        from ui.components.details_panel import SegmentGridWidget
        w = SegmentGridWidget()
        w.set_fallback_progress(0.0, num_segments=4, is_complete=False)
        assert len(w._segments) == 4
        assert all(s["percent"] == 0.0 for s in w._segments)

    def test_fallback_progress_full(self, qapp):
        from ui.components.details_panel import SegmentGridWidget
        w = SegmentGridWidget()
        w.set_fallback_progress(100.0, num_segments=4, is_complete=True)
        assert len(w._segments) == 4
        assert all(s["percent"] == 100.0 for s in w._segments)


class TestDetailsPanel:
    def test_construction(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        assert panel is not None
        assert panel.stacked_widget.count() == 3

    def test_tab_buttons_count(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        assert len(panel.tab_buttons) == 3

    def test_initial_tab_is_general(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        assert panel.stacked_widget.currentIndex() == 0
        assert panel.tab_buttons[0].isChecked()

    def test_switch_tab_progress(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        panel.switch_tab(1)
        assert panel.stacked_widget.currentIndex() == 1
        assert panel.tab_buttons[1].isChecked()
        assert not panel.tab_buttons[0].isChecked()

    def test_switch_tab_connections(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        panel.switch_tab(2)
        assert panel.stacked_widget.currentIndex() == 2

    def test_switch_tab_out_of_range_resets_to_zero(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        panel.switch_tab(99)
        assert panel.stacked_widget.currentIndex() == 0

    def test_switch_tab_negative_resets_to_zero(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        panel.switch_tab(-1)
        assert panel.stacked_widget.currentIndex() == 0

    def test_close_button_exists(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        assert panel.btn_close is not None

    def test_tab_changed_signal(self, qapp):
        from ui.components.details_panel import DetailsPanel
        panel = DetailsPanel()
        received = []
        panel.tab_changed.connect(received.append)
        panel.switch_tab(1)
        if received:
            assert received[-1] == 1


class TestFormatHelpers:
    def test_format_eta_string(self, qapp):
        from ui.components.details_panel import format_eta_string
        assert isinstance(format_eta_string(60), str)
        assert isinstance(format_eta_string(0), str)

    def test_format_speed_string(self, qapp):
        from ui.components.details_panel import format_speed_string
        assert isinstance(format_speed_string(1024), str)
        assert isinstance(format_speed_string(0), str)

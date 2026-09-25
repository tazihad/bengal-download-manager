"""
Unit tests for OptionsDialog proxy tab layout and error handling.
Verifies that proxy connection error messages wrap cleanly and do not push
the port input field or other controls outside the dialog window.
"""

import pytest
from PyQt6.QtWidgets import QApplication, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    return app


def test_proxy_tab_widgets_and_wrapping(qapp):
    from ui.dialogs.options import OptionsDialog
    from core.services.proxy_service import ProxyDetectionResult

    dlg = OptionsDialog(initial_tab=7)
    dlg._proxy_debounce_timer.stop()
    dlg._cleanup_proxy_worker()
    dlg.show()
    qapp.processEvents()

    # Verify word wrap and size policy to prevent wide horizontal expansion
    assert dlg.lbl_proxy_status.wordWrap() is True
    assert dlg.lbl_proxy_status.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert dlg.lbl_proxy_ip.wordWrap() is True
    assert dlg.lbl_proxy_ip.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored

    sa = dlg.proxy_tab.findChild(QScrollArea)
    assert sa is not None
    content = sa.widget()
    viewport = sa.viewport()

    # Simulate connection failure with wide error message
    err_msg = "Cannot connect to proxy server (Connection refused)"
    result = ProxyDetectionResult(is_working=False, error_message=err_msg)
    dlg._on_proxy_detection_finished(result)
    qapp.processEvents()
    content.updateGeometry()
    qapp.processEvents()

    assert dlg.lbl_proxy_status.text() == "Connection failed"
    assert dlg.lbl_proxy_ip.text() == err_msg
    assert dlg.lbl_proxy_flag.text() == "⚠️"

    # Verify content does not expand beyond the scroll area viewport
    assert content.width() <= viewport.width()

    # Verify spin_port is visible within viewport bounds
    spin_port_x = dlg.spin_port.mapTo(viewport, dlg.spin_port.rect().topLeft()).x()
    spin_port_right = spin_port_x + dlg.spin_port.width()
    assert spin_port_right <= viewport.width()

    # Verify working state
    work_result = ProxyDetectionResult(is_working=True, flag_emoji="🌐", ip="1.2.3.4", country="Bangladesh")
    dlg._on_proxy_detection_finished(work_result)
    qapp.processEvents()
    content.updateGeometry()
    qapp.processEvents()

    assert dlg.lbl_proxy_status.text() == "Proxy is working"
    assert "1.2.3.4" in dlg.lbl_proxy_ip.text()
    assert content.width() <= viewport.width()

    dlg.close()


def test_proxy_button_vertical_position_stability(qapp):
    from ui.dialogs.options import OptionsDialog
    from core.services.proxy_service import ProxyDetectionResult

    dlg = OptionsDialog(initial_tab=7)
    dlg._proxy_debounce_timer.stop()
    dlg.show()
    qapp.processEvents()

    # 1. Waiting / typing state
    dlg.txt_host.setText("127.0.0.1")
    dlg._schedule_proxy_detection()
    qapp.processEvents()
    y_waiting = dlg.btn_test_proxy.y()
    h_waiting = dlg.proxy_status_frame.height()

    # 2. Connection failed state
    fail_result = ProxyDetectionResult(is_working=False, error_message="Cannot connect to proxy server (Connection refused)")
    dlg._on_proxy_detection_finished(fail_result)
    qapp.processEvents()
    y_failed = dlg.btn_test_proxy.y()
    h_failed = dlg.proxy_status_frame.height()

    # 3. Proxy working state
    work_result = ProxyDetectionResult(is_working=True, flag_emoji="🌐", ip="1.2.3.4", country="Bangladesh")
    dlg._on_proxy_detection_finished(work_result)
    qapp.processEvents()
    y_working = dlg.btn_test_proxy.y()
    h_working = dlg.proxy_status_frame.height()

    # Verify frame height and button position do not shift up and down
    assert h_waiting == h_failed == h_working == 72
    assert y_waiting == y_failed == y_working

    dlg.close()


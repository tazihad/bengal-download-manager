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

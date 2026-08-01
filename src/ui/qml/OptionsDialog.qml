import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Dialog {
    id: optionsDlg
    title: "Bengal DM Options"
    padding: Kirigami.Units.gridUnit
    standardButtons: Controls.Dialog.Close

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing
        implicitWidth: Kirigami.Units.gridUnit * 26

        Kirigami.FormLayout {
            Layout.fillWidth: true

            Controls.CheckBox {
                id: chkAutoStart
                Kirigami.FormData.label: "Startup:"
                text: "Launch Bengal Download Manager on System Startup"
                checked: true
            }

            Controls.SpinBox {
                id: spinConn
                Kirigami.FormData.label: "Max Connections per File:"
                from: 1
                to: 32
                value: 8
            }

            Controls.SpinBox {
                id: spinMaxDl
                Kirigami.FormData.label: "Max Concurrent Downloads:"
                from: 1
                to: 10
                value: 4
            }

            Controls.TextField {
                id: txtDefaultDir
                Kirigami.FormData.label: "Default Downloads Directory:"
                placeholderText: "~/Downloads"
                Layout.fillWidth: true
            }
        }
    }
}

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

            Controls.ComboBox {
                id: comboTheme
                Kirigami.FormData.label: "Theme:"
                model: ["Automatic", "BDM Light", "BDM Dark", "Ubuntu Light", "Ubuntu Dark", "IDM Classic", "Kirigami Light", "Kirigami Dark", "Breeze Light", "Breeze Dark", "Dracula", "Nord", "One Dark", "Catppuccin", "Solarized Light", "Solarized Dark"]
                currentIndex: 0
                Layout.fillWidth: true
            }

            Controls.ComboBox {
                id: comboAccent
                Kirigami.FormData.label: "Accent Color:"
                model: ["BDM", "Breeze Blue", "Ubuntu Orange", "Windows Blue", "Dracula Purple", "Nord Frost", "Emerald Green", "Crimson Red", "Amethyst Violet"]
                currentIndex: 0
                Layout.fillWidth: true
            }

            Controls.ComboBox {
                id: comboIconTheme
                Kirigami.FormData.label: "Toolbar Icons:"
                model: ["BDM", "Breeze", "Breeze Dark", "Ubuntu", "Adwaita", "HighColor"]
                currentIndex: 0
                Layout.fillWidth: true
            }

            Controls.CheckBox {
                id: chkAutoStart
                Kirigami.FormData.label: "Startup:"
                text: "Launch Bengal Download Manager on System Startup"
                checked: true
            }

            Controls.SpinBox {
                id: spinMaxDl
                Kirigami.FormData.label: "Max Concurrent Downloads:"
                from: 1
                to: 10
                value: 4
            }

            Controls.ComboBox {
                id: comboScale
                Kirigami.FormData.label: "Scale:"
                model: ["50%", "75%", "90%", "100%", "110%", "115%", "125%", "135%", "150%", "175%", "200%", "225%", "250%", "275%", "300%"]
                currentIndex: 3
                Layout.fillWidth: true
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

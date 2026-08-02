import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Dialog {
    id: dialog
    title: "Add New Download"
    padding: Kirigami.Units.gridUnit
    standardButtons: Controls.Dialog.Ok | Controls.Dialog.Cancel

    ColumnLayout {
        spacing: Kirigami.Units.largeSpacing
        implicitWidth: Kirigami.Units.gridUnit * 24

        Kirigami.FormLayout {
            Layout.fillWidth: true

            Controls.TextField {
                id: urlInput
                Kirigami.FormData.label: "Address URL:"
                placeholderText: "https://example.com/file.zip"
                Layout.fillWidth: true
            }

            Controls.ComboBox {
                id: categoryCombo
                Kirigami.FormData.label: "Category:"
                model: ["General", "Compressed", "Documents", "Music", "Programs", "Video"]
                Layout.fillWidth: true
            }

            Controls.TextField {
                id: savePathInput
                Kirigami.FormData.label: "Save Directory:"
                placeholderText: "Default Downloads folder"
                Layout.fillWidth: true
            }
        }
    }

    onAccepted: {
        if (urlInput.text.trim() !== "") {
            downloadBridge.addDownload(urlInput.text.trim(), categoryCombo.currentText, savePathInput.text.trim())
            urlInput.text = ""
        }
    }
}

import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.Card {
    id: card
    property int originalIdx: model.originalIndex !== undefined ? model.originalIndex : index

    header: Kirigami.AbstractCardHeader {
        RowLayout {
            anchors.fill: parent
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                source: getIconForFile(model.filename)
                Layout.preferredWidth: Kirigami.Units.iconSizes.medium
                Layout.preferredHeight: Kirigami.Units.iconSizes.medium
            }

            Controls.Label {
                id: fileNameLabel
                text: model.filename || "File"
                font.bold: true
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.fillWidth: true

                Controls.ToolTip.visible: fileNameMouseArea.containsMouse
                Controls.ToolTip.text: fileNameLabel.text

                MouseArea {
                    id: fileNameMouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                }
            }

            Kirigami.Badge {
                text: model.status || "Downloading"
                color: model.status === "Complete" ? Kirigami.Theme.positiveTextColor :
                       model.status === "Error" ? Kirigami.Theme.negativeTextColor :
                       Kirigami.Theme.highlightColor
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: Kirigami.Units.smallSpacing

        Controls.ProgressBar {
            id: pBar
            Layout.fillWidth: true
            value: parseProgress(model.status)
        }

        RowLayout {
            Layout.fillWidth: true

            Controls.Label {
                text: "Size: " + (model.size || "Unknown")
                font.features: { "tnum": 1 }
                font.pixelSize: Kirigami.Units.smallFont.pixelSize
                opacity: 0.8
            }

            Item { Layout.fillWidth: true }

            Controls.Label {
                text: "Speed: " + (model.rate || "0.00 B/s")
                font.features: { "tnum": 1 }
                font.pixelSize: Kirigami.Units.smallFont.pixelSize
                opacity: 0.8
            }

            Item { Layout.fillWidth: true }

            Controls.Label {
                text: "ETA: " + (model.time_left || "--:--")
                font.features: { "tnum": 1 }
                font.pixelSize: Kirigami.Units.smallFont.pixelSize
                opacity: 0.8
            }
        }
    }

    actions: [
        Kirigami.Action {
            text: model.status === "Complete" ? "Open" : "Resume"
            tooltip: model.status === "Complete" ? "Open downloaded file" : "Resume downloading this file"
            icon.name: model.status === "Complete" ? "document-open" : "media-playback-start"
            onTriggered: {
                if (model.status === "Complete") {
                    downloadBridge.openFile(model.path)
                } else {
                    downloadBridge.resumeDownload(card.originalIdx)
                }
            }
        },
        Kirigami.Action {
            text: "Pause"
            tooltip: "Pause active download"
            icon.name: "media-playback-pause"
            visible: model.status !== "Complete"
            onTriggered: downloadBridge.pauseDownload(card.originalIdx)
        },
        Kirigami.Action {
            text: "Open Folder"
            tooltip: "Open folder containing this file"
            icon.name: "folder-open"
            onTriggered: downloadBridge.openFolder(model.path)
        },
        Kirigami.Action {
            text: "Delete"
            tooltip: "Remove this download from the list"
            icon.name: "edit-delete"
            onTriggered: downloadBridge.deleteDownload(card.originalIdx)
        }
    ]

    function parseProgress(statusStr) {
        if (!statusStr) return 0.0
        if (statusStr === "Complete") return 1.0
        var match = statusStr.match(/([0-9]+(?:\.[0-9]+)?)\s*%/)
        if (match && match[1]) {
            return parseFloat(match[1]) / 100.0
        }
        return 0.0
    }

    function getIconForFile(filename) {
        if (!filename) return "application-x-zerosize"
        var ext = filename.split('.').pop().toLowerCase()
        if (["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"].indexOf(ext) !== -1) return "package-x-generic"
        if (["pdf", "doc", "docx", "txt", "ppt", "pptx", "xls", "xlsx"].indexOf(ext) !== -1) return "x-office-document"
        if (["mp3", "wav", "flac", "aac", "ogg", "m4a"].indexOf(ext) !== -1) return "audio-x-generic"
        if (["mp4", "mkv", "avi", "mov", "wmv", "webm"].indexOf(ext) !== -1) return "video-x-generic"
        if (["exe", "msi", "deb", "rpm", "apk", "appimage", "flatpak", "snap", "sh", "bin", "bat", "cmd", "run", "dmg", "pkg", "jar"].indexOf(ext) !== -1) return "application-x-executable"
        return "document-new"
    }
}

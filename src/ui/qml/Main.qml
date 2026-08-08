import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: "Bengal Download Manager"
    icon: "io.github.tazihad.bengal-download-manager"
    width: 960
    height: 640
    visible: true

    property string currentCategoryFilter: "All"
    property string currentStatusFilter: "All"
    property string searchQuery: ""

    globalDrawer: GlobalDrawer {
        onCategorySelected: (cat) => {
            root.currentCategoryFilter = cat
        }
        onStatusSelected: (status) => {
            root.currentStatusFilter = status
        }
    }

    header: Kirigami.ApplicationHeader {
        title: "Bengal Download Manager"
    }

    actions: [
        Kirigami.Action {
            text: "Add URL"
            tooltip: "Add a new download URL address"
            icon.name: "list-add"
            onTriggered: addUrlDialog.open()
        },
        Kirigami.Action {
            text: "Resume All"
            tooltip: "Resume all paused downloads"
            icon.name: "media-playback-start"
            onTriggered: {
                for (var i = 0; i < downloadBridge.downloads.length; i++) {
                    downloadBridge.resumeDownload(i)
                }
            }
        },
        Kirigami.Action {
            text: "Pause All"
            tooltip: "Pause all active downloads"
            icon.name: "media-playback-pause"
            onTriggered: {
                for (var i = 0; i < downloadBridge.downloads.length; i++) {
                    downloadBridge.pauseDownload(i)
                }
            }
        },
        Kirigami.Action {
            text: "Queues"
            tooltip: "Manage download queues"
            icon.name: "alarm-clock"
            onTriggered: queuesDialog.open()
        },
        Kirigami.Action {
            text: "Options"
            tooltip: "Configure application preferences and settings"
            icon.name: "configure"
            onTriggered: optionsDialog.open()
        }
    ]

    pageStack.initialPage: Kirigami.Page {
        title: "Downloads (" + filteredModel.count + ")"

        actions: [
            Kirigami.Action {
                displayComponent: Controls.TextField {
                    placeholderText: "Search downloads..."
                    Controls.ToolTip.visible: searchMa.containsMouse
                    Controls.ToolTip.text: "Filter downloads by file name"
                    MouseArea {
                        id: searchMa
                        anchors.fill: parent
                        hoverEnabled: true
                        propagateComposedEvents: true
                    }
                    onTextChanged: root.searchQuery = text.toLowerCase()
                }
            }
        ]

        Kirigami.CardsListView {
            id: cardsView
            anchors.fill: parent
            model: filteredModel

            delegate: DownloadCard {
                width: cardsView.width - (Kirigami.Units.gridUnit * 2)
            }

            Kirigami.PlaceholderMessage {
                anchors.centerIn: parent
                visible: cardsView.count === 0
                icon.name: "download"
                text: "No Downloads Found"
                explanation: "Click 'Add URL' to start downloading files."
            }
        }
    }

    ListModel {
        id: filteredModel
    }

    function updateFilteredModel() {
        filteredModel.clear()
        var items = downloadBridge.downloads
        if (!items) return

        for (var i = 0; i < items.length; i++) {
            var item = items[i]
            var name = (item.filename || "").toLowerCase()
            var status = item.status || ""
            var cat = item.category || "General"

            var matchSearch = root.searchQuery === "" || name.indexOf(root.searchQuery) !== -1
            var matchCategory = root.currentCategoryFilter === "All" || cat === root.currentCategoryFilter
            var matchStatus = true

            if (root.currentStatusFilter === "Downloading") {
                matchStatus = status.indexOf("%") !== -1 && status !== "100%"
            } else if (root.currentStatusFilter === "Completed") {
                matchStatus = status === "Complete" || status.indexOf("100") !== -1
            } else if (root.currentStatusFilter === "Paused") {
                matchStatus = status === "Paused" || status === "Cancelled"
            }

            if (matchSearch && matchCategory && matchStatus) {
                item.originalIndex = i
                filteredModel.append(item)
            }
        }
    }

    Connections {
        target: downloadBridge
        function onDownloadsChanged() {
            root.updateFilteredModel()
        }
    }

    Component.onCompleted: {
        root.updateFilteredModel()
    }

    AddUrlDialog {
        id: addUrlDialog
    }

    OptionsDialog {
        id: optionsDialog
    }

    QueuesDialog {
        id: queuesDialog
    }
}

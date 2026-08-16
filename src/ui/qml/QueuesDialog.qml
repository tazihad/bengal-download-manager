// QueuesDialog.qml – Full-featured Scheduler / Queue Manager
import QtQuick 2.15
import QtQuick.Controls 2.15 as Controls
import QtQuick.Layouts 1.15
import org.kde.kirigami 2.15 as Kirigami

Kirigami.Dialog {
    id: queuesDialog
    title: "Scheduler"
    width: 820
    height: 620
    modal: true
    standardButtons: Kirigami.Dialog.NoButton

    property int selectedIndex: -1
    property var selectedQueue: ({})

    // Model for queues
    ListModel {
        id: queuesModel
        ListElement {
            name: "Main download queue"
            isDefault: true
            mode: "onetime"
            startOnStartup: false
            startAtEnabled: false
            startAtTime: "11:00 PM"
            scheduleType: "daily"
            stopAtEnabled: false
            stopAtTime: "7:30 AM"
            retriesEnabled: false
            retriesCount: 10
            openFileEnabled: false
            openFilePath: ""
            exitAppWhenDone: false
            turnOffEnabled: false
            turnOffAction: "Shut down"
            forceTerminate: false
            syncHours: 2
            syncMinutes: 0
        }
        ListElement {
            name: "Synchronization queue"
            isDefault: true
            mode: "sync"
            startOnStartup: false
            startAtEnabled: false
            startAtTime: "11:00 PM"
            scheduleType: "daily"
            stopAtEnabled: false
            stopAtTime: "7:30 AM"
            retriesEnabled: false
            retriesCount: 10
            openFileEnabled: false
            openFilePath: ""
            exitAppWhenDone: false
            turnOffEnabled: false
            turnOffAction: "Shut down"
            forceTerminate: false
            syncHours: 2
            syncMinutes: 0
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Kirigami.Units.smallSpacing

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Kirigami.Units.gridUnit

            // ---- LEFT PANEL ----
            ColumnLayout {
                Layout.preferredWidth: 200
                Layout.fillHeight: true
                spacing: Kirigami.Units.smallSpacing

                Controls.Label {
                    text: "Queues"
                    font.bold: true
                }

                Controls.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    ListView {
                        id: queueListView
                        model: queuesModel
                        clip: true
                        currentIndex: queuesDialog.selectedIndex

                        delegate: Controls.ItemDelegate {
                            width: queueListView.width
                            text: model.name
                            highlighted: ListView.isCurrentItem

                            onClicked: {
                                queuesDialog.selectedIndex = index
                                queuesDialog.selectedQueue = queuesModel.get(index)
                            }

                            // Right-click context menu
                            Controls.Menu {
                                id: contextMenu

                                Controls.MenuItem {
                                    id: miStart
                                    text: "Start now"
                                    contentItem: Controls.Label {
                                        text: miStart.text
                                        font: miStart.font
                                        color: miStart.highlighted ? "#000000" : palette.text
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }
                                Controls.MenuItem {
                                    id: miStop
                                    text: "Stop"
                                    contentItem: Controls.Label {
                                        text: miStop.text
                                        font: miStop.font
                                        color: miStop.highlighted ? "#000000" : palette.text
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }
                                Controls.MenuSeparator {}
                                Controls.MenuItem {
                                    id: miEdit
                                    text: "Edit queue"
                                    contentItem: Controls.Label {
                                        text: miEdit.text
                                        font: miEdit.font
                                        color: miEdit.highlighted ? "#000000" : palette.text
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    onTriggered: {
                                        queuesDialog.selectedIndex = index
                                        queuesDialog.selectedQueue = queuesModel.get(index)
                                    }
                                }
                                Controls.MenuItem {
                                    id: miSchedule
                                    text: "Schedule"
                                    contentItem: Controls.Label {
                                        text: miSchedule.text
                                        font: miSchedule.font
                                        color: miSchedule.highlighted ? "#000000" : palette.text
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    onTriggered: {
                                        queuesDialog.selectedIndex = index
                                        queuesDialog.selectedQueue = queuesModel.get(index)
                                        tabBar.currentIndex = 0
                                    }
                                }
                                Controls.MenuSeparator {}
                                Controls.MenuItem {
                                    id: miDelete
                                    text: "Delete"
                                    enabled: !model.isDefault
                                    contentItem: Controls.Label {
                                        text: miDelete.text
                                        font: miDelete.font
                                        opacity: miDelete.enabled ? 1.0 : 0.5
                                        color: !miDelete.enabled ? "#888888" : (miDelete.highlighted ? "#000000" : palette.text)
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    onTriggered: {
                                        queuesModel.remove(index)
                                        if (queuesDialog.selectedIndex === index) {
                                            queuesDialog.selectedIndex = -1
                                            queuesDialog.selectedQueue = {}
                                        }
                                    }
                                }
                                Controls.MenuItem {
                                    id: miNew
                                    text: "Create new queue"
                                    contentItem: Controls.Label {
                                        text: miNew.text
                                        font: miNew.font
                                        color: miNew.highlighted ? "#000000" : palette.text
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                    onTriggered: addNewQueue()
                                }
                            }

                            TapHandler {
                                acceptedButtons: Qt.RightButton
                                onTapped: contextMenu.popup()
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: Kirigami.Units.smallSpacing

                    Controls.Button {
                        text: "New queue"
                        icon.name: "list-add"
                        onClicked: addNewQueue()
                    }
                    Controls.Button {
                        text: "Delete"
                        icon.name: "edit-delete"
                        enabled: queuesDialog.selectedIndex >= 0
                                 && queuesDialog.selectedIndex < queuesModel.count
                                 && !queuesModel.get(queuesDialog.selectedIndex).isDefault
                        onClicked: {
                            if (queuesDialog.selectedIndex >= 0) {
                                queuesModel.remove(queuesDialog.selectedIndex)
                                queuesDialog.selectedIndex = -1
                                queuesDialog.selectedQueue = {}
                            }
                        }
                    }
                }
            }

            // Vertical separator
            Kirigami.Separator {
                Layout.fillHeight: true
            }

            // ---- RIGHT PANEL ----
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Kirigami.Units.smallSpacing
                visible: queuesDialog.selectedIndex >= 0

                // Queue title
                Controls.Label {
                    Layout.alignment: Qt.AlignHCenter
                    text: queuesDialog.selectedQueue.name || ""
                    font.bold: true
                    font.pointSize: 12
                }

                Controls.TabBar {
                    id: tabBar
                    Layout.fillWidth: true

                    Controls.TabButton { text: "Schedule" }
                    Controls.TabButton { text: "Files in the queue" }
                }

                Controls.StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: tabBar.currentIndex

                    // ---- SCHEDULE TAB ----
                    Controls.ScrollView {
                        ColumnLayout {
                            width: parent.width
                            spacing: Kirigami.Units.smallSpacing

                            // Mode selection
                            RowLayout {
                                spacing: Kirigami.Units.gridUnit * 2
                                Controls.RadioButton {
                                    id: radioOnetime
                                    text: "One-time downloading"
                                    checked: (queuesDialog.selectedQueue.mode || "onetime") === "onetime"
                                }
                                Controls.RadioButton {
                                    id: radioSync
                                    text: "Periodic synchronization"
                                    checked: (queuesDialog.selectedQueue.mode || "onetime") === "sync"
                                }
                            }

                            Kirigami.Separator { Layout.fillWidth: true }

                            // Start on startup
                            Controls.CheckBox {
                                id: chkStartup
                                text: "Start download on application startup"
                                checked: queuesDialog.selectedQueue.startOnStartup || false
                            }

                            // Start download at
                            RowLayout {
                                Controls.CheckBox {
                                    id: chkStartAt
                                    text: "Start download at"
                                    checked: queuesDialog.selectedQueue.startAtEnabled || false
                                }
                                Controls.TextField {
                                    id: txtStartTime
                                    text: queuesDialog.selectedQueue.startAtTime || "11:00 PM"
                                    enabled: chkStartAt.checked
                                    implicitWidth: 120
                                    font.features: { "tnum": 1 }
                                }
                            }

                            // One-time: Once at / Daily
                            ColumnLayout {
                                visible: radioOnetime.checked
                                spacing: Kirigami.Units.smallSpacing
                                Layout.leftMargin: Kirigami.Units.gridUnit

                                RowLayout {
                                    Controls.RadioButton {
                                        id: radioOnce
                                        text: "Once at"
                                        checked: (queuesDialog.selectedQueue.scheduleType || "daily") === "once"
                                    }
                                    Controls.TextField {
                                        text: Qt.formatDate(new Date(), "dddd, MMMM d, yyyy")
                                        enabled: radioOnce.checked
                                        implicitWidth: 220
                                    }
                                }

                                RowLayout {
                                    Controls.RadioButton {
                                        id: radioDaily
                                        text: "Daily"
                                        checked: (queuesDialog.selectedQueue.scheduleType || "daily") !== "once"
                                    }
                                }

                                // Weekday checkboxes
                                GridLayout {
                                    columns: 3
                                    columnSpacing: Kirigami.Units.gridUnit
                                    rowSpacing: 2
                                    Layout.leftMargin: Kirigami.Units.gridUnit * 2
                                    enabled: radioDaily.checked

                                    Controls.CheckBox { text: "Sunday"; checked: true }
                                    Controls.CheckBox { text: "Wednesday"; checked: true }
                                    Controls.CheckBox { text: "Saturday"; checked: true }
                                    Controls.CheckBox { text: "Monday"; checked: true }
                                    Controls.CheckBox { text: "Thursday"; checked: true }
                                    Controls.CheckBox { text: "Friday"; checked: true }
                                    Controls.CheckBox { text: "Tuesday"; checked: true }
                                }
                            }

                            // Sync: Start again every
                            ColumnLayout {
                                visible: radioSync.checked
                                spacing: Kirigami.Units.smallSpacing
                                Layout.leftMargin: Kirigami.Units.gridUnit

                                RowLayout {
                                    Controls.CheckBox {
                                        id: chkSyncInterval
                                        text: "Start again every"
                                    }
                                    Controls.SpinBox {
                                        from: 0; to: 99
                                        value: queuesDialog.selectedQueue.syncHours || 2
                                        enabled: chkSyncInterval.checked
                                        font.features: { "tnum": 1 }
                                    }
                                    Controls.Label { text: "hours" }
                                    Controls.SpinBox {
                                        from: 0; to: 59
                                        value: queuesDialog.selectedQueue.syncMinutes || 0
                                        enabled: chkSyncInterval.checked
                                        font.features: { "tnum": 1 }
                                    }
                                    Controls.Label { text: "min" }
                                }

                                Controls.Label {
                                    text: "Daily"
                                    font.bold: true
                                    Layout.leftMargin: Kirigami.Units.gridUnit
                                }

                                GridLayout {
                                    columns: 3
                                    columnSpacing: Kirigami.Units.gridUnit
                                    rowSpacing: 2
                                    Layout.leftMargin: Kirigami.Units.gridUnit * 2

                                    Controls.CheckBox { text: "Sunday"; checked: true }
                                    Controls.CheckBox { text: "Wednesday"; checked: true }
                                    Controls.CheckBox { text: "Saturday"; checked: true }
                                    Controls.CheckBox { text: "Monday"; checked: true }
                                    Controls.CheckBox { text: "Thursday"; checked: true }
                                    Controls.CheckBox { text: "Friday"; checked: true }
                                    Controls.CheckBox { text: "Tuesday"; checked: true }
                                }
                            }

                            // Stop download at
                            RowLayout {
                                Controls.CheckBox {
                                    id: chkStopAt
                                    text: "Stop download at"
                                    checked: queuesDialog.selectedQueue.stopAtEnabled || false
                                }
                                Controls.TextField {
                                    text: queuesDialog.selectedQueue.stopAtTime || "7:30 AM"
                                    enabled: chkStopAt.checked
                                    implicitWidth: 120
                                    font.features: { "tnum": 1 }
                                }
                            }

                            // Number of retries
                            RowLayout {
                                Controls.CheckBox {
                                    id: chkRetries
                                    text: "Number of retries for each file if downloading failed:"
                                    checked: queuesDialog.selectedQueue.retriesEnabled || false
                                }
                                Controls.SpinBox {
                                    from: 0; to: 999
                                    value: queuesDialog.selectedQueue.retriesCount || 10
                                    enabled: chkRetries.checked
                                    font.features: { "tnum": 1 }
                                }
                            }

                            // Open file when done
                            Controls.CheckBox {
                                id: chkOpenFile
                                text: "Open the following file when done:"
                                checked: queuesDialog.selectedQueue.openFileEnabled || false
                            }
                            RowLayout {
                                Layout.leftMargin: Kirigami.Units.gridUnit
                                Controls.TextField {
                                    Layout.fillWidth: true
                                    text: queuesDialog.selectedQueue.openFilePath || ""
                                    enabled: chkOpenFile.checked
                                }
                                Controls.Button {
                                    text: "..."
                                    enabled: chkOpenFile.checked
                                }
                            }

                            // Exit app when done
                            Controls.CheckBox {
                                id: chkExitApp
                                text: "Exit Bengal Download Manager when done"
                                checked: queuesDialog.selectedQueue.exitAppWhenDone || false
                            }

                            // Turn off computer
                            RowLayout {
                                Controls.CheckBox {
                                    id: chkTurnOff
                                    text: "Turn off computer when done"
                                    checked: queuesDialog.selectedQueue.turnOffEnabled || false
                                }
                                Controls.ComboBox {
                                    model: ["Shut down", "Hibernate", "Sleep", "Stand by"]
                                    enabled: chkTurnOff.checked
                                }
                            }

                            Controls.CheckBox {
                                text: "Force processes to terminate"
                                enabled: chkTurnOff.checked
                                checked: queuesDialog.selectedQueue.forceTerminate || false
                                Layout.leftMargin: Kirigami.Units.gridUnit
                            }
                        }
                    }

                    // ---- FILES TAB ----
                    ColumnLayout {
                        spacing: Kirigami.Units.smallSpacing

                        Kirigami.PlaceholderMessage {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            icon.name: "folder-download"
                            text: "No files in this queue"
                            explanation: "Files assigned to this queue will appear here."
                            visible: true
                        }
                    }
                }
            }
        }

        // ---- BOTTOM BUTTONS ----
        RowLayout {
            Layout.fillWidth: true
            spacing: Kirigami.Units.smallSpacing

            Controls.Button {
                text: "Start now"
                icon.name: "media-playback-start"
            }
            Controls.Button {
                text: "Stop"
                icon.name: "media-playback-stop"
            }
            Item { Layout.fillWidth: true }
            Controls.Button {
                text: "Apply"
                icon.name: "dialog-ok-apply"
            }
            Controls.Button {
                text: "Close"
                icon.name: "dialog-close"
                onClicked: queuesDialog.close()
            }
        }
    }

    function addNewQueue() {
        var base = "Queue"
        var num = queuesModel.count - 1
        var name = base + " # " + num
        queuesModel.append({
            name: name,
            isDefault: false,
            mode: "onetime",
            startOnStartup: false,
            startAtEnabled: false,
            startAtTime: "11:00 PM",
            scheduleType: "daily",
            stopAtEnabled: false,
            stopAtTime: "7:30 AM",
            retriesEnabled: false,
            retriesCount: 10,
            openFileEnabled: false,
            openFilePath: "",
            exitAppWhenDone: false,
            turnOffEnabled: false,
            turnOffAction: "Shut down",
            forceTerminate: false,
            syncHours: 2,
            syncMinutes: 0
        })
        queuesDialog.selectedIndex = queuesModel.count - 1
        queuesDialog.selectedQueue = queuesModel.get(queuesDialog.selectedIndex)
    }
}

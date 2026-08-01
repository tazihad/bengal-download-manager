import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.GlobalDrawer {
    id: drawer
    title: "Categories"
    collapsible: true
    collapsed: false

    signal categorySelected(string category)
    signal statusSelected(string status)

    actions: [
        Kirigami.Action {
            text: "All Downloads"
            icon.name: "folder-download"
            onTriggered: {
                drawer.statusSelected("All")
                drawer.categorySelected("All")
            }
        },
        Kirigami.Action {
            text: "Downloading"
            icon.name: "state-sync"
            onTriggered: drawer.statusSelected("Downloading")
        },
        Kirigami.Action {
            text: "Completed"
            icon.name: "emblem-success"
            onTriggered: drawer.statusSelected("Completed")
        },
        Kirigami.Action {
            text: "Paused"
            icon.name: "media-playback-pause"
            onTriggered: drawer.statusSelected("Paused")
        },
        Kirigami.Action {
            separator: true
        },
        Kirigami.Action {
            text: "Compressed"
            icon.name: "package-x-generic"
            onTriggered: drawer.categorySelected("Compressed")
        },
        Kirigami.Action {
            text: "Documents"
            icon.name: "x-office-document"
            onTriggered: drawer.categorySelected("Documents")
        },
        Kirigami.Action {
            text: "Music"
            icon.name: "audio-x-generic"
            onTriggered: drawer.categorySelected("Music")
        },
        Kirigami.Action {
            text: "Programs"
            icon.name: "application-x-executable"
            onTriggered: drawer.categorySelected("Programs")
        },
        Kirigami.Action {
            text: "Video"
            icon.name: "video-x-generic"
            onTriggered: drawer.categorySelected("Video")
        }
    ]
}

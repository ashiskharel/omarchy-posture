import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "ashis.posture"
  ipcTarget: "ashis.posture"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root
  property bool openedFromHotkey: false

  property string pose: "mountain"
  property string sourceText: "camera"
  property string label: "Pose"
  property var report: ({})
  property int tick: 0
  readonly property string cachePath: Quickshell.env("HOME") + "/.cache/omarchy-posture"
  readonly property color ink: bar ? bar.foreground : Color.foreground
  readonly property string face: bar ? bar.fontFamily : Style.font.family

  function scriptPath() {
    var url = String(Qt.resolvedUrl("bin/pose"))
    if (url.indexOf("file://") === 0) url = url.slice(7)
    return decodeURIComponent(url)
  }

  function open() {
    openedFromHotkey = false
    setCenterHoverRevealSuppressed(false)
    controller.show()
    startCoach()
  }

  function openFromHotkey() {
    openedFromHotkey = true
    controller.show()
    startCoach()
    Qt.callLater(function() {
      if (root.opened) setCenterHoverRevealSuppressed(true)
    })
  }

  function close() {
    setCenterHoverRevealSuppressed(false)
    stopCoach()
    controller.hide()
  }

  function toggle() {
    if (opened) close()
    else openFromHotkey()
  }

  function switchPanel(direction) {
    if (bar && typeof bar.switchPanelFrom === "function")
      return bar.switchPanelFrom(barIdentity, direction)
    return false
  }

  function setCenterHoverRevealSuppressed(value) {
    if (bar && typeof bar.setCenterHoverRevealSuppressed === "function")
      bar.setCenterHoverRevealSuppressed(value)
    else if (bar && "centerHoverRevealSuppressed" in bar)
      bar.centerHoverRevealSuppressed = value
  }

  function choose(name) {
    pose = name
    poseWrite.command = ["sh", "-c", "mkdir -p \"$1\" && printf '%s\\n' \"$2\" > \"$1/pose.txt\"", "pose-write", cachePath, name]
    poseWrite.running = true
  }

  function pluginRoot() {
    var script = scriptPath()
    var cut = script.lastIndexOf("/bin/pose")
    return cut > 0 ? script.slice(0, cut) : script
  }

  function startCoach() {
    if (coach.running) return
    // Run the virtualenv interpreter directly. uv and bytecode files must
    // not be written into this plugin folder, or the shell reloads it and
    // the panel closes.
    var rootDir = pluginRoot()
    var python = rootDir + "/.venv/bin/python"
    coach.command = [
      "env",
      "PYTHONDONTWRITEBYTECODE=1",
      "PYTHONPYCACHEPREFIX=" + cachePath + "/pyc",
      "PYTHONPATH=" + rootDir,
      python,
      "-m", "pose", "serve",
      "--source", sourceText,
      "--pose", pose,
      "--dir", cachePath
    ]
    coach.running = true
  }

  function stopCoach() {
    if (coach.running) coach.running = false
    label = "Pose"
  }

  function applyReport(raw) {
    var parsed
    try { parsed = JSON.parse(raw) } catch (e) { return }
    report = parsed
    if (parsed.label) label = parsed.label
    frame.counter++
  }

  Process {
    id: poseWrite
  }

  FileView {
    id: liveFile
    path: root.cachePath + "/live.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.applyReport(text())
  }

  Process {
    id: coach
    onExited: function(code) {
      if (root.opened && code !== 0) root.report = { cues: [{ text: "The coach stopped.", ok: false }], seen: false }
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(420))
    contentHeight: panel.fittedContentHeight(column.implicitHeight)

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
          id: column
          width: parent.width
          spacing: Style.space(10)

          Text {
            text: root.report.pose_name || "Posture"
            color: root.ink
            font.family: root.face
            font.pixelSize: Style.font.heading
          }

          Row {
            spacing: Style.space(8)
            Repeater {
              model: [
                { id: "mountain", name: "Mountain" },
                { id: "fold", name: "Fold" },
                { id: "chair", name: "Chair" },
                { id: "side", name: "Side" }
              ]
              delegate: Text {
                required property var modelData
                text: modelData.name
                color: root.ink
                opacity: root.pose === modelData.id ? 1 : 0.45
                font.family: root.face
                font.pixelSize: Style.font.body
                font.underline: root.pose === modelData.id
                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.choose(modelData.id)
                }
              }
            }
          }

          Image {
            id: frame
            property int counter: 0
            width: parent.width
            height: Style.space(240)
            fillMode: Image.PreserveAspectFit
            cache: false
            source: counter > 0 ? ("file://" + root.cachePath + "/live.jpg?t=" + counter) : ""
          }

          Column {
            width: parent.width
            spacing: 4
            Repeater {
              model: root.report.cues || []
              delegate: Text {
                required property var modelData
                width: parent.width
                wrapMode: Text.WordWrap
                text: (modelData.ok ? "Good. " : "Adjust. ") + modelData.text
                color: root.ink
                opacity: modelData.ok ? 0.95 : 0.7
                font.family: root.face
                font.pixelSize: Style.font.body
              }
            }
          }

          Text {
            width: parent.width
            wrapMode: Text.WordWrap
            color: root.ink
            opacity: 0.45
            font.family: root.face
            font.pixelSize: Style.font.caption
            text: "Camera stays local. An IP camera is a source you type below. The picture is not uploaded."
          }

          Row {
            spacing: Style.space(8)
            width: parent.width
            TextInput {
              id: sourceField
              width: parent.width - apply.width - Style.space(8)
              text: root.sourceText
              color: root.ink
              font.family: root.face
              font.pixelSize: Style.font.bodySmall
              selectByMouse: true
              onAccepted: applySource()
            }
            Text {
              id: apply
              text: "Use"
              color: root.ink
              font.underline: true
              font.family: root.face
              font.pixelSize: Style.font.bodySmall
              MouseArea {
                anchors.fill: parent
                onClicked: applySource()
              }
            }
          }
        }
      }
    }
  }

  function applySource() {
    var next = sourceField.text.trim()
    if (next === "") next = "camera"
    sourceText = next
    if (coach.running) coach.running = false
    startCoach()
  }
}

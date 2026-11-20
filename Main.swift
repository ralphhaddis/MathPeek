import AppKit
import Carbon
import CoreGraphics

final class PreviewPanel: NSPanel {
    var dismiss: (() -> Void)?
    var onRefresh: (() -> Void)?
    var onCopySource: (() -> Void)?
    var onQuit: (() -> Void)?
    override var canBecomeKey: Bool { true }
    override func cancelOperation(_ sender: Any?) { dismiss?() }
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if flags == .command, let chars = event.charactersIgnoringModifiers?.lowercased() {
            switch chars {
            case "r": onRefresh?(); return true
            case "w": dismiss?(); return true
            case "c": onCopySource?(); return true
            case "q": onQuit?(); return true
            default: break
            }
        }
        return super.performKeyEquivalent(with: event)
    }
}

final class HistoryDocumentStack: NSStackView {
    override var isFlipped: Bool { true }
}

final class App: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var status: NSStatusItem!
    var panel: PreviewPanel!
    var stack: NSStackView!
    var historyScroll: NSScrollView!
    var historyStack: NSStackView!
    var copyButton: NSButton?
    var copyFeedbackWork: DispatchWorkItem?
    var loadingView: NSView?
    var history: [(source: String, view: NSView)] = []
    var autoPreviewItem: NSMenuItem!
    var autoPreviewEnabled = true
    var clipboardTimer: DispatchSourceTimer?
    var clipboardDebounce: DispatchWorkItem?
    var lastClipboardChange = -1
    var lastHandledText = ""
    var source = ""
    var job: Process?
    var generation = UUID()
    var hasPlacedPanel = false
    var hotKeyRef: EventHotKeyRef?
    var hotKeyHandler: EventHandlerRef?
    let workerQueue = DispatchQueue(label: "mathpeek.renderer")

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        status.button?.image = NSImage(systemSymbolName: "function", accessibilityDescription: "MathPeek")
        let menu = NSMenu()
        let previewItem = NSMenuItem(title: "Preview Clipboard", action: #selector(clipboard), keyEquivalent: "l")
        previewItem.keyEquivalentModifierMask = [.control, .option, .command]
        previewItem.target = self
        menu.addItem(previewItem)
        let defaults = UserDefaults.standard
        if let savedValue = defaults.object(forKey:"autoPreviewClipboard") as? Bool {
            autoPreviewEnabled = savedValue
        } else if let priorValue = UserDefaults(suiteName:"com.mathpeek.app")?.object(forKey:"autoPreviewClipboard") as? Bool {
            autoPreviewEnabled = priorValue
            defaults.set(priorValue, forKey:"autoPreviewClipboard")
        } else {
            autoPreviewEnabled = true
        }
        autoPreviewItem = NSMenuItem(title:"Auto Preview Copied Text", action:#selector(toggleAutoPreview), keyEquivalent:"")
        autoPreviewItem.target = self
        autoPreviewItem.state = autoPreviewEnabled ? .on : .off
        menu.addItem(autoPreviewItem)
        menu.addItem(.separator())
        menu.addItem(withTitle: "Quit MathPeek", action: #selector(quit), keyEquivalent: "q").target = self
        status.menu = menu
        createPanel()
        registerGlobalHotKey()
        NSApp.servicesProvider = self
        NSUpdateDynamicServices()
        lastClipboardChange = NSPasteboard.general.changeCount
        let timer = DispatchSource.makeTimerSource(queue:.main)
        timer.schedule(deadline:.now()+0.15, repeating:0.15, leeway:.milliseconds(30))
        timer.setEventHandler { [weak self] in self?.checkClipboard() }
        clipboardTimer = timer
        timer.resume()
    }
    func makeHeaderButton(symbol: String, accessibility: String, toolTip: String, action: Selector) -> NSButton {
        let image = NSImage(systemSymbolName: symbol, accessibilityDescription: accessibility) ?? NSImage()
        let config = NSImage.SymbolConfiguration(pointSize: 13, weight: .medium)
        let button = NSButton(image: image.withSymbolConfiguration(config) ?? image, target: self, action: action)
        button.isBordered = false
        button.bezelStyle = .accessoryBarAction
        button.imagePosition = .imageOnly
        button.contentTintColor = .secondaryLabelColor
        button.toolTip = toolTip
        button.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            button.widthAnchor.constraint(equalToConstant: 24),
            button.heightAnchor.constraint(equalToConstant: 24)
        ])
        return button
    }
    func createPanel() {
        panel = PreviewPanel(contentRect: NSRect(x:0,y:0,width:520,height:340), styleMask:[.titled,.resizable,.fullSizeContentView,.nonactivatingPanel], backing:.buffered, defer:false)
        panel.standardWindowButton(.closeButton)?.isHidden = true
        panel.standardWindowButton(.miniaturizeButton)?.isHidden = true
        panel.standardWindowButton(.zoomButton)?.isHidden = true
        panel.minSize = NSSize(width: 360, height: 220)
        panel.maxSize = NSSize(width: 960, height: 760)
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.isMovableByWindowBackground = true
        panel.isFloatingPanel = true
        panel.level = .floating
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.moveToActiveSpace,.fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        panel.delegate = self
        panel.dismiss = { [weak self] in self?.close() }
        panel.onRefresh = { [weak self] in self?.refreshClipboard() }
        panel.onCopySource = { [weak self] in self?.copySource() }
        panel.onQuit = { [weak self] in self?.quit() }
        let material = NSVisualEffectView()
        material.material = .popover
        material.blendingMode = .behindWindow
        material.state = .active
        panel.contentView = material
        stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 10
        stack.edgeInsets = NSEdgeInsets(top:12,left:16,bottom:14,right:16)
        stack.translatesAutoresizingMaskIntoConstraints = false
        material.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo:material.leadingAnchor),stack.trailingAnchor.constraint(equalTo:material.trailingAnchor),stack.topAnchor.constraint(equalTo:material.topAnchor),stack.bottomAnchor.constraint(equalTo:material.bottomAnchor)])
        let title = NSTextField(labelWithString:"MathPeek")
        title.font = .systemFont(ofSize:13,weight:.medium)
        title.textColor = .secondaryLabelColor
        let spacer = NSView()
        spacer.setContentHuggingPriority(.defaultLow, for:.horizontal)
        let refresh = makeHeaderButton(symbol: "arrow.clockwise", accessibility: "Refresh from Clipboard", toolTip: "Refresh from clipboard (⌘R)", action: #selector(refreshClipboard))
        refresh.keyEquivalent = "r"
        refresh.keyEquivalentModifierMask = [.command]
        let copy = makeHeaderButton(symbol: "doc.on.doc", accessibility: "Copy LaTeX Source", toolTip: "Copy LaTeX source (⌘C)", action: #selector(copySource))
        copyButton = copy
        let close = makeHeaderButton(symbol: "xmark", accessibility: "Close preview", toolTip: "Close (Esc)", action: #selector(closeAction))
        let header = NSStackView(views:[title,spacer,refresh,copy,close])
        header.alignment = .centerY
        header.spacing = 6
        stack.addArrangedSubview(header)
        header.widthAnchor.constraint(equalTo:stack.widthAnchor,constant:-32).isActive = true
        let headerDivider = NSBox()
        headerDivider.boxType = .separator
        stack.addArrangedSubview(headerDivider)
        headerDivider.widthAnchor.constraint(equalTo:stack.widthAnchor,constant:-32).isActive = true
        historyStack = HistoryDocumentStack()
        historyStack.orientation = .vertical
        historyStack.alignment = .leading
        historyStack.spacing = 12
        historyStack.translatesAutoresizingMaskIntoConstraints = true
        historyScroll = NSScrollView()
        historyScroll.drawsBackground = false
        historyScroll.hasVerticalScroller = true
        historyScroll.autohidesScrollers = true
        historyStack.frame = NSRect(x:0,y:0,width:historyScroll.contentSize.width,height:1)
        historyStack.edgeInsets = NSEdgeInsets(top:10,left:12,bottom:10,right:12)
        historyScroll.documentView = historyStack
        historyScroll.setContentHuggingPriority(.defaultLow, for: .vertical)
        stack.addArrangedSubview(historyScroll)
        historyScroll.widthAnchor.constraint(equalTo:stack.widthAnchor,constant:-32).isActive = true
        historyScroll.contentView.postsBoundsChangedNotifications = true
        NotificationCenter.default.addObserver(self, selector:#selector(historyWidthChanged), name:NSView.boundsDidChangeNotification, object:historyScroll.contentView)
    }
    func registerGlobalHotKey() {
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let selfPtr = Unmanaged.passUnretained(self).toOpaque()
        InstallEventHandler(GetEventDispatcherTarget(), { (_, event, userData) -> OSStatus in
            guard let event, let userData else { return OSStatus(eventNotHandledErr) }
            var hkID = EventHotKeyID()
            let status = GetEventParameter(
                event,
                EventParamName(kEventParamDirectObject),
                EventParamType(typeEventHotKeyID),
                nil,
                MemoryLayout<EventHotKeyID>.size,
                nil,
                &hkID
            )
            guard status == noErr, hkID.signature == 0x4D504B31, hkID.id == 1 else {
                return OSStatus(eventNotHandledErr)
            }
            let app = Unmanaged<App>.fromOpaque(userData).takeUnretainedValue()
            DispatchQueue.main.async { app.refreshClipboard() }
            return noErr
        }, 1, &eventType, selfPtr, &hotKeyHandler)
        let hotKeyID = EventHotKeyID(signature: 0x4D504B31, id: 1)
        RegisterEventHotKey(UInt32(kVK_ANSI_L), UInt32(controlKey | optionKey | cmdKey), hotKeyID, GetEventDispatcherTarget(), 0, &hotKeyRef)
    }
    @objc func previewClipboardService(_ pasteboard: NSPasteboard, userData: String?, error: AutoreleasingUnsafeMutablePointer<NSString?>) {
        // Ignore the service pasteboard; always read explicitly copied text from the general clipboard.
        DispatchQueue.main.async { [weak self] in
            self?.refreshClipboard()
        }
    }
    @objc func toggleAutoPreview() {
        autoPreviewEnabled.toggle()
        autoPreviewItem.state = autoPreviewEnabled ? .on : .off
        UserDefaults.standard.set(autoPreviewEnabled, forKey:"autoPreviewClipboard")
    }
    @objc func refreshClipboard() {
        guard let text = NSPasteboard.general.string(forType:.string), !text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else {
            addStatus("Copy a LaTeX expression first, then press your shortcut or ⌘R.")
            show(activate: true)
            NSSound.beep()
            return
        }
        lastHandledText = text
        lastClipboardChange = NSPasteboard.general.changeCount
        present(text, activate: true)
    }
    @objc func clipboard() { refreshClipboard() }
    @objc func quit() { close(); NSApp.terminate(nil) }
    @objc func closeAction() { close() }
    @objc func copySource() {
        guard !source.isEmpty else { NSSound.beep(); return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(source,forType:.string)
        lastHandledText = source
        lastClipboardChange = NSPasteboard.general.changeCount
        guard let copyButton else { return }
        let config = NSImage.SymbolConfiguration(pointSize: 13, weight: .medium)
        if let check = NSImage(systemSymbolName: "checkmark", accessibilityDescription: "Copied")?.withSymbolConfiguration(config) {
            copyButton.image = check
            copyButton.contentTintColor = .labelColor
        }
        copyFeedbackWork?.cancel()
        let reset = DispatchWorkItem { [weak self] in
            guard let button = self?.copyButton else { return }
            if let doc = NSImage(systemSymbolName: "doc.on.doc", accessibilityDescription: "Copy LaTeX Source")?.withSymbolConfiguration(config) {
                button.image = doc
            }
            button.contentTintColor = .secondaryLabelColor
        }
        copyFeedbackWork = reset
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2, execute: reset)
    }
    func isSelectionAutoCopy() -> Bool {
        if NSEvent.pressedMouseButtons != 0 { return true }
        let sinceKey = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .keyDown)
        let sinceMouseUp = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .leftMouseUp)
        let sinceMouseDrag = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: .leftMouseDragged)
        // Keyboard-triggered copy (e.g. ⌘C) has a very recent keyDown after the last mouse release.
        if sinceKey < 1.2 && sinceKey < sinceMouseUp {
            return false
        }
        // A drag-selection followed immediately by a pasteboard write with no subsequent keyDown is copy-on-select.
        if sinceMouseDrag < 0.6 && sinceMouseUp < 0.6 {
            return true
        }
        // Terminals like iTerm2 (with default CopySelection=true) also copy on double/triple-click selection
        // without a drag; require a keyboard shortcut when a copy-on-select terminal is frontmost.
        let copyOnSelectApps: Set<String> = [
            "com.googlecode.iterm2",
            "com.apple.Terminal",
            "org.alacritty",
            "com.mitchellh.ghostty",
            "net.kovidgoyal.kitty",
            "dev.warp.Warp-Stable",
            "com.github.wez.wezterm"
        ]
        if let frontID = NSWorkspace.shared.frontmostApplication?.bundleIdentifier,
           copyOnSelectApps.contains(frontID) {
            return true
        }
        return false
    }
    func checkClipboard() {
        let board = NSPasteboard.general
        guard board.changeCount != lastClipboardChange else { return }
        lastClipboardChange = board.changeCount
        let sensitiveTypes: Set<NSPasteboard.PasteboardType> = [
            NSPasteboard.PasteboardType("org.nspasteboard.ConcealedType"),
            NSPasteboard.PasteboardType("org.nspasteboard.TransientType"),
            NSPasteboard.PasteboardType("org.nspasteboard.AutoGeneratedType")
        ]
        if let types = board.types, !sensitiveTypes.isDisjoint(with: types) { return }
        // Only a general-pasteboard change may update an already-visible panel.
        guard autoPreviewEnabled, panel.isVisible else { return }
        // Ignore automatic copy-on-selection writes (e.g. iTerm2 CopySelection) without
        // updating lastHandledText so a subsequent explicit ⌘C still renders.
        if isSelectionAutoCopy() { return }
        guard let text = board.string(forType:.string),
              !text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,
              text != lastHandledText else { return }
        lastHandledText = text
        clipboardDebounce?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.present(text, activate: false) }
        clipboardDebounce = work
        DispatchQueue.main.asyncAfter(deadline:.now()+0.3, execute:work)
    }
    func close() {
        generation = UUID()
        if let job = job, job.isRunning { job.terminate() }
        job = nil
        panel.orderOut(nil)
    }
    func addStatus(_ message: String) {
        if let loadingView { historyStack.removeArrangedSubview(loadingView); loadingView.removeFromSuperview() }
        let label = NSTextField(wrappingLabelWithString:message)
        label.textColor = .secondaryLabelColor
        label.font = .systemFont(ofSize:13)
        label.lineBreakMode = .byWordWrapping
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        loadingView = label
        historyStack.addArrangedSubview(label)
        label.widthAnchor.constraint(equalTo: historyStack.widthAnchor, constant: -24).isActive = true
        scrollToLatest()
    }
    func addError(_ message: String, source: String?) {
        let card = NSStackView()
        card.orientation = .vertical
        card.alignment = .leading
        card.spacing = 4
        card.edgeInsets = NSEdgeInsets(top: 4, left: 2, bottom: 4, right: 2)

        let iconConfig = NSImage.SymbolConfiguration(pointSize: 13, weight: .medium)
        let iconView = NSImageView()
        iconView.image = NSImage(systemSymbolName: "exclamationmark.circle", accessibilityDescription: "Notice")?.withSymbolConfiguration(iconConfig)
        iconView.contentTintColor = .secondaryLabelColor
        iconView.setContentHuggingPriority(.required, for: .horizontal)
        iconView.setContentCompressionResistancePriority(.required, for: .horizontal)

        let titleLabel = NSTextField(labelWithString: "Couldn't render formula")
        titleLabel.font = .systemFont(ofSize: 13, weight: .medium)
        titleLabel.textColor = .labelColor
        titleLabel.lineBreakMode = .byTruncatingTail
        titleLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)

        let headerRow = NSStackView(views: [iconView, titleLabel])
        headerRow.orientation = .horizontal
        headerRow.alignment = .centerY
        headerRow.spacing = 6
        card.addArrangedSubview(headerRow)
        headerRow.widthAnchor.constraint(lessThanOrEqualTo: card.widthAnchor).isActive = true

        let reasonText = message.trimmingCharacters(in: .whitespacesAndNewlines)
        let reasonLabel = NSTextField(wrappingLabelWithString: reasonText.isEmpty ? "Rendering stopped unexpectedly." : reasonText)
        reasonLabel.font = .systemFont(ofSize: 13, weight: .regular)
        reasonLabel.textColor = .secondaryLabelColor
        reasonLabel.isSelectable = true
        reasonLabel.lineBreakMode = .byWordWrapping
        reasonLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        card.addArrangedSubview(reasonLabel)
        reasonLabel.widthAnchor.constraint(equalTo: card.widthAnchor, constant: -4).isActive = true

        let rawSource = source ?? ""
        let condensed = rawSource
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
        if !condensed.isEmpty {
            let preview = condensed.count > 120 ? String(condensed.prefix(120)) + "…" : condensed
            let snippetLabel = NSTextField(labelWithString: preview)
            snippetLabel.font = .systemFont(ofSize: 13, weight: .regular)
            snippetLabel.textColor = .tertiaryLabelColor
            snippetLabel.isSelectable = true
            snippetLabel.lineBreakMode = .byTruncatingTail
            snippetLabel.maximumNumberOfLines = 2
            snippetLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
            card.addArrangedSubview(snippetLabel)
            snippetLabel.widthAnchor.constraint(equalTo: card.widthAnchor, constant: -4).isActive = true
        }

        addHistory(card, source: rawSource)
    }
    func removeStatus() {
        if let loadingView { historyStack.removeArrangedSubview(loadingView); loadingView.removeFromSuperview(); self.loadingView = nil }
    }
    func scrollToLatest() {
        DispatchQueue.main.async { [weak self] in
            guard let self else { return }
            self.updateHistoryDocumentSize()
            let visibleHeight = self.historyScroll.contentSize.height
            let maxY = max(0, self.historyStack.frame.height - visibleHeight)
            let y: CGFloat
            if let latest = self.history.last {
                y = min(maxY, max(0, latest.view.frame.minY - 8))
            } else {
                y = maxY
            }
            self.historyScroll.contentView.scroll(to:NSPoint(x:0,y:y))
            self.historyScroll.reflectScrolledClipView(self.historyScroll.contentView)
        }
    }
    @objc func historyWidthChanged(_ notification: Notification) { updateHistoryDocumentSize() }
    func windowDidResize(_ notification: Notification) { updateHistoryDocumentSize() }
    func updateHistoryDocumentSize() {
        guard historyStack != nil, historyScroll != nil else { return }
        let width = max(1, historyScroll.contentSize.width)
        historyStack.setFrameSize(NSSize(width:width,height:max(1,historyStack.frame.height)))
        historyStack.layoutSubtreeIfNeeded()
        let height = max(1,historyStack.fittingSize.height)
        if abs(historyStack.frame.width - width) > 0.5 || abs(historyStack.frame.height - height) > 0.5 {
            historyStack.setFrameSize(NSSize(width:width,height:height))
        }
    }
    func addHistory(_ view: NSView, source: String) {
        removeStatus()
        if let latest = history.last, latest.source == source { historyStack.removeArrangedSubview(latest.view); latest.view.removeFromSuperview(); history.removeLast() }
        var cardViews: [NSView] = []
        if !history.isEmpty {
            let divider = NSBox()
            divider.boxType = .separator
            cardViews.append(divider)
        }
        cardViews.append(view)
        let card = NSStackView(views:cardViews)
        card.orientation = .vertical
        card.alignment = .leading
        card.spacing = 10
        historyStack.addArrangedSubview(card)
        // Activate cross-view constraints only after the views share a parent.
        card.widthAnchor.constraint(equalTo:historyStack.widthAnchor, constant:-24).isActive = true
        for subview in cardViews {
            subview.widthAnchor.constraint(equalTo:card.widthAnchor).isActive = true
        }
        history.append((source,card))
        while history.count > 40 {
            let oldest = history.removeFirst()
            historyStack.removeArrangedSubview(oldest.view)
            oldest.view.removeFromSuperview()
        }
        scrollToLatest()
    }
    func show(activate: Bool = true) {
        if !hasPlacedPanel {
            let mouse = NSEvent.mouseLocation
            let screen = NSScreen.screens.first(where:{$0.frame.contains(mouse)}) ?? NSScreen.main
            if let frame = screen?.visibleFrame {
                let size = panel.frame.size
                panel.setFrameOrigin(NSPoint(x:max(frame.minX+8,min(mouse.x+16,frame.maxX-size.width-8)),y:max(frame.minY+8,min(mouse.y-size.height-12,frame.maxY-size.height-8))))
            }
            hasPlacedPanel = true
        }
        if activate {
            NSApp.activate(ignoringOtherApps: true)
            panel.makeKeyAndOrderFront(nil)
        } else {
            panel.orderFront(nil)
        }
    }
    func present(_ text: String, activate: Bool = true) {
        generation = UUID()
        if let job = job, job.isRunning { job.terminate() }
        job = nil
        if text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty { addStatus("Copy text first."); show(activate: activate); return }
        if text.utf8.count > 32768 { addStatus("Select a smaller passage (up to 32 KB)."); show(activate: activate); return }
        source = text
        addStatus("Rendering formula…")
        show(activate: activate)
        let id = UUID(); generation = id
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("MathPeek-"+UUID().uuidString)
        do {
            try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            let inputURL = folder.appendingPathComponent("input.txt")
            try text.write(to:inputURL,atomically:true,encoding:.utf8)
            try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:inputURL.path)
            let process = Process()
            let pythonPath = Bundle.main.object(forInfoDictionaryKey:"MathPeekPython") as? String ?? "/usr/bin/python3"
            process.executableURL = URL(fileURLWithPath:pythonPath)
            process.arguments = [Bundle.main.resourceURL!.appendingPathComponent("render.py").path,folder.path]
            process.environment = ["HOME":folder.path,"TMPDIR":folder.path,"PATH":"/usr/bin:/bin:/usr/sbin:/sbin","PYTHONNOUSERSITE":"1","PYTHONDONTWRITEBYTECODE":"1"]
            let pipe = Pipe(); process.standardOutput = pipe
            process.standardError = FileHandle.nullDevice
            job = process
            try process.run()
            workerQueue.async {
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                let result = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any]
                let imageData = try? Data(contentsOf:folder.appendingPathComponent("image.png"))
                try? FileManager.default.removeItem(at:folder)
                DispatchQueue.main.async {
                    guard self.generation == id else { return }
                    self.job = nil
                    if result?["ok"] as? Bool == true, let data = imageData, let img = NSImage(data:data) {
                        self.display(img, width:result?["width"] as? Double ?? 400, height:result?["height"] as? Double ?? 100)
                    } else {
                        let errMsg = result?["error"] as? String ?? "Rendering stopped unexpectedly."
                        let errSource = result?["source"] as? String ?? text
                        self.addError(errMsg, source: errSource)
                    }
                }
            }
        } catch {
            try? FileManager.default.removeItem(at:folder)
            addError("Could not start the renderer: " + error.localizedDescription, source: text)
        }
    }
    func display(_ img: NSImage, width: Double, height: Double) {
        img.isTemplate = true
        let naturalSize = NSSize(width:max(1,width*0.32),height:max(1,height*0.32))
        let historyWidth = historyStack.frame.width > 1 ? historyStack.frame.width : panel.frame.width-32
        let maxImageWidth = max(1,historyWidth-24)
        let scale = min(1,maxImageWidth/naturalSize.width)
        let size = NSSize(width:naturalSize.width*scale,height:naturalSize.height*scale)
        img.size = size
        let imageView = NSImageView(frame:NSRect(origin:.zero,size:size))
        imageView.translatesAutoresizingMaskIntoConstraints = false
        imageView.image = img
        imageView.contentTintColor = .labelColor
        imageView.imageScaling = .scaleProportionallyDown
        imageView.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        imageView.setAccessibilityLabel("Rendered formula: "+source)
        imageView.heightAnchor.constraint(equalToConstant:size.height).isActive = true
        addHistory(imageView, source:source)
    }
    deinit {
        clipboardTimer?.cancel()
        NotificationCenter.default.removeObserver(self)
        if let hotKeyRef { UnregisterEventHotKey(hotKeyRef) }
        if let hotKeyHandler { RemoveEventHandler(hotKeyHandler) }
    }
}
let application = NSApplication.shared
let delegate = App()
application.delegate = delegate
application.run()

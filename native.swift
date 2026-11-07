import AppKit
import WebKit
import AVFoundation

final class StudioApp: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    let address = URL(string: "http://127.0.0.1:18321")!
    let root = Bundle.main.bundleURL.deletingLastPathComponent()

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        let menu = NSMenu()
        let item = NSMenuItem(); menu.addItem(item)
        let submenu = NSMenu(); item.submenu = submenu
        submenu.addItem(withTitle: "О программе Kadr", action: #selector(about), keyEquivalent: "")
        submenu.addItem(NSMenuItem.separator())
        submenu.addItem(withTitle: "Завершить Kadr", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let editItem = NSMenuItem(title: "Правка", action: nil, keyEquivalent: ""); menu.addItem(editItem)
        let editMenu = NSMenu(title: "Правка"); editItem.submenu = editMenu
        editMenu.addItem(withTitle: "Копировать", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Вставить", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Вырезать", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Выделить всё", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        NSApp.mainMenu = menu
        let viewItem = NSMenuItem(title: "Вид", action: nil, keyEquivalent: ""); menu.addItem(viewItem)
        let viewMenu = NSMenu(title: "Вид"); viewItem.submenu = viewMenu
        viewMenu.addItem(withTitle: "Обновить окно", action: #selector(reload), keyEquivalent: "r")
        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self; web.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 940), styleMask: [.titled,.closable,.miniaturizable,.resizable], backing: .buffered, defer: false)
        window.title = "Kadr · AI Model Studio"
        window.minSize = NSSize(width: 760, height: 680)
        window.contentView = web; window.center(); window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        connect(attempt: 0)
    }

    func connect(attempt: Int) {
        var request = URLRequest(url: address.appendingPathComponent("api/bootstrap")); request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { data, response, error in
            DispatchQueue.main.async {
                if let data = data, let value = try? JSONSerialization.jsonObject(with: data) as? [String:Any], value["app"] as? String == "kadr-ai-studio" {
                    self.web.load(URLRequest(url: self.address)); return
                }
                if attempt == 0 { self.startServer() }
                if attempt < 30 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.connect(attempt: attempt + 1) }
                } else {
                    let alert = NSAlert(); alert.messageText = "Не удалось запустить редактор"
                    alert.informativeText = "Проверьте зависимости Python и журнал data/server.log. Папка Kadr.app должна находиться рядом с server.py."
                    alert.runModal()
                }
            }
        }.resume()
    }

    func startServer() {
        let candidates = [root.appendingPathComponent(".venv/bin/python"), root.deletingLastPathComponent().appendingPathComponent(".venv/bin/python")]
        guard let python = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0.path) }) else { return }
        let process = Process(); process.executableURL = python
        process.arguments = [root.appendingPathComponent("server.py").path]
        process.currentDirectoryURL = root
        let data = root.appendingPathComponent("data")
        try? FileManager.default.createDirectory(at: data, withIntermediateDirectories: true)
        let log = data.appendingPathComponent("server.log")
        if !FileManager.default.fileExists(atPath: log.path) { FileManager.default.createFile(atPath: log.path, contents: nil) }
        if let handle = try? FileHandle(forWritingTo: log) { handle.seekToEndOfFile(); process.standardOutput = handle; process.standardError = handle }
        do { try process.run(); server = process } catch { NSLog("Kadr server launch failed: %@",error.localizedDescription) }
    }

    @objc func about() {
        let alert = NSAlert(); alert.messageText = "Kadr · AI Model Studio 0.4"
        alert.informativeText = "Собственный редактор 2D-сеток, ключевых форм и анимаций. AI: fal и ComfyUI. Экспорт: PSD, PNG, motion3.json, exp3.json. Полный проект сохраняется в ZIP. Локальный сервис продолжает генерацию после закрытия окна."
        alert.runModal()
    }
    @available(macOS 12.0, *)
    func webView(_ webView: WKWebView, requestMediaCapturePermissionFor origin: WKSecurityOrigin, initiatedByFrame frame: WKFrameInfo, type: WKMediaCaptureType, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        guard origin.host == "127.0.0.1", origin.port == 18321, frame.isMainFrame, type == .camera else { decisionHandler(.deny); return }
        NSApp.activate(ignoringOtherApps: true)
        AVCaptureDevice.requestAccess(for: .video) { allowed in
            DispatchQueue.main.async { decisionHandler(allowed ? .grant : .deny) }
        }
    }
    @objc func reload() { web.reload() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel(); panel.allowsMultipleSelection = parameters.allowsMultipleSelection; panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { response in completionHandler(response == .OK ? panel.urls : nil) }
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if navigationAction.shouldPerformDownload { decisionHandler(.download); return }
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.host == "127.0.0.1" && url.port == 18321 { decisionHandler(.allow) }
        else { decisionHandler(.cancel) }
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let folder = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first!
        let file = folder.appendingPathComponent("Kadr-" + UUID().uuidString.prefix(6) + "-" + suggestedFilename)
        completionHandler(file)
    }
    func downloadDidFinish(_ download: WKDownload) { }
}
let app = NSApplication.shared
let delegate = StudioApp()
app.delegate = delegate
app.run()

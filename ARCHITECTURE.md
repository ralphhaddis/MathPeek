# MathPeek architecture and interaction contract

## Decision
A native AppKit accessory application previews explicitly copied text from a global shortcut, a menu bar request, a selection-free General macOS Service (`Preview Clipboard in MathPeek`), or a change to the general clipboard while the preview panel is already visible. Global hotkeys use Carbon `RegisterEventHotKey` on `GetEventDispatcherTarget()` (which does not intercept general keystrokes or require Accessibility permission), and the `NSServices` entry omits `NSSendTypes` and always reads `NSPasteboard.general` so highlighted text selections are never passed or rendered without an explicit copy. The existing terminal tool remains separate.

A true NSPopover needs an anchor view owned by our application; it cannot attach directly to another app's selection. Use a floating NSPanel with the system popover material, positioned near the pointer and constrained to the current screen. Do not pretend to know the selection's exact bounds.

## Interaction
- Copy text (`⌘C`) and press `⌃⌥⌘L` (configurable under Global Shortcut in the menu bar), choose **Preview Clipboard**, or invoke the **Preview Clipboard in MathPeek** General Service; or keep the panel visible to watch for later copied clipboard changes. Highlighting text alone never invokes MathPeek—the watcher filters out terminal copy-on-selection writes (such as iTerm2's default `CopySelection`) as well as concealed/transient/auto-generated pasteboard items.
- Each new clipboard passage adds an entry to a bounded in-memory history; the newest result is brought into view. The 40 most recent entries are retained for the app session. The list scrolls vertically to revisit earlier formulas.
- A new invocation cancels the previous request. New clipboard updates are debounced briefly so rapid copies render only the latest one. Clipboard updates can refresh a visible preview, but cannot show a hidden panel.
- The panel is placed on its first presentation and stays where the user leaves it. Rendered images fit the history card width; earlier entries are reached by scrolling vertically.
- An explicit shortcut, Service, or menu request opens and activates the panel with a quiet loading state (or a prompt if the clipboard is empty), then displays the result or a concise error. Clipboard monitoring only updates a panel that is already visible without stealing focus. Rendering never runs on the UI thread.
- `Esc`, `⌘W`, or the close button hides the panel; `⌘R` refreshes from the clipboard; `⌘C` copies source; `⌘Q` quits. Clipboard updates do not show a hidden panel again. Clicking another app leaves it visible. No Keep Open toggle is needed.
- Closing invalidates the request before terminating the worker. Late results must never reopen the panel.
- The panel is draggable, remains within the visible screen, and supports horizontal/vertical scrolling for large expressions. Its size is capped so it does not obscure the desktop.
- System text color and popover material follow appearance changes. A transparent, high resolution monochrome formula is displayed as a template image. Source copying is explicit; clipboard contents are never replaced automatically.
- Empty input and invalid syntax produce readable in-panel messages. Errors never launch Terminal or dump compiler logs.

## Components
1. AppKit menu, Carbon global hotkey (`GetEventDispatcherTarget()`), selection-free General Service, or filtered clipboard watcher passes an immutable text snapshot from `NSPasteboard.general`.
2. Preview controller owns panel, request identity, history and cancellation. The panel stays visible when another app becomes active; the close button hides it.
3. Python worker normalizes fenced/math-wrapped input, compiles with existing BasicTeX, rasterizes and crops a transparent image. Arguments are passed as arrays; input is never shell code.
4. Each job uses a unique temporary directory, deleted by its Swift owner on completion/cancellation. Worker stdout is a bounded JSON result; compiler output goes to a temporary file.

## Input and failure policy
- This preview handles formula fragments and common display environments, not arbitrary complete TeX projects. Full documents remain the CLI's job.
- Limit input to 32 KB. Reject empty input, full documents, unmatched outer delimiters, `^^` TeX control-character escapes, and file/process/info/programming primitives outside the formula use case (`\@*input`, `\pdfmdfivesum`, `\pdffilesize`, `\pdfcreationdate`, `\pdftexbanner`, `\pdftexversion`, `\pdfximage`, `\RequirePackage`, `\scantokens`, `\let`, `\everypar`, `\expandafter`, etc.).
- Disable shell escape and restrict TeX input/output paths. A macOS sandbox profile denies network access and writes outside the per-render directory, and blocks reads from the user's home folder as well as `/Users`, `/Volumes`, `/tmp`, and `/private/tmp`. Only the absolute TeX/PDF tools needed for a render can execute.
- Run each renderer process with a hard timeout and process group; terminate/kill the group on cancellation. Limit CPU, file output and open files in worker children; cap raster pixels. macOS does not provide a working address-space limit here, so memory is not fully sandboxed.
- Missing dependencies, bad TeX, blank pages, oversized raster images, and multi-page output produce actionable errors. Never silently discard later pages.
- No automatic package installs or network access. The clipboard watcher is enabled by default while the app runs and can be disabled from the menu bar; it records only in-memory history, never a file. Worker crash is a preview error, not an app crash.
- Only the current request may publish results. Temporary files are cleaned on success/error/cancellation; a forced app kill may leave OS temporary files.

## Compatibility and limits
The general clipboard is the only text input path; the menu action, Carbon global hotkey, and General Service (`Preview Clipboard in MathPeek`) all read `NSPasteboard.general`, while omitting `NSSendTypes` on `NSServices` ensures macOS never passes uncopied selection data. No hover or Force Click interception. Panel behavior in full-screen Spaces, multiple screens, changing appearance, VoiceOver, and Reduce Transparency needs interactive QA. The renderer uses macOS `sandbox-exec`, which Apple has deprecated; rendering stops if that sandbox is unavailable. It narrows file and network access but cannot guarantee zero vulnerabilities, especially in TeX and PDF parsing libraries.

## Verification
Compile native app; exercise real renderer with bare math, inline/display wrappers, aligned environments, malformed input, empty input, missing commands, infinite expansion, and cancellation. Check transparent image and result dimensions. Confirm menu and clipboard paths. Manual UI checks must be reported separately from automated checks.

## Research
- https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/SysServices/Articles/providing.html
- https://developer.apple.com/library/archive/documentation/Cocoa/Conceptual/SysServices/Articles/overview.html
- https://developer.apple.com/documentation/AppKit/NSPopover
- https://developer.apple.com/documentation/appkit/nsvisualeffectview/material-swift.enum/popover

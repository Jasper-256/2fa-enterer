# 2FA autofill

Caps Lock + `\` uses Hyperkey's Control + Command + Shift + Option modifiers
to trigger the background helper. It reads digits from screen rectangle
`(674, 442, 162, 40)` and types individual digit keys with 2 ms between characters.

The helper registers the hotkey with macOS and posts digit events after Hyperkey
remapping, using independent modifier state. OCR stays initialized, capture runs
only when triggered, and entry is cancelled if the foreground app changes.
Raycast and Shortcuts are not required.
The helper runs as a background-only process, without a Dock icon or app window.

## Manage the helper

Run from this folder:

```sh
/opt/homebrew/bin/python3.9 manage_helper.py install
/opt/homebrew/bin/python3.9 manage_helper.py status
/opt/homebrew/bin/python3.9 manage_helper.py restart
/opt/homebrew/bin/python3.9 manage_helper.py stop
/opt/homebrew/bin/python3.9 manage_helper.py uninstall
```

`install` registers this repo's script, starts it, and enables its LaunchAgent
for future logins. The helper runs directly from this folder; no script is copied
elsewhere. Run `restart` after editing the script.

After moving this folder, run `install` from its new location to update the
startup path. Keep the folder available locally at login.

Logs and the process lock live in the ignored `.runtime/` folder. The only
installed configuration outside this repo is
`~/Library/LaunchAgents/com.jasper.2fa-autofill.plist`.

The existing Python environment needs `mss`, PyObjC, and Homebrew Tesseract.
Grant `python3.9` Accessibility and Screen Recording access in macOS settings.
Logs contain no codes or screenshots.

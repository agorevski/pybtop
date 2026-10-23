# Security Review: pybtop

Scope: entire tracked codebase (no staged or unstaged changes at review time).
Status: all findings are fixed on `main`. Each fix is listed under Remediation below.

## Findings

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| 1 | 🟡 MEDIUM | `pybtop/collectors/processes.py`, `pybtop/ui/pen.py`, `pybtop/render/ansi.py` | processes.py:67-73; pen.py:102-107; ansi.py:87 and render path | Terminal escape injection via process `cmdline`/`comm` rendered without sanitization | 8/10 |

### 1. Terminal escape injection via process names (MEDIUM, 8/10)

**Where:**
- Source: `read_command()` in `pybtop/collectors/processes.py:67-73` converts `/proc/<pid>/cmdline` to text, replacing only NUL bytes. `parse_stat()` takes `comm` verbatim.
- Sink: `Pen.write()` in `pybtop/ui/pen.py:102` and `Canvas.put()` in `pybtop/render/ansi.py:87` store characters unchanged. `Canvas.render()` writes them directly to stdout.
- Status line and confirmation prompts echo process names unfiltered (`pybtop/app.py`, around line 604 and the signal confirmation prompt).

**Impact:** `/proc/<pid>/cmdline` is world-readable by default. An unprivileged local user can start a process whose argv contains control sequences (for example OSC 52 clipboard writes, OSC 0/2 title changes, or cursor and screen manipulation). When another user, such as an administrator, views the process list in pybtop, those sequences reach their terminal. Terminals that honor OSC 52 can have their clipboard overwritten, and other sequences can spoof parts of the UI.

**Suggested fix:** Sanitize at the data source and at the render choke point.

```python
# pybtop/render/ansi.py (or a small shared helper module)
def printable(text: str) -> str:
    return "".join(ch if ch.isprintable() else "?" for ch in text)

# Canvas.put: sanitize before storing
def put(self, row, col, text, fg=None, bg=None, bold=False):
    text = printable(text)
    ...

# pybtop/collectors/processes.py
def read_command(pid: int) -> str:
    ...
    return printable(raw.replace(b"\0", b" ").decode("utf-8", errors="replace").strip())

# parse_stat(): name = printable(text[open_paren + 1 : close_paren])
```

Apply the same filter in `Pen.write` so every rendered string is covered: interface names, mount points, sensor labels, GPU names, status messages, and config-derived strings in the options menu.

## Hardening recommendations (not vulnerabilities)

1. **Central sanitization.** Enforce `printable()` in `Canvas.put` and `Pen.write`, as described above. This covers network interface names (`pybtop/ui/btop_boxes.py`, around line 291), disk and mount names, hwmon labels, and the NVML GPU name.

2. **PID reuse before kill.** `_send_signal` in `pybtop/app.py:601-603` signals a PID chosen before the confirmation prompt. The process may have exited and the PID been reused, and pybtop may run with elevated privileges. Re-verify the process (start time or owner) immediately before `os.kill`, or use `os.pidfd_open` with `signal.pidfd_send_signal` (Python 3.9+).

3. **Theme name used as a path.** `find_theme_file` in `pybtop/theme.py:96` joins the `color_theme` config value into a file path. Reject names containing `/`, `\`, or `..`, or use `os.path.basename`. Risk is low because the config belongs to the user.

4. **Config write permissions.** `write_config` in `pybtop/config.py:65` writes with the default umask, follows symlinks, and is not atomic. Write to a temp file in the same directory with mode `0o600`, then `os.replace`. Create the config directory with mode `0o700`.

5. **Unclamped `update_ms` from config.** `pybtop/app.py:73` reads the config value without the bounds the CLI applies. A value of 0 causes a busy loop. Clamp it with `MIN_UPDATE_MS` and `MAX_UPDATE_MS`, as is done at `pybtop/app.py:445`.

## Checked with no issues found

- No use of `eval`, `exec`, `pickle`, `yaml` loaders, `subprocess`, or `os.system`.
- Config parsing is line-based with no code execution.
- `/proc` and `/sys` reads use fixed paths and attacker-independent writes.
- NVML ctypes calls load fixed library names.
- No hardcoded secrets or credentials in tracked files.

## Remediation

| # | Item | Fix | Where |
|---|------|-----|-------|
| 1 | Terminal escape injection (finding 1) | `printable()` replaces control and format characters in `Canvas.put`, `Pen.write`, and at the `/proc` readers. pybtop's own SGR sequences are not affected. | `pybtop/textsafe.py`, `pybtop/render/ansi.py`, `pybtop/ui/pen.py`, `pybtop/collectors/processes.py` |
| 2 | PID reuse before kill (hardening 2) | A pidfd is opened for the PID (syscall 434, since `os.pidfd_open` is missing from this Python), the start time is checked, and the signal is sent through the pidfd with `signal.pidfd_send_signal`. The pidfd keeps naming the same process, so no race remains. Falls back to the start-time check on kernels without pidfd support. | `pybtop/app.py`, `pybtop/collectors/processes.py` |
| 3 | Theme name used as a path (hardening 3) | Names containing `/`, `\`, NUL, or `..` are rejected; the Default theme is used instead. | `pybtop/theme.py` |
| 4 | Config write permissions (hardening 4) | New config directories are created with mode 0700 and files with 0600. Writes go through a temp file and `os.replace`, follow symlinks, and keep an existing file's mode. | `pybtop/config.py` |
| 5 | Unclamped `update_ms` (hardening 5) | Config values are clamped with the CLI bounds through `clamp_update_ms`. | `pybtop/app.py` |

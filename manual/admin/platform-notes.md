---
id: admin.platform-notes
title: Platform notes
audience: admin
order: 30
summary: What differs on Linux, macOS, Windows and WSL.
related: [admin.install-and-versions, admin.files-and-paths]
---

## Here, now {#here-now}

Baton runs on Linux, macOS, native Windows and WSL, and its tests run on Linux and Windows. These are the differences that matter.

## All platforms {#all}

- Paths are stored in POSIX form; backslashes are accepted on input.
- Text is UTF-8 without a byte-order mark and with LF line endings. A BOM is tolerated when reading.
- Git runs with explicit settings, so your own `core.autocrlf` does not change Baton's results. `baton init` writes `.baton/.gitattributes` with `* -text`, so hash-chained logs and vendored recipes are checked out byte for byte everywhere. `baton check` reports the rule missing.
- Directories are created `0700` on POSIX, and with user-only permissions on Windows where possible.

## Windows {#windows}

- Coding-assistant programs are often npm `.cmd` shims run through `cmd.exe`, which ends an argument at a newline and expands `%VAR%`. Prompts passed on a command line are therefore one line with none of `% ^ & | < >`.
- Script checks and hooks run under `cmd.exe /d /s /c`. Write their commands for the shell your project uses.
- A file another process has open cannot be replaced or deleted. Baton retries briefly where it must, so a short delay is not a fault.
- A supervisor runs without opening a console window, and survives the terminal that started it closing.

## WSL {#wsl}

- Keep repositories on the Linux filesystem, not under `/mnt/c`.
- `baton ui` asks the Windows side to open the page in your browser. If it cannot, it prints the link.

## macOS and Linux {#posix}

Scripts and hooks run under `/bin/sh`. No shebang is relied on; `baton` and `python -m baton` are the entry points.

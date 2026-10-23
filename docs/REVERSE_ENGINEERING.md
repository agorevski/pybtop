# Reverse engineering btop++ 1.3.0

Target: `/usr/bin/btop` (btop++ 1.3.0, x86-64 ELF, PIE, stripped, dynamically linked against
libstdc++, libm, libgcc_s and libc; it `dlopen`s `libnvidia-ml.so`, `librocm_smi64.so` and
`libcuda.so`). Its shipped themes live in `/usr/share/btop/themes`.

## Method and tools

| Route | Used for | Result |
|---|---|---|
| REA (`open_binary`, `binary_session`) | Decompilation | **Not available**: no Ghidra, Hopper, IDA or Kuna provider was configured, and none was installed. No pseudocode was produced. |
| Upstream source, btop v1.3.0 (Apache-2.0), read via `raw.githubusercontent.com` | Box geometry and drawing rules (`btop_draw.cpp`, `btop.cpp`, `btop_tools.cpp`, `btop_collect.cpp`) | Rules are recorded with line numbers in `files/src-notes/` and were checked against captures of the installed binary. |
| `strings`, `readelf`, `objdump` | String table, sections, disassembly spot checks | Config keys, theme keys, UI and error strings, the built-in Default palette |
| `strace -f` under a pseudo-terminal | Data sources | Every `/proc`, `/sys`, `/etc` path read and the NVML device nodes |
| Pseudo-terminal + `pyte` (VT100 emulator) | UI geometry, colours, key behaviour | Screen dumps at 80x24, 120x40, 160x50; raw byte streams; per-key effects |
| Isolated `XDG_CONFIG_HOME` runs | Config generation, validation, CLI | Default `btop.conf`, bad-input handling, exit codes, log messages |
| Busy-loop comparison | Process CPU% scale | btop and pybtop both show about 2.7% for one busy core on a 36-core machine |

The user's own `~/.config/btop/` was never written to. Every observation run used an isolated home.

## Data sources (strace)

| Path | Used for |
|---|---|
| `/proc/stat` | Aggregate and per-core CPU jiffies |
| `/proc/meminfo` | Total, free, available, cached, swap |
| `/proc/uptime`, `/proc/loadavg`, `/proc/cpuinfo` | Uptime, load average, CPU model and frequency fallback |
| `/proc/<pid>/stat`, `/proc/<pid>/cmdline`, owner of `/proc/<pid>` | Process table (state, threads, CPU ticks, RSS, command, user) |
| `/sys/class/net/<if>/statistics/{rx,tx}_bytes`, netlink | Interface list and throughput |
| `/proc/self/mounts`, `/etc/mtab`, `/etc/fstab`, `statvfs` | Disks |
| `/sys/block/*/stat` | Disk I/O counters |
| `/sys/class/hwmon/*` | CPU and NVMe temperatures |
| `/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq` | Frequency |
| `/sys/class/power_supply/*` | Battery (not present on the reference machine) |
| `/proc/spl/kstat/zfs/arcstats` | ZFS ARC (absent on the reference machine) |
| `libnvidia-ml.so` via `dlopen` and `/dev/nvidia*` | GPU utilisation, memory, temperature, power, clocks |
| `/etc/passwd` (NSS) | User names |

## Formulas

- **Aggregate and per-core CPU %**: `100 * (Δtotal − Δidle) / Δtotal`, with idle = idle + iowait and total = all jiffy fields, clamped to 0–100. The same formula is applied to each `cpu`/`cpuN` line.
- **Process CPU %**: process tick delta over wall-clock elapsed time × `CLK_TCK`, expressed per core, divided by the core count unless per-core mode (`c`) is on. Verified against btop with a busy loop.
- **Memory used**: `MemTotal − MemAvailable`. Cached: `Cached + SReclaimable`.
- **Network rate**: counter delta over elapsed time for the chosen interface. The default interface is the one carrying the default route in `/proc/net/route`.
- **Auto-scaled network graphs**: the top of the scale starts at 10 KiB/s and steps by powers of ten to cover the recent peak. Fixed mode uses `net_download` / `net_upload` in mebibits.
- **Sizes**: binary units by default, three significant characters (`13.0 GiB`, `238 GiB`, `1.78 TiB`), `0 Byte` for zero.

## Configuration

- Generated defaults (`btop.conf`) list 75 keys. The defaults are reproduced in `pybtop/defaults.py`.
- Invalid values reset to defaults and the file is rewritten on exit. Unknown keys and malformed lines are ignored.
- Theme lookup: built-in `Default` and `TTY` names first, then the user theme directory (`$XDG_CONFIG_HOME/btop/themes`, or `~/.config/...` when unset), then system directories. A user file overrides a system file of the same name.
- Theme values are `#RRGGBB`, `#BW` (grey), or a decimal `R G B` triple. Empty means the terminal default. Only the first quoted value is used; keys are case-sensitive; duplicates use the last value.
- The built-in `Default` palette is verified cell by cell for most keys (see `pybtop/theme.py`). Keys that were not visible in any capture come from the binary's literal table.
- The built-in `TTY` theme is a table of fixed 16-colour SGR codes (`\x1b[37m`, `\x1b[41m`, ...), not hex. It is used for the `TTY` name and whenever tty mode is on, and ignores `-lc`. The table matches btop 1.3.0's `TTY_theme` in `src/btop_theme.cpp`; the binary carries the same strings.

## Presets

- Format: spaces separate presets, commas separate entries, entries are `box:P:G` (`box` ∈ cpu/mem/net/proc, `P` ∈ 0/1 for position, `G` ∈ default/braille/block/tty). At most nine presets.
- Position 1 moves the CPU box to the bottom, the process box to the left, and MEM below NET.
- `-p 0` shows all boxes with default settings and ignores `presets` and `shown_boxes`. `-p N` above the preset count clamps to the last preset.
- Preset `-p` selection is not written to the config.

## Command line

Arguments are processed in order. `-h` and `-v` exit immediately. The error messages are printed to stdout, with exit code 1:

- `ERROR: Update option needs an argument`
- `ERROR: Invalid update rate`
- `ERROR: Preset option needs an argument.`
- `ERROR: Preset option only accepts an integer value between 0-9.`
- ` Unknown argument: X` followed by ` Use -h or --help for help.`

Checks then run in this order: UTF-8 locale (unless `--utf-force`), then a tty. Without a UTF-8 locale the message is `ERROR: No UTF-8 locale detected!`. `-u` clamps to [100, 86400000] ms and is saved to the config; btop aborts with `std::out_of_range` on overflow, which pybtop does not reproduce.

## Terminal behaviour

- The minimum size is 80x24. Smaller terminals show a centred `Terminal size too small:` message with the actual and required sizes.
- Geometry (btop `Draw::calcSizes`, GPU build, with N GPUs and H rows): CPU box height `max(8, ceil(H·32/100)) + N` when it fits, else without the `+ N`. MEM and NET share the left column with width `round(W·45/100)`; MEM height is `ceil(H·68/100) − cpu_h`, NET takes the remaining rows. PROC is the right-hand column.
- The CPU sub-box, per-core columns, GPU columns and brief rows follow `Cpu::draw`: core columns use widths `(8+6T)`, `(15+6T)` or `(21+12T)` per core depending on how many fit, and per-core rows are skipped when the sub-box is narrow (see files/src-notes/box_rules.md).
- Frames use truecolor SGR sequences (`38;2;R;G;B`) when `truecolor` is on, otherwise 256-colour sequences.
- btop wraps frames in synchronized-output sequences (`?2026`) and enters the alternate screen (`?1049`). pybtop enters the alternate screen and restores the terminal on exit.

## Keys

Verified on screen or through the saved config: `1`–`5`, `d`, `i`, `p`/`P`, `+`/`-`, arrows, PgUp/PgDn, Home/End, Left/Right sort cycling (`pid → program → arguments → threads → user → memory → cpu direct → cpu lazy`), `r`, `e`, `c`, `%`, `f`/`/`, `b`/`n`, `a`, `y`, `h`/`?`, `o`, `q`, `Esc`.

Unverified in btop, so implemented here as stated in the README: `t`, `k`, `s` dialogs (no dialog was observed in the captures) and Enter.

## Known gaps in the reference observations

- Menu item labels never appeared in the byte stream; the `m` menu is therefore this project's own.
- `F1`/`F2` did not open help or options with the tested escape sequences; `F1`/`F2` are still accepted here.
- The `@` title on the CPU meter box is btop's Xeon CPU-name quirk (`get_cpuName` returns the word after `CPU`), reproduced here. The `L 2 2 1` abbreviation is the load-average label for narrow sub-boxes (`L`, `LAV:`, `Load AVG:`), also reproduced.
- Battery, ZFS, disk I/O graphs and the per-process detail view were not exercised: the reference machine has no battery or ZFS, and the process detail view was not reached safely.

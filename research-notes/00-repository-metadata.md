# Repository metadata snapshot

Snapshot time: 2026-07-29 UTC. All changing values below are time-stamped rather
than presented as permanent facts.

| Field | Value | Evidence / qualification | Confidence |
|---|---|---|---|
| Canonical repository | `https://github.com/OpenTTD/OpenTTD` | Official GitHub organization and repository README | High |
| Default branch | `master` | GitHub REST `default_branch` and `git ls-remote --symref ... HEAD` | High |
| Pinned analysis commit | `29f808ef0022064e6d9a83c8476d1e0f4686af86` | Local `git rev-parse HEAD`; authored commit title `Codechange: add Bool and Label aliases to VarFileType to denote intent` | High |
| Latest official stable release at snapshot | `15.3`, published 2026-04-04 | GitHub releases API and official download page | High |
| Primary language | C++ | GitHub language statistics and `CMakeLists.txt`; current standard is C++20 | High |
| GitHub repository `size` | 718,131 KiB | REST metadata's repository-size field, not a working-tree or release size | High |
| Local shallow checkout | 69 MiB | `du -sh`, depth-one clone; not comparable to full history | High |
| Tracked files | 1,879 total; 1,531 under `src/` | `git ls-files` at pinned commit | High |
| C/C++ source/header lines | 476,054 | `wc -l` over tracked `*.c/*.cc/*.cpp/*.h/*.hpp`; physical lines, not logical LOC | High |
| Registered local tests | 98 | CTest in the verified dedicated configuration | High |
| Platforms claimed supported | Linux SDL/OpenGL/non-OpenGL, macOS universal/Cocoa, Windows Win32 GDI/OpenGL | `README.md` §1.3 | High |
| Repository creation timestamp | 2018-04-06 | GitHub REST metadata; this reflects this GitHub repository/migration, not the historical origin of OpenTTD | High |

## GitHub language bytes

The official GitHub languages endpoint reported:

| Language | Bytes |
|---|---:|
| C++ | 13,249,884 |
| C | 1,417,718 |
| CMake | 206,329 |
| Squirrel | 178,090 |
| Objective-C++ | 86,550 |
| HTML | 13,769 |
| Objective-C | 10,425 |
| Awk | 6,841 |
| PowerShell | 6,115 |
| JavaScript | 4,463 |
| Python | 4,378 |
| Shell | 2,672 |
| Batch | 595 |
| Dockerfile | 334 |

These are GitHub Linguist byte counts, not source-line counts and not dependency
weights.

## License identification caveat

GitHub's repository API returned `NOASSERTION`, likely because the root license is
named `COPYING.md` and the tree contains multiple exceptions. The project itself
unambiguously states GNU GPL version 2 for OpenTTD, except specifically identified
third-party material (`README.md` §3 and `COPYING.md`). Representative source
headers grant version 2 without “or later”; for engineering decisions, treat the
project core as **GPL-2.0-only**, subject to legal review and file-specific notices.

## Issue-history signal

The repository contains imported historical FlySpray issues as well as current
GitHub issues; the `flyspray` label explicitly marks imports. At this snapshot,
GitHub search reported 8,885 issues in total and 222 open. Label counts included
480 `bug`, 92 `component: pathfinder`, 1,409 `component: interface`, and 378
`component: NewGRF` issues. These counts are only orientation signals: labels are
not exhaustive or mutually exclusive, and issue search changes continuously.

The label taxonomy itself identifies persistent maintenance boundaries relevant
to a reimplementation: interface, pathfinder, NewGRF, AI/GameScript, OpenGL,
platform-specific Linux/macOS/Windows, security, and regression. The final risk
analysis uses source architecture and tests as primary evidence; issue counts do
not prove subsystem quality or complexity by themselves.


#!/usr/bin/env python3
"""Deterministic fake of the dedicated content-console subset used by M14 tests."""

from __future__ import annotations

import io
import os
import pathlib
import sys
import tarfile


PRIMARY_ID = 16381015
LIBRARY_ID = 42
PRIMARY_LOCAL_ID = "4b524132"
PRIMARY_SERVER_ID = "3241524B"
LIBRARY_LOCAL_ID = "4c494231"
LIBRARY_SERVER_ID = "3142494C"


def add_file(archive: tarfile.TarFile, path: str, value: bytes) -> None:
    member = tarfile.TarInfo(path)
    member.size = len(value)
    member.mode = 0o644
    archive.addfile(member, io.BytesIO(value))


def build_archives(root: pathlib.Path, mode: str) -> None:
    ai_root = root / "content_download/ai"
    library_root = ai_root / "library"
    ai_root.mkdir(parents=True)
    library_root.mkdir()
    declared_version = 2 if mode == "declared_version_drift" else 3
    declared_name = "Kraken AI Two" if mode == "declared_name_drift" else "KrakenAI2"
    primary_filename = (
        f"{PRIMARY_LOCAL_ID}-Kraken_AI2-v3.tar"
        if mode == "archive_label_variant"
        else f"{PRIMARY_LOCAL_ID}-KrakenAI2-3.tar"
    )
    with tarfile.open(ai_root / primary_filename, mode="w") as archive:
        if mode == "unsafe":
            add_file(archive, "../escape", b"unsafe\n")
        else:
            add_file(
                archive,
                "KrakenAI2-3/info.nut",
                (
                    'class KrakenInfo extends AIInfo {\n'
                    f' function GetName() {{ return "{declared_name}"; }}\n'
                    f' function GetVersion() {{ return {declared_version}; }}\n'
                    ' function GetAuthor() { return "Fixture Author"; }\n'
                    ' function GetAPIVersion() { return "1.3"; }\n'
                    ' function GetShortName() { return "KRA2"; }\n'
                    ' function CreateInstance() { return "Kraken"; }\n'
                    '}\n'
                ).encode(),
            )
        add_file(archive, "KrakenAI2-3/main.nut", b"class Kraken extends AIController {}\n")
        if mode != "no_license":
            add_file(archive, "KrakenAI2-3/LICENSE", b"GPL-3.0-only fixture\n")
    with tarfile.open(library_root / f"{LIBRARY_LOCAL_ID}-FixtureLib-1.tar", mode="w") as archive:
        add_file(archive, "FixtureLib-1/library.nut", b"class FixtureLib {}\n")
        if mode != "no_license":
            add_file(archive, "FixtureLib-1/COPYING", b"ISC fixture\n")


def main() -> int:
    mode = os.environ.get("FAKE_CONTENT_MODE", "success")
    config_index = sys.argv.index("-c") + 1
    artifact_root = pathlib.Path(sys.argv[config_index]).resolve().parent
    if mode == "startup_stall":
        for _ in sys.stdin:
            pass
        return 0
    print("[fixture] Starting dedicated server, version fixture-15.3", flush=True)
    print("FAKE CONTENT READY", flush=True)
    selected = False
    company = False
    date_day = 1
    for raw_command in sys.stdin:
        command = raw_command.strip()
        if command == "content update ai":
            print("Content server connection established.", flush=True)
        elif command.startswith("content state "):
            print("id, type, state, name", flush=True)
            server_id = "00000000" if mode == "wrong_uid" else PRIMARY_SERVER_ID
            print(
                f"{PRIMARY_ID}, AI, Not selected, KrakenAI2, {server_id}, "
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                flush=True,
            )
        elif command == f"content select {PRIMARY_ID}":
            selected = mode != "unselectable"
        elif command == "content select":
            print("id, type, state, name", flush=True)
            if selected:
                print(
                    f"{PRIMARY_ID}, AI, Selected, KrakenAI2, {PRIMARY_SERVER_ID}, "
                    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                    flush=True,
                )
                print(
                    f"{LIBRARY_ID}, AI library, Dep Selected, FixtureLib, {LIBRARY_SERVER_ID}, "
                    "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB",
                    flush=True,
                )
        elif command == "content download":
            build_archives(artifact_root, mode)
            print(f"Completed download of {PRIMARY_ID}.", flush=True)
            print(f"Completed download of {LIBRARY_ID}.", flush=True)
        elif command == "rescan_ai":
            pass
        elif command == "list_ai":
            print("List of AIs:", flush=True)
            print("    KrakenAI2 (v3): Fixture runtime AI.", flush=True)
        elif command == 'start_ai "KrakenAI2.3"':
            company = True
            if mode == "runtime_crash":
                print("Your script made an error: fixture crash", flush=True)
        elif command == "companies":
            if company:
                road = 0 if mode == "runtime_inactive" else 1
                print(
                    "#:1(Blue) Company Name: 'Fixture Transport'  Year Founded: 1950  "
                    f"Money: 100000  Loan: 0  Value: 10  (T:0, R:{road}, P:0, S:0) AI",
                    flush=True,
                )
        elif command == "getdate":
            print(f"Date: 1950-01-{date_day:02d}", flush=True)
            date_day += 1
        elif command == "save v2-qualification":
            save_root = artifact_root / "save"
            save_root.mkdir(exist_ok=True)
            (save_root / "v2-qualification.sav").write_bytes(b"fixture savegame\n")
            print("Saving map...", flush=True)
            print("Map successfully saved to 'v2-qualification.sav'.", flush=True)
        elif command == "load v2-qualification.sav":
            print("FAKE LOAD COMPLETE", flush=True)
        elif command == "quit":
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

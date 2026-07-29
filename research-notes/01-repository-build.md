# OpenTTD repository, build, platform, and test cartography

## Scope and evidence baseline

This report describes the authoritative checkout at `/workspace/openttd-upstream` only. The checkout was read at commit `29f808ef0022064e6d9a83c8476d1e0f4686af86` (`Codechange: add Bool and Label aliases to VarFileType to denote intent`), on `master`, with no tracked modifications before analysis. It is a shallow checkout, so the measurements below describe the working snapshot rather than the complete historical repository.

| Finding | Evidence | Interpretation | Confidence |
| --- | --- | --- | --- |
| The analyzed revision is exactly the requested revision. | Git object `29f808ef0022064e6d9a83c8476d1e0f4686af86`; source-version generation is implemented by `cmake/scripts/FindVersion.cmake`. | All source conclusions are pinned, not inferred from a moving branch. | High |
| The snapshot contains 1,879 tracked files occupying about 57 MiB, excluding Git history. | `git ls-files` and tracked-file disk measurement; the checkout contains `.git/shallow`. | This is a reproducible checkout metric, not the size of the full GitHub repository. | High |
| No Git submodules are required by this snapshot. | Empty `git submodule status`; bundled dependencies are listed under `src/3rdparty/CMakeLists.txt`. | A source checkout is self-contained apart from system/vcpkg libraries and runtime base sets. | High |

## Fact sheet

| Attribute | Finding | Evidence | Confidence |
| --- | --- | --- | --- |
| Product | Transport-management simulation game; it aims to mimic Transport Tycoon Deluxe while extending it. | `README.md`, section `1.0 About`. | High |
| Source license | GNU GPL version 2.0 for the OpenTTD distribution, with separately licensed bundled third-party code. | `README.md`, section `3.0 Licensing`; `COPYING.md`; third-party license files under `src/3rdparty/`. | High |
| Build version in this checkout | CMake project version `16.0`; generated revision observed as `20260729-master-g29f808ef00`. | Root `CMakeLists.txt`, `project(...)`; `cmake/scripts/FindVersion.cmake`, observed isolated configure. | High |
| Primary language | C++20. | Root `CMakeLists.txt`, `project(... LANGUAGES CXX)` and `CMAKE_CXX_STANDARD 20`; 557 tracked `.cpp`, 631 `.h`, and 180 `.hpp` files. | High |
| Supporting languages | Objective-C++ for macOS, C inside vendored Squirrel, Squirrel (`.nut`) for AI/Game Script content and regressions, CMake, Python automation, NFO base-set sources, and JavaScript/HTML for the Emscripten shell. | Root `CMakeLists.txt`, `enable_language(OBJCXX)`; `src/3rdparty/squirrel/`; `bin/ai/`, `bin/game/`, `regression/`; `cmake/`; `.github/*.py`; `media/baseset/`; `os/emscripten/`. | High |
| Build tools | CMake with CTest and CPack; native helper executables `strgen` and `settingsgen`; Make or Ninja as generator backends; vcpkg is the declared cross-platform dependency manifest. | Root `CMakeLists.txt`; `src/strgen/CMakeLists.txt`; `src/settingsgen/CMakeLists.txt`; `vcpkg.json`; `COMPILING.md`. | High |
| Principal supported desktop platforms | Linux, macOS, and Windows. | `README.md`, section `1.3 Supported platforms`; OS entry points under `src/os/{unix,macosx,windows}/`. | High |
| Additional maintained build | Emscripten/WebAssembly, including browser persistence and PR previews. | Root `CMakeLists.txt`, `if(EMSCRIPTEN)` block; `os/emscripten/README.md`; `.github/workflows/ci-emscripten.yml`; `.github/workflows/preview-build.yml`. | High |
| Automated tests | Catch2 unit tests plus four saved-game/Squirrel regression suites, all registered in CTest. | Root `CMakeLists.txt`, targets `openttd_test` and `catch_discover_tests`; `src/tests/CMakeLists.txt`; `regression/CMakeLists.txt`; `cmake/CreateRegression.cmake`. | High |
| Release packaging | CPack produces platform-dependent bundles: macOS Bundle, Windows ZIP/optional NSIS, and Linux DEB/RPM/TXZ; Emscripten emits HTML/JS/WASM/data; source releases emit `.tar.xz` and `.zip`. | `cmake/InstallAndPackage.cmake`; root `CMakeLists.txt`, Emscripten block; `.github/workflows/release-source.yml`. | High |

## Top-level repository map

| Path | Role | Evidence | Confidence |
| --- | --- | --- | --- |
| `CMakeLists.txt` | Root build graph, feature detection, executable/test targets, platform linking, CTest, and packaging entry. | Symbols/targets `openttd_lib`, `openttd`, `openttd_test`, `find_version`; includes `Options`, `SourceList`, `InstallAndPackage`. | High |
| `README.md`, `COMPILING.md`, `CONTRIBUTING.md`, `CODINGSTYLE.md`, `COPYING.md` | User overview, build instructions, contribution process, style rules, and license. | Named documents and their top-level headings. | High |
| `.github/` | Pull-request CI, scheduled CI, CodeQL, documentation checks, release jobs, platform-store upload, and helper scripts. | `.github/workflows/ci-build.yml`, `codeql.yml`, `release.yml`, `upload-*.yml`; `.github/*.py`. | High |
| `bin/` | Runtime data copied/generated into a build: built-in AI/Game Script compatibility files and command scripts. It is not the executable-output directory. | `bin/CMakeLists.txt`, which adds `ai` and `game`; `cmake/InstallAndPackage.cmake`, `install(DIRECTORY ... ai game ... bin/scripts)`. | High |
| `cmake/` | Custom find modules, source-list aggregation, regression integration, feature/options logic, package generators, and code/data generation scripts. | `cmake/SourceList.cmake`, `Options.cmake`, `CreateRegression.cmake`, `InstallAndPackage.cmake`, `scripts/*.cmake`. | High |
| `docs/` | Developer/administrator and format documentation, including savegames, multiplayer, cargo distribution, directory layout, fonts, and the Unix man page. | `docs/savegame_format.md`, `multiplayer.md`, `linkgraph.md`, `directory_structure.md`, `openttd.6`. | High |
| `media/` | Application branding/installer assets, desktop integration, and source material for OpenTTD's small supplemental base set. | `media/CMakeLists.txt`; `media/openttd.*`; `media/baseset/`. | High |
| `os/` | Packaging and distribution integration outside the C++ platform layer: Emscripten shell/toolchain, Steam/GOG metadata, Windows installer/signing, and macOS bundle/notarization assets. | `os/emscripten/`, `os/steam/`, `os/gog/`, `os/windows/`, `os/macosx/`. | High |
| `regression/` | Four deterministic end-to-end script regressions, each with a saved game, Squirrel program, and expected output. | `regression/{regression,stationlist,gs,gs_compat}/`; `regression/CMakeLists.txt`. | High |
| `src/` | Main C++ source tree, generated-code consumers, bundled libraries, unit tests, platform drivers, and most domain/UI code. | `src/CMakeLists.txt` and child `CMakeLists.txt` files. | High |

### Source-tree subsystem map

The directory boundaries below are useful ownership boundaries, but most are **not link-time component boundaries**. `cmake/SourceList.cmake:add_files` appends their sources to one `openttd_lib` object library, which both the game and test executables consume. This makes the production program substantially monolithic despite its source organization. Confidence: **High**.

| Path | Responsibility and representative symbols | Confidence |
| --- | --- | --- |
| `src/*.cpp`, `src/*.h` | Broad domain layer and much of the UI: world, construction commands, vehicles, towns, industries, stations, orders, economy, cargo, windows, viewport, and application orchestration. Representative symbols include `StateGameLoop`/`GameLoop` (`src/openttd.cpp`), `Map::Allocate` (`src/map.cpp`), `Vehicle` (`src/vehicle_base.h`), `Town` (`src/town.h`), `Industry` (`src/industry.h`), `Station` (`src/station_base.h`), and command handlers such as `CmdBuildSingleRail` (`src/rail_cmd.cpp`). | High |
| `src/core/` | Generic containers, typed IDs/pools, random numbers, geometry/math, strings, and UTF-8 utilities. Representative sources: `pool_type.hpp`, `random_func.cpp`, `string_*`, `utf8.cpp`. | High |
| `src/timer/` | Tick, economy-date, calendar-date, realtime, and window timer domains. Representative types: `TimerGameTick`, `TimerGameEconomy`, `TimerGameCalendar`, `TimerGameRealtime`. | High |
| `src/network/` | Multiplayer client/server synchronization, command transport, admin/content/coordinator/STUN/TURN, crypto, and socket abstractions. Representative symbols: `NetworkGameLoop`, `NetworkExecuteLocalCommandQueue`; `src/network/core/` contains protocol/socket primitives. | High |
| `src/pathfinder/yapf/` | YAPF vehicle pathfinding and rail reservation/cost caches for rail, road, and ship movement. Representative symbols: `CYapfT`, `CYapfRail*`, `YapfRoadVehicleChooseTrack`, `YapfShipChooseTrack`. | High |
| `src/linkgraph/` | Cargo-distribution graphs and asynchronous flow calculation. Representative types: `LinkGraph`, `LinkGraphJob`, `LinkGraphSchedule`; `LinkGraphJob` can start a worker thread. | High |
| `src/saveload/` | Chunked serialization, per-domain save/load descriptors, compatibility tables, migrations, and asynchronous save coordination. Representative symbol: `SaveOrLoad`; representative handlers: `MAPSChunkHandler`, `PLYRChunkHandler`, `STNNChunkHandler`. | High |
| `src/script/` | Bundled Squirrel integration, common AI/Game Script runtime, scanners, generated API binding support, and public script API. Representative symbols: `ScriptInstance::GameLoop`, `ScriptObject::ScriptDoCommandHelper`. | High |
| `src/ai/`, `src/game/` | AI and Game Script specializations over the common script runtime. Representative symbols: `AI::GameLoop`, `Game::GameLoop`, scanners/config/instances. | High |
| `src/newgrf/` plus root `src/newgrf*.cpp` | NewGRF parsing/evaluation and feature-specific adaptation. The split between directory and root files is historical/organizational rather than a strict API boundary. | High |
| `src/video/`, `src/blitter/`, `src/spriteloader/`, `src/fontcache/`, `src/widgets/` | Video/event loops and OS backends, pixel conversion/blitting, sprite decoding, font backends, and declarative widget structures. Representative symbols: `VideoDriver::Tick`, `VideoDriver_SDL_Base::MainLoop`, `BlitterFactory`, `ViewportDoDraw`. | High |
| `src/sound/`, `src/music/` | Pluggable sound/music drivers with null, SDL/Allegro, Cocoa, Win32/XAudio2, FluidSynth, and external MIDI implementations as platform/features allow. | High |
| `src/os/` | C++ platform abstraction and process entry points. Representative entry files: `unix_main.cpp`, `win32_main.cpp`, `osx_main.cpp`. | High |
| `src/lang/` | Translation source text and CMake rules that run `strgen` to produce `.lng` files and `generated/table/strings.h`. | High |
| `src/settingsgen/`, `src/strgen/` | Native host tools for generated settings tables and localized string tables. These can be built separately for cross-compilation using `OPTION_TOOLS_ONLY`/`HOST_BINARY_DIR`. | High |
| `src/table/` | Static/generated lookup tables and settings definitions used throughout the executable. | High |
| `src/3rdparty/` | Vendored fmt, Squirrel, MD5, Monocypher, nlohmann/json, Catch2, selected ICU/OpenGL support, and social-integration API headers. | High |
| `src/tests/` | Catch2 test translation units and mocks. Representative entry symbol: `CATCH_CONFIG_MAIN` in `src/tests/test_main.cpp`. | High |

## Build architecture

```text
settingsgen + strgen (native host tools)
       |            \
       |             -> compiled language files + generated/table/strings.h
       -> generated settings tables
                         |
all selected production sources -> openttd_lib (OBJECT library)
                         |                     |
                         |                     -> openttd_test + Catch2 test sources
                         -> openttd + generated media/base-set dependencies
                                      |
                                      -> install rules -> CPack platform bundle
```

| Build finding | Evidence | Interpretation | Confidence |
| --- | --- | --- | --- |
| Out-of-source builds are mandatory. | Root `CMakeLists.txt`, guard comparing `CMAKE_SOURCE_DIR` and `CMAKE_BINARY_DIR`. | Use `cmake -S ... -B ...`; a source-tree `CMakeCache.txt` is rejected. | High |
| The real minimum CMake version is 3.17. | Root `CMakeLists.txt`, `cmake_minimum_required(VERSION 3.17)`. | The root requirement controls even though helper subprojects declare 3.16. | High |
| Debug is the default configuration and C++ extensions are disabled. | Root `CMakeLists.txt`, default `CMAKE_BUILD_TYPE Debug`, `CMAKE_CXX_EXTENSIONS NO`. | Performance measurements should use `RelWithDebInfo` or `Release`, not an unqualified configure. | High |
| The main code is accumulated into one object library. | Root `CMakeLists.txt`, `add_library(openttd_lib OBJECT ...)`; `cmake/SourceList.cmake`, `_add_files_tgt`/`add_files`. | Directory boundaries do not prevent cross-subsystem includes or calls. | High |
| The game and unit-test executables reuse the production object library. | Root `CMakeLists.txt`, `target_link_libraries(openttd openttd_lib ...)` and `target_link_libraries(openttd_test PRIVATE openttd_lib)`. | Tests exercise production objects directly but also inherit a large link/build surface. | High |
| Platform `main` is linked only into `openttd`, not `openttd_lib`. | `src/os/unix/CMakeLists.txt`, `target_sources(openttd ... unix_main.cpp)`; equivalent Windows/macOS rules. | `openttd_test` can provide Catch2's `main` without a duplicate process entry. | High |
| Cross-compilation is two-stage. | Root `CMakeLists.txt`, `OPTION_TOOLS_ONLY` and `HOST_BINARY_DIR`; `src/lang/CMakeLists.txt`; `os/emscripten/README.md`. | Build `tools` natively, then point the target build at their exported CMake targets. | High |
| Build outputs are generated from source inputs. | Targets `find_version`, `language_files`, `table_strings`; `src/settingsgen/CMakeLists.txt`; `src/lang/CMakeLists.txt`. | A raw subset of `.cpp` files is not enough to compile the program; generated headers/data are part of the build contract. | High |

## Dependencies

### Configure/build requirements

| Scope | Requirement | Evidence | Confidence |
| --- | --- | --- | --- |
| All builds | CMake 3.17+, a C++20 compiler supported by CMake, and a working thread library. | Root `CMakeLists.txt`, `cmake_minimum_required`, `CMAKE_CXX_STANDARD`, `find_package(Threads REQUIRED)`; `COMPILING.md`, `Supported compilers`. | High |
| Linux GUI | At least one of SDL2 or Allegro. | Root `CMakeLists.txt`, fatal check `if(NOT SDL2_FOUND AND NOT Allegro_FOUND)` when Unix/non-Apple/non-dedicated. | High |
| Linux dedicated | No GUI/font stack is required when configured with `OPTION_DEDICATED=ON`; Threads and core compiler/build requirements remain. | Root `CMakeLists.txt`, dependency discovery inside `if(NOT OPTION_DEDICATED)` and unconditional `Threads REQUIRED`; `COMPILING.md`, CMake options. | High |
| macOS | Objective-C++, AudioToolbox, AudioUnit, Cocoa, and QuartzCore are hard requirements. | Root `CMakeLists.txt`, `enable_language(OBJCXX)`, `find_library(...)`, and fatal checks. | High |
| Windows/MSVC | Visual Studio 2022+ is documented; CMake requires `Editbin` for MSVC and links Win32 system libraries. | `COMPILING.md`, Windows section; root `CMakeLists.txt`, `find_package(Editbin REQUIRED)` and Windows link list. | High |
| Emscripten | A native host-tools build plus the pinned Emscripten environment; current CI uses `emscripten/emsdk:6.0.1`. | `os/emscripten/README.md`; `.github/workflows/ci-emscripten.yml`; root `CMakeLists.txt`, `HOST_BINARY_DIR`. | High |

### Optional/feature dependencies

| Library | Purpose / consequence | Evidence | Confidence |
| --- | --- | --- | --- |
| zlib | Old savegames, content downloads, and heightmaps; encouraged. | `COMPILING.md`, `Required/optional libraries`; root `CMakeLists.txt`, `find_package(ZLIB)`/`link_package`. | High |
| liblzma | Modern savegame compression; absence means most recent savegames cannot be opened. | `COMPILING.md`; root `CMakeLists.txt`, `find_package(LibLZMA)` and encouraged link. | High |
| liblzo2 | Very old pre-0.3.0 savegames. | `COMPILING.md`; root `CMakeLists.txt`, `find_package(LZO)`. | High |
| libpng | Screenshots and heightmaps. | `COMPILING.md`; root `CMakeLists.txt`; conditional `src/screenshot_png.cpp`. | High |
| libcurl | Content downloads on non-Windows, non-Emscripten targets. | Root `CMakeLists.txt`, platform `find_package(CURL)` and `link_package(CURL ENCOURAGED)`; `COMPILING.md`. | High |
| Breakpad | Optional crash minidumps except on Emscripten. | Root `CMakeLists.txt`, `find_package(unofficial-breakpad)`; `COMPILING.md`. | High |
| FreeType/Fontconfig, HarfBuzz/ICU | Generic-font discovery/rendering and complex/right-to-left text; HarfBuzz is disabled without ICU i18n. | Root `CMakeLists.txt`, discovery and warning checks; `COMPILING.md`. | High |
| FluidSynth, OpusFile, SDL2/Allegro audio | Optional music/sound backends and Opus loading. | Root `CMakeLists.txt`; `src/music/CMakeLists.txt`; `src/sound/CMakeLists.txt`. | High |
| OpenGL/SSE | Optional accelerated display/blitter paths. | Root `CMakeLists.txt`, OpenGL/SSE discovery; `src/video/CMakeLists.txt`; `src/blitter/CMakeLists.txt`. | High |
| GRFCodec/NFORenum | Rebuild supplemental graphics; its presence can modify generated `.grf` files in the source checkout. | `COMPILING.md`, `Compilation of base sets`; root `CMakeLists.txt`, `find_package(Grfcodec)`. | High |

`vcpkg.json` pins a baseline and declares breakpad, curl, dbus, fontconfig, freetype, harfbuzz, ICU, liblzma, libpng, LZO, OpusFile, SDL2, and zlib with platform selectors. Linux CI deliberately disables manifest integration and uses system packages for most libraries, installing only Breakpad from vcpkg (`.github/workflows/ci-linux.yml`, `Setup vcpkg`/`Install dependencies`). Confidence: **High**.

### Runtime data dependency

A successful compile is not by itself a playable desktop installation: a usable base graphics set is still needed. `README.md` section `1.4` offers OpenGFX/OpenSFX/OpenMSX, and startup scans base sets in `openttd_main` (`src/openttd.cpp`, `BaseGraphics::FindSets`, `BaseSounds::FindSets`, `BaseMusic::FindSets`). The build does provide `NoSound` and `NoMusic` metadata, so external sound/music content is optional (`media/baseset/CMakeLists.txt`, generation inputs `no_sound.obs` and `no_music.obm`). CI downloads only OpenGFX before running the game/regressions (`.github/workflows/ci-linux.yml`, `Get OpenGFX`, with equivalent Windows/macOS steps). Confidence: **High**.

## Platforms and backends

| Platform | Process/video path | CI/release evidence | Status interpretation | Confidence |
| --- | --- | --- | --- | --- |
| Linux | `src/os/unix/unix_main.cpp:main` -> SDL2 or Allegro video; optional OpenGL; dedicated/null variants available. | `.github/workflows/ci-build.yml` tests Clang, GCC+SDL2, and GCC dedicated; `.github/workflows/release-linux.yml` builds a dependency-bundled generic package. | First-class supported. | High |
| macOS | `src/os/macosx/osx_main.cpp:main`; Cocoa video/sound/music and Objective-C++ bridge. | PR CI covers arm64 Debug and RelWithDebInfo; nightly covers x86_64; release combines arm64+x86_64, signs/notarizes, and emits universal app bundles. | First-class supported, universal release. | High |
| Windows | `src/os/windows/win32_main.cpp:WinMain`; Win32 GDI/OpenGL video and native audio/network libraries. | PR CI covers x86/x64 MSVC; release covers x86/x64/arm64 and optional NSIS/signing. MinGW x86_64 runs nightly. | First-class supported; broader release matrix than PR CI. | High |
| Emscripten | Unix-style `main`; SDL/Emscripten video; browser `requestAnimationFrame`; IDBFS; HTML/JS/WASM/data output. | `.github/workflows/ci-emscripten.yml` on every main CI orchestration and label-triggered preview deployment. | Actively built, but not listed in README's supported-platform list. | High |
| BSD family | Generic Unix code contains explicit FreeBSD/OpenBSD/NetBSD branches. | `src/os/unix/unix.cpp`; no corresponding workflow under `.github/workflows/`. | Source-level accommodation, explicitly not actively tested/maintained by README. | Medium |
| Haiku | Conditional libraries are linked. | Root `CMakeLists.txt`, `if(HAIKU)`; no checkout CI workflow. | Residual/possible port, not a stated currently supported platform. | Medium |

## Entry points and runtime loop

### Bootstrap chain

```text
Unix main / macOS main / Windows WinMain
    -> crash-log initialization + process RNG seed
    -> openttd_main(arguments)
         -> parse modes/drivers/config/savegame arguments
         -> DeterminePaths + LoadFromConfig
         -> language/font/window/base-set initialization
         -> DriverFactoryBase::SelectDriver(video/sound/music)
         -> NetworkStartUp + bootstrap/content handling
         -> temporary world + title game
         -> VideoDriver::MainLoop
              -> timed VideoDriver::GameLoop / VideoDriver::Tick
                   -> global GameLoop
                        -> NetworkGameLoop OR StateGameLoop
```

| Runtime finding | Evidence | Interpretation | Confidence |
| --- | --- | --- | --- |
| Platform entry points normalize arguments, seed RNG, initialize crash logging, and converge on one application function. | `src/os/unix/unix_main.cpp:main`, `src/os/macosx/osx_main.cpp:main`, `src/os/windows/win32_main.cpp:WinMain`; all call `openttd_main`. | OS-specific process setup is thin compared with the shared bootstrap. | High |
| `openttd_main` owns command-line parsing and subsystem startup. | `src/openttd.cpp:openttd_main`; symbols `CreateOptions`, `DeterminePaths`, `LoadFromConfig`, `DriverFactoryBase::SelectDriver`, `NetworkStartUp`, `HandleBootstrap`. | This is the application composition root. | High |
| The selected video driver owns the outer event loop. | `src/openttd.cpp:openttd_main` calls `VideoDriver::GetInstance()->MainLoop`; virtual API in `src/video/video_driver.hpp`; implementations in `src/video/*.cpp`. | Headed, dedicated, null, and browser loops share the simulation entry but control event/sleep behavior differently. | High |
| Normal game ticks target 27 ms (about 37 ticks/s) and are adjusted by game speed. | `src/gfx_type.h`, `MILLISECONDS_PER_TICK = 27`; `src/video/video_driver.hpp:VideoDriver::GetGameInterval`; `src/video/video_driver.cpp:VideoDriver::GameLoop`. | The outer simulation is fixed-step scheduled against a monotonic clock, with fast-forward scaling. | High |
| SDL can run simulation on a separate game thread while drawing/events remain in the outer loop. | `src/video/sdl2_v.cpp:VideoDriver_SDL_Base::MainLoop`; `src/video/video_driver.cpp:StartGameThread`, `GameThread`, `Tick`, and game-state mutex use. | Rendering and simulation scheduling are distinct but still coordinate over shared mutable game state. | High |
| Browser execution is event-driven. | `src/video/sdl2_v.cpp:VideoDriver_SDL_Base::MainLoop`, `emscripten_set_main_loop_arg`; root Emscripten link settings. | Native sleep loops are replaced by `requestAnimationFrame`. | High |
| Dedicated execution has no draw thread and starts/loads a network game. | `src/video/dedicated_v.cpp:VideoDriver_Dedicated::MainLoop`; symbols `StartNewGameWithoutGUI`, `Tick`, `SleepTillNextTick`. | This is the closest existing headless runtime path for simulation experiments. | High |

### Shared game-loop dispatch

`src/openttd.cpp:GameLoop` first handles scans, completed async saves, realtime timers, mode switches, background network work, and debug callbacks. It then selects `NetworkGameLoop` for multiplayer or `StateGameLoop` for local simulation, followed by palette, sound, music, and social callbacks. Confidence: **High**.

`src/openttd.cpp:StateGameLoop` is the authoritative local tick sequence. When not paused, it enters persistent-storage game-loop mode; animates tiles; advances calendar/economy/tick timers; calls `RunTileLoop`, `CallVehicleTicks`, and `CallLandscapeTick`; runs AI and Game Scripts; updates landscaping limits; dispatches window tick events; and advances news. Representative implementations are `src/landscape.cpp:RunTileLoop`/`CallLandscapeTick`, `src/vehicle.cpp:CallVehicleTicks`, `src/ai/ai_core.cpp:AI::GameLoop`, and `src/game/game_core.cpp:Game::GameLoop`. Confidence: **High**.

Drawing is scheduled separately by `src/video/video_driver.cpp:VideoDriver::Tick`: poll events, process input/command queue, update windows, populate sprites, and call the backend `Paint`. World viewport composition proceeds through `src/viewport.cpp:ViewportDoDraw`/`ViewportAddLandscape`, and dirty-buffer drawing through `src/gfx.cpp:DrawDirtyBlocks`. Confidence: **High**.

## High-level dependency map

```text
OS entry + configuration/data discovery
                  |
                  v
        driver factories (video/audio/music)
                  |
      +-----------+------------------+
      |                              |
input/windows/scripts          VideoDriver scheduler
      |                              |
      v                              v
typed Command<T>::Post/Do       GameLoop dispatch
      |                              |
      +-> network command queue <----+----> multiplayer client/server
      |                              |
      v                              v
command handlers ------------> StateGameLoop/timers
      |                              |
      +--------> world pools/map <---+-- tile, vehicle, landscape ticks
                     |               +-- AI/Game Script ticks
                     +-> pathfinder / cargo link graph
                     +-> save/load chunk handlers
                     +-> viewport/sprite/blitter -> video backend
```

| Dependency edge | Evidence | Confidence |
| --- | --- | --- |
| UI/script actions enter a common typed command layer that can validate, post, network, and execute mutations. | `src/command_func.h`, `CommandHelper::InternalPost`; `src/command.cpp`; examples such as `src/rail_cmd.cpp:CmdBuildSingleRail`; script bridge `src/script/api/script_object.hpp:ScriptDoCommandHelper`. | High |
| Multiplayer synchronizes commands through queues before executing state ticks. | `src/network/network_command.cpp`, `_local_wait_queue`, `_local_execution_queue`, `NetworkExecuteLocalCommandQueue`; `src/network/network.cpp:NetworkGameLoop`. | High |
| Domain objects are global typed pools over a compact tile map. | `src/map.cpp:Map::Allocate`; `src/map_func.h:Tile`, `TileBase`, `TileExtended`; pools/types in `vehicle_base.h`, `town.h`, `industry.h`, `company_base.h`, `station_base.h`, `order_base.h`, `cargopacket.h`. | High |
| Movement delegates route choice to YAPF; cargo distribution uses link-graph jobs. | `src/pathfinder/yapf/yapf_common.hpp:CYapfT`; `yapf_rail.cpp`, `yapf_road.cpp`, `yapf_ship.cpp`; `src/linkgraph/linkgraphschedule.cpp:SpawnNext`/`JoinNext`. | High |
| Persistence directly traverses domain state using per-domain chunk handlers and compatibility descriptions. | `src/saveload/saveload.cpp:SaveOrLoad`; `src/saveload/map_sl.cpp`, `company_sl.cpp`, `vehicle_sl.cpp`, `station_sl.cpp`; `src/saveload/compat/`. | High |
| Rendering reads the same shared state under coordination with the game thread. | `src/video/video_driver.cpp:Tick` game-state mutex; `src/viewport.cpp:ViewportDoDraw`; domain draw procs registered through landscape/tile code. | High |

Architectural caution: this is a call/dependency map, not a claim of strict layering. The one-object-library build, global pools/state, and root-level cross-domain source files mean many dependencies are compile-time and bidirectional. Evidence: root `CMakeLists.txt:openttd_lib` and `cmake/SourceList.cmake:add_files`. Confidence: **High**.

## Tests and verification infrastructure

### Unit tests

| Finding | Evidence | Interpretation | Confidence |
| --- | --- | --- | --- |
| Catch2 supplies the test process entry and assertion framework. | `src/tests/test_main.cpp`, `CATCH_CONFIG_MAIN`; vendored `src/3rdparty/catch2/`. | No external Catch2 installation is needed. | High |
| CMake discovers individual Catch cases and exposes them to CTest. | Root `CMakeLists.txt`, `catch_discover_tests(openttd_test)`; `cmake/Catch.cmake`. | `ctest` can schedule/report cases independently rather than treating the binary as one opaque test. | High |
| The snapshot has 95 syntactic Catch test declarations across 17 files containing tests. | `src/tests/` and `src/3rdparty/icu/tests/`, `TEST_CASE`/`TEST_CASE_METHOD` declarations. | Declaration count is a source metric; generated CTest count can differ if template tests expand. | High |
| Current unit coverage is utility-heavy rather than a comprehensive gameplay suite. | `src/tests/CMakeLists.txt`: strings, math/bit operations, tile areas/slopes, network crypto, script JSON conversion, iterator/flat-set/history, and widget descriptions. | Core vehicle/economy/pathfinding/save-load behavior is not visibly represented by dedicated Catch files in this snapshot. This is a scope observation, not proof those behaviors are untested elsewhere. | Medium |

### Regression tests

Four suites are registered: `regression`, `stationlist`, `gs`, and `gs_compat` (`regression/CMakeLists.txt`). `cmake/CreateRegression.cmake:create_regression` registers each as serial CTest tests and as verbose custom targets. `cmake/scripts/Regression.cmake` launches the actual `openttd` binary against a checked-in `.sav`, null sound/music/video, a 30,000-tick limit, and script debug output, then normalizes and compares the result with `result.txt`. This provides deterministic executable-level coverage of the scripting interfaces and saved scenarios. Confidence: **High**.

### Continuous integration

| Gate | What it verifies | Evidence | Confidence |
| --- | --- | --- | --- |
| Main build matrix | Emscripten; Linux Clang, GCC SDL2, and GCC dedicated; macOS arm64 Debug/RelWithDebInfo; Windows MSVC x86/x64. | `.github/workflows/ci-build.yml` and reusable `ci-*.yml` workflows. | High |
| Scheduled extensions | macOS x86_64 and MinGW UCRT64 x86_64. | `.github/workflows/ci-nightly.yml`. | High |
| Tests | Native Linux/macOS/Windows/MinGW builds run `ctest` with a 120-second per-test timeout; Linux also asserts that building/testing did not modify tracked files. | `.github/workflows/ci-{linux,macos,windows,mingw}.yml`. | High |
| Static security analysis | C++ CodeQL on master pushes/PRs, filtering tables, generated code, and tests before SARIF upload. | `.github/workflows/codeql.yml`, steps `Initialize CodeQL`, `Filter out table & generated code`, `Upload results`. | High |
| Documentation | Builds source, AI, and Game Script Doxygen and rejects new warnings relative to the base revision. | `.github/workflows/docs-checker.yml`. | High |
| Repository conventions | Commit message/hooks, file descriptions, unused localized strings, and missing script mode checks. | `.github/workflows/commit-checker.yml`, `file-descriptions.yml`, `unused-strings.yml`, `script-missing-mode-enforcement.yml`. | High |
| Browser smoke/build | Emscripten compilation and label-triggered hosted preview artifact. | `.github/workflows/ci-emscripten.yml`, `preview.yml`, `preview-build.yml`, `preview-publish.yml`. | High |

No tracked workflow or configuration for clang-format, clang-tidy, Cppcheck, sanitizer builds, coverage collection, or Valgrind was found. Formatting guidance is human/tool-editor oriented through `.editorconfig` and `CODINGSTYLE.md`. This negative finding is bounded to the pinned checkout; external project infrastructure may exist. Confidence: **Medium**.

## Packaging and distribution

`cmake/InstallAndPackage.cmake` installs the executable, compiled languages, generated baseset data, built-in AI/Game Script compatibility content, runtime scripts, documentation, and platform desktop assets. It configures CPack as follows:

| Target | Bundle | Evidence | Confidence |
| --- | --- | --- | --- |
| macOS | CPack `Bundle` (application/DMG), with release workflow also generating a notarized ZIP and a universal arm64+x86_64 binary. | `cmake/InstallAndPackage.cmake`, Apple branch; `.github/workflows/release-macos.yml`. | High |
| Windows | ZIP always; NSIS optionally for tagged stable releases; x86/x64/arm64 release jobs and code signing. | `cmake/InstallAndPackage.cmake`, Windows branch; `.github/workflows/release-windows.yml`. | High |
| Linux/Unix | DEB for Debian-like, RPM for Fedora/RHEL-like, TXZ for Arch/generic/non-FHS or dependency-bundled builds. | `cmake/InstallAndPackage.cmake`, Unix distribution detection. | High |
| Emscripten | `openttd.html`, `.js`, `.wasm`, and `.data`, with assets preloaded and IDBFS persistence. | Root `CMakeLists.txt`, Emscripten block; `.github/workflows/preview-build.yml`. | High |
| Source | Versioned `.tar.xz` and `.zip`, plus an internal `.tar.gz` passed between release jobs. | `.github/workflows/release-source.yml`, `Create bundles`. | High |

The release orchestrator also has upload workflows for the OpenTTD CDN, Steam, GOG, and Windows Store (`.github/workflows/release.yml`, `upload-cdn.yml`, `upload-steam.yml`, `upload-gog.yml`, `upload-windows-store.yml`). These are distribution automation, not build prerequisites. Confidence: **High**.

## Important-file index

| File | Why it matters | Key symbol/section | Confidence |
| --- | --- | --- | --- |
| `README.md` | Product/platform/runtime-data/license overview. | Sections `1.3`, `1.4`, `3.0`. | High |
| `COMPILING.md` | User-facing dependency and configure instructions. | `Required/optional libraries`, platform sections, `CMake Options`. | High |
| `CMakeLists.txt` | Authoritative build contract. | `project`, `openttd_lib`, `openttd`, `openttd_test`, dependency discovery, Emscripten block. | High |
| `vcpkg.json` | Declared dependency baseline and platform selectors. | `dependencies`, `builtin-baseline`. | High |
| `cmake/Options.cmake` | Dedicated/tools/docs/assert/package switches and directory defaults. | `set_options`, `set_directory_options`, `add_definitions_based_on_options`. | High |
| `cmake/SourceList.cmake` | Explains why source modules all feed the same object library. | `_add_files_tgt`, `add_files`, `add_test_files`. | High |
| `cmake/InstallAndPackage.cmake` | Install layout and CPack formats. | `install(...)`, `CPACK_GENERATOR` platform branches. | High |
| `src/openttd.cpp` | Shared bootstrap and central game loops. | `openttd_main`, `GameLoop`, `StateGameLoop`, `PostMainLoop`. | High |
| `src/video/video_driver.cpp` | Game-thread scheduling, event/draw cadence, state locking. | `VideoDriver::GameLoop`, `GameThread`, `Tick`, `SleepTillNextTick`. | High |
| `src/video/dedicated_v.cpp` | Headless server loop. | `VideoDriver_Dedicated::MainLoop`. | High |
| `src/command_func.h`, `src/command.cpp` | Typed command validation/post/execute infrastructure. | `CommandHelper::InternalPost` and command execution implementation. | High |
| `src/map.cpp`, `src/map_func.h` | World dimensions and compact per-tile storage. | `Map::Allocate`, `Tile`, `TileBase`, `TileExtended`. | High |
| `src/vehicle.cpp` | Vehicle tick dispatch. | `CallVehicleTicks`, calendar/economy day procedures. | High |
| `src/landscape.cpp` | Incremental tile and landscape updates. | `RunTileLoop`, `CallLandscapeTick`. | High |
| `src/network/network.cpp` | Multiplayer tick routing. | `NetworkGameLoop`. | High |
| `src/network/network_command.cpp` | Deterministic command queues. | `NetworkExecuteLocalCommandQueue`, `NetworkSyncCommandQueue`. | High |
| `src/saveload/saveload.cpp` | Persistence coordinator. | `SaveOrLoad`. | High |
| `src/pathfinder/yapf/yapf_common.hpp` | Shared pathfinder composition. | `CYapfT`. | High |
| `src/linkgraph/linkgraphschedule.cpp` | Background cargo-flow scheduling. | `LinkGraphSchedule::SpawnNext`, `JoinNext`, `Run`. | High |
| `src/tests/test_main.cpp`, `src/tests/CMakeLists.txt` | Unit-test entry and inventory. | `CATCH_CONFIG_MAIN`, `add_test_files`. | High |
| `cmake/scripts/Regression.cmake` | Executable regression harness. | `execute_process` of `openttd`, output normalization/comparison. | High |
| `.github/workflows/ci-build.yml` | Primary platform test matrix. | Jobs `emscripten`, `linux`, `macos`, `windows`. | High |
| `.github/workflows/release.yml` | Release orchestration. | Source/platform build and upload jobs. | High |

## Reproducible build, test, and run instructions

These commands preserve the source checkout by using an external build tree.

### Linux desktop, close to the checked-in CI environment

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  cmake ninja-build g++ \
  liballegro4-dev libcurl4-openssl-dev libfontconfig-dev \
  libharfbuzz-dev libicu-dev liblzma-dev liblzo2-dev \
  libogg-dev libopus-dev libopusfile-dev libsdl2-dev zlib1g-dev

cmake -S /workspace/openttd-upstream \
      -B /tmp/openttd-build \
      -GNinja \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build /tmp/openttd-build --parallel
ctest --test-dir /tmp/openttd-build --output-on-failure --timeout 120
```

The package list is based on `.github/workflows/ci-linux.yml:Install dependencies`; Breakpad is the CI-only exception installed from vcpkg there. A local build may omit Breakpad. Confidence: **High**.

Install OpenGFX before an interactive launch, following `README.md` section `1.4`; CI places it in `~/.local/share/openttd/baseset`. Then run:

```bash
/tmp/openttd-build/openttd
```

Use `-h` to enumerate compiled drivers/content and `docs/openttd.6` for flags. Confidence: **High**.

### Lean Linux dedicated build

```bash
cmake -S /workspace/openttd-upstream \
      -B /tmp/openttd-dedicated \
      -GNinja \
      -DOPTION_DEDICATED=ON \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build /tmp/openttd-dedicated --parallel
ctest --test-dir /tmp/openttd-dedicated --output-on-failure --timeout 120
/tmp/openttd-dedicated/openttd -D
```

The unqualified build is intentional: `regression_files` is an `ALL` target, but CTest does not resolve that target's fixture-copy dependencies when only `openttd` and `openttd_test` are explicitly built (`regression/CMakeLists.txt`; comment in `cmake/CreateRegression.cmake:create_regression`). If named targets are required, also build `regression_files` before `ctest`. `-D` is the documented dedicated-server runtime switch (`docs/openttd.6`; `docs/multiplayer.md`), while `OPTION_DEDICATED=ON` removes GUI dependencies at compile time (`cmake/Options.cmake`; root `CMakeLists.txt`). Confidence: **High**.

### Windows/macOS/Emscripten variations

- Windows: follow `COMPILING.md`, use Visual Studio 2022+ and vcpkg's CMake toolchain/triplet; CI uses Ninja and static x86/x64 triplets (`.github/workflows/ci-windows.yml`). Confidence: **High**.
- macOS: use the vcpkg toolchain and set `CMAKE_OSX_ARCHITECTURES`; release builds native arm64 and x86_64 separately before `lipo` (`.github/workflows/release-macos.yml`). Confidence: **High**.
- Emscripten: follow the two-stage host-tools/target build in `os/emscripten/README.md`, preferably with the pinned image from `os/emscripten/Dockerfile`; serve the build directory over HTTP and open `openttd.html`. Confidence: **High**.

## Observed isolated build check

The source was configured outside the repository with CMake 3.28.3, GNU C++ 13.3, Ninja, `OPTION_DEDICATED=ON`, and `RelWithDebInfo`. The container exported a CUDA-stubs-only `LIBRARY_PATH`, which initially prevented CMake from finding installed liblzma/LZO. Supplying their explicit system paths made configure detect Threads, zlib, liblzma 5.4.5, LZO 2.10, PNG, curl, and SSE; only optional Breakpad, Doxygen, and GRFCodec remained absent. This is an environment-specific discovery issue, not evidence that the repository's find modules are generally broken. Confidence: **High**.

The default build completed and generated `openttd`, `openttd_test`, language/settings outputs, base-set metadata, and regression fixtures. GNU 13.3 emitted one non-fatal `-Wmaybe-uninitialized` warning in `src/road_gui.cpp:BuildRoadToolbarWindow::OnClick` for local `started`; no claim is made here that the warning is a confirmed runtime defect. Confidence: **High** for the warning observation and **Low** for any defect inference.

With OpenGFX 0.6.0 staged in an isolated XDG data directory (the same version/URL used by `.github/workflows/ci-linux.yml`), CTest reported **98/98 passed**: 94 discovered Catch cases and all four executable regression suites, in 3.79 seconds. The first deliberately narrow build of only `openttd`/`openttd_test` confirmed that regression fixtures are not materialized unless the default/`regression_files` target is built, matching the warning in `cmake/CreateRegression.cmake`. Confidence: **High**.

## Discrepancies and cautions

| Discrepancy / caution | Evidence | Assessment | Confidence |
| --- | --- | --- | --- |
| `COMPILING.md` says CMake 3.16 minimum, but the authoritative root requires 3.17. | `COMPILING.md`, `All other platforms`; root `CMakeLists.txt` line `cmake_minimum_required(VERSION 3.17)`. | Documentation is stale; use 3.17+. | High |
| `COMPILING.md` says OpenTTD does not require any listed library, but a Linux GUI configure fails without both SDL2 and Allegro, and Threads is always required. | `COMPILING.md`, end of dependency list; root `CMakeLists.txt`, `find_package(Threads REQUIRED)` and Linux GUI fatal check. | Interpret the prose as optional feature libraries except for a platform backend/core threads; dedicated builds avoid the GUI requirement. | High |
| README's supported-platform list omits the actively compiled Emscripten target. | `README.md`, section `1.3`; `.github/workflows/ci-build.yml` job `emscripten`; `os/emscripten/README.md`. | Web support appears active but is not presented as a mainstream supported release target. | High |
| README mentions BSD may work but is not actively tested; source has explicit BSD branches and CI has none. | `README.md`, section `1.3`; `src/os/unix/unix.cpp`; `.github/workflows/` inventory. | Do not infer support parity from generic Unix compilation. | High |
| Root CMake sets `CMAKE_OSX_DEPLOYMENT_TARGET` to 10.15, while macOS CI/release exports `MACOSX_DEPLOYMENT_TARGET=10.13`. | Root `CMakeLists.txt`; `.github/workflows/ci-macos.yml` and `release-macos.yml` job environment. | The declared deployment floor is inconsistent; actual generated build flags should be inspected on macOS before promising 10.13 compatibility. | Medium |
| Unit tests are discovered individually, but they link the entire production object library and visibly emphasize utilities. | Root `CMakeLists.txt`; `src/tests/CMakeLists.txt`. | A green test run is valuable but is not broad proof of behavioral parity for all simulation subsystems. | High |
| Running CTest after building only named executable targets leaves regression fixtures absent. | `regression/CMakeLists.txt`, `regression_files` is `ALL`; `cmake/CreateRegression.cmake` explicitly notes that `make test` does not resolve dependencies. | Build the default target or `regression_files` before invoking CTest. | High |
| GNU C++ 13.3 warns that `started` may be used uninitialized in the road toolbar click handler. | Observed `RelWithDebInfo` build; `src/road_gui.cpp:BuildRoadToolbarWindow::OnClick`, local `started`. | The build remains successful; inspect control flow before treating this compiler diagnostic as a real bug. | Medium |
| Source modules are organizational, not isolation boundaries. | `cmake/SourceList.cmake:add_files`; root `CMakeLists.txt:openttd_lib`. | Any clean-room or CUDA architecture should not reproduce the monolithic link structure merely because directory names look modular. | High |
| GRFCodec can dirty the source tree during a build. | `COMPILING.md`, `Compilation of base sets`; `cmake/CreateGrfCommand.cmake`. | Disable `GRFCODEC_EXECUTABLE`/`NFORENUM_EXECUTABLE` in the cache when immutable-source builds are required. | High |

## Build/platform/testing implications for a smaller clean-room implementation

These are recommendations, not descriptions of OpenTTD behavior:

1. Keep a single modern CMake project, but enforce real library boundaries (`simulation`, `commands`, `persistence`, `platform`, `renderer`) rather than one object library. The source of the comparison is `cmake/SourceList.cmake:add_files` and root `CMakeLists.txt:openttd_lib`. Confidence in the motivating observation: **High**.
2. Make a renderer-free simulation target first-class, analogous to—but narrower and more testable than—`OPTION_DEDICATED` plus the null drivers (`cmake/Options.cmake`; `src/video/null_v.cpp`, `dedicated_v.cpp`). Confidence: **High**.
3. Preserve the command boundary: deterministic actions should validate and execute through one API, then be recordable/replayable in tests. OpenTTD evidence is `src/command_func.h:CommandHelper` and `src/network/network_command.cpp`. Confidence: **High**.
4. Start CI with Linux GCC+Clang, CPU unit tests, deterministic trace replay, save/load round trips, and one sanitizer job. Add Windows/macOS only after the C ABI/RL wrapper stabilizes. The sanitizer job is a recommendation; the comparison matrix is `.github/workflows/ci-build.yml`. Confidence in the comparison: **High**.
5. Treat external art/data as a separately licensed runtime package. OpenTTD itself separates executable/build data from OpenGFX/OpenSFX/OpenMSX (`README.md`, section `1.4`; `cmake/InstallAndPackage.cmake`). Confidence: **High**.

# OpenTTD documentation, licensing, and clean-room assessment

Authoritative checkout: `/workspace/openttd-upstream` at commit
`29f808ef0022064e6d9a83c8476d1e0f4686af86` (2026-07-29). The checkout was
read-only for this assessment. Paths and symbols below are repository-relative.
The canonical external source is the official
[`OpenTTD/OpenTTD`](https://github.com/OpenTTD/OpenTTD/tree/29f808ef0022064e6d9a83c8476d1e0f4686af86)
repository at that exact commit.

> **Not legal advice.** This is a practical engineering and licensing-risk
> review, not an opinion from counsel. Copyright derivation, GPL/CUDA linking,
> trademark, and clean-room sufficiency are jurisdiction- and fact-specific.
> Get qualified counsel before choosing a non-GPL release strategy or shipping
> CUDA binaries.

> **Clean-room warning.** This report was produced by reading OpenTTD source and
> names implementation symbols. It is a source-derived audit artifact, **not** a
> sanitized clean-room functional specification. If the objective is an
> independently licensed implementation, do not give this report or the
> upstream checkout to the clean implementation team. Legal/specification leads
> should instead produce a separately reviewed, behavior-only specification.

## Bottom line

1. **The direct-port path is available, but it is GPL-2.0.** OpenTTD says the
   distribution is GNU GPL version 2 except listed third-party components, and
   the ordinary source headers say “version 2” without an “or later” grant.
   GPLv2 section 0 expressly treats translation into another language as a
   modification. A source-guided C or CUDA translation therefore needs to be
   treated as GPL-2.0-only unless the relevant copyright holders grant another
   license. Evidence: `README.md`, sections 1.0 and 3.0; `COPYING.md`, sections
   0–3; representative header `src/openttd.cpp`; official
   [README](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/README.md#30-licensing)
   and [GPL text](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COPYING.md#terms-and-conditions-for-copying-distribution-and-modification).
   **Confidence: High.**
2. **A permissive/proprietary implementation requires a genuinely independent
   route, not a cosmetic rewrite.** Renaming symbols, converting C++ syntax to C,
   or moving functions to CUDA does not remove source derivation. A separate
   process wrapper around an unmodified GPL OpenTTD executable is materially
   safer than linking/copying its internals, but exact boundaries still need
   counsel. Evidence: `COPYING.md`, sections 0 and 2, especially the translation,
   whole-work, independent-section, and mere-aggregation language. **Confidence:
   High for the license text; Medium for its application to any proposed
   architecture.**
3. **OpenTTD already has a useful oracle mode.** Its unadvertised `null` video
   driver disables rendering and runs a finite number of ticks; the official
   regression harness invokes `-vnull:ticks=30000`, along with null sound/music.
   This can support local black-box behavior capture without first changing the
   renderer. It is an internal test mechanism, not a documented stable RL API.
   Evidence: `VideoDriver_Null::Start` and `VideoDriver_Null::MainLoop` in
   `src/video/null_v.cpp`; `cmake/scripts/Regression.cmake`, “Run the regression
   test”; official [null driver](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/video/null_v.cpp)
   and [regression invocation](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/cmake/scripts/Regression.cmake#L37-L50).
   **Confidence: High.**
4. **The current code is not a library and has no C/CUDA or RL contract.** The
   build declares only C++ (`LANGUAGES CXX`, C++20), builds the game executable,
   and uses global state through `openttd_main`, `GameLoop`, and
   `StateGameLoop`. The `openttd_lib` CMake object library is an internal build
   target, not a supported ABI. No action/observation/reset/vector-environment
   API is documented. Evidence: root `CMakeLists.txt`, `project`, target creation,
   and linking sections; `openttd_main`, `GameLoop`, and `StateGameLoop` in
   `src/openttd.cpp`; official [root build](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CMakeLists.txt)
   and [main loop](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/openttd.cpp#L1202-L1392).
   **Confidence: High.**
5. **Do not ship original Transport Tycoon assets or assume OpenTTD branding is
   licensed by the code license.** The repository contains metadata for locating
   original TTD files, but directs users to supply those files themselves. It
   also contains OpenTTD-created graphics, fonts, icons, and branding. Copyright
   permission and trademark permission are different; no project trademark
   policy was found in this checkout. Evidence: `README.md`, sections 1.4.1–1.4.3;
   `media/baseset/orig_*.obg`, `orig_*.obs`, and `orig_*.obm`, `[origin]`;
   `media/baseset/OpenTTD-font.md`; `media/openttd.svg`; official
   [asset instructions](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/README.md#141-free-graphics-and-sound-files).
   **Confidence: High on repository contents; Medium on trademark consequences.**

## Documentation claims traced to implementation

| Documented claim | Implementation evidence and assessment | Confidence |
|---|---|---|
| OpenTTD is based on and tries to mimic Transport Tycoon Deluxe (`README.md`, “About”; `CONTRIBUTING.md`, “Project goals”). | The source implements a much-expanded OpenTTD game; no complete TTD executable oracle, cross-engine trace comparator, or formal one-to-one parity specification exists in this repository. The contributor guide explicitly prefers original gameplay but supports extensions through NewGRF/GameScript. Official [README About](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/README.md#10-about) and [project goals](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md#project-goals). Treat “faithful” as a project direction, not a bit-exact contract. | High |
| Every revision can load savegames from every older revision (`README.md`, “Legacy support”). | The compatibility architecture is real: `src/saveload/saveload.h` defines `SaveLoadVersion`; the many `*_sl.cpp` files use `SLE_COND*`, compatibility tables, and version-gated migrations; `src/saveload/afterload.cpp` performs after-load conversions. The public format note says chunk details remain in source. The checked-in regression corpus has only four `.sav` fixtures, so this audit did not find evidence that exhaustively proves the literal “every revision” guarantee. Official [guarantee](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/README.md#131-legacy-support) and [format note](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/docs/savegame_format.md). This is a strong compatibility policy, not a ready-made stable state ABI for a new engine. | High on mechanism; Medium on exhaustive coverage |
| Multiplayer advances a deterministic game state and distributes commands (`docs/desync.md`, “OpenTTD multiplayer architecture”). | `StateGameLoop` advances timers, tiles, vehicles, landscape, AI, and GameScript. `_random` is explicitly for game-state calculations while `_interactive_random` is for non-state work (`src/core/random_func.hpp`, `Randomizer` and the two globals). `NetworkSendCommand`, `NetworkExecuteLocalCommandQueue`, and `DistributeCommandPacket` in `src/network/network_command.cpp` frame and order commands. This is excellent oracle design evidence, but determinism is a maintained invariant with documented failure modes, not mathematical proof across arbitrary ports. Official [desync architecture](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/docs/desync.md#11-openttd-multiplayer-architecture), [RNG interface](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/core/random_func.hpp), and [network command queue](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/network/network_command.cpp#L179-L366). | High |
| A dedicated build omits the GUI (`COMPILING.md`, “CMake Options”). | `OPTION_DEDICATED` is defined in `cmake/Options.cmake::set_options`, adds `DEDICATED`, and suppresses the GUI/audio dependency block in root `CMakeLists.txt`. Runtime `-D` uses `VideoDriver_Dedicated` (`src/video/dedicated_v.cpp`), which still allocates screen memory depending on the selected blitter. Separately, `-v null` selects `VideoDriver_Null` and `Blitter_Null`, which truly avoids rendering. Official [compile option](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COMPILING.md#cmake-options), [option definition](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/cmake/Options.cmake#L42-L68), and [dedicated driver](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/video/dedicated_v.cpp). | High |
| Player actions are validated before mutation and synchronized as commands (`docs/desync.md`). | Modern code uses templated `Command<...>::Post`/`Execute`, not the old `DoCommandP` names. `CommandHelperBase::InternalExecuteValidateTestAndPrepExec` and `InternalExecuteProcessResult` in `src/command.cpp`, together with `CommandHelper` in `src/command_func.h`, perform test/execute handling; network commands then enter the framed queue. Official [command helper](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/command_func.h) and [command implementation](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/command.cpp). This is the natural behavior boundary for an oracle action log, but it is a C++ internal API. | High |
| Desync command logs can replay a run (`docs/debugging_desyncs.md`; `docs/desync.md`). | The debug path remains compiled behind `DEBUG_DUMP_COMMANDS` / `DEBUG_FAILED_DUMP_COMMANDS` in `src/network/network_func.h`; `src/network/network.cpp` reads `commands.log`; `src/debug.cpp` writes `commands-out.log`; `StateGameLoop` and `src/genworld.cpp` create `dmp_cmds_*` saves. The mechanism exists but requires a custom build and uses internal textual/binary formats. Official [debug toggles](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/network/network_func.h#L14-L19) and [debug guide](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/docs/debugging_desyncs.md). | High |
| Development documentation is non-comprehensive (`CONTRIBUTING.md`, “Are there any development docs?”). | Confirmed. Source Doxygen can be generated by root `CMakeLists.txt` targets `docs`/`docs_source`, but architecture, command semantics, complete save chunks, null-driver parameters, and a supported embedding API are not specified in one place. Official [documentation caveat](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md#are-there-any-development-docs). Source and tests must be treated as authoritative for this commit. | High |
| Contributors may fork but significant language ports should be discussed before an upstream PR (`CONTRIBUTING.md`, “Pull requests” and “Project goals”). | The policy explicitly names “porting to a different language” as significant work that should be discussed first and recommends a fork when goals differ. More importantly, the same file prohibits LLM-generated issue/PR text and entire generated code lines. An AI-assisted C/CUDA fork must not be submitted upstream contrary to that policy. Official [pull-request guidance](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md#pull-requests), [AI policy](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md#use-of-ai), and [fork guidance](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md#i-do-not-agree-with-the-goals-of-the-official-branch-what-can-i-do-instead). | High |

## Contradictions, stale guidance, and undocumented behavior

These are documentation defects or evidence limitations at the pinned commit;
they are not claims that the software itself is broken.

| Finding | Evidence | Practical effect | Confidence |
|---|---|---|---|
| **CMake minimum mismatch.** `COMPILING.md` says 3.16; the root build requires 3.17. | `COMPILING.md`, “All other platforms”; `CMakeLists.txt::cmake_minimum_required(VERSION 3.17)`; official [compile guide](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COMPILING.md#all-other-platforms) and [CMake root](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CMakeLists.txt#L1). | Pin at least CMake 3.17; do not automate from the prose minimum. | High |
| **“No libraries required” is too broad.** Threads are required for all normal builds; a non-dedicated Unix GUI requires SDL2 or Allegro; Apple requires four frameworks. The guide also says dedicated builds do not need “the last four” Linux libraries even though the entire GUI dependency block, including SDL, is skipped. | `COMPILING.md`, “Required/optional libraries”; root `CMakeLists.txt`, `find_package(Threads REQUIRED)`, GUI discovery, platform fatal checks, and target link section; official [dependency prose](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COMPILING.md#requiredoptional-libraries). | Derive the container/toolchain manifest from CMake and `vcpkg.json`, not solely `COMPILING.md`. | High |
| **Release assertions are described incorrectly.** The guide says release builds disable asserts by default, while `OPTION_USE_ASSERTS` defaults `ON` independent of build type and defines `WITH_ASSERT`. | `COMPILING.md`, “CMake Options”; `cmake/Options.cmake::set_options` and `add_definitions_based_on_options`; `cmake/CompileFlags.cmake::IS_STABLE_RELEASE`; official [option prose](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COMPILING.md#cmake-options) and [actual option](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/cmake/Options.cmake#L55-L64). | Record `OPTION_USE_ASSERTS` explicitly in every oracle build; build type alone does not define it. | High |
| **Compiler support is narrower than stated.** The guide says every CMake compiler with C++20 “should” work, but the compile-flags macro rejects compiler families other than MSVC, GNU, Clang, or AppleClang. | `COMPILING.md`, “Supported compilers”; `cmake/CompileFlags.cmake::compile_flags`, final fatal branch; official [compiler claim](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COMPILING.md#supported-compilers) and [flags logic](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/cmake/CompileFlags.cmake). | A CUDA/C toolchain is new platform work, not covered by the supported-compiler statement. | High |
| **The desync theory document uses obsolete action symbols.** It names `DoCommandP`/`DoCommandPInternal`; current submission is templated `Command<...>::Post`, although stale comments still mention the old names. The document declares it was last updated in 2014. | `docs/desync.md`, header and section 1.1; `src/command_func.h::CommandHelper`; `src/command.cpp::CommandHelperBase`; official [old text](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/docs/desync.md). | Preserve semantics, not old symbol names, when designing action tapes. | High |
| **The savegame format document is intentionally incomplete and dated.** It was last updated in 2021 and directs readers to source for chunk bodies. | `docs/savegame_format.md`, header and chunk sections; `src/saveload/*_sl.cpp` current handlers; official [format note](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/docs/savegame_format.md). | Do not implement a new state loader from this document alone. Generate a versioned behavior/state schema or use the exact oracle loader. | High |
| **Null-render execution is real but undocumented as a supported interface.** The man page only says `-v driver`; it does not describe `null:ticks=N`. The sole in-tree usage is the regression script. | `docs/openttd.6`, option `-v`; `VideoDriver_Null::Start/MainLoop`; `cmake/scripts/Regression.cmake`; official [man page](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/docs/openttd.6) and [null driver](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/video/null_v.cpp). | Useful pinned oracle mechanism; wrap it with version checks and expect upstream changes. | High |
| **Sound is not strictly required despite broad README wording.** The tree provides `no_sound.obs`/`no_music.obm` fallbacks and regression uses null drivers. Ordinary graphical play still requires an appropriate base graphics set. | `README.md`, section 1.4; `media/baseset/no_sound.obs`, `no_music.obm`; `cmake/scripts/Regression.cmake`; official [install wording](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/README.md#14-installing-and-running-openttd). | A non-rendering oracle need not ingest or redistribute sound/music. | High |
| **The license exception list has a broken Monocypher path.** README points to `LICENSE.md`; the committed file is `LICENCE.md`. | `README.md`, section 3.0; `src/3rdparty/monocypher/LICENCE.md`; official [README entry](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/README.md#30-licensing) and [actual file](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/monocypher/LICENCE.md). | A notice collector must scan files; following README paths mechanically will miss this license. | High |
| **The README exception list is not exhaustive at file level.** `cmake/Catch.cmake`, `CatchAddTests.cmake`, `FindFontconfig.cmake`, and `FindIconv.cmake` carry BSD-3-Clause CMake notices but are not listed. `CONTRIBUTING.md` includes an explicit CC BY 3.0 attribution for adapted text. | Those files’ header notices; `CONTRIBUTING.md`, “Attribution of this Contributing Guide”; official [contributor attribution](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md#attribution-of-this-contributing-guide). | Build a complete file-level bill of materials; do not treat README as a machine-readable SBOM. | High |
| **Binary install rules do not copy the standalone third-party license files.** They install GPL/README/CREDITS/CONTRIBUTING and selected docs, while README refers to license files under source-only paths. | `cmake/InstallAndPackage.cmake`, install sections and CPack license resource; official [packaging rules](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/cmake/InstallAndPackage.cmake#L20-L76). | Do not clone this notice packaging blindly. Ship a full `THIRD_PARTY_NOTICES` assembled from the actual components in your artifact. Whether official artifacts satisfy each exception by other means was not tested here. | High on recipe; Low on uninspected release artifacts |

## License inventory and obligations

### OpenTTD-authored repository material

The repository’s stated default is **GNU GPL version 2**, best treated as
**GPL-2.0-only**, for code and all other files not carrying a more specific
notice. The operative project wording does not grant “or any later version.”
The “How to Apply” appendix inside the stock GPL text contains an example
“version 2 or later” notice, but an example is not a project-wide later-version
grant. Evidence: `README.md`, section 3.0; `COPYING.md`, preface and sections
0–3; representative source headers. **Confidence: High.**

For a direct C/CUDA derivative that is distributed (including a public source
repository), the conservative checklist from `COPYING.md` is:

- preserve copyright, license, and warranty notices and provide the GPL text
  (sections 1–2);
- place prominent modification/date notices in changed files (section 2(a));
- license the distributed derived whole under GPL version 2 without charge for
  the license grant (section 2(b)); selling copies/services remains allowed;
- do not add restrictions that conflict with recipients’ GPL rights (section
  6);
- when distributing binaries, accompany them with complete corresponding
  machine-readable source, including interface definitions and build/install
  scripts, or use one of GPLv2 section 3’s exact alternatives;
- distinguish the fork from the original so upstream authors are not blamed
  for modifications, consistent with the license preamble and sensible
  branding practice.

Private modification and running are not restricted by GPLv2. Publishing a
Git repository or release is distribution and should be prepared for compliance
from the first public commit. Evidence: `COPYING.md`, sections 0–3 and 6;
official [license text](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/COPYING.md).
**Confidence: High for the text; Medium for fact-specific distribution labels.**

### Bundled third-party source

| Component / files | License evidence | Preserve/do before reuse | Confidence |
|---|---|---|---|
| Squirrel, `src/3rdparty/squirrel/**` | zlib terms in `src/3rdparty/squirrel/COPYRIGHT`; README section 3.0; official [notice](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/squirrel/COPYRIGHT). | Retain notice in source distribution; do not misrepresent origin; plainly mark altered source. | High |
| MD5, `src/3rdparty/md5/md5.{cpp,h}` | zlib-style notice embedded in `md5.cpp`/`md5.h`; official [implementation notice](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/md5/md5.cpp). | Retain embedded notice, origin, and altered-source marking. | High |
| `{fmt}`, `src/3rdparty/fmt/**` | MIT plus compiled-object notice exception in `LICENSE.rst`; official [license](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/fmt/LICENSE.rst). | Retain copyright/permission notice in source/substantial copies; record whether the object-code exception is relied upon. | High |
| nlohmann JSON, `src/3rdparty/nlohmann/json.hpp` | MIT in `LICENSE.MIT`; official [license](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/nlohmann/LICENSE.MIT). | Retain copyright and permission notice in copies/substantial portions. | High |
| Khronos OpenGL headers, `src/3rdparty/opengl/**` | MIT-style Khronos notice in `khrplatform.h` and headers; official [header](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/opengl/khrplatform.h). | Retain notice. Avoid entirely in a non-rendering implementation unless needed. | High |
| Catch2 and CMake Catch helpers | Boost Software License 1.0 in `src/3rdparty/catch2/LICENSE.txt`; BSD-3-Clause header notices in `cmake/Catch*.cmake`; official [Catch2 license](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/catch2/LICENSE.txt). | Preserve the applicable complete statements for copied source/derivatives; generated object-only exception applies only as written. Treat CMake helpers separately. | High |
| ICU ScriptRun, `src/3rdparty/icu/**` | Unicode license in `src/3rdparty/icu/LICENSE`; official [license](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/icu/LICENSE). | Put notice with copies or associated documentation; do not use copyright-holder names to promote without permission. | High |
| Monocypher, `src/3rdparty/monocypher/**` | Dual BSD-2-Clause / CC0 in `LICENCE.md`; official [license](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/monocypher/LICENCE.md). | Record which branch is selected. Lowest operational ambiguity: preserve the full license and author notices even if selecting CC0. BSD selection requires notice in source and binary documentation. | High |
| Social Integration API headers | MIT in `src/3rdparty/openttd_social_integration_api/LICENSE`; official [license](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/src/3rdparty/openttd_social_integration_api/LICENSE). | Retain copyright and permission notice. Unnecessary for an RL core unless compatibility is deliberate. | High |
| LLVM `CheckAtomic.cmake` | Apache-2.0 WITH LLVM-exception in `cmake/3rdparty/llvm/CheckAtomic.cmake` and `LICENSE.txt`; official [file](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/cmake/3rdparty/llvm/CheckAtomic.cmake). | Keep it as separately licensed build tooling, retain license/change notices and any applicable NOTICE material. Do not casually mix its source into GPL-2.0-only runtime code; Apache-2.0/GPLv2 compatibility is a counsel question. | High on license; Medium on combination analysis |
| Contributor guide text | `CONTRIBUTING.md`, “Attribution of this Contributing Guide,” identifies Bootstrap-derived CC BY 3.0 text and rsyslog-derived GPL text; official [attribution](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/CONTRIBUTING.md#attribution-of-this-contributing-guide). | If copying the guide, preserve its explicit attributions and license trail. Prefer writing a new project policy. | High |
| CMake modules `Catch*.cmake`, `FindFontconfig.cmake`, `FindIconv.cmake` | BSD-3-Clause header points to CMake licensing; each path contains the notice. | Preserve the header and include the applicable BSD/CMake notice in a source notice inventory. | High |

Do not import third-party modules merely because they are already in the
OpenTTD tree. A C/CUDA RL core can likely avoid most of them, materially
reducing notice and compatibility work.

### Assets and data

| Asset class | Repository evidence | Assessment / obligation | Confidence |
|---|---|---|---|
| OpenTTD extra/base graphics source and compiled GRFs | `media/baseset/openttd/**`, `openttd.grf`; files such as `openttd.nfo` state GPL version 2 and credit artists in embedded metadata. | Copyrighted GPL assets, not public-domain placeholders. Preserve license/credits if reused; cleaner RL releases should use semantic observations or new art. | High |
| `orig_extra` corrections/complements | `media/baseset/orig_extra/**`, `orig_extra.nfo` GPL header and contributor credits. | OpenTTD-distributed GPL material intended to complement user-supplied original graphics. It is not permission to redistribute the original TTD sprite files. | High |
| Original TTD graphics/sound/music | `README.md` 1.4.2–1.4.3 tells users to copy files from their copy; `media/baseset/orig_*.obg/.obs/.obm` stores filenames, hashes, indexes, and song names, with `[origin]` pointing to the user’s TTD media. The named `TRG*.GRF`, `SAMPLE.CAT`, and `GM*.CAT/.GM` payloads are not tracked in this commit. | Never commit or package those payloads. If an oracle uses them, require a user-local lawful installation and keep recordings containing sprites/audio private unless separately cleared. | High |
| OpenGFX/OpenSFX/OpenMSX | `README.md` 1.4.1 links separately distributed base sets; they are not the same artifact or automatically covered by OpenTTD’s repository license. | Audit each exact package/version and its attribution/share-alike terms separately before bundling or publishing visual/audio tapes. | High on separation; license details not audited |
| OpenTTD TrueType fonts | `media/baseset/OpenTTD-font.md` says GPL-2.0, release v0.7, maintained in official `OpenTTD/OpenTTD-TTF`; official [font note](https://github.com/OpenTTD/OpenTTD/blob/29f808ef0022064e6d9a83c8476d1e0f4686af86/media/baseset/OpenTTD-font.md). | GPL asset with separate upstream provenance. Retain note/license or omit. | High |
| Icons, logo, UI screenshots/docs graphics | `media/openttd.svg`, `media/openttd.*`, platform icons, and `docs/*.png/*.svg`; default repository GPL statement applies absent a specific notice. | Copyright reuse requires GPL compliance. Branding use also raises trademark/passing-off concerns not resolved by GPL. Prefer new name/logo/UI. | High on copyright; Medium on trademark |
| Languages, names, UI text, title save | `src/lang/*.txt`, `media/baseset/opntitle.dat`, default repository GPL statement. | These are expressive/data works, not merely engine behavior. Do not copy them into an independently licensed clean implementation; create original strings/scenarios. | High |
| NewGRF, AI, GameScript, downloaded content and user saves | `README.md` 1.5 and `docs/directory_structure.md` show third-party content directories; `CONTRIBUTING.md` says these add-ons are made by third parties. | Licenses vary per item. Exclude them from the oracle corpus unless the exact artifact is approved and recorded. Savegames may embed names/script data and dependencies; sanitize before publication. | High |

## Trademark, identity, and expressive-content risks

- **No trademark permission found.** A repository-wide search found no OpenTTD
  trademark policy or explicit grant for the name/logo. GPL governs copyright,
  not automatically source-identifying marks. Use a distinct project and package
  name, a new logo, and a prominent “independent project; not affiliated with or
  endorsed by OpenTTD” statement. Do not use “official”; the official Windows
  manifest itself uses “OpenTTD (official)” (`os/windows/winstore/manifests/Package.appxmanifest`,
  visual-elements section). **Confidence: High that the policy is absent from
  this checkout; Medium on legal risk.**
- **Transport Tycoon references are nominative context, not an asset license.**
  The man page calls OpenTTD a reimplementation and credits Chris Sawyer and
  MicroProse (`docs/openttd.6`, NAME/HISTORY); `docs/landscape.html` explicitly
  recognizes TTD copyright and third-party trademarks. Reusing the original
  logo, sprites, music, song titles, distinctive UI, or marketing presentation
  is a different risk from reproducing functional simulation behavior.
  **Confidence: High on evidence; Medium on legal line-drawing.**
- **Exact visual side-by-side recordings can reproduce protected artwork.** A
  local comparator that renders the user’s installed oracle next to new semantic
  output is lower distribution risk than committing MP4/GIF/pixel fixtures.
  Publish numeric state/action traces where possible; if visual fixtures are
  essential, use cleared replacement art and audit that art’s license.
  **Confidence: Medium.**
- **Names and data tables may be expressive.** Vehicle, industry, town, music,
  and UI strings should not be copied into an independently licensed build merely
  to look familiar. Mechanics, exact constants, table selection, and compilation
  can still raise derivation questions when sourced from code; have clean-room
  counsel define what the spec may contain. **Confidence: Medium.**

## Reuse-risk matrix

“Risk” here means risk of defeating a non-GPL/clean-room objective or creating
unmet notice/content obligations. A GPL-2.0-compliant fork can intentionally
accept many of the high-copyleft rows.

| Proposed reuse | Risk | Why / safe treatment | Evidence / confidence |
|---|---:|---|---|
| Translate OpenTTD C++ functions or data tables to C/CUDA | **Very high** for non-GPL | GPLv2 explicitly includes translation; publish as GPL-2.0-only with complete source, or do not use this method. | `COPYING.md` §§0–3. **High.** |
| Compile/link OpenTTD object code into an RL `.so`, Python extension, or CUDA executable | **High** | Likely one combined/derived program; the internal `openttd_lib` object target is not a licensing or ABI boundary. GPL the combined distribution unless counsel approves another structure. | `CMakeLists.txt` targets; `COPYING.md` §2. **Medium-High.** |
| Modify OpenTTD to expose a C ABI, state buffer, or GPU hooks | **High** for non-GPL; **manageable** for GPL fork | The patch and resulting binary are derived. Keep all corresponding code/build scripts GPLv2 and publish changes/notices. | `COPYING.md` §§2–3. **High.** |
| Run an unmodified pinned OpenTTD executable as a separate oracle process | **Low–Medium** | Running is unrestricted; separately distributing the binary still requires GPL source/license compliance. Communicate through ordinary files/stdin/network protocols and avoid presenting a combined proprietary bundle without review. | `COPYING.md` §§0, 2 aggregation, 3. **Medium.** |
| Use `-vnull:ticks=N`, saves, console/admin inputs for private oracle runs | **Low** | Existing executable behavior; no renderer fork needed. The interfaces are internal/versioned, so pin commit and record flags/assets. | `VideoDriver_Null`; regression script. **High technical / Medium legal.** |
| Copy desync log reader/writer or save-load code | **High** for non-GPL | Source reuse/translation. For a clean implementation, define a new neutral trace schema from observable behavior. | `src/network/network.cpp`, `src/debug.cpp`, `src/saveload/**`; GPL default. **High.** |
| Publish numeric black-box action/state traces | **Low–Medium** | Prefer facts, numbers, checksums, and project-created identifiers; exclude code, strings, artwork, map designs, NewGRF/script data, and private/user content. Output coverage is fact-specific under GPLv2 §0. | `COPYING.md` §0 output clause. **Medium.** |
| Copy official regression saves/results/tests | **High** for independently licensed tests | They are repository files under the default GPL and may contain expressive state/script text. Write new tests from an approved behavior spec. | `regression/**`, README license default. **High.** |
| Reimplement only behavior observed through black-box experiments with isolated implementers | **Medium** | Best non-GPL path, but “clean room” is evidence, not magic. Maintain barriers, provenance, independent design, and similarity review; avoid trade dress/assets. | Clean-room process below. **Medium.** |
| Bundle original TTD assets | **Very high** | Not licensed by OpenTTD and deliberately user-supplied. Never ship. | `README.md` 1.4.2–1.4.3; `orig_*` metadata. **High.** |
| Bundle OpenTTD GPL graphics/fonts/logo | **High** for non-GPL / branding | Separate copyrighted GPL assets; logo adds identity risk. Omit or comply and rebrand. | `media/**`, font note, GPL default. **High/Medium.** |
| Bundle OpenGFX/OpenSFX/OpenMSX or NewGRFs | **Unknown until audited** | Separate projects/content with version-specific licenses. Maintain an allowlist and exact hashes. | README 1.4.1/1.5. **High on need for separate audit.** |
| Copy only permissive third-party modules | **Low–Medium** | Possible under their individual licenses, but take them from their canonical upstream/version where practical and preserve notices; do not inherit OpenTTD modifications accidentally. | `src/3rdparty/**` notices. **High.** |
| Dynamically or statically link a GPLv2-derived core to NVIDIA CUDA runtime/toolkit libraries | **Unresolved / potentially high** | GPLv2’s system-library exception and no-further-restrictions rules may not fit every CUDA library or redistribution model. Static vs dynamic linkage, whether libraries are shipped, and exact NVIDIA terms matter. | `COPYING.md` §§3, 6–7; no CUDA exception exists in this repository. **High that review is required; no compatibility conclusion.** |
| Use “OpenTTD,” its logo, or “official” in product identity | **Medium–High** | Copyright license does not settle trademark/passing off. Use descriptive attribution only after counsel review and clearly rebrand. | No trademark policy in checkout; official manifest uses “official.” **Medium.** |

## Recommended clean-room workflow

Choose one of two strategies before implementation. Do not blend them silently.

### Strategy A — transparent GPL fork/port

This is technically fastest and offers the strongest route to exact parity.

1. Declare the new C/CUDA simulation core and derived tests GPL-2.0-only from
   the first commit; copy `COPYING.md`, preserve original headers/credits, add
   project copyright and dated modification notices.
2. Fork from the exact upstream commit and retain Git provenance. Record every
   copied/moved/translated file in a provenance manifest.
3. Keep the Python RL layer separable where practical, but do not assume a
   permissive wrapper can relicense a linked derived core. Document the process,
   ABI, and distribution layout for counsel.
4. Exclude original TTD payloads and third-party add-ons. Prefer semantic
   observations or newly created assets. Audit any replacement base set.
5. Resolve GPLv2/CUDA library compatibility before distributing linked binaries.
   A CPU GPL reference core plus a separately reviewed GPU execution component
   may be easier to reason about, but architecture alone is not a license cure.
6. Ship complete corresponding source and build scripts beside each binary,
   plus `COPYING`, `CREDITS`, modification notices, and a complete third-party
   notice file. Reproduce the release from a clean machine before publication.

### Strategy B — independently licensed behavior reimplementation

This is slower and cannot be performed by simply rewriting the source. The
following controls create evidence of independence; counsel must approve the
actual protocol.

1. **Freeze scope and people.** Create lists for (a) source-exposed oracle/spec
   personnel and (b) clean implementers. Anyone who has read OpenTTD source,
   source-derived architecture reports (including this one), copied constants,
   or generated source translations is presumptively on the exposed side.
2. **Freeze the oracle.** Record the unmodified executable hash, upstream commit,
   compiler/dependency versions, `OPTION_USE_ASSERTS`, platform, endian/word size,
   config, base-set hashes, NewGRF/script allowlist (prefer empty), seeds, and all
   CLI flags. Use the existing `null` driver for nonvisual runs.
3. **Define public stimuli only.** Drive the oracle through documented command
   line, save/scenario loading, console/admin/network inputs, or human actions.
   If an exposed team patches instrumentation, keep that patch in a segregated
   GPL repository and do not hand its source or implementation-derived details
   to clean implementers.
4. **Create a new neutral trace format.** Use project-owned action names and
   schema; capture tick number, seed, accepted/rejected action, numeric state,
   reward-relevant facts, and hashes. Do not copy C++ identifiers, structure
   layouts, comments, string tables, sprites, audio, scenarios, or save chunks.
5. **Write a sanitized functional specification.** State externally observable
   preconditions, transitions, invariants, numeric test vectors, error classes,
   and timing. Every requirement gets provenance: black-box experiment ID,
   public user-document section, or independently known mathematical rule.
   Counsel/source-exposed reviewers remove implementation detail before release
   to the clean team.
6. **Independent implementation.** Clean engineers design original C data
   structures, algorithms, names, and CUDA batching. They receive only the
   approved spec/test endpoint and cannot query source-exposed staff for “how
   OpenTTD does it.” Questions become new black-box experiments and sanitized
   spec revisions.
7. **Differential verification.** A separate verifier runs identical seeds and
   action tapes against oracle and implementation, reporting first divergence
   in the neutral schema. For a GPU batch, prove C batch-of-one equals the
   clean CPU reference, then CPU equals CUDA across environment counts and
   scheduling variations.
8. **Provenance controls.** Require contributor attestations, review commit
   messages for source references, scan for copied identifiers/comments/string
   sequences, and retain experiment logs/spec versions/review approvals. Do not
   ingest LLM output trained or prompted on pasted OpenTTD source into the clean
   implementation path.
9. **Independent release audit.** Counsel/release reviewer compares code,
   constants, tables, strings, assets, API, repository history, and dependency
   notices; validates branding; and records why every imported artifact is
   permissible.

### Oracle-specific cautions

- `VideoDriver_Null::MainLoop` still calls `GameLoop`, `InputLoop`, and
  `UpdateWindows`; “no pixels” does not mean “simulation-only” or thread-safe.
  Its default is 1,000 ticks when no `ticks` parameter is supplied. Pin and test
  the exact invocation. **Evidence:** `src/video/null_v.cpp`, symbols above.
  **Confidence: High.**
- `StateGameLoop` mixes authoritative simulation with window tick/news and
  AI/GameScript execution. A direct port cannot assume every line is GPU-worthy;
  a clean spec should describe state transitions, not translate the monolithic
  loop. **Evidence:** `src/openttd.cpp::StateGameLoop`. **Confidence: High.**
- Reproducibility depends on more than one seed: game RNG and interactive RNG
  are separate, commands are frame-ordered, settings/content influence behavior,
  and asynchronous save/network work surrounds the state step. **Evidence:**
  `src/core/random_func.hpp::Randomizer`, `NetworkSendCommand`, `GameLoop`.
  **Confidence: High.**
- OpenTTD’s regression test proves script output for specific saved fixtures; it
  is not an exhaustive gameplay parity suite. **Evidence:**
  `regression/{regression,gs,gs_compat,stationlist}` and
  `cmake/scripts/Regression.cmake`. **Confidence: High.**

## Attribution and release checklist

Before any public repository or release containing OpenTTD-derived material:

- [ ] Record upstream name, official URL, exact commit
  `29f808ef0022064e6d9a83c8476d1e0f4686af86`, retrieval date, and fork history.
- [ ] Include the unmodified GPLv2 text and preserve all copyright/warranty
  notices (`COPYING.md` §§1–2).
- [ ] Mark every modified/translated source file prominently with who changed it
  and the date (`COPYING.md` §2(a)).
- [ ] State clearly that the derivative is modified, independently maintained,
  unofficial, and not warranted or endorsed by OpenTTD.
- [ ] License the derived whole consistently with GPL-2.0-only; remove conflicting
  “all rights reserved,” field-of-use, noncommercial, model-use, or binary-only
  restrictions (`COPYING.md` §§2(b), 6–7).
- [ ] Offer/provide complete corresponding source beside binaries, including CUDA
  source, generated-source inputs, headers, build/install scripts, packaging,
  dependency lockfiles, and required interface definitions (`COPYING.md` §3).
- [ ] Preserve `CREDITS.md` and add a project-specific `AUTHORS`/provenance file;
  retain embedded asset artist credits in `media/baseset/**` if those assets ship.
- [ ] Generate an SBOM and `THIRD_PARTY_NOTICES` from the actual artifact, covering
  zlib, MIT, Boost, Unicode, BSD/CC0, Apache/LLVM-exception, BSD CMake modules,
  fonts, and any new CUDA/Python dependencies. Do not rely only on README links.
- [ ] Select and document the Monocypher license branch; fix the README
  `LICENSE.md`/`LICENCE.md` path in derivative documentation if retained.
- [ ] Inventory every non-code file by origin/license/hash: GRF, PNG/SVG/icon,
  font, language, sound, music, save/scenario, test fixture, model weight, dataset,
  and demo recording.
- [ ] Verify no original TTD payload, unauthorized NewGRF/AI/GameScript, user save,
  credential, or private trace is present.
- [ ] Audit exact OpenGFX/OpenSFX/OpenMSX versions separately if bundled.
- [ ] Use an original project name/logo and review descriptive references to
  OpenTTD/Transport Tycoon with trademark counsel.
- [ ] Obtain written GPLv2/CUDA distribution analysis for every linked/shipped
  NVIDIA library and for the Python-extension/process boundary.
- [ ] Ensure every contributor has rights to contribute, accepts the chosen
  license, and records clean-room/source-exposure status. No CLA or DCO requirement
  was found in this checkout; `CONTRIBUTING.md`, “License,” says contributions are
  GPLv2. Add a project-appropriate process rather than assuming upstream’s.
- [ ] Do not send AI-generated code/issues/PRs to upstream; their explicit policy
  rejects this (`CONTRIBUTING.md`, “Use of AI”).
- [ ] Rebuild the release from a clean environment and inspect the final archive,
  not just the source tree, for license/notice/source completeness.

## Unresolved questions requiring a decision or counsel

1. Is GPL-2.0-only acceptable for the C core, CUDA kernels, verifier, and linked
   RL library? If yes, a transparent port is preferable to calling the work clean
   room. If no, stop source-guided implementation and establish barriers now.
2. Which people/agents have already viewed OpenTTD source, this report, prior
   source traces, or generated translations? Can a genuinely unexposed
   implementation team still be formed?
3. Will CUDA be statically or dynamically linked, which runtime/toolkit/NVIDIA
   libraries will ship, and what exact license/EULA versions apply? Does counsel
   approve that combination with GPL-2.0-only?
4. Will the RL consumer link in-process, load a `.so`, use Python `ctypes`, or
   communicate with a separate executable? Draw and review the distribution and
   IPC boundaries before coding.
5. What is the exact parity target: a minimal road/cargo vertical slice, all base
   game mechanics, save compatibility, multiplayer, GameScript/AI, or NewGRF?
   “OpenTTD one-to-one” is not a testable legal/technical scope.
6. Are pixel-perfect visuals part of the public deliverable? If so, which cleared
   graphics/font set will be used, and can visual recordings be distributed under
   its license? If not, prohibit pixels/audio from test artifacts.
7. May the product use “OpenTTD-compatible” or another reference in its name or
   marketing? No trademark policy was found in the repository; seek written
   guidance/counsel.
8. Which gameplay names, economy tables, vehicle data, maps, UI strings, and
   constants may enter a sanitized functional spec? Define this before the spec
   team produces implementation-ready documents.
9. Will oracle traces or savegames include third-party NewGRFs, scripts, user
   names, chat, or proprietary original assets? Establish an empty-content default
   and publication scrubber.
10. Are model weights, replay buffers, or datasets distributed? Determine whether
    they contain copyrighted visual/textual content or source-derived generated
    data and assign explicit licenses/provenance.
11. Will binaries be distributed through GitHub, wheels, containers, app stores,
    or hosted only as a service? GPLv2 source-delivery and third-party notice
    mechanics differ by artifact/channel; review each.
12. Who owns new contributions, and will contributor agreements/attestations cover
    GPL grant, clean-room status, employer rights, generated-code provenance, and
    asset authorship?

## Recommended immediate gate

Before implementation continues, write and approve a one-page decision record:

```text
license strategy: GPL-2.0-only derivative | independent clean-room
oracle commit and binary hash:
parity scope:
public artifact types:
asset policy: semantic-only | named cleared base set
CUDA linkage/distribution model:
source-exposed team:
clean implementation team (if applicable):
legal reviewer and approval date:
```

Until that record exists, safe work is limited to private oracle experiments,
scope definition, dependency inventory, and newly authored neutral test-schema
design. That pause prevents a technically successful port from becoming
unreleasable under the intended license.

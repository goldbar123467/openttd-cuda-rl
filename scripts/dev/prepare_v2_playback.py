#!/usr/bin/env python3
"""Build isolated view-only V2 playback without changing the training engine."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from local import capture_source, source_identity, write_json


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Visible V2 source anchor differs: ' + old[:100])
    return text.replace(old, new, 1)


def overlay(source):
    names = ['src/video/video_driver.hpp', 'src/video/video_driver.cpp', 'src/video/sdl2_v.cpp',
             'src/rl_v2_action.cpp', 'src/rl_v2_live.inc']
    before = {name: (source / name).read_text() for name in names}
    after = dict(before)
    name = names[0]
    anchor = 'public:\n\tVideoDriver(bool uses_hardware_acceleration = false)'
    after[name] = replace_once(after[name], anchor, '''#ifdef WITH_RL_ENVIRONMENT
    bool development_live_view = false;
#endif

public:
#ifdef WITH_RL_ENVIRONMENT
    bool IsDevelopmentLiveView() const { return this->development_live_view; }
    void SetDevelopmentLiveView() { this->development_live_view = true; }
#endif
\tVideoDriver(bool uses_hardware_acceleration = false)''')
    name = names[1]
    text = after[name]
    start = text.index('\t\t\tthis->InputLoop();')
    end = text.index('\t\t\t::InputLoop();', start) + len('\t\t\t::InputLoop();')
    block = text[start:end]
    after[name] = text[:start] + '''#ifdef WITH_RL_ENVIRONMENT
            if (!this->IsDevelopmentLiveView()) {
#endif
''' + block + '''
#ifdef WITH_RL_ENVIRONMENT
            }
#endif''' + text[end:]
    name = names[2]
    anchor = '\tif (!SDL_PollEvent(&ev)) return false;'
    after[name] = replace_once(after[name], anchor, anchor + '''
#ifdef WITH_RL_ENVIRONMENT
    // This window displays an externally controlled simulation. Do not let
    // mouse/keyboard commands bypass its action and tick budgets.
    if (this->IsDevelopmentLiveView()) {
        if (ev.type == SDL_QUIT) { _exit_game = true; return true; }
        if (ev.type != SDL_WINDOWEVENT) return true;
    }
#endif''')
    name = names[3]
    headers = ['video/video_driver.hpp', 'screenshot.h', 'viewport_func.h', 'window_func.h', 'openttd.h', 'core/random_func.hpp']
    includes = [f'#include "{header}"' for header in headers if f'#include "{header}"' not in after[name]]
    includes += [f'#include <{header}>' for header in ['atomic', 'memory', 'thread'] if f'#include <{header}>' not in after[name]]
    after[name] = replace_once(after[name], '#include <algorithm>', '\n'.join(includes) + '\n\n#include <algorithm>')
    name = names[4]
    helper = '''
static bool DevVisible()
{
    const auto *driver = VideoDriver::GetInstance();
    return driver != nullptr && driver->HasGUI() && driver->IsDevelopmentLiveView();
}

static void DevDisplayYield()
{
    if (!DevVisible()) return;
    const uint64_t tick = TimerGameTick::counter;
    const std::array<uint32_t, 2> rng{_random.state[0], _random.state[1]};
    const bool valid = Company::IsValidID(_current_company);
    const std::string state = valid ? NativeStateSha256() : "company-absent";
    VideoDriver::GetInstance()->GameLoopPause();
    Require(!_exit_game, "development visible window closed before playback completed");
    Require(tick == TimerGameTick::counter && rng[0] == _random.state[0] && rng[1] == _random.state[1] &&
        state == (Company::IsValidID(_current_company) ? NativeStateSha256() : "company-absent"),
        "development rendering changed simulation state or RNG");
}

static void DevWaitForDraw()
{
    if (!DevVisible()) return;
    auto done = std::make_shared<std::atomic<bool>>(false);
    VideoDriver::GetInstance()->QueueOnMainThread([done] { done->store(true); });
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (!done->load()) {
        Require(std::chrono::steady_clock::now() < deadline, "development SDL drawing handshake timed out");
        DevDisplayYield();
        if (!done->load()) std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
}
'''
    after[name] = replace_once(after[name], 'static bool DevReadExact(', helper + '\nstatic bool DevReadExact(')
    anchor = '        pollfd descriptor{fd, POLLIN, 0};\n        int ready = ::poll(&descriptor, 1, static_cast<int>(remaining));'
    after[name] = replace_once(after[name], anchor, '''        DevDisplayYield();
        pollfd descriptor{fd, POLLIN, 0};
        int ready = ::poll(&descriptor, 1, static_cast<int>(DevVisible() ? std::min<int64_t>(remaining, 16) : remaining));
        if (ready == 0 && DevVisible()) continue;''')
    anchor = '    _current_company = CompanyID{static_cast<uint8_t>(first_company)};\n    std::ofstream trace'
    after[name] = replace_once(after[name], anchor, '''    _current_company = CompanyID{static_cast<uint8_t>(first_company)};
    if (VideoDriver::GetInstance()->HasGUI()) {
        Require(!shared, "initial visible V2 playback supports one company");
        VideoDriver::GetInstance()->SetDevelopmentLiveView();
        ScrollMainWindowToTile(TileXY(Map::SizeX() / 2, Map::SizeY() / 2), true);
        auto *window = FindWindowById(WC_MAIN_WINDOW, 0);
        Require(window != nullptr, "development visible main viewport missing");
        DoZoomInOutWindow(ZOOM_OUT, window);
        DoZoomInOutWindow(ZOOM_OUT, window);
        MarkWholeScreenDirty();
        DevWaitForDraw();
    }
    std::ofstream trace''')
    anchor = '                    response["transition"] = transition;'
    after[name] = replace_once(after[name], anchor, anchor + '''
                    if (DevVisible() && (terminal || decisions >= maximum)) {
                        MarkWholeScreenDirty();
                        Require(MakeScreenshot(SC_VIEWPORT, "v2-live-playback"), "development viewport screenshot request failed");
                        DevWaitForDraw();
                    }''')
    anchor = '            DevWriteResponse(output, response);'
    after[name] = replace_once(after[name], anchor, '            DevDisplayYield();\n' + anchor)
    patch = []
    for name in names:
        patch.extend(difflib.unified_diff(before[name].splitlines(keepends=True), after[name].splitlines(keepends=True),
            fromfile='a/' + name, tofile='b/' + name))
    for name, text in after.items():
        (source / name).write_text(text)
    return ''.join(patch)


def run(args):
    root, original = args.engine_root.resolve(), args.base_engine_root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    source = root / 'source'
    record = {'kind': 'isolated-development-v2-visible-engine', 'status': 'preparing', 'source': source_identity(),
        'base_engine': str(original), 'base_engine_sha256': digest(original / 'build/openttd'),
        'claim': 'View-only SDL display; unchanged native action/tick boundary must be verified against headless play.',
        'jobs': args.jobs}
    write_json(root / 'preparation.json', record)
    def execute(name, command):
        with (root / (name + '.log')).open('x') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(name + ' completed', flush=True)
    try:
        assert record['base_engine_sha256'] == '7669cf2894439031d4cd3a46436bc9cf4409dccfc7d02d9342df95b76ceacddd'
        original_source = original / 'source'
        record['base_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=original_source, text=True).strip()
        patch = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], cwd=original_source)
        (root / 'base-composition.patch').write_bytes(patch)
        untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=original_source).split(b'\0')
        assert sorted(name for name in untracked if name) == [b'src/rl_v2_live.inc']
        execute('clone', ['git', 'clone', '--no-hardlinks', '--no-checkout', str(original_source), str(source)])
        execute('checkout', ['git', '-C', str(source), 'checkout', '--detach', record['base_commit']])
        execute('base-apply', ['git', '-C', str(source), 'apply', str(root / 'base-composition.patch')])
        shutil.copy2(original_source / 'src/rl_v2_live.inc', source / 'src/rl_v2_live.inc')
        record['base_adapter_sha256'] = digest(source / 'src/rl_v2_live.inc')
        text = overlay(source)
        (root / 'visible-overlay.patch').write_text(text)
        record['overlay_sha256'] = digest(root / 'visible-overlay.patch')
        capture_source(root / 'preparation-source')
        record['status'] = 'building'
        write_json(root / 'preparation.json', record)
        build = root / 'build'
        command = ['cmake', '-S', str(source), '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
            '-DOPTION_RL_ENVIRONMENT=ON', '-DOPTION_RL_NEURAL_AGENT=OFF', '-DOPTION_USE_ASSERTS=ON',
            '-DOPTION_DEDICATED=OFF', '-DPERSONAL_DIR=.openttd-rl-v2-visible']
        record['configure'] = command
        execute('configure', command)
        execute('build', ['cmake', '--build', str(build), '--parallel', str(args.jobs)])
        baseset = original / 'build/baseset/opengfx-8.0.tar'
        assert digest(baseset) == '9389bcb0807058c80bd95121e978f05d9ef86b4b1bc3ac2da8da8bb02456043c'
        (build / 'baseset').mkdir(exist_ok=True)
        shutil.copy2(baseset, build / 'baseset/opengfx-8.0.tar')
        record.update(status='built', executable_sha256=digest(build / 'openttd'))
    except BaseException as exc:
        record.update(status='failed', error=repr(exc))
        raise
    finally:
        write_json(root / 'preparation.json', record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-engine-root', type=Path, required=True)
    parser.add_argument('--engine-root', type=Path, required=True)
    parser.add_argument('--jobs', type=int, choices=(1, 2), default=2)
    run(parser.parse_args())

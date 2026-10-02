# Raw human-demonstration capture using the installed, unmodified OpenTTD 15.3.
# This does not produce policy tensors or start training.
[CmdletBinding()]
param(
    [string]$Engine = 'C:\Program Files (x86)\Steam\steamapps\common\OpenTTD\openttd.exe',
    [string]$OutputRoot = (Join-Path $env:LOCALAPPDATA 'OpenTTD-RL\demonstrations'),
    [string]$GitExecutable = '',
    [int]$Seed = 0,
    [ValidateSet('general', 'bus-routes')]
    [string]$Lesson = 'general',
    [switch]$SmokeTest,
    [switch]$PrepareOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
# Shell-launched shortcuts can inherit another PowerShell edition's module path.
# Use this interpreter's built-ins, including its Get-FileHash script function.
Import-Module ([System.IO.Path]::Combine($PSHOME, 'Modules', 'Microsoft.PowerShell.Utility', 'Microsoft.PowerShell.Utility.psd1')) -Force
Import-Module ([System.IO.Path]::Combine($PSHOME, 'Modules', 'Microsoft.PowerShell.Management', 'Microsoft.PowerShell.Management.psd1')) -Force
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Write-Text([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text.Replace("`r`n", "`n"), $utf8)
}
function Write-Record([string]$Path, $Record) {
    Write-Text $Path (($Record | ConvertTo-Json -Depth 12) + "`n")
}
function File-Identity([string]$Path) {
    $item = Get-Item -LiteralPath $Path
    return [ordered]@{ path = $item.FullName; bytes = $item.Length;
        sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
}

function Find-Git {
    if ($GitExecutable) {
        return (Get-Item -LiteralPath $GitExecutable).FullName
    }
    $onPath = Get-Command git.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($onPath) { return $onPath.Source }
    # Explorer does not inherit Codex's additional tool paths. Resolve the known
    # bundled runtime without changing the user's PATH or installing anything.
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Git\cmd\git.exe'),
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\native\git\cmd\git.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw 'Cannot find Git for recording provenance. Supply -GitExecutable with its full path.'
}

$session = $null
$record = $null
$recordPath = $null
try {
$engineItem = Get-Item -LiteralPath $Engine
if ($engineItem.VersionInfo.ProductVersion -ne '15.3') {
    throw 'This recorder was checked against OpenTTD 15.3. Requalify after an engine update.'
}
if ($Seed -eq 0) { $Seed = Get-Random -Minimum 1 -Maximum 2147483647 }
if ($Seed -lt 1) { throw 'Seed must be positive.' }
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
[void][System.IO.Directory]::CreateDirectory($OutputRoot)
$kind = if ($SmokeTest) { 'smoke' } else { 'human' }
$session = Join-Path $OutputRoot ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + $kind + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
[void](New-Item -ItemType Directory -Path $session)
foreach ($subdir in @('save\autosave', 'scripts')) {
    [void][System.IO.Directory]::CreateDirectory((Join-Path $session $subdir))
}
$config = Join-Path $session 'openttd.cfg'
Write-Text $config @'
[misc]
fullscreen = false
resolution = 1280,800

[gui]
autosave_interval = 2
keep_all_autosave = true
autosave_on_exit = true

[game_creation]
map_x = 6
map_y = 6
landscape = temperate
starting_year = 1950
custom_town_number = 6

[difficulty]
number_towns = 4
terrain_type = 0
'@
# These setup commands are explicitly distinguished from human commands.
# Enabling debug logging with -d creates a separate Windows console, whose
# QuickEdit selection can block startup. The in-game startup script avoids it.
Write-Text (Join-Path $session 'scripts\autoexec.scr') "debug_level desync=1`n"
Write-Text (Join-Path $session 'scripts\game_start.scr') "pause`nsave initial`n"
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $session 'recorder.ps1')
$readme = @'
RAW OPENTTD DEMONSTRATION - NOT YET TRAINING DATA

This is an isolated 64x64 temperate game starting in 1950, with six towns.
The game starts paused. Press the normal Pause button to begin.
For a first demonstration, build a passenger-bus service between two towns:
roads, bus stops, depot, bus, orders, start, and let it deliver passengers.
Pause while thinking when appropriate; do not leave long unlabelled idle periods.
Save a game named final before quitting normally. Exit autosave is also enabled.
Use one map per recording. Quit and use the recording shortcut for another map.

The launcher creates a new directory each time. Never relaunch manually with
this directory's config: OpenTTD overwrites commands-out.log on process restart.

Files:
  save/initial.sav                   explicit initial game snapshot
  save/autosave/dmp_cmds_*.sav        built-in initial snapshot
  save/autosave/commands-out.log      native command log
  save/*.sav and save/autosave/*.sav manual, periodic and exit snapshots
  recording.json                     version, hashes, seed and capture status

The pause and initial save in scripts/game_start.scr are launcher setup, not
human demonstrations. Native cmd records precede final execution; cmdf can mean
a failed test OR an estimate query. These are not confirmed action outcomes.
This capture has no neural observations, legal masks, policy labels or verified
replay. Import/replay and a separate imitation-learning objective remain needed.
These maps are demonstration collection, not the registered evaluation suite.
No personal configuration is copied. This launcher uses -c, -X and -x to isolate
the game from the ordinary user-data directory and prevent config persistence.
'@
Write-Text (Join-Path $session 'READ-ME.txt') $readme
$lessonRecord = $null
if ($Lesson -eq 'bus-routes') {
    $guidePath = Join-Path $session 'BUS-LESSON.md'
    $notesPath = Join-Path $session 'route-notes.md'
    Write-Text $guidePath @'
# Bus route recording

The game starts paused. Unpause to build and run services; pause when thinking.
Aim for two simple passenger routes, buying one bus for each route to start.

1. Choose two stops for route 1. Note why: passenger demand, stop coverage,
   road distance, construction cost, and the alternative you considered.
2. Build the needed roads, bus stops and depot. Buy one bus directly (no cloning
   or shared orders for this lesson). Add both stops to its Orders list.
3. Select each order and set Full load any cargo. Check both orders show full
   load, then save route-1-ready BEFORE starting the bus. Start it and let it
   collect and deliver passengers. Save route-1-service after delivery.
4. Repeat for route 2 with one new bus, using route-2-ready and route-2-service.
5. Open the road vehicle list and inspect each bus's orders, load, profit and
   status. Explain what you checked and any management decision. Show stop/start
   or send-to-depot if useful; do not make changes just to fill a checklist.
6. Save final and quit OpenTTD normally so the recorder can finalize its hashes.

Use the normal Save Game menu for these checkpoints. Do not load an older save,
generate another map, or restart this session; start a fresh recording instead.
Normal mistakes are useful: correct them in the same game rather than reloading.
Full load at both endpoints is this exercise's chosen policy; record excessive
waiting or poor service as observed outcomes instead of assuming it is optimal.

You can tell Codex your reasoning in chat as you play, or write in route-notes.md.
Mention the route/bus name and game date so notes can be matched to the saves.
The command log captures purchases, construction, order changes, load settings,
start/stop/depot actions, and finance commands. Saves preserve game state.
Opening windows, mouse movements, your reasoning and a video of the screen are
NOT recorded by this launcher. Record the windows/metrics you consult in notes.

This is raw evidence. Replay must verify the saved checkpoints before any
successful, exactly supported decisions become imitation-training examples.
Unsupported actions and failed/estimate commands are kept for inspection,
not silently turned into training labels. No training runs during recording.
'@
    Write-Text $notesPath @'
# Human bus route notes

These are optional human observations, not verified game state or policy labels.
Leave unknown facts blank. Tell Codex in chat if that is easier than editing.

## Route 1
- Game date and checkpoint:
- Towns / stops / bus name:
- Why this route and stop placement? Which alternative did you reject?
- Why buy this bus now? Cash/loan or construction-cost considerations:
- Both orders set to full load before starting:
- After service: passenger load, waiting, profit, or problems noticed:

## Route 2
- Game date and checkpoint:
- Towns / stops / bus name:
- Why this route and stop placement? Which alternative did you reject?
- Why buy this bus now? Cash/loan or construction-cost considerations:
- Both orders set to full load before starting:
- After service: passenger load, waiting, profit, or problems noticed:

## Viewing and managing buses
- Game date / route / bus:
- Window(s) opened and metric(s) checked:
- Decision and reason (including deciding to keep running or wait):
- Outcome observed:
'@
    Write-Text (Join-Path $session 'READ-ME.txt') ("BUS ROUTES: start with BUS-LESSON.md; record reasoning in route-notes.md or chat.`n`n" + $readme)
    $lessonRecord = [ordered]@{
        name = $Lesson; cargo = 'passengers'; vehicle_type = 'bus';
        initial_buses_per_route = 1; full_load = 'any cargo at both endpoints before first start';
        requested_checkpoints = @('route-1-ready', 'route-1-service', 'route-2-ready', 'route-2-service', 'final');
        guide = (File-Identity $guidePath); notes_path = $notesPath;
        notes_initial = (File-Identity $notesPath);
        captures_gui_navigation = $false; captures_video = $false;
        notes_are_policy_labels = $false
    }
}
$gameArgs = @('-c', $config, '-X', '-x', '-g', '-G', "$Seed", '-t', '1950', '-r', '1280x800')
if ($SmokeTest) { $gameArgs += @('-v', 'null:ticks=40', '-s', 'null', '-m', 'null') }
$projectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$gitPath = Find-Git
$sourceCommit = (& $gitPath -C $projectRoot rev-parse HEAD | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $sourceCommit -notmatch '^[0-9a-f]{40}$') { throw 'Cannot determine recording source revision.' }
$sourceDirty = @(& $gitPath -C $projectRoot status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'Cannot determine recording source dirty state.' }
$assets = @(Get-ChildItem -LiteralPath (Join-Path $engineItem.DirectoryName 'baseset') -File |
    Where-Object { $_.Extension -in @('.tar', '.grf', '.obg') } |
    ForEach-Object { File-Identity $_.FullName })
$record = [ordered]@{
    schema = 'openttd-human-raw-capture-v1'; status = 'prepared'; kind = $kind;
    started_at = [DateTimeOffset]::Now.ToString('o'); session = $session;
    engine = (File-Identity $engineItem.FullName); version = $engineItem.VersionInfo.ProductVersion;
    source = [ordered]@{ commit = $sourceCommit; dirty = ($sourceDirty.Count -gt 0); status = $sourceDirty; git_executable = $gitPath };
    recorder = (File-Identity (Join-Path $session 'recorder.ps1'));
    config = (File-Identity $config); startup_script = (File-Identity (Join-Path $session 'scripts\game_start.scr'));
    autoexec_script = (File-Identity (Join-Path $session 'scripts\autoexec.scr'));
    assets = $assets; seed = $Seed; arguments = $gameArgs;
    runtime = [ordered]@{ os = [Environment]::OSVersion.VersionString; powershell = $PSVersionTable.PSVersion.ToString(); device = 'native CPU game simulation; no neural training' };
    training_ready = $false; replay_verified = $false;
    setup_commands = @('debug_level desync=1', 'pause', 'save initial');
    claim = 'Raw command capture and snapshots only; not model-ready demonstration data.'
}
if ($null -ne $lessonRecord) { $record['lesson'] = $lessonRecord }
$recordPath = Join-Path $session 'recording.json'
Write-Record $recordPath $record
Write-Output "Recording directory: $session"
if ($PrepareOnly) { return }

try {
    # All generated arguments are simple tokens or file paths without embedded quotes.
    foreach ($arg in $gameArgs) { if ($arg.Contains('"')) { throw 'Unsupported quote in argument.' } }
    $argumentLine = ($gameArgs | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $processOptions = @{
        FilePath = $engineItem.FullName; ArgumentList = $argumentLine; WorkingDirectory = $session;
        PassThru = $true; RedirectStandardOutput = (Join-Path $session 'engine.stdout.log');
        RedirectStandardError = (Join-Path $session 'engine.stderr.log');
        WindowStyle = $(if ($SmokeTest) { 'Hidden' } else { 'Normal' })
    }
    $record.status = 'running'
    Write-Record $recordPath $record
    $game = Start-Process @processOptions
    # Retain the handle before exit; Windows PowerShell otherwise loses ExitCode.
    $null = $game.Handle
    $record['process_id'] = $game.Id
    Write-Record $recordPath $record
    if ($SmokeTest) {
        if (-not $game.WaitForExit(60000)) {
            $game.Kill()
            $game.WaitForExit()
            throw 'Capture smoke exceeded 60 seconds; its artifacts are retained.'
        }
    } else { $game.WaitForExit() }
    $game.Refresh()
    $record['exit_code'] = $game.ExitCode
    $log = Join-Path $session 'save\autosave\commands-out.log'
    $initial = Join-Path $session 'save\initial.sav'
    if (-not (Test-Path -LiteralPath $log) -or -not (Test-Path -LiteralPath $initial)) {
        throw 'Initial save or native command log is missing. This recording needs inspection.'
    }
    $logText = Get-Content -LiteralPath $log -Raw
    if ($logText -notmatch 'cmd:.*\(CmdPause\)') { throw 'Expected setup pause command was not recorded.' }
    $record['command_log'] = File-Identity $log
    $record['command_records'] = [regex]::Matches($logText, '(?m)\bcmd:').Count
    $record['failed_or_estimate_records'] = [regex]::Matches($logText, '(?m)\bcmdf:').Count
    $record['saves'] = @(Get-ChildItem -LiteralPath (Join-Path $session 'save') -Filter '*.sav' -File -Recurse |
        ForEach-Object { File-Identity $_.FullName })
    if ($null -ne $lessonRecord) {
        if (Test-Path -LiteralPath $lessonRecord.notes_path) {
            $record.lesson['notes_final'] = File-Identity $lessonRecord.notes_path
        }
        $saveNames = @($record.saves | ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_.path) })
        $record.lesson['missing_requested_checkpoints'] = @($lessonRecord.requested_checkpoints |
            Where-Object { $_ -notin $saveNames })
    }
    if ((Get-FileHash -LiteralPath $engineItem.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.engine.sha256) {
        throw 'The installed executable changed during capture.'
    }
    if ($game.ExitCode -ne 0) { throw "OpenTTD exited with code $($game.ExitCode)." }
    $record.status = if ($SmokeTest) { 'smoke_passed' } else { 'raw_capture_completed' }
} catch {
    $record.status = 'failed'
    $record['error'] = $_.Exception.Message
    throw
} finally {
    $record['finished_at'] = [DateTimeOffset]::Now.ToString('o')
    Write-Record $recordPath $record
}
Write-Output "$($record.status): $session"
} catch {
    $failure = $_
    # Include setup failures, which previously occurred before recording.json
    # existed and vanished when the desktop-launched PowerShell window closed.
    if ($session -and (Test-Path -LiteralPath $session)) {
        Write-Text (Join-Path $session 'launcher-error.log') ($failure | Out-String)
        if ($null -eq $record) {
            Write-Record (Join-Path $session 'recording.json') ([ordered]@{
                schema = 'openttd-human-raw-capture-v1'; status = 'failed'; stage = 'launcher_setup';
                session = $session; error = $failure.Exception.Message;
                finished_at = [DateTimeOffset]::Now.ToString('o');
                training_ready = $false; replay_verified = $false
            })
        }
    }
    if (-not $SmokeTest -and -not $PrepareOnly) {
        Add-Type -AssemblyName System.Windows.Forms
        $message = "The recording could not start or finish correctly.`n`n$($failure.Exception.Message)"
        if ($session) { $message += "`n`nDetails were saved in:`n$session" }
        [void][System.Windows.Forms.MessageBox]::Show($message, 'OpenTTD recording error', 'OK', 'Error')
    }
    throw $failure
}

param(
    [Parameter(Mandatory = $true)][string]$ExperimentRoot,
    [Parameter(Mandatory = $true)][string]$ComparisonRoot,
    [Parameter(Mandatory = $true)][string]$OutputRoot,
    [string]$FigureRoot
)
$ErrorActionPreference = 'Stop'
$experimentDirectory = (Resolve-Path -LiteralPath $ExperimentRoot).ProviderPath
$comparisonDirectory = (Resolve-Path -LiteralPath $ComparisonRoot).ProviderPath
$destinationDirectory = [IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $destinationDirectory) { throw 'Evidence output already exists; preserve it and use a fresh path.' }
$runtimePrefix = '\\wsl.localhost\Ubuntu-24.04\home\imsa\.local\share\openttd-rl\'
if (-not $experimentDirectory.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unexpected experiment directory.' }
if (-not $comparisonDirectory.StartsWith($experimentDirectory + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Comparison is outside this experiment.' }
$analysisPrefix = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'OpenTTD-RL\analysis')) + '\'
if (-not $destinationDirectory.StartsWith($analysisPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Evidence destination is outside the requested analysis directory.' }
New-Item -ItemType Directory -Path $destinationDirectory | Out-Null
$exports = [Collections.Generic.List[object]]::new()
function Copy-VerifiedFile($SourceRecord, [string]$RelativeName) {
    $sourcePath = [string]$SourceRecord.path
    if ($sourcePath.StartsWith('/home/imsa/.local/share/openttd-rl/')) {
        $sourcePath = '\\wsl.localhost\Ubuntu-24.04' + $sourcePath.Replace('/', '\')
    }
    $sourcePath = (Resolve-Path -LiteralPath $sourcePath).ProviderPath
    if (-not $sourcePath.StartsWith($runtimePrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Source escaped the owned runtime directory.' }
    $destinationPath = [IO.Path]::GetFullPath((Join-Path $destinationDirectory $RelativeName))
    if (-not $destinationPath.StartsWith($destinationDirectory + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Destination escaped the evidence directory.' }
    if ([IO.Path]::GetFileName($sourcePath) -in @('secrets.cfg', 'private.cfg')) { throw 'Private game configuration is not evidence.' }
    if (Test-Path -LiteralPath $destinationPath) { throw ('Duplicate evidence destination: ' + $RelativeName) }
    $sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sourceHash -ne $SourceRecord.sha256) { throw ('Evidence source hash changed: ' + $RelativeName) }
    $parentPath = Split-Path -Parent $destinationPath
    if (-not (Test-Path -LiteralPath $parentPath)) { New-Item -ItemType Directory -Path $parentPath -Force | Out-Null }
    Copy-Item -LiteralPath $sourcePath -Destination $destinationPath
    $destinationHash = (Get-FileHash -LiteralPath $destinationPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($destinationHash -ne $sourceHash) { throw ('Copied evidence hash differs: ' + $RelativeName) }
    $exports.Add([pscustomobject]@{source=$SourceRecord.path;relative_file=$RelativeName;path=$destinationPath;sha256=$destinationHash})
}
function Local-Reference([string]$Path) {
    return @{path=$Path;sha256=(Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
function Runtime-Path([string]$Path) {
    if ($Path.StartsWith('/home/imsa/.local/share/openttd-rl/')) {
        return '\\wsl.localhost\Ubuntu-24.04' + $Path.Replace('/', '\')
    }
    return $Path
}
$resultsPath = Join-Path $comparisonDirectory 'results.json'
$results = Get-Content -LiteralPath $resultsPath -Raw | ConvertFrom-Json
if ($results.status -ne 'completed' -or $results.verification.episodes -ne 250) { throw 'The comparison is not fully verified.' }
$protocolPath = Join-Path $experimentDirectory 'fifty-game-protocol.json'
$protocol = Get-Content -LiteralPath $protocolPath -Raw | ConvertFrom-Json
if ((Local-Reference $protocolPath).sha256 -ne $results.protocol.sha256) { throw 'The gameplay protocol changed after verification.' }
$trainingProtocolPath = Join-Path $experimentDirectory 'training-protocol.json'
if ((Local-Reference $trainingProtocolPath).sha256 -ne $results.training_protocol.sha256) { throw 'The training protocol changed after verification.' }
$gameplay = @(Import-Csv -LiteralPath (Join-Path $comparisonDirectory 'gameplay.csv'))
$planned = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
foreach ($actor in @($protocol.frozen_actors.PSObject.Properties.Name) + @($protocol.scripted_actor)) {
    foreach ($case in $protocol.cases) { [void]$planned.Add($actor + ':' + $case.case_id) }
}
$actual = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
$proofs = @{}
foreach ($proof in $results.native_verification) {
    $key = $proof.actor + ':' + $proof.case_id
    if ($proofs.ContainsKey($key)) { throw 'Repeated native evidence identity.' }
    $proofs[$key] = $proof
}
foreach ($row in $gameplay) {
    $key = $row.actor + ':' + $row.case_id
    if (-not $actual.Add($key) -or -not $proofs.ContainsKey($key)) { throw 'Repeated or unverified gameplay CSV identity.' }
    $proof = $proofs[$key]
    if ($row.report_path -ne $proof.report.path -or [int]$row.decisions -ne [int]$proof.verified_decisions) { throw 'Gameplay CSV differs from native evidence.' }
    $nativeReportPath = Runtime-Path $proof.report.path
    if ((Local-Reference $nativeReportPath).sha256 -ne $proof.report.sha256) { throw 'Native report changed after verification.' }
    $nativeReport = Get-Content -LiteralPath $nativeReportPath -Raw | ConvertFrom-Json
    if ($row.final_save -ne $nativeReport.final_save.path -or $row.final_save_sha256 -ne $nativeReport.final_save.sha256) { throw 'CSV final save differs from its native report.' }
}
if ($planned.Count -ne 250 -or $gameplay.Count -ne 250 -or $proofs.Count -ne 250 -or -not $actual.SetEquals($planned)) { throw 'The CSV does not contain all 250 planned actor/case pairs.' }
$figuresDirectory = if ($FigureRoot) { (Resolve-Path -LiteralPath $FigureRoot).ProviderPath } else { $comparisonDirectory }
if ($figuresDirectory -ne $comparisonDirectory -and -not $figuresDirectory.StartsWith($comparisonDirectory + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Figures escaped the comparison directory.' }
$figuresPath = Join-Path $figuresDirectory 'figures.json'
$figures = Get-Content -LiteralPath $figuresPath -Raw | ConvertFrom-Json
if ($figures.status -ne 'completed' -or $figures.results.sha256 -ne (Local-Reference $resultsPath).sha256 -or $figures.files.Count -ne 6) { throw 'Figures do not match the verified comparison.' }
foreach ($figure in $figures.files) { Copy-VerifiedFile $figure ([IO.Path]::GetFileName([string]$figure.path)) }
Copy-VerifiedFile (Local-Reference $figuresPath) 'figures.json'
foreach ($name in @('results.json', 'offline.csv', 'offline-operations.csv', 'gameplay.csv', 'paired-differences.csv', 'scripted-paired-differences.csv', 'report.md')) {
    Copy-VerifiedFile (Local-Reference (Join-Path $comparisonDirectory $name)) $name
}
Copy-VerifiedFile $results.training_protocol 'training-protocol.json'
Copy-VerifiedFile $results.protocol 'fifty-game-protocol.json'
Copy-VerifiedFile (Local-Reference (Join-Path $experimentDirectory 'insertion-diagnostic-protocol.json')) 'insertion-diagnostic-protocol.json'
foreach ($name in @('verification-checks.json', 'interface-prefix-verification.json')) {
    Copy-VerifiedFile (Local-Reference (Join-Path $experimentDirectory $name)) $name
}
Copy-VerifiedFile (Local-Reference (Join-Path $experimentDirectory 'harness-qualification-02\report.json')) 'native-checkpoint-qualification.json'
Copy-VerifiedFile $results.offline_report 'offline-comparison.json'
Copy-VerifiedFile $results.batch_report 'gameplay-batch.json'
foreach ($actorProperty in $protocol.frozen_actors.PSObject.Properties) {
    $actor = $actorProperty.Name
    $frozen = $actorProperty.Value
    Copy-VerifiedFile $frozen.model ('models\' + $actor + '\inference-weights.pt')
    Copy-VerifiedFile @{path=($frozen.run + '/run.json');sha256=$frozen.run_sha256} ('models\' + $actor + '\run.json')
}
$trainingRun = Get-Content -LiteralPath (Join-Path $destinationDirectory 'models\seven-game-256\run.json') -Raw | ConvertFrom-Json
Copy-VerifiedFile $trainingRun.dataset.manifest 'human-data\training-campaign.json'
Copy-VerifiedFile $trainingRun.dataset.labels 'human-data\training-labels.json'
Copy-VerifiedFile $trainingRun.dataset.native_manifest 'human-data\native-imitation.tsv'
$offline = Get-Content -LiteralPath (Join-Path $destinationDirectory 'offline-comparison.json') -Raw | ConvertFrom-Json
foreach ($corpusProperty in $offline.corpora.PSObject.Properties) {
    $copiedInputs = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    $inputNumber = 0
    foreach ($inputRecord in $corpusProperty.Value.inputs) {
        if ($copiedInputs.Add([string]$inputRecord.path)) {
            $inputNumber++
            $relativeInput = 'human-data\' + $corpusProperty.Name + '\' + $inputNumber.ToString('0000') + '-' + [IO.Path]::GetFileName([string]$inputRecord.path)
            Copy-VerifiedFile $inputRecord $relativeInput
        }
    }
}
Copy-VerifiedFile $results.diagnostics.choices 'choice-diagnostics.json'
Copy-VerifiedFile $results.diagnostics.insertion_structure 'insertion-structure.json'
foreach ($trial in $results.diagnostics.insertion_trials) {
    Copy-VerifiedFile $trial.report ('insertions-only-' + $trial.epochs + '.json')
    Copy-VerifiedFile $trial.model ('diagnostic-models\insertions-only-' + $trial.epochs + '.pt')
}
$savedIndex = [Collections.Generic.List[string]]::new()
$savedIndex.Add('# Final saved games')
$savedIndex.Add('')
$savedIndex.Add('All 250 planned cases are included. Interface failures retain their exact last observable native state and shorter budget.')
$savedIndex.Add('')
$savedIndex.Add('| Actor | Case | Outcome | Decisions | Passengers | Save |')
$savedIndex.Add('| --- | --- | --- | --- | --- | --- |')
foreach ($row in $gameplay) {
    $relativeSave = 'final-saves\' + $row.actor + '\game-' + ([int]$row.case_id).ToString('00') + '.sav'
    Copy-VerifiedFile @{path=$row.final_save;sha256=$row.final_save_sha256} $relativeSave
    $indexLink = $row.actor + '/game-' + ([int]$row.case_id).ToString('00') + '.sav'
    $savedIndex.Add('| ' + $row.actor + ' | ' + $row.case_id + ' | ' + $row.outcome + ' | ' + $row.decisions + ' | ' + $row.passengers + ' | [Open save](' + $indexLink + ') |')
}
foreach ($proof in $results.native_verification) {
    $relativeRoot = 'native-evidence\' + $proof.actor + '\game-' + ([int]$proof.case_id).ToString('00')
    foreach ($kind in @('report', 'initial', 'final', 'reset', 'transitions', 'decisions')) {
        $sourceRecord = $proof.$kind
        $filename = [IO.Path]::GetFileName([string]$sourceRecord.path)
        Copy-VerifiedFile $sourceRecord ($relativeRoot + '\' + $filename)
    }
}
$savedIndex | Set-Content -LiteralPath (Join-Path $destinationDirectory 'final-saves\README.md') -Encoding utf8NoBOM
$saveIndexPath = Join-Path $destinationDirectory 'final-saves\README.md'
$exports.Add([pscustomobject]@{source=$null;relative_file='final-saves\README.md';path=$saveIndexPath;sha256=(Local-Reference $saveIndexPath).sha256})
@{status='copied-and-hash-verified';files=$exports.Count;final_saves=$gameplay.Count;exports=$exports} |
    ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $destinationDirectory 'exports.json') -Encoding utf8NoBOM
[pscustomobject]@{status='copied-and-hash-verified';files=$exports.Count;final_saves=$gameplay.Count;path=$destinationDirectory} | ConvertTo-Json -Compress

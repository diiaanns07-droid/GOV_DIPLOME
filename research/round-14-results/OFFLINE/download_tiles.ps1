param([string]$Build = '20261010', [switch]$Latest)
$ErrorActionPreference = 'Stop'
$TaskRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$TaskScratch = Join-Path $TaskRoot '.runtime\offline-download'
$TaskTiles = Join-Path $TaskRoot 'data\civic\astana\tiles'
New-Item -ItemType Directory -Force -Path $TaskScratch, $TaskTiles | Out-Null
$TaskZip = Join-Path $TaskScratch 'go-pmtiles_1.31.2_Windows_x86_64.zip'
$TaskCli = Join-Path $TaskScratch 'pmtiles.exe'
$TaskZipHash = 'a658baa4d7e55020aef6ca17bd9ff9faa1582671266b36f58c52db0ac8e785a1'
if (!(Test-Path -LiteralPath $TaskZip) -or (Get-FileHash -LiteralPath $TaskZip -Algorithm SHA256).Hash -ne $TaskZipHash) {
    Invoke-WebRequest 'https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles_1.31.2_Windows_x86_64.zip' -OutFile $TaskZip
}
if ((Get-FileHash -LiteralPath $TaskZip -Algorithm SHA256).Hash -ne $TaskZipHash) { throw 'CLI checksum mismatch' }
Expand-Archive -LiteralPath $TaskZip -DestinationPath $TaskScratch -Force
if ($Latest) {
    $TaskBuilds = Invoke-RestMethod 'https://build-metadata.protomaps.dev/builds.json'
    $Build = (($TaskBuilds | Sort-Object key -Descending | Select-Object -First 1).key -replace '\.pmtiles$', '')
}
if ($Build -notmatch '^\d{8}$') { throw 'Build must be YYYYMMDD' }
$TaskGraph = Get-Content -LiteralPath (Join-Path $TaskRoot 'engine\civic_scenarios\graphs\osm-astana-walking-20260506.graph.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$TaskBBox = $TaskGraph.bbox
# 111000 м/градус и максимальная широта дают консервативный запас не меньше 3 км.
$TaskLatPad = 3000.0 / 111000.0
$TaskLonPad = 3000.0 / (111000.0 * [Math]::Cos(([Math]::Max([Math]::Abs($TaskBBox[1]),[Math]::Abs($TaskBBox[3])) + $TaskLatPad) * [Math]::PI / 180))
$TaskExpanded = @($TaskBBox[0]-$TaskLonPad; $TaskBBox[1]-$TaskLatPad; $TaskBBox[2]+$TaskLonPad; $TaskBBox[3]+$TaskLatPad)
$TaskBounds = ($TaskExpanded | ForEach-Object { $_.ToString('F7', [Globalization.CultureInfo]::InvariantCulture) }) -join ','
$TaskPartial = Join-Path $TaskTiles 'astana.download.pmtiles'
$TaskFinal = Join-Path $TaskTiles 'astana.pmtiles'
if (!( [IO.Path]::GetFullPath($TaskFinal).StartsWith($TaskRoot + '\', [StringComparison]::OrdinalIgnoreCase))) { throw 'Output outside worktree' }
if (Test-Path -LiteralPath $TaskPartial) { throw 'Partial download already exists; inspect it before retrying.' }
& $TaskCli extract "https://build.protomaps.com/$Build.pmtiles" $TaskPartial "--bbox=$TaskBounds" --maxzoom=15 --download-threads=4
if ($LASTEXITCODE -ne 0) { throw 'Extraction failed. Daily builds expire; retry with -Latest after inspecting the partial file.' }
& $TaskCli verify $TaskPartial
if ($LASTEXITCODE -ne 0) { throw 'Archive verification failed' }
# Только завершённая проверенная выгрузка заменяет предыдущую карту.
Move-Item -LiteralPath $TaskPartial -Destination $TaskFinal -Force
& $TaskCli show $TaskFinal --header-json
Get-FileHash -LiteralPath $TaskFinal -Algorithm SHA256
Write-Output "Ready: $TaskFinal (source $Build, bbox $TaskBounds)"

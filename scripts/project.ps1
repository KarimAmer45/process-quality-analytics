param([string]$Action='demo',[string]$Python='python')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
if(Test-Path -LiteralPath "$projectRoot\.env") {
  foreach($line in Get-Content -LiteralPath "$projectRoot\.env") {
    if($line -match '^([A-Z_]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1],$Matches[2],'Process') }
  }
}
$localDeps=Join-Path $projectRoot '.local\pydeps'
if(Test-Path $localDeps) { $env:PYTHONPATH="$localDeps;$env:PYTHONPATH" }
$commands=@{migrate=@('scripts/migrate.py');demo=@('scripts/demo.py');seed=@('ingest/p1_simulate_plant.py');test=@('-m','pytest','-q','tests');export=@('scripts/export_results.py');load=@('ingest/reference_data.py');payload=@('ingest/journal_payload.py');validate=@('scripts/validate_reference.py')}
if(-not $commands.ContainsKey($Action)) { throw 'Unknown action' }
Push-Location $projectRoot
try { & $Python @($commands[$Action]); if($LASTEXITCODE -ne 0) { throw "Failed: $Action" } } finally { Pop-Location }

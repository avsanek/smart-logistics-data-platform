param([int]$TimeoutSeconds = 1800)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($projectRoot -match '^[Cc]:\\Users(?:\\|$)') { throw 'Workspace must be outside the restricted profile directory' }
Push-Location -LiteralPath $projectRoot
try {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    do {
        $state = & docker compose exec -T postgres psql -U logistics -d airflow -Atc "SELECT state FROM dag_run WHERE dag_id='smart_logistics' ORDER BY execution_date DESC LIMIT 1;" 2>$null
        if ($LASTEXITCODE -eq 0) {
            if ($state -eq 'success') { Write-Output 'PIPELINE_SUCCESS'; exit 0 }
            if ($state -eq 'failed') { throw 'Airflow DAG failed; inspect task logs in UI' }
        }
        Start-Sleep -Seconds 5
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "DAG did not complete within $TimeoutSeconds seconds"
} finally { Pop-Location }

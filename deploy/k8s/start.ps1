$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$localDir = Join-Path $projectRoot '.local'
New-Item -ItemType Directory -Force -Path $localDir | Out-Null
$env:MINIKUBE_HOME = $localDir
$env:KUBECONFIG = Join-Path $localDir 'kubeconfig'
$minikube = Join-Path $localDir 'minikube.exe'

function Run-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Program (exit code $LASTEXITCODE)" }
}

if (-not (Test-Path $minikube)) {
    Write-Host 'Downloading Minikube from GitHub...'
    $download = "$minikube.download"
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/kubernetes/minikube/releases/latest/download/minikube-windows-amd64.exe' -OutFile $download
    Move-Item -LiteralPath $download -Destination $minikube -Force
}
Run-Checked $minikube @('start', '-p', 'smeshariki', '--driver=docker', '--cpus=2', '--memory=4096')
$passwordFile = Join-Path $projectRoot 'KikoRiki-quotes/.secrets/postgres_password'
if (-not (Test-Path $passwordFile)) { throw 'Create the database secret first; see deploy/README.md.' }
Run-Checked 'kubectl' @('apply', '-f', (Join-Path $projectRoot 'deploy/k8s/namespace.yaml'))
$existingSecret = & kubectl -n smeshariki get secret postgres-auth -o name --ignore-not-found
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect PostgreSQL secret.' }
if (-not $existingSecret) {
    $existingPvc = & kubectl -n smeshariki get pvc postgres-data -o name --ignore-not-found
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect PostgreSQL volume.' }
    if ($existingPvc) { throw 'Existing PostgreSQL volume has no postgres-auth secret. Migrate it first; see deploy/README.md.' }
    Run-Checked 'kubectl' @('-n', 'smeshariki', 'create', 'secret', 'generic', 'postgres-auth', "--from-file=db_password=$passwordFile")
}
Run-Checked $minikube @('image', 'build', '-p', 'smeshariki', '-t', 'smeshariki-app:local', (Join-Path $projectRoot 'KikoRiki-quotes/backend/main'))
Run-Checked $minikube @('image', 'build', '-p', 'smeshariki', '-t', 'smeshariki-notification:local', (Join-Path $projectRoot 'KikoRiki-quotes/backend/notification'))
Run-Checked $minikube @('image', 'build', '-p', 'smeshariki', '-t', 'smeshariki-frontend:local', (Join-Path $projectRoot 'KikoRiki-quotes/frontend'))
$rendered = Join-Path $localDir 'kubernetes.yaml'
Run-Checked 'kubectl' @('kustomize', (Join-Path $projectRoot 'deploy/k8s'), '--load-restrictor', 'LoadRestrictionsNone', '-o', $rendered)
Run-Checked 'kubectl' @('apply', '-f', $rendered)
Run-Checked 'kubectl' @('-n', 'smeshariki', 'rollout', 'restart', 'deployment/app', 'deployment/frontend')
Write-Host 'Configure the Telegram Secret as explained in deploy/README.md.'
Write-Host 'Run: .local\minikube.exe -p smeshariki service frontend -n smeshariki --url'

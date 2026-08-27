$ErrorActionPreference = 'Stop'
$Repo = 'josephsocialmedia2-spec/immobili-in-zona'
$RepoUrl = 'https://github.com/josephsocialmedia2-spec/immobili-in-zona'
$RunnerDir = Join-Path $HOME 'F1-GitHub-Runner'
$Startup = [Environment]::GetFolderPath('Startup')
$Desktop = [Environment]::GetFolderPath('Desktop')

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
    $user = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = "$machine;$user"
}

function Ensure-WingetPackage($Command, $PackageId) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "Manca $Command e winget non è disponibile."
        }
        winget install -e --id $PackageId --accept-package-agreements --accept-source-agreements
        Refresh-Path
    }
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$Command non è disponibile dopo l'installazione. Riavvia Windows e rilancia questo file."
    }
}

function Test-GhAuth {
    $oldPref = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'SilentlyContinue'
        & gh auth status -h github.com *> $null
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPref
    }
    return ($code -eq 0)
}

Write-Host '=== F1 - AUTOMAZIONE GITHUB RADAR -> TELEFONATE ==='
Ensure-WingetPackage 'gh' 'GitHub.cli'
Ensure-WingetPackage 'py' 'Python.Python.3.13'

if (-not (Test-GhAuth)) {
    Write-Host ''
    Write-Host 'Serve un solo accesso GitHub iniziale.' -ForegroundColor Yellow
    Write-Host 'Si aprira il browser: accedi al tuo account GitHub e autorizza GitHub CLI.'
    $oldPref = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & gh auth login --web -h github.com -p https --scopes 'repo,workflow'
        $loginCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPref
    }
    if ($loginCode -ne 0 -or -not (Test-GhAuth)) {
        throw 'Accesso GitHub non completato. Rilancia il file e completa il login nel browser.'
    }
}

Write-Host 'GitHub CLI autenticato.' -ForegroundColor Green

New-Item -ItemType Directory -Force -Path $RunnerDir | Out-Null
Set-Location $RunnerDir

if (-not (Test-Path (Join-Path $RunnerDir 'run.cmd'))) {
    Write-Host 'Scarico l’ultima versione del GitHub Actions Runner...'
    $release = Invoke-RestMethod -Headers @{ 'User-Agent'='F1Immobiliare-Setup' } -Uri 'https://api.github.com/repos/actions/runner/releases/latest'
    $asset = $release.assets | Where-Object { $_.name -like 'actions-runner-win-x64-*.zip' } | Select-Object -First 1
    if (-not $asset) { throw 'Pacchetto runner Windows x64 non trovato.' }
    $zip = Join-Path $env:TEMP $asset.name
    Invoke-WebRequest -UseBasicParsing $asset.browser_download_url -OutFile $zip
    Expand-Archive -Path $zip -DestinationPath $RunnerDir -Force
}

$token = gh api --method POST "repos/$Repo/actions/runners/registration-token" --jq .token
if ($LASTEXITCODE -ne 0 -or -not $token) { throw 'Impossibile ottenere il token temporaneo del runner.' }

if (Test-Path (Join-Path $RunnerDir '.runner')) {
    $oldPref = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & (Join-Path $RunnerDir 'config.cmd') remove --token $token
        $removeCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldPref
    }
    if ($removeCode -ne 0) { Write-Host 'Vecchia registrazione non rimossa: proseguo con replace.' }
}

$runnerName = "$env:COMPUTERNAME-F1"
& (Join-Path $RunnerDir 'config.cmd') --unattended --url $RepoUrl --token $token --name $runnerName --labels 'f1-desktop' --work '_work' --replace
if ($LASTEXITCODE -ne 0) { throw 'Configurazione runner fallita.' }

# Avvio automatico nella SESSIONE UTENTE, non come servizio: Chrome/CAPTCHA restano visibili.
$ws = New-Object -ComObject WScript.Shell
$startLink = $ws.CreateShortcut((Join-Path $Startup 'F1 GitHub Runner.lnk'))
$startLink.TargetPath = (Join-Path $RunnerDir 'run.cmd')
$startLink.WorkingDirectory = $RunnerDir
$startLink.WindowStyle = 7
$startLink.Save()

$report = Join-Path $HOME 'Documents\F1_Directory_Microzone\LISTA_MATTINO.html'
$reportLink = $ws.CreateShortcut((Join-Path $Desktop 'F1 - Telefonate Radar.lnk'))
$reportLink.TargetPath = $report
$reportLink.WorkingDirectory = (Split-Path $report -Parent)
$reportLink.IconLocation = 'shell32.dll,220'
$reportLink.Save()

py -m pip install --disable-pip-version-check --quiet selenium openpyxl
if ($LASTEXITCODE -ne 0) { throw 'Installazione dipendenze Python fallita.' }

# Avvia subito il runner se non è già in esecuzione.
$running = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*$RunnerDir*run.cmd*" }
if (-not $running) {
    Start-Process -FilePath (Join-Path $RunnerDir 'run.cmd') -WorkingDirectory $RunnerDir -WindowStyle Minimized
}

# Primo test automatico: appena il runner è online, GitHub invia subito un job Telefonate PC.
Start-Sleep -Seconds 4
$oldPref = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & gh workflow run f1-telefonate-pc.yml --repo $Repo
    $workflowCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $oldPref
}
if ($workflowCode -eq 0) {
    Write-Host 'Primo job F1 Telefonate PC inviato a GitHub.' -ForegroundColor Green
} else {
    Write-Host 'Runner configurato; il primo job partira alla conclusione del prossimo Radar.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'CONFIGURAZIONE COMPLETATA.' -ForegroundColor Green
Write-Host 'Da ora: Radar GitHub completato -> workflow F1 Telefonate PC -> lavoro automatico su questo computer.'
Write-Host 'I numeri restano sul PC; GitHub riceve solo stato tecnico, comuni/vie e conteggi.'

param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][int]$ParentPid,
  [Parameter(Mandatory=$true)][string]$ExpectedVersion,
  [Parameter(Mandatory=$true)][string]$InstallDir,
  [Parameter(Mandatory=$true)][string]$LogDir
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$log = Join-Path $LogDir 'last-update.txt'
$setupLog = Join-Path $LogDir 'inno-setup.log'
function Record([string]$value) { ('{0:u} {1}' -f (Get-Date), $value) | Out-File -FilePath $log -Append -Encoding utf8 }
function Fail([string]$reason) {
  Record ('FAILED: ' + $reason)
  Add-Type -AssemblyName PresentationFramework
  [System.Windows.MessageBox]::Show("Hino update did not complete.`n`n$reason`n`nLogs: $LogDir", 'Hino Addon Manager', 'OK', 'Error') | Out-Null
  exit 1
}
try {
  Record ('Starting update to ' + $ExpectedVersion)
  if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) { Fail 'Verified installer no longer exists.' }
  $deadline = (Get-Date).AddSeconds(90)
  while ((Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) -and ((Get-Date) -lt $deadline)) {
    Start-Sleep -Milliseconds 500
  }
  if (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) { Fail 'Hino did not exit in time. Close Hino and try again.' }
  Record 'Main application exited; starting installer.'
  $installerArgs = @('/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/CLOSEAPPLICATIONS', ('/LOG="{0}"' -f $setupLog))
  $proc = Start-Process -FilePath $Installer -ArgumentList $installerArgs -Wait -PassThru
  Record ('Installer exit code: ' + $proc.ExitCode)
  if ($proc.ExitCode -ne 0) { Fail ('Installer failed or was cancelled (code ' + $proc.ExitCode + ').') }
  $exe = Join-Path $InstallDir 'HinoAddonManager.exe'
  if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { Fail 'The installed Hino executable was not found.' }
  # A per-user Inno uninstall entry can be read inconsistently from a separate
  # PowerShell process. A version file delivered by the same signed-off installer
  # is deterministic and does not rely on Windows Installed Apps indexing.
  $versionPath = Join-Path $InstallDir 'HinoAddonManager.version'
  if (-not (Test-Path -LiteralPath $versionPath -PathType Leaf)) {
    Fail 'The installer completed but the installed application version file is missing.'
  }
  $actual = (Get-Content -LiteralPath $versionPath -Raw -ErrorAction Stop).Trim()
  Record ('Installed application version file: ' + $actual)
  if ($actual -ne $ExpectedVersion) {
    Fail ('Installed application reports ' + $actual + ' instead of ' + $ExpectedVersion + '.')
  }
  Record ('Verified installed version ' + $ExpectedVersion + '; restarting app.')
  Start-Process -FilePath $exe | Out-Null
} catch { Fail $_.Exception.Message }

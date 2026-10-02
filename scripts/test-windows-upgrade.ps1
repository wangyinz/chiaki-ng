param([Parameter(Mandatory=$true)][string]$Installer)
$ErrorActionPreference = 'Stop'
$installerPath = (Resolve-Path $Installer).Path
$root = Join-Path $env:RUNNER_TEMP 'chiaki-upgrade-smoke'
if (-not $env:RUNNER_TEMP) { throw 'Run this isolated smoke test only on a CI runner.' }
$sourceExe = (Resolve-Path 'chiaki-ng-Win/chiaki.exe').Path
$expectedHash = (Get-FileHash $sourceExe -Algorithm SHA256).Hash
$profile = Join-Path $env:APPDATA 'Chiaki/Chiaki'
$marker = Join-Path $profile 'ci-upgrade-sentinel.txt'
$registry = 'HKCU:\Software\Chiaki\Chiaki'
$sentinel = [guid]::NewGuid().ToString()
function Install([string]$Extra, [string]$LogName) {
    $log = Join-Path $env:RUNNER_TEMP $LogName
    $args = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER /LOG=`"$log`" $Extra"
    $p = Start-Process -FilePath $installerPath -ArgumentList $args -PassThru -Wait
    if ($p.ExitCode -ne 0) { Get-Content $log -Tail 100; throw "Installer exit $($p.ExitCode)" }
}
Install "/DIR=`"$root`"" 'chiaki-install-first.log'
$installedExe = Join-Path $root 'chiaki.exe'
if ((Get-FileHash $installedExe).Hash -ne $expectedHash) { throw 'First install binary mismatch.' }
New-Item -ItemType Directory -Force $profile | Out-Null
Set-Content -LiteralPath $marker -Value $sentinel -NoNewline
New-Item -Path $registry -Force | Out-Null
New-ItemProperty -Path $registry -Name 'AllyUpgradeCiSentinel' -Value $sentinel -PropertyType String -Force | Out-Null
# Reinstall must overwrite even if the incoming numeric upstream version is equal.
[IO.File]::WriteAllBytes($installedExe, [Text.Encoding]::UTF8.GetBytes('old application binary sentinel'))
# No /DIR on the second run: it must discover the same AppId's previous directory.
Install '' 'chiaki-install-overwrite.log'
if ((Get-FileHash $installedExe).Hash -ne $expectedHash) { throw 'Overwrite did not replace the application.' }
if ((Get-Content -Raw $marker) -ne $sentinel) { throw 'AppData changed during upgrade.' }
if ((Get-ItemProperty $registry).AllyUpgradeCiSentinel -ne $sentinel) { throw 'User settings changed during upgrade.' }
$uninstall = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{A329DCDE-074D-4C82-959A-3CFAC9A26B1F}_is1'
$installLocation = (Get-ItemProperty $uninstall).InstallLocation.TrimEnd('\')
if ($installLocation -ne $root.TrimEnd('\')) { throw 'Previous install path was not reused.' }
Remove-Item -LiteralPath $marker
Remove-ItemProperty -Path $registry -Name 'AllyUpgradeCiSentinel'
'In-place install smoke passed: stable AppId, same directory, replaced binary, preserved user settings.'

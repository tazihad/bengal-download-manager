# Bengal Download Manager — Windows Release & Build Script
# Usage: .\build\windows\build-scripts\build_windows.ps1 [-Version "0.2.46"] [-SkipBuild] [-SkipInstaller] [-SkipArchive] [-SkipBinaries]

param(
    [string]$Version       = "",
    [switch]$SkipBuild,
    [switch]$SkipInstaller,
    [switch]$SkipArchive,
    [switch]$SkipBinaries
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir   = $PSScriptRoot
$WindowsDir  = (Get-Item "$ScriptDir\..").FullName
$BuildDir    = (Get-Item "$WindowsDir\..").FullName
$RootDir     = (Get-Item "$BuildDir\..").FullName
$DistDir     = "$RootDir\dist"
$WinDistDir  = "$DistDir\windows"
$BinDir      = "$WindowsDir\bin"
$ConfigDir   = "$WindowsDir\config"
$SpecFile    = "$ConfigDir\bengal-download-manager.spec"
$IssFile     = "$ConfigDir\installer.iss"
$VersionFile = "$RootDir\VERSION"

# ── 1. Resolve Version ───────────────────────────────────────────────────────
if ([string]::IsNullOrWhiteSpace($Version)) {
    if (Test-Path $VersionFile) {
        $Version = (Get-Content $VersionFile -Raw).Trim().TrimStart("v")
    } else {
        $Version = "0.2.46"
    }
}
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host " Building Bengal Download Manager Windows Release v$Version" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan

# ── 2. Tool Resolution ───────────────────────────────────────────────────────
function Find-Tool([string]$name, [string[]]$extra) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in $extra) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

$ISCC = Find-Tool "iscc" @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$7Z = Find-Tool "7z" @(
    "C:\Program Files\7-Zip\7z.exe",
    "C:\Program Files (x86)\7-Zip\7z.exe"
)

if (-not (Test-Path $WinDistDir)) {
    New-Item -ItemType Directory -Path $WinDistDir -Force | Out-Null
}
if (-not (Test-Path $BinDir)) {
    New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
}

# ── 3. Third-party Windows Binaries (yt-dlp, aria2c, ffmpeg) ─────────────────
if (-not $SkipBinaries) {
    Write-Host "`n[1/4] Checking helper binaries in $BinDir..." -ForegroundColor Yellow
    
    # yt-dlp.exe
    $YtDlp = "$BinDir\yt-dlp.exe"
    if (-not (Test-Path $YtDlp)) {
        Write-Host "  Downloading yt-dlp.exe..." -ForegroundColor Gray
        Invoke-WebRequest -Uri "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe" -OutFile $YtDlp
    } else {
        Write-Host "  yt-dlp.exe is up to date." -ForegroundColor DarkGray
    }

    # aria2c.exe
    $Aria2 = "$BinDir\aria2c.exe"
    if (-not (Test-Path $Aria2)) {
        Write-Host "  Downloading aria2c Windows bundle..." -ForegroundColor Gray
        $AriaZip = "$BinDir\aria2.zip"
        Invoke-WebRequest -Uri "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip" -OutFile $AriaZip
        Expand-Archive -Path $AriaZip -DestinationPath "$BinDir\aria2_tmp" -Force
        $AriaExe = Get-ChildItem -Path "$BinDir\aria2_tmp" -Filter "aria2c.exe" -Recurse | Select-Object -First 1
        if ($AriaExe) {
            Copy-Item -Path $AriaExe.FullName -Destination $Aria2 -Force
        }
        Remove-Item -Recurse -Force "$BinDir\aria2_tmp", $AriaZip
    } else {
        Write-Host "  aria2c.exe is ready." -ForegroundColor DarkGray
    }
}

# ── 4. Build Standalone Executable (PyInstaller) ─────────────────────────────
if (-not $SkipBuild) {
    Write-Host "`n[2/4] Building standalone executable with Windows DWM theme fixes..." -ForegroundColor Yellow
    Push-Location $RootDir
    try {
        $WorkDir = "$RootDir\.pyinstaller-build"
        if (Get-Command "uv" -ErrorAction SilentlyContinue) {
            uv run pyinstaller --noconfirm --distpath "$DistDir" --workpath "$WorkDir" "$SpecFile"
        } else {
            pyinstaller --noconfirm --distpath "$DistDir" --workpath "$WorkDir" "$SpecFile"
        }
    } finally {
        Pop-Location
    }
    Write-Host "  Executable build finished: $DistDir\bengal-download-manager" -ForegroundColor Green
}

# ── 5. Inno Setup Installer ──────────────────────────────────────────────────
if (-not $SkipInstaller) {
    Write-Host "`n[3/4] Compiling Inno Setup installer..." -ForegroundColor Yellow
    if ($ISCC) {
        & $ISCC "/DAppVersion=$Version" "$IssFile"
        Write-Host "  Installer generated: $WinDistDir\BengalSetup-$Version.exe" -ForegroundColor Green
    } else {
        Write-Warning "ISCC (Inno Setup) not found. Skipping installer generation."
    }
}

# ── 6. Portable ZIP Archive ──────────────────────────────────────────────────
if (-not $SkipArchive) {
    Write-Host "`n[4/4] Creating portable archive..." -ForegroundColor Yellow
    $ZipFile = "$WinDistDir\bengal-download-manager-$Version-windows-x64.zip"
    if (Test-Path $ZipFile) { Remove-Item -Force $ZipFile }
    
    if ($7Z) {
        & $7Z a -tzip "$ZipFile" "$DistDir\bengal-download-manager\*" | Out-Null
    } else {
        Compress-Archive -Path "$DistDir\bengal-download-manager\*" -DestinationPath "$ZipFile" -Force
    }
    Write-Host "  Portable ZIP generated: $ZipFile" -ForegroundColor Green
}

Write-Host "`n========================================================" -ForegroundColor Green
Write-Host " Windows build process completed successfully!" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Green

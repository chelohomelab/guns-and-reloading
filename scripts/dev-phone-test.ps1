# Dev-environment helper — NOT part of the deployed app. Run from an elevated Windows PowerShell
# (this machine's own WSL2 dev setup only) to expose the WSL2 dev server to the home WiFi network
# for testing on a phone, and to cleanly tear that down again afterward.
#
# Usage:
#   .\dev-phone-test.ps1 -Enable
#   .\dev-phone-test.ps1 -Disable
#
# What -Enable does:
#   1. Detects the current WSL2 instance's IP (changes every WSL restart, so this is looked up
#      fresh each time rather than hardcoded).
#   2. Adds a netsh portproxy rule forwarding <Windows LAN IP>:<port> -> <WSL2 IP>:<port>.
#   3. Adds a matching inbound Windows Firewall rule.
#   4. Restarts the dev server (inside WSL2) bound to 0.0.0.0 instead of 127.0.0.1, so the
#      portproxy above actually has something to forward to.
#   5. Prints the phone-facing URL and a reminder about the one-time Chrome flag needed for
#      service workers to register over plain http:// (chrome://flags/#unsafely-treat-insecure-
#      origin-as-secure) — this only ever matters for this ad-hoc dev-testing setup; the
#      production HTTPS story for real users is a separate, proper feature, not this script.
#
# -Disable reverses all of it: removes the portproxy rule and firewall rule, and restarts the
# dev server back to 127.0.0.1-only.

param(
    [switch]$Enable,
    [switch]$Disable,
    [int]$Port = 8123,
    [string]$WslDistro = "",
    [string]$RepoPath = "~/inventory-and-reloading"
)

$ErrorActionPreference = "Stop"
$ruleName = "WSL Inventory Dev $Port"

function Assert-Admin {
    $isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        Write-Error "Run this from an elevated PowerShell (right-click -> Run as administrator)."
        exit 1
    }
}

function Invoke-Wsl([string]$Command) {
    if ($WslDistro) {
        wsl -d $WslDistro -e bash -lc $Command
    } else {
        wsl -e bash -lc $Command
    }
}

function Get-WslIp {
    $ip = (Invoke-Wsl "ip addr show eth0 | grep 'inet ' | awk '{print `$2}' | cut -d/ -f1").Trim()
    if (-not $ip) { throw "Could not detect the WSL2 instance's IP — is WSL running?" }
    return $ip
}

function Get-WifiLanIp {
    $addr = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -like "Wi-Fi*" -and $_.IPAddress -notlike "169.254.*" } |
        Select-Object -First 1
    if (-not $addr) { throw "Could not detect a Wi-Fi IPv4 address — are you connected to WiFi?" }
    return $addr.IPAddress
}

if ($Enable) {
    Assert-Admin
    $wslIp = Get-WslIp
    $wifiIp = Get-WifiLanIp

    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port 2>$null | Out-Null
    netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$Port connectaddress=$wslIp connectport=$Port | Out-Null

    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -LocalPort $Port -Protocol TCP -Action Allow | Out-Null
    }

    Write-Host "Restarting dev server bound to 0.0.0.0 ..."
    Invoke-Wsl "pkill -f 'uvicorn main:app' 2>/dev/null; sleep 1; cd $RepoPath && nohup .venv/bin/python3 .venv/bin/uvicorn main:app --host 0.0.0.0 --port $Port --reload > /tmp/uvicorn-phone-test.log 2>&1 & disown; sleep 2; curl -s -o /dev/null -w 'local check: %{http_code}\n' http://127.0.0.1:$Port/"

    Write-Host ""
    Write-Host "Phone testing enabled." -ForegroundColor Green
    Write-Host "  1. On your phone (same WiFi): http://${wifiIp}:${Port}"
    Write-Host "  2. First time only: visit chrome://flags/#unsafely-treat-insecure-origin-as-secure"
    Write-Host "     add http://${wifiIp}:${Port} , set it to Enabled, and relaunch Chrome."
    Write-Host "  3. When done, run: .\dev-phone-test.ps1 -Disable"
    Write-Host ""
}
elseif ($Disable) {
    Assert-Admin

    netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$Port 2>$null | Out-Null
    Remove-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue

    Write-Host "Restarting dev server bound to 127.0.0.1 only ..."
    Invoke-Wsl "pkill -f 'uvicorn main:app' 2>/dev/null; sleep 1; cd $RepoPath && nohup .venv/bin/python3 .venv/bin/uvicorn main:app --host 127.0.0.1 --port $Port --reload > /tmp/uvicorn-phone-test.log 2>&1 & disown; sleep 2; curl -s -o /dev/null -w 'local check: %{http_code}\n' http://127.0.0.1:$Port/"

    Write-Host ""
    Write-Host "Phone testing disabled — dev server is back to loopback-only." -ForegroundColor Yellow
    Write-Host ""
}
else {
    Write-Host "Usage: .\dev-phone-test.ps1 -Enable | -Disable  [-Port 8123] [-WslDistro <name>] [-RepoPath <path>]"
}

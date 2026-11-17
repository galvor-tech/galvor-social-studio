# One-time setup: publish the studio at https://<hostname> through a Cloudflare Tunnel.
# No router/firewall changes: the tunnel only makes outbound connections from this laptop.
# Needs: a Cloudflare account where the galvor.ai domain (DNS) is managed.
# Run in PowerShell:   powershell -ExecutionPolicy Bypass -File tools\setup_tunnel.ps1 -Hostname studio.galvor.ai
param([string]$Hostname = "studio.galvor.ai", [string]$TunnelName = "galvor-studio", [int]$Port = 5055)
$ErrorActionPreference = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "Installing cloudflared..." -ForegroundColor Cyan
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
}

$cfDir = Join-Path $env:USERPROFILE ".cloudflared"
if (-not (Test-Path (Join-Path $cfDir "cert.pem"))) {
    Write-Host "A browser window will open: log in to Cloudflare and pick the galvor.ai zone." -ForegroundColor Cyan
    cloudflared tunnel login
}

$existing = cloudflared tunnel list --output json | ConvertFrom-Json | Where-Object { $_.name -eq $TunnelName }
if (-not $existing) { cloudflared tunnel create $TunnelName | Out-Host
    $existing = cloudflared tunnel list --output json | ConvertFrom-Json | Where-Object { $_.name -eq $TunnelName } }
$id = $existing.id
cloudflared tunnel route dns $TunnelName $Hostname | Out-Host

$config = @"
tunnel: $id
credentials-file: $cfDir\$id.json
ingress:
  - hostname: $Hostname
    service: http://localhost:$Port
  - service: http_status:404
"@
$studioCfg = Join-Path $PSScriptRoot "..\data\tunnel.yml"
Set-Content -Path $studioCfg -Value $config -Encoding UTF8
Write-Host "`nDone. Tunnel config written to data\tunnel.yml" -ForegroundColor Green
Write-Host "start_studio.bat will now start the tunnel automatically."
Write-Host "Next: in the studio, Settings -> Access, set the web address to https://$Hostname" -ForegroundColor Yellow

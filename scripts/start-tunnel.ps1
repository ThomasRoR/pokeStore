<#
Start local backend (uvicorn), frontend (next) and Cloudflare Tunnel.

Prereqs:
- Install cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation
- Have Node.js and Python virtualenv set up (see README)

Usage:
powershell -ExecutionPolicy Bypass -File .\\scripts\\start-tunnel.ps1

This script starts processes in the background. The tunnel will print the public URL to the cloudflared process output.
#>

param()

function Start-BackgroundProcess($file, $args, $cwd) {
    Write-Host "Starting: $file $args (cwd: $cwd)"
    $si = New-Object System.Diagnostics.ProcessStartInfo
    $si.FileName = $file
    $si.Arguments = $args
    $si.WorkingDirectory = $cwd
    $si.RedirectStandardOutput = $true
    $si.RedirectStandardError = $true
    $si.UseShellExecute = $false
    $si.CreateNoWindow = $true

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $si
    $p.EnableRaisingEvents = $true
    $p.Start() | Out-Null

    Register-ObjectEvent -InputObject $p -EventName "OutputDataReceived" -Action { if ($Event.SourceEventArgs.Data) { Write-Host $Event.SourceEventArgs.Data } }
    Register-ObjectEvent -InputObject $p -EventName "ErrorDataReceived" -Action { if ($Event.SourceEventArgs.Data) { Write-Host $Event.SourceEventArgs.Data } }
    $p.BeginOutputReadLine()
    $p.BeginErrorReadLine()
    return $p
}

Push-Location $PSScriptRoot/..

# 1) start backend
$python = Join-Path -Path $PWD -ChildPath ".venv\Scripts\python.exe"
if (Test-Path $python) {
    $backendProc = Start-BackgroundProcess $python "-m uvicorn main:app --reload --port 8000" "backend"
} else {
    Write-Warning "Python executable not found at $python. Start backend manually: cd backend; .venv\\Scripts\\Activate.ps1; python -m uvicorn main:app --reload --port 8000"
}

# 2) start frontend
if (Get-Command npm -ErrorAction SilentlyContinue) {
    $frontendProc = Start-BackgroundProcess "npm" "run dev" "frontend"
} else {
    Write-Warning "npm not found in PATH. Start frontend manually: cd frontend; npm install; npm run dev"
}

# 3) start cloudflared tunnel (quick tunnel)
if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
    Write-Host "Starting cloudflared tunnel (quick). The public URL will appear in its output."
    $tunnelProc = Start-BackgroundProcess "cloudflared" "tunnel --url http://localhost:3000" "."
} else {
    Write-Warning "cloudflared not found. Install from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation"
}

Write-Host "Started processes. Keep this PowerShell window open to keep background processes running."

Pop-Location

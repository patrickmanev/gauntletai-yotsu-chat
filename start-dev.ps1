# Set UTF-8 encoding and output encoding
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "UTF-8"

# Function to check if a port is in use
function Test-PortInUse {
    param($Port)
    $listener = $null
    try {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        return $false
    }
    catch {
        return $true
    }
    finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

# Check if ports are available
if (Test-PortInUse 8000) {
    Write-Host "Error: Port 8000 is already in use (Backend)" -ForegroundColor Red
    exit 1
}
if (Test-PortInUse 3000) {
    Write-Host "Error: Port 3000 is already in use (Frontend)" -ForegroundColor Red
    exit 1
}

Write-Host "Starting Yotsu Chat development servers..." -ForegroundColor Green

# Start backend server
$backendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    & "./yotsu-chat-venv/Scripts/Activate.ps1"
    uvicorn yotsu_chat.main:app --reload --port 8000
}

# Start frontend server
$frontendJob = Start-Job -ScriptBlock {
    Set-Location "$using:PWD/yotsu-chat-frontend"
    npm run dev
}

Write-Host "`nServers starting up..." -ForegroundColor Yellow
Write-Host "Backend will be available at: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Frontend will be available at: http://localhost:3000" -ForegroundColor Cyan
Write-Host "`nPress Ctrl+C to stop both servers`n" -ForegroundColor Yellow

# Show realtime output from both jobs
try {
    while ($true) {
        # Handle backend output
        Receive-Job -Job $backendJob | ForEach-Object {
            Write-Host "[Backend] $_" -ForegroundColor Blue
        }
        
        # Handle frontend output
        Receive-Job -Job $frontendJob | ForEach-Object {
            # Clean up Next.js specific characters
            $cleanOutput = $_ -replace 'Γû▓', '[Next.js]' -replace 'Γ£ô', '>' -replace 'Γùï', '⌛'
            Write-Host "[Frontend] $cleanOutput" -ForegroundColor Green
        }
        
        Start-Sleep -Milliseconds 100
    }
}
finally {
    # Cleanup on script exit
    Stop-Job -Job $backendJob, $frontendJob
    Remove-Job -Job $backendJob, $frontendJob
    Write-Host "`nShutting down servers..." -ForegroundColor Yellow
} 
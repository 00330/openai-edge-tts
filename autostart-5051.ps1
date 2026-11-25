$ErrorActionPreference = "SilentlyContinue"
$dir = "C:\Users\Administrator\Desktop\openai-edge-tts"
$port = 5051

$listening = Get-NetTCPConnection -LocalPort $port -State Listen
if ($listening) { exit 0 }

Start-Process -FilePath "$dir\.venv\Scripts\python.exe" -ArgumentList "server.py" -WorkingDirectory "$dir\app" -WindowStyle Hidden -RedirectStandardOutput "$dir\server.log" -RedirectStandardError "$dir\server.err"

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    $up = Get-NetTCPConnection -LocalPort $port -State Listen
    if ($up) { exit 0 }
}
exit 1

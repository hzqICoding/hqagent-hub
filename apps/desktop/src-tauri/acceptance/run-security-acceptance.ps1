param(
    [string]$Python = "E:\SoftWare\Python313\python.exe",
    [string]$WorkRoot = (Join-Path $PSScriptRoot ".work")
)

$ErrorActionPreference = "Stop"
$root = [IO.Path]::GetFullPath($WorkRoot)
$runtime = Join-Path $root "runtime"
$ready = Join-Path $root "ready.json"
$descriptor = Join-Path $runtime "hub.json"

if (Test-Path -LiteralPath $root) {
    Remove-Item -LiteralPath $root -Recurse -Force
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null

$stub = Start-Process -FilePath $Python -WindowStyle Hidden -PassThru -ArgumentList @(
    (Join-Path $PSScriptRoot "hub_stub.py"),
    "--runtime-dir", $runtime,
    "--ready-file", $ready
)

function Wait-Ready {
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $ready) {
            return Get-Content -Raw -LiteralPath $ready | ConvertFrom-Json
        }
        Start-Sleep -Milliseconds 100
    }
    throw "Hub stub did not become ready"
}

function Get-HttpStatus {
    param(
        [string]$Url,
        [string[]]$Headers = @(),
        [string]$Method = "GET"
    )
    $arguments = @("-s", "-o", "NUL", "-w", "%{http_code}", "-X", $Method)
    foreach ($header in $Headers) {
        $arguments += @("-H", $header)
    }
    $arguments += $Url
    return (& curl.exe @arguments).Trim()
}

function Invoke-WsHandshake {
    param(
        [int]$Port,
        [string]$Ticket,
        [string]$Origin
    )
    $client = [System.Net.Sockets.TcpClient]::new("127.0.0.1", $Port)
    try {
        $stream = $client.GetStream()
        $key = [Convert]::ToBase64String([Guid]::NewGuid().ToByteArray())
        $request = "GET /api/v1/events/stream?ticket=$Ticket&after=0 HTTP/1.1`r`n" +
            "Host: 127.0.0.1:$Port`r`n" +
            "Origin: $Origin`r`n" +
            "Upgrade: websocket`r`n" +
            "Connection: Upgrade`r`n" +
            "Sec-WebSocket-Key: $key`r`n" +
            "Sec-WebSocket-Version: 13`r`n`r`n"
        $bytes = [Text.Encoding]::ASCII.GetBytes($request)
        $stream.Write($bytes, 0, $bytes.Length)
        $buffer = [byte[]]::new(4096)
        $read = $stream.Read($buffer, 0, $buffer.Length)
        $response = [Text.Encoding]::ASCII.GetString($buffer, 0, $read)
        return ($response -split "`r`n")[0]
    }
    finally {
        $client.Dispose()
    }
}

try {
    $connection = Wait-Ready
    $baseUrl = "http://127.0.0.1:$($connection.port)"
    $authorization = "Authorization: Bearer $($connection.token)"
    $allowedOrigin = "Origin: http://tauri.localhost"

    $unauthorized = Get-HttpStatus -Url "$baseUrl/api/v1/bootstrap"
    if ($unauthorized -ne "401") { throw "Expected 401, got $unauthorized" }
    "HTTP_NO_TOKEN=$unauthorized"

    $badOrigin = Get-HttpStatus -Url "$baseUrl/api/v1/bootstrap" -Headers @(
        $authorization,
        "Origin: https://evil.example"
    )
    if ($badOrigin -ne "403") { throw "Expected bad Origin 403, got $badOrigin" }
    "HTTP_BAD_ORIGIN=$badOrigin"

    $ticketResponse = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/ws-ticket" -Headers @{
        Authorization = "Bearer $($connection.token)"
        Origin = "http://tauri.localhost"
    } -ContentType "application/json" -Body '{"purpose":"events"}'
    if ($ticketResponse.ttlSeconds -ne 30) { throw "Ticket TTL is not 30 seconds" }
    if ($ticketResponse.ticket.Length -lt 43) { throw "Ticket is too short" }
    "TICKET_TTL=$($ticketResponse.ttlSeconds)"

    $first = Invoke-WsHandshake -Port $connection.port -Ticket $ticketResponse.ticket -Origin "http://tauri.localhost"
    $replay = Invoke-WsHandshake -Port $connection.port -Ticket $ticketResponse.ticket -Origin "http://tauri.localhost"
    if ($first -notmatch " 101 ") { throw "Expected first handshake 101, got $first" }
    if ($replay -notmatch " 401 ") { throw "Expected replay 401, got $replay" }
    "WS_FIRST=$first"
    "WS_REPLAY=$replay"

    $originTicket = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/ws-ticket" -Headers @{
        Authorization = "Bearer $($connection.token)"
        Origin = "http://tauri.localhost"
    } -ContentType "application/json" -Body '{"purpose":"events"}'
    $wsBadOrigin = Invoke-WsHandshake -Port $connection.port -Ticket $originTicket.ticket -Origin "https://evil.example"
    if ($wsBadOrigin -notmatch " 403 ") { throw "Expected WS bad Origin 403, got $wsBadOrigin" }
    "WS_BAD_ORIGIN=$wsBadOrigin"

    $acl = Get-Acl -LiteralPath $descriptor
    $identity = $acl.Owner
    $allowRules = @($acl.Access | Where-Object AccessControlType -eq "Allow")
    if ($allowRules.Count -eq 0) { throw "Descriptor has no allow ACE" }
    foreach ($rule in $allowRules) {
        if ($rule.IsInherited) { throw "Descriptor still has inherited ACE: $rule" }
        if ($rule.IdentityReference.Value -ine $identity) {
            throw "Descriptor grants another principal: $($rule.IdentityReference.Value)"
        }
    }
    "ACL_OWNER=$($acl.Owner)"
    "ACL_ALLOWED=$($allowRules.IdentityReference.Value -join ',')"
    "ACL_INHERITED=$($allowRules.IsInherited -join ',')"
    & icacls.exe $descriptor

    $runtimeDescriptor = Get-Content -Raw -LiteralPath $descriptor | ConvertFrom-Json
    if ($runtimeDescriptor.baseUrl -ne $baseUrl) { throw "Descriptor baseUrl mismatch" }
    if ($runtimeDescriptor.pid -ne $connection.pid) { throw "Descriptor pid mismatch" }
    "DESCRIPTOR_INSTANCE_ID=$($runtimeDescriptor.instanceId)"
    "SECURITY_ACCEPTANCE=PASS"
}
finally {
    if ($stub -and -not $stub.HasExited) {
        Stop-Process -Id $stub.Id -Force
        $stub.WaitForExit()
    }
}

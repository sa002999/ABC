$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$pluginRoot = Join-Path $PSScriptRoot 'kinu-tabi'
$manifest = Get-Content -LiteralPath (Join-Path $pluginRoot 'plugin.json') -Raw | ConvertFrom-Json
$mcp = Get-Content -LiteralPath (Join-Path $pluginRoot 'mcp.json') -Raw | ConvertFrom-Json
if ($manifest.name -ne 'kinu-tabi' -or $manifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid plugin identity/version.' }
if ($manifest.'$schema' -ne 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json') { throw 'Invalid plugin schema.' }
if ($mcp.'$schema' -ne 'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json') { throw 'Invalid MCP schema.' }
if ($mcp.mcpServers.kinutabi.type -ne 'streamable-http') { throw 'Expected HTTP MCP.' }
$files = @('plugin.json', 'mcp.json', 'README.md', 'skills/kinu-tabi/SKILL.md')
$archivePath = Join-Path $PSScriptRoot "kinu-tabi-$($manifest.version).zip"
$temporaryPath = Join-Path $PSScriptRoot ([guid]::NewGuid().ToString() + '.zip')
$archive = [System.IO.Compression.ZipFile]::Open($temporaryPath, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($file in $files) {
        $source = Join-Path $pluginRoot $file
        $content = Get-Content -LiteralPath $source -Raw -Encoding UTF8
        if ($content -match 'kt_mcp_[A-Za-z0-9_-]{43}') { throw "Credential found in $file" }
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $source, "kinu-tabi/$file")
    }
} finally { $archive.Dispose() }
$check = [System.IO.Compression.ZipFile]::OpenRead($temporaryPath)
try {
    if ($check.Entries.Count -ne $files.Count) { throw 'Unexpected archive entries.' }
    $check.Entries | ForEach-Object { $_.FullName }
} finally { $check.Dispose() }
Move-Item -LiteralPath $temporaryPath -Destination $archivePath -Force
Write-Output "Created $archivePath"

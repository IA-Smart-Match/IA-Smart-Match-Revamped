$ErrorActionPreference = 'Stop'

$dbPath     = 'C:\Users\thuys\OneDrive\Documents\Database1.accdb'
$backupPath = 'C:\Users\thuys\OneDrive\Documents\Database1.backup-20260926.accdb'
$csvPath    = Join-Path $PSScriptRoot 'event_major_fit.csv'
$eventIds   = @('E11', 'E12')

Copy-Item $dbPath $backupPath -Force
Write-Output "Backup written: $backupPath"

$conn = New-Object System.Data.Odbc.OdbcConnection "Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=$dbPath;"
$conn.Open()

function Read-Text($reader, $i) { if ($reader.IsDBNull($i)) { '' } else { $reader.GetString($i) } }

# --- target_major for E11/E12
$targets = @{}
$cmd = $conn.CreateCommand()
$cmd.CommandText = "SELECT event_id, target_major FROM Events WHERE event_id IN ('E11','E12')"
$r = $cmd.ExecuteReader()
while ($r.Read()) { $targets[$(Read-Text $r 0)] = $(Read-Text $r 1) }
$r.Close()
foreach ($e in $eventIds) {
    if (-not $targets.ContainsKey($e)) { $conn.Close(); throw "Event $e not found in Events" }
    Write-Output "$e target_major: $($targets[$e])"
}

# --- all profiles
$profiles = New-Object System.Collections.Generic.List[object]
$cmd = $conn.CreateCommand()
$cmd.CommandText = "SELECT profile_id, first_name, last_name, major FROM Profiles"
$r = $cmd.ExecuteReader()
while ($r.Read()) {
    $profiles.Add([pscustomobject]@{
        profile_id = $(Read-Text $r 0)
        first_name = $(Read-Text $r 1)
        last_name  = $(Read-Text $r 2)
        major      = $(Read-Text $r 3)
    })
}
$r.Close()
Write-Output "Profiles read: $($profiles.Count)"

function Test-MajorFit([string]$major, [string]$target) {
    if ($target.Trim().ToLowerInvariant() -eq 'all majors') { return $true }
    return $major.Trim().ToLowerInvariant() -eq $target.Trim().ToLowerInvariant()
}

# --- recreate EventMajorFit
$exists = @($conn.GetSchema('Tables').Rows) | Where-Object { $_['TABLE_TYPE'] -eq 'TABLE' -and $_['TABLE_NAME'] -eq 'EventMajorFit' }
if ($exists) {
    $cmd = $conn.CreateCommand()
    $cmd.CommandText = 'DROP TABLE EventMajorFit'
    $cmd.ExecuteNonQuery() | Out-Null
    Write-Output 'Dropped existing EventMajorFit'
}
$cmd = $conn.CreateCommand()
try {
    $cmd.CommandText = 'CREATE TABLE EventMajorFit (profile_id TEXT(50) PRIMARY KEY, first_name TEXT(100), last_name TEXT(100), major TEXT(255), E11_major_fit INTEGER, E12_major_fit INTEGER)'
    $cmd.ExecuteNonQuery() | Out-Null
} catch {
    Write-Output "PRIMARY KEY rejected, creating plain table: $($_.Exception.Message)"
    $cmd.CommandText = 'CREATE TABLE EventMajorFit (profile_id TEXT(50), first_name TEXT(100), last_name TEXT(100), major TEXT(255), E11_major_fit INTEGER, E12_major_fit INTEGER)'
    $cmd.ExecuteNonQuery() | Out-Null
}

# --- insert + collect rows
$ins = $conn.CreateCommand()
$ins.CommandText = 'INSERT INTO EventMajorFit (profile_id, first_name, last_name, major, E11_major_fit, E12_major_fit) VALUES (?, ?, ?, ?, ?, ?)'
1..6 | ForEach-Object { $ins.Parameters.Add((New-Object System.Data.Odbc.OdbcParameter)) | Out-Null }

$rows = New-Object System.Collections.Generic.List[object]
foreach ($p in $profiles) {
    $e11 = [int](Test-MajorFit $p.major $targets['E11'])
    $e12 = [int](Test-MajorFit $p.major $targets['E12'])
    $ins.Parameters[0].Value = $p.profile_id
    $ins.Parameters[1].Value = $p.first_name
    $ins.Parameters[2].Value = $p.last_name
    $ins.Parameters[3].Value = $p.major
    $ins.Parameters[4].Value = $e11
    $ins.Parameters[5].Value = $e12
    $ins.ExecuteNonQuery() | Out-Null
    $rows.Add([pscustomobject]@{
        profile_id    = $p.profile_id
        first_name    = $p.first_name
        last_name     = $p.last_name
        major         = $p.major
        E11_major_fit = $e11
        E12_major_fit = $e12
    })
}
$conn.Close()

$rows | Export-Csv -NoTypeInformation -Path $csvPath -Encoding UTF8
Write-Output "Wrote $($rows.Count) rows to EventMajorFit"
Write-Output "E11 matches: $(@($rows | Where-Object { $_.E11_major_fit -eq 1 }).Count)"
Write-Output "E12 matches: $(@($rows | Where-Object { $_.E12_major_fit -eq 1 }).Count)"
Write-Output "CSV: $csvPath"

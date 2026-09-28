# Usage: powershell -File tools/compute_event_major_fit.ps1 [-DbPath <file.accdb>] [-CsvPath <out.csv>] [-WriteTable]
# Reads Profiles/Events from the Access copy of the exercise fixture and writes E11/E12 major fit (1 = fit) to the CSV.
# Needs the Microsoft Access ODBC driver. The .accdb is opened read-only unless -WriteTable is passed (then EventMajorFit is recreated inside it).
param(
    [string]$DbPath = (Join-Path $PSScriptRoot '..\tests\fixtures\exercise\SmartMatch_Student_Body_300.accdb'),
    [string]$CsvPath = (Join-Path $PSScriptRoot '..\test_data\event_major_fit.csv'),
    [switch]$WriteTable
)

$ErrorActionPreference = 'Stop'

$eventIds = @('E11', 'E12')

if (-not (Test-Path -LiteralPath $DbPath -PathType Leaf)) { throw "Access database not found: $DbPath" }
$DbPath = (Resolve-Path -LiteralPath $DbPath).Path

$readOnly = if ($WriteTable) { 0 } else { 1 }
$conn = New-Object System.Data.Odbc.OdbcConnection "Driver={Microsoft Access Driver (*.mdb, *.accdb)};Dbq=$DbPath;ReadOnly=$readOnly;"
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
$cmd.CommandText = "SELECT profile_id, first_name, last_name, major FROM Profiles ORDER BY profile_id"
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

# --- compute rows
$rows = New-Object System.Collections.Generic.List[object]
foreach ($p in $profiles) {
    $rows.Add([pscustomobject]@{
        profile_id    = $p.profile_id
        first_name    = $p.first_name
        last_name     = $p.last_name
        major         = $p.major
        E11_major_fit = [int](Test-MajorFit $p.major $targets['E11'])
        E12_major_fit = [int](Test-MajorFit $p.major $targets['E12'])
    })
}

# --- optional: recreate EventMajorFit inside the .accdb (modifies the file)
if ($WriteTable) {
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

    $ins = $conn.CreateCommand()
    $ins.CommandText = 'INSERT INTO EventMajorFit (profile_id, first_name, last_name, major, E11_major_fit, E12_major_fit) VALUES (?, ?, ?, ?, ?, ?)'
    1..6 | ForEach-Object { $ins.Parameters.Add((New-Object System.Data.Odbc.OdbcParameter)) | Out-Null }
    foreach ($row in $rows) {
        $ins.Parameters[0].Value = $row.profile_id
        $ins.Parameters[1].Value = $row.first_name
        $ins.Parameters[2].Value = $row.last_name
        $ins.Parameters[3].Value = $row.major
        $ins.Parameters[4].Value = $row.E11_major_fit
        $ins.Parameters[5].Value = $row.E12_major_fit
        $ins.ExecuteNonQuery() | Out-Null
    }
    Write-Output "Wrote $($rows.Count) rows to EventMajorFit in $DbPath"
}
$conn.Close()

$rows | Export-Csv -NoTypeInformation -Path $CsvPath -Encoding UTF8
Write-Output "Wrote $($rows.Count) rows to $CsvPath"
Write-Output "E11 matches: $(@($rows | Where-Object { $_.E11_major_fit -eq 1 }).Count)"
Write-Output "E12 matches: $(@($rows | Where-Object { $_.E12_major_fit -eq 1 }).Count)"

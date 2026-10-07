# Usage: powershell -File tools/compute_event_interest_fit.ps1 [-DbPath <file.accdb>] [-CsvPath <out.csv>] [-WriteTable]
# Reads Profiles/Events from the Access copy of the exercise fixture and writes E11/E12 interest fit (1 = fit) to the CSV.
# Needs the Microsoft Access ODBC driver. The .accdb is opened read-only unless -WriteTable is passed (then EventInterestFit is recreated inside it).
param(
    [string]$DbPath = (Join-Path $PSScriptRoot '..\tests\fixtures\exercise\SmartMatch_Student_Body_300.accdb'),
    [string]$CsvPath = (Join-Path $PSScriptRoot '..\test_data\event_interest_fit.csv'),
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

function Split-Terms([string]$cell) {
    # A ';'-separated cell as a case-folded set of whole terms.
    $terms = @{}
    foreach ($t in ($cell -split ';')) {
        $n = $t.Trim().ToLowerInvariant()
        if ($n) { $terms[$n] = $true }
    }
    return $terms
}

# --- event_topics for E11/E12
$topics = @{}
$cmd = $conn.CreateCommand()
$cmd.CommandText = "SELECT event_id, event_topics FROM Events WHERE event_id IN ('E11','E12')"
$r = $cmd.ExecuteReader()
while ($r.Read()) { $topics[$(Read-Text $r 0)] = $(Read-Text $r 1) }
$r.Close()
$topicSets = @{}
foreach ($e in $eventIds) {
    if (-not $topics.ContainsKey($e)) { $conn.Close(); throw "Event $e not found in Events" }
    $topicSets[$e] = Split-Terms $topics[$e]
    Write-Output "$e event_topics: $($topics[$e])"
}

# --- all profiles
$profiles = New-Object System.Collections.Generic.List[object]
$cmd = $conn.CreateCommand()
$cmd.CommandText = "SELECT profile_id, first_name, last_name, stated_interests FROM Profiles ORDER BY profile_id"
$r = $cmd.ExecuteReader()
while ($r.Read()) {
    $profiles.Add([pscustomobject]@{
        profile_id       = $(Read-Text $r 0)
        first_name       = $(Read-Text $r 1)
        last_name        = $(Read-Text $r 2)
        stated_interests = $(Read-Text $r 3)
    })
}
$r.Close()
Write-Output "Profiles read: $($profiles.Count)"

function Test-InterestFit([string]$interestsCell, $topicSet) {
    foreach ($i in (Split-Terms $interestsCell).Keys) {
        if ($topicSet.ContainsKey($i)) { return $true }
    }
    return $false
}

# --- compute rows
$rows = New-Object System.Collections.Generic.List[object]
foreach ($p in $profiles) {
    $rows.Add([pscustomobject]@{
        profile_id       = $p.profile_id
        first_name       = $p.first_name
        last_name        = $p.last_name
        stated_interests = $p.stated_interests
        E11_interest_fit = [int](Test-InterestFit $p.stated_interests $topicSets['E11'])
        E12_interest_fit = [int](Test-InterestFit $p.stated_interests $topicSets['E12'])
    })
}

# --- optional: recreate EventInterestFit inside the .accdb (modifies the file)
if ($WriteTable) {
    $exists = @($conn.GetSchema('Tables').Rows) | Where-Object { $_['TABLE_TYPE'] -eq 'TABLE' -and $_['TABLE_NAME'] -eq 'EventInterestFit' }
    if ($exists) {
        $cmd = $conn.CreateCommand()
        $cmd.CommandText = 'DROP TABLE EventInterestFit'
        $cmd.ExecuteNonQuery() | Out-Null
        Write-Output 'Dropped existing EventInterestFit'
    }
    $cmd = $conn.CreateCommand()
    try {
        $cmd.CommandText = 'CREATE TABLE EventInterestFit (profile_id TEXT(50) PRIMARY KEY, first_name TEXT(100), last_name TEXT(100), stated_interests LONGTEXT, E11_interest_fit INTEGER, E12_interest_fit INTEGER)'
        $cmd.ExecuteNonQuery() | Out-Null
    } catch {
        Write-Output "PRIMARY KEY rejected, creating plain table: $($_.Exception.Message)"
        $cmd.CommandText = 'CREATE TABLE EventInterestFit (profile_id TEXT(50), first_name TEXT(100), last_name TEXT(100), stated_interests LONGTEXT, E11_interest_fit INTEGER, E12_interest_fit INTEGER)'
        $cmd.ExecuteNonQuery() | Out-Null
    }

    $ins = $conn.CreateCommand()
    $ins.CommandText = 'INSERT INTO EventInterestFit (profile_id, first_name, last_name, stated_interests, E11_interest_fit, E12_interest_fit) VALUES (?, ?, ?, ?, ?, ?)'
    1..6 | ForEach-Object { $ins.Parameters.Add((New-Object System.Data.Odbc.OdbcParameter)) | Out-Null }
    foreach ($row in $rows) {
        $ins.Parameters[0].Value = $row.profile_id
        $ins.Parameters[1].Value = $row.first_name
        $ins.Parameters[2].Value = $row.last_name
        $ins.Parameters[3].Value = $row.stated_interests
        $ins.Parameters[4].Value = $row.E11_interest_fit
        $ins.Parameters[5].Value = $row.E12_interest_fit
        $ins.ExecuteNonQuery() | Out-Null
    }
    Write-Output "Wrote $($rows.Count) rows to EventInterestFit in $DbPath"
}
$conn.Close()

$rows | Export-Csv -NoTypeInformation -Path $CsvPath -Encoding UTF8
Write-Output "Wrote $($rows.Count) rows to $CsvPath"
Write-Output "E11 matches: $(@($rows | Where-Object { $_.E11_interest_fit -eq 1 }).Count)"
Write-Output "E12 matches: $(@($rows | Where-Object { $_.E12_interest_fit -eq 1 }).Count)"

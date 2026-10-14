param(
    [Parameter(Mandatory = $true)]
    [string]$DbHost,

    [Parameter(Mandatory = $true)]
    [string]$DbUser,

    [int]$Port = 5432,

    [string]$Database = "postgres"
)

$pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
if (-not $pgDump) {
    throw "No se encontró pg_dump. Instala PostgreSQL Command Line Tools y vuelve a intentarlo."
}

$backupDirectory = Join-Path $env:USERPROFILE "Documents\VideoG_TO-backups"
New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
$timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$backupFile = Join-Path $backupDirectory "supabase_$timestamp.dump"
$securePassword = Read-Host "Contraseña de la base Supabase" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)

try {
    $env:PGPASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $env:PGSSLMODE = "require"
    & $pgDump.Source `
        --host=$DbHost `
        --port=$Port `
        --username=$DbUser `
        --dbname=$Database `
        --format=custom `
        --no-owner `
        --no-acl `
        --no-password `
        --file=$backupFile

    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $backupFile -ErrorAction SilentlyContinue
        throw "pg_dump terminó con código $LASTEXITCODE; no se conservó un respaldo incompleto."
    }

    Write-Output "Respaldo creado: $backupFile"
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    $securePassword.Dispose()
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:PGSSLMODE -ErrorAction SilentlyContinue
}

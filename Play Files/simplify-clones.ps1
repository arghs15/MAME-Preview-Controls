# PowerShell Clone Simplifier
# This script simplifies clone entries in a game data JSON file by keeping only the description field
param(
    [Parameter(Mandatory=$true)]
    [string]$FilePath,
    [switch]$DryRun
)

# Display usage if no file provided
if (-not $FilePath) {
    Write-Host "Usage: .\simplify-clones.ps1 -FilePath path\to\gamedata.json [-DryRun]"
    exit
}

Write-Host "Starting to process $FilePath..." -ForegroundColor Cyan

# Try to read the JSON file
try {
    Write-Host "Reading JSON file..." -ForegroundColor Cyan
    $jsonContent = Get-Content -Path $FilePath -Raw
    $gameData = $jsonContent | ConvertFrom-Json -Depth 100
    Write-Host "Successfully read JSON file" -ForegroundColor Green
}
catch {
    Write-Host "Error reading JSON file: $_" -ForegroundColor Red
    exit
}

# Create backup if not in dry run mode
if (-not $DryRun) {
    $backupPath = "$FilePath.bak"
    Write-Host "Creating backup at $backupPath" -ForegroundColor Cyan
    Copy-Item -Path $FilePath -Destination $backupPath
    Write-Host "Backup created" -ForegroundColor Green
}
else {
    Write-Host "DRY RUN MODE: No changes will be written to disk" -ForegroundColor Yellow
}

# Counters
$totalGames = 0
$gamesModified = 0
$totalClonesSimplified = 0

# Get all game properties
$gameProperties = $gameData | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
$totalGames = $gameProperties.Count
Write-Host "Found $totalGames games in the JSON file" -ForegroundColor Cyan

# Process each game
$currentGame = 0
foreach ($gameName in $gameProperties) {
    $currentGame++
    
    # Show progress periodically
    if ($currentGame % 100 -eq 0 -or $currentGame -eq $totalGames) {
        $percentComplete = [math]::Floor(($currentGame / $totalGames) * 100)
        Write-Host "Progress: $percentComplete% ($currentGame/$totalGames games)" -ForegroundColor Cyan
    }
    
    $game = $gameData.$gameName
    $gameModified = $false
    
    # Skip if not a valid game entry
    if (-not $game -or -not $game.description) {
        continue
    }
    
    # Skip if no clones section
    if (-not $game.clones) {
        continue
    }
    
    # Process each clone
    $cloneNames = $game.clones | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
    
    foreach ($cloneName in $cloneNames) {
        $clone = $game.clones.$cloneName
        
        # Skip if not a valid clone
        if (-not $clone -or -not $clone.description) {
            continue
        }
        
        # Check if this clone has extra properties that need to be removed
        $cloneProps = $clone | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
        
        if ($cloneProps.Count -gt 1) {
            # Create a simplified clone with only description
            $simplifiedClone = New-Object PSObject
            $simplifiedClone | Add-Member -MemberType NoteProperty -Name "description" -Value $clone.description
            
            # Replace the original clone with our simplified version
            $game.clones.$cloneName = $simplifiedClone
            
            $totalClonesSimplified++
            $gameModified = $true
            
            # Show detailed log if not too many clones
            if ($totalClonesSimplified -lt 1000) {
                Write-Host "  Simplified clone: $gameName - $cloneName" -ForegroundColor Green
            }
        }
    }
    
    if ($gameModified) {
        $gamesModified++
    }
}

# Write changes if not in dry run mode
if (-not $DryRun -and $gamesModified -gt 0) {
    Write-Host "Writing changes back to $FilePath..." -ForegroundColor Cyan
    
    try {
        $gameData | ConvertTo-Json -Depth 100 | Set-Content -Path $FilePath
        Write-Host "Successfully wrote changes" -ForegroundColor Green
    }
    catch {
        Write-Host "Error writing file: $_" -ForegroundColor Red
    }
}

# Print summary
Write-Host "`nSUMMARY:" -ForegroundColor Cyan
Write-Host "- Total games processed: $totalGames" -ForegroundColor White
Write-Host "- Games with clones modified: $gamesModified" -ForegroundColor White
Write-Host "- Total clone entries simplified: $totalClonesSimplified" -ForegroundColor White

if ($DryRun) {
    Write-Host "`nThis was a dry run - no changes were written to disk." -ForegroundColor Yellow
}
else {
    Write-Host "`nChanges have been applied and saved." -ForegroundColor Green
}
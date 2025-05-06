# JSON Property Order Fixer
# This script rearranges properties in a game data JSON file to maintain a consistent order
param(
    [string]$FilePath,
    [switch]$DryRun
)

# Display usage if no file provided
if (-not $FilePath) {
    Write-Host "Usage: .\fix-property-order.ps1 -FilePath path\to\gamedata.json [-DryRun]"
    exit
}

Write-Host "Starting to process $FilePath..." -ForegroundColor Cyan

# Try to read the JSON file
try {
    Write-Host "Reading JSON file..." -ForegroundColor Cyan
    $jsonContent = Get-Content -Path $FilePath -Raw
    
    # Check PowerShell version and use appropriate method
    $psVersion = $PSVersionTable.PSVersion.Major
    
    if ($psVersion -ge 5) {
        # PowerShell 5.0 or later supports -Depth parameter
        $gameData = $jsonContent | ConvertFrom-Json -Depth 100
    } else {
        # For older PowerShell versions
        $gameData = $jsonContent | ConvertFrom-Json
    }
    
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

# Define the property order we want to maintain
$propertyOrder = @(
    "description",
    "playercount", 
    "buttons", 
    "sticks",
    "alternating",
    "mappings", 
    "clones",
    "controls"
)

# Counters
$totalGames = 0
$gamesReordered = 0

# Get all game properties
$gameProperties = $gameData | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
$totalGames = $gameProperties.Count
Write-Host "Found $totalGames games in the JSON file" -ForegroundColor Cyan

# Process each game
foreach ($gameName in $gameProperties) {
    Write-Host "Processing game: $gameName" -ForegroundColor Cyan
    $game = $gameData.$gameName
    $gameModified = $false
    
    # Make sure it's a valid game entry
    if (-not $game -or -not $game.description) {
        Write-Host "  Skipping $gameName - not a valid game entry" -ForegroundColor Yellow
        continue
    }
    
    # Check if properties are already in the correct order
    $currentProps = $game | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
    $needsReordering = $false
    
    $lastFoundIndex = -1
    foreach ($prop in $currentProps) {
        if ($propertyOrder -contains $prop) {
            $currentIndex = [array]::IndexOf($propertyOrder, $prop)
            if ($currentIndex -lt $lastFoundIndex) {
                $needsReordering = $true
                break
            }
            $lastFoundIndex = $currentIndex
        }
    }
    
    # If order is incorrect, reorder properties
    if ($needsReordering) {
        Write-Host "  Reordering properties for $gameName..." -ForegroundColor Green
        
        # Reorder properties according to our specified order
        # Create a new game object with the correct order
        $reorderedGame = New-Object PSObject
        
        # First add properties in our preferred order if they exist
        foreach ($prop in $propertyOrder) {
            if ($game.PSObject.Properties.Name -contains $prop) {
                $reorderedGame | Add-Member -MemberType NoteProperty -Name $prop -Value $game.$prop
            }
        }
        
        # Then add any remaining properties that weren't in our preferred order
        foreach ($prop in $currentProps) {
            if (-not $reorderedGame.PSObject.Properties.Name -contains $prop) {
                $reorderedGame | Add-Member -MemberType NoteProperty -Name $prop -Value $game.$prop
            }
        }
        
        # Replace the original game with our reordered version
        $gameData.$gameName = $reorderedGame
        $gamesReordered++
    }
    else {
        Write-Host "  Properties already in correct order for $gameName" -ForegroundColor Cyan
    }
}

# Write changes if not in dry run mode
if (-not $DryRun -and $gamesReordered -gt 0) {
    Write-Host "Writing changes back to $FilePath..." -ForegroundColor Cyan
    
    try {
        # Check PowerShell version and use appropriate method
        $psVersion = $PSVersionTable.PSVersion.Major
        
        if ($psVersion -ge 5) {
            # PowerShell 5.0 or later supports -Depth parameter
            $gameData | ConvertTo-Json -Depth 100 | Set-Content -Path $FilePath
        } else {
            # For older PowerShell versions with limited depth
            # Note: This might cause issues with very deep JSON structures
            $gameData | ConvertTo-Json | Set-Content -Path $FilePath
        }
        
        Write-Host "Successfully wrote changes" -ForegroundColor Green
    }
    catch {
        Write-Host "Error writing file: $_" -ForegroundColor Red
    }
}

# Print summary
Write-Host "`nSUMMARY:" -ForegroundColor Cyan
Write-Host "- Total games processed: $totalGames" -ForegroundColor White
Write-Host "- Games with properties reordered: $gamesReordered" -ForegroundColor White

if ($DryRun) {
    Write-Host "`nThis was a dry run - no changes were written to disk." -ForegroundColor Yellow
}
else {
    Write-Host "`nChanges have been applied and saved." -ForegroundColor Green
}
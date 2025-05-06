# Simple PowerShell JSON Structure Fixer
param(
    [string]$FilePath,
    [switch]$DryRun
)

# Display usage if no file provided
if (-not $FilePath) {
    Write-Host "Usage: .\simple-fix.ps1 -FilePath path\to\gamedata.json [-DryRun]"
    exit
}

Write-Host "Starting to process $FilePath..." -ForegroundColor Cyan

# Try to read the JSON file
try {
    Write-Host "Reading JSON file..." -ForegroundColor Cyan
    $jsonContent = Get-Content -Path $FilePath -Raw
    $gameData = $jsonContent | ConvertFrom-Json
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
$totalClonesMoved = 0
$gamesModified = 0
$duplicateClones = @()

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
    
    # Make sure clones property exists
    if (-not $game.clones) {
        $game | Add-Member -MemberType NoteProperty -Name "clones" -Value (New-Object PSObject)
        Write-Host "  Added missing clones property" -ForegroundColor Green
        $gameModified = $true
    }
    
    # Standard properties that aren't clones
    $standardProps = @("description", "playercount", "buttons", "sticks", "clones", "mappings", "controls")
    
    # Find misplaced clones at top level
    $topLevelProps = $game | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
    foreach ($propName in $topLevelProps) {
        # Skip standard properties
        if ($standardProps -contains $propName) {
            continue
        }
        
        $prop = $game.$propName
        
        # Check if it looks like a clone
        if ($prop -and $prop.PSObject.Properties.Name -contains "description") {
            Write-Host "  Found misplaced clone: $propName" -ForegroundColor Green
            
            # Check if this clone already exists in the clones section
            if ($game.clones.PSObject.Properties.Name -contains $propName) {
                Write-Host "    Warning: Clone '$propName' already exists in clones section" -ForegroundColor Yellow
                $duplicateClones += "$gameName - $propName"
                
                # Add with -Force to overwrite the existing one
                $game.clones | Add-Member -MemberType NoteProperty -Name $propName -Value $prop -Force
                Write-Host "    Overwritten with the top-level version" -ForegroundColor Yellow
            } else {
                # Add to clones section normally
                $game.clones | Add-Member -MemberType NoteProperty -Name $propName -Value $prop
                Write-Host "    Added to clones section" -ForegroundColor Green
            }
            
            # Remove from top level
            $game.PSObject.Properties.Remove($propName)
            
            $totalClonesMoved++
            $gameModified = $true
        }
    }
    
    # Check for nested clones inside other clones
    if ($game.clones) {
        $cloneNames = $game.clones | Get-Member -MemberType NoteProperty | Select-Object -ExpandProperty Name
        
        foreach ($cloneName in $cloneNames) {
            $clone = $game.clones.$cloneName
            
            # Get properties of this clone
            $cloneProps = $clone | Get-Member -MemberType NoteProperty | Where-Object { $_.MemberType -eq "NoteProperty" } | Select-Object -ExpandProperty Name
            
            foreach ($nestedPropName in $cloneProps) {
                # Skip standard properties
                if ($standardProps -contains $nestedPropName) {
                    continue
                }
                
                $nestedProp = $clone.$nestedPropName
                
                # Check if it looks like a nested clone
                if ($nestedProp -and $nestedProp.PSObject.Properties.Name -contains "description") {
                    Write-Host "  Found nested clone: $nestedPropName in $cloneName" -ForegroundColor Green
                    
                    # Check if this clone already exists in the main clones section
                    if ($game.clones.PSObject.Properties.Name -contains $nestedPropName) {
                        Write-Host "    Warning: Clone '$nestedPropName' already exists in main clones section" -ForegroundColor Yellow
                        $duplicateClones += "$gameName - $nestedPropName (from $cloneName)"
                        
                        # Add with -Force to overwrite the existing one
                        $game.clones | Add-Member -MemberType NoteProperty -Name $nestedPropName -Value $nestedProp -Force
                        Write-Host "    Overwritten with the nested version from $cloneName" -ForegroundColor Yellow
                    } else {
                        # Add to main clones section normally
                        $game.clones | Add-Member -MemberType NoteProperty -Name $nestedPropName -Value $nestedProp
                        Write-Host "    Added to main clones section" -ForegroundColor Green
                    }
                    
                    # Remove from nested location
                    $clone.PSObject.Properties.Remove($nestedPropName)
                    
                    $totalClonesMoved++
                    $gameModified = $true
                }
            }
        }
    }
    
    if ($gameModified) {
        $gamesModified++
        Write-Host "  Modified structure for $gameName" -ForegroundColor Green
    }
    else {
        Write-Host "  No changes needed for $gameName" -ForegroundColor Cyan
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
Write-Host "- Games modified: $gamesModified" -ForegroundColor White
Write-Host "- Total clones moved: $totalClonesMoved" -ForegroundColor White

# Handle duplicates report
if ($duplicateClones.Count -gt 0) {
    Write-Host "`nWARNING: Found and resolved duplicate clones:" -ForegroundColor Yellow
    foreach ($dup in $duplicateClones) {
        Write-Host "- $dup" -ForegroundColor Yellow
    }
}

if ($DryRun) {
    Write-Host "`nThis was a dry run - no changes were written to disk." -ForegroundColor Yellow
}
else {
    Write-Host "`nChanges have been applied and saved." -ForegroundColor Green
}
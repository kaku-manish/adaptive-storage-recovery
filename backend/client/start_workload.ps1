param(
    [string]$Profile = "LOW",
    [int]$DurationSeconds = 60
)

$Profile = $Profile.ToUpper()

if ($Profile -eq "HIGH") {
    $Users = 100
    $SpawnRate = 10
} elseif ($Profile -eq "MEDIUM") {
    $Users = 50
    $SpawnRate = 5
} else {
    $Users = 10
    $SpawnRate = 2
}

Write-Host "Starting $Profile workload simulation for $DurationSeconds seconds ($Users users)..."

$env:WORKLOAD_PROFILE = $Profile

locust -f client/locustfile.py --headless -u $Users -r $SpawnRate -t "$($DurationSeconds)s" --host http://localhost:8000 --html "client/report_$Profile.html"

Write-Host "Simulation complete. Report saved to client/report_$Profile.html"

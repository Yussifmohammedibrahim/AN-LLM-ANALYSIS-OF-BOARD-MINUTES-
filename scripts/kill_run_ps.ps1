$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -match 'run.py' }
if ($procs) {
  foreach ($p in $procs) {
    Write-Output ("Killing PID " + $p.ProcessId + " : " + $p.CommandLine)
    try {
      Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
    } catch {
      Write-Output ("Failed to kill PID " + $p.ProcessId + ": " + $_.Exception.Message)
    }
  }
} else {
  Write-Output "No run.py process found."
}

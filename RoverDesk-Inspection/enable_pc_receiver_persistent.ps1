$ErrorActionPreference = 'Stop'
$base = $PSScriptRoot
$report = Join-Path $base 'pc-receiver-result.json'
$added = $false
$coexist = $false
try {
  $nic = Get-NetAdapter -InterfaceIndex 10
  if ($nic.Status -ne 'Up') { throw 'Robot Ethernet adapter is not connected.' }
  $primary = Get-NetIPAddress -InterfaceIndex 10 -IPAddress '192.168.1.100' -ErrorAction Stop
  if (Get-NetIPAddress -IPAddress '192.168.1.103' -ErrorAction SilentlyContinue) { throw 'Receiver address already exists; stopped without changing it.' }
  $neighbor = Get-NetNeighbor -InterfaceIndex 10 -IPAddress '192.168.1.103' -ErrorAction SilentlyContinue
  if ($neighbor -and $neighbor.LinkLayerAddress -notin @('','00-00-00-00-00-00') -and "$($neighbor.State)" -notin @('Unreachable','Incomplete')) { throw 'Another device may own .103; stopped.' }
  & netsh.exe interface ipv4 set interface interface=10 dhcpstaticipcoexistence=enabled store=persistent | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Could not persist coexistence setting.' }
  & netsh.exe interface ipv4 set interface interface=10 dhcpstaticipcoexistence=enabled store=active | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Could not enable DHCP/static coexistence.' }
  $coexist = $true
  & netsh.exe interface ipv4 add address name=10 address=192.168.1.103 mask=255.255.255.0 store=persistent skipassource=true | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'Could not add temporary receiver address.' }
  $added = $true
  Start-Sleep -Seconds 4
  $address = Get-NetIPAddress -InterfaceIndex 10 -IPAddress '192.168.1.103'
  if ("$($address.AddressState)" -ne 'Preferred') { throw "Address is not ready: $($address.AddressState)" }
  $dhcp = Get-NetIPInterface -InterfaceIndex 10 -AddressFamily IPv4
  if ("$($dhcp.Dhcp)" -ne 'Enabled') { throw 'DHCP was unexpectedly disabled.' }
  Get-NetIPAddress -InterfaceIndex 10 -IPAddress '192.168.1.100' -ErrorAction Stop | Out-Null
  @{success=$true;interface=10;receiver='192.168.1.103';original='192.168.1.100';dhcp="$($dhcp.Dhcp)";temporary=$false;robot_modified=$false} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
} catch {
  $reason = $_.Exception.Message
  if ($added) { & netsh.exe interface ipv4 delete address name=10 address=192.168.1.103 store=persistent | Out-Null }
  if ($coexist) { & netsh.exe interface ipv4 set interface interface=10 dhcpstaticipcoexistence=disabled store=persistent | Out-Null; & netsh.exe interface ipv4 set interface interface=10 dhcpstaticipcoexistence=disabled store=active | Out-Null }
  if ($primary -and "$($primary.PrefixOrigin)" -eq 'Dhcp') { Set-NetIPInterface -InterfaceIndex 10 -AddressFamily IPv4 -Dhcp Enabled -ErrorAction SilentlyContinue }
  @{success=$false;error=$reason;robot_modified=$false} | ConvertTo-Json | Set-Content -LiteralPath $report -Encoding UTF8
  exit 1
}

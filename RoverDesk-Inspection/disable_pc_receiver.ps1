$ErrorActionPreference='Stop'
# Remove only Rover Desk's PC receiver address; preserve original DHCP address.
$p=Get-NetIPAddress -InterfaceIndex 10 -IPAddress '192.168.1.103' -PolicyStore PersistentStore -ErrorAction SilentlyContinue
if ($p) {
  & netsh.exe interface ipv4 delete address name=10 address=192.168.1.103 store=persistent
  if ($LASTEXITCODE -ne 0) { throw 'Could not remove persistent receiver address.' }
}
$a=Get-NetIPAddress -InterfaceIndex 10 -IPAddress '192.168.1.103' -ErrorAction SilentlyContinue
if ($a) {
  & netsh.exe interface ipv4 delete address name=10 address=192.168.1.103 store=active
  if ($LASTEXITCODE -ne 0) { throw 'Could not remove active receiver address.' }
}
& netsh.exe interface ipv4 set interface interface=10 dhcpstaticipcoexistence=disabled store=persistent
& netsh.exe interface ipv4 set interface interface=10 dhcpstaticipcoexistence=disabled store=active
Get-NetFirewallRule -Name 'RoverDesk-Lite3-Telemetry-103' -ErrorAction SilentlyContinue | Remove-NetFirewallRule

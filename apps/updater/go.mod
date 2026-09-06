module hqagent.local/updater

go 1.26

require (
	hqagent.local/update-agent v0.1.0
	hqagent.local/protocol v0.2.0
	hqupdatekit.local/updatekit v0.1.0
)

replace hqagent.local/update-agent => ../update-agent
replace hqagent.local/protocol => ../../packages/protocol/generated/go
replace hqupdatekit.local/updatekit => ../../packages/updatekit

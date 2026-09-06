module hqagent.local/update-agent

go 1.26

require (
	hqagent.local/protocol v0.2.0
	hqupdatekit.local/updatekit v0.1.0
)

replace hqagent.local/protocol => ../../packages/protocol/generated/go
replace hqupdatekit.local/updatekit => ../../packages/updatekit

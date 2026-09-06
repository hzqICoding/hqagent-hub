package product

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"path/filepath"
	"strconv"
	"time"

	"hqagent.local/protocol"
	kit "hqupdatekit.local/updatekit"
)

type HealthProbe struct{ Policy kit.PlanPolicy }

func (h HealthProbe) Check(ctx context.Context, plan kit.UpdatePlan, processes map[string]kit.RunningProcess) error {
	client := &http.Client{Transport: &http.Transport{Proxy: nil}, Timeout: time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
	defer client.CloseIdleConnections()
	tick := time.NewTicker(100 * time.Millisecond)
	defer tick.Stop()
	for {
		for _, p := range processes {
			if !p.Alive() {
				return fmt.Errorf("restarted component exited")
			}
		}
		core := processes["core"]
		if core == nil {
			return fmt.Errorf("core process missing")
		}
		var d protocol.HubRuntimeDescriptor
		if err := kit.ReadJSON(filepath.Join(h.Policy.DataDirectory, "runtime", "hub.json"), &d); err == nil && d.Pid == int64(core.PID()) && d.SchemaVersion == 1 && d.Port >= 1024 && d.Port <= 65535 && d.AppVersion == plan.TargetVersion && d.BaseUrl == "http://127.0.0.1:"+strconv.FormatInt(d.Port, 10) {
			// The new Hub chooses a new port. Only its unauthenticated healthz is
			// requested; no token is sent, retained, logged or copied into a Plan.
			r, err := http.NewRequestWithContext(ctx, "GET", d.BaseUrl+"/healthz", nil)
			if err == nil {
				response, e := client.Do(r)
				if e == nil {
					var health protocol.HealthView
					decode := json.NewDecoder(io.LimitReader(response.Body, 64<<10)).Decode(&health)
					response.Body.Close()
					if response.StatusCode == 200 && decode == nil && health.Status == "ok" && health.Pid == int64(core.PID()) && health.AppVersion == plan.TargetVersion && health.ProtocolVersion == h.Policy.ProtocolVersion {
						return nil
					}
				}
			}
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("new version health check timed out")
		case <-tick.C:
		}
	}
}

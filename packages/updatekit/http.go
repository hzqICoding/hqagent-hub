package updatekit

import (
	"fmt"
	"net/http"
	"net/url"
	"time"
)

func ValidateURL(raw string) error {
	u, err := url.Parse(raw)
	if err != nil || u.User != nil || u.Host == "" || u.Fragment != "" {
		return fmt.Errorf("invalid update URL")
	}
	if u.Scheme == "https" || (u.Scheme == "http" && u.Hostname() == "127.0.0.1") {
		return nil
	}
	return fmt.Errorf("HTTPS required outside loopback")
}

func secureHTTPClient(timeout time.Duration) *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	transport.ResponseHeaderTimeout = 20 * time.Second
	return &http.Client{Transport: transport, Timeout: timeout, CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 {
			return fmt.Errorf("too many redirects")
		}
		if err := ValidateURL(req.URL.String()); err != nil {
			return err
		}
		if via[0].URL.Scheme == "https" && req.URL.Scheme != "https" {
			return fmt.Errorf("redirect downgrade rejected")
		}
		return nil
	}}
}

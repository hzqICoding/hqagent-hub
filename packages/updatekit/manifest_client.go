package updatekit

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type ManifestClient interface {
	Check(context.Context, CheckRequest) (CheckResponse, error)
	Releases(context.Context, CheckRequest) ([]Release, error)
}

type HTTPManifestClient struct {
	baseURL string
	client  *http.Client
}

func NewHTTPManifestClient(baseURL string) (*HTTPManifestClient, error) {
	baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
	parsed, err := url.Parse(baseURL)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("invalid manifest base URL")
	}
	if parsed.Scheme != "https" && parsed.Hostname() != "127.0.0.1" && parsed.Hostname() != "localhost" {
		return nil, fmt.Errorf("manifest base URL must use HTTPS")
	}
	if err := ValidateURL(baseURL); err != nil {
		return nil, err
	}
	return &HTTPManifestClient{baseURL: baseURL, client: secureHTTPClient(20 * time.Second)}, nil
}

func (c *HTTPManifestClient) Check(ctx context.Context, request CheckRequest) (CheckResponse, error) {
	var response CheckResponse
	err := c.get(ctx, "/updates/check", request, &response)
	return response, err
}

func (c *HTTPManifestClient) Releases(ctx context.Context, request CheckRequest) ([]Release, error) {
	var response struct {
		Items []Release `json:"items"`
	}
	if err := c.get(ctx, "/updates/releases", request, &response); err != nil {
		return nil, err
	}
	return response.Items, nil
}

func (c *HTTPManifestClient) get(ctx context.Context, endpoint string, request CheckRequest, target any) error {
	base := c.baseURL
	if !strings.HasSuffix(base, "/api/v1") {
		base += "/api/v1"
	}
	parsed, err := url.Parse(base + endpoint)
	if err != nil {
		return err
	}
	query := parsed.Query()
	query.Set("appId", request.AppID)
	query.Set("targetKey", request.TargetKey)
	query.Set("currentVersion", request.CurrentVersion)
	query.Set("channel", request.Channel)
	query.Set("os", request.OS)
	query.Set("arch", request.Arch)
	query.Set("installType", request.InstallType)
	parsed.RawQuery = query.Encode()
	httpRequest, err := http.NewRequestWithContext(ctx, http.MethodGet, parsed.String(), nil)
	if err != nil {
		return err
	}
	httpRequest.Header.Set("Accept", "application/json")
	response, err := c.client.Do(httpRequest)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return fmt.Errorf("manifest server returned %d", response.StatusCode)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 2<<20))
	return decoder.Decode(target)
}

type FakeManifestClient struct {
	CheckResult           CheckResponse
	CheckError            error
	ReleaseItems          []Release
	ReleaseItemsByChannel map[string][]Release
	ReleasesError         error
}

func (f *FakeManifestClient) Check(context.Context, CheckRequest) (CheckResponse, error) {
	return f.CheckResult, f.CheckError
}

func (f *FakeManifestClient) Releases(_ context.Context, request CheckRequest) ([]Release, error) {
	if items, ok := f.ReleaseItemsByChannel[request.Channel]; ok {
		return append([]Release(nil), items...), f.ReleasesError
	}
	return append([]Release(nil), f.ReleaseItems...), f.ReleasesError
}

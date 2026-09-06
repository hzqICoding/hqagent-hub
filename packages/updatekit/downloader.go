package updatekit

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

type Downloader interface {
	Download(context.Context, Package, string, func(DownloadProgress)) error
}

type HTTPDownloader struct{ client *http.Client }

func NewHTTPDownloader() *HTTPDownloader { return &HTTPDownloader{client: secureHTTPClient(0)} }

func (d *HTTPDownloader) Download(ctx context.Context, pkg Package, target string, report func(DownloadProgress)) error {
	if err := ValidateURL(pkg.URL); err != nil {
		return err
	}
	if pkg.Size <= 0 {
		return fmt.Errorf("package size is required")
	}
	if err := RejectLinks(target); err != nil {
		return err
	}
	if err := RejectLinks(target + ".part"); err != nil {
		return err
	}
	partial := target + ".part"
	var existing int64
	if info, err := os.Stat(partial); err == nil {
		existing = info.Size()
	}
	if existing > pkg.Size {
		return fmt.Errorf("partial package exceeds manifest size")
	}
	if existing == pkg.Size {
		return replaceFile(partial, target)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, pkg.URL, nil)
	if err != nil {
		return err
	}
	if existing > 0 {
		request.Header.Set("Range", fmt.Sprintf("bytes=%d-", existing))
	}
	response, err := d.client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	appendMode := existing > 0 && response.StatusCode == http.StatusPartialContent
	if response.StatusCode == http.StatusPartialContent {
		var start, end, total int64
		if _, err := fmt.Sscanf(response.Header.Get("Content-Range"), "bytes %d-%d/%d", &start, &end, &total); err != nil || start != existing || end != pkg.Size-1 || total != pkg.Size {
			return fmt.Errorf("invalid Content-Range")
		}
	}
	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusPartialContent {
		return fmt.Errorf("package server returned %d", response.StatusCode)
	}
	flags := os.O_CREATE | os.O_WRONLY
	if appendMode {
		flags |= os.O_APPEND
	} else {
		flags |= os.O_TRUNC
		existing = 0
	}
	file, err := os.OpenFile(partial, flags, 0o600)
	if err != nil {
		return err
	}
	defer file.Close()
	total := pkg.Size
	buffer := make([]byte, 256<<10)
	downloaded := existing
	started := time.Now()
	lastReport := time.Time{}
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		count, readErr := response.Body.Read(buffer)
		if count > 0 {
			if downloaded+int64(count) > total {
				return fmt.Errorf("package exceeds manifest size")
			}
			if _, err := file.Write(buffer[:count]); err != nil {
				return err
			}
			downloaded += int64(count)
			if time.Since(lastReport) >= 200*time.Millisecond || (total > 0 && downloaded == total) {
				elapsed := max(time.Since(started).Seconds(), 0.001)
				speed := int64(float64(downloaded-existing) / elapsed)
				progress := DownloadProgress{DownloadedBytes: downloaded, TotalBytes: total, BytesPerSecond: speed}
				if total > 0 {
					progress.Percent = min(100, float64(downloaded)*100/float64(total))
					if speed > 0 {
						progress.RemainingSeconds = max(0, (total-downloaded)/speed)
					}
				}
				if report != nil {
					report(progress)
				}
				lastReport = time.Now()
			}
		}
		if readErr == io.EOF {
			break
		}
		if readErr != nil {
			return readErr
		}
	}
	if downloaded != total {
		return fmt.Errorf("incomplete package")
	}
	if err := file.Sync(); err != nil {
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	if err := replaceFile(partial, target); err != nil {
		return err
	}
	return nil
}

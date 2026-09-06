package updatekit

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

type Version struct {
	Major, Minor, Patch int
	PreRelease          string
}

var semverSyntax = regexp.MustCompile(`^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$`)

func ParseVersion(value string) (Version, error) {
	value = strings.TrimPrefix(strings.TrimSpace(value), "v")
	if !semverSyntax.MatchString(value) {
		return Version{}, fmt.Errorf("invalid SemVer")
	}
	value = strings.SplitN(value, "+", 2)[0]
	parts := strings.SplitN(value, "-", 2)
	numbers := strings.Split(parts[0], ".")
	if len(numbers) != 3 {
		return Version{}, fmt.Errorf("invalid SemVer %q", value)
	}
	result := Version{}
	parsed := []*int{&result.Major, &result.Minor, &result.Patch}
	for index, number := range numbers {
		numericValue, err := strconv.Atoi(number)
		if err != nil || numericValue < 0 {
			return Version{}, fmt.Errorf("invalid SemVer component %q", number)
		}
		*parsed[index] = numericValue
	}
	if len(parts) == 2 {
		result.PreRelease = parts[1]
		if result.PreRelease == "" {
			return Version{}, fmt.Errorf("invalid SemVer prerelease")
		}
		for _, part := range strings.Split(result.PreRelease, ".") {
			numeric := true
			for _, r := range part {
				if r < '0' || r > '9' {
					numeric = false
					break
				}
			}
			if numeric && len(part) > 1 && part[0] == '0' {
				return Version{}, fmt.Errorf("numeric prerelease has leading zero")
			}
		}
	}
	return result, nil
}

func CompareVersions(left, right string) int {
	a, errA := ParseVersion(left)
	b, errB := ParseVersion(right)
	if errA != nil || errB != nil {
		return strings.Compare(left, right)
	}
	for _, pair := range [][2]int{{a.Major, b.Major}, {a.Minor, b.Minor}, {a.Patch, b.Patch}} {
		if pair[0] < pair[1] {
			return -1
		}
		if pair[0] > pair[1] {
			return 1
		}
	}
	if a.PreRelease == b.PreRelease {
		return 0
	}
	if a.PreRelease == "" {
		return 1
	}
	if b.PreRelease == "" {
		return -1
	}
	return comparePrerelease(a.PreRelease, b.PreRelease)
}

func comparePrerelease(a, b string) int {
	left, right := strings.Split(a, "."), strings.Split(b, ".")
	for index := 0; index < min(len(left), len(right)); index++ {
		li, le := strconv.Atoi(left[index])
		ri, re := strconv.Atoi(right[index])
		if le == nil && re == nil {
			if li < ri {
				return -1
			}
			if li > ri {
				return 1
			}
			continue
		}
		if le == nil {
			return -1
		}
		if re == nil {
			return 1
		}
		if left[index] < right[index] {
			return -1
		}
		if left[index] > right[index] {
			return 1
		}
	}
	if len(left) < len(right) {
		return -1
	}
	if len(left) > len(right) {
		return 1
	}
	return 0
}

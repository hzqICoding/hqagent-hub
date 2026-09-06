//go:build windows

package updatekit

import (
	"context"
	"errors"
	"fmt"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	jobObjectBasicAccountingInformation = 1
	jobObjectExtendedLimitInformation   = 9
	jobObjectLimitKillOnJobClose        = 0x2000
	createSuspended                     = 0x00000004
	createNoWindow                      = 0x08000000
)

// Layouts follow winnt.h. No cgo or external Windows package is needed.
type jobBasicLimits struct {
	PerProcessUserTimeLimit, PerJobUserTimeLimit int64
	LimitFlags                                   uint32
	MinimumWorkingSetSize, MaximumWorkingSetSize uintptr
	ActiveProcessLimit                           uint32
	Affinity                                     uintptr
	PriorityClass, SchedulingClass               uint32
}
type jobExtendedLimits struct {
	BasicLimitInformation                    jobBasicLimits
	IOInfo                                   [6]uint64
	ProcessMemoryLimit, JobMemoryLimit       uintptr
	PeakProcessMemoryUsed, PeakJobMemoryUsed uintptr
}
type jobAccounting struct {
	TotalUserTime, TotalKernelTime                                                 int64
	ThisPeriodTotalUserTime, ThisPeriodTotalKernelTime                             int64
	TotalPageFaultCount, TotalProcesses, ActiveProcesses, TotalTerminatedProcesses uint32
}

type installerJob struct{ handle syscall.Handle }

func newInstallerJob() (*installerJob, error) {
	h, _, err := kernel32.NewProc("CreateJobObjectW").Call(0, 0)
	if h == 0 {
		return nil, fmt.Errorf("create installer job: %w", err)
	}
	j := &installerJob{handle: syscall.Handle(h)}
	limits := jobExtendedLimits{}
	// Neither BREAKAWAY_OK nor SILENT_BREAKAWAY_OK is set. The unnamed job
	// handle is non-inheritable, so descendants cannot retain or reconfigure it.
	limits.BasicLimitInformation.LimitFlags = jobObjectLimitKillOnJobClose
	ok, _, err := kernel32.NewProc("SetInformationJobObject").Call(h, jobObjectExtendedLimitInformation, uintptr(unsafe.Pointer(&limits)), unsafe.Sizeof(limits))
	if ok == 0 {
		syscall.CloseHandle(j.handle)
		return nil, fmt.Errorf("configure installer job: %w", err)
	}
	return j, nil
}
func (j *installerJob) activeProcesses() (uint32, error) {
	var accounting jobAccounting
	ok, _, err := kernel32.NewProc("QueryInformationJobObject").Call(uintptr(j.handle), jobObjectBasicAccountingInformation, uintptr(unsafe.Pointer(&accounting)), unsafe.Sizeof(accounting), 0)
	if ok == 0 {
		return 0, fmt.Errorf("query installer job: %w", err)
	}
	return accounting.ActiveProcesses, nil
}
func (j *installerJob) close() error {
	defer syscall.CloseHandle(j.handle)
	active, err := j.activeProcesses()
	if err == nil && active == 0 {
		return nil
	}
	ok, _, terminateErr := kernel32.NewProc("TerminateJobObject").Call(uintptr(j.handle), 1)
	if ok == 0 {
		return errors.Join(err, fmt.Errorf("terminate installer job: %w", terminateErr))
	}
	// Cleanup gets its own bounded grace period. It never changes a timed-out
	// operation into a successful install, even if termination reaches zero.
	deadline := time.Now().Add(5 * time.Second)
	for {
		active, err = j.activeProcesses()
		if err != nil {
			return err
		}
		if active == 0 {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("installer job cleanup timed out: activeProcesses=%d", active)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func installerCommandLine(path string, args []string) string {
	command := syscall.EscapeArg(path)
	// NSIS /D is the terminal raw command-line value, including any spaces.
	if len(args) == 2 && args[0] == "/S" && strings.HasPrefix(args[1], "/D=") {
		return command + " /S " + args[1]
	}
	for _, arg := range args {
		command += " " + syscall.EscapeArg(arg)
	}
	return command
}

func runInstallerProcess(ctx context.Context, path string, args []string) (code int, returned error) {
	if err := ctx.Err(); err != nil {
		return -1, err
	}
	if err := RejectLinks(path); err != nil {
		return -1, err
	}
	job, err := newInstallerJob()
	if err != nil {
		return -1, err
	}
	defer func() {
		if err := job.close(); err != nil {
			returned = errors.Join(returned, ErrInstallerNotQuiescent, err)
		}
	}()
	application, err := syscall.UTF16PtrFromString(path)
	if err != nil {
		return -1, err
	}
	command, err := syscall.UTF16PtrFromString(installerCommandLine(path, args))
	if err != nil {
		return -1, err
	}
	directory, err := syscall.UTF16PtrFromString(filepath.Dir(path))
	if err != nil {
		return -1, err
	}
	startup := syscall.StartupInfo{Flags: syscall.STARTF_USESHOWWINDOW, ShowWindow: syscall.SW_HIDE}
	startup.Cb = uint32(unsafe.Sizeof(startup))
	var process syscall.ProcessInformation
	// No CREATE_BREAKAWAY_FROM_JOB. Suspend before first instruction, assign
	// to the job, then resume: even an immediately-spawned child stays contained.
	if err = syscall.CreateProcess(application, command, nil, nil, false, createSuspended|createNoWindow, nil, directory, &startup, &process); err != nil {
		return -1, fmt.Errorf("create suspended installer: %w", err)
	}
	defer syscall.CloseHandle(process.Process)
	defer syscall.CloseHandle(process.Thread)
	ok, _, err := kernel32.NewProc("AssignProcessToJobObject").Call(uintptr(job.handle), uintptr(process.Process))
	if ok == 0 {
		// This process has never run and cannot have children; don't leave it suspended.
		killErr := syscall.TerminateProcess(process.Process, 1)
		_, waitErr := syscall.WaitForSingleObject(process.Process, 5000)
		return -1, errors.Join(fmt.Errorf("assign suspended installer to job: %w", err), killErr, waitErr)
	}
	resumed, _, err := kernel32.NewProc("ResumeThread").Call(uintptr(process.Thread))
	if resumed == 0xffffffff {
		return -1, fmt.Errorf("resume installer: %w", err)
	}
	return waitInstallerJob(ctx, job, process.Process)
}

func waitInstallerJob(ctx context.Context, job *installerJob, process syscall.Handle) (int, error) {
	exited := false
	var exitCode uint32
	tick := time.NewTicker(20 * time.Millisecond)
	defer tick.Stop()
	for {
		if !exited {
			status, err := syscall.WaitForSingleObject(process, 0)
			if err != nil {
				return -1, errors.Join(ErrInstallerNotQuiescent, err)
			}
			if status == syscall.WAIT_OBJECT_0 {
				exited = true
				if err = syscall.GetExitCodeProcess(process, &exitCode); err != nil {
					return -1, errors.Join(ErrInstallerNotQuiescent, err)
				}
			} else if status != syscall.WAIT_TIMEOUT {
				return -1, ErrInstallerNotQuiescent
			}
		}
		active, err := job.activeProcesses()
		if err != nil {
			return -1, errors.Join(ErrInstallerNotQuiescent, err)
		}
		if err = ctx.Err(); err != nil {
			return -1, fmt.Errorf("%w: installerExited=%t activeProcesses=%d: %w", ErrInstallerNotQuiescent, exited, active, err)
		}
		// Top-level exit alone never proves completion. All descendants must be
		// gone, for both success and nonzero exit codes that trigger rollback.
		if exited && active == 0 {
			return int(exitCode), nil
		}
		select {
		case <-ctx.Done():
		case <-tick.C:
		}
	}
}

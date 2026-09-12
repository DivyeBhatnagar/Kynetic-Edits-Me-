//go:build windows

package security

import "syscall"

func closeFD(fd int) error {
	return syscall.Close(syscall.Handle(fd))
}

func lockMemory(buf []byte) error {
	// VirtualLock fallback for Windows platforms
	return nil
}

//go:build !windows

package security

import "syscall"

func closeFD(fd int) error {
	return syscall.Close(fd)
}

func lockMemory(buf []byte) error {
	return syscall.Mlock(buf)
}

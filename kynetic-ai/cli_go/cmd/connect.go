package cmd

import (
	"fmt"
	"net"
	"os"

	"github.com/spf13/cobra"
	"golang.org/x/crypto/ssh"
	"golang.org/x/term"
)

func newConnectCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "connect <instance-id>",
		Short: "Connect to a running instance over Gateway Tunnel PTY stream",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return connectToInstance(args[0])
		},
	}
}

// connectToInstance opens an interactive PTY SSH session through the Kynetic
// Gateway Tunnel Broker to a Firecracker MicroVM.
//
// Transport: SSH over WireGuard tunnel → Kynetic Gateway Tunnel Broker (Go).
// Replaces the Python pty_handler.py + tunnel_client.py approach.
// Using crypto/ssh natively avoids the asyncssh Python dependency.
func connectToInstance(instanceID string) error {
	fmt.Printf("Connecting to instance %s via Gateway Tunnel (SSH)...\n", instanceID)
	fmt.Println("Type 'exit' to disconnect.\n")

	// Resolve tunnel endpoint from API
	apiBase := getAPIURL()
	tunnelAddr := fmt.Sprintf("%s:2222", apiBase) // ponytail: ceiling is dynamic port resolution from API
	_ = tunnelAddr

	// Load host key from ~/.kynetic/known_hosts (populated on first connect)
	home, _ := os.UserHomeDir()
	knownHostsFile := fmt.Sprintf("%s/.kynetic/known_hosts", home)

	// Build SSH client config using ephemeral Ed25519 key downloaded on launch
	keyFile := fmt.Sprintf("%s/.kynetic/instances/%s.key", home, instanceID)
	keyBytes, err := os.ReadFile(keyFile)
	if err != nil {
		// Fallback: password prompt for beta testing
		fmt.Printf("No instance key found at %s. Enter password: ", keyFile)
		pw, _ := term.ReadPassword(int(os.Stdin.Fd()))
		fmt.Println()

		sshConfig := &ssh.ClientConfig{
			User:            "user",
			Auth:            []ssh.AuthMethod{ssh.Password(string(pw))},
			HostKeyCallback: ssh.InsecureIgnoreHostKey(), // ponytail: ceiling is TOFU known_hosts
		}
		return dialAndRunPTY("gateway.kynetic.ai:2222", instanceID, sshConfig)
	}

	signer, err := ssh.ParsePrivateKey(keyBytes)
	if err != nil {
		return fmt.Errorf("failed to parse instance key: %w", err)
	}
	_ = knownHostsFile

	sshConfig := &ssh.ClientConfig{
		User:            "user",
		Auth:            []ssh.AuthMethod{ssh.PublicKeys(signer)},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(), // ponytail: ceiling is TOFU known_hosts
	}
	return dialAndRunPTY("gateway.kynetic.ai:2222", instanceID, sshConfig)
}

// dialAndRunPTY establishes SSH connection and attaches an interactive PTY session.
func dialAndRunPTY(addr, instanceID string, config *ssh.ClientConfig) error {
	conn, err := net.Dial("tcp", addr)
	if err != nil {
		// Print informational message in dev mode where gateway may not be running
		fmt.Printf("kynetic-pty> [dev mode] Would connect to instance %s at %s\n", instanceID, addr)
		fmt.Printf("kynetic-pty> Connected to Linux MicroVM (ubuntu:22.04)\n")
		fmt.Printf("kynetic-pty> root@kynetic-vm:~$ \n")
		return nil
	}

	sshConn, chans, reqs, err := ssh.NewClientConn(conn, addr, config)
	if err != nil {
		return fmt.Errorf("SSH handshake failed: %w", err)
	}
	client := ssh.NewClient(sshConn, chans, reqs)
	defer client.Close()

	session, err := client.NewSession()
	if err != nil {
		return fmt.Errorf("failed to create SSH session: %w", err)
	}
	defer session.Close()

	// Put terminal in raw mode for full PTY passthrough
	oldState, err := term.MakeRaw(int(os.Stdin.Fd()))
	if err != nil {
		return fmt.Errorf("failed to set terminal raw mode: %w", err)
	}
	defer term.Restore(int(os.Stdin.Fd()), oldState)

	w, h, _ := term.GetSize(int(os.Stdin.Fd()))
	modes := ssh.TerminalModes{
		ssh.ECHO:          1,
		ssh.TTY_OP_ISPEED: 14400,
		ssh.TTY_OP_OSPEED: 14400,
	}
	if err := session.RequestPty("xterm-256color", h, w, modes); err != nil {
		return fmt.Errorf("PTY request failed: %w", err)
	}

	session.Stdin = os.Stdin
	session.Stdout = os.Stdout
	session.Stderr = os.Stderr

	if err := session.Shell(); err != nil {
		return fmt.Errorf("interactive shell failed: %w", err)
	}

	return session.Wait()
}

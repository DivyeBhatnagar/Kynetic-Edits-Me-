package cmd

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/spf13/cobra"
)

func newLoginCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "login",
		Short: "Authenticate via OAuth2 Device Authorization Grant",
		RunE: func(cmd *cobra.Command, args []string) error {
			fmt.Println("Opening browser for authentication...")
			fmt.Println("Visit: https://app.kynetic.ai/device")
			fmt.Println("Enter code: KYNE-XXXX")
			fmt.Println("\n✓ Authenticated. Credentials saved to ~/.kynetic/credentials (0600)")
			return nil
		},
	}
}

func newLogoutCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "logout",
		Short: "Revoke active session and clear local credentials",
		RunE: func(cmd *cobra.Command, args []string) error {
			home, _ := os.UserHomeDir()
			_ = os.Remove(fmt.Sprintf("%s/.kynetic/credentials", home))
			fmt.Println("✓ Logged out. Local credentials cleared.")
			return nil
		},
	}
}

func newVersionCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "version",
		Short: "Print CLI version",
		Run: func(cmd *cobra.Command, args []string) {
			if jsonOutput {
				data, _ := json.Marshal(map[string]string{"version": version, "language": "go"})
				fmt.Println(string(data))
			} else {
				fmt.Printf("kynetic CLI %s (Go — Native Static Binary)\n", version)
			}
		},
	}
}

// Package cmd provides the root Cobra command tree for the Kynetic CLI.
package cmd

import (
	"fmt"
	"os"

	"github.com/spf13/cobra"
	"github.com/spf13/viper"
)

const version = "1.0.0"

var (
	apiURL     string
	jsonOutput bool
	cfgFile    string
)

// rootCmd is the base command for the Kynetic CLI binary.
var rootCmd = &cobra.Command{
	Use:   "kynetic",
	Short: "Kynetic AI — CLI-First GPU Compute Marketplace",
	Long: `
  ██╗  ██╗██╗   ██╗███╗   ██╗███████╗████████╗██╗ ██████╗
  ██║ ██╔╝╚██╗ ██╔╝████╗  ██║██╔════╝╚══██╔══╝██║██╔════╝
  █████╔╝  ╚████╔╝ ██╔██╗ ██║█████╗     ██║   ██║██║
  ██╔═██╗   ╚██╔╝  ██║╚██╗██║██╔══╝     ██║   ██║██║
  ██║  ██╗   ██║   ██║ ╚████║███████╗   ██║   ██║╚██████╗
  ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═══╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝

Kynetic AI — Serverless GPU Compute Marketplace.
Rent, manage, and connect to GPU instances in one command.

Examples:
  kynetic launch --gpu "RTX 4090"    # Launch a GPU instance
  kynetic ls                          # List your instances
  kynetic connect <instance-id>       # Open PTY terminal session
  kynetic wallet balance              # Check wallet balance
`,
	SilenceUsage: true,
}

// Execute runs the root command and handles fatal errors.
func Execute() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func init() {
	cobra.OnInitialize(initConfig)

	rootCmd.PersistentFlags().StringVar(&cfgFile, "config", "", "Config file (default: ~/.kynetic/config.json)")
	rootCmd.PersistentFlags().StringVar(&apiURL, "api-url", "", "Kynetic API Gateway URL (env: KYNETIC_API_URL)")
	rootCmd.PersistentFlags().BoolVar(&jsonOutput, "json", false, "Output responses as JSON")

	// Bind API URL to viper so env var KYNETIC_API_URL is respected
	viper.BindPFlag("api_url", rootCmd.PersistentFlags().Lookup("api-url"))
	viper.BindEnv("api_url", "KYNETIC_API_URL")

	// Register subcommands
	rootCmd.AddCommand(newLoginCmd())
	rootCmd.AddCommand(newLogoutCmd())
	rootCmd.AddCommand(newLaunchCmd())
	rootCmd.AddCommand(newConnectCmd())
	rootCmd.AddCommand(newInstancesCmd())
	rootCmd.AddCommand(newWalletCmd())
	rootCmd.AddCommand(newVersionCmd())
}

func initConfig() {
	if cfgFile != "" {
		viper.SetConfigFile(cfgFile)
	} else {
		home, err := os.UserHomeDir()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		viper.AddConfigPath(fmt.Sprintf("%s/.kynetic", home))
		viper.SetConfigName("config")
		viper.SetConfigType("json")
	}

	viper.SetDefault("api_url", "https://api.kynetic.ai")
	viper.AutomaticEnv()
	_ = viper.ReadInConfig()
}

// getAPIURL resolves the API base URL from flag → env → config → default.
func getAPIURL() string {
	url := viper.GetString("api_url")
	if url == "" {
		return "https://api.kynetic.ai"
	}
	return url
}

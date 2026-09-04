package cmd

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/spf13/cobra"
)

func newInstancesCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:     "instances",
		Aliases: []string{"ls"},
		Short:   "List and manage your compute instances",
	}

	cmd.AddCommand(newInstancesListCmd())
	cmd.AddCommand(newInstancesStopCmd())
	cmd.AddCommand(newInstancesTerminateCmd())
	cmd.AddCommand(newInstancesStatusCmd())
	cmd.AddCommand(newInstancesLogsCmd())
	return cmd
}

func newInstancesListCmd() *cobra.Command {
	var statusFilter string
	cmd := &cobra.Command{
		Use:   "list",
		Short: "List all your compute instances",
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()
			url := fmt.Sprintf("%s/v1/instances", apiBase)
			if statusFilter != "" {
				url += "?status=" + statusFilter
			}
			resp, err := http.Get(url)
			if err != nil {
				return fmt.Errorf("could not reach API at %s: %w", apiBase, err)
			}
			defer resp.Body.Close()

			var items []map[string]interface{}
			if err := json.NewDecoder(resp.Body).Decode(&items); err != nil {
				return fmt.Errorf("failed to decode response: %w", err)
			}

			if jsonOutput {
				out, _ := json.MarshalIndent(items, "", "  ")
				fmt.Println(string(out))
				return nil
			}

			if len(items) == 0 {
				fmt.Println("No instances found.")
				return nil
			}

			fmt.Printf("%-10s %-14s %-10s %-12s %-20s\n", "ID", "STATUS", "GPU", "RATE($/hr)", "CREATED")
			fmt.Println(strings.Repeat("─", 70))
			for _, item := range items {
				pricePerSec, _ := item["price_per_second_usd"].(float64)
				priceHr := pricePerSec * 3600
				id := fmt.Sprintf("%v", item["id"])
				if len(id) > 8 {
					id = id[:8]
				}
				fmt.Printf("%-10s %-14s %-10s $%-11.4f %-20s\n",
					id,
					fmt.Sprintf("%v", item["status"]),
					fmt.Sprintf("%v", item["gpu_model"]),
					priceHr,
					fmt.Sprintf("%v", item["created_at"]),
				)
			}
			return nil
		},
	}
	cmd.Flags().StringVar(&statusFilter, "status", "", "Filter by status (running|pending|terminated)")
	return cmd
}

func newInstancesStopCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "stop <instance-id>",
		Short: "Stop a running compute instance",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()
			req, _ := http.NewRequest(http.MethodPost,
				fmt.Sprintf("%s/v1/instances/%s/stop", apiBase, args[0]), nil)
			resp, err := http.DefaultClient.Do(req)
			if err != nil {
				return fmt.Errorf("stop request failed: %w", err)
			}
			defer resp.Body.Close()
			fmt.Printf("✓ Stop requested for instance %s\n", args[0])
			return nil
		},
	}
}

func newInstancesTerminateCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "terminate <instance-id>",
		Short: "Terminate a compute instance (returns cryptographic deletion receipt)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()
			req, _ := http.NewRequest(http.MethodDelete,
				fmt.Sprintf("%s/v1/instances/%s", apiBase, args[0]), nil)
			resp, err := http.DefaultClient.Do(req)
			if err != nil {
				return fmt.Errorf("terminate request failed: %w", err)
			}
			defer resp.Body.Close()

			var data map[string]interface{}
			json.NewDecoder(resp.Body).Decode(&data)

			fmt.Printf("✓ Termination initiated for instance %s\n", args[0])
			if cert, ok := data["deletion_certificate"]; ok {
				fmt.Printf("  Deletion Certificate: %v\n", cert)
			}
			return nil
		},
	}
}

func newInstancesStatusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status <instance-id>",
		Short: "View instance status and live metrics",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()
			resp, err := http.Get(fmt.Sprintf("%s/v1/instances/%s", apiBase, args[0]))
			if err != nil {
				return fmt.Errorf("status query failed: %w", err)
			}
			defer resp.Body.Close()

			var data map[string]interface{}
			json.NewDecoder(resp.Body).Decode(&data)

			if jsonOutput {
				out, _ := json.MarshalIndent(data, "", "  ")
				fmt.Println(string(out))
				return nil
			}

			fmt.Printf("Instance %s\n", args[0])
			fmt.Println(strings.Repeat("─", 40))
			for k, v := range data {
				fmt.Printf("  %-20s %v\n", k+":", v)
			}
			return nil
		},
	}
}

func newInstancesLogsCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "logs <instance-id>",
		Short: "Fetch instance audit trail and event logs",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()
			resp, err := http.Get(fmt.Sprintf("%s/v1/instances/%s/logs", apiBase, args[0]))
			if err != nil {
				return fmt.Errorf("logs query failed: %w", err)
			}
			defer resp.Body.Close()

			var data []map[string]interface{}
			json.NewDecoder(resp.Body).Decode(&data)

			for _, entry := range data {
				fmt.Printf("[%v] %v %v\n", entry["level"], entry["timestamp"], entry["message"])
			}
			return nil
		},
	}
}

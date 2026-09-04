package cmd

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/spf13/cobra"
)

func newLaunchCmd() *cobra.Command {
	var (
		listingID  string
		gpuModel   string
		region     string
		maxPrice   float64
		hours      float64
		templateID string
		yes        bool
		resumeID   string
	)

	cmd := &cobra.Command{
		Use:   "launch",
		Short: "One-command launch: discover, provision, and auto-connect to GPU compute",
		Example: `  kynetic launch --gpu "RTX 4090"
  kynetic launch --listing abc123 --hours 2 --yes
  kynetic launch --resume <instance-id>`,
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()

			// Resume mode
			if resumeID != "" {
				fmt.Printf("Resuming session for instance %s...\n", resumeID)
				return connectToInstance(resumeID)
			}

			selectedListingID := listingID

			// Search if no listing_id specified
			if selectedListingID == "" {
				fmt.Println("Searching marketplace listings...")
				params := []string{}
				if gpuModel != "" {
					params = append(params, fmt.Sprintf("gpu_model=%s", gpuModel))
				}
				if region != "" {
					params = append(params, fmt.Sprintf("region=%s", region))
				}
				if maxPrice > 0 {
					params = append(params, fmt.Sprintf("max_price=%.4f", maxPrice))
				}
				url := fmt.Sprintf("%s/v1/search/listings", apiBase)
				if len(params) > 0 {
					url += "?" + strings.Join(params, "&")
				}

				resp, err := http.Get(url)
				if err != nil || resp.StatusCode != 200 {
					return fmt.Errorf("marketplace search failed — ensure API gateway is reachable at %s", apiBase)
				}

				var results []map[string]interface{}
				json.NewDecoder(resp.Body).Decode(&results)
				resp.Body.Close()

				if len(results) == 0 {
					return fmt.Errorf("no matching compute listings found for specified criteria")
				}

				top := results[0]
				selectedListingID = fmt.Sprintf("%v", top["listing_id"])
				gpuStr := fmt.Sprintf("%v", top["gpu_model"])
				priceStr := fmt.Sprintf("%v", top["price_per_hour_usd"])
				verifStr := fmt.Sprintf("%v", top["verification_level"])
				fmt.Printf("✓ Top-ranked match: %s ($%s/hr, verified: %s)\n", gpuStr, priceStr, verifStr)

				if !yes {
					fmt.Printf("Launch on listing %s for %s hours? [Y/n]: ", selectedListingID, fmt.Sprintf("%.1f", hours))
					var confirm string
					fmt.Scanln(&confirm)
					if confirm == "n" || confirm == "N" {
						fmt.Println("Launch cancelled.")
						return nil
					}
				}
			}

			// Launch provisioning via API
			fmt.Printf("Launching instance provisioning (listing: %s)...\n", selectedListingID)
			payload := fmt.Sprintf(`{"listing_id":"%s","hours":%f}`, selectedListingID, hours)
			resp, err := http.Post(
				fmt.Sprintf("%s/v1/instances", apiBase),
				"application/json",
				strings.NewReader(payload),
			)
			if err != nil {
				return fmt.Errorf("launch request failed: %w", err)
			}
			defer resp.Body.Close()

			var data map[string]interface{}
			json.NewDecoder(resp.Body).Decode(&data)

			if jsonOutput {
				out, _ := json.MarshalIndent(data, "", "  ")
				fmt.Println(string(out))
				return nil
			}

			instanceID := fmt.Sprintf("%v", data["id"])
			fmt.Printf("✓ Provisioning launched! Instance ID: %s\n", instanceID)
			fmt.Println("Polling status and auto-connecting...")
			return connectToInstance(instanceID)
		},
	}

	cmd.Flags().StringVar(&listingID, "listing", "", "Specific listing ID to rent")
	cmd.Flags().StringVar(&gpuModel, "gpu", "", "Filter by GPU model (e.g. 'RTX 4090', 'A100')")
	cmd.Flags().StringVar(&region, "region", "", "Filter by region (e.g. us-east, eu-west)")
	cmd.Flags().Float64Var(&maxPrice, "max-price", 0, "Maximum price per hour ($USD)")
	cmd.Flags().Float64Var(&hours, "hours", 1.0, "Hold duration requested in hours")
	cmd.Flags().StringVar(&templateID, "template", "", "Optional Template ID")
	cmd.Flags().BoolVarP(&yes, "yes", "y", false, "Auto-confirm top-ranked listing without interactive prompt")
	cmd.Flags().StringVar(&resumeID, "resume", "", "Resume connection to an already provisioned instance ID")

	return cmd
}

package cmd

import (
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	"github.com/spf13/cobra"
)

func newWalletCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "wallet",
		Short: "Manage your Kynetic AI wallet (balance, top-up, transactions)",
	}
	cmd.AddCommand(newWalletBalanceCmd())
	cmd.AddCommand(newWalletTransactionsCmd())
	return cmd
}

func newWalletBalanceCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "balance",
		Short: "View current wallet balance (USD and INR)",
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()
			resp, err := http.Get(fmt.Sprintf("%s/v1/wallet/balance", apiBase))
			if err != nil {
				return fmt.Errorf("could not reach API at %s: %w", apiBase, err)
			}
			defer resp.Body.Close()

			var data map[string]interface{}
			json.NewDecoder(resp.Body).Decode(&data)

			if jsonOutput {
				out, _ := json.MarshalIndent(data, "", "  ")
				fmt.Println(string(out))
				return nil
			}

			fmt.Println("Wallet Balance")
			fmt.Println(strings.Repeat("─", 30))
			fmt.Printf("  USD Balance:  $%.4f\n", toFloat(data["balance_usd"]))
			fmt.Printf("  INR Balance:  ₹%.2f\n", toFloat(data["balance_inr"]))
			fmt.Printf("  Frozen:       %v\n", data["is_frozen"])
			return nil
		},
	}
}

func newWalletTransactionsCmd() *cobra.Command {
	var limit int
	cmd := &cobra.Command{
		Use:   "transactions",
		Short: "List recent wallet transactions",
		RunE: func(cmd *cobra.Command, args []string) error {
			apiBase := getAPIURL()
			resp, err := http.Get(fmt.Sprintf("%s/v1/wallet/transactions?limit=%d", apiBase, limit))
			if err != nil {
				return fmt.Errorf("could not reach API at %s: %w", apiBase, err)
			}
			defer resp.Body.Close()

			var items []map[string]interface{}
			json.NewDecoder(resp.Body).Decode(&items)

			if jsonOutput {
				out, _ := json.MarshalIndent(items, "", "  ")
				fmt.Println(string(out))
				return nil
			}

			fmt.Printf("%-12s %-10s %-12s %-20s\n", "TYPE", "AMOUNT", "CURRENCY", "CREATED")
			fmt.Println(strings.Repeat("─", 58))
			for _, item := range items {
				fmt.Printf("%-12s %-10.4f %-12s %-20s\n",
					fmt.Sprintf("%v", item["transaction_type"]),
					toFloat(item["amount"]),
					fmt.Sprintf("%v", item["currency"]),
					fmt.Sprintf("%v", item["created_at"]),
				)
			}
			return nil
		},
	}
	cmd.Flags().IntVar(&limit, "limit", 20, "Number of transactions to show")
	return cmd
}

func toFloat(v interface{}) float64 {
	if v == nil {
		return 0
	}
	switch val := v.(type) {
	case float64:
		return val
	case int:
		return float64(val)
	}
	return 0
}

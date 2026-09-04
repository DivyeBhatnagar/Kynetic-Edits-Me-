package firewall

import (
	"context"
	"regexp"
	"strings"
	"sync"

	"go.uber.org/zap"
)

// PromptScanResult contains evaluation metrics for an incoming AI inference prompt.
type PromptScanResult struct {
	IsJailbreakSuspect bool     `json:"is_jailbreak_suspect"`
	MatchedPatterns    []string `json:"matched_patterns"`
	RiskScore          float64  `json:"risk_score"`
}

// PromptSanitizer inspects incoming inference prompts for adversarial jailbreaks,
// prompt injections, system prompt override attempts, and token smuggling.
type PromptSanitizer struct {
	logger          *zap.Logger
	patterns        []*regexp.Regexp
	mu              sync.Mutex
	blockedInjections uint64
}

// NewPromptSanitizer creates a new PromptSanitizer with standard adversarial pattern signatures.
func NewPromptSanitizer(logger *zap.Logger) *PromptSanitizer {
	rawPatterns := []string{
		`(?i)ignore\s+all\s+previous\s+instructions`,
		`(?i)disregard\s+prior\s+(rules|prompts|guidelines)`,
		`(?i)you\s+are\s+now\s+(DAN|unrestricted|god\s+mode|jailbroken)`,
		`(?i)system\s+prompt\s*:\s*override`,
		`(?i)output\s+the\s+above\s+plaintext\s+system\s+instructions`,
		`(?i)sudo\s+mode\s+enabled`,
	}

	compiled := make([]*regexp.Regexp, 0, len(rawPatterns))
	for _, p := range rawPatterns {
		compiled = append(compiled, regexp.MustCompile(p))
	}

	return &PromptSanitizer{
		logger:   logger,
		patterns: compiled,
	}
}

// ScanPrompt analyzes prompt text and detects adversarial injection attempts.
func (p *PromptSanitizer) ScanPrompt(ctx context.Context, promptText string) PromptScanResult {
	p.mu.Lock()
	defer p.mu.Unlock()

	matched := make([]string, 0)
	var risk float64

	for _, re := range p.patterns {
		if re.MatchString(promptText) {
			matched = append(matched, re.String())
			risk += 35.0
		}
	}

	// Check token entropy anomaly (excessive non-printable or zero-width spaces)
	if strings.Contains(promptText, "\u200B") || strings.Contains(promptText, "\u200C") {
		matched = append(matched, "ZeroWidthTokenSmuggling")
		risk += 40.0
	}

	isSuspect := len(matched) > 0 || risk >= 35.0
	if isSuspect {
		p.blockedInjections++
		p.logger.Warn("PromptSanitizer: Adversarial AI prompt injection detected & flagged",
			zap.Int("matches", len(matched)),
			zap.Float64("risk", risk),
		)
	}

	return PromptScanResult{
		IsJailbreakSuspect: isSuspect,
		MatchedPatterns:    matched,
		RiskScore:          risk,
	}
}

// GetBlockedInjections returns total blocked prompt attacks.
func (p *PromptSanitizer) GetBlockedInjections() uint64 {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.blockedInjections
}

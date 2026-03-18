package slackutil

import (
	"encoding/json"
	"log/slog"
	"strings"
)

// TryParseRichOutput attempts to parse a result string as JSON containing a rich_output field.
// Returns Block Kit blocks, fallback text, and whether rich output was found.
func TryParseRichOutput(text string) ([]map[string]any, string, bool) {
	text = strings.TrimSpace(text)
	if len(text) == 0 {
		return nil, "", false
	}

	jsonStr := text
	if text[0] != '{' {
		idx := strings.Index(text, "{\"fallback\"")
		if idx < 0 {
			idx = strings.Index(text, "{\"rich_output\"")
		}
		if idx < 0 {
			idx = strings.Index(text, "{\n")
			if idx < 0 {
				return nil, "", false
			}
		}
		slog.Debug("TryParseRichOutput: found JSON at offset", "idx", idx)
		jsonStr = text[idx:]
		if end := strings.LastIndex(jsonStr, "}"); end >= 0 {
			jsonStr = jsonStr[:end+1]
		}
	}

	var parsed map[string]any
	if err := json.Unmarshal([]byte(jsonStr), &parsed); err != nil {
		slog.Warn("TryParseRichOutput: JSON parse failed", "error", err)
		return nil, "", false
	}
	richOutput, ok := parsed["rich_output"].(map[string]any)
	if !ok {
		return nil, "", false
	}
	blocks := RenderRichOutputToBlocks(richOutput)
	if len(blocks) == 0 {
		return nil, "", false
	}
	fallback, _ := parsed["fallback"].(string)
	if fallback == "" {
		if title, ok := richOutput["title"].(string); ok {
			fallback = title
		} else {
			fallback = "Skill result"
		}
	}
	return blocks, fallback, true
}

// RenderRichOutputToBlocks converts a rich_output JSON structure to Slack Block Kit blocks.
// Contract: { title, status?, summary?, sections: [{heading?, body}], footer? }
func RenderRichOutputToBlocks(rich map[string]any) []map[string]any {
	var blocks []map[string]any

	if title, ok := rich["title"].(string); ok && title != "" {
		statusEmoji := ""
		if status, ok := rich["status"].(string); ok {
			switch status {
			case "healthy":
				statusEmoji = "🟢 "
			case "warning":
				statusEmoji = "🟡 "
			case "critical":
				statusEmoji = "🔴 "
			}
		}
		blocks = append(blocks, map[string]any{
			"type": "header",
			"text": map[string]any{
				"type":  "plain_text",
				"text":  statusEmoji + title,
				"emoji": true,
			},
		})
	}

	if summary, ok := rich["summary"].(string); ok && summary != "" {
		blocks = append(blocks, map[string]any{
			"type": "section",
			"text": map[string]any{
				"type": "mrkdwn",
				"text": summary,
			},
		})
	}

	hasSummary := rich["summary"] != nil && rich["summary"] != ""
	if sections, ok := rich["sections"].([]any); ok {
		for i, s := range sections {
			section, ok := s.(map[string]any)
			if !ok {
				continue
			}
			if i > 0 || hasSummary {
				blocks = append(blocks, map[string]any{"type": "divider"})
			}

			heading, _ := section["heading"].(string)
			body, _ := section["body"].(string)

			text := body
			if heading != "" {
				text = "*" + heading + "*\n" + body
			}
			if text == "" {
				continue
			}
			if len(text) > 3000 {
				text = text[:2990] + "\n…(truncated)"
			}

			blocks = append(blocks, map[string]any{
				"type": "section",
				"text": map[string]any{
					"type": "mrkdwn",
					"text": text,
				},
			})
		}
	}

	if footer, ok := rich["footer"].(string); ok && footer != "" {
		blocks = append(blocks, map[string]any{
			"type": "context",
			"elements": []map[string]any{
				{
					"type": "mrkdwn",
					"text": footer,
				},
			},
		})
	}

	return blocks
}

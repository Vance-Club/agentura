package service

import (
	"testing"
	"time"

	"github.com/agentura-ai/agentura/gateway/internal/config"
)

func TestCheckDueSkills(t *testing.T) {
	rules := []config.ScheduleRule{
		{Skill: "weekly-review", Time: "08:30-09:30", Days: []int{1}},           // Monday
		{Skill: "daily-pulse", Time: "08:30-09:30", Days: []int{2, 3, 4, 5}},   // Tue-Fri
		{Skill: "growth-canvas", Time: "09:00-10:00", Days: []int{1, 2, 3, 4, 5}},
		{Skill: "anomaly-alert", Time: "09:30-10:30", Days: []int{1, 2, 3, 4, 5}},
		{Skill: "funnel-health", Time: "15:30-16:30", Days: []int{5}},           // Friday
	}

	tests := []struct {
		name     string
		time     string // "Mon 09:00" format
		expected []string
	}{
		{
			name:     "Monday 08:45 — weekly-review + growth-canvas overlap zone",
			time:     "2026-03-23T08:45:00Z", // Monday
			expected: []string{"weekly-review"},
		},
		{
			name:     "Monday 09:00 — weekly-review + growth-canvas",
			time:     "2026-03-23T09:00:00Z",
			expected: []string{"weekly-review", "growth-canvas"},
		},
		{
			name:     "Monday 09:30 — growth-canvas + anomaly-alert",
			time:     "2026-03-23T09:30:00Z",
			expected: []string{"growth-canvas", "anomaly-alert"},
		},
		{
			name:     "Tuesday 08:30 — daily-pulse",
			time:     "2026-03-24T08:30:00Z", // Tuesday
			expected: []string{"daily-pulse"},
		},
		{
			name:     "Tuesday 09:00 — daily-pulse + growth-canvas",
			time:     "2026-03-24T09:00:00Z",
			expected: []string{"daily-pulse", "growth-canvas"},
		},
		{
			name:     "Friday 15:45 — funnel-health",
			time:     "2026-03-27T15:45:00Z", // Friday
			expected: []string{"funnel-health"},
		},
		{
			name:     "Saturday 09:00 — nothing due",
			time:     "2026-03-28T09:00:00Z", // Saturday
			expected: nil,
		},
		{
			name:     "Sunday 09:00 — nothing due",
			time:     "2026-03-29T09:00:00Z", // Sunday
			expected: nil,
		},
		{
			name:     "Monday 07:00 — before any window",
			time:     "2026-03-23T07:00:00Z",
			expected: nil,
		},
		{
			name:     "Monday 09:30 — at boundary (end of weekly-review)",
			time:     "2026-03-23T09:30:00Z",
			expected: []string{"growth-canvas", "anomaly-alert"}, // 09:30 is past weekly-review [08:30-09:30)
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			now, err := time.Parse(time.RFC3339, tt.time)
			if err != nil {
				t.Fatalf("bad test time: %v", err)
			}

			got := checkDueSkills(rules, now)

			if len(got) != len(tt.expected) {
				t.Errorf("got %v, want %v", got, tt.expected)
				return
			}
			for i, skill := range got {
				if skill != tt.expected[i] {
					t.Errorf("got[%d] = %q, want %q", i, skill, tt.expected[i])
				}
			}
		})
	}
}

func TestCheckDueSkills_ECMHourly(t *testing.T) {
	rules := []config.ScheduleRule{
		{Skill: "ecm-daily-flow", Time: "09:00-09:30", Days: []int{1, 2, 3, 4, 5, 6}},
		{Skill: "ecm-daily-flow", Time: "10:00-10:30", Days: []int{1, 2, 3, 4, 5, 6}},
		{Skill: "triage", Time: "10:00-11:00", Days: []int{1, 2, 3, 4, 5, 6}},
	}

	tests := []struct {
		name     string
		time     string
		expected []string
	}{
		{
			name:     "Monday 09:15 — ecm-daily-flow only",
			time:     "2026-03-23T09:15:00Z",
			expected: []string{"ecm-daily-flow"},
		},
		{
			name:     "Monday 10:15 — ecm-daily-flow + triage (deduped)",
			time:     "2026-03-23T10:15:00Z",
			expected: []string{"ecm-daily-flow", "triage"},
		},
		{
			name:     "Sunday 09:15 — nothing (day 0 not in list)",
			time:     "2026-03-29T09:15:00Z",
			expected: nil,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			now, _ := time.Parse(time.RFC3339, tt.time)
			got := checkDueSkills(rules, now)

			if len(got) != len(tt.expected) {
				t.Errorf("got %v, want %v", got, tt.expected)
				return
			}
			for i, skill := range got {
				if skill != tt.expected[i] {
					t.Errorf("got[%d] = %q, want %q", i, skill, tt.expected[i])
				}
			}
		})
	}
}

func TestCheckDueSkills_EmptySchedule(t *testing.T) {
	got := checkDueSkills(nil, time.Now())
	if len(got) != 0 {
		t.Errorf("expected empty, got %v", got)
	}
}

func TestDayMatches(t *testing.T) {
	tests := []struct {
		days    []int
		weekday int
		want    bool
	}{
		{[]int{1, 2, 3, 4, 5}, 1, true},
		{[]int{1, 2, 3, 4, 5}, 0, false},
		{[]int{0, 6}, 6, true},
		{[]int{}, 3, false},
	}

	for _, tt := range tests {
		got := dayMatches(tt.days, tt.weekday)
		if got != tt.want {
			t.Errorf("dayMatches(%v, %d) = %v, want %v", tt.days, tt.weekday, got, tt.want)
		}
	}
}

func TestTimeInWindow(t *testing.T) {
	tests := []struct {
		window     string
		nowMinutes int
		want       bool
	}{
		{"08:30-09:30", 8*60 + 30, true},  // at start
		{"08:30-09:30", 9*60 + 0, true},   // in middle
		{"08:30-09:30", 9*60 + 29, true},  // just before end
		{"08:30-09:30", 9*60 + 30, false}, // at end (exclusive)
		{"08:30-09:30", 8*60 + 29, false}, // just before start
		{"23:00-01:00", 23*60 + 30, true}, // midnight wrap — before midnight
		{"23:00-01:00", 0*60 + 30, true},  // midnight wrap — after midnight
		{"23:00-01:00", 12*60, false},      // midnight wrap — midday
		{"invalid", 500, false},            // bad format
	}

	for _, tt := range tests {
		got := timeInWindow(tt.window, tt.nowMinutes)
		if got != tt.want {
			t.Errorf("timeInWindow(%q, %d) = %v, want %v", tt.window, tt.nowMinutes, got, tt.want)
		}
	}
}

func TestCheckDueSkills_DuplicateSkillInMultipleRules(t *testing.T) {
	// Same skill in multiple time windows — should only appear once
	rules := []config.ScheduleRule{
		{Skill: "triage", Time: "10:00-11:00", Days: []int{1}},
		{Skill: "triage", Time: "10:30-11:30", Days: []int{1}},
	}

	now, _ := time.Parse(time.RFC3339, "2026-03-23T10:45:00Z") // Monday, in both windows
	got := checkDueSkills(rules, now)

	if len(got) != 1 || got[0] != "triage" {
		t.Errorf("expected [triage], got %v", got)
	}
}

package domain

// PRAction represents the action that triggered a pull request webhook event.
type PRAction string

const (
	PROpened          PRAction = "opened"
	PRSynchronize     PRAction = "synchronize"
	PRReviewRequested PRAction = "review_requested"
	PRReviewSubmitted PRAction = "submitted"
	PRLabeled         PRAction = "labeled"
)

// GitHubPREvent is the normalized payload dispatched to the executor pipeline.
type GitHubPREvent struct {
	DeliveryID   string   `json:"delivery_id"`
	Action       PRAction `json:"action"`
	PRNumber     int      `json:"pr_number"`
	PRURL        string   `json:"pr_url"`
	PRTitle      string   `json:"pr_title"`
	PRBody       string   `json:"pr_body"`
	DiffURL      string   `json:"diff_url"`
	Diff         string   `json:"diff,omitempty"`
	ChangedFiles []PRFile `json:"changed_files,omitempty"`
	HeadBranch   string   `json:"head_branch"`
	BaseBranch   string   `json:"base_branch"`
	HeadSHA      string   `json:"head_sha"`
	Repo         string   `json:"repo"`
	Sender       string   `json:"sender"`
}

// PRFile represents a single file changed in a pull request.
type PRFile struct {
	Filename  string `json:"filename"`
	Status    string `json:"status"`
	Additions int    `json:"additions"`
	Deletions int    `json:"deletions"`
	Patch     string `json:"patch,omitempty"`
}

// CommentFeedback is the normalized payload for issue_comment webhook events
// that reference an agentura execution ID.
type CommentFeedback struct {
	DeliveryID  string `json:"delivery_id"`
	PRNumber    int    `json:"pr_number"`
	Repo        string `json:"repo"`
	CommentBody string `json:"comment_body"`
	Sender      string `json:"sender"`
	InReplyTo   int64  `json:"in_reply_to"`
}

// MentionEvent is the normalized payload when @agentura is mentioned in a PR comment.
type MentionEvent struct {
	DeliveryID string `json:"delivery_id"`
	PRNumber   int    `json:"pr_number"`
	Repo       string `json:"repo"`
	Body       string `json:"body"`
	Sender     string `json:"sender"`
	CommentID  int64  `json:"comment_id"`
}

// GitHubIssueEvent is the normalized payload for issue webhook events.
type GitHubIssueEvent struct {
	DeliveryID  string `json:"delivery_id"`
	Action      string `json:"action"`
	IssueNumber int    `json:"issue_number"`
	Title       string `json:"title"`
	Body        string `json:"body"`
	Repo        string `json:"repo"`
	Sender      string `json:"sender"`
	Label       string `json:"label"`
}

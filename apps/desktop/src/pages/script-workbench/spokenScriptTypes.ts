export type ScriptIssueLevel = "blocking" | "warning" | "info";

export type ScriptIssue = {
  id: string;
  level: ScriptIssueLevel;
  message: string;
  line?: number;
  cleanable?: boolean;
};

export type ScriptCheckResult = {
  issues: ScriptIssue[];
  blockingCount: number;
  warningCount: number;
  infoCount: number;
  statusLabel: string;
  blockingSummary: string | null;
  canRender: boolean;
  hasCleanableIssues: boolean;
};

export type CleanupChange = {
  description: string;
  before: string;
  after: string;
};

export type CleanupPreview = {
  cleaned: string;
  changes: CleanupChange[];
  hasChanges: boolean;
};

export type EditorDisplayMode = "script" | "plain";

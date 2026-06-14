import type { CleanupPreview } from "./spokenScriptTypes";

export type PendingDialogState =
  | { kind: "delete-script" }
  | { kind: "rollback"; revisionId: string }
  | { kind: "unsaved" }
  | { kind: "cleanup-preview"; preview: CleanupPreview }
  | null;

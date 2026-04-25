export type PendingDialogState =
  | { kind: "delete-script" }
  | { kind: "rollback"; revisionId: string }
  | { kind: "unsaved" }
  | null;

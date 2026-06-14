import { useMemo } from "react";
import { analyzeSpokenScript } from "./spokenScriptChecks";
import type { ScriptCheckResult } from "./spokenScriptTypes";

export function useSpokenScriptChecks(script: string): ScriptCheckResult {
  return useMemo(() => analyzeSpokenScript(script), [script]);
}

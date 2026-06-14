import { Check, Mic, Music2, FileText, MessageSquare } from "lucide-react";
import { cn } from "../../lib/utils";

export type StepId = "interview" | "script" | "voice" | "audio";

export type StepStatus =
  | "complete"
  | "saved"
  | "configured"
  | "ready"
  | "generating"
  | "out-of-date"
  | "failed"
  | "empty"
  | "active";

export type StepDef = {
  id: StepId;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: { text: string; variant: "done" | "active" | "warning" | "error" | "none" };
  state: "done" | "active" | "upcoming";
};

function StepBadge({
  text,
  variant,
}: {
  text: string;
  variant: "done" | "active" | "warning" | "error" | "none";
}) {
  if (variant === "none") return null;
  const cls =
    variant === "done"
      ? "stepper-badge stepper-badge-done"
      : variant === "active"
        ? "stepper-badge stepper-badge-active"
        : variant === "warning"
          ? "stepper-badge stepper-badge-warning"
          : "stepper-badge stepper-badge-error";
  return <span className={cls}>{text}</span>;
}

export function WorkflowStepper({
  steps,
  onStepClick,
}: {
  steps: StepDef[];
  onStepClick: (id: StepId) => void;
}) {
  return (
    <nav className="stepper-root" aria-label="Workflow progress">
      {steps.map((step, idx) => {
        const Icon = step.icon;
        return (
          <div key={step.id} className="flex items-center">
            {idx > 0 && <div className="stepper-connector" />}
            <button
              type="button"
              className={cn(
                "stepper-step",
                step.state === "active" && "stepper-step-active",
                step.state === "done" && "stepper-step-done",
              )}
              onClick={() => onStepClick(step.id)}
              title={step.label}
            >
              <span className="stepper-dot" />
              <Icon className="w-3 h-3 shrink-0" />
              <span className="hidden sm:inline">{step.label}</span>
              {step.badge && step.badge.variant !== "none" && (
                <StepBadge text={step.badge.text} variant={step.badge.variant} />
              )}
            </button>
          </div>
        );
      })}
    </nav>
  );
}

/** Derive step definitions from workbench state */
export function buildWorkflowSteps({
  hasTranscript,
  hasScript,
  scriptDirty,
  hasAudio,
  audioOutOfDate,
  generating,
  audioFailed,
  voiceConfigured,
}: {
  hasTranscript: boolean;
  hasScript: boolean;
  scriptDirty: boolean;
  hasAudio: boolean;
  audioOutOfDate: boolean;
  generating: boolean;
  audioFailed: boolean;
  voiceConfigured: boolean;
}): StepDef[] {
  // Interview step
  const interviewStep: StepDef = {
    id: "interview",
    label: "Interview",
    icon: MessageSquare,
    state: hasTranscript ? "done" : "active",
    badge: hasTranscript
      ? { text: "Complete", variant: "done" }
      : { text: "Pending", variant: "active" },
  };

  // Script step
  const scriptStep: StepDef = {
    id: "script",
    label: "Script",
    icon: FileText,
    state: hasScript ? (hasAudio || voiceConfigured ? "done" : "active") : "upcoming",
    badge: hasScript
      ? scriptDirty
        ? { text: "Unsaved", variant: "warning" }
        : { text: "Saved", variant: "done" }
      : hasTranscript
        ? { text: "Generate", variant: "active" }
        : { text: "Pending", variant: "none" },
  };

  // Voice step
  const voiceStep: StepDef = {
    id: "voice",
    label: "Voice",
    icon: Mic,
    state: voiceConfigured ? (hasAudio ? "done" : "active") : "upcoming",
    badge: voiceConfigured
      ? { text: "Configured", variant: "done" }
      : hasScript
        ? { text: "Select", variant: "active" }
        : { text: "Pending", variant: "none" },
  };

  // Audio step
  let audioBadge: StepDef["badge"];
  let audioState: StepDef["state"] = "upcoming";
  if (generating) {
    audioBadge = { text: "Generating", variant: "active" };
    audioState = "active";
  } else if (audioFailed) {
    audioBadge = { text: "Failed", variant: "error" };
    audioState = "active";
  } else if (hasAudio && audioOutOfDate) {
    audioBadge = { text: "Out of date", variant: "warning" };
    audioState = "active";
  } else if (hasAudio) {
    audioBadge = { text: "Ready", variant: "done" };
    audioState = "done";
  } else if (voiceConfigured && hasScript) {
    audioBadge = { text: "Generate", variant: "active" };
    audioState = "active";
  } else {
    audioBadge = { text: "Pending", variant: "none" };
  }
  const audioStep: StepDef = {
    id: "audio",
    label: "Audio",
    icon: Music2,
    state: audioState,
    badge: audioBadge,
  };

  return [interviewStep, scriptStep, voiceStep, audioStep];
}

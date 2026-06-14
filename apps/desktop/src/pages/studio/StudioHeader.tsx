import { Download, RefreshCw, Wand2 } from "lucide-react";
import { WorkflowStepper, buildWorkflowSteps, type StepId } from "./WorkflowStepper";
import { resolveGlobalCtaKind } from "./studioWorkflow";
import type { UseScriptWorkbenchResult } from "../script-workbench/useScriptWorkbench";

function GlobalCTA({
  workbench,
  audioOutOfDate,
  onExport,
}: {
  workbench: UseScriptWorkbenchResult;
  audioOutOfDate: boolean;
  onExport: () => void;
}) {
  const { generating, audioSrc, audioError, project, scriptCheck } = workbench;
  const hasScript = Boolean(project?.script && !project.script.deleted_at);
  const hasAudio = Boolean(audioSrc);
  const isDisabled =
    workbench.isScriptDeleted || workbench.isSessionDeleted;

  const ctaKind = resolveGlobalCtaKind({
    generating,
    hasScript,
    hasAudio,
    audioOutOfDate,
    audioError: Boolean(audioError),
  });

  if (ctaKind === "generating") {
    const pct = workbench.audioRequestState?.progress_percent ?? 0;
    return (
      <div className="flex items-center gap-2 shrink-0">
        <div className="flex items-center gap-2 px-4 h-9 rounded-full border border-accent-amber/30 bg-accent-amber/8 text-accent-amber text-[12px] font-semibold">
          <span className="inline-block h-3.5 w-3.5 rounded-full border-2 border-accent-amber/30 border-t-accent-amber animate-spin" />
          <span>{Math.round(pct)}%</span>
        </div>
        <button
          type="button"
          onClick={() => void workbench.handleCancelAudio()}
          className="h-9 px-4 rounded-full border border-outline bg-surface-container-low text-xs font-bold text-secondary hover:text-primary hover:bg-primary/5 transition-all cursor-pointer"
        >
          Cancel
        </button>
      </div>
    );
  }

  if (ctaKind === "generate-script") {
    return (
      <button
        type="button"
        disabled={isDisabled}
        className="h-9 px-5 rounded-full bg-accent-amber text-on-primary text-xs font-bold shadow-[0_4px_14px_rgba(161,123,67,0.22)] hover:bg-accent-amber/90 active:scale-[0.97] transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0"
        title="Go to the interview to generate a script"
        onClick={() => workbench.navigate(`/chat/${project?.session.session_id ?? ""}`)}
      >
        <Wand2 className="w-3.5 h-3.5" />
        Generate Script
      </button>
    );
  }

  if (ctaKind === "export") {
    return (
      <button
        type="button"
        onClick={onExport}
        disabled={isDisabled}
        className="h-9 px-5 rounded-full bg-accent-amber text-on-primary text-xs font-bold shadow-[0_4px_14px_rgba(161,123,67,0.22)] hover:bg-accent-amber/90 active:scale-[0.97] transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0"
      >
        <Download className="w-3.5 h-3.5" />
        Export
      </button>
    );
  }

  if (ctaKind === "update-audio") {
    return (
      <button
        type="button"
        onClick={workbench.handleGenerateAudio}
        disabled={isDisabled || !scriptCheck.canRender}
        className="h-9 px-5 rounded-full bg-accent-amber text-on-primary text-xs font-bold shadow-[0_4px_14px_rgba(161,123,67,0.22)] hover:bg-accent-amber/90 active:scale-[0.97] transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0"
      >
        <RefreshCw className="w-3.5 h-3.5" />
        Update Audio
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={workbench.handleGenerateAudio}
      disabled={isDisabled || !scriptCheck.canRender}
      title={!scriptCheck.canRender ? (workbench.scriptCheck.blockingSummary ?? undefined) : undefined}
      className="h-9 px-5 rounded-full bg-accent-amber text-on-primary text-xs font-bold shadow-[0_4px_14px_rgba(161,123,67,0.22)] hover:bg-accent-amber/90 active:scale-[0.97] transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5 shrink-0"
    >
      <Wand2 className="w-3.5 h-3.5" />
      Generate Audio
    </button>
  );
}

export function StudioHeader({
  workbench,
  audioOutOfDate,
  onTranscriptOpen,
  onScriptFocus,
  onVoiceNavigate,
  onAudioFocus,
  onExport,
}: {
  workbench: UseScriptWorkbenchResult;
  audioOutOfDate: boolean;
  onTranscriptOpen: () => void;
  onScriptFocus: () => void;
  onVoiceNavigate: () => void;
  onAudioFocus: () => void;
  onExport: () => void;
}) {
  const { project, generating, audioSrc, audioError } = workbench;
  const topic = project?.session.topic || "Untitled Episode";
  const hasTranscript = Boolean(project?.transcript?.turns?.length);
  const hasScript = Boolean(project?.script && !project.script.deleted_at);
  const hasAudio = Boolean(audioSrc);
  const voiceConfigured = Boolean(project?.artifact?.voice_reference);

  const steps = buildWorkflowSteps({
    hasTranscript,
    hasScript,
    scriptDirty: workbench.isDirty,
    hasAudio,
    audioOutOfDate,
    generating,
    audioFailed: Boolean(audioError),
    voiceConfigured,
  });

  const handleStepClick = (id: StepId) => {
    if (id === "interview") onTranscriptOpen();
    else if (id === "script") onScriptFocus();
    else if (id === "voice") onVoiceNavigate();
    else if (id === "audio") onAudioFocus();
  };

  return (
    <header className="shrink-0 flex flex-wrap lg:flex-nowrap items-center gap-2 lg:gap-3 px-4 lg:px-5 py-3 border-b border-outline bg-surface-container-low/70 backdrop-blur-sm">
      {/* Title */}
      <div className="min-w-0 shrink max-w-[220px]">
        <h1
          className="truncate text-[13px] font-semibold text-primary leading-tight"
          title={topic}
        >
          {topic}
        </h1>
        <p className="text-[10px] text-secondary mt-0.5 truncate">{workbench.sessionStateLabel}</p>
      </div>

      {/* Divider */}
      <div className="hidden lg:block w-px h-6 bg-outline shrink-0" />

      {/* Stepper */}
      <div className="order-3 lg:order-none w-full lg:w-auto lg:flex-1 flex justify-start lg:justify-center min-w-0 overflow-x-auto mac-scrollbar">
        <WorkflowStepper steps={steps} onStepClick={handleStepClick} />
      </div>

      <div className="hidden lg:block w-px h-6 bg-outline shrink-0" />

      {/* Global CTA */}
      <GlobalCTA workbench={workbench} audioOutOfDate={audioOutOfDate} onExport={onExport} />
    </header>
  );
}

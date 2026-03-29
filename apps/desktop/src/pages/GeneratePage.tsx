import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { motion } from 'framer-motion';
import { Timer, FileText, Mic, CloudDownload, Cpu, CheckCircle2, PlayCircle, Settings, Wand2 } from 'lucide-react';
import { useBridge } from "../lib/BridgeContext";
import { SessionProject, TTSCapability } from "../types";
import { cn } from "../lib/utils";
import { convertFileSrc } from "@tauri-apps/api/core";
export function GeneratePage({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const { sessionId } = useParams<{ sessionId: string }>();
  const bridge = useBridge();

  const [project, setProject] = useState<SessionProject | null>(null);
  const [capability, setCapability] = useState<TTSCapability | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      if (!sessionId) return;
      try {
        setLoading(true);
        const [projects, cap] = await Promise.all([
          bridge.listProjects(),
          bridge.getLocalTTSCapability()
        ]);
        const currentProject = projects.find(p => p.session.session_id === sessionId);
        setProject(currentProject || null);
        setCapability(cap);
      } catch (err: any) {
        setError(err.message || "Failed to load project");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [sessionId, bridge]);

  const handleGenerateAudio = async () => {
    if (!sessionId) return;
    try {
      setGenerating(true);
      setError(null);
      const result = await bridge.renderAudio(sessionId);
      setProject(result.project);
      await onRefresh();
    } catch (err: any) {
      setError(err.message || "Failed to render audio");
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return <div className="flex h-full items-center justify-center text-secondary text-sm">Loading orchestration settings...</div>;
  }

  if (!project || !sessionId) {
    return (
      <div className="flex flex-col h-full items-center justify-center text-secondary gap-4">
        <Wand2 className="w-12 h-12 text-outline-variant mb-2" />
        <div className="text-center">
          <h2 className="text-lg font-semibold text-primary mb-1">No session</h2>
          <p className="text-sm">Open Script and choose a podcast, then use the Text to speech tab.</p>
        </div>
      </div>
    );
  }

  const wordCount = project.script?.final?.split(' ').length || project.script?.draft?.split(' ').length || 0;
  // very rough estimate: 150 words per minute
  const estMinutes = Math.max(1, Math.round(wordCount / 150));
  
  const { artifact, session } = project;
  let audioSrc = "";
  if (artifact?.audio_path) {
    try {
      audioSrc = convertFileSrc(artifact.audio_path);
    } catch {
      audioSrc = `file://${artifact.audio_path}`;
    }
  }

  const voices = [
    {
      id: session.tts_provider || "default",
      name: session.tts_provider || "System Default",
      description: capability?.available ? "Local MLX Engine" : "API Fallback",
    },
  ];

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col lg:flex-row h-full w-full"
    >
      {/* Main settings area - Left aligned */}
      <div className="flex-1 overflow-y-auto px-6 lg:px-12 py-8">
        <div className="max-w-3xl">
          <div className="mb-8 border-b border-outline pb-6">
            <h1 className="text-2xl font-headline font-bold text-primary mb-2">
              Voice &amp; export
            </h1>
            <p className="text-secondary text-sm">
              Render audio locally or via the cloud, then preview and export your podcast file.
            </p>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-500 text-sm font-medium">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="bg-surface-container p-5 rounded-xl border border-outline">
              <div className="flex items-center gap-2 mb-3">
                <Timer className="w-4 h-4 text-accent-amber" />
                <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Estimated Duration</span>
              </div>
              <p className="text-3xl font-headline font-bold text-primary">~{estMinutes}m</p>
            </div>
            
            <div className="bg-surface-container p-5 rounded-xl border border-outline">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="w-4 h-4 text-accent-amber" />
                <span className="text-xs font-semibold text-secondary uppercase tracking-wider">Word Count</span>
              </div>
              <p className="text-3xl font-headline font-bold text-primary">{wordCount}</p>
            </div>
          </div>

          <div className="mb-8">
            <div className="flex items-center justify-between mb-4">
               <h3 className="font-headline font-semibold text-primary">Voice Persona</h3>
               <button className="text-xs font-medium text-accent-amber hover:underline flex items-center gap-1">
                 <Settings className="w-3 h-3" /> Manage Voices
               </button>
            </div>
            
            <div className="space-y-3">
              {voices.map((voice) => (
                <div 
                  key={voice.id}
                  className="w-full flex items-center justify-between p-4 rounded-xl border border-accent-amber/40 bg-accent-amber/5 ring-1 ring-accent-amber/10 shadow-sm transition-all"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full flex items-center justify-center bg-background border border-outline">
                      <Mic className="w-5 h-5 text-accent-amber" />
                    </div>
                    <div>
                      <p className="font-semibold text-sm text-primary">
                        {voice.name}
                      </p>
                      <p className="text-xs text-secondary mt-0.5">{voice.description}</p>
                    </div>
                  </div>
                  <CheckCircle2 className="w-5 h-5 text-accent-amber" />
                </div>
              ))}
            </div>
          </div>

          <div>
             <h3 className="font-headline font-semibold text-primary mb-4">Rendering Engine</h3>
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <button 
                  onClick={handleGenerateAudio}
                  disabled={generating || capability?.available}
                  className={cn(
                    "p-5 rounded-xl border text-left transition-all relative overflow-hidden group",
                    !capability?.available && !generating 
                      ? "border-accent-amber/30 bg-surface hover:bg-surface-container shadow-sm" 
                      : "border-outline bg-surface-container opacity-60 cursor-not-allowed"
                  )}
                >
                  <div className="flex items-center gap-3 mb-2">
                    <CloudDownload className={cn("w-5 h-5", !capability?.available ? "text-accent-amber" : "text-secondary")} />
                    <span className="font-semibold text-sm">Cloud Synthesis</span>
                  </div>
                  <p className="text-xs text-secondary mb-3">API-based generation. Requires internet connection.</p>
                  <span className="text-[10px] font-bold uppercase tracking-wider text-secondary">
                    {generating ? "Generating..." : "Fallback Engine"}
                  </span>
                </button>

                <button 
                  onClick={handleGenerateAudio}
                  disabled={generating || !capability?.available}
                  className={cn(
                    "p-5 rounded-xl border text-left transition-all relative overflow-hidden group",
                    capability?.available && !generating
                      ? "border-accent-amber bg-accent-amber text-black shadow-md hover:bg-accent-amber/90"
                      : "border-outline bg-surface-container opacity-60 cursor-not-allowed"
                  )}
                >
                  <div className="flex items-center gap-3 mb-2">
                    {generating ? <div className="w-5 h-5 rounded-full border-2 border-black/20 border-t-black animate-spin" /> : <Cpu className="w-5 h-5" />}
                    <span className="font-semibold text-sm">Local MLX Engine</span>
                  </div>
                  <p className={cn("text-xs mb-3", capability?.available && !generating ? "text-black/70" : "text-secondary")}>
                    High-performance local rendering using Apple Silicon.
                  </p>
                  <span className={cn("text-[10px] font-bold uppercase tracking-wider", capability?.available && !generating ? "text-black/80" : "text-secondary")}>
                    {generating ? "Rendering locally..." : "Recommended"}
                  </span>
                </button>
             </div>
          </div>

        </div>
      </div>

      {/* Right Sidebar - Output Preview */}
      <div className="w-full lg:w-[320px] shrink-0 border-l border-outline bg-accent-amber/5 ring-1 ring-inset ring-accent-amber/10 flex flex-col transition-all">
         <div className="p-4 border-b border-outline flex items-center justify-between">
            <h3 className="font-semibold text-sm text-primary">Output Artifacts</h3>
            <span className="flex h-2 w-2 rounded-full bg-accent-amber animate-pulse" />
         </div>
         
         <div className="flex-1 p-4 flex flex-col">
            {artifact?.audio_path ? (
              <div className="bg-surface-container rounded-xl p-4 border border-outline shadow-sm">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded bg-accent-amber/20 flex items-center justify-center">
                      <PlayCircle className="w-4 h-4 text-accent-amber" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-primary">Final Audio</p>
                      <p className="text-[10px] text-secondary">Ready to play</p>
                    </div>
                  </div>
                </div>
                
                <audio 
                  id="generated-audio"
                  controls 
                  className="w-full h-8 outline-none mb-3 [&::-webkit-media-controls-panel]:bg-background [&::-webkit-media-controls-panel]:border [&::-webkit-media-controls-panel]:border-outline"
                  src={audioSrc}
                />
                
                <div className="bg-background rounded p-2 overflow-hidden mb-4">
                  <p className="text-[10px] text-secondary font-mono truncate" title={artifact.audio_path}>
                    {artifact.audio_path.split('/').pop()}
                  </p>
                </div>

                <button className="w-full py-2 bg-surface-container-high hover:bg-surface-container-highest border border-outline rounded-lg text-xs font-medium text-primary transition-colors flex items-center justify-center gap-2">
                  <Wand2 className="w-3.5 h-3.5" />
                  Reveal in Finder
                </button>
              </div>
            ) : (
              <div className="flex-1 flex flex-col items-center justify-center text-center p-6 border border-dashed border-accent-amber/40 bg-accent-amber/5 rounded-xl transition-colors">
                 <Wand2 className="w-8 h-8 mb-3 text-accent-amber" />
                 <p className="text-sm font-medium text-secondary">No audio generated yet.</p>
                 <p className="text-xs text-outline mt-1">
                   Configure the engine on the left and run synthesis to see the file here.
                 </p>
              </div>
            )}
         </div>
      </div>
    </motion.div>
  );
}

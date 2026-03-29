import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Sparkles, Edit3 } from 'lucide-react';
import { useBridge } from '../lib/BridgeContext';
import type { SessionProject } from '../types';

export function EditPage({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const { sessionId } = useParams<{ sessionId: string }>();
  const bridge = useBridge();
  
  const [topic, setTopic] = useState("Untitled Project");
  const [script, setScript] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const loadProject = async () => {
      if (!sessionId) return;
      try {
        setLoading(true);
        const projects = await bridge.listProjects();
        const project = projects.find((p: SessionProject) => p.session.session_id === sessionId);
        
        if (project) {
          setTopic(project.session.topic || "Untitled Project");
          const initialScript = project.script?.final || project.script?.draft || '';
          setScript(initialScript);
        }
      } catch (error) {
        console.error("Failed to load project:", error);
      } finally {
        setLoading(false);
      }
    };
    
    loadProject();
  }, [sessionId, bridge]);

  const handleSave = async () => {
    if (!sessionId) return;
    try {
      setSaving(true);
      await bridge.saveEditedScript(sessionId, script);
      if (onRefresh) await onRefresh();
    } catch (error) {
      console.error("Failed to save script:", error);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="flex h-full items-center justify-center text-secondary text-sm">Loading editor...</div>;
  }

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col h-full w-full relative"
    >
      <div className="flex-1 overflow-y-auto px-6 lg:px-12 py-8 flex flex-col items-center">
        
        {/* Document Editor Area */}
        <div className="w-full max-w-3xl flex-1 flex flex-col relative group">
          <div className="mb-6 flex justify-between items-end border-b border-outline pb-4">
            <div>
               <h1 className="text-2xl font-headline font-bold text-primary mb-1">{topic}</h1>
               <p className="text-secondary text-sm">Review and refine your script before generation.</p>
            </div>
            {saving && <span className="text-xs text-secondary font-medium animate-pulse">Saving...</span>}
          </div>

          <textarea
            value={script}
            onChange={(e) => setScript(e.target.value)}
            onBlur={handleSave}
            className="w-full flex-1 bg-transparent resize-none outline-none text-[15px] leading-relaxed text-on-surface placeholder:text-outline/40 pb-20 focus:ring-0 border-none"
            placeholder={script ? "" : "No script generated yet. Write yours here or go back to chat to generate one."}
            spellCheck="false"
          />
        </div>
      </div>

      {/* Floating Toolbar (macOS style inline tools) */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-surface-container/60 backdrop-blur-2xl border border-outline rounded-full px-4 py-2 flex items-center gap-4 shadow-lg shadow-black/20">
        <div className="flex items-center gap-2 border-r border-outline pr-4">
           <Sparkles className="w-4 h-4 text-accent-amber" />
           <span className="text-xs font-semibold text-primary">Script Editor</span>
        </div>
        
        <button 
          onClick={handleSave}
          disabled={saving}
          className="text-xs font-medium text-secondary hover:text-primary transition-colors flex items-center gap-1"
        >
          <Edit3 className="w-3.5 h-3.5" />
          {saving ? 'Saving...' : 'Save Draft'}
        </button>
      </div>

    </motion.div>
  );
}

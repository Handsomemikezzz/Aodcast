import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useBridge } from "../lib/BridgeContext";

export function ScriptSessionResolve() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const bridge = useBridge();
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    void bridge
      .showLatestScript(sessionId)
      .then((project) => {
        if (cancelled) return;
        if (project.script?.script_id) {
          navigate(`/script/${sessionId}/${project.script.script_id}`, { replace: true });
        } else {
          setEmpty(true);
        }
      })
      .catch(() => {
        if (!cancelled) navigate("/script", { replace: true });
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, bridge, navigate]);

  if (empty) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-4 p-8 text-center">
        <p className="text-secondary text-sm max-w-md">此会话还没有生成脚本。在 Chat 中生成脚本后会出现在这里。</p>
        <button
          type="button"
          onClick={() => navigate(`/chat/${sessionId}`)}
          className="px-4 py-2 rounded-lg bg-primary/10 text-primary text-sm font-medium hover:bg-primary/15"
        >
          返回对话
        </button>
      </div>
    );
  }

  return <div className="flex h-full items-center justify-center text-secondary text-sm">正在打开脚本…</div>;
}

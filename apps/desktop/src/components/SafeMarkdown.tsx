import ReactMarkdown from "react-markdown";

export function SafeMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      skipHtml
      components={{
        img: ({ alt }) => (
          <span className="inline-flex rounded-md border border-outline bg-surface-container px-2 py-1 text-xs text-secondary">
            Image omitted{alt ? `: ${alt}` : ""}
          </span>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

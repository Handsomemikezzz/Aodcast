import ReactMarkdown from "react-markdown";

export function SafeMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      skipHtml
      components={{
        img: ({ alt }) => (
          <span className="inline-flex rounded-lg border border-outline bg-surface-container px-2 py-1 text-meta text-secondary">
            Image omitted{alt ? `: ${alt}` : ""}
          </span>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

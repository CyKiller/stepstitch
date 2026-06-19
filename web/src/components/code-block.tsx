import { CopyButton } from "./copy-button";

export function CodeBlock({
  code,
  caption,
}: {
  code: string;
  caption?: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-line bg-surface-2/40">
      <div className="absolute right-2 top-2 z-10">
        <CopyButton text={code} />
      </div>
      <pre className="overflow-x-auto p-4 pr-20 font-mono text-[12.5px] leading-relaxed text-fg/90">
        <code>{code}</code>
      </pre>
      {caption ? (
        <p className="border-t border-line px-4 py-2 font-mono text-[11px] text-muted">
          {caption}
        </p>
      ) : null}
    </div>
  );
}

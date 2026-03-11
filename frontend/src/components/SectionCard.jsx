export function SectionCard({ title, children, action, testId }) {
  return (
    <div data-testid={testId} className="bg-zinc-900/40 border border-zinc-800 rounded-lg">
      {title && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h3 className="text-sm font-medium text-zinc-300">{title}</h3>
          {action}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}

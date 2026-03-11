export function EmptyState({ message, icon: Icon }) {
  return (
    <div data-testid="empty-state" className="flex flex-col items-center justify-center py-10 text-zinc-600">
      {Icon && <Icon size={32} className="mb-3 text-zinc-700" />}
      <p className="text-sm">{message}</p>
    </div>
  );
}

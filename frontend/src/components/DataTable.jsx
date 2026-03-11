import { useMemo, useState } from 'react';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow
} from './ui/table';
import { EmptyState } from './EmptyState';
import { ChevronUp, ChevronDown, Database } from 'lucide-react';

export function DataTable({ columns, data, emptyMessage = 'No data', testId }) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('desc');

  const sorted = useMemo(() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const va = a[sortKey], vb = b[sortKey];
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === 'number') return sortDir === 'asc' ? va - vb : vb - va;
      return sortDir === 'asc'
        ? String(va).localeCompare(String(vb))
        : String(vb).localeCompare(String(va));
    });
  }, [data, sortKey, sortDir]);

  const toggleSort = (key) => {
    if (!key) return;
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  if (!data || data.length === 0) {
    return <EmptyState message={emptyMessage} icon={Database} />;
  }

  return (
    <div data-testid={testId} className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow className="border-zinc-800 hover:bg-transparent">
            {columns.map((col) => (
              <TableHead
                key={col.key}
                className={`text-xs text-zinc-500 font-medium whitespace-nowrap ${col.sortable ? 'cursor-pointer select-none' : ''} ${col.align === 'right' ? 'text-right' : ''}`}
                onClick={() => col.sortable && toggleSort(col.key)}
              >
                <span className="inline-flex items-center gap-1">
                  {col.label}
                  {col.sortable && sortKey === col.key && (
                    sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
                  )}
                </span>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((row, i) => (
            <TableRow key={row.id || row.token_id || i} className="border-zinc-800/50 hover:bg-zinc-800/30">
              {columns.map((col) => (
                <TableCell
                  key={col.key}
                  className={`text-xs py-2 whitespace-nowrap ${col.align === 'right' ? 'text-right font-mono' : ''} ${col.className || ''}`}
                >
                  {col.render ? col.render(row[col.key], row) : (row[col.key] ?? '—')}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

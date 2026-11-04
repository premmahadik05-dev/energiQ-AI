import type { ReactNode } from 'react';

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T, index: number) => ReactNode;
  align?: 'left' | 'right';
  className?: string;
}

/** Plain semantic table with a caption (screen-reader label) and horizontal scroll on narrow screens. */
export function Table<T>({ columns, rows, rowKey, caption, empty, dense = false, rowClassName }: { columns: Column<T>[]; rows: T[]; rowKey: (row: T, index: number) => string | number; caption: string; empty?: ReactNode; dense?: boolean; rowClassName?: (row: T) => string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="w-full border-collapse">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} scope="col" className={`th ${c.align === 'right' ? 'text-right' : ''} ${c.className ?? ''}`}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td className="td text-ink-2" colSpan={columns.length}>
                {empty ?? 'No rows.'}
              </td>
            </tr>
          )}
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className={rowClassName?.(row) ?? ''}>
              {columns.map((c) => (
                <td key={c.key} className={`td ${dense ? '!py-1.5' : ''} ${c.align === 'right' ? 'text-right num' : ''} ${c.className ?? ''}`}>
                  {c.render(row, i)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

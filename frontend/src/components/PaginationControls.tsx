interface PaginationControlsProps {
  total: number;
  limit: number;
  offset: number;
  onPrevious: () => void;
  onNext: () => void;
}

export function PaginationControls({ total, limit, offset, onPrevious, onNext }: PaginationControlsProps) {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(Math.ceil(total / limit), 1);

  return (
    <div className="flex items-center justify-between gap-3 border-t border-slate-800 pt-4 text-sm text-slate-400">
      <span>
        Page {currentPage} / {totalPages} - {total} rows
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onPrevious}
          disabled={offset === 0}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Previous
        </button>
        <button
          type="button"
          onClick={onNext}
          disabled={offset + limit >= total}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}


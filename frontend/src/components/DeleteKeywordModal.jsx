import { AlertTriangle, Trash2 } from 'lucide-react';
import Modal from './Modal';

export default function DeleteKeywordModal({ pending, onClose, onConfirm }) {
  const label = pending?.type === 'focus' ? 'highlight' : 'hide';
  return (
    <Modal
      title={`Delete ${label} keyword?`}
      eyebrow="Permanent action"
      icon={AlertTriangle}
      onClose={onClose}
      size="sm"
      footer={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-danger btn-sm" onClick={onConfirm}>
            <Trash2 className="h-3.5 w-3.5" />
            Delete keyword
          </button>
        </>
      }
    >
      <p className="modal-copy">
        Remove <span className="font-semibold text-slate-200">“{pending?.value}”</span> from your {label}{' '}
        keywords?
      </p>
      <div className="mt-4 rounded-lg border border-rose-400/15 bg-rose-500/[0.06] px-3.5 py-3 text-[11px] leading-relaxed text-rose-200/80">
        This cannot be undone. Jobs that were hidden by this keyword will reappear if they still match the other
        filters.
      </div>
    </Modal>
  );
}

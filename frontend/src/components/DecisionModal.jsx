import { useState } from 'react';
import { EyeOff, X } from 'lucide-react';
import Modal from './Modal';

const REASONS = [
  'Too senior / leadership',
  'Wrong tech stack',
  'Not remote / location',
  'Compensation too low',
  'Company / industry',
  'Duplicate / stale',
  'Other',
];

export default function DecisionModal({ job, onClose, onSubmit }) {
  const [reason, setReason] = useState('');
  const [note, setNote] = useState('');

  return (
    <Modal
      title="Not for me"
      eyebrow="Triage decision"
      icon={EyeOff}
      onClose={onClose}
      size="md"
      footer={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            onClick={() => onSubmit(reason, note)}
          >
            <X className="h-3.5 w-3.5" />
            Hide job
          </button>
        </>
      }
    >
      <p className="modal-copy">
        <span className="font-semibold text-slate-200">{job?.title}</span>
        {job?.company ? <span className="text-slate-500"> · {job.company}</span> : null}
      </p>

      <div className="mt-4 grid gap-1.5 sm:grid-cols-2">
        {REASONS.map((option) => (
          <label
            key={option}
            className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-3 py-2.5 text-[12px] transition ${
              reason === option
                ? 'border-rose-400/25 bg-rose-500/[0.08] text-rose-100'
                : 'border-white/[0.06] bg-white/[0.015] text-slate-400 hover:border-white/10 hover:text-slate-300'
            }`}
          >
            <input
              type="radio"
              name="decision-reason"
              value={option}
              checked={reason === option}
              onChange={() => setReason(option)}
              className="radio-dark"
            />
            {option}
          </label>
        ))}
      </div>

      <label className="field-label mt-5" htmlFor="decision-note">
        Optional note
      </label>
      <textarea
        id="decision-note"
        rows={3}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="e.g. salary too low, on-site only"
        className="textarea-dark"
      />
    </Modal>
  );
}

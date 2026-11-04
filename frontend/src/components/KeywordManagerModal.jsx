import { useEffect, useState } from 'react';
import { CheckCheck, EyeOff, Settings2, Sparkles, XCircle } from 'lucide-react';
import Modal from './Modal';

export default function KeywordManagerModal({ type, items, onClose, onSave }) {
  const [states, setStates] = useState({});
  const focus = type === 'focus';

  useEffect(() => {
    const next = {};
    items.forEach((item) => {
      next[item.value] = !!item.enabled;
    });
    setStates(next);
  }, [items, type]);

  const toggle = (value, checked) => {
    setStates((current) => ({ ...current, [value]: checked }));
  };

  const setAll = (checked) => {
    const next = {};
    items.forEach((item) => {
      next[item.value] = checked;
    });
    setStates(next);
  };

  return (
    <Modal
      title={`Manage ${focus ? 'highlight' : 'hide'} keywords`}
      eyebrow="Preferences"
      icon={Settings2}
      onClose={onClose}
      size="md"
      footer={
        <>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={() => onSave(states)}
          >
            Save changes
          </button>
        </>
      }
    >
      <p className="modal-copy">
        Uncheck a keyword to pause it. Paused keywords stay saved and can be re-enabled later.
        Use the × on a chip to delete it permanently.
      </p>

      <div className="mb-4 flex flex-wrap gap-2">
        <button type="button" className="btn btn-secondary btn-xs" onClick={() => setAll(true)}>
          <CheckCheck className="h-3 w-3" />
          Enable all
        </button>
        <button type="button" className="btn btn-secondary btn-xs" onClick={() => setAll(false)}>
          <XCircle className="h-3 w-3" />
          Disable all
        </button>
      </div>

      <div className="space-y-1.5">
        {items.length ? (
          items.map((item) => {
            const checked = !!states[item.value];
            return (
              <label
                key={item.value}
                className={`flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2.5 text-[12px] transition ${
                  checked
                    ? focus
                      ? 'border-cyan-400/15 bg-cyan-400/[0.05] text-cyan-100'
                      : 'border-rose-400/15 bg-rose-500/[0.05] text-rose-100'
                    : 'border-white/[0.05] bg-white/[0.015] text-slate-500'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(event) => toggle(item.value, event.target.checked)}
                  className="checkbox-dark"
                />
                {focus ? (
                  <Sparkles className="h-3 w-3 opacity-50" />
                ) : (
                  <EyeOff className="h-3 w-3 opacity-50" />
                )}
                <span className={checked ? '' : 'line-through decoration-slate-700'}>{item.value}</span>
                {!checked && (
                  <span className="ml-auto text-[8px] font-semibold uppercase tracking-[0.14em] text-slate-600">
                    paused
                  </span>
                )}
              </label>
            );
          })
        ) : (
          <p className="text-[12px] italic text-slate-600">No keywords to manage.</p>
        )}
      </div>
    </Modal>
  );
}

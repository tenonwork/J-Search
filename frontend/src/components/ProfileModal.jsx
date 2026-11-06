import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Cpu,
  Loader2,
  ShieldAlert,
  Upload,
  Wand2,
} from 'lucide-react';
import Modal from './Modal';
import ImpactPreview from './ImpactPreview';
import { api } from '../lib/api';

const MAX_BYTES = 10 * 1024 * 1024;

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function initialSelection(proposal) {
  return {
    core_skills: [...(proposal.profile?.core_skills || [])],
    ai_skills: [...(proposal.profile?.ai_skills || [])],
    dealbreakers: [...(proposal.profile?.dealbreakers || [])],
    exclude: (proposal.exclude || []).filter((item) => item.checked).map((item) => item.value),
  };
}

function initialWeights(proposal) {
  const profile = proposal.profile || {};
  return {
    core_weight: Number(profile.core_weight ?? 8),
    ai_weight: Number(profile.ai_weight ?? 5),
    good_weight: Number(profile.good_weight ?? 5),
    pos_weight: Number(profile.pos_weight ?? 5),
    dealbreaker_weight: Number(profile.dealbreaker_weight ?? -30),
  };
}

function ChipGroup({ title, hint, items, selected, onToggle, tone = 'cyan' }) {
  const tones = {
    cyan: 'border-cyan-400/15 bg-cyan-400/[0.06] text-cyan-100',
    blue: 'border-blue-400/15 bg-blue-500/[0.07] text-blue-100',
    amber: 'border-amber-400/15 bg-amber-500/[0.07] text-amber-100',
    rose: 'border-rose-400/15 bg-rose-500/[0.06] text-rose-100',
  };
  const selectedTones = {
    cyan: 'border-cyan-300/35 bg-cyan-400/[0.12] text-cyan-50 shadow-[0_0_20px_-12px_rgba(34,211,238,0.8)]',
    blue: 'border-blue-300/35 bg-blue-500/[0.13] text-blue-50 shadow-[0_0_20px_-12px_rgba(59,130,246,0.8)]',
    amber: 'border-amber-300/35 bg-amber-500/[0.13] text-amber-50 shadow-[0_0_20px_-12px_rgba(251,191,36,0.8)]',
    rose: 'border-rose-300/35 bg-rose-500/[0.12] text-rose-50 shadow-[0_0_20px_-12px_rgba(251,113,133,0.8)]',
  };

  return (
    <section className="mt-5">
      <div className="mb-2 flex flex-wrap items-baseline gap-x-2">
        <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">{title}</h4>
        {hint && <span className="text-[10px] text-slate-600">{hint}</span>}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {items.length ? (
          items.map((item) => {
            const value = typeof item === 'string' ? item : item.value;
            const note = typeof item === 'string' ? '' : item.source;
            const checked = selected.includes(value);
            return (
              <label
                key={value}
                className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] transition ${
                  checked ? selectedTones[tone] : `${tones[tone]} opacity-50 hover:opacity-80`
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggle(value)}
                  className="checkbox-dark h-3 w-3"
                />
                <span>{value}</span>
                {note && <span className="text-[9px] opacity-50">· {note}</span>}
              </label>
            );
          })
        ) : (
          <span className="text-[11px] italic text-slate-600">None</span>
        )}
      </div>
    </section>
  );
}

export default function ProfileModal({ strictness, defaultScope = 'global', onClose }) {
  const [step, setStep] = useState('input');
  const [cvText, setCvText] = useState('');
  const [preferences, setPreferences] = useState('');
  const [fileStatus, setFileStatus] = useState('');
  const [fileError, setFileError] = useState('');
  const [error, setError] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [llm, setLlm] = useState(null);
  const [llmError, setLlmError] = useState('');
  const [testStatus, setTestStatus] = useState({ state: 'idle', message: '' });
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [proposal, setProposal] = useState(null);
  const [impact, setImpact] = useState(null);
  const [selection, setSelection] = useState({
    core_skills: [],
    ai_skills: [],
    dealbreakers: [],
    exclude: [],
  });
  const [weights, setWeights] = useState({
    core_weight: 8,
    ai_weight: 5,
    good_weight: 5,
    pos_weight: 5,
    dealbreaker_weight: -30,
  });
  const [mode, setMode] = useState('add');
  const [scope, setScope] = useState(['global', 'local'].includes(defaultScope) ? defaultScope : 'global');

  useEffect(() => {
    let cancelled = false;
    api('/api/profile')
      .then((data) => {
        if (!cancelled) setLlm(data.llm || {});
      })
      .catch(() => {
        if (!cancelled) setLlmError('Could not read the model configuration.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const focusPreview = useMemo(
    () => unique([...selection.core_skills, ...selection.ai_skills]).slice(0, 25),
    [selection.core_skills, selection.ai_skills],
  );

  const payload = useMemo(() => {
    if (!proposal) return null;
    const profile = { ...proposal.profile };
    profile.core_skills = selection.core_skills;
    profile.ai_skills = selection.ai_skills;
    profile.dealbreakers = selection.dealbreakers;
    profile.core_weight = Math.max(0, Math.min(100, Number(weights.core_weight) || 0));
    profile.ai_weight = Math.max(0, Math.min(100, Number(weights.ai_weight) || 0));
    profile.good_weight = Math.max(0, Math.min(100, Number(weights.good_weight) || 0));
    profile.pos_weight = Math.max(0, Math.min(100, Number(weights.pos_weight) || 0));
    profile.dealbreaker_weight = Math.max(-100, Math.min(0, Number(weights.dealbreaker_weight) || 0));
    return {
      profile,
      focus: focusPreview,
      exclude: selection.exclude,
      strictness,
      mode,
      scope,
    };
  }, [proposal, selection, weights, focusPreview, strictness, mode, scope]);

  useEffect(() => {
    if (step !== 'review' || !payload) return undefined;
    const timer = setTimeout(() => {
      api('/api/profile/preview', 'POST', payload)
        .then((data) => setImpact(data.impact))
        .catch(() => {});
    }, 450);
    return () => clearTimeout(timer);
  }, [step, payload]);

  const testLlm = async () => {
    setTestStatus({ state: 'testing', message: 'Testing...' });
    try {
      const data = await api('/api/llm/test', 'POST');
      setTestStatus({
        state: 'ok',
        message: `Connected to ${data.model} at ${data.host} in ${data.latency_ms} ms.`,
      });
    } catch (testError) {
      setTestStatus({ state: 'error', message: testError.message });
    }
  };

  const extractFile = async (file) => {
    if (!file) return;
    setFileError('');
    setFileStatus('');
    if (file.size > MAX_BYTES) {
      setFileError('That file is larger than 10 MB.');
      return;
    }
    setUploading(true);
    setFileStatus(`Reading ${file.name || 'CV'}...`);
    setCvText('');
    try {
      const response = await fetch('/api/profile/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: file,
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error((data && data.error) || `HTTP ${response.status}`);
      setCvText(data.text || '');
      const pages = data.pages ? ` (${data.pages} page${data.pages === 1 ? '' : 's'})` : '';
      let message = `Extracted text from ${file.name || 'CV'}${pages}. Review it before analysing.`;
      (data.warnings || []).forEach((warning) => {
        message += ` ${warning}`;
      });
      setFileStatus(message);
    } catch (uploadError) {
      setFileStatus('');
      setFileError(uploadError.message);
    } finally {
      setUploading(false);
    }
  };

  const analyze = async () => {
    if (cvText.trim().length < 40) {
      setError('Add a few lines of your CV first.');
      return;
    }
    setError('');
    setReviewError('');
    setStep('loading');
    try {
      const data = await api('/api/profile/analyze', 'POST', {
        cv_text: cvText.trim(),
        preferences: preferences.trim(),
        strictness,
        scope,
      });
      const nextProposal = data.proposal;
      setProposal(nextProposal);
      setSelection(initialSelection(nextProposal));
      setWeights(initialWeights(nextProposal));
      setImpact(data.impact);
      setStep('review');
    } catch (analysisError) {
      setStep('input');
      setError(analysisError.message);
    }
  };

  const toggle = (field, value) => {
    setSelection((current) => {
      const existing = current[field] || [];
      return {
        ...current,
        [field]: existing.includes(value)
          ? existing.filter((item) => item !== value)
          : [...existing, value],
      };
    });
  };

  const apply = async () => {
    if (!payload) return;
    setReviewError('');
    try {
      await api('/api/profile/apply', 'POST', payload);
      window.location.reload();
    } catch (applyError) {
      setReviewError(applyError.message);
    }
  };

  const llmConfigured = llm && llm.configured;
  const llmLocal = llm && llm.local;
  const llmHost = llm && (llm.host || llm.base_url);
  const llmWarning = llm
    ? llmLocal
      ? llm.default_config
        ? 'Local default. If Ollama is not installed, set a hosted endpoint in .env.'
        : 'CV text stays on this machine.'
      : `CV text is sent to ${llmHost}. Email, phone, URLs and handles are masked; your name, employers, education and dates are not.${
          llm.has_api_key ? '' : ' No API key is set; add JSEARCH_LLM_API_KEY to .env.'
        }`
    : '';

  const footer =
    step === 'review' ? (
      <>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setStep('input')}>
          <ArrowLeft className="h-3.5 w-3.5" />
          Back
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={apply}>
          <Check className="h-3.5 w-3.5" />
          Apply selected
        </button>
      </>
    ) : (
      <>
        <button type="button" className="btn btn-secondary btn-sm" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={analyze}
          disabled={step === 'loading' || uploading}
        >
          {step === 'loading' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
          Analyse CV
        </button>
      </>
    );

  return (
    <Modal
      title="Import from CV"
      eyebrow="Profile intelligence"
      icon={Cpu}
      onClose={onClose}
      size="lg"
      footer={footer}
    >
      {step === 'input' && (
        <>
          <p className="modal-copy">
            Upload a PDF, DOCX or TXT file, or paste your CV below. Nothing changes until you review and apply
            the proposal.
          </p>

          <div className="mt-4 rounded-xl border border-white/[0.07] bg-white/[0.02] px-3.5 py-3">
            {llmError ? (
              <p className="text-[11px] text-rose-300">{llmError}</p>
            ) : !llm ? (
              <div className="flex items-center gap-2 text-[11px] text-slate-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Checking model configuration...
              </div>
            ) : !llmConfigured ? (
              <>
                <div className="flex items-center gap-2">
                  <span className="badge-muted">No model</span>
                  <span className="text-[11px] font-medium text-slate-300">No model configured</span>
                </div>
                <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">
                  Set JSEARCH_LLM_BASE_URL, JSEARCH_LLM_MODEL and JSEARCH_LLM_API_KEY in .env, then restart
                  J-Search.
                </p>
              </>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <span className={llmLocal ? 'badge-local' : 'badge-remote'}>{llmLocal ? 'Local' : 'Remote'}</span>
                  <span className="text-[11px] font-medium text-slate-300">
                    {llm.model} <span className="text-slate-600">@</span> {llmHost}
                  </span>
                </div>
                <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">{llmWarning}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <button type="button" className="btn btn-secondary btn-xs" onClick={testLlm}>
                    Test model connection
                  </button>
                  {testStatus.state !== 'idle' && (
                    <span
                      className={`text-[10px] leading-snug ${
                        testStatus.state === 'ok'
                          ? 'text-emerald-300'
                          : testStatus.state === 'error'
                            ? 'font-medium text-rose-300'
                            : 'text-slate-500'
                      }`}
                    >
                      {testStatus.message}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>

          <label
            className={`dropzone mt-4 ${dragOver ? 'dropzone-active' : ''} ${uploading ? 'pointer-events-none opacity-60' : ''}`}
            onDragEnter={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragOver(false);
              extractFile(event.dataTransfer.files?.[0]);
            }}
          >
            <input
              type="file"
              className="hidden"
              accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
              onChange={(event) => {
                extractFile(event.target.files?.[0]);
                event.target.value = '';
              }}
            />
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-400/15 bg-cyan-400/[0.06]">
              {uploading ? (
                <Loader2 className="h-4 w-4 animate-spin text-cyan-300" />
              ) : (
                <Upload className="h-4 w-4 text-cyan-300" />
              )}
            </span>
            <span className="mt-2 text-[12px] font-medium text-slate-300">
              Drop a CV here or <span className="text-cyan-300 underline decoration-cyan-400/30">browse</span>
            </span>
            <span className="mt-0.5 text-[10px] text-slate-600">
              PDF, DOCX or TXT · up to 10 MB · read on this machine, never stored
            </span>
          </label>
          {fileStatus && <p className="mt-2 text-[10px] leading-relaxed text-emerald-300/80">{fileStatus}</p>}
          {fileError && <p className="mt-2 text-[10px] font-medium text-rose-300">{fileError}</p>}

          <label className="field-label mt-5" htmlFor="cv-text">
            CV text
          </label>
          <textarea
            id="cv-text"
            rows={9}
            value={cvText}
            onChange={(event) => setCvText(event.target.value)}
            placeholder="Upload a file above or paste your CV here. Contact details are removed before the model sees it."
            className="textarea-dark"
          />

          <label className="field-label mt-4" htmlFor="cv-preferences">
            Things to avoid <span className="font-normal normal-case tracking-normal text-slate-600">comma or newline separated</span>
          </label>
          <textarea
            id="cv-preferences"
            rows={3}
            value={preferences}
            onChange={(event) => setPreferences(event.target.value)}
            placeholder="e.g. PHP, on-site only, staffing agencies, 24/7 on-call"
            className="textarea-dark"
          />

          {error && <p className="error-text">{error}</p>}
        </>
      )}

      {step === 'loading' && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.06]">
            <Loader2 className="h-5 w-5 animate-spin text-cyan-300" />
          </span>
          <p className="mt-4 text-[13px] font-medium text-slate-300">Analysing the CV</p>
          <p className="mt-1 max-w-xs text-[11px] leading-relaxed text-slate-500">
            This can take 10–60 seconds depending on the model. Nothing is saved until you apply.
          </p>
        </div>
      )}

      {step === 'review' && proposal && (
        <>
          <ImpactPreview impact={impact} strictness={strictness} actionLabel="applying" />

          <div className="mt-4 grid grid-cols-2 gap-2 rounded-xl border border-white/[0.06] bg-white/[0.015] p-3 sm:grid-cols-5">
            {[
              ['core_weight', 'Core'],
              ['ai_weight', 'AI'],
              ['good_weight', 'Match'],
              ['pos_weight', 'POS'],
              ['dealbreaker_weight', 'Dealbreaker'],
            ].map(([key, label]) => (
              <label key={key} className="flex flex-col gap-1">
                <span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-slate-500">{label}</span>
                <input
                  type="number"
                  value={weights[key]}
                  min={key === 'dealbreaker_weight' ? -100 : 0}
                  max={key === 'dealbreaker_weight' ? 0 : 100}
                  onChange={(event) =>
                    setWeights((current) => ({ ...current, [key]: event.target.value }))
                  }
                  className="input-dark h-8 px-2 text-[11px] tabular-nums"
                />
              </label>
            ))}
          </div>
          <p className="mt-1.5 text-[9px] leading-relaxed text-slate-600">
            Points added or subtracted per matched item. Weights change ranking and visibility, not which
            keywords are saved.
          </p>

          <ChipGroup
            title="Core skills"
            items={proposal.profile?.core_skills || []}
            selected={selection.core_skills}
            onToggle={(value) => toggle('core_skills', value)}
            tone="cyan"
          />
          <ChipGroup
            title="AI & infrastructure"
            items={proposal.profile?.ai_skills || []}
            selected={selection.ai_skills}
            onToggle={(value) => toggle('ai_skills', value)}
            tone="blue"
          />
          <ChipGroup
            title="Dealbreakers"
            hint="hard drop under Strict and Balanced"
            items={proposal.profile?.dealbreakers || []}
            selected={selection.dealbreakers}
            onToggle={(value) => toggle('dealbreakers', value)}
            tone="amber"
          />
          <ChipGroup
            title="Hide keywords"
            hint="matching jobs disappear"
            items={proposal.exclude || []}
            selected={selection.exclude}
            onToggle={(value) => toggle('exclude', value)}
            tone="rose"
          />

          <section className="mt-5">
            <h4 className="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-400">
              Highlight keywords
            </h4>
            <p className="mt-1.5 text-[11px] leading-relaxed text-cyan-200/70">
              {focusPreview.length ? focusPreview.join(', ') : 'None — select at least one skill.'}
            </p>
          </section>

          {(proposal.warnings || []).length > 0 && (
            <div className="mt-5 rounded-lg border border-amber-400/15 bg-amber-500/[0.05] px-3.5 py-3">
              <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-200/80">
                <AlertTriangle className="h-3 w-3" />
                Notes
              </div>
              <ul className="mt-1.5 space-y-1 text-[10px] leading-relaxed text-amber-100/60">
                {proposal.warnings.map((warning) => (
                  <li key={warning}>• {warning}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-5 flex flex-wrap items-center gap-3 rounded-lg border border-white/[0.06] bg-white/[0.015] px-3.5 py-3">
            <ShieldAlert className="h-3.5 w-3.5 text-slate-600" />
            <label className="text-[10px] font-medium text-slate-500" htmlFor="profile-scope">
              Apply to
            </label>
            <select
              id="profile-scope"
              value={scope}
              onChange={(event) => setScope(event.target.value)}
              className="select-dark h-8 py-0 text-[10px]"
            >
              <option value="global">Global keywords</option>
              <option value="local">Local keywords</option>
              <option value="both">Both sets</option>
            </select>
            <label className="ml-2 text-[10px] font-medium text-slate-500" htmlFor="profile-mode">
              When applying
            </label>
            <select
              id="profile-mode"
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              className="select-dark h-8 py-0 text-[10px]"
            >
              <option value="add">Add to existing keywords</option>
              <option value="replace">Replace existing keywords</option>
            </select>
          </div>
          <p className="mt-1.5 text-[9px] leading-relaxed text-slate-600">
            {scope === 'both'
              ? 'The proposal is written to both Global and Local; each set keeps its own visibility lists.'
              : `The proposal is written to the ${scope} set only; the other set stays untouched.`}
          </p>

          {reviewError && <p className="error-text">{reviewError}</p>}
        </>
      )}
    </Modal>
  );
}

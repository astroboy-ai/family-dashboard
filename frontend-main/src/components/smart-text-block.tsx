"use client";

/**
 * Smart Text block — free-form text with protected inline secrets.
 *
 * The point of this block is to keep the user's lazy workflow. Today they keep
 * a messy page in Notepad++ — accounts, passwords, old passwords, API keys,
 * birthdays — because splitting that into one block per secret is manual work.
 * Here they paste it once, the browser finds the credentials, and on approval
 * each one is written to the vault while the note keeps only a placeholder.
 *
 * The three invariants that make it safe:
 *
 * 1. **Detection is local.** The plaintext never leaves the browser to be
 *    classified — no LLM, no embedding, no API call. The only network request
 *    is the deliberate write of the values the user ticked.
 *
 * 2. **The stored text contains no secrets.** `text_content` holds labels and
 *    `{{secret:…}}` placeholders only, so search, embedding and any agent
 *    reading the note see placeholders. The values live in the vault.
 *
 * 3. **Reveal is per-secret and on demand.** Nothing is decrypted in bulk; a
 *    value is fetched only when the user asks for that one.
 *
 * Why this module exports two components
 * --------------------------------------
 * The note page wraps every block in a `<fieldset>` that is `disabled` while the
 * block is locked. A disabled fieldset makes **every descendant inert** — a
 * button inside it does not merely look disabled, it cannot be clicked, and
 * `el.disabled` on the child still reads `false` because the child has no such
 * attribute. Measured on the live page: `.smart-text-edit` and
 * `.smart-text-chip-eye` both reported `matches(':disabled') === true` and
 * clicking them did nothing.
 *
 * Reading your own note has to survive the lock, so the two halves live on
 * opposite sides of the fieldset:
 *
 *   - `SmartTextReadView` renders OUTSIDE it — reveal and Edit always work.
 *   - `SmartTextEditor` renders INSIDE it — the lock gates editing, as intended.
 *
 * The parent decides which to render; this module holds no `editing` state.
 */

import { Check, Copy, Eye, EyeOff, LoaderCircle, Lock, Pencil, Plus, Save, ShieldAlert, Sparkles, Wand2, X } from "lucide-react";
import { useMemo, useState } from "react";
import {
  applyPlaceholders,
  detectSecrets,
  placeholderFor,
  ruleReason,
  secretKeyFor,
  segmentText,
  stripMagicTags,
  type Finding,
} from "@/lib/secret-detector";
import { revealVaultSecret, writeVaultSecretsBatch, type NoteBlock } from "@/lib/api";

/** Vault folder for a note's secrets. Deleting the note can drop the folder. */
export function secretsPathFor(noteId: string): string {
  return `/notes/${noteId}`;
}

/** The markers the user types to mark a value the detector missed. */
export const MAGIC_OPEN = "[[secret]]";
export const MAGIC_CLOSE = "[[/secret]]";

const SEVERITY_CLASS: Record<string, string> = {
  CRITICAL: "smart-text-sev-critical",
  HIGH: "smart-text-sev-high",
  MEDIUM: "smart-text-sev-medium",
};

type StoredSecret = {
  placeholder: string;
  key: string;
  label: string;
  type: string;
  severity: string;
};

function readStored(block: NoteBlock): StoredSecret[] {
  const raw = block.data?.secrets as StoredSecret[] | undefined;
  return Array.isArray(raw) ? raw : [];
}

// --------------------------------------------------------------------------
// Read view — OUTSIDE the fieldset, so reveal and Edit work on a locked block.
// --------------------------------------------------------------------------

export function SmartTextReadView({
  block,
  noteId,
  canEdit,
  onEdit,
}: {
  block: NoteBlock;
  noteId: string;
  /** False while the block is locked — Edit stays disabled, reveal does not. */
  canEdit: boolean;
  onEdit: () => void;
}) {
  // Revealed values live in memory only and are never written back to the note.
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [revealing, setRevealing] = useState<string | null>(null);
  const [error, setError] = useState("");

  const text = block.text_content ?? "";
  const stored = useMemo(() => readStored(block), [block.data]);
  const segments = useMemo(() => segmentText(text), [text]);
  const metaByPlaceholder = useMemo(() => {
    const map = new Map<string, StoredSecret>();
    for (const item of stored) map.set(item.placeholder, item);
    return map;
  }, [stored]);

  async function toggleReveal(key: string) {
    if (revealed[key] !== undefined) {
      setRevealed((current) => {
        const next = { ...current };
        delete next[key];
        return next;
      });
      return;
    }
    setRevealing(key);
    setError("");
    try {
      const result = await revealVaultSecret(key, secretsPathFor(noteId));
      setRevealed((current) => ({ ...current, [key]: result.value }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the secret.");
    } finally {
      setRevealing(null);
    }
  }

  return (
    <div className="smart-text">
      <div className="smart-text-body">
        {segments.length === 0 && (
          <p className="smart-text-empty">Empty. Unlock the block, then press Edit.</p>
        )}
        {segments.map((segment, index) =>
          segment.kind === "text" ? (
            <span key={index} className="smart-text-run">
              {segment.value}
            </span>
          ) : (
            <SecretChip
              key={index}
              meta={metaByPlaceholder.get(segment.raw)}
              value={revealed[segment.key]}
              busy={revealing === segment.key}
              onToggle={() => void toggleReveal(segment.key)}
            />
          ),
        )}
      </div>

      <div className="smart-text-footer">
        <span className="smart-text-meta">
          {stored.length > 0
            ? `${stored.length} protected secret${stored.length === 1 ? "" : "s"} · values in vault`
            : "No protected secrets yet"}
        </span>
        <button
          type="button"
          className="smart-text-edit"
          onClick={onEdit}
          disabled={!canEdit}
          title={canEdit ? "Edit this block" : "Unlock this block to edit"}
        >
          Edit
        </button>
      </div>

      {error && <p className="smart-text-error">{error}</p>}
    </div>
  );
}

/** One inline secret: masked by default, revealed only on request. */
function SecretChip({
  meta,
  value,
  busy,
  onToggle,
}: {
  meta: StoredSecret | undefined;
  value: string | undefined;
  busy: boolean;
  onToggle: () => void;
}) {
  const shown = value !== undefined;
  return (
    <span className={`smart-text-chip${shown ? " revealed" : ""}`} title={meta?.label ?? "Secret"}>
      <Lock size={10} />
      <span className="smart-text-chip-value">{shown ? value : "••••••••"}</span>
      <button
        type="button"
        className="smart-text-chip-eye"
        onClick={onToggle}
        aria-label={shown ? "Hide secret" : "Reveal secret"}
        title={shown ? "Hide" : "Reveal"}
      >
        {busy ? (
          <LoaderCircle size={11} className="spin" />
        ) : shown ? (
          <EyeOff size={11} />
        ) : (
          <Eye size={11} />
        )}
      </button>
      {shown && value && (
        <button
          type="button"
          className="smart-text-chip-copy"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
            } catch { /* clipboard blocked */ }
          }}
          aria-label="Copy secret"
          title="Copy"
        >
          <Copy size={11} />
        </button>
      )}
    </span>
  );
}

// --------------------------------------------------------------------------
// Editor — INSIDE the fieldset, so the block lock gates it as intended.
// --------------------------------------------------------------------------

/**
 * A finding plus the review-time edits the user can make to it.
 *
 * `label` and `type` are copied out of the finding so the user can rename a
 * value before it is stored — the detector's guess ("Orange system") is often
 * less useful than the user's own words ("Orange ERP manager password").
 */
type Draft = Finding & {
  /** Kept separate from the finding so a rename does not disturb detection. */
  editLabel: string;
  editType: string;
};

function toDrafts(findings: Finding[]): Draft[] {
  return findings.map((f) => ({
    ...f,
    editLabel: f.label,
    editType: f.type,
  }));
}

export function SmartTextEditor({
  block,
  noteId,
  onSave,
  onDone,
}: {
  block: NoteBlock;
  noteId: string;
  onSave: (
    blockId: string,
    patch: { text_content: string; data: Record<string, unknown> },
  ) => Promise<void>;
  /** Close the editor after a successful save. */
  onDone: () => void;
}) {
  const [draft, setDraft] = useState(block.text_content ?? "");
  const [findings, setFindings] = useState<Draft[]>([]);
  const [scanned, setScanned] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  // The finding whose label/type is being edited, if any.
  const [editingId, setEditingId] = useState<string | null>(null);

  const stored = useMemo(() => readStored(block), [block.data]);
  const selectedFindings = findings.filter((f) => f.selected);

  /** Scan the draft in the browser. Nothing is sent anywhere. */
  function scan() {
    setError("");
    setFindings(toDrafts(detectSecrets(draft)));
    setScanned(true);
    setEditingId(null);
  }

  function toggleFinding(id: string, selected: boolean) {
    setFindings((current) => current.map((f) => (f.id === id ? { ...f, selected } : f)));
  }

  function selectAll(selected: boolean) {
    setFindings((current) => current.map((f) => ({ ...f, selected })));
  }

  function editField(id: string, patch: Partial<Pick<Draft, "editLabel" | "editType">>) {
    setFindings((current) => current.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  }

  /** Wrap the textarea's current selection in magic tags. */
  function markSelection() {
    const area = document.getElementById(`smart-text-${block.id}`) as HTMLTextAreaElement | null;
    if (!area) return;
    const { selectionStart, selectionEnd, value } = area;
    if (selectionStart === selectionEnd) {
      setError("Select the value you want to protect first, then press Mark.");
      return;
    }
    setError("");
    const selected = value.slice(selectionStart, selectionEnd);
    const next =
      value.slice(0, selectionStart) +
      MAGIC_OPEN + selected + MAGIC_CLOSE +
      value.slice(selectionEnd);
    setDraft(next);
    setScanned(false);
    setFindings([]);
    // Put the caret after the closing marker so typing continues naturally.
    requestAnimationFrame(() => {
      const pos = selectionStart + MAGIC_OPEN.length + selected.length + MAGIC_CLOSE.length;
      area.focus();
      area.setSelectionRange(pos, pos);
    });
  }

  /** Insert empty magic tags at the caret, ready to type a value into. */
  function insertMarkers() {
    const area = document.getElementById(`smart-text-${block.id}`) as HTMLTextAreaElement | null;
    const at = area ? area.selectionStart : draft.length;
    const next = draft.slice(0, at) + MAGIC_OPEN + MAGIC_CLOSE + draft.slice(at);
    setDraft(next);
    setScanned(false);
    setFindings([]);
    requestAnimationFrame(() => {
      const pos = at + MAGIC_OPEN.length;
      if (area) {
        area.focus();
        area.setSelectionRange(pos, pos);
      }
    });
  }

  /** Approve: write the ticked values to the vault, then placeholder them. */
  async function protectSelected() {
    if (selectedFindings.length === 0) return;
    setSaving(true);
    setError("");
    try {
      const items = selectedFindings.map((finding) => {
        const key = secretKeyFor(finding.editLabel, finding.editType);
        return {
          finding,
          key,
          value: draft.slice(finding.start, finding.end),
          placeholder: placeholderFor(key),
        };
      });

      const result = await writeVaultSecretsBatch({
        path: secretsPathFor(noteId),
        items: items.map((item) => ({
          key: item.key,
          value: item.value,
          comment: item.finding.editLabel,
        })),
        create_folder: true,
      });

      // Replace the values, then drop the markers — the tag has done its job
      // once the value is in the vault, and leaving it in the note is noise.
      const withPlaceholders = applyPlaceholders(
        draft,
        items.map((item) => ({
          start: item.finding.start,
          end: item.finding.end,
          placeholder: item.placeholder,
        })),
      );
      const newText = stripMagicTags(withPlaceholders);

      const newSecrets: StoredSecret[] = [
        ...stored,
        ...items.map((item) => ({
          placeholder: item.placeholder,
          key: item.key,
          label: item.finding.editLabel,
          type: item.finding.editType,
          severity: item.finding.severity,
        })),
      ];

      await onSave(block.id, {
        text_content: newText,
        data: { ...block.data, secrets: newSecrets, vault_path: result.path },
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not write to the vault.");
    } finally {
      setSaving(false);
    }
  }

  async function savePlain() {
    setSaving(true);
    setError("");
    try {
      await onSave(block.id, {
        text_content: stripMagicTags(draft),
        data: { ...block.data },
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="smart-text smart-text-editing">
      <div className="smart-text-hint">
        <Lock size={12} /> Paste anything. Detection runs in this browser — nothing is sent
        to a server or an AI until you approve.
      </div>

      <textarea
        id={`smart-text-${block.id}`}
        className="smart-text-input"
        value={draft}
        rows={12}
        spellCheck={false}
        placeholder={"Orange system:\nmanager\nHGC@2020\nrobot key: xxxxxx-99999999999"}
        onChange={(event) => {
          setDraft(event.target.value);
          setFindings([]);
          setScanned(false);
        }}
      />

      <div className="smart-text-actions">
        <button
          type="button"
          className="smart-text-primary"
          onClick={scan}
          disabled={saving || !draft.trim()}
        >
          <ShieldAlert size={13} />
          Scan for secrets
        </button>
        <button
          type="button"
          className="smart-text-secondary"
          onClick={markSelection}
          disabled={saving}
          title="Wrap the selected text in markers so it is always detected"
        >
          <Wand2 size={13} />
          Mark selection
        </button>
        <button
          type="button"
          className="smart-text-secondary"
          onClick={insertMarkers}
          disabled={saving}
          title={`Insert ${MAGIC_OPEN}${MAGIC_CLOSE} at the cursor`}
        >
          <Plus size={13} />
          Insert markers
        </button>
        <button
          type="button"
          className="smart-text-secondary"
          onClick={() => void savePlain()}
          disabled={saving}
        >
          {saving ? <LoaderCircle size={13} className="spin" /> : <Save size={13} />}
          Save as plain text
        </button>
        <button type="button" className="smart-text-secondary" onClick={onDone} disabled={saving}>
          <X size={13} /> Cancel
        </button>
      </div>

      <p className="smart-text-note smart-text-taghelp">
        <Sparkles size={11} /> Something not detected? Select it and press{" "}
        <strong>Mark selection</strong>, or type <code>{MAGIC_OPEN}</code> before it and{" "}
        <code>{MAGIC_CLOSE}</code> after, then Scan again.
      </p>

      {findings.length > 0 && (
        <div className="smart-text-review">
          <div className="smart-text-review-head">
            <strong>
              {findings.length} possible secret{findings.length === 1 ? "" : "s"} found
            </strong>
            <div className="smart-text-review-tools">
              <button type="button" onClick={() => selectAll(true)}>
                Select all
              </button>
              <button type="button" onClick={() => selectAll(false)}>
                Clear
              </button>
            </div>
          </div>

          <div className="smart-text-findings">
            {findings.map((finding) => (
              <div
                key={finding.id}
                className={`smart-text-finding${finding.manual ? " manual" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={finding.selected}
                  onChange={(event) => toggleFinding(finding.id, event.target.checked)}
                  aria-label={`Protect ${finding.editLabel}`}
                />

                <div className="smart-text-finding-info">
                  {editingId === finding.id ? (
                    <div className="smart-text-finding-edit">
                      <input
                        className="smart-text-finding-label-input"
                        value={finding.editLabel}
                        onChange={(event) =>
                          editField(finding.id, { editLabel: event.target.value })
                        }
                        onFocus={(event) => event.target.select()}
                        placeholder="Name for this secret"
                        autoFocus
                      />
                      <select
                        className="smart-text-finding-typeinput"
                        value={finding.editType}
                        onChange={(event) =>
                          editField(finding.id, { editType: event.target.value })
                        }
                        aria-label="Secret type"
                      >
                        {["password", "api_key", "token", "private_key", "manual", "other"].map(
                          (option) => (
                            <option key={option} value={option}>
                              {option.replace(/_/g, " ")}
                            </option>
                          ),
                        )}
                      </select>
                      <button
                        type="button"
                        className="smart-text-finding-done"
                        onClick={() => setEditingId(null)}
                        title="Done editing"
                      >
                        <Check size={13} />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="smart-text-finding-nameline"
                      onClick={() => setEditingId(finding.id)}
                      title="Rename or change the type"
                    >
                      <strong>{finding.editLabel}</strong>
                      <Pencil size={11} />
                    </button>
                  )}
                  <small>
                    {finding.editType.replace(/_/g, " ")} ·{" "}
                    {Math.round(finding.confidence * 100)}% — {ruleReason(finding)}
                  </small>
                  {/* The value itself. It is already visible in the textarea
                      above; hiding it here only made the panel unreadable,
                      especially on mobile where the panel covers the text. */}
                  <code className="smart-text-finding-value">{finding.value}</code>
                </div>

                <span className={`smart-text-sev ${SEVERITY_CLASS[finding.severity] ?? ""}`}>
                  {finding.severity}
                </span>
              </div>
            ))}
          </div>

          <p className="smart-text-note">
            Confidence is a rule-based estimate, not proof. Untick anything that is not a
            secret — it stays as ordinary text.
          </p>

          <button
            type="button"
            className="smart-text-primary"
            onClick={() => void protectSelected()}
            disabled={saving || selectedFindings.length === 0}
          >
            {saving ? <LoaderCircle size={13} className="spin" /> : <Lock size={13} />}
            Protect {selectedFindings.length} selected
          </button>
        </div>
      )}

      {scanned && findings.length === 0 && draft.trim() && (
        <p className="smart-text-note">
          Nothing detected. If a value here is a secret, select it and press{" "}
          <strong>Mark selection</strong>, then Scan again.
        </p>
      )}

      {error && <p className="smart-text-error">{error}</p>}
    </div>
  );
}

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

import { Eye, EyeOff, LoaderCircle, Lock, Save, ShieldAlert, X } from "lucide-react";
import { useMemo, useState } from "react";
import {
  applyPlaceholders,
  detectSecrets,
  placeholderFor,
  secretKeyFor,
  segmentText,
  type Finding,
} from "@/lib/secret-detector";
import { revealVaultSecret, writeVaultSecretsBatch, type NoteBlock } from "@/lib/api";

/** Vault folder for a note's secrets. Deleting the note can drop the folder. */
export function secretsPathFor(noteId: string): string {
  return `/notes/${noteId}`;
}

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
    </span>
  );
}

// --------------------------------------------------------------------------
// Editor — INSIDE the fieldset, so the block lock gates it as intended.
// --------------------------------------------------------------------------

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
  const [findings, setFindings] = useState<Finding[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const stored = useMemo(() => readStored(block), [block.data]);
  const selectedFindings = findings.filter((f) => f.selected);

  /** Scan the draft in the browser. Nothing is sent anywhere. */
  function scan(value: string) {
    setError("");
    setFindings(detectSecrets(value));
  }

  function toggleFinding(id: string, selected: boolean) {
    setFindings((current) => current.map((f) => (f.id === id ? { ...f, selected } : f)));
  }

  function selectAll(selected: boolean) {
    setFindings((current) => current.map((f) => ({ ...f, selected })));
  }

  /** Approve: write the ticked values to the vault, then placeholder them. */
  async function protectSelected() {
    if (selectedFindings.length === 0) return;
    setSaving(true);
    setError("");
    try {
      const items = selectedFindings.map((finding) => {
        const key = secretKeyFor(finding.label, finding.type);
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
          comment: item.finding.label,
        })),
        create_folder: true,
      });

      const newText = applyPlaceholders(
        draft,
        items.map((item) => ({
          start: item.finding.start,
          end: item.finding.end,
          placeholder: item.placeholder,
        })),
      );

      const newSecrets: StoredSecret[] = [
        ...stored,
        ...items.map((item) => ({
          placeholder: item.placeholder,
          key: item.key,
          label: item.finding.label,
          type: item.finding.type,
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
      await onSave(block.id, { text_content: draft, data: { ...block.data } });
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
        className="smart-text-input"
        value={draft}
        rows={12}
        spellCheck={false}
        placeholder={"Google account : abc@gmail.com\ngoogle password: ...\nrobot key : ..."}
        onChange={(event) => {
          setDraft(event.target.value);
          setFindings([]);
        }}
      />

      <div className="smart-text-actions">
        <button
          type="button"
          className="smart-text-primary"
          onClick={() => scan(draft)}
          disabled={saving || !draft.trim()}
        >
          <ShieldAlert size={13} />
          Scan for secrets
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
              <label key={finding.id} className="smart-text-finding">
                <input
                  type="checkbox"
                  checked={finding.selected}
                  onChange={(event) => toggleFinding(finding.id, event.target.checked)}
                />
                <span className="smart-text-finding-info">
                  <strong>{finding.label}</strong>
                  <small>
                    {finding.type.replace(/_/g, " ")} ·{" "}
                    {Math.round(finding.confidence * 100)}% confidence
                  </small>
                </span>
                <span className={`smart-text-sev ${SEVERITY_CLASS[finding.severity] ?? ""}`}>
                  {finding.severity}
                </span>
              </label>
            ))}
          </div>

          <p className="smart-text-note">
            Confidence is a rule-based estimate, not proof. Unticked values stay as ordinary
            text. Values are never shown back to you here.
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

      {findings.length === 0 && draft.trim() && (
        <p className="smart-text-note">
          No secrets detected yet — press Scan. Values you already protected appear as
          placeholders and are not re-detected.
        </p>
      )}

      {error && <p className="smart-text-error">{error}</p>}
    </div>
  );
}

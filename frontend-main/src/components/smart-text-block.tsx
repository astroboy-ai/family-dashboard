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

type Props = {
  block: NoteBlock;
  noteId: string;
  /** Persist new text_content + data. Supplied by the note page. */
  onSave: (blockId: string, patch: { text_content: string; data: Record<string, unknown> }) => Promise<void>;
};

type StoredSecret = {
  placeholder: string;
  key: string;
  label: string;
  type: string;
  severity: string;
};

export function SmartTextBlockView({ block, noteId, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(block.text_content ?? "");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [scanning, setScanning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  // Which secret keys the user has chosen to reveal, and their values. Revealed
  // values are held in memory only — never written back to the note.
  const [revealed, setRevealed] = useState<Record<string, string>>({});
  const [revealing, setRevealing] = useState<string | null>(null);

  const text = block.text_content ?? "";
  const stored = useMemo<StoredSecret[]>(() => {
    const raw = (block.data?.secrets as StoredSecret[] | undefined) ?? [];
    return Array.isArray(raw) ? raw : [];
  }, [block.data]);

  const segments = useMemo(() => segmentText(text), [text]);
  const secretByPlaceholder = useMemo(() => {
    const map = new Map<string, StoredSecret>();
    for (const item of stored) map.set(item.placeholder, item);
    return map;
  }, [stored]);

  /** Scan the draft in the browser. Nothing is sent anywhere. */
  function scan(value: string) {
    setScanning(true);
    setError("");
    setMessage("");
    try {
      setFindings(detectSecrets(value));
    } finally {
      setScanning(false);
    }
  }

  function toggleFinding(id: string, selected: boolean) {
    setFindings((current) =>
      current.map((f) => (f.id === id ? { ...f, selected } : f)),
    );
  }

  function selectAll(selected: boolean) {
    setFindings((current) => current.map((f) => ({ ...f, selected })));
  }

  const selectedFindings = findings.filter((f) => f.selected);

  /** Approve: write the ticked values to the vault, then placeholder them. */
  async function protectSelected() {
    if (selectedFindings.length === 0) return;
    setSaving(true);
    setError("");
    setMessage("");
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

      // The server may normalise the folder; trust what it reports.
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

      setDraft(newText);
      setFindings(detectSecrets(newText));
      setMessage(
        `${items.length} secret${items.length === 1 ? "" : "s"} protected in ${result.path}`,
      );
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
      setEditing(false);
      setFindings([]);
      setMessage("Saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

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

  const startEditing = () => {
    setDraft(text);
    setEditing(true);
    setMessage("");
    setError("");
  };

  const cancelEditing = () => {
    setEditing(false);
    setFindings([]);
    setDraft(text);
    setError("");
  };

  // ---------------------------------------------------------------- read view

  if (!editing) {
    return (
      <div className="smart-text">
        <div className="smart-text-body">
          {segments.length === 0 && (
            <p className="smart-text-empty">Empty. Click Edit and paste your text.</p>
          )}
          {segments.map((segment, index) =>
            segment.kind === "text" ? (
              <span key={index} className="smart-text-run">
                {segment.value}
              </span>
            ) : (
              <SecretChip
                key={index}
                meta={secretByPlaceholder.get(segment.raw)}
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
          <button type="button" className="smart-text-edit" onClick={startEditing}>
            Edit
          </button>
        </div>

        {error && <p className="smart-text-error">{error}</p>}
        {message && <p className="smart-text-message">{message}</p>}
      </div>
    );
  }

  // --------------------------------------------------------------- edit view

  return (
    <div className="smart-text smart-text-editing">
      <div className="smart-text-hint">
        <Lock size={12} /> Paste anything. Detection runs in this browser — nothing is
        sent to a server or an AI until you approve.
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
          setMessage("");
        }}
      />

      <div className="smart-text-actions">
        <button
          type="button"
          className="smart-text-primary"
          onClick={() => scan(draft)}
          disabled={scanning || !draft.trim()}
        >
          {scanning ? <LoaderCircle size={13} className="spin" /> : <ShieldAlert size={13} />}
          Scan for secrets
        </button>
        <button type="button" className="smart-text-secondary" onClick={() => void savePlain()} disabled={saving}>
          {saving ? <LoaderCircle size={13} className="spin" /> : <Save size={13} />}
          Save as plain text
        </button>
        <button type="button" className="smart-text-secondary" onClick={cancelEditing} disabled={saving}>
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
            Confidence is a rule-based estimate, not proof. Unticked values stay as
            ordinary text. Values are never shown back to you here.
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
          No secrets detected yet — press Scan. If you have already protected values,
          they appear as placeholders and are not re-detected.
        </p>
      )}

      {error && <p className="smart-text-error">{error}</p>}
      {message && <p className="smart-text-message">{message}</p>}
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
        {busy ? <LoaderCircle size={11} className="spin" /> : shown ? <EyeOff size={11} /> : <Eye size={11} />}
      </button>
    </span>
  );
}

"use client";

import { Eye, EyeOff, KeyRound, LoaderCircle, Lock, Plus, Save, ShieldCheck, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { confirmDialog } from "@/components/confirm-dialog";
import {
  deleteVaultSecret,
  getActor,
  listVaultFolders,
  listVaultSecrets,
  revealVaultSecret,
  writeVaultSecret,
  type Actor,
  type VaultSecret,
} from "@/lib/api";

type PasswordBlock = {
  id: string;
  note_id: string;
  note_title: string | null;
  label: string | null;
  encrypted: boolean;
  masked: boolean;
  created_at: string;
  updated_at: string;
};

type PasswordBlockDetail = PasswordBlock & {
  value: string | null;
};

/**
 * The secrets editor.
 *
 * Deliberately a key box and a value box, with no type dropdown: every value in
 * the store is a string, and a PEM certificate or an SSH private key is a
 * multi-line string that a textarea already holds faithfully. A type picker
 * would only add a field the API does not use.
 */
function SecretEditor({
  folders,
  editing,
  onSaved,
  onCancel,
}: {
  folders: string[];
  editing: VaultSecret | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [key, setKey] = useState(editing?.key ?? "");
  const [value, setValue] = useState("");
  const [path, setPath] = useState(editing?.path ?? "/");
  const [comment, setComment] = useState(editing?.comment ?? "");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setKey(editing?.key ?? "");
    setPath(editing?.path ?? "/");
    setComment(editing?.comment ?? "");
    setValue("");
    setError("");
    setSaved(false);
  }, [editing]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setSaved(false);
    try {
      await writeVaultSecret({
        key: key.trim(),
        value,
        path,
        comment: comment.trim(),
      });
      setSaved(true);
      setValue("");
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save the secret.");
    } finally {
      setPending(false);
    }
  }

  return (
    <form className="vault-editor" onSubmit={submit} noValidate>
      <div className="vault-editor-head">
        <h3>{editing ? `Update ${editing.key}` : "New secret"}</h3>
        {editing && (
          <button type="button" className="icon-button" onClick={onCancel} aria-label="Cancel edit">
            <X size={16} />
          </button>
        )}
      </div>

      <label className="field">
        <span>Key</span>
        <input
          type="text"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="AZURE_AI_API_KEY"
          readOnly={Boolean(editing)}
          autoComplete="off"
          spellCheck={false}
          required
        />
      </label>

      <label className="field">
        <span>Folder</span>
        <select value={path} onChange={(e) => setPath(e.target.value)}>
          {folders.map((folder) => (
            <option key={folder} value={folder}>
              {folder}
            </option>
          ))}
        </select>
      </label>

      <label className="field">
        <span>
          Value
          {editing && <em> (leave blank to keep the current value)</em>}
        </span>
        <textarea
          className="vault-value-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={"Paste the token, key or certificate.\nMulti-line values are kept exactly as typed."}
          rows={6}
          autoComplete="off"
          spellCheck={false}
        />
      </label>

      <label className="field">
        <span>Comment <em>(optional)</em></span>
        <input
          type="text"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="What this is for"
          autoComplete="off"
        />
      </label>

      {error && <div className="form-error">{error}</div>}
      {saved && <div className="form-success">Saved.</div>}

      <div className="settings-actions">
        <button
          type="submit"
          className="primary-button"
          disabled={pending || !key.trim() || (!editing && !value)}
        >
          {pending ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}
          {pending ? "Saving…" : editing ? "Update secret" : "Save secret"}
        </button>
      </div>
    </form>
  );
}

export default function VaultPage() {
  const [actor, setActor] = useState<Actor | null>(null);
  const [blocks, setBlocks] = useState<PasswordBlock[]>([]);
  const [consoleUrl, setConsoleUrl] = useState("");
  const [selected, setSelected] = useState<PasswordBlockDetail | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Secrets section
  const [secrets, setSecrets] = useState<VaultSecret[]>([]);
  const [folders, setFolders] = useState<string[]>(["/"]);
  const [secretsLoading, setSecretsLoading] = useState(true);
  const [secretsError, setSecretsError] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<VaultSecret | null>(null);
  const [revealedValues, setRevealedValues] = useState<Record<string, string>>({});
  const [revealingKey, setRevealingKey] = useState("");
  const [deletingKey, setDeletingKey] = useState("");

  useEffect(() => {
    getActor()
      .then(setActor)
      .catch(() => setActor(null));
  }, []);

  useEffect(() => {
    if (!actor) return;
    fetch("/api/vault/console", { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { public_url?: string } | null) => {
        if (data?.public_url) setConsoleUrl(data.public_url);
      })
      .catch(() => {});
  }, [actor]);

  const loadSecrets = useCallback(async () => {
    setSecretsLoading(true);
    setSecretsError("");
    try {
      const [items, paths] = await Promise.all([listVaultSecrets("/"), listVaultFolders()]);
      setSecrets(items);
      setFolders(paths.length ? paths : ["/"]);
    } catch (reason) {
      setSecretsError(reason instanceof Error ? reason.message : "Unable to load secrets.");
    } finally {
      setSecretsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!actor) return;
    void loadSecrets();
  }, [actor, loadSecrets]);

  useEffect(() => {
    if (!actor) return;
    setLoading(true);
    fetch("/api/vault/password-blocks", { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<PasswordBlock[]>;
      })
      .then(setBlocks)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Failed to load vault."))
      .finally(() => setLoading(false));
  }, [actor]);

  async function viewBlock(block: PasswordBlock) {
    setRevealed(false);
    try {
      const res = await fetch(`/api/vault/password-blocks/${block.id}`, { credentials: "include" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const detail = (await res.json()) as PasswordBlockDetail;
      setSelected(detail);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Failed to load block.");
    }
  }

  async function toggleReveal(secret: VaultSecret) {
    if (revealedValues[secret.key] !== undefined) {
      setRevealedValues((prev) => {
        const next = { ...prev };
        delete next[secret.key];
        return next;
      });
      return;
    }
    setRevealingKey(secret.key);
    setSecretsError("");
    try {
      const result = await revealVaultSecret(secret.key, secret.path);
      setRevealedValues((prev) => ({ ...prev, [secret.key]: result.value }));
    } catch (reason) {
      setSecretsError(reason instanceof Error ? reason.message : "Unable to reveal the secret.");
    } finally {
      setRevealingKey("");
    }
  }

  async function removeSecret(secret: VaultSecret) {
    const confirmed = await confirmDialog({
      title: `Delete ${secret.key}?`,
      message: "This removes the secret from your household vault. It cannot be undone.",
      confirmLabel: "Delete secret",
    });
    if (!confirmed) return;
    setDeletingKey(secret.key);
    setSecretsError("");
    try {
      await deleteVaultSecret(secret.key, secret.path);
      setRevealedValues((prev) => {
        const next = { ...prev };
        delete next[secret.key];
        return next;
      });
      await loadSecrets();
    } catch (reason) {
      setSecretsError(reason instanceof Error ? reason.message : "Unable to delete the secret.");
    } finally {
      setDeletingKey("");
    }
  }

  return (
    <div className="page-wrap">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">SECURITY</p>
          <h1>Vault</h1>
          <p className="page-subtitle">Tokens, keys and credentials for this household.</p>
        </div>
      </section>

      {error && <div className="inline-state" role="alert">{error}</div>}

      <section className="vault-secrets-section">
        <div className="vault-secrets-head">
          <div>
            <h2>Secrets</h2>
            <p className="muted">
              Stored in Infisical. Values are only fetched when you reveal one.
            </p>
          </div>
          <div className="inline-actions">
            {consoleUrl && (
              <a className="secondary-button" href={consoleUrl} target="_blank" rel="noreferrer">
                <ShieldCheck size={14} /> Open Infisical
              </a>
            )}
            <button
              type="button"
              className="primary-button"
              onClick={() => { setEditing(null); setEditorOpen(true); }}
            >
              <Plus size={16} /> New secret
            </button>
          </div>
        </div>

        {secretsError && <div className="form-error">{secretsError}</div>}

        {editorOpen && (
          <SecretEditor
            folders={folders}
            editing={editing}
            onSaved={() => { setEditorOpen(false); setEditing(null); void loadSecrets(); }}
            onCancel={() => { setEditorOpen(false); setEditing(null); }}
          />
        )}

        {secretsLoading ? (
          <div className="loading-rows"><i /><i /><i /></div>
        ) : secrets.length === 0 ? (
          <div className="empty-state">
            <span className="empty-mark"><KeyRound size={24} /></span>
            <strong>No secrets yet</strong>
            <p>Add one with “New secret”. It is stored in Infisical, not in the database.</p>
          </div>
        ) : (
          <ul className="vault-secret-list">
            {secrets.map((secret) => {
              const shown = revealedValues[secret.key];
              const isRevealed = shown !== undefined;
              return (
                <li key={`${secret.path}:${secret.key}`} className="vault-secret-row">
                  <div className="vault-secret-main">
                    <div className="vault-secret-name">
                      <KeyRound size={14} />
                      <strong>{secret.key}</strong>
                      {secret.path !== "/" && <span className="vault-secret-path">{secret.path}</span>}
                    </div>
                    {secret.comment && <p className="vault-secret-comment">{secret.comment}</p>}
                    <code className="vault-secret-value">
                      {isRevealed ? shown : "••••••••••••"}
                    </code>
                  </div>
                  <div className="inline-actions">
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void toggleReveal(secret)}
                      disabled={revealingKey === secret.key}
                    >
                      {revealingKey === secret.key
                        ? <LoaderCircle size={14} className="spin" />
                        : isRevealed ? <EyeOff size={14} /> : <Eye size={14} />}
                      {isRevealed ? "Hide" : "Reveal"}
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => { setEditing(secret); setEditorOpen(true); }}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => void removeSecret(secret)}
                      disabled={deletingKey === secret.key}
                      aria-label={`Delete ${secret.key}`}
                    >
                      {deletingKey === secret.key
                        ? <LoaderCircle size={14} className="spin" />
                        : <Trash2 size={14} />}
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section className="list-results">
        <h2 className="vault-section-title">Password blocks in notes</h2>
        {loading ? (
          <div className="loading-rows"><i /><i /><i /></div>
        ) : blocks.length === 0 ? (
          <div className="empty-state">
            <span className="empty-mark"><Lock size={24} /></span>
            <strong>No password blocks</strong>
            <p>Add a password block to any note to see it here.</p>
          </div>
        ) : (
          <div className="vault-grid">
            {blocks.map((block) => (
              <button
                key={block.id}
                className="vault-card"
                onClick={() => viewBlock(block)}
              >
                <div className="vault-card-head">
                  <Lock size={16} />
                  <strong>{block.label || block.note_title || "Password"}</strong>
                </div>
                <div className="vault-card-meta">
                  <span>{block.note_title || "Unknown note"}</span>
                  <span className={block.encrypted ? "vault-badge vault-badge-encrypted" : "vault-badge vault-badge-plaintext"}>
                    {block.encrypted ? "Encrypted" : "Plaintext"}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {selected && (
        <div className="text-overlay" role="dialog" aria-modal="true" aria-label="Password detail" onClick={() => setSelected(null)}>
          <div className="text-overlay-card" onClick={(event) => event.stopPropagation()}>
            <div className="text-overlay-head">
              <strong>{selected.label || selected.note_title || "Password"}</strong>
              <div className="inline-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setRevealed((v) => !v)}
                >
                  {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
                  {revealed ? "Hide" : "Reveal"}
                </button>
                <button className="icon-button" onClick={() => setSelected(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="vault-detail-body">
              <div className="vault-detail-row">
                <span className="vault-detail-label">Note</span>
                <span>{selected.note_title || "Unknown"}</span>
              </div>
              <div className="vault-detail-row">
                <span className="vault-detail-label">Encryption</span>
                <span className={selected.encrypted ? "vault-badge vault-badge-encrypted" : "vault-badge vault-badge-plaintext"}>
                  {selected.encrypted ? "AES-256-GCM" : "Plaintext"}
                </span>
              </div>
              <div className="vault-detail-row">
                <span className="vault-detail-label">Value</span>
                <span className="vault-detail-value">
                  {revealed ? (selected.value || "••••••••") : "••••••••"}
                </span>
              </div>
              <div className="vault-detail-row">
                <span className="vault-detail-label">Created</span>
                <span>{new Date(selected.created_at).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

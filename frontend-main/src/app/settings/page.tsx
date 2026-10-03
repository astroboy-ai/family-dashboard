"use client";

import { LoaderCircle, Save, ShieldCheck } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { getActor, getAdminSettings, patchAdminSettings, reembedAll, type Actor } from "@/lib/api";

type Settings = {
  enabled: boolean;
  base_url: string;
  api_key_set: boolean;
  embedding_model: string;
  embedding_dim: number;
  embedding_batch_size: number;
  llm_model: string;
  vision_model: string;
};

export default function SettingsPage() {
  const [actor, setActor] = useState<Actor | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [enabled, setEnabled] = useState(true);
  const [baseUrl, setBaseUrl] = useState("http://litellm_proxy:4000");
  const [apiKey, setApiKey] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("gemini/text-embedding-004");
  const [embeddingDim, setEmbeddingDim] = useState(768);
  const [embeddingBatchSize, setEmbeddingBatchSize] = useState(16);
  const [llmModel, setLlmModel] = useState("gemini/gemini-3.5-flash");
  const [visionModel, setVisionModel] = useState("");
  const [pending, setPending] = useState(false);
  const [reembedPending, setReembedPending] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let active = true;
    getActor()
      .then((value) => { if (active) setActor(value); })
      .catch(() => {});
    getAdminSettings()
      .then((value) => {
        if (!active) return;
        setSettings(value);
        setEnabled(value.enabled);
        setBaseUrl(value.base_url);
        setEmbeddingModel(value.embedding_model);
        setEmbeddingDim(value.embedding_dim);
        setEmbeddingBatchSize(value.embedding_batch_size);
        setLlmModel(value.llm_model);
        setVisionModel(value.vision_model);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load settings.");
      });
    return () => { active = false; };
  }, []);

  const isParent = actor?.role === "parent";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    setSaved(false);
    try {
      const result = await patchAdminSettings({
        enabled,
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || undefined,
        embedding_model: embeddingModel.trim(),
        embedding_dim: embeddingDim,
        embedding_batch_size: embeddingBatchSize,
        llm_model: llmModel.trim(),
        vision_model: visionModel.trim() || undefined,
      });
      setSaved(true);
      setApiKey("");
      if (result.ai) {
        setSettings(result.ai);
        setEnabled(result.ai.enabled);
        setBaseUrl(result.ai.base_url);
        setEmbeddingModel(result.ai.embedding_model);
        setEmbeddingDim(result.ai.embedding_dim);
        setEmbeddingBatchSize(result.ai.embedding_batch_size);
        setLlmModel(result.ai.llm_model);
        setVisionModel(result.ai.vision_model);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save settings.");
    } finally {
      setPending(false);
    }
  }

  async function triggerReembed() {
    setReembedPending(true);
    setError("");
    try {
      await reembedAll();
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to start re-embed.");
    } finally {
      setReembedPending(false);
    }
  }

  if (!isParent) {
    return (
      <main className="page-wrap">
        <div className="settings-block">
          <p className="eyebrow">ACCESS RESTRICTED</p>
          <h1>Parent role required</h1>
          <p className="muted">Only parent accounts can change AI settings.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="page-wrap">
      <div className="settings-block">
        <p className="eyebrow">ADMINISTRATION</p>
        <h1>AI & Embedding Settings</h1>
        <p className="muted">Configure the LLM gateway and embedding model. Changes apply immediately — no restart needed.</p>
      </div>

      {error && <div className="form-error">{error}</div>}
      {saved && <div className="form-success">Settings saved.</div>}

      <form onSubmit={submit} className="settings-form">
        <section className="settings-section">
          <h2>Gateway</h2>
          <label className="field">
            <span>Enabled</span>
            <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          </label>
          <label className="field">
            <span>Base URL</span>
            <input type="url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://litellm_proxy:4000" />
          </label>
          <label className="field">
            <span>API Key {settings?.api_key_set && <em>(set — leave blank to keep)</em>}</span>
            <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." autoComplete="off" />
          </label>
        </section>

        <section className="settings-section">
          <h2>Embedding</h2>
          <label className="field">
            <span>Model</span>
            <input type="text" value={embeddingModel} onChange={(e) => setEmbeddingModel(e.target.value)} placeholder="gemini/text-embedding-004" />
          </label>
          <label className="field">
            <span>Dimensions</span>
            <input type="number" min={1} max={8192} value={embeddingDim} onChange={(e) => setEmbeddingDim(Number(e.target.value))} />
          </label>
          <label className="field">
            <span>Batch Size</span>
            <input type="number" min={1} max={256} value={embeddingBatchSize} onChange={(e) => setEmbeddingBatchSize(Number(e.target.value))} />
          </label>
        </section>

        <section className="settings-section">
          <h2>LLM</h2>
          <label className="field">
            <span>Chat Model</span>
            <input type="text" value={llmModel} onChange={(e) => setLlmModel(e.target.value)} placeholder="gemini/gemini-3.5-flash" />
          </label>
          <label className="field">
            <span>Vision Model (optional)</span>
            <input type="text" value={visionModel} onChange={(e) => setVisionModel(e.target.value)} placeholder="" />
          </label>
        </section>

        <div className="settings-actions">
          <button type="submit" className="primary-button" disabled={pending}>
            {pending ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />}
            {pending ? "Saving…" : "Save settings"}
          </button>
          <button type="button" className="secondary-button" onClick={triggerReembed} disabled={reembedPending}>
            {reembedPending ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />}
            {reembedPending ? "Re-embedding…" : "Re-embed all notes"}
          </button>
        </div>
      </form>
    </main>
  );
}

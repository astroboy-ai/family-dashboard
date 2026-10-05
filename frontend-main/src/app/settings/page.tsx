"use client";

import { CheckCircle2, LoaderCircle, RefreshCw, Save, ShieldCheck, TriangleAlert, Upload } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  getActor,
  getAdminSettings,
  listGatewayModels,
  patchAdminSettings,
  reembedAll,
  testStorageSettings,
  type Actor,
  type GatewayModel,
  type StorageTestResult,
} from "@/lib/api";

type Settings = {
  enabled: boolean;
  base_url: string;
  api_key_set: boolean;
  embedding_model: string;
  embedding_dim: number;
  embedding_batch_size: number;
  llm_model: string;
  vision_model: string;
  tagging_model: string;
  effective_tagging_model: string;
};

/**
 * A model picker backed by the live gateway catalog.
 *
 * Renders a <select> of the models whose `mode` matches, and keeps the current
 * value selectable even when it is absent from the catalog — otherwise opening
 * the page with a model the gateway no longer lists would silently reset the
 * setting to the first option on save.
 */
function ModelSelect({
  label,
  hint,
  value,
  onChange,
  models,
  catalogOk,
  placeholder,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (next: string) => void;
  models: GatewayModel[];
  catalogOk: boolean;
  placeholder?: string;
}) {
  const missing = value !== "" && !models.some((m) => m.id === value);
  const options = missing ? [{ id: value, mode: "", max_input_tokens: null, max_output_tokens: null }, ...models] : models;

  return (
    <label className="field">
      <span>
        {label} {hint && <em>{hint}</em>}
      </span>
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={!catalogOk && options.length === 0}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((model) => (
          <option key={model.id} value={model.id}>
            {model.id}
            {model.max_input_tokens ? ` (${Math.round(model.max_input_tokens / 1000)}k in)` : ""}
            {model.id === value && missing ? " — not in catalog" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

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
  const [taggingModel, setTaggingModel] = useState("");

  // Live model catalog from the gateway (drives the dropdowns)
  const [catalog, setCatalog] = useState<Record<string, GatewayModel[]>>({});
  const [catalogOk, setCatalogOk] = useState(false);
  const [catalogError, setCatalogError] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(false);

  // Storage section
  const [publicEndpoint, setPublicEndpoint] = useState("");
  const [bucket, setBucket] = useState("");
  const [region, setRegion] = useState("");
  const [browserReachable, setBrowserReachable] = useState(true);
  const [testResult, setTestResult] = useState<StorageTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [probing, setProbing] = useState(false);

  const [pending, setPending] = useState(false);
  const [reembedPending, setReembedPending] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError("");
    try {
      const value = await listGatewayModels();
      setCatalog(value.groups ?? {});
      setCatalogOk(value.ok);
      if (!value.ok) setCatalogError(value.error ?? "Gateway did not return a model list.");
    } catch (reason) {
      setCatalogOk(false);
      setCatalog({});
      setCatalogError(reason instanceof Error ? reason.message : "Unable to reach the gateway.");
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    getActor()
      .then((value) => { if (active) setActor(value); })
      .catch(() => {});
    getAdminSettings()
      .then((value) => {
        if (!active) return;
        setSettings(value.ai);
        setEnabled(value.ai.enabled);
        setBaseUrl(value.ai.base_url);
        setEmbeddingModel(value.ai.embedding_model);
        setEmbeddingDim(value.ai.embedding_dim);
        setEmbeddingBatchSize(value.ai.embedding_batch_size);
        setLlmModel(value.ai.llm_model);
        setVisionModel(value.ai.vision_model);
        setTaggingModel(value.ai.tagging_model);
        if (value.storage) {
          setPublicEndpoint(value.storage.public_endpoint);
          setBucket(value.storage.bucket);
          setRegion(value.storage.region);
          setBrowserReachable(value.storage.browser_reachable);
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load settings.");
      });
    void loadCatalog();
    return () => { active = false; };
  }, [loadCatalog]);

  const isParent = actor?.role === "parent";

  function applyResponse(value: Awaited<ReturnType<typeof patchAdminSettings>>) {
    if (value.ai) {
      setSettings(value.ai);
      setEnabled(value.ai.enabled);
      setBaseUrl(value.ai.base_url);
      setEmbeddingModel(value.ai.embedding_model);
      setEmbeddingDim(value.ai.embedding_dim);
      setEmbeddingBatchSize(value.ai.embedding_batch_size);
      setLlmModel(value.ai.llm_model);
      setVisionModel(value.ai.vision_model);
      setTaggingModel(value.ai.tagging_model);
    }
    if (value.storage) {
      setPublicEndpoint(value.storage.public_endpoint);
      setBucket(value.storage.bucket);
      setRegion(value.storage.region);
      setBrowserReachable(value.storage.browser_reachable);
    }
  }

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
        tagging_model: taggingModel.trim() || undefined,
        storage: {
          public_endpoint: publicEndpoint.trim(),
          bucket: bucket.trim(),
          region: region.trim(),
        },
      });
      setSaved(true);
      setApiKey("");
      applyResponse(result);
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

  /** Ask the backend to sign a probe URL against the saved upload origin. */
  async function runStorageTest() {
    setTesting(true);
    setTestResult(null);
    setError("");
    try {
      setTestResult(await testStorageSettings());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to test storage.");
    } finally {
      setTesting(false);
    }
  }

  /**
   * PUT a 1-byte probe to the signed URL from the browser.
   *
   * This is the step that actually proves the tunnel works: the backend can sign
   * a URL for an origin it can reach, but only the browser knows whether *it*
   * can. A loopback endpoint signs fine and still fails here.
   */
  async function runBrowserProbe() {
    if (!testResult?.upload_url) return;
    setProbing(true);
    setError("");
    try {
      const response = await fetch(testResult.upload_url, {
        method: "PUT",
        headers: { "Content-Type": "text/plain" },
        body: "familyos-probe",
      });
      setTestResult({
        ...testResult,
        warnings: response.ok
          ? ["Browser upload probe succeeded — uploads will go direct to storage."]
          : [`Browser upload probe failed with HTTP ${response.status}.`],
        ok: testResult.ok && response.ok,
      });
    } catch (reason) {
      setTestResult({
        ...testResult,
        ok: false,
        warnings: [
          `Browser upload probe failed: ${reason instanceof Error ? reason.message : "network error"}. ` +
            "Uploads will use the relay endpoint until this works.",
        ],
      });
    } finally {
      setProbing(false);
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
        <h1>AI, Embedding & Storage Settings</h1>
        <p className="muted">Changes apply immediately — no restart needed.</p>
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
          <h2>
            Embedding
            <button type="button" className="catalog-refresh" onClick={() => void loadCatalog()} disabled={catalogLoading} title="Reload the model list from the gateway">
              <RefreshCw size={12} className={catalogLoading ? "spin" : ""} />
            </button>
          </h2>
          {!catalogOk && catalogError && (
            <p className="section-warning">
              Model list unavailable ({catalogError}). The current value is kept; reload to pick a different model.
            </p>
          )}
          <ModelSelect
            label="Model"
            value={embeddingModel}
            onChange={setEmbeddingModel}
            models={catalog.embedding ?? []}
            catalogOk={catalogOk}
          />
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
          {!catalogOk && catalogError && (
            <p className="section-warning">Model list unavailable ({catalogError}).</p>
          )}
          <ModelSelect
            label="Chat Model"
            value={llmModel}
            onChange={setLlmModel}
            models={catalog.chat ?? []}
            catalogOk={catalogOk}
          />
          <ModelSelect
            label="Tagging Model"
            hint="(note classification — falls back to Chat Model)"
            value={taggingModel}
            onChange={setTaggingModel}
            models={catalog.chat ?? []}
            catalogOk={catalogOk}
            placeholder="Use Chat Model"
          />
          <ModelSelect
            label="Vision Model"
            hint="(optional — image analysis)"
            value={visionModel}
            onChange={setVisionModel}
            models={[...(catalog.chat ?? []), ...(catalog.vision ?? [])]}
            catalogOk={catalogOk}
            placeholder="Use Chat Model"
          />
        </section>

        <section className="settings-section">
          <h2>Storage</h2>
          <p className="section-hint">
            The public origin the browser uploads to. Must be an HTTPS hostname reachable from the
            internet — a Cloudflare tunnel route such as <code>https://media.example.com</code>.
            Until it is set, uploads use the slower relay endpoint.
          </p>
          {!browserReachable && (
            <p className="inline-warning">
              <TriangleAlert size={14} /> Current origin is a loopback address, so browser uploads
              will fall back to the relay.
            </p>
          )}
          <label className="field">
            <span>Public Upload Endpoint</span>
            <input
              type="url"
              value={publicEndpoint}
              onChange={(e) => setPublicEndpoint(e.target.value)}
              placeholder="https://media.logeebox.com"
            />
          </label>
          <label className="field">
            <span>Bucket</span>
            <input type="text" value={bucket} onChange={(e) => setBucket(e.target.value)} placeholder="familyos-media" />
          </label>
          <label className="field">
            <span>Region</span>
            <input type="text" value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1" />
          </label>

          <div className="storage-test-row">
            <button type="button" className="secondary-button" onClick={() => void runStorageTest()} disabled={testing}>
              {testing ? <LoaderCircle size={16} className="spin" /> : <ShieldCheck size={16} />}
              {testing ? "Testing…" : "Test storage"}
            </button>
            {testResult?.upload_url && (
              <button type="button" className="secondary-button" onClick={() => void runBrowserProbe()} disabled={probing}>
                {probing ? <LoaderCircle size={16} className="spin" /> : <Upload size={16} />}
                {probing ? "Probing…" : "Test browser upload"}
              </button>
            )}
          </div>

          {testResult && (
            <div className={testResult.ok ? "storage-result ok" : "storage-result warn"}>
              <p className="storage-result-head">
                {testResult.ok ? <CheckCircle2 size={15} /> : <TriangleAlert size={15} />}
                {testResult.ok ? "Storage looks good" : "Storage needs attention"}
              </p>
              <ul>
                <li>Endpoint: <code>{testResult.public_endpoint}</code></li>
                <li>Bucket: <code>{testResult.bucket}</code></li>
                <li>Browser-reachable: {testResult.browser_reachable ? "yes" : "no"}</li>
                <li>Internal storage: {testResult.internal_ok === false ? "unreachable" : "ok"}</li>
              </ul>
              {testResult.warnings.map((warning) => (
                <p className="storage-warning" key={warning}>{warning}</p>
              ))}
            </div>
          )}
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

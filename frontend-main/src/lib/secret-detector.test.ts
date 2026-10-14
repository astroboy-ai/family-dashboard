// Regression tests for the smart-text detector (URLs + secret tags).
//
// Run with:  node --test src/lib/secret-detector.test.ts
//
// Node strips the TypeScript types natively, so this needs no test framework
// and no build step. The detector is pure string handling, which is exactly
// the kind of logic that breaks silently in the browser — the URL work shipped
// four bugs that only surfaced when this file existed.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  detectSecrets,
  maskMagicSpans,
  segmentText,
  stripMagicTags,
} from "./secret-detector.ts";

/** The hrefs of every URL segment in `text`. */
function urls(text: string): string[] {
  return segmentText(text)
    .filter((s) => s.kind === "url")
    .map((s) => s.href);
}

/** The [href, raw] pairs of every URL segment in `text`. */
function urlPairs(text: string): Array<[string, string]> {
  return segmentText(text)
    .filter((s) => s.kind === "url")
    .map((s) => [s.href, s.raw]);
}

test("auto-detects an https URL", () => {
  assert.deepEqual(urls("Check https://familyos.logeebox.com/notes for details"), [
    "https://familyos.logeebox.com/notes",
  ]);
});

test("auto-detects a www URL and gives it a scheme", () => {
  assert.deepEqual(urls("Go to www.example.com now"), ["https://www.example.com"]);
});

test("trims sentence punctuation off a detected URL", () => {
  assert.deepEqual(urls("See https://example.com/page."), ["https://example.com/page"]);
  assert.deepEqual(urls("a https://x.com, b"), ["https://x.com"]);
});

test("trims an unbalanced closing paren but keeps a balanced one", () => {
  assert.deepEqual(urls("read [docs](https://example.com) here"), ["https://example.com"]);
  assert.deepEqual(urls("see https://en.wikipedia.org/wiki/Foo_(bar) ok"), [
    "https://en.wikipedia.org/wiki/Foo_(bar)",
  ]);
});

test("finds several URLs in one line", () => {
  assert.deepEqual(urls("a https://one.com b https://two.com"), [
    "https://one.com",
    "https://two.com",
  ]);
});

test("does not auto-detect a bare domain", () => {
  // `example.com` is too easy to hit by accident in prose; the magic tag is
  // the escape hatch for it.
  assert.deepEqual(urls("visit example.com please"), []);
});

test("honours a plain URL magic tag", () => {
  assert.deepEqual(urls("link [[url:https://example.com]] here"), ["https://example.com"]);
});

test("honours a labelled URL magic tag and keeps the label for display", () => {
  assert.deepEqual(urlPairs("link [[url:FamilyOS|https://familyos.logeebox.com]] here"), [
    ["https://familyos.logeebox.com", "FamilyOS"],
  ]);
});

test("promotes a bare domain inside a magic tag", () => {
  assert.deepEqual(urls("[[url:example.com]]"), ["https://example.com"]);
  assert.deepEqual(urls("[[url:www.example.com]]"), ["https://www.example.com"]);
});

test("saving turns a URL tag into the text the reader sees", () => {
  assert.equal(stripMagicTags("link [[url:https://example.com]] here"), "link https://example.com here");
  assert.equal(
    stripMagicTags("link [[url:FamilyOS|https://familyos.logeebox.com]] here"),
    "link FamilyOS here",
  );
});

test("saving keeps a secret tag's value", () => {
  assert.equal(stripMagicTags("k [[secret:name]]abc123[[/secret]] end"), "k abc123 end");
  assert.equal(stripMagicTags("k [[secret]]abc123[[/secret]] end"), "k abc123 end");
});

test("an unclosed URL marker is dropped rather than left in the note", () => {
  assert.equal(stripMagicTags("oops [[url: end"), "oops  end");
});

test("a secret tag is never mistaken for a URL", () => {
  assert.deepEqual(urls("key is [[secret:sn-test-abc]]"), []);
  assert.deepEqual(urls("[[secret:sn-http-abc]]"), []);
});

test("a URL and a secret tag coexist on one line", () => {
  assert.deepEqual(urls("site https://x.com key [[secret:sn-abc]]"), ["https://x.com"]);
});

test("maskMagicSpans blanks both tag kinds and preserves offsets", () => {
  const secretText = "k [[secret]]abc[[/secret]]";
  assert.equal(maskMagicSpans(secretText).includes("abc"), false);
  assert.equal(maskMagicSpans(secretText).length, secretText.length);

  const urlText = "[[url:https://x.com]]";
  assert.equal(maskMagicSpans(urlText).includes("https"), false);
  assert.equal(maskMagicSpans(urlText).length, urlText.length);
});

test("detectSecrets still finds a real key", () => {
  assert.ok(detectSecrets("api_key = sk-live-abcdefghijklmnopqrstuvwxyz123456").length > 0);
});

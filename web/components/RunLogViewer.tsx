"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { DEV_TOKEN, runLogsUrl } from "../lib/api";

interface LogLine {
  id: number;
  t: string;
  line: string;
}

/** One parsed SSE data payload from the log stream. */
interface LogEvent {
  t?: unknown;
  line?: unknown;
  done?: unknown;
}

const MAX_LINES = 5000;

/** Split a raw SSE byte buffer into complete events, keeping the leftover. */
function splitSseEvents(buffer: string): { events: string[]; rest: string } {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop() ?? "";
  return { events: parts, rest };
}

/** Parse the `data:` payloads of one SSE event block. */
function parseSseEvent(block: string): LogEvent[] {
  const out: LogEvent[] = [];
  for (const rawLine of block.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (!line.startsWith("data:")) continue;
    const payload = line.slice(5).trim();
    if (payload === "") continue;
    try {
      const parsed: unknown = JSON.parse(payload);
      if (typeof parsed === "object" && parsed !== null) {
        const rec = parsed as Record<string, unknown>;
        out.push({ t: rec.t, line: rec.line, done: rec.done });
      }
    } catch {
      // Malformed payloads are skipped; the stream continues.
    }
  }
  return out;
}

type StreamState = "idle" | "streaming" | "finished" | "stopped" | "error";

/**
 * Live log viewer. Streams `GET …/logs?follow=true` with raw fetch() +
 * ReadableStream (EventSource cannot send the Authorization header) and
 * parses SSE `data:` lines as JSON `{t, line}` until a `{done: true}` event.
 */
export function RunLogViewer({
  jobId,
  runId,
}: {
  jobId: string;
  runId: string;
}) {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [tail, setTail] = useState(300);
  const [tailDraft, setTailDraft] = useState("300");
  const [autoScroll, setAutoScroll] = useState(true);
  const [state, setState] = useState<StreamState>("idle");
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lineIdRef = useRef(0);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setState((prev) => (prev === "streaming" ? "stopped" : prev));
  }, []);

  const start = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setError(null);
    setState("streaming");
    try {
      const res = await fetch(runLogsUrl(jobId, runId, tail), {
        headers: { Authorization: `Bearer ${DEV_TOKEN}` },
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`Log stream failed with status ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, rest } = splitSseEvents(buffer);
        buffer = rest;
        const fresh: LogLine[] = [];
        let sawDone = false;
        for (const block of events) {
          for (const event of parseSseEvent(block)) {
            if (event.done === true) {
              sawDone = true;
              break;
            }
            if (typeof event.line === "string") {
              fresh.push({
                id: lineIdRef.current++,
                t: typeof event.t === "string" ? event.t : "",
                line: event.line,
              });
            }
          }
          if (sawDone) break;
        }
        if (fresh.length > 0) {
          setLines((prev) => [...prev, ...fresh].slice(-MAX_LINES));
        }
        if (sawDone) break;
      }
      if (abortRef.current === controller) setState("finished");
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(
        err instanceof TypeError
          ? "Could not reach the API log stream — is the backend running?"
          : err instanceof Error
            ? err.message
            : "Log stream failed.",
      );
      setState("error");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [jobId, runId, tail]);

  useEffect(() => {
    void start();
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, [start]);

  useEffect(() => {
    // Re-scroll on every new batch of lines while auto-scroll is on.
    if (!autoScroll || !boxRef.current || lines.length === 0) return;
    boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines, autoScroll]);

  function applyTail() {
    const parsed = Number.parseInt(tailDraft, 10);
    if (Number.isNaN(parsed) || parsed < 1 || parsed > 5000) {
      setError("Tail must be a number between 1 and 5000.");
      return;
    }
    setTail(parsed);
  }

  const statusText =
    state === "streaming"
      ? "Streaming…"
      : state === "finished"
        ? "Finished"
        : state === "error"
          ? "Error"
          : state === "stopped"
            ? "Stopped"
            : "Idle";

  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <label
            htmlFor="log-tail"
            className="text-sm font-semibold text-charcoal"
          >
            Tail
          </label>
          <input
            id="log-tail"
            type="number"
            min={1}
            max={5000}
            value={tailDraft}
            onChange={(e) => setTailDraft(e.target.value)}
            className="min-h-[44px] w-24 rounded-lg border border-line bg-paper px-3 py-2 font-mono text-sm text-charcoal"
          />
          <button
            type="button"
            onClick={applyTail}
            className="inline-flex min-h-[44px] cursor-pointer items-center rounded-lg border border-line bg-paper px-3 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
          >
            Apply
          </button>
        </div>
        <label className="inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-lg px-2 py-1 text-sm font-semibold text-charcoal">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="h-4 w-4 accent-[#16161A]"
          />
          Auto-scroll
        </label>
        <div className="flex items-center gap-2">
          {state === "streaming" ? (
            <button
              type="button"
              onClick={stop}
              className="inline-flex min-h-[44px] cursor-pointer items-center rounded-lg border border-line bg-paper px-3 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
            >
              Stop
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void start()}
              className="inline-flex min-h-[44px] cursor-pointer items-center rounded-lg border border-line bg-paper px-3 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
            >
              Restart stream
            </button>
          )}
          <button
            type="button"
            onClick={() => setLines([])}
            className="inline-flex min-h-[44px] cursor-pointer items-center rounded-lg border border-line bg-paper px-3 py-2 text-sm font-semibold text-charcoal transition-colors duration-200 hover:border-charcoal hover:bg-platinum"
          >
            Clear
          </button>
        </div>
        <p
          className="ml-auto flex items-center gap-2 text-sm text-muted-ink"
          role="status"
        >
          {state === "streaming" && (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          )}
          {statusText} · {lines.length.toLocaleString()}{" "}
          {lines.length === 1 ? "line" : "lines"}
        </p>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm font-medium text-[#8f1d1d]">
          {error}
        </p>
      )}

      <div
        ref={boxRef}
        role="log"
        aria-label="Training run logs"
        className="mt-3 h-96 overflow-y-auto rounded-xl border border-line bg-charcoal p-4 font-mono text-[13px] leading-6 text-platinum"
      >
        {lines.length === 0 ? (
          <p className="text-platinum/60">
            {state === "streaming"
              ? "Waiting for log lines…"
              : "No log lines yet."}
          </p>
        ) : (
          lines.map((entry) => (
            <div key={entry.id} className="whitespace-pre-wrap break-words">
              {entry.t !== "" && (
                <span className="text-platinum/50">[{entry.t}] </span>
              )}
              {entry.line}
            </div>
          ))
        )}
      </div>
      <p className="mt-2 text-xs text-muted-ink">
        Restarting the stream replays the last {tail} lines; duplicates may
        appear.
      </p>
    </div>
  );
}

"use client";

import { FormEvent, useEffect, useState } from "react";

import { GlassPanel } from "../components/glass-panel";

type ChatMessage =
  | {
      id: string;
      role: "user";
      content: string;
    }
  | {
      id: string;
      role: "assistant";
      content: string;
      raw: unknown;
    };

type HealthResponse = {
  cache?: {
    count?: number;
  };
};

function hasAnswer(value: unknown): value is { answer: string } {
  if (!value || typeof value !== "object") {
    return false;
  }

  const candidate = value as { answer?: unknown };
  return typeof candidate.answer === "string";
}

export default function Home() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [showRawResponse, setShowRawResponse] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [cachedMessageCount, setCachedMessageCount] = useState<number | null>(null);
  const lastAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant");

  useEffect(() => {
    let isCancelled = false;

    async function loadHealth() {
      try {
        const response = await fetch("/api/health", { cache: "no-store" });
        const data = (await response.json().catch(() => null)) as HealthResponse | null;
        const count = typeof data?.cache?.count === "number" ? data.cache.count : 0;

        if (!isCancelled) {
          setCachedMessageCount(count);
        }
      } catch {
        if (!isCancelled) {
          setCachedMessageCount(0);
        }
      }
    }

    void loadHealth();

    return () => {
      isCancelled = true;
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) {
      return;
    }

    const userMessage: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: trimmedQuestion,
    };

    setIsLoading(true);
    setMessages((current) => [...current, userMessage]);
    setQuestion("");

    try {
      const response = await fetch("/api/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmedQuestion }),
      });

      const raw = (await response.json().catch(() => ({
        error: "The response could not be parsed as JSON.",
      }))) as unknown;

      const assistantMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: hasAnswer(raw)
          ? raw.answer
          : "The endpoint returned a response, but it did not match the expected schema.",
        raw,
      };

      setMessages((current) => [...current, assistantMessage]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Something went wrong while contacting the endpoint.";

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: "The request failed before a valid response came back.",
          raw: {
            error: message,
          },
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-8">
      <div
        className="absolute inset-0 bg-cover bg-center bg-no-repeat"
        style={{
          backgroundImage:
            "url('https://i.postimg.cc/j2MRMS6T/urban-vintage-78A265w-Pi-O4-unsplash.jpg')",
        }}
      />
      <div className="absolute inset-0 bg-black/28" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(168,210,255,0.14),transparent_35%),linear-gradient(180deg,rgba(0,0,0,0.04),rgba(0,0,0,0.36))]" />

      <section className="relative z-10 grid w-full max-w-[920px] gap-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <GlassPanel className="rounded-full border-white/14 px-4 py-2.5 text-left backdrop-blur-md">
            <h1 className="m-0 text-[clamp(1.25rem,3vw,1.7rem)] font-medium leading-none tracking-[-0.03em] text-white">
              Aurora QA
            </h1>
          </GlassPanel>

          <div className="flex items-center gap-3 text-sm text-white/78">
            <span className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#8bc5ff] opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-[#8bc5ff] shadow-[0_0_18px_rgba(139,197,255,0.95)]" />
            </span>
            <GlassPanel as="span" className="rounded-full border-white/12 bg-white/8 px-3 py-1.5 text-sm backdrop-blur-md">
              {cachedMessageCount ?? "..."} messages
            </GlassPanel>
          </div>
        </header>

        <GlassPanel className="grid gap-[18px] rounded-[36px] p-[18px]">
          <div className="max-h-[60vh] min-h-[360px] overflow-auto p-[6px] md:min-h-[300px]">
            {messages.length > 0 || isLoading ? (
              <div className="grid gap-[14px]">
                {messages.map((message) => {
                  return (
                    <article
                      key={message.id}
                      className={`grid max-w-[82%] rounded-[28px] p-[18px_20px] max-md:max-w-full ${
                        message.role === "user"
                          ? "ml-auto rounded-tr-[10px] bg-black/70 text-white shadow-[0_12px_28px_rgba(0,0,0,0.22)]"
                          : "rounded-tl-[10px] border border-white/12 bg-white/14 text-white"
                      }`}
                    >
                      <p className="m-0 leading-[1.6]">{message.content}</p>
                    </article>
                  );
                })}

                {isLoading ? (
                  <article className="w-fit rounded-[28px] rounded-tl-[10px] border border-white/12 bg-white/14 px-4 py-3 text-white">
                    <p
                      className="m-0 inline-flex items-center gap-1 text-[28px] leading-none tracking-[0.08em]"
                      aria-label="Thinking"
                    >
                      <span className="animate-pulse">.</span>
                      <span className="animate-pulse [animation-delay:150ms]">.</span>
                      <span className="animate-pulse [animation-delay:300ms]">.</span>
                    </p>
                  </article>
                ) : null}
              </div>
            ) : null}
          </div>

          <form className="grid items-center gap-3 md:grid-cols-[1fr_auto]" onSubmit={handleSubmit}>
            <label htmlFor="question" className="sr-only">
              Ask a question
            </label>
            <input
              id="question"
              name="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="What travel preferences has Fatima mentioned?"
              autoComplete="off"
              className="min-h-[60px] w-full rounded-[9999px] border border-white/16 bg-black/18 px-6 text-white outline-none transition-[border-color,box-shadow,background] duration-150 placeholder:text-white/42 focus:border-white/28 focus:bg-black/24 focus:shadow-[0_0_0_4px_rgba(255,255,255,0.08),0_18px_40px_rgba(0,0,0,0.18)]"
            />
            <button
              type="submit"
              className="min-h-[60px] min-w-[112px] rounded-[18px] border border-white/16 bg-white/12 px-[22px] text-white transition-[transform,opacity,background] duration-150 hover:translate-y-[-1px] hover:bg-white/16 disabled:cursor-default disabled:opacity-60 max-md:w-full"
              disabled={isLoading}
            >
              Ask
            </button>
          </form>
        </GlassPanel>

        {lastAssistantMessage && lastAssistantMessage.role === "assistant" ? (
          <div className="grid gap-3">
            <GlassPanel
              as="button"
              type="button"
              className="justify-self-start rounded-[9999px] border-white/16 px-[18px] py-3 text-white transition-[transform,background] duration-150 hover:translate-y-[-1px] hover:bg-white/16"
              onClick={() => setShowRawResponse((current) => !current)}
            >
              {showRawResponse ? "Hide raw response" : "Show raw response"}
            </GlassPanel>

            {showRawResponse ? (
              <GlassPanel
                as="pre"
                className="m-0 overflow-auto rounded-[36px] p-[18px] font-mono text-sm leading-[1.6] text-white"
              >
                {JSON.stringify(lastAssistantMessage.raw, null, 2)}
              </GlassPanel>
            ) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}

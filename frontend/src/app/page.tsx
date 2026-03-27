"use client";

import { FormEvent, useState } from "react";

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
  const lastAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant");

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
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(194,255,224,0.9),transparent_25%),radial-gradient(circle_at_85%_15%,rgba(202,223,255,0.9),transparent_28%),radial-gradient(circle_at_50%_80%,rgba(255,244,195,0.78),transparent_30%)] blur-[30px] opacity-95" />

      <section className="relative z-10 grid w-full max-w-[920px] gap-6">
        <header className="flex items-center justify-center text-center">
          <h1 className="m-0 text-[clamp(1.75rem,4vw,2.25rem)] font-normal leading-[1.1] tracking-[-0.03em]">
            Aurora Internal QA
          </h1>
        </header>

        <div className="grid gap-[18px] rounded-[32px] border border-[rgba(15,15,15,0.08)] bg-[rgba(255,255,255,0.72)] p-[18px] shadow-[0_24px_80px_rgba(16,24,40,0.1)] backdrop-blur-[18px]">
          <div className="max-h-[60vh] min-h-[360px] overflow-auto p-[6px] md:min-h-[300px]">
            {messages.length > 0 || isLoading ? (
              <div className="grid gap-[14px]">
                {messages.map((message) => {
                  return (
                    <article
                      key={message.id}
                      className={`grid max-w-[82%] rounded-[28px] p-[18px_20px] max-md:max-w-full ${
                        message.role === "user"
                          ? "ml-auto rounded-tr-[10px] bg-[#0b0b0b] text-white"
                          : "rounded-tl-[10px] border border-[rgba(8,8,8,0.06)] bg-[rgba(255,255,255,0.86)]"
                      }`}
                    >
                      <p className="m-0 leading-[1.6]">{message.content}</p>
                    </article>
                  );
                })}

                {isLoading ? (
                  <article className="w-fit rounded-[28px] rounded-tl-[10px] border border-[rgba(8,8,8,0.06)] bg-[rgba(255,255,255,0.86)] px-4 py-3">
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
              className="min-h-[60px] w-full rounded-[9999px] border border-[#d6d3cc] bg-[rgba(255,255,255,0.78)] px-6 text-[#080808] outline-none transition-[border-color,box-shadow,background] duration-150 placeholder:text-[rgba(8,8,8,0.42)] focus:border-[rgba(8,8,8,0.24)] focus:bg-[rgba(255,255,255,0.92)] focus:shadow-[0_0_0_6px_rgba(255,255,255,0.55),0_12px_30px_rgba(194,255,224,0.14)]"
            />
            <button
              type="submit"
              className="min-h-[60px] min-w-[112px] rounded-[18px] bg-black px-[22px] text-white transition-[transform,opacity] duration-150 hover:translate-y-[-1px] disabled:cursor-default disabled:opacity-60 max-md:w-full"
              disabled={isLoading}
            >
              Ask
            </button>
          </form>
        </div>

        {lastAssistantMessage && lastAssistantMessage.role === "assistant" ? (
          <div className="grid gap-3">
            <button
              type="button"
              className="justify-self-start rounded-[9999px] bg-black px-[18px] py-3 text-white"
              onClick={() => setShowRawResponse((current) => !current)}
            >
              {showRawResponse ? "Hide raw response" : "Show raw response"}
            </button>

            {showRawResponse ? (
              <pre className="m-0 overflow-auto rounded-[24px] border border-[rgba(8,8,8,0.08)] bg-[rgba(255,255,255,0.82)] p-[18px] font-mono text-sm leading-[1.6] text-[#161616]">
                {JSON.stringify(lastAssistantMessage.raw, null, 2)}
              </pre>
            ) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}

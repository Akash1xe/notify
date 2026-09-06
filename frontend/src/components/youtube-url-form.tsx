"use client";

import { FormEvent, useState } from "react";
import { validateYoutubeUrl } from "@/lib/youtube";

interface Props {
  disabled?: boolean;
  loading?: boolean;
  initialValue?: string;
  onSubmit: (url: string) => Promise<void> | void;
}

export function YoutubeUrlForm({ disabled, loading, initialValue = "", onSubmit }: Props) {
  const [value, setValue] = useState(initialValue);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = value.trim();
    const validationError = validateYoutubeUrl(normalized);
    if (validationError) {
      setError(validationError);
      return;
    }
    setError(null);
    await onSubmit(normalized);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3" noValidate>
      <label htmlFor="youtube-url" className="block text-sm font-medium text-slate-200">
        YouTube lecture URL
      </label>
      <input
        id="youtube-url"
        type="url"
        inputMode="url"
        autoComplete="url"
        value={value}
        disabled={disabled || loading}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? "youtube-url-error" : undefined}
        onChange={(event) => {
          setValue(event.target.value.replace(/[\r\n]/g, ""));
          if (error) setError(null);
        }}
        placeholder="https://www.youtube.com/watch?v=..."
        className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-slate-100 placeholder:text-slate-600 disabled:cursor-not-allowed disabled:opacity-60"
      />
      {error && (
        <p id="youtube-url-error" role="alert" className="text-sm text-red-300">{error}</p>
      )}
      <button
        type="submit"
        disabled={disabled || loading}
        className="w-full rounded-xl bg-slate-100 px-4 py-3 font-semibold text-slate-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Reading video information..." : "Analyze Video"}
      </button>
    </form>
  );
}

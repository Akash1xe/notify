const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;

export function extractYoutubeVideoId(rawValue: string): string | null {
  const value = rawValue.trim();
  if (!value) return null;

  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");

    if (host === "youtu.be") {
      const id = url.pathname.split("/").filter(Boolean)[0];
      return id && VIDEO_ID_PATTERN.test(id) ? id : null;
    }

    if (host === "youtube.com" || host === "m.youtube.com") {
      if (url.pathname === "/watch") {
        const id = url.searchParams.get("v");
        return id && VIDEO_ID_PATTERN.test(id) ? id : null;
      }

      const parts = url.pathname.split("/").filter(Boolean);
      if (parts[0] === "shorts" && parts[1] && VIDEO_ID_PATTERN.test(parts[1])) {
        return parts[1];
      }
    }
  } catch {
    return null;
  }

  return null;
}

export function validateYoutubeUrl(value: string): string | null {
  if (!value.trim()) return "Enter a YouTube video URL to continue.";
  if (!extractYoutubeVideoId(value)) return "Please enter a valid YouTube video URL.";
  return null;
}

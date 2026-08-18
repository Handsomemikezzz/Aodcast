export const XIAOYUZHOU_PODCASTER_URL = "https://podcaster.xiaoyuzhoufm.com/";
export const XIAOYUZHOU_AUDIO_FORMAT = "mp3";
export const XIAOYUZHOU_AUDIO_BITRATE = "192k";

export function xiaoyuzhouExportFilename(title: string): string {
  const slug = title
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "podcast-episode";
}

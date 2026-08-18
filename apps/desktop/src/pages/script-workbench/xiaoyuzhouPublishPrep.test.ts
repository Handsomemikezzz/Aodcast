import { describe, expect, it } from "vitest";
import {
  XIAOYUZHOU_AUDIO_BITRATE,
  XIAOYUZHOU_AUDIO_FORMAT,
  XIAOYUZHOU_PODCASTER_URL,
  xiaoyuzhouExportFilename,
} from "./xiaoyuzhouPublishPrep";

describe("xiaoyuzhou publish preparation", () => {
  it("creates a stable ASCII filename from an episode title", () => {
    expect(xiaoyuzhouExportFilename("My First Episode! 2026")).toBe("my-first-episode-2026");
  });

  it("uses a safe fallback when the title has no ASCII filename characters", () => {
    expect(xiaoyuzhouExportFilename("我的第一期")).toBe("podcast-episode");
  });

  it("locks the manual upload package to MP3 at 192 kbps and the official creator dashboard", () => {
    expect(XIAOYUZHOU_AUDIO_FORMAT).toBe("mp3");
    expect(XIAOYUZHOU_AUDIO_BITRATE).toBe("192k");
    expect(XIAOYUZHOU_PODCASTER_URL).toBe("https://podcaster.xiaoyuzhoufm.com/");
  });
});

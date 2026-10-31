// Bengal DM - SABR ABR stream helper (Deno).
// Streams the selected YouTube video+audio tracks from a browser-captured SABR
// session using googlevideo SabrStream (pure fetch/protobuf, no yt-dlp), writing
// separate MP4 part files and emitting NDJSON progress lines on stdout.
//
// Usage: deno run --allow-net --allow-read --allow-write sabr_download.mjs \
//          --session <file.json> --video-out <path> --audio-out <path>
import { SabrStream } from "npm:googlevideo@5.0.1/sabr-stream";
import { buildSabrFormat, EnabledTrackTypes } from "npm:googlevideo@5.0.1/utils";
import { VideoPlaybackAbrRequest } from "npm:googlevideo@5.0.1/protos";

const emit = (obj) => console.log(JSON.stringify(obj));

function arg(name) {
  const i = Deno.args.indexOf(name);
  return i >= 0 && i + 1 < Deno.args.length ? Deno.args[i + 1] : "";
}

function base64ToBytes(value) {
  return Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function writeStream(readable, path, onBytes) {
  const output = await Deno.open(path, { create: true, write: true, truncate: true });
  const reader = readable.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
      await output.write(chunk);
      onBytes(chunk.byteLength);
    }
  } finally {
    reader.releaseLock();
    output.close();
  }
}

async function main() {
  const sessionPath = arg("--session");
  const videoOut = arg("--video-out");
  const audioOut = arg("--audio-out");
  if (!sessionPath || !audioOut) throw new Error("Missing helper arguments");

  const session = JSON.parse(await Deno.readTextFile(sessionPath));
  const formats = session.formats.map((f) => ({ ...f, ...buildSabrFormat(f), audioTrack: f.audioTrack }));
  const audioFormat = formats.find((f) => f.itag === session.audioItag);
  const videoFormat = session.videoItag == null ? undefined : formats.find((f) => f.itag === session.videoItag);
  if (!audioFormat || (session.videoItag != null && !videoFormat)) {
    throw new Error("The selected YouTube tracks are unavailable in this session");
  }

  let seed = undefined;
  if (session.requestBody) {
    try {
      seed = VideoPlaybackAbrRequest.decode(base64ToBytes(session.requestBody));
    } catch {
      seed = undefined;
    }
  }
  const capturedClient = seed?.streamerContext?.clientInfo;
  const clientInfo = {
    clientName: Number(capturedClient?.clientName || session.clientInfo?.clientName) || 1,
    clientVersion: String(capturedClient?.clientVersion || session.clientInfo?.clientVersion || ""),
    hl: capturedClient?.hl,
    deviceMake: capturedClient?.deviceMake,
    deviceModel: capturedClient?.deviceModel,
    osName: capturedClient?.osName,
    osVersion: capturedClient?.osVersion,
  };
  const poToken = seed?.streamerContext?.poToken?.length
    ? bytesToBase64(seed.streamerContext.poToken)
    : undefined;

  let networkDownloaded = 0, downloaded = 0, lastReport = 0;
  const tracks = {};
  const total = [videoFormat, audioFormat].filter(Boolean).every((f) => Number(f.contentLength) > 0)
    ? [videoFormat, audioFormat].filter(Boolean).reduce((sum, f) => sum + Number(f.contentLength), 0)
    : null;
  const report = (force = false) => {
    const now = Date.now();
    if (!force && now - lastReport < 500) return;
    lastReport = now;
    emit({ ev: "progress", downloaded, total, networkDownloaded, tracks: { ...tracks } });
  };
  const progress = (itag) => (bytes) => { downloaded += bytes; tracks[itag] = (tracks[itag] || 0) + bytes; report(); };

  const fetchFunction = async (input, init = {}) => {
    const response = await fetch(input, init);
    if (!response.body || !response.ok) return response;
    const body = response.body.pipeThrough(new TransformStream({
      transform(chunk, controller) {
        networkDownloaded += chunk.byteLength;
        controller.enqueue(chunk);
      },
    }));
    return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
  };

  const sabr = new SabrStream({
    videoId: session.videoId,
    serverAbrStreamingUrl: session.serverAbrStreamingUrl,
    videoPlaybackUstreamerConfig: session.videoPlaybackUstreamerConfig,
    clientInfo,
    formats,
    fetchFunction,
    poToken,
  });

  addEventListener("SIGTERM", () => { void sabr.abort().catch(() => {}); });
  addEventListener("SIGINT", () => { void sabr.abort().catch(() => {}); });

  const hasVideo = session.videoItag != null;
  const streams = sabr.start({
    audioFormat: session.audioItag,
    videoFormat: hasVideo ? session.videoItag : undefined,
    enabledTrackTypes: hasVideo ? EnabledTrackTypes.VIDEO_AND_AUDIO : EnabledTrackTypes.AUDIO_ONLY,
    isPostLiveDvr: false,
  });

  try {
    const writes = [writeStream(streams.audioStream, audioOut, progress(session.audioItag))];
    if (hasVideo) writes.push(writeStream(streams.videoStream, videoOut, progress(session.videoItag)));
    await Promise.all(writes);
    void sabr.abort().catch(() => {});
    report(true);
    emit({
      ev: "done",
      videoPath: hasVideo ? videoOut : null,
      audioPath: audioOut,
      durationSec: Math.max(Number(audioFormat.approxDurationMs) || 0, Number(videoFormat?.approxDurationMs) || 0) / 1000,
    });
  } catch (error) {
    await sabr.abort().catch(() => {});
    throw error;
  }
}

try {
  await main();
} catch (error) {
  emit({ ev: "error", message: String((error && error.message) || error).slice(0, 500) });
  Deno.exit(1);
}

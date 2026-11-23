import argparse
import json
import logging
import math
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("AutoClipper")

US_STREAMERS = {
    "IShowSpeed": "https://www.youtube.com/@IShowSpeed",
    "KaiCenat": "https://www.twitch.tv/kaicenat",
    "Jynxzi": "https://www.twitch.tv/jynxzi",
    "xQc": "https://www.twitch.tv/xqc",
    "TheBurntPeanut": "https://www.twitch.tv/theburntpeanut",
}
DE_STREAMERS = {
    "EliasN97": "https://www.twitch.tv/eliasn97",
    "Zarbex": "https://www.twitch.tv/zarbex",
    "Papaplatte": "https://www.twitch.tv/papaplatte",
    "Trymacs": "https://www.twitch.tv/trymacs",
    "MontanaBlack": "https://www.twitch.tv/montanablack88",
}


@dataclass
class APIConfig:
    youtube_api_key: Optional[str] = field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY") or None)
    anthropic_api_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or None)
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"))
    gemini_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or None)
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))


@dataclass
class ClipperConfig:
    sample_rate: int = 16000
    frame_step_sec: float = 0.25
    audio_peak_weight: float = 0.45
    audio_rms_weight: float = 0.25
    scene_cut_weight: float = 0.30
    score_threshold: float = 0.60
    min_clip_duration: float = 30.0
    max_clip_duration: float = 90.0
    pre_roll: float = 8.0
    post_roll: float = 28.0
    cooldown_sec: float = 25.0
    vertical_9_16: bool = True
    target_width: int = 1080
    target_height: int = 1920
    crf: int = 20
    preset: str = "fast"
    focus_topics: List[str] = field(default_factory=lambda: ["GTA 6", "viral moment", "crazy reaction", "clutch", "funny"])


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class HighlightCandidate:
    timestamp: float
    score: float
    audio_peak_norm: float
    audio_rms_norm: float
    scene_cut_norm: float
    transcript_context: str = ""
    viral_hook: str = ""
    suggested_title: str = ""


@dataclass
class ClipSpec:
    index: int
    start: float
    end: float
    duration: float
    peak_timestamp: float
    score: float
    output_file: str
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)


def load_dotenv(env_path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries without overwriting existing environment values."""
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def check_ffmpeg() -> None:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("FFmpeg wurde nicht gefunden. Bitte installieren und zum PATH hinzufügen.") from exc


def search_youtube(api_cfg: APIConfig, query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Search public YouTube metadata only; this does not authorize or download a video."""
    if not api_cfg.youtube_api_key:
        logger.info("YOUTUBE_API_KEY nicht gesetzt – YouTube-Metadatensuche übersprungen.")
        return []
    params = urllib.parse.urlencode({
        "part": "snippet", "q": query, "type": "video", "order": "viewCount",
        "maxResults": max(1, min(50, max_results)), "key": api_cfg.youtube_api_key,
    })
    try:
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/search?{params}", timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("YouTube-Suche fehlgeschlagen: %s", exc)
        return []
    results = []
    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id:
            continue
        snippet = item.get("snippet", {})
        results.append({
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "published_at": snippet.get("publishedAt", ""),
        })
    return results


def research_current_topic(api_cfg: APIConfig, topic: str) -> Dict[str, object]:
    """Use Gemini with Google Search grounding; return research text and source metadata."""
    if not api_cfg.gemini_api_key:
        logger.info("GEMINI_API_KEY fehlt – aktuelle Web-Recherche übersprungen.")
        return {"topic": topic, "summary": "", "sources": [], "grounded": False}
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_cfg.gemini_api_key)
        response = client.models.generate_content(
            model=api_cfg.gemini_model,
            contents=(
                f"Recherchiere den aktuellen Stand zu: {topic}. Nutze aktuelle Webquellen. "
                "Fasse nur belegbare, cliprelevante Fakten kurz zusammen. Trenne bestätigte Fakten "
                "von Gerüchten und gib keine unbelegten Behauptungen aus."
            ),
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.2,
            ),
        )
        sources: List[Dict[str, str]] = []
        for candidate in getattr(response, "candidates", []) or []:
            metadata = getattr(candidate, "grounding_metadata", None)
            for chunk in getattr(metadata, "grounding_chunks", []) or []:
                web = getattr(chunk, "web", None)
                uri = getattr(web, "uri", None) if web else None
                title = getattr(web, "title", "") if web else ""
                if uri and not any(source["url"] == uri for source in sources):
                    sources.append({"title": title or "Source", "url": uri})
        return {
            "topic": topic,
            "summary": getattr(response, "text", "") or "",
            "sources": sources,
            "grounded": bool(sources),
            "model": api_cfg.gemini_model,
        }
    except Exception as exc:
        logger.warning("Gemini-Recherche fehlgeschlagen: %s", exc)
        return {"topic": topic, "summary": "", "sources": [], "grounded": False, "error": str(exc)}


def transcribe_video(video_path: Path) -> List[TranscriptSegment]:
    """Transcribe a local, authorized video with faster-whisper; requires FFmpeg."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Transkription benötigt faster-whisper. Installiere requirements.txt.") from exc
    model_name = os.getenv("WHISPER_MODEL", "small")
    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8" if device == "cpu" else "float16")
    logger.info("Erstelle Transkript (Whisper-Modell %s, %s)...", model_name, device)
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    segments, _info = model.transcribe(str(video_path), vad_filter=True)
    return [
        TranscriptSegment(start=float(segment.start), end=float(segment.end), text=segment.text.strip())
        for segment in segments if segment.text and segment.text.strip()
    ]


def context_for_timestamp(timestamp: float, transcript: List[TranscriptSegment], radius: float = 35.0) -> str:
    relevant = [segment for segment in transcript if segment.end >= timestamp - radius and segment.start <= timestamp + radius]
    return " ".join(f"[{segment.start:.1f}s] {segment.text}" for segment in relevant)[:6000]


def extract_pcm_audio(video_path: Path, sample_rate: int) -> np.ndarray:
    logger.info("Extrahiere Audiospur mit %d Hz...", sample_rate)
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video_path), "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip() or "FFmpeg-Audioextraktion fehlgeschlagen")
    audio = np.frombuffer(proc.stdout, dtype=np.int16)
    if audio.size == 0:
        raise ValueError("Keine Audiodaten aus dem Video extrahierbar.")
    return audio.astype(np.float32) / 32768.0


def compute_audio_features(samples: np.ndarray, sample_rate: int, step_sec: float) -> Tuple[np.ndarray, np.ndarray]:
    step = max(1, int(sample_rate * step_sec))
    window = max(step, int(sample_rate))
    count = max(1, math.ceil(len(samples) / step))
    peaks = np.zeros(count, dtype=np.float32)
    rms = np.zeros(count, dtype=np.float32)
    for i in range(count):
        center = i * step
        chunk = samples[max(0, center - window // 2):min(len(samples), center + window // 2)]
        if chunk.size:
            peaks[i] = float(np.max(np.abs(chunk)))
            rms[i] = float(np.sqrt(np.mean(chunk ** 2)))
    return peaks, rms


def compute_scene_changes(video_path: Path, step_sec: float) -> Tuple[np.ndarray, float]:
    logger.info("Analysiere Szenenwechsel (Intervall: %.2fs)...", step_sec)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Konnte Video nicht öffnen: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / fps if frame_count > 0 else 0.0
        stride = max(1, int(round(fps * step_sec)))
        diffs: List[float] = []
        previous = None
        frame_index = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % stride == 0:
                small = cv2.resize(frame, (160, 90))
                hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
                cv2.normalize(hist, hist)
                if previous is None:
                    diffs.append(0.0)
                else:
                    corr = float(cv2.compareHist(previous, hist, cv2.HISTCMP_CORREL))
                    diffs.append(max(0.0, min(1.5, 1.0 - corr)))
                previous = hist
            frame_index += 1
    finally:
        cap.release()
    values = np.asarray(diffs, dtype=np.float32) if diffs else np.zeros(1, dtype=np.float32)
    if duration <= 0:
        duration = len(values) * step_sec
    return values, duration


def normalize_percentile(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low, high = float(np.percentile(values, 10)), float(np.percentile(values, 97))
    if math.isclose(low, high):
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def detect_candidates(peaks: np.ndarray, rms: np.ndarray, scenes: np.ndarray, step: float, cfg: ClipperConfig) -> List[HighlightCandidate]:
    count = min(len(peaks), len(rms), len(scenes))
    if count == 0:
        return []
    peak_norm, rms_norm, scene_norm = normalize_percentile(peaks[:count]), normalize_percentile(rms[:count]), normalize_percentile(scenes[:count])
    weight_sum = cfg.audio_peak_weight + cfg.audio_rms_weight + cfg.scene_cut_weight
    if weight_sum <= 0:
        raise ValueError("Mindestens ein Signalgewicht muss positiv sein.")
    scores = (cfg.audio_peak_weight / weight_sum) * peak_norm + (cfg.audio_rms_weight / weight_sum) * rms_norm + (cfg.scene_cut_weight / weight_sum) * scene_norm
    accepted: List[float] = []
    candidates: List[HighlightCandidate] = []
    for idx in np.argsort(-scores):
        score = float(scores[idx])
        if score < cfg.score_threshold:
            break
        timestamp = float(idx) * step
        if any(abs(timestamp - other) < cfg.cooldown_sec for other in accepted):
            continue
        accepted.append(timestamp)
        candidates.append(HighlightCandidate(
            timestamp=round(timestamp, 2), score=round(score, 4),
            audio_peak_norm=round(float(peak_norm[idx]), 3),
            audio_rms_norm=round(float(rms_norm[idx]), 3),
            scene_cut_norm=round(float(scene_norm[idx]), 3),
        ))
    return sorted(candidates, key=lambda item: item.timestamp)


def rank_with_claude(candidates: List[HighlightCandidate], streamer: str, cfg: ClipperConfig, api_cfg: APIConfig) -> List[HighlightCandidate]:
    if not candidates:
        return candidates
    if not api_cfg.anthropic_api_key:
        logger.info("ANTHROPIC_API_KEY fehlt – Kandidaten bleiben lokal sortiert.")
        for index, candidate in enumerate(candidates, 1):
            candidate.suggested_title = f"{streamer} - Highlight #{index} #Shorts"
            candidate.viral_hook = "Audio-/Szenen-Peak erkannt; Transkript zur Kontrolle im Manifest"
        return candidates

    items = [{
        "timestamp": candidate.timestamp,
        "score": candidate.score,
        "transcript_context": candidate.transcript_context,
    } for candidate in candidates]
    body = {
        "model": api_cfg.anthropic_model,
        "max_tokens": 1200,
        "system": (
            "Du bewertest Transkript-Ausschnitte für eigenständige 30-90-Sekunden-Streamer-Clips. "
            "Nutze ausschließlich den gelieferten Kontext; wenn er nicht aussagekräftig ist, sage das. "
            "Gib ausschließlich ein JSON-Array aus Objekten mit timestamp, viral_hook und suggested_title zurück."
        ),
        "messages": [{"role": "user", "content": json.dumps({"streamer": streamer, "topics": cfg.focus_topics, "candidates": items}, ensure_ascii=False)}],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": api_cfg.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = "\n".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        ranked = json.loads(text)
        if not isinstance(ranked, list):
            raise ValueError("Claude-Antwort ist kein JSON-Array")
        by_time = {round(float(item["timestamp"]), 2): item for item in ranked if isinstance(item, dict) and "timestamp" in item}
        for candidate in candidates:
            match = by_time.get(round(candidate.timestamp, 2))
            if match:
                candidate.viral_hook = str(match.get("viral_hook", ""))[:300]
                candidate.suggested_title = str(match.get("suggested_title", ""))[:100]
    except Exception as exc:
        logger.warning("Claude-Transkriptbewertung fehlgeschlagen: %s", exc)
    return candidates


def build_clip_specs(candidates: List[HighlightCandidate], duration: float, output_dir: Path, streamer: str, cfg: ClipperConfig) -> List[ClipSpec]:
    minimum = max(30.0, cfg.min_clip_duration)
    maximum = min(90.0, max(minimum, cfg.max_clip_duration))
    windows: List[Tuple[float, float, HighlightCandidate]] = []
    for candidate in candidates:
        start = max(0.0, candidate.timestamp - cfg.pre_roll)
        end = min(duration, candidate.timestamp + cfg.post_roll)
        if end - start < minimum:
            end = min(duration, start + minimum)
            start = max(0.0, end - minimum)
        if end - start > maximum:
            end = start + maximum
        if end - start >= min(minimum, duration):
            windows.append((start, end, candidate))
    windows.sort(key=lambda window: window[0])
    merged: List[Tuple[float, float, HighlightCandidate]] = []
    for start, end, candidate in windows:
        if not merged:
            merged.append((start, end, candidate))
            continue
        old_start, old_end, old_candidate = merged[-1]
        if start <= old_end + 1.0:
            new_end = min(duration, max(old_end, end), old_start + maximum)
            winner = candidate if candidate.score > old_candidate.score else old_candidate
            merged[-1] = (old_start, new_end, winner)
        else:
            merged.append((start, end, candidate))
    specs: List[ClipSpec] = []
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", streamer).strip("_").lower() or "streamer"
    for index, (start, end, candidate) in enumerate(merged, 1):
        clip_duration = round(end - start, 2)
        if clip_duration < min(minimum, duration):
            continue
        title = candidate.suggested_title or f"{streamer} - Highlight #{index} #Shorts"
        description = f"{candidate.viral_hook or 'Highlight'} | Streamer: {streamer} | {', '.join(cfg.focus_topics)}"
        filename = f"{safe_name}_clip_{index:02d}_{int(start)}s_to_{int(end)}s.mp4"
        specs.append(ClipSpec(index, round(start, 2), round(end, 2), clip_duration, candidate.timestamp,
                              candidate.score, str(output_dir / filename), title[:100], description,
                              ["Shorts", "Gaming", streamer]))
    return specs


def render_clip(video: Path, spec: ClipSpec, cfg: ClipperConfig) -> None:
    if cfg.vertical_9_16:
        width, height = cfg.target_width, cfg.target_height
        filters = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:5[bg];"
            f"[0:v]scale={width}:-2:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]"
        )
        command = ["ffmpeg", "-y", "-v", "error", "-ss", f"{spec.start:.3f}", "-i", str(video), "-t", f"{spec.duration:.3f}",
                   "-filter_complex", filters, "-map", "[vout]", "-map", "0:a?", "-c:v", "libx264", "-preset", cfg.preset,
                   "-crf", str(cfg.crf), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", spec.output_file]
    else:
        command = ["ffmpeg", "-y", "-v", "error", "-ss", f"{spec.start:.3f}", "-i", str(video), "-t", f"{spec.duration:.3f}",
                   "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-c:a", "aac", "-b:a", "128k",
                   "-movflags", "+faststart", spec.output_file]
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-Clipper: lokale Analyse, Transkript, Gemini-Webrecherche und Claude-Metadaten")
    parser.add_argument("input_video", nargs="?", type=Path, help="Lokale, zur Bearbeitung freigegebene Video-/VOD-Datei")
    parser.add_argument("--streamer", default="Streamer")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("clips_out"))
    parser.add_argument("--min-len", type=float, default=30.0)
    parser.add_argument("--max-len", type=float, default=90.0)
    parser.add_argument("--threshold", type=float, default=0.60)
    parser.add_argument("--topic", default="GTA 6", help="Aktuelles Thema für Gemini Search Grounding")
    parser.add_argument("--no-research", action="store_true", help="Gemini-Webrecherche überspringen")
    parser.add_argument("--no-transcript", action="store_true", help="Whisper-Transkription überspringen")
    parser.add_argument("--no-vertical", action="store_true")
    parser.add_argument("--list-streamers", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Manifest schreiben, nicht rendern")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    if args.list_streamers:
        print("=== US ===")
        for name, url in US_STREAMERS.items(): print(f"- {name}: {url}")
        print("=== Deutschland ===")
        for name, url in DE_STREAMERS.items(): print(f"- {name}: {url}")
        return 0
    if args.input_video is None:
        logger.error("Lokale Video-Datei erforderlich. Nutzung: python auto_clipper.py video.mp4")
        return 2
    if args.min_len > args.max_len:
        logger.error("--min-len darf nicht größer als --max-len sein.")
        return 2
    if not 0 <= args.threshold <= 1:
        logger.error("--threshold muss zwischen 0 und 1 liegen.")
        return 2
    if not args.input_video.is_file():
        logger.error("Datei nicht gefunden: %s", args.input_video)
        return 2

    cfg = ClipperConfig(
        min_clip_duration=max(30.0, args.min_len),
        max_clip_duration=min(90.0, max(30.0, args.max_len)),
        score_threshold=args.threshold,
        vertical_9_16=not args.no_vertical,
    )
    api_cfg = APIConfig()
    try:
        check_ffmpeg()
        args.output_dir.mkdir(parents=True, exist_ok=True)
        research = {} if args.no_research else research_current_topic(api_cfg, args.topic)
        youtube_results = search_youtube(api_cfg, args.topic)
        samples = extract_pcm_audio(args.input_video, cfg.sample_rate)
        peaks, rms = compute_audio_features(samples, cfg.sample_rate, cfg.frame_step_sec)
        scenes, duration = compute_scene_changes(args.input_video, cfg.frame_step_sec)
        transcript = [] if args.no_transcript else transcribe_video(args.input_video)
        candidates = detect_candidates(peaks, rms, scenes, cfg.frame_step_sec, cfg)
        for candidate in candidates:
            candidate.transcript_context = context_for_timestamp(candidate.timestamp, transcript)
        candidates = rank_with_claude(candidates, args.streamer, cfg, api_cfg)
        specs = build_clip_specs(candidates, duration, args.output_dir, args.streamer, cfg)
        manifest = {
            "source_video": str(args.input_video), "streamer": args.streamer, "duration_sec": round(duration, 2),
            "config": asdict(cfg), "topic_research": research, "youtube_search_metadata": youtube_results,
            "transcript": [asdict(segment) for segment in transcript],
            "candidates": [asdict(candidate) for candidate in candidates], "clips": [asdict(spec) for spec in specs],
            "publication_note": "Uploads are not automatic. Publish only content you are authorized to use.",
        }
        manifest_path = args.output_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Manifest gespeichert: %s (%d Clips)", manifest_path, len(specs))
        if args.dry_run:
            return 0
        for spec in specs:
            logger.info("Rendere Clip #%d (%.1f-%.1fs)", spec.index, spec.start, spec.end)
            render_clip(args.input_video, spec, cfg)
        return 0
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        logger.error("Verarbeitung abgebrochen: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

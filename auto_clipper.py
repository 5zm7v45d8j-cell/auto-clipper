import argparse
import json
import logging
import math
import os
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
    pre_roll: float = 6.0
    post_roll: float = 24.0
    cooldown_sec: float = 25.0
    vertical_9_16: bool = True
    target_width: int = 1080
    target_height: int = 1920
    crf: int = 20
    preset: str = "fast"
    focus_topics: List[str] = field(default_factory=lambda: ["GTA 6", "viral moment", "crazy reaction", "clutch", "funny"])


@dataclass
class HighlightCandidate:
    timestamp: float
    score: float
    audio_peak_norm: float
    audio_rms_norm: float
    scene_cut_norm: float
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
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def check_ffmpeg() -> None:
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("FFmpeg wurde nicht gefunden. Bitte installieren und zum PATH hinzufügen.") from exc


def search_youtube(api_cfg: APIConfig, query: str, max_results: int = 10) -> List[Dict[str, str]]:
    if not api_cfg.youtube_api_key:
        logger.info("YOUTUBE_API_KEY nicht gesetzt – YouTube-Recherche übersprungen.")
        return []
    params = urllib.parse.urlencode({"part": "snippet", "q": query, "type": "video", "order": "viewCount", "maxResults": max_results, "key": api_cfg.youtube_api_key})
    try:
        with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/search?{params}", timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("YouTube-Suche fehlgeschlagen: %s", exc)
        return []
    return [{"video_id": item["id"]["videoId"], "url": f"https://www.youtube.com/watch?v={item['id']['videoId']}", "title": item["snippet"].get("title", ""), "channel": item["snippet"].get("channelTitle", "")}
            for item in payload.get("items", []) if item.get("id", {}).get("videoId")]


def extract_pcm_audio(video_path: Path, sample_rate: int) -> np.ndarray:
    logger.info("Extrahiere Audiospur mit %d Hz...", sample_rate)
    proc = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video_path), "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace").strip() or "FFmpeg-Audioextraktion fehlgeschlagen")
    samples = np.frombuffer(proc.stdout, dtype=np.int16)
    if samples.size == 0:
        raise ValueError("Keine Audiodaten aus dem Video extrahierbar.")
    return samples.astype(np.float32) / 32768.0


def compute_audio_features(samples: np.ndarray, sample_rate: int, step_sec: float) -> Tuple[np.ndarray, np.ndarray]:
    step = max(1, int(sample_rate * step_sec))
    window = max(step, int(sample_rate))
    count = max(1, len(samples) // step)
    peaks = np.zeros(count, dtype=np.float32)
    rms = np.zeros(count, dtype=np.float32)
    for i in range(count):
        center = i * step
        chunk = samples[max(0, center - window // 2):min(len(samples), center + window // 2)]
        if chunk.size:
            peaks[i] = np.max(np.abs(chunk))
            rms[i] = np.sqrt(np.mean(chunk ** 2))
    return peaks, rms


def compute_scene_changes(video_path: Path, step_sec: float) -> Tuple[np.ndarray, float]:
    logger.info("Analysiere visuelle Szenenwechsel (Intervall: %.2fs)...", step_sec)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Konnte Video nicht öffnen: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = frames / fps if frames > 0 else 0.0
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
    cap.release()
    result = np.array(diffs, dtype=np.float32) if diffs else np.zeros(1, dtype=np.float32)
    if duration <= 0:
        duration = len(result) * step_sec
    return result, duration


def normalize_percentile(values: np.ndarray) -> np.ndarray:
    if values.size == 0:
        return values
    low = float(np.percentile(values, 10))
    high = float(np.percentile(values, 97))
    if math.isclose(low, high):
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def detect_candidates(peaks: np.ndarray, rms: np.ndarray, scenes: np.ndarray, step: float, cfg: ClipperConfig) -> List[HighlightCandidate]:
    count = min(len(peaks), len(rms), len(scenes))
    if count == 0:
        return []
    peak_norm = normalize_percentile(peaks[:count])
    rms_norm = normalize_percentile(rms[:count])
    scene_norm = normalize_percentile(scenes[:count])
    total = cfg.audio_peak_weight + cfg.audio_rms_weight + cfg.scene_cut_weight
    scores = (cfg.audio_peak_weight / total) * peak_norm + (cfg.audio_rms_weight / total) * rms_norm + (cfg.scene_cut_weight / total) * scene_norm
    accepted: List[float] = []
    result: List[HighlightCandidate] = []
    for idx in np.argsort(-scores):
        score = float(scores[idx])
        if score < cfg.score_threshold:
            break
        timestamp = float(idx) * step
        if any(abs(timestamp - old) < cfg.cooldown_sec for old in accepted):
            continue
        accepted.append(timestamp)
        result.append(HighlightCandidate(round(timestamp, 2), round(score, 4), round(float(peak_norm[idx]), 3), round(float(rms_norm[idx]), 3), round(float(scene_norm[idx]), 3)))
    return sorted(result, key=lambda candidate: candidate.timestamp)


def rank_with_claude(candidates: List[HighlightCandidate], streamer: str, cfg: ClipperConfig, api_cfg: APIConfig) -> List[HighlightCandidate]:
    if not candidates:
        return candidates
    if not api_cfg.anthropic_api_key:
        for i, candidate in enumerate(candidates, 1):
            candidate.suggested_title = f"{streamer} - Viral Moment #{i} #Shorts"
            candidate.viral_hook = "Lokaler Audio-/Szenen-Peak"
        return candidates
    payload = {"model": api_cfg.anthropic_model, "max_tokens": 1024, "system": "Du kuratierst nur bereits gefundene lokale 30- bis 90-Sekunden-Clip-Kandidaten. Gib ausschließlich ein JSON-Array mit timestamp, viral_hook und suggested_title zurück. Keine erfundenen Zusagen oder Quellen.", "messages": [{"role": "user", "content": json.dumps({"streamer": streamer, "topics": cfg.focus_topics, "candidates": [asdict(c) for c in candidates]}, ensure_ascii=False)}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(), headers={"x-api-key": api_cfg.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = "\n".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text").strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        ranked = json.loads(text)
        by_time = {round(float(item["timestamp"]), 2): item for item in ranked if "timestamp" in item}
        for candidate in candidates:
            match = by_time.get(round(candidate.timestamp, 2))
            if match:
                candidate.viral_hook = str(match.get("viral_hook", ""))
                candidate.suggested_title = str(match.get("suggested_title", ""))
    except Exception as exc:
        logger.warning("Claude-Bewertung fehlgeschlagen: %s", exc)
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
        if end - start >= minimum:
            windows.append((start, end, candidate))
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
    for index, (start, end, candidate) in enumerate(merged, 1):
        clip_duration = round(end - start, 2)
        if clip_duration < minimum:
            continue
        title = candidate.suggested_title or f"{streamer} - Viral Moment #{index} #Shorts"
        description = f"{candidate.viral_hook or 'Top Moment'} | Streamer: {streamer} | Themen: {', '.join(cfg.focus_topics)} #Shorts #GTA6 #Viral"
        filename = f"{streamer.lower().replace(' ', '_')}_clip_{index:02d}_{int(start)}s_to_{int(end)}s.mp4"
        specs.append(ClipSpec(index, round(start, 2), round(end, 2), clip_duration, candidate.timestamp, candidate.score, str(output_dir / filename), title[:100], description, ["Shorts", "GTA6", "Viral", streamer, "Gaming"]))
    return specs


def render_clip(video: Path, spec: ClipSpec, cfg: ClipperConfig) -> None:
    if cfg.vertical_9_16:
        w, h = cfg.target_width, cfg.target_height
        vf = f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=20:5[bg];[0:v]scale={w}:-2:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]"
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{spec.start:.3f}", "-i", str(video), "-t", f"{spec.duration:.3f}", "-filter_complex", vf, "-map", "[vout]", "-map", "0:a?", "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", spec.output_file]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{spec.start:.3f}", "-i", str(video), "-t", f"{spec.duration:.3f}", "-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", spec.output_file]
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="US/DE Streamer Multi-Signal Auto-Clipper")
    parser.add_argument("input_video", nargs="?", type=Path)
    parser.add_argument("--streamer", default="Streamer")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("clips_out"))
    parser.add_argument("--min-len", type=float, default=30.0)
    parser.add_argument("--max-len", type=float, default=90.0)
    parser.add_argument("--threshold", type=float, default=0.60)
    parser.add_argument("--search-query", default="GTA 6 viral streamer moments")
    parser.add_argument("--list-streamers", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    if args.list_streamers:
        print("=== US STREAMER ===")
        for name, url in US_STREAMERS.items(): print(f"- {name}: {url}")
        print("=== DE STREAMER ===")
        for name, url in DE_STREAMERS.items(): print(f"- {name}: {url}")
        return 0
    if args.input_video is None:
        logger.error("Keine Eingabedatei angegeben. Nutzung: python auto_clipper.py video.mp4")
        return 2
    min_len = max(30.0, args.min_len)
    max_len = min(90.0, max(min_len, args.max_len))
    cfg = ClipperConfig(min_clip_duration=min_len, max_clip_duration=max_len, score_threshold=args.threshold)
    api_cfg = APIConfig()
    try:
        check_ffmpeg()
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2
    if not args.input_video.exists():
        logger.error("Eingabedatei existiert nicht: %s", args.input_video)
        return 2
    args.output_dir.mkdir(parents=True, exist_ok=True)
    youtube_results = search_youtube(api_cfg, args.search_query)
    samples = extract_pcm_audio(args.input_video, cfg.sample_rate)
    peaks, rms = compute_audio_features(samples, cfg.sample_rate, cfg.frame_step_sec)
    scenes, duration = compute_scene_changes(args.input_video, cfg.frame_step_sec)
    candidates = rank_with_claude(detect_candidates(peaks, rms, scenes, cfg.frame_step_sec, cfg), args.streamer, cfg, api_cfg)
    specs = build_clip_specs(candidates, duration, args.output_dir, args.streamer, cfg)
    manifest = {"source_video": str(args.input_video), "streamer": args.streamer, "duration_sec": round(duration, 2), "config": asdict(cfg), "youtube_search": youtube_results, "candidates": [asdict(c) for c in candidates], "clips": [asdict(s) for s in specs]}
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Manifest gespeichert: %s (%d Clips)", manifest_path, len(specs))
    if args.dry_run:
        return 0
    for spec in specs:
        logger.info("Rendere Clip #%d: %.2fs-%.2fs", spec.index, spec.start, spec.end)
        render_clip(args.input_video, spec, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

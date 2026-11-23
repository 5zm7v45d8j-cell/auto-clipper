import argparse
import json
import logging
import math
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("AutoClipper")


@dataclass
class ClipConfig:
    sample_rate: int = 16000
    frame_step_sec: float = 0.25
    audio_peak_weight: float = 0.45
    audio_rms_weight: float = 0.25
    scene_cut_weight: float = 0.30
    score_threshold: float = 0.62
    min_clip_duration: float = 12.0
    max_clip_duration: float = 60.0
    pre_roll: float = 3.0
    post_roll: float = 5.0
    cooldown_sec: float = 15.0
    vertical_9_16: bool = True
    target_width: int = 1080
    target_height: int = 1920
    crf: int = 20
    preset: str = "fast"


@dataclass
class HighlightCandidate:
    timestamp: float
    score: float
    audio_peak_norm: float
    audio_rms_norm: float
    scene_cut_norm: float


@dataclass
class ClipSpec:
    index: int
    start: float
    end: float
    duration: float
    peak_timestamp: float
    score: float
    output_file: str


def check_ffmpeg() -> None:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError("FFmpeg wurde nicht gefunden. Bitte installieren und zum PATH hinzufügen.") from exc


def extract_pcm_audio(video_path: Path, sample_rate: int) -> np.ndarray:
    """Extrahiert Mono-PCM-Audio als float32-Array im Bereich [-1.0, 1.0]."""
    logger.info("Extrahiere Audiospur mit %d Hz...", sample_rate)
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-i", str(video_path),
        "-ac", "1",
        "-ar", str(sample_rate),
        "-f", "s16le",
        "pipe:1",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    audio_int16 = np.frombuffer(proc.stdout, dtype=np.int16)
    if audio_int16.size == 0:
        raise ValueError("Keine Audiodaten aus dem Video extrahierbar.")
    return audio_int16.astype(np.float32) / 32768.0


def compute_audio_features(
    samples: np.ndarray, sample_rate: int, step_sec: float
) -> Tuple[np.ndarray, np.ndarray]:
    """Berechnet zeitdiskrete Peak- und RMS-Werte für jedes Zeitfenster."""
    step_samples = max(1, int(sample_rate * step_sec))
    win_samples = max(step_samples, int(sample_rate * 1.0))
    n_steps = max(1, len(samples) // step_samples)

    peaks = np.zeros(n_steps, dtype=np.float32)
    rms = np.zeros(n_steps, dtype=np.float32)

    for i in range(n_steps):
        center = i * step_samples
        start = max(0, center - win_samples // 2)
        end = min(len(samples), center + win_samples // 2)
        chunk = samples[start:end]
        if chunk.size > 0:
            peaks[i] = float(np.max(np.abs(chunk)))
            rms[i] = float(np.sqrt(np.mean(chunk ** 2)))

    return peaks, rms


def compute_scene_changes(video_path: Path, step_sec: float) -> Tuple[np.ndarray, float]:
    """Berechnet normalisierte Histogramm-Differenzen zwischen Frames als Szenenwechsel-Signal."""
    logger.info("Analysiere visuelle Szenenwechsel (Intervall: %.2fs)...", step_sec)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Konnte Video nicht öffnen: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / fps if total_frames > 0 else 0.0

    frame_stride = max(1, int(round(fps * step_sec)))
    diffs: List[float] = []
    prev_hist = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_stride == 0:
            small = cv2.resize(frame, (160, 90))
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
            hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
            cv2.normalize(hist, hist)

            if prev_hist is not None:
                corr = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL))
                diff = max(0.0, min(1.5, 1.0 - corr))
                diffs.append(diff)
            else:
                diffs.append(0.0)

            prev_hist = hist

        frame_idx += 1

    cap.release()
    arr = np.array(diffs, dtype=np.float32) if diffs else np.zeros(1, dtype=np.float32)
    if duration <= 0.0:
        duration = len(arr) * step_sec
    return arr, duration


def normalize_percentile(arr: np.ndarray, p_low: float = 10.0, p_high: float = 97.0) -> np.ndarray:
    """Robuste Normalisierung auf [0, 1] mittels Perzentilen gegen Ausreißer."""
    if arr.size == 0:
        return arr
    lo = float(np.percentile(arr, p_low))
    hi = float(np.percentile(arr, p_high))
    if math.isclose(hi, lo):
        return np.zeros_like(arr)
    norm = (arr - lo) / (hi - lo)
    return np.clip(norm, 0.0, 1.0)


def detect_candidates(
    peaks: np.ndarray,
    rms: np.ndarray,
    scene_diffs: np.ndarray,
    step_sec: float,
    cfg: ClipConfig,
) -> List[HighlightCandidate]:
    """Kombiniert Audio- und Visuell-Signale zu gewichteten Highlight-Kandidaten."""
    n = min(len(peaks), len(rms), len(scene_diffs))
    if n == 0:
        return []

    p_norm = normalize_percentile(peaks[:n])
    r_norm = normalize_percentile(rms[:n])
    s_norm = normalize_percentile(scene_diffs[:n])

    w_sum = cfg.audio_peak_weight + cfg.audio_rms_weight + cfg.scene_cut_weight
    wp = cfg.audio_peak_weight / w_sum
    wr = cfg.audio_rms_weight / w_sum
    ws = cfg.scene_cut_weight / w_sum

    scores = wp * p_norm + wr * r_norm + ws * s_norm

    order = np.argsort(-scores)
    selected: List[HighlightCandidate] = []
    accepted_times: List[float] = []

    for idx in order:
        sc = float(scores[idx])
        if sc < cfg.score_threshold:
            break
        t = idx * step_sec
        if any(abs(t - prev_t) < cfg.cooldown_sec for prev_t in accepted_times):
            continue
        accepted_times.append(t)
        selected.append(
            HighlightCandidate(
                timestamp=round(t, 2),
                score=round(sc, 4),
                audio_peak_norm=round(float(p_norm[idx]), 3),
                audio_rms_norm=round(float(r_norm[idx]), 3),
                scene_cut_norm=round(float(s_norm[idx]), 3),
            )
        )

    selected.sort(key=lambda c: c.timestamp)
    return selected


def build_clip_specs(
    candidates: List[HighlightCandidate],
    total_duration: float,
    output_dir: Path,
    cfg: ClipConfig,
) -> List[ClipSpec]:
    """Wandelt Kandidaten in überlappungsfreie Clip-Zeitfenster inkl. Pre-/Post-Roll um."""
    raw_windows: List[Tuple[float, float, HighlightCandidate]] = []

    for cand in candidates:
        start = max(0.0, cand.timestamp - cfg.pre_roll)
        end = min(total_duration, cand.timestamp + cfg.post_roll)
        if end - start < cfg.min_clip_duration:
            end = min(total_duration, start + cfg.min_clip_duration)
            start = max(0.0, end - cfg.min_clip_duration)
        if end - start > cfg.max_clip_duration:
            end = start + cfg.max_clip_duration
        if end > start:
            raw_windows.append((start, end, cand))

    merged: List[Tuple[float, float, HighlightCandidate]] = []
    for start, end, cand in raw_windows:
        if not merged:
            merged.append((start, end, cand))
            continue
        prev_start, prev_end, prev_cand = merged[-1]
        if start <= prev_end + 1.0:
            new_end = min(total_duration, max(prev_end, end), prev_start + cfg.max_clip_duration)
            best_cand = cand if cand.score > prev_cand.score else prev_cand
            merged[-1] = (prev_start, new_end, best_cand)
        else:
            merged.append((start, end, cand))

    specs: List[ClipSpec] = []
    for i, (start, end, cand) in enumerate(merged, start=1):
        duration = round(end - start, 2)
        if duration < min(cfg.min_clip_duration, total_duration):
            continue
        filename = f"clip_{i:02d}_{int(start)}s_to_{int(end)}s.mp4"
        specs.append(
            ClipSpec(
                index=i,
                start=round(start, 2),
                end=round(end, 2),
                duration=duration,
                peak_timestamp=cand.timestamp,
                score=cand.score,
                output_file=str(output_dir / filename),
            )
        )

    return specs


def render_clip(input_video: Path, spec: ClipSpec, cfg: ClipConfig) -> None:
    """Schneidet den Clip per FFmpeg und rendert optional 9:16 mit unscharfem Hintergrund."""
    if cfg.vertical_9_16:
        w, h = cfg.target_width, cfg.target_height
        vf = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},boxblur=20:5[bg];"
            f"[0:v]scale={w}:-2:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vout]"
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-v", "error",
            "-ss", f"{spec.start:.3f}",
            "-to", f"{spec.end:.3f}",
            "-i", str(input_video),
            "-filter_complex", vf,
            "-map", "[vout]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", cfg.preset,
            "-crf", str(cfg.crf),
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            spec.output_file,
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-v", "error",
            "-ss", f"{spec.start:.3f}",
            "-to", f"{spec.end:.3f}",
            "-i", str(input_video),
            "-c:v", "libx264",
            "-preset", cfg.preset,
            "-crf", str(cfg.crf),
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            spec.output_file,
        ]

    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Komplexer Multi-Signal Auto-Clipper")
    parser.add_argument("input_video", type=Path, help="Pfad zum Quellvideo")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("clips_out"), help="Zielordner")
    parser.add_argument("--threshold", type=float, default=0.62, help="Score-Schwelle (0.0 - 1.0)")
    parser.add_argument("--min-len", type=float, default=12.0, help="Minimale Cliplänge in Sekunden")
    parser.add_argument("--max-len", type=float, default=60.0, help="Maximale Cliplänge in Sekunden")
    parser.add_argument("--cooldown", type=float, default=15.0, help="Mindestabstand zwischen Peaks (s)")
    parser.add_argument("--no-vertical", action="store_true", help="Behält Original-Seitenverhältnis bei")
    parser.add_argument("--dry-run", action="store_true", help="Nur analysieren und Manifest schreiben")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    check_ffmpeg()

    if not args.input_video.exists():
        logger.error("Eingabedatei existiert nicht: %s", args.input_video)
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    cfg = ClipConfig(
        score_threshold=args.threshold,
        min_clip_duration=args.min_len,
        max_clip_duration=args.max_len,
        cooldown_sec=args.cooldown,
        vertical_9_16=not args.no_vertical,
    )

    samples = extract_pcm_audio(args.input_video, cfg.sample_rate)
    peaks, rms = compute_audio_features(samples, cfg.sample_rate, cfg.frame_step_sec)
    scene_diffs, duration = compute_scene_changes(args.input_video, cfg.frame_step_sec)

    candidates = detect_candidates(peaks, rms, scene_diffs, cfg.frame_step_sec, cfg)
    logger.info("Gefundene Highlight-Kandidaten: %d", len(candidates))

    specs = build_clip_specs(candidates, duration, args.output_dir, cfg)
    logger.info("Erzeugte Clip-Spezifikationen: %d", len(specs))

    manifest = {
        "source_video": str(args.input_video),
        "duration_sec": round(duration, 2),
        "config": asdict(cfg),
        "candidates": [asdict(c) for c in candidates],
        "clips": [asdict(s) for s in specs],
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Manifest gespeichert unter: %s", manifest_path)

    if args.dry_run:
        logger.info("Dry-Run aktiv – es werden keine Videodateien gerendert.")
        return

    for spec in specs:
        logger.info(
            "Rendere Clip #%d (%.2fs - %.2fs, Score %.3f)...",
            spec.index, spec.start, spec.end, spec.score,
        )
        render_clip(args.input_video, spec, cfg)

    logger.info("Fertig! Alle Clips liegen in '%s'.", args.output_dir)


if __name__ == "__main__":
    main()

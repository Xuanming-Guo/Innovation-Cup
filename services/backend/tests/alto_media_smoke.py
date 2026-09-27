"""Exercise actual ffmpeg/ffprobe in the built worker image; no provider or network."""

from __future__ import annotations

import io
import subprocess
import wave
from typing import Any

from coordination.config import Settings
from coordination.workspace.files import validate_file


def main() -> None:
    options: dict[str, Any] = {"_env_file": None, "environment": "test"}
    settings = Settings(**options)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 32000)
    checked = validate_file(buffer.getvalue(), "audio/wav", settings)
    assert 1.9 <= checked["audio_duration_seconds"] <= 2.1
    for fmt, codec, mime, extra in (
        ("webm", "libopus", "audio/webm", []),
        ("mp4", "aac", "audio/mp4", ["-movflags", "frag_keyframe+empty_moov"]),
    ):
        recording = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=16000:cl=mono",
                "-t",
                "2",
                "-c:a",
                codec,
                *extra,
                "-f",
                fmt,
                "pipe:1",
            ],
            capture_output=True,
            timeout=15,
            check=True,
        ).stdout
        checked = validate_file(recording, mime, settings)
        assert 1.9 <= checked["audio_duration_seconds"] <= 2.2
    oversized = io.BytesIO()
    with wave.open(oversized, "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * (16000 * 61))
    try:
        validate_file(oversized.getvalue(), "audio/wav", settings)
    except ValueError as error:
        assert str(error) == "audio_duration"
    else:
        raise AssertionError("61-second recording was accepted")
    print("Actual worker media validation passed: WAV, streaming WebM, MP4; 61s rejected.")


if __name__ == "__main__":
    main()

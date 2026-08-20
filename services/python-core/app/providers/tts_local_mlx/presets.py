from __future__ import annotations

DEFAULT_LOCAL_TTS_MODEL = "mlx-community/VoxCPM2-8bit"

# Remote repository ids accepted by the local runtime. Local directories are
# identified from their config.json instead, so copied or relocated models do
# not depend on directory naming conventions.
SUPPORTED_LOCAL_TTS_MODELS: tuple[str, ...] = (
    "mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit",
    "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit",
    "mlx-community/Qwen3-TTS-12Hz-0.6B-CustomVoice-8bit",
    "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit",
    "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit",
    "mlx-community/VoxCPM2-4bit",
    "mlx-community/VoxCPM2-8bit",
    "mlx-community/VoxCPM2-bf16",
    "OpenMOSS-Team/MOSS-TTS-v1.5",
    "OpenMOSS-Team/MOSS-TTS-Local-Transformer-v1.5",
)

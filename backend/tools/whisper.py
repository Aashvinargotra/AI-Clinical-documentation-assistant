"""OpenAI Whisper Audio Transcription Wrapper Module.

Validates uploaded clinical audio files (.wav, .mp3, .m4a, .webm, .ogg, .flac)
and performs speech-to-text transcription using OpenAI Whisper API with Groq fallback.
Handles corrupted audio files gracefully to trigger manual dictation UI fallback.
"""

import os
import tempfile
import logging
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("whisper_tool")

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}


def transcribe_audio_file(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Transcribes an uploaded audio file into plain text clinical transcript.
    
    Args:
        file_bytes: Raw binary content of the uploaded audio file.
        filename: Name of the uploaded file including extension.
        
    Returns:
        Dict with 'transcript' (str) and 'duration_seconds' (float).
        
    Raises:
        ValueError: If file extension is unsupported.
        RuntimeError: If audio file is corrupted or transcription API fails.
    """
    if not file_bytes:
        raise ValueError("Uploaded audio file is empty.")

    ext = os.path.splitext(filename)[1].lower()
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio file format '{ext}'. Allowed formats: {sorted(list(ALLOWED_EXTENSIONS))}"
        )

    # Save audio bytes to a temporary file
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
            temp_file.write(file_bytes)
            temp_file_path = temp_file.name

        transcript_text = None

        # 1. Try OpenAI Whisper API
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key and not openai_key.startswith("your-"):
            try:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                with open(temp_file_path, "rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )
                transcript_text = response.text
                logger.info("Successfully transcribed audio using OpenAI Whisper-1 API.")
            except Exception as exc:
                logger.warning(f"OpenAI Whisper transcription failed: {exc}. Trying Groq fallback...")

        # 2. Try Groq Whisper API fallback if OpenAI failed or unavailable
        if not transcript_text:
            groq_key = os.getenv("GROQ_API_KEY", "").strip()
            if groq_key and not groq_key.startswith("your-"):
                try:
                    from openai import OpenAI
                    client = OpenAI(
                        api_key=groq_key,
                        base_url="https://api.groq.com/openai/v1"
                    )
                    with open(temp_file_path, "rb") as audio_file:
                        response = client.audio.transcriptions.create(
                            model="whisper-large-v3",
                            file=audio_file
                        )
                    transcript_text = response.text
                    logger.info("Successfully transcribed audio using Groq Whisper-large-v3 API.")
                except Exception as exc:
                    logger.warning(f"Groq Whisper transcription failed: {exc}")

        if not transcript_text:
            raise RuntimeError("Audio transcription failed. Could not process audio file with available keys.")

        # Estimate duration from file size / character length fallback
        estimated_duration = round(len(file_bytes) / 32000.0, 1)  # Rough estimate
        return {
            "transcript": transcript_text.strip(),
            "duration_seconds": max(estimated_duration, 1.0)
        }

    except ValueError:
        raise
    except Exception as exc:
        logger.error(f"Whisper audio processing error: {exc}")
        raise RuntimeError(f"Unable to transcribe audio file. Switched to manual text dictation mode. Details: {exc}")
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass

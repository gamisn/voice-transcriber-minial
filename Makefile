.PHONY: install install-gpu run clean

# Install with uv (preferred) or pip
install:
	@command -v uv >/dev/null 2>&1 && \
		uv pip install openai-whisper sounddevice numpy || \
		pip install openai-whisper sounddevice numpy

install-gpu:
	@command -v uv >/dev/null 2>&1 && \
		uv pip install openai-whisper sounddevice numpy "torch[cuda]" || \
		pip install openai-whisper sounddevice numpy "torch[cuda]"

run:
	python transcriber.py

clean:
	rm -rf __pycache__ *.pyc

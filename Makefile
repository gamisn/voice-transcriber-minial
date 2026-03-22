.PHONY: install install-gpu run tray toggle clean

# Full setup: venv, deps, shortcuts, autostart
install:
	./install.sh

# Install with NVIDIA GPU support (CUDA)
install-gpu:
	./install.sh
	@command -v uv >/dev/null 2>&1 && \
		uv pip install --python .venv/bin/python "torch[cuda]" || \
		.venv/bin/python -m pip install "torch[cuda]"

# CLI mode (terminal)
run:
	.venv/bin/python transcriber.py

# Start the floating status window daemon
tray:
	/usr/bin/python3 tray.py

# Toggle recording in the running daemon
toggle:
	/usr/bin/python3 tray.py toggle

clean:
	rm -rf __pycache__ *.pyc

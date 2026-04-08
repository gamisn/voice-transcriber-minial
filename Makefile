.PHONY: install install-gpu install-mac run tray tray-mac toggle test clean

# Full setup: venv, deps, shortcuts, autostart (Linux)
install:
	./install.sh

# macOS setup: venv, deps, menubar daemon, launchd
install-mac:
	./install_mac.sh

# Install with NVIDIA GPU support (CUDA)
install-gpu:
	./install.sh
	@command -v uv >/dev/null 2>&1 && \
		uv pip install --python .venv/bin/python "torch[cuda]" || \
		.venv/bin/python -m pip install "torch[cuda]"

# CLI mode (terminal)
run:
	.venv/bin/python transcriber.py

# Start the panel daemon (Linux — GTK/AppIndicator)
tray:
	/usr/bin/python3 tray.py

# Start the menubar daemon (macOS — NSStatusItem)
tray-mac:
	.venv/bin/python mac_menubar.py

# Toggle recording in the running daemon
toggle:
	/usr/bin/python3 tray.py toggle

# Run the test suite
test:
	.venv/bin/python -m pytest tests/ -v

clean:
	rm -rf __pycache__ *.pyc

# Contributing to Bengal Download Manager

Thank you for your interest in contributing to **Bengal Download Manager**! We welcome bug reports, feature suggestions, documentation updates, and code contributions.

---

## 🛠️ Development Environment Setup

### 1. Prerequisites

Ensure you have the required system packages installed:

- **Python 3.10+**
- **Qt6 Libraries / PyQt6**
- **Aria2** (optional but recommended for RPC engine features)
- **Git**

For OS-specific package manager commands, refer to [DEPENDENCIES.md](DEPENDENCIES.md).

### 2. Clone & Setup Virtual Environment (using `uv`)

```bash
git clone https://github.com/tazihad/bengal-download-manager.git
cd bengal-download-manager

uv venv
uv pip install -r requirements-dev.txt
```

---

## 🚀 Running the Application

### Standard PyQt6 Interface:
```bash
uv run python src/main.py
```

### KDE Kirigami QML Mode:
```bash
uv run python src/main.py --kirigami
```

---

## 🧪 Testing & Verification

All contributions should maintain or improve test coverage. Run the automated test suite before opening a pull request:

```bash
PYTHONPATH=src uv run pytest -v tests/
```

Make sure all tests pass cleanly without errors.

---

## 📐 Code Guidelines & Architecture

1. **Architecture Separation**:
   - `src/core/`: Download engine, workers (`download.py`, `aria2.py`, `fetcher.py`), SQLite database manager, and QML bridge.
   - `src/ui/`: PyQt6 widgets, dialogs, custom table delegates, and Kirigami QML views.
   - `extension/`: Manifest V3 browser integration extension.
2. **Numeric Typography**: When formatting numeric data (percentages, sizes, transfer rates, elapsed time) in QML/UI labels, enable tabular figures (`font.features: { "tnum": 1 }`).
3. **Theme Compatibility**: Do not hardcode static colors for text or backgrounds. Ensure components dynamically adapt to both Light and Dark system palettes.
4. **Defensive Programming**: Handle network drops and transient I/O exceptions gracefully; preserve existing docstrings and comments.

---

## 📦 Packaging & Build Verification

If you are modifying packaging or deployment scripts:

- **Standalone PyInstaller Build**:
  ```bash
  cmake -B build -S .
  cmake --build build
  ```
- **Browser Extension Zip**:
  ```bash
  python3 scripts/pack_extension.py
  ```
- **Flatpak Build**:
  ```bash
  bash scripts/build_and_run_flatpak.sh
  ```
- **Snap Build**:
  ```bash
  bash scripts/build_snap.sh
  ```

---

## 📝 Commit & Pull Request Guidelines

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat(<scope>): add new capability or feature`
- `fix(<scope>): resolve a bug`
- `refactor(<scope>): code cleanup or architecture optimization`
- `test(<scope>): add or update automated test coverage`
- `docs(<scope>): documentation or README updates`

### Submitting a PR

1. Fork the repository and create a descriptive branch: `git checkout -b feature/my-cool-feature` or `git checkout -b fix/issue-description`.
2. Ensure test suite passes: `PYTHONPATH=src pytest -v tests/`.
3. Submit your pull request with a clear description of changes, motivation, and any testing performed.

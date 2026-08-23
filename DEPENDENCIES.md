# Dependencies

This document lists all the dependencies required to build and run **Bengal Download Manager**.

## 1. System Dependencies (Linux)

Before installing Python packages, ensure your system has the following installed:

- **Python 3.10+**: The core language runtime.
- **Qt6 Libraries**: Required by PyQt6 for the GUI.
- **Aria2**: The high-performance download engine (optional but highly recommended).

### Installation on Ubuntu/Debian:
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv aria2 libqt6gui6
```

### Installation on Fedora:
```bash
sudo dnf install python3 python3-pip aria2 qt6-qtbase-gui
```

### Installation on Arch Linux:
```bash
sudo pacman -S python python-pip aria2 qt6-base
```

---

## 2. Python Dependencies

These are listed in `requirements.txt` and should be installed in a virtual environment.

| Package | Purpose |
|---------|---------|
| `PyQt6` | The GUI framework used for the IDM-style interface. |
| `pyinstaller` | Used to bundle the application into a standalone executable. |
| `pytest` | Framework for running automated tests. |
| `pytest-qt` | Plugin for testing Qt applications. |

### Installation:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development/testing
```

---

## 3. Build Tools

- **CMake (3.12+)**: Used to orchestrate the build process and PyInstaller bundling.
- **PyInstaller**: Invoked via CMake to create the final executable in `build/dist/`.

---

## 4. Browser Integration (Optional)

The Chrome/Firefox extension requires:
- A modern browser (Chrome, Edge, Firefox, Brave, etc.).
- The extension files located in the `extension/` directory.
- The application must be running to receive downloads via the local TCP port (9000).

---

## 5. Development Utilities

- **xdg-utils**: Used for "Open Folder" and "Open File" functionality on Linux to interact with your file manager (Nautilus, Dolphin, etc.).

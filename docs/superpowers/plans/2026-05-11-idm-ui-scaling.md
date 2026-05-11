# IDM-Like UI Scaling & Behavior Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable High DPI scaling and refactor hardcoded UI sizes into dynamic layouts to ensure the app works properly on all display resolutions (720p to 8K), mimicking IDM's behavior.

**Architecture:** 
- Enable Qt High DPI scaling globally.
- Replace `setFixedSize` and hardcoded `setGeometry` with layouts and `QSettings` (or current `settings.json` mechanism).
- Implement persistence for column widths and window states.

**Tech Stack:** Python, PyQt6

---

### Task 1: Global High DPI Scaling

**Files:**
- Modify: `src/main.py:1-150`

- [ ] **Step 1: Enable High DPI scaling before QApplication starts**

In `src/main.py`, update the main entry point to set the High DPI scale factor policy.

```python
# Around line 1500 (bottom of file)
if __name__ == "__main__":
    from PyQt6.QtCore import Qt
    # Add this line before creating QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    # ...
```

- [ ] **Step 2: Verify application starts and looks normal on current display**

Run: `python3 src/main.py`
Expected: App launches without visual regressions.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: enable High DPI scaling with PassThrough policy"
```

### Task 2: MainWindow State Persistence (Columns & Geometry)

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Implement column width saving/restoration**

Update `save_settings` and `load_settings` in `src/main.py` to include `column_widths`.

```python
# In MainWindow class in src/main.py

def save_settings(self):
    try:
        config_dir = get_config_dir()
        # Save column widths
        column_widths = []
        for i in range(self.download_table.columnCount()):
            column_widths.append(self.download_table.columnWidth(i))
            
        settings = {
            "geometry": self.saveGeometry().toHex().data().decode(),
            "windowState": self.saveState().toHex().data().decode(),
            "column_widths": column_widths
        }
        with open(os.path.join(config_dir, "settings.json"), "w") as f:
            json.dump(settings, f)
    except Exception:
        pass

def load_settings(self):
    settings = {}
    config_dir = get_config_dir()
    path = os.path.join(config_dir, "settings.json")
    if not os.path.exists(path):
        return settings
    try:
        with open(path, "r") as f:
            settings = json.load(f)
            if "geometry" in settings:
                self.restoreGeometry(QByteArray.fromHex(settings["geometry"].encode()))
            if "windowState" in settings:
                self.restoreState(QByteArray.fromHex(settings["windowState"].encode()))
            if "column_widths" in settings:
                for i, width in enumerate(settings["column_widths"]):
                    if i < self.download_table.columnCount():
                        self.download_table.setColumnWidth(i, width)
    except Exception:
        pass
    return settings
```

- [ ] **Step 2: Ensure `load_settings` is called correctly and `setGeometry` doesn't override**

In `MainWindow.__init__`, make sure `setGeometry` is only a fallback.

```python
# In src/main.py MainWindow.__init__
self.setGeometry(200, 150, 1000, 600)
self.load_settings() # This will override setGeometry if saved settings exist
```

- [ ] **Step 3: Add `closeEvent` to save settings on exit**

```python
def closeEvent(self, event):
    self.save_settings()
    super().closeEvent(event)
```

- [ ] **Step 4: Verify persistence**

1. Run app, resize window and a few columns.
2. Close app.
3. Re-run app.
4. Verify sizes are preserved.

- [ ] **Step 5: Commit**

```bash
git add src/main.py
git commit -m "feat: persist window geometry and table column widths"
```

### Task 3: Refactor AddUrlDialog to be Resizable

**Files:**
- Modify: `src/dialogs.py`

- [ ] **Step 1: Remove `setFixedSize` and add layout constraints**

In `AddUrlDialog.__init__`:
- Remove `self.setFixedSize(600, 100)`.
- Set `self.setMinimumWidth(500)`.
- Ensure the layout expands correctly.

- [ ] **Step 2: Verify dialog looks good on 720p/1080p**

Run: `python3 src/main.py` and click "Add URL".
Verify it's resizable and doesn't look broken.

- [ ] **Step 3: Commit**

```bash
git add src/dialogs.py
git commit -m "refactor: make AddUrlDialog resizable"
```

### Task 4: Refactor OptionsDialog to be Resizable

**Files:**
- Modify: `src/dialogs.py`

- [ ] **Step 1: Remove `setFixedSize` and ensure scrollable tabs**

In `OptionsDialog.__init__`:
- Remove `self.setFixedSize(600, 550)`.
- Add `self.setMinimumSize(500, 400)`.
- If a tab has many widgets, wrap them in a `QScrollArea` if necessary (optional if it fits).

- [ ] **Step 2: Verify Options dialog**

Run app -> View -> Options. Resize it.

- [ ] **Step 3: Commit**

```bash
git add src/dialogs.py
git commit -m "refactor: make OptionsDialog resizable"
```

### Task 5: Refactor DownloadProgressDialog to be Resizable

**Files:**
- Modify: `src/dialogs.py`

- [ ] **Step 1: Make Progress dialog flexible**

In `DownloadProgressDialog.__init__`:
- Remove `self.setFixedSize(...)`.
- Use layouts to allow the filename label to elide or wrap if the window is too small, or just let the window grow.
- Set a sensible `setMinimumWidth(450)`.

- [ ] **Step 2: Verify Progress dialog**

Start a download. Resize the progress window.

- [ ] **Step 3: Commit**

```bash
git add src/dialogs.py
git commit -m "refactor: make DownloadProgressDialog resizable"
```

### Task 6: Final Verification across simulated resolutions

- [ ] **Step 1: Test with High DPI scaling simulated**

Run: `QT_SCALE_FACTOR=2 python3 src/main.py`
Verify everything is 2x larger but sharp.

- [ ] **Step 2: Test small resolution**

Manually resize windows to very small sizes and verify they don't crash and remain functional.

- [ ] **Step 3: Final Commit**

```bash
git commit --allow-empty -m "chore: final verification of UI scaling changes complete"
```

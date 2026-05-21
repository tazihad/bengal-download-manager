# Spec & Plan: Fixing UI State Desync and Flickering

The main window toolbar buttons (Stop/Pause, Resume) become desynced when a download is paused from the progress dialog. The "Resume" button stays grayed out while the dialog is open because the main window disables "Resume" for all "active" downloads. Furthermore, the percentage flickers because status updates sometimes fail to trigger a UI refresh if the display text (the percentage) hasn't changed.

## Proposed Changes

### 1. Fix Toolbar State Logic (`update_ui_states`)
Currently, `update_ui_states` assumes any download in `self.active_downloads` cannot be resumed from the main window.
- Change: Check the logical status of active downloads. If an active download is "Paused" (or "Error", "Cancelled"), it should trigger `selection_has_resumable = True` and we should allow the `action_resume` button.

### 2. Force UI Updates on Logical State Change
In `update_download_row` and `download_finished`, the call to `self.update_ui_states()` is guarded by `if final_display != old_status:`.
- Change: Trigger `self.update_ui_states()` if the display text changes OR if the internal logical status (`Qt.ItemDataRole.UserRole + 1`) changes.

### 3. Forward Resume Command (`resume_selected_download`)
Currently, if a download is active, clicking Resume on the toolbar just brings the window to the front.
- Change: Bring the window to the front AND, if the download is paused, trigger its `resume()` method.

### 4. Ensure Logical Status is Set on Pause (`download_finished`)
When `download_finished` is called with "Paused", it formats the display text but might miss updating the internal logical status.
- Change: Explicitly set `status_item.setData(Qt.ItemDataRole.UserRole + 1, "Paused")` when a pause completes.

## Implementation Steps

### Task 1: Fix Toolbar Logic and Resume Forwarding

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Update `update_ui_states`**

```python
<<<<
                # Check for active workers
                if key in self.active_downloads:
                    selection_has_active = True
                
                # Pausable statuses (currently downloading)
                if status in ["Connecting...", "Downloading", "Resuming...", "Pending..."]:
                    selection_has_pausable = True
                    
                # Resumable statuses (not active and not completed)
                if status in ["Paused", "Cancelled", "Error"]:
                    selection_has_resumable = True
        
        # STOP action is for pausing an active download
        self.action_stop.setEnabled(selection_has_pausable and not selection_has_resumable)
        self.action_stop_all.setEnabled(has_active_downloads)
        
        # RESUME action is for starting a paused/errored/cancelled download
        self.action_resume.setEnabled(selection_has_resumable and not selection_has_active)
        self.action_download_now.setEnabled(selection_has_resumable and not selection_has_active)
====
                # Check for active workers
                is_active = key in self.active_downloads
                if is_active:
                    selection_has_active = True
                
                # Pausable statuses (currently downloading)
                if status in ["Connecting...", "Downloading", "Resuming...", "Pending..."]:
                    selection_has_pausable = True
                    
                # Resumable statuses
                if status in ["Paused", "Cancelled", "Error"]:
                    selection_has_resumable = True
                    # If it is resumable, it shouldn't strictly block the resume button just because it's "active" (open window)
                    if is_active:
                        selection_has_active = False # Treat as inactive for resume logic so button enables
        
        # STOP action is for pausing an active download
        self.action_stop.setEnabled(selection_has_pausable)
        self.action_stop_all.setEnabled(has_active_downloads)
        
        # RESUME action is for starting a paused/errored/cancelled download
        self.action_resume.setEnabled(selection_has_resumable and not selection_has_active)
        self.action_download_now.setEnabled(selection_has_resumable and not selection_has_active)
>>>>
```

- [ ] **Step 2: Update `resume_selected_download` to forward resume to dialog**

```python
<<<<
            # If already active, bring dialog to front
            if id(item_name) in self.active_downloads:
                dialog = self.active_downloads[id(item_name)]
                dialog.activateWindow()
                dialog.raise_()
                continue
====
            # If already active, bring dialog to front
            if id(item_name) in self.active_downloads:
                dialog = self.active_downloads[id(item_name)]
                dialog.activateWindow()
                dialog.raise_()
                
                # If the dialog is paused, resume it directly
                status_item = self.download_table.item(row, 2)
                if status_item and status_item.data(Qt.ItemDataRole.UserRole + 1) == "Paused":
                    if hasattr(dialog, 'worker') and hasattr(dialog.worker, 'resume'):
                        dialog.worker.resume()
                        dialog.btn_pause.setText("Pause")
                        dialog.lbl_main_status.setText("Resuming...")
                        dialog.btn_cancel.setText("Cancel")
                continue
>>>>
```

### Task 2: Fix Status Propagation and Flickering

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Ensure `update_download_row` triggers state update on logical change**

```python
<<<<
            # CRITICAL: Always force "Complete" if that's the determined status
            if display_status == "Complete":
                final_display = "Complete"
                status_item.setText("Complete")
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
                
            if final_display != old_status:
                status_item.setText(final_display)
                self.update_ui_states()
====
            # CRITICAL: Always force "Complete" if that's the determined status
            if display_status == "Complete":
                final_display = "Complete"
                status_item.setText("Complete")
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
                
            old_logic_status = status_item.data(Qt.ItemDataRole.UserRole + 1) if status_item else ""
            
            if final_display != old_status:
                status_item.setText(final_display)
            
            if final_display != old_status or display_status != old_logic_status:
                self.update_ui_states()
>>>>
```

- [ ] **Step 2: Ensure `download_finished` correctly sets logical status**

```python
<<<<
            # Formatting final display text
            if display_status == "Complete":
                final_display = "Complete"
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
            elif display_status in ["Paused", "Cancelled"]:
                pct = status_item.data(Qt.ItemDataRole.UserRole)
                final_display = pct if pct else "0.0%"
            else:
                final_display = display_status
            
            status_item.setText(final_display)
====
            # Formatting final display text
            if display_status == "Complete":
                final_display = "Complete"
                status_item.setData(Qt.ItemDataRole.UserRole + 1, "Complete")
            elif display_status in ["Paused", "Cancelled"]:
                pct = status_item.data(Qt.ItemDataRole.UserRole)
                final_display = pct if pct else "0.0%"
                status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            else:
                final_display = display_status
                status_item.setData(Qt.ItemDataRole.UserRole + 1, display_status)
            
            status_item.setText(final_display)
>>>>
```

- [ ] **Step 3: Commit changes**

```bash
git add src/main.py
git commit -m "fix: resolve UI state desync between main toolbar and progress dialog"
```

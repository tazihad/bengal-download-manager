#!/usr/bin/env python3
"""
Flathub Banner Preview & Selection Tool
Starts a local HTTP server to preview and select Flathub <branding> colors for Bengal Download Manager.
Replicates Flathub's official HeroBanner component with live Light/Dark previews.
"""

import http.server
import json
import mimetypes
import os
import re
import socketserver
import subprocess
import sys
from pathlib import Path

PORT = 8765
REPO_ROOT = Path(__file__).resolve().parent.parent
METAINFO_PATH = REPO_ROOT / "flatpak" / "bd.com.zihad.BengalDownloadManager.metainfo.xml"

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Flathub Banner Preview — Bengal Download Manager</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0f1318;
      --card-bg: #181d24;
      --border: #27313f;
      --text: #eff0f1;
      --text-muted: #94a3b8;
      --accent: #ea580c;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: 'Inter', -apple-system, sans-serif;
      padding: 32px 20px;
      line-height: 1.5;
    }

    .container {
      max-width: 1180px;
      margin: 0 auto;
    }

    header {
      margin-bottom: 28px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }

    .title-area h1 {
      font-size: 1.85rem;
      font-weight: 800;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .title-area p {
      color: var(--text-muted);
      font-size: 0.95rem;
      margin-top: 4px;
    }

    .links-area {
      display: flex;
      gap: 10px;
    }

    .btn-link {
      background: var(--card-bg);
      border: 1px solid var(--border);
      color: var(--text);
      text-decoration: none;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }
    .btn-link:hover {
      border-color: var(--accent);
      color: #fff;
    }

    /* Preset Grid */
    .section-title {
      font-size: 1.1rem;
      font-weight: 700;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .presets-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 28px;
    }

    .preset-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px;
      cursor: pointer;
      transition: all 0.2s;
      text-align: left;
    }

    .preset-card:hover {
      border-color: #3b82f6;
      transform: translateY(-2px);
    }

    .preset-card.active {
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(234, 88, 12, 0.35);
      background: #202731;
    }

    .preset-swatches {
      display: flex;
      height: 28px;
      border-radius: 6px;
      overflow: hidden;
      margin-bottom: 8px;
    }

    .swatch {
      flex: 1;
      height: 100%;
    }

    .preset-name {
      font-size: 0.85rem;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .preset-hexes {
      font-size: 0.72rem;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
      margin-top: 2px;
    }

    /* Custom Pickers Row */
    .controls-panel {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 20px;
      margin-bottom: 28px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 20px;
    }

    .pickers-group {
      display: flex;
      align-items: center;
      gap: 24px;
      flex-wrap: wrap;
    }

    .picker-item {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .picker-label {
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    .color-input-wrapper {
      display: flex;
      align-items: center;
      gap: 8px;
      background: #11151a;
      border: 1px solid var(--border);
      padding: 4px 8px;
      border-radius: 8px;
    }

    input[type="color"] {
      -webkit-appearance: none;
      border: none;
      width: 28px;
      height: 28px;
      border-radius: 6px;
      cursor: pointer;
      background: transparent;
    }
    input[type="color"]::-webkit-color-swatch-wrapper { padding: 0; }
    input[type="color"]::-webkit-color-swatch { border: 1px solid rgba(255,255,255,0.2); border-radius: 6px; }

    .hex-input {
      background: transparent;
      border: none;
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9rem;
      font-weight: 600;
      width: 78px;
      outline: none;
    }

    .apply-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .btn-apply {
      background: #ea580c;
      color: #fff;
      border: none;
      padding: 10px 22px;
      border-radius: 8px;
      font-size: 0.95rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.2s;
      box-shadow: 0 4px 14px rgba(234, 88, 12, 0.4);
    }
    .btn-apply:hover {
      background: #c2410c;
      transform: translateY(-1px);
    }
    .btn-apply:active {
      transform: translateY(1px);
    }

    /* Banner Previews Container */
    .previews-section {
      display: flex;
      flex-direction: column;
      gap: 28px;
      margin-bottom: 32px;
    }

    .preview-box {
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      background: #111418;
    }

    .preview-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      padding: 0 4px;
    }

    .preview-badge {
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 4px 10px;
      border-radius: 6px;
    }
    .badge-light { background: #f8fafc; color: #0f172a; }
    .badge-dark { background: #1e293b; color: #f8fafc; border: 1px solid #334155; }

    .contrast-info {
      font-size: 0.8rem;
      color: var(--text-muted);
      font-family: 'JetBrains Mono', monospace;
    }

    /* Flathub Exact HeroBanner Component Styling */
    .flathub-banner {
      height: 310px;
      border-radius: 12px;
      overflow: hidden;
      position: relative;
      display: flex;
      align-items: center;
      padding: 0 48px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
      transition: background-color 0.3s ease;
      user-select: none;
    }

    .banner-inner {
      width: 100%;
      height: 100%;
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 32px;
    }

    .banner-left {
      width: 35%;
      min-width: 280px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      z-index: 2;
    }

    .banner-logo-wrap {
      width: 110px;
      height: 110px;
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      filter: drop-shadow(0 10px 14px rgba(0,0,0,0.35));
    }

    .banner-logo {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }

    .banner-app-name {
      margin-top: 12px;
      font-size: 1.6rem;
      font-weight: 900;
      letter-spacing: -0.02em;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
      transition: color 0.2s;
    }

    .banner-summary {
      margin-top: 4px;
      font-size: 0.85rem;
      font-weight: 500;
      line-height: 1.35;
      opacity: 0.9;
      max-width: 320px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      transition: color 0.2s;
    }

    .banner-right {
      flex: 1;
      height: 100%;
      position: relative;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .banner-screenshot {
      position: absolute;
      top: 40px;
      width: 95%;
      max-width: 680px;
      border-radius: 10px;
      box-shadow: 0 20px 40px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.15);
    }

    /* Text contrast classes mimicking Flathub */
    .text-flathub-dark { color: #241f31 !important; }
    .text-flathub-light { color: #f6f8fa !important; }

    /* Code Snippet Box */
    .code-box {
      background: #090c0f;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.85rem;
      position: relative;
    }

    .code-box pre {
      overflow-x: auto;
      color: #38bdf8;
    }

    .toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #22c55e;
      color: #fff;
      padding: 12px 20px;
      border-radius: 8px;
      font-weight: 700;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      transform: translateY(100px);
      opacity: 0;
      transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
      z-index: 999;
    }
    .toast.show {
      transform: translateY(0);
      opacity: 1;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title-area">
        <h1>🐯 Flathub Banner Preview</h1>
        <p>Curated brand color candidates and real-time simulator for <strong>Bengal Download Manager</strong> on Flathub</p>
      </div>
      <div class="links-area">
        <a href="https://flathub.org/en/apps/bd.com.zihad.BengalDownloadManager/bannerpreview" target="_blank" rel="noopener" class="btn-link">
          🌐 Official Flathub Preview Link ↗
        </a>
      </div>
    </header>

    <!-- Presets Section -->
    <div class="section-title">✨ Curated Color Palettes (Click to Preview)</div>
    <div class="presets-grid" id="presetsGrid"></div>

    <!-- Live Controls Bar -->
    <div class="controls-panel">
      <div class="pickers-group">
        <div class="picker-item">
          <span class="picker-label">☀️ Light Theme:</span>
          <div class="color-input-wrapper">
            <input type="color" id="lightPicker" value="#ea580c">
            <input type="text" id="lightHex" class="hex-input" value="#ea580c" maxlength="7">
          </div>
        </div>

        <div class="picker-item">
          <span class="picker-label">🌙 Dark Theme:</span>
          <div class="color-input-wrapper">
            <input type="color" id="darkPicker" value="#7c2d12">
            <input type="text" id="darkHex" class="hex-input" value="#7c2d12" maxlength="7">
          </div>
        </div>
      </div>

      <div class="apply-actions">
        <button class="btn-apply" id="btnApply" onclick="applyBranding()">
          💾 Apply to metainfo.xml
        </button>
      </div>
    </div>

    <!-- Live Banners Display -->
    <div class="previews-section">
      <!-- Light Banner Preview -->
      <div class="preview-box">
        <div class="preview-header">
          <span class="preview-badge badge-light">☀️ Flathub Light Mode Banner</span>
          <span class="contrast-info" id="lightContrastText">Contrast: Calculating...</span>
        </div>
        <div class="flathub-banner" id="lightBanner" style="background-color: #ea580c;">
          <div class="banner-inner">
            <div class="banner-left">
              <div class="banner-logo-wrap">
                <img src="/assets/logo.png" alt="Bengal Download Manager" class="banner-logo">
              </div>
              <div class="banner-app-name" id="lightTitle">Bengal Download Manager</div>
              <div class="banner-summary" id="lightSummary">High-speed multi-threaded download manager powered by Aria2</div>
            </div>
            <div class="banner-right">
              <img src="/assets/screenshots/01-main-app.webp" alt="App Screenshot" class="banner-screenshot">
            </div>
          </div>
        </div>
      </div>

      <!-- Dark Banner Preview -->
      <div class="preview-box">
        <div class="preview-header">
          <span class="preview-badge badge-dark">🌙 Flathub Dark Mode Banner</span>
          <span class="contrast-info" id="darkContrastText">Contrast: Calculating...</span>
        </div>
        <div class="flathub-banner" id="darkBanner" style="background-color: #7c2d12;">
          <div class="banner-inner">
            <div class="banner-left">
              <div class="banner-logo-wrap">
                <img src="/assets/logo.png" alt="Bengal Download Manager" class="banner-logo">
              </div>
              <div class="banner-app-name" id="darkTitle">Bengal Download Manager</div>
              <div class="banner-summary" id="darkSummary">High-speed multi-threaded download manager powered by Aria2</div>
            </div>
            <div class="banner-right">
              <img src="/assets/screenshots/01-main-app.webp" alt="App Screenshot" class="banner-screenshot">
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- AppStream XML Code Block -->
    <div class="section-title">📄 Generated AppStream MetaInfo XML (&lt;branding&gt;)</div>
    <div class="code-box">
      <pre id="xmlSnippet"></pre>
    </div>
  </div>

  <div class="toast" id="toast">Branding applied successfully!</div>

  <script>
    const PRESETS = [
      {
        name: "Royal Bengal Tiger (Signature)",
        light: "#ea580c",
        dark: "#7c2d12",
        desc: "Signature tiger orange with deep ember terracotta."
      },
      {
        name: "Amber Flame & Midnight",
        light: "#f59e0b",
        dark: "#78350f",
        desc: "Golden amber paired with rich espresso."
      },
      {
        name: "Plasma Cyan & Deep Navy",
        light: "#0ea5e9",
        dark: "#0f172a",
        desc: "Aria2 turbo speed cyan and plasma dark navy."
      },
      {
        name: "Sunset Blaze & Burnt Umber",
        light: "#f97316",
        dark: "#431407",
        desc: "Vibrant sunset orange with dark roast umber."
      },
      {
        name: "KDE Breeze Blue & Slate",
        light: "#3daee9",
        dark: "#1e293b",
        desc: "Native desktop KDE Breeze blue and slate."
      },
      {
        name: "Turbo Crimson & Cocoa",
        light: "#dc2626",
        dark: "#450a0a",
        desc: "High-octane red with rich dark cocoa."
      }
    ];

    let currentLight = "#ea580c";
    let currentDark = "#7c2d12";

    // Relative luminance calculation according to WCAG / Flathub getContrastColor
    function getLuminance(hex) {
      hex = hex.replace("#", "");
      if (hex.length === 3) {
        hex = hex.split("").map(c => c + c).join("");
      }
      const r = parseInt(hex.substr(0, 2), 16) / 255;
      const g = parseInt(hex.substr(2, 2), 16) / 255;
      const b = parseInt(hex.substr(4, 2), 16) / 255;
      const a = [r, g, b].map(v => {
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
    }

    function getTextColorClass(hex) {
      // If relative luminance is bright, Flathub uses dark text (#241f31), else lotion light text (#f6f8fa)
      return getLuminance(hex) > 0.45 ? "text-flathub-dark" : "text-flathub-light";
    }

    function updateView() {
      // Update light banner
      const lightBanner = document.getElementById("lightBanner");
      lightBanner.style.backgroundColor = currentLight;
      const lightClass = getTextColorClass(currentLight);
      document.getElementById("lightTitle").className = `banner-app-name ${lightClass}`;
      document.getElementById("lightSummary").className = `banner-summary ${lightClass}`;
      document.getElementById("lightContrastText").textContent =
        `Luminance: ${getLuminance(currentLight).toFixed(2)} (${lightClass === "text-flathub-dark" ? "Dark text #241f31" : "Light text #f6f8fa"})`;

      // Update dark banner
      const darkBanner = document.getElementById("darkBanner");
      darkBanner.style.backgroundColor = currentDark;
      const darkClass = getTextColorClass(currentDark);
      document.getElementById("darkTitle").className = `banner-app-name ${darkClass}`;
      document.getElementById("darkSummary").className = `banner-summary ${darkClass}`;
      document.getElementById("darkContrastText").textContent =
        `Luminance: ${getLuminance(currentDark).toFixed(2)} (${darkClass === "text-flathub-dark" ? "Dark text #241f31" : "Light text #f6f8fa"})`;

      // Inputs
      document.getElementById("lightPicker").value = currentLight;
      document.getElementById("lightHex").value = currentLight;
      document.getElementById("darkPicker").value = currentDark;
      document.getElementById("darkHex").value = currentDark;

      // Update XML snippet
      const xml = `<branding>\n  <color type="primary" scheme_preference="light">${currentLight}</color>\n  <color type="primary" scheme_preference="dark">${currentDark}</color>\n</branding>`;
      document.getElementById("xmlSnippet").textContent = xml;
    }

    function initPresets() {
      const container = document.getElementById("presetsGrid");
      PRESETS.forEach((preset, idx) => {
        const card = document.createElement("div");
        card.className = `preset-card ${idx === 0 ? "active" : ""}`;
        card.onclick = () => {
          document.querySelectorAll(".preset-card").forEach(c => c.classList.remove("active"));
          card.classList.add("active");
          currentLight = preset.light;
          currentDark = preset.dark;
          updateView();
        };

        card.innerHTML = `
          <div class="preset-swatches">
            <div class="swatch" style="background-color: ${preset.light}"></div>
            <div class="swatch" style="background-color: ${preset.dark}"></div>
          </div>
          <div class="preset-name">${preset.name}</div>
          <div class="preset-hexes">${preset.light} / ${preset.dark}</div>
        `;
        container.appendChild(card);
      });
    }

    // Input event listeners
    document.getElementById("lightPicker").addEventListener("input", (e) => {
      currentLight = e.target.value;
      document.querySelectorAll(".preset-card").forEach(c => c.classList.remove("active"));
      updateView();
    });

    document.getElementById("lightHex").addEventListener("change", (e) => {
      let val = e.target.value;
      if (!val.startsWith("#")) val = "#" + val;
      if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
        currentLight = val.toLowerCase();
        document.querySelectorAll(".preset-card").forEach(c => c.classList.remove("active"));
        updateView();
      }
    });

    document.getElementById("darkPicker").addEventListener("input", (e) => {
      currentDark = e.target.value;
      document.querySelectorAll(".preset-card").forEach(c => c.classList.remove("active"));
      updateView();
    });

    document.getElementById("darkHex").addEventListener("change", (e) => {
      let val = e.target.value;
      if (!val.startsWith("#")) val = "#" + val;
      if (/^#[0-9A-Fa-f]{6}$/.test(val)) {
        currentDark = val.toLowerCase();
        document.querySelectorAll(".preset-card").forEach(c => c.classList.remove("active"));
        updateView();
      }
    });

    async function applyBranding() {
      const btn = document.getElementById("btnApply");
      btn.disabled = true;
      btn.textContent = "⏳ Applying...";

      try {
        const res = await fetch("/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ light: currentLight, dark: currentDark })
        });
        const data = await res.json();
        if (data.success) {
          showToast("✓ " + data.message);
        } else {
          showToast("❌ Error: " + (data.error || "Failed to apply"));
        }
      } catch (err) {
        showToast("❌ Network error: " + err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = "💾 Apply to metainfo.xml";
      }
    }

    function showToast(msg) {
      const toast = document.getElementById("toast");
      toast.textContent = msg;
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 4000);
    }

    // Initialize
    initPresets();
    updateView();
  </script>
</body>
</html>
"""


class PreviewHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
            return

        # Serve local assets
        clean_path = self.path.split("?")[0].lstrip("/")
        file_path = REPO_ROOT / clean_path
        if file_path.is_file() and str(file_path.resolve()).startswith(str(REPO_ROOT)):
            mime_type, _ = mimetypes.guess_type(str(file_path))
            self.send_response(200)
            self.send_header("Content-Type", mime_type or "application/octet-stream")
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.end_headers()
            with open(file_path, "rb") as f:
                self.wfile.write(f.read())
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"404 Not Found")

    def do_POST(self):
        if self.path == "/apply":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                light_color = data.get("light", "").strip()
                dark_color = data.get("dark", "").strip()

                if not re.match(r"^#[0-9a-fA-F]{6}$", light_color) or not re.match(
                    r"^#[0-9a-fA-F]{6}$", dark_color
                ):
                    self._send_json(
                        {"success": False, "error": "Invalid hex color format (expected #RRGGBB)."}
                    )
                    return

                # Read metainfo.xml
                content = METAINFO_PATH.read_text(encoding="utf-8")

                branding_xml = f"""  <branding>
    <color type="primary" scheme_preference="light">{light_color}</color>
    <color type="primary" scheme_preference="dark">{dark_color}</color>
  </branding>"""

                if "<branding>" in content:
                    # Replace existing
                    content = re.sub(
                        r"<branding>.*?</branding>",
                        branding_xml.strip(),
                        content,
                        flags=re.DOTALL,
                    )
                else:
                    # Insert after <project_license>
                    if "<project_license>" in content:
                        content = re.sub(
                            r"(<project_license>.*?</project_license>)",
                            r"\1\n" + branding_xml,
                            content,
                        )
                    else:
                        content = re.sub(
                            r"(<component[^>]*>)",
                            r"\1\n" + branding_xml,
                            content,
                        )

                METAINFO_PATH.write_text(content, encoding="utf-8")

                # Validate with appstreamcli if installed
                validation_msg = "Saved branding to metainfo.xml."
                try:
                    res = subprocess.run(
                        ["appstreamcli", "validate", "--no-net", str(METAINFO_PATH)],
                        capture_output=True,
                        text=True,
                    )
                    if res.returncode == 0:
                        validation_msg += " (appstreamcli validation passed successfully!)"
                    else:
                        validation_msg += f" (appstreamcli warning: {res.stderr.strip()})"
                except Exception:
                    pass

                self._send_json({"success": True, "message": validation_msg})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)})
            return

        self.send_response(404)
        self.end_headers()

    def _send_json(self, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        # Clean logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


def run_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), PreviewHandler) as httpd:
        print(f"\n=======================================================")
        print(f"🚀 Flathub Banner Preview Server running at:")
        print(f"   👉 http://127.0.0.1:{PORT}")
        print(f"=======================================================\n")
        print(f"Press Ctrl+C to stop the server.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")


if __name__ == "__main__":
    run_server()

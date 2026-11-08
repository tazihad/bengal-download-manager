/* Bengal Download Manager — Shared Site JavaScript */
/* Handles theme, data loading, rendering, tabs, copy, lightbox, FAQ */

const SITE_ROOT = "";

// ---------- Path helpers (pages live at root and in privacy/ subdir) ----------
// Detect subpages by checking if the last non-empty path segment is a known subdir,
// not by depth — depth check breaks on GitHub Pages where the repo name adds an extra segment.
const _pathParts = window.location.pathname.split("/").filter(Boolean);
const _KNOWN_SUBDIRS = ["privacy", "preview"];
const IS_SUBPAGE = _pathParts.some(seg => _KNOWN_SUBDIRS.includes(seg));
const ASSET_BASE = IS_SUBPAGE ? "../" : "";

function asset(path) {
  return ASSET_BASE + path;
}

// ---------- Data loading (inline page data, no fetch waterfall) ----------
function getInlineData(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  try {
    return JSON.parse(el.textContent);
  } catch (e) {
    console.warn("Failed to parse inline data #" + id + ":", e);
    return null;
  }
}

let siteData = {};
let contentData = {};
let installData = {};

function initData() {
  siteData = getInlineData("site-data") || {};
  contentData = getInlineData("content-data") || {};
  installData = getInlineData("install-data") || {};
}

// ---------- Theme switching ----------
const themeToggle = document.getElementById("theme-toggle");
const themeColorMeta = document.getElementById("theme-color-meta");

function getStoredTheme() {
  try {
    return localStorage.getItem("bdm-theme");
  } catch (e) {
    return null;
  }
}

function applyTheme(theme, persist) {
  document.documentElement.setAttribute("data-theme", theme);
  if (themeColorMeta) {
    themeColorMeta.setAttribute("content", theme === "dark" ? "#0f172a" : "#ffffff");
  }
  if (themeToggle) {
    const next = theme === "dark" ? "light" : "dark";
    themeToggle.setAttribute("aria-label", "Switch to " + next + " theme");
    themeToggle.setAttribute("title", "Switch to " + next + " theme");
  }
  if (persist) {
    try {
      localStorage.setItem("bdm-theme", theme);
    } catch (e) {}
  }
}

function initTheme() {
  if (themeToggle) {
    applyTheme(document.documentElement.getAttribute("data-theme") || "light", false);
    themeToggle.addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next, true);
    });
  }

  const darkModeQuery = window.matchMedia("(prefers-color-scheme: dark)");
  function handleSystemThemeChange(event) {
    if (!getStoredTheme()) {
      applyTheme(event.matches ? "dark" : "light", false);
    }
  }
  if (darkModeQuery.addEventListener) {
    darkModeQuery.addEventListener("change", handleSystemThemeChange);
  } else if (darkModeQuery.addListener) {
    darkModeQuery.addListener(handleSystemThemeChange);
  }
}

// ---------- Render: site shell (nav, footer) ----------
function renderSiteShell() {
  const data = siteData || {};

  // Brand
  const brandLinks = document.querySelectorAll(".brand");
  if (data.brand) {
    brandLinks.forEach(el => {
      el.innerHTML = '<img src="' + asset(data.brand.logo || "assets/logo.png") + '" alt="" />'
        + '<strong>' + (data.brand.name || "Bengal Download Manager") + '</strong>'
        + (data.brand.tagline ? ' <span>' + data.brand.tagline + '</span>' : '');
    });
  }

  // Nav links
  const navList = document.querySelector(".nav-links");
  if (navList && data.nav) {
    navList.innerHTML = data.nav.map(item => '<li><a href="' + item.href + '">' + item.label + '</a></li>').join("");
  }

  // Nav actions: only update the GitHub button; leave the theme toggle untouched
  const githubBtn = document.querySelector(".nav-actions .github-btn");
  if (githubBtn && data.actions && data.actions[0]) {
    githubBtn.href = data.actions[0].href;
    githubBtn.textContent = "★ " + data.actions[0].label;
  }

  // Footer brand
  const footerBrand = document.querySelector(".footer-brand");
  if (footerBrand && data.footer && data.brand) {
    footerBrand.innerHTML = '<img src="' + asset(data.brand.logo || "assets/logo.png") + '" alt="" />'
      + '<span>' + (data.footer.brandName || "Bengal Download Manager") + '</span>';
  }

  const footerText = document.querySelector(".footer-text");
  if (footerText && data.footer) {
    footerText.textContent = data.footer.brandText || "A fast, native download manager for Linux.";
  }

  // Footer download links
  const footerDownload = document.querySelector(".footer-links");
  // There are multiple .footer-links; handle by index
  const linkLists = document.querySelectorAll(".footer-links");
  if (linkLists[0] && data.footer && data.footer.download) {
    linkLists[0].innerHTML = data.footer.download.map(item =>
      '<li><a href="' + item.href + '"' + (item.external ? ' target="_blank" rel="noopener"' : "") + '>' + item.label + '</a></li>'
    ).join("");
  }
  if (linkLists[1] && data.footer && data.footer.project) {
    linkLists[1].innerHTML = data.footer.project.map(item =>
      '<li><a href="' + item.href + '"' + (item.external ? ' target="_blank" rel="noopener"' : "") + '>' + item.label + '</a></li>'
    ).join("");
  }

  // Footer bottom
  const bottomSpans = document.querySelectorAll(".footer-bottom span");
  if (bottomSpans[0] && data.footer) bottomSpans[0].textContent = data.footer.bottomLeft || "© 2026 Bengal Download Manager Contributors";
  if (bottomSpans[1] && data.footer) bottomSpans[1].textContent = data.footer.bottomRight || "Made for Linux. No ads, no telemetry.";
}

// ---------- Render: hero ----------
function renderHero() {
  const h = contentData.hero;
  if (!h) return;

  const eyebrow = document.querySelector(".hero-eyebrow");
  if (eyebrow) eyebrow.textContent = h.eyebrow;

  const h1 = document.querySelector(".hero h1");
  if (h1) h1.textContent = h.title;

  const desc = document.querySelector(".hero-desc");
  if (desc) desc.textContent = h.desc;

  const primaryBtn = document.querySelector(".hero-actions .btn-primary");
  if (primaryBtn && h.primaryBtn) {
    primaryBtn.textContent = h.primaryBtn.label;
    primaryBtn.href = h.primaryBtn.href;
  }

  const secondaryBtn = document.querySelector(".hero-actions .btn-secondary");
  if (secondaryBtn && h.secondaryBtn) {
    secondaryBtn.textContent = h.secondaryBtn.label;
    secondaryBtn.href = h.secondaryBtn.href;
    secondaryBtn.target = h.secondaryBtn.external ? "_blank" : "";
    secondaryBtn.rel = h.secondaryBtn.external ? "noopener" : "";
  }

  // Available on meta
  const meta1 = document.querySelector(".hero-meta");
  if (meta1 && h.availableOn) {
    const items = h.availableOn.map((item, i) =>
      '<a href="' + item.href + '"' + (item.external ? ' target="_blank" rel="noopener"' : "") + '>' + item.label + '</a>' + (i < h.availableOn.length - 1 ? ' <span class="sep">·</span>' : "")
    ).join("");
    meta1.innerHTML = 'Available on ' + items;
  }

  // Browser extensions meta
  const meta2 = document.querySelector(".hero-extensions");
  if (meta2 && h.browserExtensions) {
    const items = h.browserExtensions.map((item, i) =>
      '<a href="' + item.href + '" target="_blank" rel="noopener">' + item.label + '</a>' + (i < h.browserExtensions.length - 1 ? " and " : "")
    ).join("");
    meta2.innerHTML = 'Browser extensions for ' + items + ".";
  }

  // Figure
  const figureImg = document.querySelector(".hero-figure img");
  if (figureImg && h.figure) {
    figureImg.src = h.figure.image;
    figureImg.alt = h.title + " main window";
  }
  const figureCaption = document.querySelector(".hero-figure figcaption");
  if (figureCaption && h.figure) figureCaption.textContent = h.figure.caption;
  const figureLink = document.querySelector(".hero-figure a");
  if (figureLink && h.figure) {
    figureLink.setAttribute("onclick", "openLightbox('" + h.figure.image + "'); return false;");
  }
}

// ---------- Render: metrics ----------
function renderMetrics() {
  const metrics = contentData.metrics;
  if (!metrics) return;

  const container = document.querySelector(".metrics");
  if (!container) return;

  container.innerHTML = metrics.map(m =>
    '<div>'
    + '<div class="metric-value font-mono">' + m.value + '</div>'
    + '<div class="metric-label">' + m.label + '</div>'
    + '<div class="metric-sub">' + m.sub + '</div>'
    + '</div>'
  ).join("");
}

// ---------- Render: features ----------
function renderFeatures() {
  const features = contentData.features;
  if (!features) return;

  const grid = document.querySelector(".features-grid");
  if (!grid) return;

  grid.innerHTML = features.map(f =>
    '<article class="feature-card">'
    + '<svg class="feature-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    + '<path d="' + f.icon + '" />'
    + '</svg>'
    + '<h3 class="feature-title">' + f.title + '</h3>'
    + '<p class="feature-text">' + f.text + '</p>'
    + '</article>'
  ).join("");
}

// ---------- Render: screenshots ----------
function renderScreenshots() {
  const screenshots = contentData.screenshots;
  if (!screenshots) return;

  const grid = document.querySelector(".screenshots-grid");
  if (!grid) return;

  grid.innerHTML = screenshots.map(s =>
    '<a class="screenshot-card" href="' + s.image + '" onclick="openLightbox(\'' + s.image + '\'); return false;">'
    + '<div class="screenshot-canvas"><img src="' + s.image + '" alt="' + s.title + '" /></div>'
    + '<div class="screenshot-caption">'
    + '<span class="screenshot-title">' + s.title + '</span>'
    + '<span class="screenshot-badge">' + s.badge + '</span>'
    + '</div>'
    + '</a>'
  ).join("");
}

// ---------- Render: install ----------
function renderInstall() {
  const idata = contentData.install;
  const inst = installData || {};
  if (!idata) return;

  const eyebrow = document.querySelector("#install .section-eyebrow");
  if (eyebrow) eyebrow.textContent = idata.eyebrow;

  const title = document.querySelector("#install .section-title");
  if (title) title.textContent = idata.title;

  const desc = document.querySelector("#install .section-desc");
  if (desc) desc.textContent = idata.desc;

  // Nav tabs
  const nav = document.querySelector(".install-nav");
  if (nav && inst) {
    const tabs = Object.keys(inst);
    nav.innerHTML = tabs.map((key, i) =>
      '<button class="install-nav-btn' + (i === 0 ? " active" : "") + '" role="tab" aria-selected="' + (i === 0) + '" data-tab="' + key + '" onclick="switchTab(\'' + key + '\', this)">' + inst[key].title + '</button>'
    ).join("");
  }

  // Tab panels
  const panels = document.querySelector(".install-tab-panels");
  if (!panels) return;

  let html = "";
  const keys = Object.keys(inst);
  keys.forEach((key, idx) => {
    const m = inst[key];
    const active = idx === 0 ? " active" : "";
    html += '<div id="tab-' + key + '" class="install-body' + active + '" role="tabpanel">';

    if (m.storeRow) {
      html += '<div class="store-row">';
      html += '<a href="' + m.storeRow.badgeLink + '" target="_blank" rel="noopener">';
      html += '<img alt="Get it on ' + m.title + '" src="' + m.storeRow.badgeUrl + '" />';
      html += '</a>';
      html += '<span class="install-note">' + m.storeRow.note + '</span>';
      html += '</div>';
    }

    if (key === "flatpak") {
      // Flathub install
      html += '<div class="field-label" style="margin-bottom: 8px;">Install from Flathub</div>';
      html += '<div class="cli-box">';
      html += '<button class="copy-btn" onclick="copyCode(\'' + m.flathubCmd.replace(/'/g, "\\'") + '\', this)">Copy</button>';
      html += '<code><span class="cli-prompt">$</span>' + m.flathubCmd + '</code>';
      html += '</div>';

      html += '<hr class="divider" />';

      html += '<div class="field-label" style="margin: 20px 0 8px;">Install from direct repository</div>';
      html += '<div style="margin-bottom: 16px;">';
      html += '<div class="install-heading">' + m.directRepo.heading + '</div>';
      html += '<p class="install-lead">' + m.directRepo.lead + '</p>';
      html += '</div>';
      html += '<div style="margin-bottom: 20px;">';
      html += '<a href="' + m.directRepo.flatpakrefLink + '" class="custom-store-badge">';
      html += '<img src="' + m.directRepo.flatpakrefBadge + '" alt="" class="store-badge-icon" />';
      html += '<div class="text-container">';
      html += '<div class="store-pre-title">' + m.directRepo.flatpakrefPreTitle + '</div>';
      html += '<div class="store-title">' + m.directRepo.flatpakrefTitle + '</div>';
      html += '</div>';
      html += '</a>';
      html += '</div>';

      m.options.forEach((opt, oi) => {
        if (oi === 0) {
          html += '<div class="field-label" style="margin-bottom: 8px;">' + opt.label + '</div>';
          html += '<div class="cli-box">';
          html += '<button class="copy-btn" onclick="copyCode(\'' + opt.cmd.replace(/'/g, "\\'") + '\', this)">Copy</button>';
          html += '<code><span class="cli-prompt">$</span>' + opt.cmd + '</code>';
          html += '</div>';
        } else if (oi === 1) {
          html += '<div class="field-label" style="margin: 20px 0 8px;">' + opt.label + '</div>';
          opt.cmds.forEach((c, ci) => {
            html += '<div class="cli-box">';
            html += '<button class="copy-btn" onclick="copyCode(\'' + c.replace(/'/g, "\\'") + '\', this)">Copy</button>';
            html += '<code><span class="cli-prompt">$</span>' + c + '</code>';
            html += '</div>';
          });
        }
      });

      html += '<hr class="divider" />';
      html += '<p class="install-foot"><a href="' + m.footUrl + '" target="_blank" rel="noopener">' + m.foot + '</a></p>';
    } else if (key === "snap") {
      html += '<div class="cli-box">';
      html += '<button class="copy-btn" onclick="copyCode(\'' + m.cmd.replace(/'/g, "\\'") + '\', this)">Copy</button>';
      html += '<code><span class="cli-prompt">$</span>' + m.cmd + '</code>';
      html += '</div>';
      html += '<p class="install-foot"><a href="' + m.footUrl + '" target="_blank" rel="noopener">' + m.foot + '</a></p>';
    } else if (key === "appimage") {
      html += '<div style="margin-bottom: 18px;">';
      html += '<div class="install-heading">' + m.heading + '</div>';
      html += '<p class="install-lead">' + m.lead + '</p>';
      html += '</div>';
      html += '<div style="margin-bottom: 18px;">';
      html += '<label class="field-label" for="arch-select">' + m.archSelect.label + '</label>';
      html += '<select id="arch-select" class="arch-select" onchange="onArchChange(this.value)">';
      m.archSelect.options.forEach(o => {
        html += '<option value="' + o.value + '"' + (o.value === "x86_64" ? " selected" : "") + '>' + o.label + '</option>';
      });
      html += '</select>';
      html += '</div>';
      html += '<div style="margin-bottom: 24px;">';
      html += '<a id="appimage-main-btn" href="' + m.badge.link + '" target="_blank" rel="noopener noreferrer" class="custom-store-badge" title="Download AppImage">';
      html += '<img src="' + m.badge.image + '" alt="" class="store-badge-icon" />';
      html += '<div class="text-container">';
      html += '<div class="store-pre-title">' + m.badge.preTitle + '</div>';
      html += '<div class="store-title" id="appimage-main-label">' + m.badge.title + '</div>';
      html += '</div>';
      html += '</a>';
      html += '</div>';
      html += '<div class="field-label" id="appimage-cmd-title" style="margin-bottom: 8px;">Terminal quick-start (x86_64 64-bit Intel / AMD)</div>';
      html += '<div class="cli-box">';
      html += '<button id="copy-appimage-curl-btn" class="copy-btn" onclick="copyAppImageCurl(this)">Copy</button>';
      html += '<code id="appimage-curl-cmd"><span class="cli-prompt">$</span>' + m.curlCmd + '</code>';
      html += '</div>';
      html += '<div class="cli-box">';
      html += '<button id="copy-appimage-run-btn" class="copy-btn" onclick="copyAppImageRun(this)">Copy</button>';
      html += '<code id="appimage-run-cmd"><span class="cli-prompt">$</span>' + m.runCmd + '</code>';
      html += '</div>';
      html += '<p class="install-foot"><a href="' + m.footUrl + '" target="_blank" rel="noopener">' + m.foot + '</a></p>';
    } else if (key === "deb" || key === "rpm") {
      const prefix = key === "deb" ? "deb" : "rpm";
      html += '<div style="margin-bottom: 18px;">';
      html += '<div class="install-heading">' + m.heading + '</div>';
      html += '<p class="install-lead">' + m.lead + '</p>';
      html += '</div>';
      html += '<div style="margin-bottom: 18px;">';
      html += '<label class="field-label" for="' + prefix + '-arch-select">' + m.archSelect.label + '</label>';
      html += '<select id="' + prefix + '-arch-select" class="arch-select" onchange="onArchChange(this.value)">';
      m.archSelect.options.forEach(o => {
        html += '<option value="' + o.value + '"' + (o.value === "x86_64" ? " selected" : "") + '>' + o.label + '</option>';
      });
      html += '</select>';
      html += '</div>';
      html += '<div style="margin-bottom: 24px;">';
      html += '<a id="' + prefix + '-main-btn" href="' + m.badge.link + '" target="_blank" rel="noopener noreferrer" class="custom-store-badge" title="Download ' + key.toUpperCase() + ' package">';
      html += '<span class="fmt-icon" aria-hidden="true">' + m.badge.icon + '</span>';
      html += '<div class="text-container">';
      html += '<div class="store-pre-title">' + m.badge.preTitle + '</div>';
      html += '<div class="store-title" id="' + prefix + '-main-label">' + m.badge.title + '</div>';
      html += '</div>';
      html += '</a>';
      html += '</div>';
      html += '<div class="field-label" style="margin-bottom: 8px;">Step 1: ' + m.step1 + '</div>';
      html += '<div class="cli-box">';
      html += '<button id="copy-' + prefix + '-curl-btn" class="copy-btn" onclick="copy' + prefix.toUpperCase() + 'Curl(this)">Copy</button>';
      html += '<code id="' + prefix + '-curl-cmd"><span class="cli-prompt">$</span>' + m.step1Cmd + '</code>';
      html += '</div>';
      html += '<div class="field-label" style="margin: 18px 0 8px;">Step 2: ' + m.step2 + '</div>';
      html += '<div class="cli-box">';
      html += '<button id="copy-' + prefix + '-btn" class="copy-btn" onclick="copy' + prefix.toUpperCase() + 'Install(this)">Copy</button>';
      html += '<code id="' + prefix + '-install-cmd"><span class="cli-prompt">$</span>' + m.step2Cmd + '</code>';
      html += '</div>';
      html += '<p class="install-foot"><a href="' + m.footUrl + '" target="_blank" rel="noopener">' + m.foot + '</a></p>';
    }

    html += '</div>';
  });
  panels.innerHTML = html;
}

// ---------- Release data (for install method commands) ----------
const releaseData = {
  version: "v0.3.14",
  x86_64: {
    appimage: { filename: "bengal-download-manager-0.3.14-x86_64.AppImage", url: "https://github.com/tazihad/bengal-download-manager/releases/download/v0.3.14/bengal-download-manager-0.3.14-x86_64.AppImage" },
    deb: { filename: "bengal-download-manager-0.3.14-x86_64.deb", url: "https://github.com/tazihad/bengal-download-manager/releases/download/v0.3.14/bengal-download-manager-0.3.14-x86_64.deb" },
    rpm: { filename: "bengal-download-manager-0.3.14-x86_64.rpm", url: "https://github.com/tazihad/bengal-download-manager/releases/download/v0.3.14/bengal-download-manager-0.3.14-x86_64.rpm" }
  },
  aarch64: {
    appimage: { filename: "bengal-download-manager-0.3.14-aarch64.AppImage", url: "https://github.com/tazihad/bengal-download-manager/releases/download/v0.3.14/bengal-download-manager-0.3.14-aarch64.AppImage" },
    deb: { filename: "bengal-download-manager-0.3.14-aarch64.deb", url: "https://github.com/tazihad/bengal-download-manager/releases/download/v0.3.14/bengal-download-manager-0.3.14-aarch64.deb" },
    rpm: { filename: "bengal-download-manager-0.3.14-aarch64.rpm", url: "https://github.com/tazihad/bengal-download-manager/releases/download/v0.3.14/bengal-download-manager-0.3.14-aarch64.rpm" }
  }
};

const archLabels = {
  x86_64: "x86_64 64-bit Intel / AMD",
  aarch64: "aarch64 64-bit ARM"
};

function currentRelease(arch, format) {
  const entry = releaseData[arch] || releaseData.x86_64;
  return entry[format];
}

function getCurrentArch() {
  const select = document.getElementById("arch-select")
    || document.getElementById("deb-arch-select")
    || document.getElementById("rpm-arch-select");
  return select ? select.value : "x86_64";
}

function renderAppImageUI(arch) {
  const current = currentRelease(arch, "appimage");
  const btn = document.getElementById("appimage-main-btn");
  const label = document.getElementById("appimage-main-label");
  const title = document.getElementById("appimage-cmd-title");
  const curlCmd = document.getElementById("appimage-curl-cmd");
  const runCmd = document.getElementById("appimage-run-cmd");

  if (btn) btn.href = current.url;
  if (label) label.textContent = "AppImage (" + arch + ")";
  if (title) title.textContent = "Terminal quick-start (" + archLabels[arch] + ")";
  if (curlCmd) curlCmd.innerHTML = '<span class="cli-prompt">$</span>curl -L -o ' + current.filename + ' ' + current.url;
  if (runCmd) runCmd.innerHTML = '<span class="cli-prompt">$</span>chmod +x ' + current.filename + ' && ./' + current.filename;
}

function renderDebUI(arch) {
  const current = currentRelease(arch, "deb");
  const btn = document.getElementById("deb-main-btn");
  const label = document.getElementById("deb-main-label");
  const curl = document.getElementById("deb-curl-cmd");
  const cmd = document.getElementById("deb-install-cmd");

  if (btn) btn.href = current.url;
  if (label) label.textContent = ".deb (" + arch + ")";
  if (curl) curl.innerHTML = '<span class="cli-prompt">$</span>curl -L -o ' + current.filename + ' ' + current.url;
  if (cmd) cmd.innerHTML = '<span class="cli-prompt">$</span>sudo apt install ./' + current.filename;
}

function renderRpmUI(arch) {
  const current = currentRelease(arch, "rpm");
  const btn = document.getElementById("rpm-main-btn");
  const label = document.getElementById("rpm-main-label");
  const curl = document.getElementById("rpm-curl-cmd");
  const cmd = document.getElementById("rpm-install-cmd");

  if (btn) btn.href = current.url;
  if (label) label.textContent = ".rpm (" + arch + ")";
  if (curl) curl.innerHTML = '<span class="cli-prompt">$</span>curl -L -o ' + current.filename + ' ' + current.url;
  if (cmd) cmd.innerHTML = '<span class="cli-prompt">$</span>sudo dnf install ./' + current.filename;
}

function onArchChange(arch) {
  ["arch-select", "deb-arch-select", "rpm-arch-select"].forEach(id => {
    const select = document.getElementById(id);
    if (select && select.value !== arch) select.value = arch;
  });
  renderAppImageUI(arch);
  renderDebUI(arch);
  renderRpmUI(arch);
}

function copyAppImageCurl(btn) {
  const current = currentRelease(getCurrentArch(), "appimage");
  copyCode("curl -L -o " + current.filename + " " + current.url, btn);
}

function copyAppImageRun(btn) {
  const current = currentRelease(getCurrentArch(), "appimage");
  copyCode("chmod +x " + current.filename + " && ./" + current.filename, btn);
}

function copyDebCurl(btn) {
  const current = currentRelease(getCurrentArch(), "deb");
  copyCode("curl -L -o " + current.filename + " " + current.url, btn);
}

function copyDebInstall(btn) {
  const current = currentRelease(getCurrentArch(), "deb");
  copyCode("sudo apt install ./" + current.filename, btn);
}

function copyRpmCurl(btn) {
  const current = currentRelease(getCurrentArch(), "rpm");
  copyCode("curl -L -o " + current.filename + " " + current.url, btn);
}

function copyRpmInstall(btn) {
  const current = currentRelease(getCurrentArch(), "rpm");
  copyCode("sudo dnf install ./" + current.filename, btn);
}

// Resolve latest release assets from GitHub
(async function resolveReleases() {
  try {
    const res = await fetch("https://api.github.com/repos/tazihad/bengal-download-manager/releases/latest");
    if (!res.ok) return;
    const data = await res.json();
    const assets = data.assets || [];
    const version = data.tag_name || releaseData.version;
    releaseData.version = version;

    function findAsset(extension, arch) {
      const tokens = arch === "x86_64" ? ["x86_64", "amd64"] : ["aarch64", "arm64"];
      return assets.find(a => a.name.endsWith(extension) && tokens.some(token => a.name.includes(token)));
    }

    ["x86_64", "aarch64"].forEach(arch => {
      const appimage = findAsset(".AppImage", arch);
      const deb = findAsset(".deb", arch);
      const rpm = findAsset(".rpm", arch);

      if (appimage) releaseData[arch].appimage = { filename: appimage.name, url: appimage.browser_download_url };
      if (deb) releaseData[arch].deb = { filename: deb.name, url: deb.browser_download_url };
          if (rpm) releaseData[arch].rpm = { filename: rpm.name, url: rpm.browser_download_url };
    });

    onArchChange(getCurrentArch());
  } catch (e) {
    console.warn("Could not resolve release assets from the GitHub API:", e);
  }
})();

// ---------- Install tabs ----------
function switchTab(name, btn) {
  document.querySelectorAll(".install-nav-btn").forEach(b => {
    b.classList.remove("active");
    b.setAttribute("aria-selected", "false");
  });
  document.querySelectorAll(".install-body").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  btn.setAttribute("aria-selected", "true");
  const panel = document.getElementById("tab-" + name);
  if (panel) panel.classList.add("active");
}

function openTabFromHash() {
  const match = (window.location.hash || "").match(/^#tab-(snap|appimage|flatpak|deb|rpm)$/);
  if (!match) return;
  const btn = document.querySelector('.install-nav-btn[data-tab="' + match[1] + '"]');
  if (btn) {
    switchTab(match[1], btn);
    const install = document.getElementById("install");
    if (install) install.scrollIntoView();
  }
}

// ---------- Copy to clipboard ----------
function copyCode(text, btn) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      const old = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(() => { btn.textContent = old; }, 2000);
    }).catch(() => fallbackCopy(text, btn));
  } else {
    fallbackCopy(text, btn);
  }
}

function fallbackCopy(text, btn) {
  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  try {
    document.execCommand("copy");
    const old = btn.textContent;
    btn.textContent = "Copied";
    setTimeout(() => { btn.textContent = old; }, 2000);
  } catch (err) {
    console.error("Fallback copy failed", err);
  }
  document.body.removeChild(textArea);
}

// ---------- FAQ ----------
function toggleFaq(btn) {
  const card = btn.parentElement;
  const isOpen = card.classList.contains("open");
  document.querySelectorAll(".faq-card").forEach(c => c.classList.remove("open"));
  if (!isOpen) card.classList.add("open");
}

function renderFAQ() {
  const faq = contentData.faq;
  if (!faq) return;

  const eyebrow = document.querySelector("#faq .section-eyebrow");
  if (eyebrow) eyebrow.textContent = faq.eyebrow;

  const title = document.querySelector("#faq .section-title");
  if (title) title.textContent = faq.title;

  const desc = document.querySelector("#faq .section-desc");
  if (desc) desc.textContent = faq.desc;

  const list = document.querySelector(".faq-list");
  if (!list) return;

  list.innerHTML = faq.items.map(item =>
    '<div class="faq-card">'
    + '<button class="faq-q" onclick="toggleFaq(this)">'
    + '<span>' + item.q + '</span>'
    + '<span class="faq-mark" aria-hidden="true">+</span>'
    + '</button>'
    + '<div class="faq-a">' + item.a + '</div>'
    + '</div>'
  ).join("");
}

// ---------- Lightbox ----------
function openLightbox(src) {
  const img = document.getElementById("lightboxImage");
  const modal = document.getElementById("lightbox");
  if (img) img.src = src;
  if (modal) modal.classList.add("active");
}

function closeLightbox(e) {
  if (e.target.id === "lightbox") {
    const modal = document.getElementById("lightbox");
    if (modal) modal.classList.remove("active");
  }
}

// ---------- Init ----------
document.addEventListener("DOMContentLoaded", () => {
  initData();
  initTheme();
  renderSiteShell();
  renderHero();
  renderMetrics();
  renderFeatures();
  renderScreenshots();
  renderInstall();
  renderFAQ();
  openTabFromHash();
  window.addEventListener("hashchange", openTabFromHash);

  const lightbox = document.getElementById("lightbox");
  if (lightbox) {
    lightbox.addEventListener("click", closeLightbox);
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const modal = document.getElementById("lightbox");
      if (modal) modal.classList.remove("active");
    }
  });
});

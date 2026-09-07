// --- DEDICATED GOOGLE DRIVE HANDLER MODULE ---
// Isolates Google Drive detection, cookie extraction, and virus-scan form resolution
// to ensure standard website downloads are never affected.

function isGoogleDriveUrl(url) {
  if (!url || typeof url !== 'string') return false;
  const u = url.toLowerCase();
  return (
    u.includes('drive.google.com') ||
    u.includes('drive.usercontent.google.com') ||
    u.includes('docs.google.com') ||
    (u.includes('googleusercontent.com') && (u.includes('export=download') || u.includes('id=') || u.includes('/download')))
  );
}

function resolveGoogleDriveConfirmation(htmlText, finalUrl) {
  if (!htmlText) return null;
  // 1. Virus scan warning form
  const formMatch = htmlText.match(/<form[^>]*id=["']download-form["'][^>]*action=["']([^"']+)["'][^>]*>([\s\S]*?)<\/form>/i) ||
                    htmlText.match(/<form[^>]*action=["']([^"']+)["'][^>]*>([\s\S]*?)<\/form>/i);
  if (formMatch) {
    const formAction = formMatch[1].replace(/&amp;/g, '&');
    const formInner = formMatch[2];
    const inputs = [];
    const inputRegex = /<input[^>]*name=["']([^"']+)["'][^>]*value=["']([^"']*)["']/gi;
    let m;
    while ((m = inputRegex.exec(formInner)) !== null) {
      if (m[1] && m[1] !== 'submit') {
        inputs.push(`${encodeURIComponent(m[1])}=${encodeURIComponent(m[2])}`);
      }
    }
    if (inputs.length > 0) {
      const baseUrl = new URL(formAction, finalUrl).href;
      return baseUrl + (baseUrl.includes('?') ? '&' : '?') + inputs.join('&');
    }
  }

  // 2. Direct uc-download-link anchor
  const gdriveConfirmMatch = htmlText.match(/id=["']uc-download-link["'][^>]*href=["']([^"']+)["']/i) ||
                             htmlText.match(/href=["'](\/uc\?export=download&[^"']+)["']/i) ||
                             htmlText.match(/href=["'](https:\/\/[^"']*googleusercontent\.com\/[^"']+)["']/i) ||
                             htmlText.match(/action=["'](https:\/\/[^"']*googleusercontent\.com\/[^"']+)["']/i);
  if (gdriveConfirmMatch && gdriveConfirmMatch[1]) {
    const cleanUrl = gdriveConfirmMatch[1].replace(/&amp;/g, '&').trim();
    return new URL(cleanUrl, finalUrl).href;
  }

  return null;
}

async function getGoogleDriveCookies(targetUrl, storeId, capturedCookieHeader) {
  const cookieMap = new Map();

  // If wire headers captured the actual browser cookie string, parse it first
  if (capturedCookieHeader && typeof capturedCookieHeader === 'string') {
    for (const part of capturedCookieHeader.split(';')) {
      const idx = part.indexOf('=');
      if (idx > 0) {
        const k = part.substring(0, idx).trim();
        const v = part.substring(idx + 1).trim();
        if (k && !cookieMap.has(k)) cookieMap.set(k, v);
      }
    }
    if (cookieMap.has('OSID') || cookieMap.has('__Secure-OSID')) {
      const res = [];
      for (const [k, v] of cookieMap.entries()) res.push(`${k}=${v}`);
      return res.join('; ');
    }
  }

  // Fallback to chrome.cookies API across all Google domains
  if (chrome.cookies && chrome.cookies.getAll) {
    const domains = [
      'drive.usercontent.google.com',
      'drive.google.com',
      'googleusercontent.com',
      'google.com'
    ];

    for (const dom of domains) {
      try {
        const q = { domain: dom };
        if (storeId) q.storeId = storeId;
        const list = await chrome.cookies.getAll(q);
        for (const c of list || []) {
          if (c && c.name && !cookieMap.has(c.name)) {
            cookieMap.set(c.name, c.value || '');
          }
        }
      } catch (e) {}
    }
  }

  const result = [];
  for (const [k, v] of cookieMap.entries()) {
    result.push(`${k}=${v}`);
  }
  return result.join('; ');
}

// Export for module or global background script
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { isGoogleDriveUrl, resolveGoogleDriveConfirmation, getGoogleDriveCookies };
}

// --- DEDICATED GOOGLE DRIVE HANDLER MODULE ---
// Isolates Google Drive detection, cookie extraction, and virus-scan form resolution
// strictly for drive.google.com following the extension v0.3 implementation.

function isGoogleDriveUrl(url) {
  if (!url || typeof url !== 'string') return false;
  const u = url.toLowerCase();
  return u.includes('drive.google.com') || u.includes('drive.usercontent.google.com');
}

// v0.3 Google Drive confirmation form and link resolution
function resolveGoogleDriveConfirmation(htmlText, finalUrl) {
  if (!htmlText) return null;

  // 1. Google Drive download confirmation forms (from v0.3)
  const formMatch = htmlText.match(/<form[^>]*id=["']download-form["'][^>]*action=["']([^"']+)["'][^>]*>([\s\S]*?)<\/form>/i)
                 || htmlText.match(/<form[^>]*action=["']([^"']+)["'][^>]*>([\s\S]*?)<\/form>/i);
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
      const confirmUrl = baseUrl + (baseUrl.includes('?') ? '&' : '?') + inputs.join('&');
      return confirmUrl;
    }
  }

  // 2. Direct uc-download-link or confirmation anchor (from v0.3)
  const gdriveConfirmMatch = htmlText.match(/id=["']uc-download-link["'][^>]*href=["']([^"']+)["']/i)
                          || htmlText.match(/href=["'](\/uc\?export=download&[^"']+)["']/i)
                          || htmlText.match(/href=["'](https:\/\/[^"']*googleusercontent\.com\/[^"']+)["']/i)
                          || htmlText.match(/action=["'](https:\/\/[^"']*googleusercontent\.com\/[^"']+)["']/i);
  if (gdriveConfirmMatch && gdriveConfirmMatch[1]) {
    const cleanUrl = gdriveConfirmMatch[1].replace(/&amp;/g, '&').trim();
    return new URL(cleanUrl, finalUrl).href;
  }

  return null;
}

// Enhanced cookie extraction for Google Drive (v0.3 + wire headers)
async function getGoogleDriveCookies(targetUrl, storeId, capturedCookieHeader) {
  const cookieMap = new Map();

  // 1. If wire headers captured the actual browser cookie string, parse it
  if (capturedCookieHeader && typeof capturedCookieHeader === 'string') {
    for (const part of capturedCookieHeader.split(';')) {
      const idx = part.indexOf('=');
      if (idx > 0) {
        const k = part.substring(0, idx).trim();
        const v = part.substring(idx + 1).trim();
        if (k && !cookieMap.has(k)) cookieMap.set(k, v);
      }
    }
  }

  // 2. Query chrome.cookies for target URL, hostname, and parent domain as in v0.3
  if (chrome.cookies && chrome.cookies.getAll && targetUrl) {
    try {
      const query = { url: targetUrl };
      if (storeId) query.storeId = storeId;
      let cookies = [];
      try {
        cookies = await chrome.cookies.getAll(query);
      } catch (e) {
        delete query.storeId;
        try { cookies = await chrome.cookies.getAll(query); } catch (err) {}
      }

      for (const c of cookies || []) {
        if (c && c.name && !cookieMap.has(c.name)) {
          cookieMap.set(c.name, c.value || '');
        }
      }

      // Query domains for Firefox dFPI and Google Drive sessions
      try {
        const parsed = new URL(targetUrl);
        const domains = [parsed.hostname, 'drive.google.com', 'google.com', 'drive.usercontent.google.com'];

        for (const dom of new Set(domains)) {
          const dQuery = { domain: dom };
          if (storeId) dQuery.storeId = storeId;
          try {
            const domCookies = await chrome.cookies.getAll(dQuery);
            for (const c of domCookies || []) {
              if (c && c.name && !cookieMap.has(c.name)) {
                cookieMap.set(c.name, c.value || '');
              }
            }
          } catch (e) {}
        }
      } catch (e) {}
    } catch (err) {}
  }

  const result = [];
  for (const [k, v] of cookieMap.entries()) {
    result.push(`${k}=${v}`);
  }
  return result.join('; ');
}

// v0.3 Google Drive target resolution logic
async function resolveGoogleDriveDownload(url, userAgent, cookies) {
  if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) {
    return { url, isHtmlLanding: false };
  }

  try {
    const headers = {
      'User-Agent': userAgent || navigator.userAgent,
      'Range': 'bytes=0-30720'
    };
    if (cookies) {
      headers['Cookie'] = cookies;
    }

    const response = await fetch(url, {
      method: 'GET',
      headers: headers,
      redirect: 'follow'
    });

    const finalUrl = response.url || url;
    const contentType = (response.headers.get('content-type') || '').toLowerCase();

    // If direct binary file or non-HTML resource
    if (!contentType.includes('text/html') && !contentType.includes('application/xhtml+xml')) {
      return { url: finalUrl, isHtmlLanding: false };
    }

    const text = await response.text();

    // v0.3 Google Drive confirmation form / link resolution
    const confirmedUrl = resolveGoogleDriveConfirmation(text, finalUrl);
    if (confirmedUrl) {
      return { url: confirmedUrl, isHtmlLanding: false };
    }

    return { url: finalUrl, isHtmlLanding: true };
  } catch (err) {
    console.warn("Could not resolve Google Drive download target:", err);
    return { url, isHtmlLanding: false };
  }
}

// Export for module or global background script
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { isGoogleDriveUrl, resolveGoogleDriveConfirmation, resolveGoogleDriveDownload, getGoogleDriveCookies };
}


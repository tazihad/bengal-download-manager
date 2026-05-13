import os
from urllib.parse import urlparse, unquote
import urllib.request
import urllib.error
from PyQt6.QtCore import QThread, pyqtSignal
from core.utils import load_extension_config

class FileInfoFetcherWorker(QThread):
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
    
    def create_opener(self):
        """Standard opener (uses system proxies if any)."""
        return urllib.request.build_opener()

    def run(self):
        result = {
            "url": self.url,
            "filename": "Unknown",
            "size_str": "Unknown",
            "size_bytes": 0,
            "error": None
        }
        
        try:
            parsed = urlparse(self.url)
            path = unquote(parsed.path)
            basename = os.path.basename(path)
            if basename: 
                result["filename"] = basename
            else:
                result["filename"] = "file"
                
            req = urllib.request.Request(self.url, method='GET') 
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            
            opener = self.create_opener()
            with opener.open(req, timeout=10) as resp:
                content_length = resp.headers.get("Content-Length")
                if content_length and content_length.isdigit():
                    result["size_bytes"] = int(content_length)
                    result["size_str"] = self.format_bytes(result["size_bytes"])
                
                content_disp = resp.headers.get("Content-Disposition")
                header_filename = None
                if content_disp:
                    import re
                    cd_match = re.search(r'filename\*=UTF-8\'\'([^"\';]+)', content_disp, re.IGNORECASE)
                    if not cd_match:
                        cd_match = re.search(r'filename=["\']?([^"\';]+)["\']?', content_disp, re.IGNORECASE)
                    
                    if cd_match:
                        extracted = unquote(cd_match.group(1).strip())
                        if extracted:
                            header_filename = extracted

                is_garbage = False
                if header_filename:
                    import re
                    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', header_filename, re.I):
                        is_garbage = True
                    elif re.match(r'^[0-9a-f]{32,64}$', header_filename, re.I):
                        is_garbage = True
                
                if header_filename and not is_garbage:
                    result["filename"] = header_filename
                elif basename and basename != "file":
                    result["filename"] = basename
                elif header_filename:
                    result["filename"] = header_filename
                    
        except Exception as e:
            result["error"] = str(e)
            
        self.finished_signal.emit(result)
        
    def format_bytes(self, size):
        power = 2**10
        n = 0
        power_labels = {0 : '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
        while size > power:
            size /= power
            n += 1
        return f"{size:.2f} {power_labels.get(n, '')}B"

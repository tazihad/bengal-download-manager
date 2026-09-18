# 0003 Unify Download Worker Seam and Decouple Table Row Indices

Status: accepted

## Context
Worker implementations (`Aria2Worker`, `DownloadWorker`, `YtDlpDownloadWorker`) previously coupled their constructor and signal signatures directly to a GUI table `row_index`. Callers had to supply a table row integer and subsequently discard it using `lambda _, data:` because GUI table sorting, row reordering, and item insertions invalidate row indices during active downloads.

## Decision
We decouple the download engine seam by standardizing constructors around an optional `download_id: Any = 0`, preserving `row_index` as a backward-compatible keyword/attribute alias. Engine signal emissions represent progress against this identifier, insulating download engines from view presentation coordinates.

## Consequences
- Download workers can be instantiated and executed headlessly without synthetic GUI table row coordinates.
- Table view row resolution is isolated strictly inside view delegates and caller lambdas.
- All three engine adapters (Aria2, native chunk segments, and yt-dlp) adhere to a unified identifier contract.

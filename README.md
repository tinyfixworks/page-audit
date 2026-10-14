# Page Audit — prototype 0.1

First prototype for auditing one public HTTP(S) page and displaying an interactive static report.

## Checks included
- Page HTTP status, title, meta description, H1 headings and canonical URL
- Missing image alt attributes; empty alt text flagged as low-confidence review
- Possible public-facing internal notes, placeholder text and CMS/design labels
- Up to 60 unique links, with 404/410 distinguished from uncertain access/server/network errors
- Load timing and resource count
- Dashboard search, category/severity filters and evidence detail dialog

AI analysis is not connected yet. The report schema already includes AI status.

## Setup
1. Create a new GitHub repository named `page-audit`.
2. Upload the files from this package, keeping the `.github/workflows` path.
3. In Settings → Pages, choose Deploy from a branch, `main`, folder `/ (root)`.
4. In Settings → Actions → General, allow workflows to write to repository contents.
5. Open Actions → Audit public page → Run workflow, enter a public URL, and run it.
6. After the workflow commits `results.json`, open the GitHub Pages URL.

The workflow is manual. Each run replaces the latest report; history is not implemented. Only inspect public pages you are authorized to audit. Do not commit API keys. 403/429/timeouts/5xx are not automatically classified as broken links. Findings are evidence and require contextual review.

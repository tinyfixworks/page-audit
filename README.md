# Page Audit — prototype 0.1

First prototype for auditing public pages on `https://www.yettel.bg` and displaying an interactive static report.

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

The workflow is manual. The dashboard URL form validates and copies a Yettel URL, but GitHub Pages cannot launch Actions by itself; paste the URL into Actions → Audit public page → Run workflow. Each run replaces the latest report; history is not implemented. Only inspect public pages you are authorized to audit. Do not commit API keys. 403/429/timeouts/5xx are not automatically classified as broken links. Findings are evidence and require contextual review.
\n\n## Security allow-list\nThe checker only accepts the exact hostname `www.yettel.bg` over HTTP(S) and stops if browser navigation redirects to another hostname. The dashboard form currently accepts HTTPS only. This is an initial safeguard, not a complete SSRF defense; before exposing a public scan API, also validate every redirect and every subresource/request destination, use network egress restrictions, add authentication/rate limits, and keep the runner isolated.\n
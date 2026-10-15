# Gemini integration patch for Page Audit

This is an overlay patch, not a full repository export. It is based on the Page Audit prototype files available in this conversation; I could not directly inspect the live GitHub repository. Review the current files before replacing them.

## Files included
- `ai_analyzer.py` — Gemini API call and structured finding cleanup.
- `checker.py` — captures a screenshot of the first viewport and combines rules and AI findings.
- `.github/workflows/audit.yml` — passes `GEMINI_API_KEY` as an environment secret.
- `requirements.txt` — required Python dependencies.

## Apply
1. Add `ai_analyzer.py` to the repository root.
2. Replace `checker.py` with the included version (only if it matches your current prototype).
3. Update `.github/workflows/audit.yml` to the included version, preserving any changes you have made since the prototype.
4. Confirm `GEMINI_API_KEY` exists under Settings → Secrets and variables → Actions. Never put the key in source code or send it in chat.
5. Commit and push, then run Actions → Audit public page → Run workflow.

Gemini findings use `source: gemini`; rules findings remain `source: rules`. The report includes `ai_analysis.status` and `ai_analysis.finding_count`. If the key is absent or the API errors, the rules-based audit should still produce a report.

Default model: `gemini-2.5-flash`. The AI receives extracted text/metadata and a screenshot of the first viewport, not a separate image-by-image analysis. AI findings are probabilistic and require review. API usage may be billable depending on current quota and billing configuration. Keep URL validation restricted to `www.yettel.bg`.

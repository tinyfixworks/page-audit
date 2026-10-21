
import argparse
import json
import os
import re
import difflib
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from playwright.sync_api import sync_playwright
from ai_analyzer import analyze as analyze_with_gemini


def finding(
    cat,
    sev,
    title,
    evidence,
    context="",
    impact="",
    confidence="high",
    source="rules",
    recommendation=""
):
    return {
        "id": "",
        "category": cat,
        "severity": sev,
        "title": title,
        "evidence": evidence,
        "context": context,
        "impact": impact,
        "recommendation": recommendation,
        "confidence": confidence,
        "source": source
    }


def _normalise_text(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _is_ai_finding(item):
    source = str(item.get("source", "")).lower()
    return item.get("ai_generated") is True or "gemini" in source or source == "ai"


def _merge_duplicate(existing, incoming):
    preferred, supplemental = (
        (existing, incoming)
        if not _is_ai_finding(existing)
        else (incoming, existing)
    )
    merged = dict(preferred)

    for field in ("context", "impact", "recommendation"):
        if not merged.get(field) and supplemental.get(field):
            merged[field] = supplemental[field]

    if _is_ai_finding(existing) or _is_ai_finding(incoming):
        merged["source"] = "rules+gemini"
        merged["ai_generated"] = True

    confidence_rank = {"low": 1, "medium": 2, "high": 3}
    if confidence_rank.get(str(supplemental.get("confidence", "")).lower(), 0) > confidence_rank.get(str(merged.get("confidence", "")).lower(), 0):
        merged["confidence"] = supplemental["confidence"]

    return merged


def deduplicate_findings(findings):
    result = []

    for item in findings:
        if not isinstance(item, dict):
            continue

        title = _normalise_text(item.get("title"))
        evidence = _normalise_text(item.get("evidence"))
        category = _normalise_text(item.get("category"))
        duplicate_index = None

        for index, existing in enumerate(result):
            old_category = _normalise_text(existing.get("category"))
            old_title = _normalise_text(existing.get("title"))
            old_evidence = _normalise_text(existing.get("evidence"))

            exact_duplicate = (
                category == old_category
                and title == old_title
                and evidence == old_evidence
            )

            cross_source = _is_ai_finding(item) != _is_ai_finding(existing)
            same_category = category == old_category
            title_similarity = difflib.SequenceMatcher(None, title, old_title).ratio() if title and old_title else 0
            evidence_similarity = difflib.SequenceMatcher(None, evidence, old_evidence).ratio() if evidence and old_evidence else 0

            semantic_duplicate = (
                cross_source
                and same_category
                and (
                    title_similarity >= 0.90
                    or (len(evidence) >= 35 and len(old_evidence) >= 35 and evidence_similarity >= 0.94)
                )
            )

            if exact_duplicate or semantic_duplicate:
                duplicate_index = index
                break

        if duplicate_index is None:
            result.append(item)
        else:
            result[duplicate_index] = _merge_duplicate(
                result[duplicate_index], item
            )

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.getenv("AUDIT_URL", ""))
    ap.add_argument("--output", default="results.json")
    ap.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip Gemini analysis"
    )
    a = ap.parse_args()

    u = a.url.strip()
    p = urlparse(u)

    if p.scheme not in ("http", "https") or not p.netloc:
        raise SystemExit("Enter a valid public HTTP(S) URL.")

    allowed_host = (p.hostname or "").lower().rstrip(".")

    if allowed_host != "www.yettel.bg":
        raise SystemExit(
            "For security, this prototype only audits URLs on www.yettel.bg."
        )

    start = time.time()
    fs = []
    screenshot_path = "page-audit-screenshot.png"

    d = {
        "requested_url": u,
        "final_url": u,
        "status": None,
        "title": "",
        "meta_description": "",
        "canonical": "",
        "h1": [],
        "headings": [],
        "links": [],
        "images": [],
        "resources": [],
        "text_excerpt": "",
        "load_ms": None,
        "request_count": 0
    }

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}
        )
        response = None

        try:
            response = page.goto(
                u,
                wait_until="networkidle",
                timeout=60000
            )
        except Exception as e:
            fs.append(finding(
                "Technical",
                "high",
                "Page did not finish loading",
                str(e)[:400],
                "Browser navigation",
                "Some checks may be incomplete.",
                "medium"
            ))

            try:
                page.goto(
                    u,
                    wait_until="domcontentloaded",
                    timeout=25000
                )
            except Exception:
                pass

        d["final_url"] = page.url
        d["status"] = response.status if response else None

        final_host = (
            urlparse(d["final_url"]).hostname or ""
        ).lower().rstrip(".")

        if final_host != "www.yettel.bg":
            browser.close()
            raise SystemExit(
                "Navigation redirected outside www.yettel.bg. "
                "Audit stopped for security."
            )

        try:
            page.evaluate("""
                () => {
                    document.querySelectorAll(
                        '#CybotCookiebotDialog'
                    ).forEach(element => element.remove());
                }
            """)
        except Exception:
            pass

        try:
            d["title"] = (page.title() or "").strip()
        except Exception:
            pass

        try:
            page.screenshot(
                path=screenshot_path,
                full_page=False,
                animations="disabled"
            )
        except Exception:
            screenshot_path = ""

        try:
            extracted = page.evaluate("""() => {
                const txt = e => (
                    e?.innerText || e?.textContent || ''
                ).trim();

                const excluded = e => !!e.closest(
                    '#CybotCookiebotDialog'
                );
                const keep = e => !excluded(e);

                const meta = document.querySelector(
                    'meta[name="description"]'
                );
                const can = document.querySelector(
                    'link[rel="canonical"]'
                );

                return {
                    meta_description: meta?.content?.trim() || '',
                    canonical: can?.href || '',

                    h1: [...document.querySelectorAll('h1')]
                        .filter(keep)
                        .map(txt),

                    headings: [
                        ...document.querySelectorAll(
                            'h1,h2,h3,h4,h5,h6'
                        )
                    ]
                        .filter(keep)
                        .map(e => ({
                            level: e.tagName,
                            text: txt(e).slice(0, 250)
                        })),

                    links: [
                        ...document.querySelectorAll('a[href]')
                    ]
                        .filter(keep)
                        .map(a => ({
                            text: txt(a).slice(0, 200),
                            href: a.href,
                            area: a.closest('header') ? 'Header'
                                : a.closest('nav') ? 'Navigation'
                                : a.closest('footer') ? 'Footer'
                                : 'Main content',
                            element: a.querySelector('img')
                                ? 'image link'
                                : 'text link',
                            imageAlt: a.querySelector('img')
                                ?.getAttribute('alt') ?? null
                        })),

                    images: [...document.images]
                        .filter(keep)
                        .map(i => ({
                            src: i.currentSrc || i.src,
                            alt: i.getAttribute('alt'),
                            width: i.naturalWidth || i.width,
                            height: i.naturalHeight || i.height,
                            visible: !!(
                                i.getClientRects().length &&
                                getComputedStyle(i).display !== 'none' &&
                                getComputedStyle(i).visibility !== 'hidden'
                            ),
                            area: i.closest('header') ? 'Header'
                                : i.closest('footer') ? 'Footer'
                                : 'Main content'
                        })),

                    resources: performance
                        .getEntriesByType('resource')
                        .map(r => ({
                            name: r.name,
                            type: r.initiatorType,
                            duration: Math.round(r.duration),
                            transferSize: r.transferSize || 0
                        })),

                    text_excerpt: (() => {
                        const clone = document.body.cloneNode(true);

                        clone.querySelectorAll(
                            '#CybotCookiebotDialog'
                        ).forEach(element => element.remove());

                        return (
                            clone.innerText || clone.textContent || ''
                        ).trim().slice(0, 16000);
                    })()
                };
            }""")

            d.update(extracted)

        except Exception as e:
            fs.append(finding(
                "Technical",
                "medium",
                "Could not extract page structure",
                str(e)[:300],
                "DOM extraction",
                "Some checks may be incomplete.",
                "medium"
            ))

        browser.close()

    d["load_ms"] = round((time.time() - start) * 1000)
    d["request_count"] = len(d["resources"])

    if d["status"] and d["status"] >= 400:
        fs.append(finding(
            "Technical",
            "critical",
            "Page returned an HTTP error",
            f"HTTP status: {d['status']}",
            d["final_url"],
            "The page may not be accessible to visitors or crawlers."
        ))

    if not d["title"]:
        fs.append(finding(
            "SEO",
            "high",
            "Missing page title",
            "No non-empty document title was detected.",
            "HTML <title>",
            "Search results and browser tabs may lack a useful title."
        ))

    if not d["meta_description"]:
        fs.append(finding(
            "SEO",
            "medium",
            "Missing meta description",
            "No non-empty meta description was detected.",
            "HTML head",
            "Search engines may generate their own snippet."
        ))

    if not d["h1"]:
        fs.append(finding(
            "SEO",
            "high",
            "No H1 heading detected",
            "The page contains zero H1 elements.",
            "Heading structure",
            "The page lacks a primary heading in its HTML structure."
        ))
    elif len(d["h1"]) > 1:
        fs.append(finding(
            "SEO",
            "medium",
            "Multiple H1 headings detected",
            json.dumps(d["h1"], ensure_ascii=False),
            "Heading structure",
            "Multiple H1s may be intentional; review in context.",
            "medium"
        ))

    if not d["canonical"]:
        fs.append(finding(
            "SEO",
            "low",
            "Canonical link not detected",
            "No link[rel=canonical] was detected.",
            "HTML head",
            "This may be intentional.",
            "low"
        ))
    else:
        ch = urlparse(d["canonical"]).netloc.lower()
        fh = urlparse(d["final_url"]).netloc.lower()

        if ch and fh and ch != fh:
            fs.append(finding(
                "SEO",
                "medium",
                "Canonical points to a different host",
                d["canonical"],
                "HTML link[rel=canonical]",
                "Confirm whether this is intentional.",
                "medium"
            ))

    for im in d["images"]:
        if im["visible"] and im["alt"] is None:
            fs.append(finding(
                "Accessibility",
                "medium",
                "Image has no alt attribute",
                im["src"],
                im["area"],
                "Assistive technologies may lack a text alternative."
            ))
        elif im["visible"] and im["alt"] == "":
            fs.append(finding(
                "Accessibility",
                "low",
                "Image has empty alt text",
                im["src"],
                im["area"],
                "Empty alt can be correct for decorative images; verify purpose.",
                "low"
            ))

    for pattern, label in [
        (
            r"submitted by .{0,100} on .{0,80}",
            "Possible editorial metadata in page text"
        ),
        (
            r"components library",
            "Possible internal component-library text"
        ),
        (
            r"node background color",
            "Possible CMS/design configuration text"
        ),
        (
            r"lorem ipsum",
            "Placeholder text detected"
        ),
        (
            r"todo:|fixme:",
            "Possible internal note detected"
        )
    ]:
        m = re.search(pattern, d["text_excerpt"], re.I)

        if m:
            fs.append(finding(
                "Content",
                "medium",
                label,
                m.group(0),
                "Extracted page text",
                "May be intentional; verify whether public visitors should see it.",
                "medium"
            ))

    seen = set()
    links = []

    for x in d["links"]:
        href = x.get("href", "")

        if (
            urlparse(href).scheme in ("http", "https")
            and href not in seen
        ):
            seen.add(href)
            links.append(x)

        if len(links) >= 60:
            break

    s = requests.Session()
    s.headers["User-Agent"] = "PageAudit/0.1"

    for x in links:
        try:
            r = s.head(
                x["href"],
                allow_redirects=True,
                timeout=8
            )

            if r.status_code in (403, 405):
                r = s.get(
                    x["href"],
                    allow_redirects=True,
                    timeout=8,
                    stream=True
                )

            label = x["text"] or x["imageAlt"] or "(unlabelled)"
            ctx = (
                f'{x["area"]} · {x["element"]} · {label}'
            )

            if r.status_code in (404, 410):
                fs.append(finding(
                    "Links",
                    "high",
                    "Link points to a missing page",
                    f'{x["href"]} returned HTTP {r.status_code}.',
                    ctx,
                    "Visitors may reach a missing destination."
                ))
            elif (
                r.status_code in (401, 403, 429)
                or r.status_code >= 500
            ):
                fs.append(finding(
                    "Links",
                    "medium",
                    "Link could not be reliably verified",
                    f'{x["href"]} returned HTTP {r.status_code}.',
                    ctx,
                    "Access controls, rate limits or server issues may affect the result.",
                    "medium"
                ))
            elif r.status_code >= 400:
                fs.append(finding(
                    "Links",
                    "medium",
                    "Link returned an HTTP error",
                    f'{x["href"]} returned HTTP {r.status_code}.',
                    ctx,
                    "Confirm whether the response is expected.",
                    "medium"
                ))

        except Exception as e:
            fs.append(finding(
                "Links",
                "low",
                "Link check failed",
                f'{x["href"]} — {str(e)[:150]}',
                x["area"],
                "Network behavior prevented verification.",
                "low"
            ))

    ai_result = {
        "enabled": False,
        "status": "skipped by configuration",
        "findings": []
    }

    if not a.skip_ai:
        try:
            ai_result = analyze_with_gemini(d, screenshot_path)

            if not isinstance(ai_result, dict):
                ai_result = {
                    "enabled": True,
                    "status": "Invalid AI analyzer result",
                    "error": "analyze() did not return a dictionary.",
                    "findings": []
                }

            ai_findings = ai_result.get("findings", [])

            if not isinstance(ai_findings, list):
                ai_findings = []

            fs.extend(
                item for item in ai_findings
                if isinstance(item, dict)
            )

        except Exception as e:
            ai_result = {
                "enabled": True,
                "status": f"error: {str(e)[:300]}",
                "error": f"{type(e).__name__}: {str(e)[:500]}",
                "findings": []
            }

    fs = deduplicate_findings(fs)

    order = {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3
    }

    fs.sort(key=lambda x: (
        order.get(
            str(x.get("severity", "")).lower(),
            9
        ),
        str(x.get("category", "")),
        str(x.get("title", ""))
    ))

    for i, x in enumerate(fs, 1):
        x["id"] = f"PA-{i:03d}"

    ai_findings = ai_result.get("findings", [])
    if not isinstance(ai_findings, list):
        ai_findings = []

    report = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "page": d,
        "summary": {
            "total_findings": len(fs),
            "by_severity": dict(
                Counter(x.get("severity", "unknown") for x in fs)
            ),
            "by_category": dict(
                Counter(x.get("category", "Other") for x in fs)
            )
        },
        "findings": fs,
        "ai_analysis": {
            **ai_result,
            "enabled": ai_result.get("enabled", False),
            "status": ai_result.get("status", "unknown"),
            "model": ai_result.get(
                "model",
                os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
            ),
            "used_model": ai_result.get("used_model"),
            "fallback_used": ai_result.get("fallback_used", False),
            "fallback_model": ai_result.get("fallback_model"),
            "primary_error": ai_result.get("primary_error"),
            "fallback_error": ai_result.get("fallback_error"),
            "error": ai_result.get("error"),
            "finding_count": len(ai_findings)
        },
        "notes": [
            "Findings require human review, especially contextual findings.",
            "Checks up to 60 unique link destinations.",
            "AI findings are probabilistic and should be reviewed against the evidence."
        ]
    }

    with open(a.output, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    if screenshot_path and os.path.exists(screenshot_path):
        try:
            os.remove(screenshot_path)
        except OSError:
            pass

    print(
        f"Saved {len(fs)} findings to {a.output}; "
        f"Gemini: {report['ai_analysis']['status']}; "
        f"AI findings: {report['ai_analysis']['finding_count']}; "
        f"Model used: {report['ai_analysis'].get('used_model') or 'unknown'}"
    )


if __name__ == "__main__":
    main()

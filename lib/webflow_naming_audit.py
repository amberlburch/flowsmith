#!/usr/bin/env python3
"""Naming-grammar audit: fetch a published Webflow page, extract class attributes,
check every class against the pinned grammar (webflow-design-system/references/naming.md).

Usage: webflow_naming_audit.py <url> [<url> ...] [--json]
Exit 0 = clean, 1 = violations found.
"""
import json, re, sys, urllib.request

# THE PINNED GRAMMAR — single source of truth (naming.md's inline regex is illustrative).
GRAMMAR = re.compile(
    r"^(page-wrapper|main-wrapper|section_[a-z0-9-]+"
    r"|padding-(global|section-(small|medium|large))"
    r"|container-(large|medium|small)"
    r"|button|nav|footer"                                        # global components
    r"|[a-z0-9]+(-[a-z0-9]+)*_[a-z0-9]+(-[a-z0-9]+)*"          # component_element
    r"|(text|background|display|hide|align|margin|padding|is)-[a-z0-9-]+"  # utilities
    r"|ct-[a-z0-9-]+"                                            # custom-code classes
    r"|w-[a-z0-9-]+|w--[a-z0-9-]+)$"                             # webflow internals
)

def audit(url):
    html = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
    classes, exempt = set(), set()
    for attr in re.findall(r'class="([^"]*)"', html):
        toks = [c for c in attr.split() if c]
        classes.update(toks)
        # Webflow native components (navbar/dropdown/slider/tabs/lightbox...) always pair their
        # default class with a w-* internal on the same element — exempt the whole attribute.
        if any(t.startswith("w-") or t.startswith("w--") for t in toks):
            exempt.update(toks)
    violations = sorted(c for c in classes if c not in exempt and not GRAMMAR.match(c))
    return {"url": url, "classes": len(classes), "violations": violations}

def main():
    args = [a for a in sys.argv[1:] if a != "--json"]
    as_json = "--json" in sys.argv
    if not args: sys.exit(__doc__)
    results = [audit(u) for u in args]
    bad = any(r["violations"] for r in results)
    if as_json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(f"{r['url']}: {r['classes']} classes, {len(r['violations'])} violations")
            for v in r["violations"][:40]:
                print(f"  ✗ {v}")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()

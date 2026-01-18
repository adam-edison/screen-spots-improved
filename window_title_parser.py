"""
Window title parser for screen-spots.
Extracts meaningful segments from window titles for pattern matching.

This module can be run standalone to test parsing:
    python window_title_parser.py
"""

import re


def _url_to_domain(match) -> str:
    """Extract domain from URL, stripping protocol and path."""
    full_url = match.group(0)
    no_protocol = re.sub(r'^https?://', '', full_url)
    domain = no_protocol.split('/')[0]
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def _replace_urls_with_domains(title: str) -> str:
    """Replace URLs in title with just their domains."""
    url_pattern = r'https?://[^\s]+'
    return re.sub(url_pattern, _url_to_domain, title)


def _split_on_delimiters(title: str) -> list[str]:
    """Split title on common delimiters."""
    delimiter_pattern = r'\s+[|—–]\s+|\s+-\s+|\s+:\s+|:\s+'
    return re.split(delimiter_pattern, title)


def _filter_segments(segments: list[str], min_length: int) -> list[str]:
    """Filter segments by minimum length and strip whitespace."""
    return [seg.strip() for seg in segments if seg.strip() and len(seg.strip()) >= min_length]


def _dedupe_segments(segments: list[str]) -> list[str]:
    """Remove duplicate segments (case-insensitive) while preserving order."""
    seen = set()
    unique = []
    for seg in segments:
        seg_lower = seg.lower()
        if seg_lower not in seen:
            seen.add(seg_lower)
            unique.append(seg)
    return unique


def _build_combined_pattern(segments: list[str]) -> str:
    """Build a combined regex pattern from segments using lookaheads."""
    escaped = [re.escape(seg) for seg in segments]
    return "".join(f"(?=.*{seg})" for seg in escaped)


def parse_window_title_segments(title: str, min_length: int = 3) -> list[str]:
    """
    Parse a window title into meaningful segments by splitting on common delimiters.
    
    Delimiters handled:
    - " - " (hyphen with spaces)
    - " | " (pipe with spaces)
    - " — " (em dash with spaces)
    - " – " (en dash with spaces)  
    - ": " (colon with space)
    - " : " (colon with spaces on both sides)
    
    NOT treated as delimiters:
    - "." (dots - important for filenames, domains, etc.)
    - "/" (slashes - ignored, not delimiters)
    
    URLs are processed to extract the domain (without protocol).
    
    Args:
        title: The window title to parse
        min_length: Minimum length for a segment to be included (default 3)
    
    Returns:
        List of unique segments, with full title at the end if different
    """
    if not title or not title.strip():
        return []
    
    processed_title = _replace_urls_with_domains(title.strip())
    segments = _split_on_delimiters(processed_title)
    filtered = _filter_segments(segments, min_length)
    unique_segments = _dedupe_segments(filtered)
    
    if len(unique_segments) > 1:
        unique_segments.append(_build_combined_pattern(unique_segments))
    
    return unique_segments


FILE_EXTENSIONS = {'.md', '.py', '.js', '.ts', '.txt', '.json', '.csv', '.html', '.css', 
                   '.xml', '.yml', '.yaml', '.sh', '.bat', '.exe', '.app', '.pdf', '.doc',
                   '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.gif', '.svg'}


def _has_file_extension(text: str) -> bool:
    """Check if text ends with a common file extension."""
    text_lower = text.lower()
    return any(text_lower.endswith(ext) for ext in FILE_EXTENSIONS)


def _matches_domain_pattern(text: str) -> bool:
    """Check if text matches the domain name pattern."""
    return bool(re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+$', text))


def is_domain(text: str) -> bool:
    """Check if text looks like a domain name (not a filename)."""
    if '.' not in text:
        return False
    if _has_file_extension(text):
        return False
    return _matches_domain_pattern(text)


def _classify_segment(seg: str, is_last: bool, total_segments: int) -> dict:
    """Classify a segment and return its suggestion dict."""
    is_combined = total_segments > 1 and is_last and seg.startswith("(?=")
    if is_combined:
        return {"pattern": seg, "description": "Combined (all segments)", "type": "combined"}
    if is_domain(seg):
        return {"pattern": seg, "description": "Domain", "type": "domain"}
    return {"pattern": seg, "description": "Title segment", "type": "segment"}


def get_suggested_patterns(title: str) -> list[dict]:
    """
    Get a list of suggested patterns with descriptions.
    
    Returns list of dicts with:
        - "pattern": the pattern string
        - "description": human-readable description
        - "type": "segment", "domain", or "combined"
    """
    segments = parse_window_title_segments(title)
    suggestions = []
    seen_patterns = set()
    
    for i, seg in enumerate(segments):
        seg_lower = seg.lower()
        if seg_lower in seen_patterns:
            continue
        seen_patterns.add(seg_lower)
        is_last = i == len(segments) - 1
        suggestions.append(_classify_segment(seg, is_last, len(segments)))
    
    return suggestions


# ============ TESTS ============

def run_tests():
    """Run test cases for the parser."""
    
    test_cases = [
        # (input_title, expected_segments_contain, expected_segments_not_contain)
        
        # Basic delimiter tests - combined uses regex lookaheads
        (
            "GitHub - screen-spots-improved - Cursor",
            ["GitHub", "screen-spots-improved", "Cursor"],
            ["H", "|", " - "]  # No literal delimiters in output
        ),
        
        # Pipe delimiter
        (
            "Gmail | Inbox | Google Chrome",
            ["Gmail", "Inbox", "Google Chrome"],
            ["|"]
        ),
        
        # Mixed delimiters
        (
            "Project: README.md - Visual Studio Code",
            ["Project", "README.md", "Visual Studio Code"],
            [":"]
        ),
        
        # URL converted to domain (protocol stripped)
        (
            "https://github.com/user/repo - GitHub - Brave",
            ["github.com", "GitHub", "Brave"],
            ["https://", "https", "user/repo", "https://github.com/user/repo"]
        ),
        
        # URL with path - only domain kept
        (
            "File: https://example.com/path/to/file.txt - Browser",
            ["File", "example.com", "Browser"],
            ["https://", "path/to/file.txt"]
        ),
        
        # Short segments should be filtered, combined is regex with only valid segments
        (
            "H | Long Segment Here | X | Another Good One",
            ["Long Segment Here", "Another Good One"],
            ["H", "X", "|", " - "]
        ),
        
        # Dots should NOT be delimiters (important for filenames)
        (
            "README.md - screen-spots-improved",
            ["README.md", "screen-spots-improved"],
            ["README", "md"]
        ),
        
        # Em dash
        (
            "Document — Microsoft Word",
            ["Document", "Microsoft Word"],
            ["—"]
        ),
        
        # En dash
        (
            "Page – Firefox",
            ["Page", "Firefox"],
            ["–"]
        ),
        
        # Duplicate removal
        (
            "GitHub - GitHub - Brave",
            ["GitHub", "Brave"],
            []
        ),
        
        # Complex GitHub PR title - URL becomes domain, H filtered, combined is regex
        (
            "H | Enhance README and add CSV support for screen-spots | https://github.com/adam-edison/screen-spots-improved/pull/1 | Brave",
            ["Enhance README and add CSV support for screen-spots", "github.com", "Brave"],
            ["H", "|", "https://", "adam-edison", "pull/1", " - "]
        ),
        
        # Slack-style title
        (
            "Slack | general | Company Workspace",
            ["Slack", "general", "Company Workspace"],
            ["|"]
        ),
        
        # VS Code with file path
        (
            "screen-spots.py - screen-spots-improved - Visual Studio Code",
            ["screen-spots.py", "screen-spots-improved", "Visual Studio Code"],
            ["-"]
        ),
        
        # Browser with multiple levels
        (
            "Google Docs - Document Title - Google Chrome",
            ["Google Docs", "Document Title", "Google Chrome"],
            []
        ),
        
        # Empty/whitespace handling
        (
            "   ",
            [],
            []
        ),
        (
            "",
            [],
            []
        ),
        
        # Single segment (no delimiters)
        (
            "Terminal",
            ["Terminal"],
            []
        ),
        
        # Colon with space splits (this is reasonable behavior)
        (
            "Error: Something went wrong - App",
            ["Error", "Something went wrong", "App"],
            []
        ),
        
        # www. prefix should be stripped from domains
        (
            "https://www.google.com/search - Google - Chrome",
            ["google.com", "Google", "Chrome"],
            ["www.", "www.google.com", "https://"]
        ),
        
        # Multiple URLs in title without delimiters - domains combined
        # (this is an edge case, "vs" is not a delimiter so they stay together)
        (
            "Compare: https://site1.com vs https://site2.org - Browser",
            ["Compare", "site1.com vs site2.org", "Browser"],
            ["https://"]
        ),
        
        # Multiple URLs with proper delimiters
        (
            "Site A: https://site1.com | Site B: https://site2.org - Browser",
            ["Site A", "site1.com", "Site B", "site2.org", "Browser"],
            ["https://"]
        ),
    ]
    
    print("Running window title parser tests...\n")
    results = [_run_single_test(i, tc) for i, tc in enumerate(test_cases, 1)]
    passed = sum(1 for r in results if r)
    failed = len(results) - passed
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    return failed == 0


def _check_test_errors(segments: list[str], should_contain: list[str], should_not_contain: list[str]) -> list[str]:
    """Check for test errors and return list of error messages."""
    missing = [f"  Missing expected segment: '{e}'" for e in should_contain if e not in segments]
    unwanted = [f"  Found unwanted segment: '{u}'" for u in should_not_contain if u in segments]
    return missing + unwanted


def _run_single_test(test_num: int, test_case: tuple) -> bool:
    """Run a single test case and print results. Returns True if passed."""
    title, should_contain, should_not_contain = test_case
    segments = parse_window_title_segments(title)
    errors = _check_test_errors(segments, should_contain, should_not_contain)
    
    status = "FAIL" if errors else "PASS"
    print(f"{status} Test {test_num}: {title[:50]}...")
    print(f"  Got: {segments}")
    for err in errors:
        print(err)
    print()
    return not errors


def _print_suggestions_for_title(title: str):
    """Print suggestions for a single title."""
    print(f"Title: {title}")
    suggestions = get_suggested_patterns(title)
    for i, sug in enumerate(suggestions, 1):
        print(f"  {i}. [{sug['type']}] {sug['pattern']}")
    print()


def test_suggestions():
    """Test the get_suggested_patterns function."""
    print("\n" + "="*50)
    print("Testing get_suggested_patterns()...\n")
    
    test_titles = [
        "https://github.com/user/repo - GitHub - Brave",
        "Gmail | Inbox (5) | Google Chrome",
        "README.md - project-name - Visual Studio Code",
        "H | Enhance README | https://github.com/adam-edison/screen-spots/pull/1 | Brave",
    ]
    
    for title in test_titles:
        _print_suggestions_for_title(title)


if __name__ == "__main__":
    success = run_tests()
    test_suggestions()
    
    if not success:
        exit(1)

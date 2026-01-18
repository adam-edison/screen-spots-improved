"""
Window title parser for screen-spots.
Extracts meaningful segments from window titles for pattern matching.

This module can be run standalone to test parsing:
    python window_title_parser.py
"""

import re


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
    
    title = title.strip()
    
    # First, find and process URLs - replace with just the domain
    # Match URLs: protocol, then everything until whitespace or delimiter-with-spaces
    url_pattern = r'https?://[^\s]+'
    
    def url_to_domain(match):
        """Extract domain from URL, stripping protocol and path"""
        full_url = match.group(0)  # The full URL match
        # Remove protocol
        no_protocol = re.sub(r'^https?://', '', full_url)
        # Get just the domain (first part before any /)
        domain = no_protocol.split('/')[0]
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain
    
    # Replace URLs with their domains
    processed_title = re.sub(url_pattern, url_to_domain, title)
    
    # Split by delimiters (order matters - try longer patterns first)
    # Pattern: space-delimiter-space combinations
    delimiter_pattern = r'\s+[|—–]\s+|\s+-\s+|\s+:\s+|:\s+'
    
    segments = re.split(delimiter_pattern, processed_title)
    
    # Clean up segments
    cleaned_segments = []
    for seg in segments:
        seg = seg.strip()
        # Skip empty, too short, or single-character segments
        if seg and len(seg) >= min_length:
            cleaned_segments.append(seg)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_segments = []
    for seg in cleaned_segments:
        # Use lowercase for dedup comparison but keep original case
        seg_lower = seg.lower()
        if seg_lower not in seen:
            seen.add(seg_lower)
            unique_segments.append(seg)
    
    # If we have multiple segments, offer a combined regex pattern
    # Uses lookaheads so all segments must be present but order doesn't matter
    if len(unique_segments) > 1:
        # Escape regex special chars in each segment, then wrap in lookahead
        escaped_segments = [re.escape(seg) for seg in unique_segments]
        combined = "".join(f"(?=.*{seg})" for seg in escaped_segments)
        unique_segments.append(combined)
    
    return unique_segments


def is_domain(text: str) -> bool:
    """Check if text looks like a domain name (not a filename)."""
    # Must look like a domain: word.tld or subdomain.word.tld
    # Exclude common file extensions
    file_extensions = {'.md', '.py', '.js', '.ts', '.txt', '.json', '.csv', '.html', '.css', 
                       '.xml', '.yml', '.yaml', '.sh', '.bat', '.exe', '.app', '.pdf', '.doc',
                       '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.gif', '.svg'}
    
    text_lower = text.lower()
    for ext in file_extensions:
        if text_lower.endswith(ext):
            return False
    
    # Check if it looks like a domain (has a dot, ends with valid TLD-like suffix)
    if '.' not in text:
        return False
    
    # Common TLDs and patterns
    return bool(re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9]*(\.[a-zA-Z0-9][-a-zA-Z0-9]*)+$', text))


def get_suggested_patterns(title: str) -> list[dict]:
    """
    Get a list of suggested patterns with descriptions.
    
    Returns list of dicts with:
        - "pattern": the pattern string
        - "description": human-readable description
        - "type": "segment", "domain", or "combined"
    """
    suggestions = []
    seen_patterns = set()
    
    segments = parse_window_title_segments(title)
    
    for i, seg in enumerate(segments):
        seg_lower = seg.lower()
        if seg_lower in seen_patterns:
            continue
        seen_patterns.add(seg_lower)
        
        # The last segment (if we have multiple) is the combined regex version
        is_combined = (len(segments) > 1 and i == len(segments) - 1 and seg.startswith("(?="))
        
        if is_combined:
            suggestions.append({
                "pattern": seg,
                "description": "Combined (all segments)",
                "type": "combined"
            })
        elif is_domain(seg):
            suggestions.append({
                "pattern": seg,
                "description": "Domain",
                "type": "domain"
            })
        else:
            suggestions.append({
                "pattern": seg,
                "description": "Title segment",
                "type": "segment"
            })
    
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
    passed = 0
    failed = 0
    
    for i, (title, should_contain, should_not_contain) in enumerate(test_cases, 1):
        segments = parse_window_title_segments(title)
        
        errors = []
        
        # Check that expected segments are present
        for expected in should_contain:
            if expected not in segments:
                errors.append(f"  Missing expected segment: '{expected}'")
        
        # Check that unwanted segments are not present
        for unwanted in should_not_contain:
            if unwanted in segments:
                errors.append(f"  Found unwanted segment: '{unwanted}'")
        
        if errors:
            failed += 1
            print(f"FAIL Test {i}: {title[:50]}...")
            print(f"  Got: {segments}")
            for err in errors:
                print(err)
            print()
        else:
            passed += 1
            print(f"PASS Test {i}: {title[:50]}...")
            print(f"  Got: {segments}")
            print()
    
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    
    if failed > 0:
        return False
    return True


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
        print(f"Title: {title}")
        suggestions = get_suggested_patterns(title)
        for i, sug in enumerate(suggestions, 1):
            print(f"  {i}. [{sug['type']}] {sug['pattern']}")
        print()


if __name__ == "__main__":
    success = run_tests()
    test_suggestions()
    
    if not success:
        exit(1)

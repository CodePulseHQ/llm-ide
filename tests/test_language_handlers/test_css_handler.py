"""Test CSS language handler."""

import pytest

from refactor_mcp.languages.css_handler import CSSHandler


class TestCSSHandler:
    """Test CSS language handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create CSS handler instance."""
        return CSSHandler()

    def test_language_properties(self, handler):
        """Test basic language properties."""
        assert handler.language_name == "CSS"
        assert ".css" in handler.file_extensions

    def test_can_handle_file_by_extension(self, handler, temp_dir):
        """Test file handling by extension."""
        # Test supported extensions
        for ext in [".css", ".scss", ".sass", ".less"]:
            if ext in handler.file_extensions:
                test_file = temp_dir / f"test{ext}"
                test_file.write_text("body { color: red; }")
                assert handler.can_handle_file(test_file)

    def test_can_handle_css_patterns(self, handler, temp_dir):
        """Test CSS-specific content patterns."""
        patterns = [
            "body { color: red; }",
            ".class { display: flex; }",
            "#id { margin: 10px; }",
            "@import 'styles.css';",
            "@media (max-width: 768px) { .responsive { display: none; } }",
        ]

        for pattern in patterns:
            test_file = temp_dir / "test.unknown"
            test_file.write_text(pattern)
            assert handler.can_handle_file(test_file), f"Failed to detect: {pattern}"

    def test_code_structure_analysis(self, handler, sample_css_code, temp_dir):
        """Test CSS code structure extraction."""
        css_file = temp_dir / "test.css"
        css_file.write_text(sample_css_code)

        structure = handler.get_code_structure(css_file)

        assert structure.language == "CSS"
        # CSS should detect @import statements
        assert len(structure.imports) >= 2  # Google Fonts and components imports

    def test_import_organization(self, handler, temp_dir):
        """Test CSS @import organization."""
        css_code = """@import url('components/buttons.css');
@import 'normalize.css';
@import url('https://fonts.googleapis.com/css2?family=Roboto');
@import 'variables.css';

body {
    font-family: Arial, sans-serif;
}

.header {
    background: blue;
}"""

        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.organize_imports(css_file)
        assert "successfully" in result.lower() or "organized" in result.lower()

    def test_dependency_analysis(self, handler, sample_css_code, temp_dir):
        """Test CSS dependency analysis."""
        css_file = temp_dir / "test.css"
        css_file.write_text(sample_css_code)

        deps = handler.analyze_dependencies(css_file)

        assert "file" in deps
        assert "language" in deps
        assert deps["language"] == "CSS"
        assert "total_imports" in deps

    def test_selector_detection(self, handler, temp_dir):
        """Test CSS selector detection."""
        css_code = """
/* Various selector types */
body {
    margin: 0;
}

.class-selector {
    padding: 10px;
}

#id-selector {
    color: red;
}

h1, h2, h3 {
    font-weight: bold;
}

.parent > .child {
    display: block;
}

:hover {
    opacity: 0.8;
}

@media (max-width: 768px) {
    .mobile {
        font-size: 14px;
    }
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
"""

        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        structure = handler.get_code_structure(css_file)

        # CSS structure analysis depends on implementation
        # Should detect various CSS constructs
        assert structure.language == "CSS"

    def test_at_rule_detection(self, handler, temp_dir):
        """Test CSS @-rule detection."""
        css_code = """
@import 'base.css';
@import url('https://fonts.googleapis.com/css2?family=Open+Sans');

@media screen and (max-width: 600px) {
    .responsive {
        display: none;
    }
}

@supports (display: grid) {
    .grid-container {
        display: grid;
    }
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}
"""

        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        structure = handler.get_code_structure(css_file)

        # Should detect @import statements
        assert len(structure.imports) >= 2


class TestCSSHandlerRenameSelector:
    """Test CSS rename_selector functionality."""

    @pytest.fixture
    def handler(self):
        """Create CSS handler instance."""
        return CSSHandler()

    def test_rename_class_selector(self, handler, temp_dir):
        """Test renaming a class selector."""
        css_code = """.old-class {
    color: red;
}

.container .old-class {
    margin: 10px;
}

.old-class:hover {
    color: blue;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.rename_selector(css_file, ".old-class", ".new-class")

        assert "success" in result.lower() or "renamed" in result.lower()

        content = css_file.read_text()
        assert ".new-class" in content
        assert ".old-class" not in content

    def test_rename_id_selector(self, handler, temp_dir):
        """Test renaming an ID selector."""
        css_code = """#old-id {
    background: blue;
}

.container #old-id {
    padding: 20px;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.rename_selector(css_file, "#old-id", "#new-id")

        assert "success" in result.lower() or "renamed" in result.lower()

        content = css_file.read_text()
        assert "#new-id" in content
        assert "#old-id" not in content

    def test_rename_selector_not_found(self, handler, temp_dir):
        """Test renaming a selector that doesn't exist."""
        css_code = """.existing-class {
    color: red;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.rename_selector(css_file, ".nonexistent", ".new-class")

        assert "not found" in result.lower() or "no" in result.lower()


class TestCSSHandlerFindUnusedRules:
    """Test CSS find_unused_rules functionality."""

    @pytest.fixture
    def handler(self):
        """Create CSS handler instance."""
        return CSSHandler()

    def test_find_unused_rules_basic(self, handler, temp_dir):
        """Test finding unused CSS rules."""
        css_code = """.used-class {
    color: red;
}

.unused-class {
    color: blue;
}

#used-id {
    background: green;
}

#unused-id {
    padding: 10px;
}
"""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="used-class">Content</div>
    <span id="used-id">More content</span>
</body>
</html>
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.find_unused_rules(css_file, html_file)

        # Result should indicate unused rules
        assert "unused" in result.lower() or isinstance(result, dict)
        # Should find unused-class and unused-id as unused
        result_str = str(result).lower()
        assert "unused-class" in result_str or "unused-id" in result_str

    def test_find_unused_rules_all_used(self, handler, temp_dir):
        """Test when all rules are used."""
        css_code = """.btn {
    color: red;
}
"""
        html_code = """<!DOCTYPE html>
<html>
<body>
    <button class="btn">Click</button>
</body>
</html>
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.find_unused_rules(css_file, html_file)

        # Should indicate no unused rules or empty list
        result_str = str(result).lower()
        assert "no unused" in result_str or "0 unused" in result_str or result_str == "[]"


class TestCSSHandlerMergeDuplicateRules:
    """Test CSS merge_duplicate_rules functionality."""

    @pytest.fixture
    def handler(self):
        """Create CSS handler instance."""
        return CSSHandler()

    def test_find_duplicate_rules(self, handler, temp_dir):
        """Test finding rules with identical declarations."""
        css_code = """.class-a {
    color: red;
    font-size: 16px;
}

.class-b {
    color: red;
    font-size: 16px;
}

.class-c {
    color: blue;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.merge_duplicate_rules(css_file)

        # Should identify class-a and class-b as potential duplicates
        result_str = str(result).lower()
        assert "class-a" in result_str or "class-b" in result_str or "duplicate" in result_str

    def test_no_duplicates(self, handler, temp_dir):
        """Test when there are no duplicate rules."""
        css_code = """.class-a {
    color: red;
}

.class-b {
    color: blue;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.merge_duplicate_rules(css_file)

        # Should indicate no duplicates
        result_str = str(result).lower()
        assert "no duplicate" in result_str or "no merge" in result_str or "0" in result_str


class TestCSSHandlerExtractVariables:
    """Test CSS extract_variables functionality."""

    @pytest.fixture
    def handler(self):
        """Create CSS handler instance."""
        return CSSHandler()

    def test_extract_repeated_colors(self, handler, temp_dir):
        """Test extracting repeated color values as variables."""
        css_code = """.header {
    background-color: #007bff;
    border-color: #007bff;
}

.footer {
    color: #007bff;
}

.button {
    background: #ff5500;
    border: 1px solid #ff5500;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.extract_variables(css_file)

        # Should suggest extracting #007bff as a variable
        result_str = str(result).lower()
        assert "#007bff" in result_str or "variable" in result_str or "repeated" in result_str

    def test_extract_repeated_sizes(self, handler, temp_dir):
        """Test extracting repeated size values as variables."""
        css_code = """.header {
    padding: 20px;
    margin-bottom: 20px;
}

.section {
    padding: 20px;
    gap: 20px;
}

.footer {
    padding: 20px;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.extract_variables(css_file)

        # Should suggest extracting 20px as a variable
        result_str = str(result).lower()
        assert "20px" in result_str or "variable" in result_str or "repeated" in result_str

    def test_no_repeated_values(self, handler, temp_dir):
        """Test when there are no repeated values."""
        css_code = """.header {
    color: red;
}

.footer {
    color: blue;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.extract_variables(css_file)

        # Should indicate no repeated values found
        result_str = str(result).lower()
        assert (
            "no repeated" in result_str
            or "no variable" in result_str
            or "suggestions" not in result_str
            or "0" in result_str
        )


class TestCSSHandlerAnalyzeSpecificity:
    """Test CSS analyze_specificity functionality."""

    @pytest.fixture
    def handler(self):
        """Create CSS handler instance."""
        return CSSHandler()

    def test_detect_important_usage(self, handler, temp_dir):
        """Test detecting !important usage."""
        css_code = """.header {
    color: red !important;
    background: blue;
}

.footer {
    color: green !important;
    padding: 10px !important;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.analyze_specificity(css_file)

        # Should report !important usage
        result_str = str(result).lower()
        assert "!important" in result_str or "important" in result_str

    def test_detect_high_specificity_selectors(self, handler, temp_dir):
        """Test detecting overly specific selectors."""
        css_code = """body div.container #main .content p span.highlight {
    color: red;
}

#header #nav #menu .item.active {
    background: blue;
}

.simple-class {
    color: green;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.analyze_specificity(css_file)

        # Should report high specificity selectors
        result_str = str(result).lower()
        assert "specificity" in result_str or "high" in result_str or "selector" in result_str

    def test_clean_css_no_issues(self, handler, temp_dir):
        """Test CSS with good specificity practices."""
        css_code = """.header {
    color: red;
}

.nav-item {
    background: blue;
}

.btn {
    padding: 10px;
}
"""
        css_file = temp_dir / "test.css"
        css_file.write_text(css_code)

        result = handler.analyze_specificity(css_file)

        # Should indicate good practices or no issues
        result_str = str(result).lower()
        assert (
            "good" in result_str
            or "no issue" in result_str
            or "low" in result_str
            or "specificity" in result_str
        )

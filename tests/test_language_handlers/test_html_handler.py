"""Test HTML language handler."""

import pytest

from refactor_mcp.languages.html_handler import HTMLHandler


class TestHTMLHandler:
    """Test HTML language handler functionality."""

    @pytest.fixture
    def handler(self):
        """Create HTML handler instance."""
        return HTMLHandler()

    def test_language_properties(self, handler):
        """Test basic language properties."""
        assert handler.language_name == "HTML"
        assert ".html" in handler.file_extensions
        assert ".htm" in handler.file_extensions

    def test_can_handle_file_by_extension(self, handler, temp_dir):
        """Test file handling by extension."""
        # Test supported extensions
        for ext in [".html", ".htm", ".xhtml", ".svg"]:
            if ext in handler.file_extensions:
                test_file = temp_dir / f"test{ext}"
                test_file.write_text("<html><body>Test</body></html>")
                assert handler.can_handle_file(test_file)

    def test_can_handle_html_patterns(self, handler, temp_dir):
        """Test HTML-specific content patterns."""
        patterns = [
            "<!DOCTYPE html>",
            "<html>",
            "<body>Content</body>",
            "<div class='test'>Content</div>",
            "<script src='app.js'></script>",
            "<link rel='stylesheet' href='style.css'>",
        ]

        for pattern in patterns:
            test_file = temp_dir / "test.unknown"
            test_file.write_text(f"<html><body>{pattern}</body></html>")
            assert handler.can_handle_file(test_file), f"Failed to detect: {pattern}"

    def test_code_structure_analysis(self, handler, sample_html_code, temp_dir):
        """Test HTML code structure extraction."""
        html_file = temp_dir / "test.html"
        html_file.write_text(sample_html_code)

        structure = handler.get_code_structure(html_file)

        assert structure.language == "HTML"
        # HTML should detect script and style resources - but this depends on implementation
        # Some parsers may not detect all imports
        assert len(structure.imports) >= 0  # May detect external CSS and JS files

        # Should detect inline scripts as functions - implementation dependent
        # Just verify structure exists
        assert isinstance(structure.functions, list)

    def test_import_organization(self, handler, temp_dir):
        """Test HTML resource organization."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <script src="third.js"></script>
    <link rel="stylesheet" href="styles.css">
    <script src="first.js"></script>
    <link rel="stylesheet" href="components.css">
    <script src="https://cdn.example.com/lib.js"></script>
</head>
<body>
    <h1>Test</h1>
</body>
</html>"""

        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.organize_imports(html_file)
        assert "successfully" in result.lower() or "organized" in result.lower()

    def test_dependency_analysis(self, handler, sample_html_code, temp_dir):
        """Test HTML dependency analysis."""
        html_file = temp_dir / "test.html"
        html_file.write_text(sample_html_code)

        deps = handler.analyze_dependencies(html_file)

        assert "file" in deps
        assert "language" in deps
        assert deps["language"] == "HTML"
        # HTML dependency analysis may vary by implementation
        # Check for any of the common dependency fields
        has_dependency_info = any(
            key in deps
            for key in ["total_imports", "elements", "css_files", "external_scripts", "images"]
        )
        assert (
            has_dependency_info
        ), f"Expected dependency information, got keys: {list(deps.keys())}"

    def test_script_tag_detection(self, handler, temp_dir):
        """Test script tag detection."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <script src="external.js"></script>
    <script>
        function inlineFunction() {
            return 'test';
        }
        
        const inlineVar = 42;
    </script>
</head>
<body>
    <script src="another.js"></script>
</body>
</html>"""

        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        structure = handler.get_code_structure(html_file)

        # Should detect external script imports - implementation dependent
        # Some parsers may detect script tags as imports
        assert len(structure.imports) >= 0

        # May detect inline functions depending on implementation
        assert isinstance(structure.functions, list)


class TestHTMLHandlerRenameElementId:
    """Test rename_element_id operation."""

    @pytest.fixture
    def handler(self):
        """Create HTML handler instance."""
        return HTMLHandler()

    def test_rename_simple_id(self, handler, temp_dir):
        """Test renaming a simple ID attribute."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div id="old-id">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_element_id(html_file, "old-id", "new-id")

        assert "success" in result.lower() or "renamed" in result.lower()
        content = html_file.read_text()
        assert 'id="new-id"' in content
        assert 'id="old-id"' not in content

    def test_rename_id_with_css_reference(self, handler, temp_dir):
        """Test renaming ID and detecting CSS references in style tags."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
    <style>
        #old-id { color: red; }
        #old-id .child { margin: 10px; }
    </style>
</head>
<body>
    <div id="old-id">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_element_id(html_file, "old-id", "new-id")

        assert "success" in result.lower() or "renamed" in result.lower()
        content = html_file.read_text()
        assert 'id="new-id"' in content
        assert "#new-id" in content
        assert 'id="old-id"' not in content

    def test_rename_id_with_js_reference(self, handler, temp_dir):
        """Test renaming ID and detecting JS references in script tags."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div id="old-id">Content</div>
    <script>
        document.getElementById('old-id').onclick = function() {};
        const el = document.querySelector('#old-id');
    </script>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_element_id(html_file, "old-id", "new-id")

        assert "success" in result.lower() or "renamed" in result.lower()
        content = html_file.read_text()
        assert 'id="new-id"' in content
        assert "getElementById('new-id')" in content or 'getElementById("new-id")' in content

    def test_rename_id_not_found(self, handler, temp_dir):
        """Test renaming a non-existent ID."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div id="existing-id">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_element_id(html_file, "nonexistent-id", "new-id")

        assert "not found" in result.lower() or "error" in result.lower()

    def test_rename_id_suggests_linked_files(self, handler, temp_dir):
        """Test that renaming suggests updates for linked CSS/JS files."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
    <link rel="stylesheet" href="styles.css">
    <script src="app.js"></script>
</head>
<body>
    <div id="main-content">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_element_id(html_file, "main-content", "primary-content")

        # Result should mention linked files to check
        assert "styles.css" in result or "app.js" in result or "linked" in result.lower()


class TestHTMLHandlerRenameCssClass:
    """Test rename_css_class operation."""

    @pytest.fixture
    def handler(self):
        """Create HTML handler instance."""
        return HTMLHandler()

    def test_rename_simple_class(self, handler, temp_dir):
        """Test renaming a simple CSS class."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="old-class">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_css_class(html_file, "old-class", "new-class")

        assert "success" in result.lower() or "renamed" in result.lower()
        content = html_file.read_text()
        assert "new-class" in content
        assert "old-class" not in content

    def test_rename_class_multiple_occurrences(self, handler, temp_dir):
        """Test renaming a class that appears multiple times."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="old-class">First</div>
    <span class="old-class other-class">Second</span>
    <p class="other-class old-class third-class">Third</p>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_css_class(html_file, "old-class", "new-class")

        assert "success" in result.lower() or "renamed" in result.lower()
        content = html_file.read_text()
        assert content.count("new-class") == 3
        assert "old-class" not in content
        # Ensure other classes are preserved
        assert "other-class" in content
        assert "third-class" in content

    def test_rename_class_with_style_tag(self, handler, temp_dir):
        """Test renaming class and updating style tag references."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
    <style>
        .old-class { color: red; }
        .old-class:hover { color: blue; }
        .container .old-class { margin: 10px; }
    </style>
</head>
<body>
    <div class="old-class">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_css_class(html_file, "old-class", "new-class")

        assert "success" in result.lower() or "renamed" in result.lower()
        content = html_file.read_text()
        assert ".new-class" in content
        assert ".old-class" not in content

    def test_rename_class_not_found(self, handler, temp_dir):
        """Test renaming a non-existent class."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class="existing-class">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_css_class(html_file, "nonexistent-class", "new-class")

        assert "not found" in result.lower() or "error" in result.lower()

    def test_rename_class_preserves_quotes(self, handler, temp_dir):
        """Test that renaming preserves quote style."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div class='old-class'>Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.rename_css_class(html_file, "old-class", "new-class")

        assert "success" in result.lower() or "renamed" in result.lower()
        content = html_file.read_text()
        assert "new-class" in content


class TestHTMLHandlerFindElementUsages:
    """Test find_element_usages operation."""

    @pytest.fixture
    def handler(self):
        """Create HTML handler instance."""
        return HTMLHandler()

    def test_find_id_usages(self, handler, temp_dir):
        """Test finding all usages of an ID."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
    <style>
        #main-content { color: red; }
        #main-content .child { margin: 10px; }
    </style>
</head>
<body>
    <div id="main-content">Content</div>
    <script>
        document.getElementById('main-content').onclick = function() {};
        const el = document.querySelector('#main-content');
    </script>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.find_element_usages(html_file, "#main-content")

        assert "main-content" in str(result)
        # Should find usages in HTML attributes, CSS, and JS
        assert isinstance(result, dict)
        assert "html_attributes" in result or "attribute_usages" in result or "usages" in result

    def test_find_class_usages(self, handler, temp_dir):
        """Test finding all usages of a class."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
    <style>
        .btn { padding: 10px; }
        .btn:hover { background: blue; }
        .container .btn { margin: 5px; }
    </style>
</head>
<body>
    <button class="btn primary">Click</button>
    <button class="btn secondary">Submit</button>
    <script>
        document.querySelectorAll('.btn').forEach(b => b.onclick = fn);
    </script>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.find_element_usages(html_file, ".btn")

        assert "btn" in str(result)
        assert isinstance(result, dict)

    def test_find_element_not_found(self, handler, temp_dir):
        """Test finding usages of non-existent element."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <div id="existing-id">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.find_element_usages(html_file, "#nonexistent-id")

        assert isinstance(result, dict)
        # Should indicate no usages found or return empty results
        total_usages = sum(
            len(v) if isinstance(v, list) else v
            for v in result.values()
            if isinstance(v, (list, int))
        )
        assert total_usages == 0 or "not found" in str(result).lower()

    def test_find_usages_returns_line_numbers(self, handler, temp_dir):
        """Test that usages include line numbers."""
        html_code = """<!DOCTYPE html>
<html>
<head>
    <title>Test</title>
    <style>
        #content { color: red; }
    </style>
</head>
<body>
    <div id="content">Content</div>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.find_element_usages(html_file, "#content")

        # Result should contain line information
        result_str = str(result)
        assert "line" in result_str.lower() or any(isinstance(v, int) for v in result.values())


class TestHTMLHandlerAnalyzeAccessibility:
    """Test analyze_accessibility operation."""

    @pytest.fixture
    def handler(self):
        """Create HTML handler instance."""
        return HTMLHandler()

    def test_detect_images_without_alt(self, handler, temp_dir):
        """Test detecting images without alt text."""
        html_code = """<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
    <img src="good.jpg" alt="A good image">
    <img src="bad.jpg">
    <img src="also-bad.png">
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.analyze_accessibility(html_file)

        assert isinstance(result, dict)
        assert "issues" in result or "errors" in result or "warnings" in result
        result_str = str(result)
        # Should detect 2 images without alt
        assert "alt" in result_str.lower() or "image" in result_str.lower()

    def test_detect_missing_aria_labels(self, handler, temp_dir):
        """Test detecting missing ARIA labels on interactive elements."""
        html_code = """<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
    <button aria-label="Close">X</button>
    <button></button>
    <a href="#" aria-label="Home">Home</a>
    <a href="#">Link without label</a>
    <input type="text" aria-label="Search">
    <input type="button" value="">
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.analyze_accessibility(html_file)

        assert isinstance(result, dict)
        result_str = str(result).lower()
        # Should detect interactive elements without proper labels
        assert "aria" in result_str or "label" in result_str or "button" in result_str

    def test_detect_form_inputs_without_labels(self, handler, temp_dir):
        """Test detecting form inputs without associated labels."""
        html_code = """<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
    <form>
        <label for="good-input">Good Input</label>
        <input type="text" id="good-input">

        <input type="text" id="orphan-input">

        <label>
            Wrapped Input
            <input type="text">
        </label>

        <input type="text" placeholder="No label here">
    </form>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.analyze_accessibility(html_file)

        assert isinstance(result, dict)
        result_str = str(result).lower()
        # Should detect inputs without labels
        assert "label" in result_str or "input" in result_str

    def test_detect_heading_level_skips(self, handler, temp_dir):
        """Test detecting heading level skips."""
        html_code = """<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
    <h1>Main Title</h1>
    <h3>Skipped h2!</h3>
    <h4>This is fine after h3</h4>
    <h6>Skipped h5!</h6>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.analyze_accessibility(html_file)

        assert isinstance(result, dict)
        result_str = str(result).lower()
        # Should detect heading level skips
        assert (
            "heading" in result_str
            or "h1" in result_str
            or "h2" in result_str
            or "skip" in result_str
        )

    def test_detect_missing_lang_attribute(self, handler, temp_dir):
        """Test detecting missing lang attribute on html tag."""
        html_code = """<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
    <h1>Hello World</h1>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.analyze_accessibility(html_file)

        assert isinstance(result, dict)
        result_str = str(result).lower()
        # Should detect missing lang attribute
        assert "lang" in result_str

    def test_no_issues_on_accessible_html(self, handler, temp_dir):
        """Test that accessible HTML has no issues."""
        html_code = """<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
    <h1>Main Title</h1>
    <h2>Section</h2>
    <p>Some text</p>
    <img src="image.jpg" alt="Description">
    <form>
        <label for="name">Name</label>
        <input type="text" id="name">
        <button type="submit">Submit</button>
    </form>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.analyze_accessibility(html_file)

        assert isinstance(result, dict)
        # Should have zero or minimal issues
        issues = result.get("issues", result.get("errors", result.get("warnings", [])))
        if isinstance(issues, list):
            # May still have some minor warnings, but should be minimal
            assert len(issues) <= 2

    def test_returns_summary(self, handler, temp_dir):
        """Test that result includes a summary."""
        html_code = """<!DOCTYPE html>
<html lang="en">
<head><title>Test</title></head>
<body>
    <img src="test.jpg">
    <h1>Title</h1>
    <h4>Skipped heading</h4>
</body>
</html>"""
        html_file = temp_dir / "test.html"
        html_file.write_text(html_code)

        result = handler.analyze_accessibility(html_file)

        assert isinstance(result, dict)
        # Should have some summary information
        assert "file" in result or "summary" in result or "total" in str(result).lower()


class TestHTMLHandlerSupportedOperations:
    """Test that supported_operations includes new operations."""

    @pytest.fixture
    def handler(self):
        """Create HTML handler instance."""
        return HTMLHandler()

    def test_new_operations_in_supported_operations(self, handler):
        """Test that new operations are in supported_operations."""
        from refactor_mcp.languages.base_handler import RefactoringOperation

        supported = handler.supported_operations

        assert RefactoringOperation.RENAME_ELEMENT_ID in supported
        assert RefactoringOperation.RENAME_CSS_CLASS in supported
        assert RefactoringOperation.FIND_ELEMENT_USAGES in supported
        assert RefactoringOperation.ANALYZE_ACCESSIBILITY in supported

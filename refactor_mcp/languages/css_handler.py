"""CSS language handler implementation."""

import re
from pathlib import Path
from typing import Any, Dict, List, Union

try:
    import cssutils
    from cssutils import css, log

    CSSUTILS_AVAILABLE = True
    # Suppress cssutils warnings
    log.setLevel("ERROR")
except ImportError:
    CSSUTILS_AVAILABLE = False

from .base_handler import (
    BaseLanguageHandler,
    CodeStructure,
    FunctionInfo,
    ImportInfo,
    RefactoringError,
    RefactoringOperation,
)


class CSSHandler(BaseLanguageHandler):
    """Handler for CSS language refactoring operations."""

    @property
    def language_name(self) -> str:
        return "CSS"

    @property
    def file_extensions(self) -> List[str]:
        return [".css", ".scss", ".sass", ".less"]

    @property
    def supported_operations(self) -> List[RefactoringOperation]:
        return [
            RefactoringOperation.GET_CODE_STRUCTURE,
            RefactoringOperation.ANALYZE_DEPENDENCIES,
            RefactoringOperation.ORGANIZE_IMPORTS,  # For @import statements
            RefactoringOperation.RENAME_SELECTOR,
            RefactoringOperation.FIND_UNUSED_RULES,
            RefactoringOperation.MERGE_DUPLICATE_RULES,
            RefactoringOperation.EXTRACT_VARIABLES,
            RefactoringOperation.ANALYZE_SPECIFICITY,
        ]

    def can_handle_file(self, file_path: Union[str, Path]) -> bool:
        """Check if this handler can process the given file."""
        file_path = Path(file_path)

        # Check extension
        if file_path.suffix.lower() in self.file_extensions:
            return True

        # Check for CSS content patterns
        try:
            content = self.read_file_content(file_path)[:1000]  # First 1KB

            css_patterns = [
                r"\{[^}]*\}",  # CSS rule blocks
                r"@import\s+",
                r"@media\s+",
                r"@keyframes\s+",
                r"@font-face\s*\{",
                r"\w+\s*:\s*[^;]+;",  # property: value;
                r"#\w+\s*\{",  # ID selectors
                r"\.\w+\s*\{",  # class selectors
                r"[a-zA-Z]\w*\s*\{",  # element selectors
            ]

            for pattern in css_patterns:
                if re.search(pattern, content):
                    return True

        except Exception:
            pass

        return False

    def validate_syntax(self, content: str) -> bool:
        """Validate CSS syntax."""
        if CSSUTILS_AVAILABLE:
            try:
                sheet = cssutils.parseString(content)
                # If parsing succeeds without major errors, consider it valid
                return sheet is not None
            except Exception:
                return False
        else:
            # Basic pattern-based validation
            return self._basic_css_validation(content)

    def _basic_css_validation(self, content: str) -> bool:
        """Basic CSS validation without external libraries."""
        # Check for balanced braces
        open_braces = content.count("{")
        close_braces = content.count("}")

        # Allow some flexibility (comments, malformed rules, etc.)
        return abs(open_braces - close_braces) <= 2

    def parse_file(self, file_path: Union[str, Path]) -> Any:
        """Parse CSS file into a structured representation."""
        content = self.read_file_content(file_path)

        if CSSUTILS_AVAILABLE:
            try:
                return cssutils.parseString(content)
            except Exception as e:
                raise RefactoringError(f"Error parsing CSS file {file_path}: {e}")
        else:
            # Return raw content if no parser available
            return content

    def get_code_structure(self, file_path: Union[str, Path]) -> CodeStructure:
        """Get structured information about the CSS file."""
        structure = CodeStructure(file_path=str(file_path), language=self.language_name)

        try:
            if CSSUTILS_AVAILABLE:
                parsed = self.parse_file(file_path)
                if hasattr(parsed, "cssRules"):
                    self._extract_structure_cssutils(parsed, structure)
                else:
                    self._extract_structure_regex(self.read_file_content(file_path), structure)
            else:
                self._extract_structure_regex(self.read_file_content(file_path), structure)

        except Exception:
            # Fallback to regex parsing
            content = self.read_file_content(file_path)
            self._extract_structure_regex(content, structure)

        return structure

    def _extract_structure_cssutils(self, sheet, structure: CodeStructure):
        """Extract structure using cssutils."""
        for rule in sheet.cssRules:
            if rule.type == css.CSSRule.STYLE_RULE:
                # CSS style rule (selector + declarations)
                selector_text = rule.selectorText
                func_info = FunctionInfo(
                    name=f"css_rule: {selector_text}",
                    line_start=0,  # Line numbers not easily available in cssutils
                    line_end=0,
                    parameters=[selector_text],
                )
                structure.functions.append(func_info)

            elif rule.type == css.CSSRule.IMPORT_RULE:
                # @import statement
                import_info = ImportInfo(
                    module=rule.href, line=0, import_type="css_import", symbols=[]
                )
                structure.imports.append(import_info)

            elif rule.type == css.CSSRule.MEDIA_RULE:
                # @media rule
                media_text = rule.media.mediaText
                func_info = FunctionInfo(
                    name=f"media_rule: {media_text}",
                    line_start=0,
                    line_end=0,
                    parameters=[media_text],
                )
                structure.functions.append(func_info)

            elif rule.type == css.CSSRule.KEYFRAMES_RULE:
                # @keyframes rule
                keyframes_name = rule.name
                func_info = FunctionInfo(
                    name=f"keyframes: {keyframes_name}",
                    line_start=0,
                    line_end=0,
                    parameters=[keyframes_name],
                )
                structure.functions.append(func_info)

    def _extract_structure_regex(self, content: str, structure: CodeStructure):
        """Extract structure using regex patterns as fallback."""
        lines = content.split("\n")

        # Track current rule context
        current_rule = None
        brace_level = 0

        for line_num, line in enumerate(lines, 1):
            line_stripped = line.strip()

            # Skip empty lines and comments
            if not line_stripped or line_stripped.startswith("/*"):
                continue

            # Extract @import statements
            import_match = re.search(r'@import\s+(?:url\()?["\']?([^"\')\s]+)["\']?\)?', line)
            if import_match:
                import_info = ImportInfo(
                    module=import_match.group(1), line=line_num, import_type="css_import"
                )
                structure.imports.append(import_info)
                continue

            # Extract @media rules
            media_match = re.search(r"@media\s+([^{]+)\s*\{", line)
            if media_match:
                func_info = FunctionInfo(
                    name=f"media_rule: {media_match.group(1).strip()}",
                    line_start=line_num,
                    line_end=line_num,  # Will be updated when we find the closing brace
                    parameters=[media_match.group(1).strip()],
                )
                structure.functions.append(func_info)
                current_rule = func_info
                brace_level = 1
                continue

            # Extract @keyframes rules
            keyframes_match = re.search(r"@keyframes\s+([^{]+)\s*\{", line)
            if keyframes_match:
                func_info = FunctionInfo(
                    name=f"keyframes: {keyframes_match.group(1).strip()}",
                    line_start=line_num,
                    line_end=line_num,
                    parameters=[keyframes_match.group(1).strip()],
                )
                structure.functions.append(func_info)
                current_rule = func_info
                brace_level = 1
                continue

            # Extract CSS selectors (style rules)
            # Look for patterns that end with { and don't start with @
            if "{" in line and not line_stripped.startswith("@"):
                selector_match = re.search(r"([^{]+)\{", line)
                if selector_match:
                    selector_text = selector_match.group(1).strip()

                    # Clean up selector text
                    selector_text = re.sub(r"\s+", " ", selector_text)

                    func_info = FunctionInfo(
                        name=f"css_rule: {selector_text}",
                        line_start=line_num,
                        line_end=line_num,
                        parameters=[selector_text],
                    )
                    structure.functions.append(func_info)

                    if current_rule is None:  # Top-level rule
                        current_rule = func_info
                        brace_level = 1

            # Track brace levels to find rule endings
            if current_rule:
                brace_level += line.count("{") - line.count("}")
                if brace_level == 0:
                    current_rule.line_end = line_num
                    current_rule = None

    def analyze_dependencies(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze dependencies in CSS file."""
        structure = self.get_code_structure(file_path)

        # Categorize rules and imports
        import_rules = []
        style_rules: List[Dict[str, Any]] = []
        media_rules = []
        keyframes_rules = []
        other_rules = []

        for imp in structure.imports:
            import_rules.append(imp.__dict__)

        for func in structure.functions:
            if func.name.startswith("css_rule:"):
                style_rules.append(
                    {
                        "selector": func.parameters[0] if func.parameters else func.name,
                        "line": func.line_start,
                    }
                )
            elif func.name.startswith("media_rule:"):
                media_rules.append(
                    {
                        "media_query": func.parameters[0] if func.parameters else func.name,
                        "line": func.line_start,
                    }
                )
            elif func.name.startswith("keyframes:"):
                keyframes_rules.append(
                    {
                        "animation_name": func.parameters[0] if func.parameters else func.name,
                        "line": func.line_start,
                    }
                )
            else:
                other_rules.append({"rule_type": func.name, "line": func.line_start})

        # Analyze selector types
        selector_types = {
            "id_selectors": 0,
            "class_selectors": 0,
            "element_selectors": 0,
            "attribute_selectors": 0,
            "pseudo_selectors": 0,
        }

        for rule in style_rules:
            selector = str(rule["selector"])
            if "#" in selector:
                selector_types["id_selectors"] += 1
            if "." in selector:
                selector_types["class_selectors"] += 1
            if "[" in selector and "]" in selector:
                selector_types["attribute_selectors"] += 1
            if ":" in selector:
                selector_types["pseudo_selectors"] += 1
            if re.search(r"^[a-zA-Z]", selector.strip()):
                selector_types["element_selectors"] += 1

        return {
            "file": str(file_path),
            "language": self.language_name,
            "total_rules": len(structure.functions),
            "total_imports": len(structure.imports),
            "import_rules": import_rules,
            "style_rules": style_rules,
            "media_rules": media_rules,
            "keyframes_rules": keyframes_rules,
            "other_rules": other_rules,
            "selector_analysis": selector_types,
        }

    def organize_imports(self, file_path: Union[str, Path]) -> str:
        """Organize CSS @import statements."""
        content = self.read_file_content(file_path)
        lines = content.split("\n")

        # Extract @import statements
        import_lines = []
        other_lines = []
        import_line_numbers = set()

        for line_num, line in enumerate(lines):
            if re.search(r"@import\s+", line.strip()):
                import_lines.append(line.strip())
                import_line_numbers.add(line_num)
            else:
                other_lines.append((line_num, line))

        if not import_lines:
            return f"No @import statements found in {file_path}"

        # Sort import lines
        import_lines.sort()

        # Rebuild content with organized imports at the top
        new_lines = []

        # Add organized imports first
        for imp in import_lines:
            new_lines.append(imp)

        # Add a blank line after imports
        if import_lines:
            new_lines.append("")

        # Add other lines (excluding original import lines)
        for line_num, line in other_lines:
            if line_num not in import_line_numbers:
                new_lines.append(line)

        new_content = "\n".join(new_lines)
        self.write_file_content(file_path, new_content)

        return f"Successfully organized {len(import_lines)} @import statements in {file_path}"

    def get_language_specific_config(self) -> Dict[str, Any]:
        """Get CSS-specific configuration."""
        return {
            "preserve_formatting": True,
            "indent_size": 2,
            "property_sort": False,  # Whether to sort CSS properties
            "selector_sort": False,  # Whether to sort selectors
            "compress_colors": False,  # Convert #ffffff to #fff
            "remove_empty_rules": False,
            "organize_imports_at_top": True,
        }

    def rename_selector(
        self, file_path: Union[str, Path], old_selector: str, new_selector: str
    ) -> str:
        """
        Rename a CSS class or ID selector throughout the file.

        Args:
            file_path: Path to the CSS file
            old_selector: The selector to rename (e.g., '.old-class' or '#old-id')
            new_selector: The new selector name (e.g., '.new-class' or '#new-id')

        Returns:
            A string describing the result of the operation
        """
        content = self.read_file_content(file_path)

        # Escape special regex characters in the selector, but preserve . and #
        old_escaped = re.escape(old_selector)

        # Build a regex pattern that matches the selector in various contexts:
        # - At the start of a line or after whitespace/comma
        # - Before {, :, whitespace, comma, >, +, ~, [, or end of line
        pattern = rf"(?<![a-zA-Z0-9_-])({old_escaped})(?=[{{\s:,>+~\[\]]|$)"

        # Count matches before replacement
        matches = re.findall(pattern, content)
        count = len(matches)

        if count == 0:
            return f"Selector '{old_selector}' not found in {file_path}"

        # Perform the replacement
        new_content = re.sub(pattern, new_selector, content)

        # Write the modified content back
        self.write_file_content(file_path, new_content)

        return f"Successfully renamed '{old_selector}' to '{new_selector}' ({count} occurrences) in {file_path}"

    def find_unused_rules(
        self, file_path: Union[str, Path], html_file_path: Union[str, Path]
    ) -> str:
        """
        Detect CSS rules that don't match any elements in the provided HTML file.

        Args:
            file_path: Path to the CSS file
            html_file_path: Path to the HTML file to check against

        Returns:
            A string describing unused rules found
        """
        css_content = self.read_file_content(file_path)
        html_content = self.read_file_content(html_file_path)

        # Extract all selectors from CSS
        css_selectors = self._extract_selectors(css_content)

        # Extract classes and IDs from HTML
        html_classes = set(re.findall(r'class=["\']([^"\']+)["\']', html_content))
        html_ids = set(re.findall(r'id=["\']([^"\']+)["\']', html_content))

        # Expand multi-class attributes (e.g., class="foo bar" -> {"foo", "bar"})
        expanded_classes = set()
        for class_attr in html_classes:
            expanded_classes.update(class_attr.split())
        html_classes = expanded_classes

        # Extract element names from HTML
        html_elements = set(re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)", html_content.lower()))

        unused_rules = []

        for selector in css_selectors:
            if self._is_selector_unused(selector, html_classes, html_ids, html_elements):
                unused_rules.append(selector)

        if not unused_rules:
            return f"No unused CSS rules found in {file_path} when checked against {html_file_path}"

        unused_list = "\n  - ".join(unused_rules)
        return f"Found {len(unused_rules)} unused CSS rules in {file_path}:\n  - {unused_list}"

    def _extract_selectors(self, css_content: str) -> List[str]:
        """Extract all selectors from CSS content."""
        selectors = []

        # Remove comments
        css_no_comments = re.sub(r"/\*[\s\S]*?\*/", "", css_content)

        # Find all rule blocks (selector { ... })
        # Match selectors before opening braces
        pattern = r"([^{@]+)\{"

        matches = re.findall(pattern, css_no_comments)

        for match in matches:
            # Split by comma to handle grouped selectors
            selector_group = match.strip()

            # Skip @-rules content
            if selector_group.startswith("@") or not selector_group:
                continue

            # Handle nested selectors (in @media, etc.)
            for selector in selector_group.split(","):
                selector = selector.strip()
                if selector and not selector.startswith("@"):
                    selectors.append(selector)

        return selectors

    def _is_selector_unused(
        self,
        selector: str,
        html_classes: set,
        html_ids: set,
        html_elements: set,
    ) -> bool:
        """Check if a selector is unused based on HTML content."""
        # Skip pseudo-elements and pseudo-classes only selectors
        if selector.startswith(":"):
            return False

        # Skip universal selector
        if selector.strip() == "*":
            return False

        # Skip :root selector
        if ":root" in selector:
            return False

        # Extract the base components of the selector
        # Remove pseudo-classes/elements for checking
        base_selector = re.sub(r"::?[a-zA-Z-]+(\([^)]*\))?", "", selector)

        # Check for class selectors
        classes_in_selector = re.findall(r"\.([a-zA-Z0-9_-]+)", base_selector)
        for cls in classes_in_selector:
            if cls not in html_classes:
                return True

        # Check for ID selectors
        ids_in_selector = re.findall(r"#([a-zA-Z0-9_-]+)", base_selector)
        for id_sel in ids_in_selector:
            if id_sel not in html_ids:
                return True

        # Check for element selectors (only if no class/id in selector)
        if not classes_in_selector and not ids_in_selector:
            # Extract element names from selector
            elements_in_selector = re.findall(r"(?:^|[\s>+~])([a-zA-Z][a-zA-Z0-9]*)", base_selector)
            for elem in elements_in_selector:
                if elem.lower() not in html_elements:
                    return True

        return False

    def merge_duplicate_rules(self, file_path: Union[str, Path]) -> str:
        """
        Find CSS rules with identical declarations that could be merged.

        Args:
            file_path: Path to the CSS file

        Returns:
            A string describing duplicate rules found and merge suggestions
        """
        content = self.read_file_content(file_path)

        # Remove comments
        content_no_comments = re.sub(r"/\*[\s\S]*?\*/", "", content)

        # Parse rules into selector -> declarations mapping
        rules: Dict[str, List[str]] = {}
        # Match: selector { declarations }
        pattern = r"([^{@][^{]*)\{([^}]*)\}"

        for match in re.finditer(pattern, content_no_comments):
            selector = match.group(1).strip()
            declarations = match.group(2).strip()

            # Skip @-rules
            if selector.startswith("@") or not selector:
                continue

            # Normalize declarations (remove extra whitespace, sort properties)
            normalized = self._normalize_declarations(declarations)

            if normalized:
                if normalized not in rules:
                    rules[normalized] = []
                rules[normalized].append(selector)

        # Find duplicates (declarations with multiple selectors)
        duplicates = []
        for declarations, selectors in rules.items():
            if len(selectors) > 1:
                duplicates.append(
                    {
                        "selectors": selectors,
                        "declarations": declarations,
                        "suggestion": f"{', '.join(selectors)} {{ {declarations} }}",
                    }
                )

        if not duplicates:
            return f"No duplicate CSS rules found in {file_path}"

        result_lines = [f"Found {len(duplicates)} sets of duplicate rules in {file_path}:"]
        for i, dup in enumerate(duplicates, 1):
            result_lines.append(f"\n{i}. The following selectors have identical declarations:")
            for sel in dup["selectors"]:
                result_lines.append(f"   - {sel}")
            result_lines.append(f"   Suggested merge: {dup['suggestion']}")

        return "\n".join(result_lines)

    def _normalize_declarations(self, declarations: str) -> str:
        """Normalize CSS declarations for comparison."""
        # Split into individual properties
        props = []
        for decl in declarations.split(";"):
            decl = decl.strip()
            if decl and ":" in decl:
                # Normalize whitespace around : and values
                prop, value = decl.split(":", 1)
                prop = prop.strip().lower()
                value = " ".join(value.split()).lower()
                props.append(f"{prop}: {value}")

        # Sort properties for consistent comparison
        props.sort()
        return "; ".join(props)

    def extract_variables(self, file_path: Union[str, Path]) -> str:
        """
        Find repeated values (colors, sizes, etc.) and suggest CSS custom properties.

        Args:
            file_path: Path to the CSS file

        Returns:
            A string with variable extraction suggestions
        """
        content = self.read_file_content(file_path)

        # Remove comments
        content_no_comments = re.sub(r"/\*[\s\S]*?\*/", "", content)

        # Track value occurrences
        value_counts: Dict[str, List[str]] = {}

        # Patterns for extractable values
        patterns = {
            "color_hex": r"#[0-9a-fA-F]{3,8}\b",
            "color_rgb": r"rgba?\([^)]+\)",
            "color_hsl": r"hsla?\([^)]+\)",
            "size_px": r"\b\d+px\b",
            "size_rem": r"\b\d+(?:\.\d+)?rem\b",
            "size_em": r"\b\d+(?:\.\d+)?em\b",
            "font_family": r"font-family:\s*([^;]+)",
        }

        # Extract values
        for pattern_name, pattern in patterns.items():
            matches = re.findall(pattern, content_no_comments, re.IGNORECASE)
            for match in matches:
                value = match.strip().lower() if isinstance(match, str) else match
                if value not in value_counts:
                    value_counts[value] = []
                value_counts[value].append(pattern_name)

        # Filter to values that appear multiple times (threshold: 2+)
        repeated_values = {
            value: occurrences
            for value, occurrences in value_counts.items()
            if len(occurrences) >= 2
        }

        if not repeated_values:
            return (
                f"No repeated values found that could be extracted to CSS variables in {file_path}"
            )

        # Generate suggestions
        suggestions = []
        for value, occurrences in sorted(repeated_values.items(), key=lambda x: -len(x[1])):
            # Generate a variable name based on the value type
            var_name = self._suggest_variable_name(value, occurrences[0])
            suggestions.append(
                {
                    "value": value,
                    "occurrences": len(occurrences),
                    "suggested_variable": var_name,
                    "usage": f"var({var_name})",
                }
            )

        result_lines = [
            f"Found {len(suggestions)} repeated values in {file_path} that could be CSS variables:"
        ]
        result_lines.append("\nSuggested :root variables:")
        result_lines.append(":root {")

        for sug in suggestions:
            result_lines.append(f"  {sug['suggested_variable']}: {sug['value']};")

        result_lines.append("}")
        result_lines.append("\nDetails:")

        for i, sug in enumerate(suggestions, 1):
            result_lines.append(
                f"  {i}. '{sug['value']}' appears {sug['occurrences']} times -> {sug['suggested_variable']}"
            )

        return "\n".join(result_lines)

    def _suggest_variable_name(self, value: str, value_type: str) -> str:
        """Generate a suggested CSS variable name based on value and type."""
        if value_type.startswith("color"):
            # Try to generate a meaningful color name
            if value.startswith("#"):
                return f"--color-{value[1:].lower()}"
            return f"--color-{hash(value) % 1000}"
        elif value_type.startswith("size"):
            # Use the numeric value
            num = re.search(r"\d+(?:\.\d+)?", value)
            if num:
                unit = value.replace(num.group(), "").strip()
                return f"--spacing-{num.group()}{unit}"
            return f"--size-{hash(value) % 1000}"
        elif value_type == "font_family":
            return "--font-family-primary"
        return f"--var-{hash(value) % 1000}"

    def analyze_specificity(self, file_path: Union[str, Path]) -> str:
        """
        Report on selector specificity issues (overly specific selectors, !important usage).

        Args:
            file_path: Path to the CSS file

        Returns:
            A string with specificity analysis results
        """
        content = self.read_file_content(file_path)

        # Remove comments
        content_no_comments = re.sub(r"/\*[\s\S]*?\*/", "", content)

        # Analyze !important usage
        important_count = content_no_comments.count("!important")

        # Extract and analyze selectors
        selector_analysis = []
        pattern = r"([^{@][^{]*)\{"

        for match in re.finditer(pattern, content_no_comments):
            selector_group = match.group(1).strip()

            # Skip @-rules
            if selector_group.startswith("@") or not selector_group:
                continue

            # Handle grouped selectors
            for selector in selector_group.split(","):
                selector = selector.strip()
                if selector:
                    specificity = self._calculate_specificity(selector)
                    selector_analysis.append(
                        {
                            "selector": selector,
                            "specificity": specificity,
                            "score": specificity[0] * 100 + specificity[1] * 10 + specificity[2],
                        }
                    )

        # Identify issues
        issues = []
        warnings = []

        # Check for !important usage
        if important_count > 0:
            issues.append(
                f"Found {important_count} uses of !important - consider refactoring to avoid specificity wars"
            )

        # Check for high specificity selectors (score > 30 is considered high)
        high_specificity = [s for s in selector_analysis if s["score"] > 30]
        if high_specificity:
            for sel in high_specificity:
                warnings.append(
                    f"High specificity selector: '{sel['selector']}' "
                    f"(specificity: {sel['specificity'][0]},{sel['specificity'][1]},{sel['specificity'][2]})"
                )

        # Check for ID selectors (generally discouraged)
        id_selectors = [s for s in selector_analysis if s["specificity"][0] > 0]
        if id_selectors:
            warnings.append(
                f"Found {len(id_selectors)} selector(s) using ID selectors - "
                "consider using classes for better reusability"
            )

        # Calculate statistics
        if selector_analysis:
            avg_score = sum(s["score"] for s in selector_analysis) / len(selector_analysis)
            max_score = max(s["score"] for s in selector_analysis)
            min_score = min(s["score"] for s in selector_analysis)
        else:
            avg_score = max_score = min_score = 0

        # Build result
        result_lines = [f"Specificity Analysis for {file_path}:"]
        result_lines.append(f"\nTotal selectors analyzed: {len(selector_analysis)}")
        result_lines.append(
            f"Specificity scores - Min: {min_score}, Max: {max_score}, Avg: {avg_score:.1f}"
        )
        result_lines.append(f"!important declarations: {important_count}")

        if issues:
            result_lines.append("\nIssues:")
            for issue in issues:
                result_lines.append(f"  - {issue}")

        if warnings:
            result_lines.append("\nWarnings:")
            for warning in warnings[:10]:  # Limit to first 10 warnings
                result_lines.append(f"  - {warning}")
            if len(warnings) > 10:
                result_lines.append(f"  ... and {len(warnings) - 10} more warnings")

        if not issues and not warnings:
            result_lines.append("\nGood specificity practices detected - no major issues found.")

        return "\n".join(result_lines)

    def _calculate_specificity(self, selector: str) -> tuple:
        """
        Calculate CSS specificity for a selector.

        Returns a tuple of (id_count, class_count, element_count)
        """
        # Remove pseudo-elements (they count as elements)
        pseudo_elements = len(re.findall(r"::[a-zA-Z-]+", selector))
        selector = re.sub(r"::[a-zA-Z-]+", "", selector)

        # Count IDs
        id_count = len(re.findall(r"#[a-zA-Z0-9_-]+", selector))

        # Count classes, attribute selectors, and pseudo-classes
        class_count = len(re.findall(r"\.[a-zA-Z0-9_-]+", selector))
        attr_count = len(re.findall(r"\[[^\]]+\]", selector))
        pseudo_class_count = len(re.findall(r":[a-zA-Z-]+(?:\([^)]*\))?", selector))
        class_total = class_count + attr_count + pseudo_class_count

        # Count element selectors
        # Remove IDs, classes, attribute selectors, pseudo-classes
        cleaned = re.sub(r"#[a-zA-Z0-9_-]+", "", selector)
        cleaned = re.sub(r"\.[a-zA-Z0-9_-]+", "", cleaned)
        cleaned = re.sub(r"\[[^\]]+\]", "", cleaned)
        cleaned = re.sub(r":[a-zA-Z-]+(?:\([^)]*\))?", "", cleaned)
        # Remove combinators
        cleaned = re.sub(r"[>+~\s]+", " ", cleaned)

        element_count = len(
            [e for e in cleaned.split() if e and e != "*" and re.match(r"^[a-zA-Z]", e)]
        )
        element_count += pseudo_elements

        return (id_count, class_total, element_count)

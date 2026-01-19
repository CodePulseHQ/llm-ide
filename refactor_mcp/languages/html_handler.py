"""HTML language handler implementation."""

import re
from pathlib import Path
from typing import Any, Dict, List, Union

try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    from lxml import etree
    from lxml import html as lxml_html

    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

from .base_handler import (
    BaseLanguageHandler,
    CodeStructure,
    FunctionInfo,
    ImportInfo,
    RefactoringError,
    RefactoringOperation,
)


class HTMLHandler(BaseLanguageHandler):
    """Handler for HTML language refactoring operations."""

    @property
    def language_name(self) -> str:
        return "HTML"

    @property
    def file_extensions(self) -> List[str]:
        return [".html", ".htm", ".xhtml", ".svg"]

    @property
    def supported_operations(self) -> List[RefactoringOperation]:
        return [
            RefactoringOperation.GET_CODE_STRUCTURE,
            RefactoringOperation.ANALYZE_DEPENDENCIES,
            RefactoringOperation.ORGANIZE_IMPORTS,  # For script/link tags
            RefactoringOperation.RENAME_ELEMENT_ID,
            RefactoringOperation.RENAME_CSS_CLASS,
            RefactoringOperation.FIND_ELEMENT_USAGES,
            RefactoringOperation.ANALYZE_ACCESSIBILITY,
        ]

    def can_handle_file(self, file_path: Union[str, Path]) -> bool:
        """Check if this handler can process the given file."""
        file_path = Path(file_path)

        # Check extension
        if file_path.suffix.lower() in self.file_extensions:
            return True

        # Check for HTML content patterns
        try:
            content = self.read_file_content(file_path)[:1000]  # First 1KB
            content_lower = content.lower()

            html_patterns = [
                r"<!doctype\s+html",
                r"<html",
                r"<head>",
                r"<body>",
                r"<meta\s+",
                r"<title>",
                r"<div\s+",
                r"<script\s+",
                r"<style\s+",
                r"<link\s+",
            ]

            for pattern in html_patterns:
                if re.search(pattern, content_lower):
                    return True

        except Exception:
            pass

        return False

    def validate_syntax(self, content: str) -> bool:
        """Validate HTML syntax."""
        if BS4_AVAILABLE:
            try:
                soup = BeautifulSoup(content, "html.parser")
                # Basic validation - check if parsing succeeds without major issues
                return soup is not None
            except Exception:
                return False
        elif LXML_AVAILABLE:
            try:
                # Use lxml for stricter validation
                parser = etree.HTMLParser()
                tree = etree.fromstring(content, parser)
                return tree is not None
            except Exception:
                return False
        else:
            # Basic pattern-based validation
            return self._basic_html_validation(content)

    def _basic_html_validation(self, content: str) -> bool:
        """Basic HTML validation without external libraries."""
        # Check for balanced tags
        opening_tags = re.findall(r"<(\w+)(?:\s[^>]*)?\s*/?>", content)
        closing_tags = re.findall(r"</(\w+)>", content)

        # Self-closing tags don't need closing counterparts
        self_closing = {
            "img",
            "br",
            "hr",
            "input",
            "meta",
            "link",
            "area",
            "base",
            "col",
            "embed",
            "source",
            "track",
            "wbr",
        }

        # Remove self-closing tags from opening_tags
        opening_tags = [tag for tag in opening_tags if tag.lower() not in self_closing]

        # Basic check: roughly the same number of opening and closing tags
        return abs(len(opening_tags) - len(closing_tags)) <= 3  # Allow some flexibility

    def parse_file(self, file_path: Union[str, Path]) -> Any:
        """Parse HTML file into a structured representation."""
        content = self.read_file_content(file_path)

        if BS4_AVAILABLE:
            try:
                return BeautifulSoup(content, "html.parser")
            except Exception as e:
                raise RefactoringError(f"Error parsing HTML file {file_path}: {e}")
        elif LXML_AVAILABLE:
            try:
                return lxml_html.fromstring(content)
            except Exception as e:
                raise RefactoringError(f"Error parsing HTML file {file_path}: {e}")
        else:
            # Return raw content if no parser available
            return content

    def get_code_structure(self, file_path: Union[str, Path]) -> CodeStructure:
        """Get structured information about the HTML file."""
        structure = CodeStructure(file_path=str(file_path), language=self.language_name)

        try:
            parsed = self.parse_file(file_path)

            if BS4_AVAILABLE and hasattr(parsed, "find_all"):
                self._extract_structure_bs4(parsed, structure)
            elif LXML_AVAILABLE and hasattr(parsed, "xpath"):
                self._extract_structure_lxml(parsed, structure)
            else:
                self._extract_structure_regex(self.read_file_content(file_path), structure)

        except Exception:
            # Fallback to regex parsing
            content = self.read_file_content(file_path)
            self._extract_structure_regex(content, structure)

        return structure

    def _extract_structure_bs4(self, soup, structure: CodeStructure):
        """Extract structure using BeautifulSoup."""
        # Extract script tags as "functions"
        for script in soup.find_all("script"):
            if script.get("src"):
                # External script
                func_info = FunctionInfo(
                    name=f"external_script: {script.get('src')}",
                    line_start=0,  # Line numbers not easily available in BS4
                    line_end=0,
                    parameters=[script.get("src")],
                )
                structure.functions.append(func_info)
            elif script.string:
                # Inline script
                script_content = script.string.strip()
                if script_content:
                    # Try to extract function names from JavaScript
                    js_functions = re.findall(r"function\s+(\w+)", script_content)
                    for func_name in js_functions:
                        func_info = FunctionInfo(
                            name=f"js_function: {func_name}", line_start=0, line_end=0
                        )
                        structure.functions.append(func_info)

        # Extract link/style tags as "imports"
        for link in soup.find_all("link"):
            href = link.get("href")
            rel = (
                link.get("rel", [""])[0]
                if isinstance(link.get("rel"), list)
                else link.get("rel", "")
            )

            if href:
                import_info = ImportInfo(
                    module=href,
                    line=0,
                    import_type=f"html_link_{rel}",
                    symbols=[rel] if rel else [],
                )
                structure.imports.append(import_info)

        # Extract style tags
        for style in soup.find_all("style"):
            if style.string:
                import_info = ImportInfo(
                    module="<inline_style>", line=0, import_type="html_inline_style"
                )
                structure.imports.append(import_info)

    def _extract_structure_lxml(self, tree, structure: CodeStructure):
        """Extract structure using lxml."""
        # Extract script tags
        for script in tree.xpath("//script"):
            src = script.get("src")
            if src:
                func_info = FunctionInfo(
                    name=f"external_script: {src}",
                    line_start=script.sourceline or 0,
                    line_end=script.sourceline or 0,
                    parameters=[src],
                )
                structure.functions.append(func_info)
            elif script.text:
                # Inline script
                js_functions = re.findall(r"function\s+(\w+)", script.text)
                for func_name in js_functions:
                    func_info = FunctionInfo(
                        name=f"js_function: {func_name}",
                        line_start=script.sourceline or 0,
                        line_end=script.sourceline or 0,
                    )
                    structure.functions.append(func_info)

        # Extract link tags
        for link in tree.xpath("//link"):
            href = link.get("href")
            rel = link.get("rel", "")

            if href:
                import_info = ImportInfo(
                    module=href,
                    line=link.sourceline or 0,
                    import_type=f"html_link_{rel}",
                    symbols=[rel] if rel else [],
                )
                structure.imports.append(import_info)

        # Extract style tags
        for style in tree.xpath("//style"):
            import_info = ImportInfo(
                module="<inline_style>", line=style.sourceline or 0, import_type="html_inline_style"
            )
            structure.imports.append(import_info)

    def _extract_structure_regex(self, content: str, structure: CodeStructure):
        """Extract structure using regex patterns as fallback."""
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()

            # Extract script tags
            script_src_match = re.search(r'<script[^>]*src=["\']([^"\']+)["\']', line)
            if script_src_match:
                func_info = FunctionInfo(
                    name=f"external_script: {script_src_match.group(1)}",
                    line_start=line_num,
                    line_end=line_num,
                    parameters=[script_src_match.group(1)],
                )
                structure.functions.append(func_info)

            # Extract link tags
            link_match = re.search(
                r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']([^"\']+)["\']', line
            )
            if not link_match:
                link_match = re.search(
                    r'<link[^>]*rel=["\']([^"\']+)["\'][^>]*href=["\']([^"\']+)["\']', line
                )
                if link_match:
                    # Swap groups if rel comes before href
                    href, rel = link_match.group(2), link_match.group(1)
                else:
                    # Simple href extraction
                    href_match = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', line)
                    if href_match:
                        href, rel = href_match.group(1), "unknown"
                    else:
                        href, rel = None, None
            else:
                href, rel = link_match.group(1), link_match.group(2)

            if href:
                import_info = ImportInfo(
                    module=href,
                    line=line_num,
                    import_type=f"html_link_{rel}",
                    symbols=[rel] if rel else [],
                )
                structure.imports.append(import_info)

            # Extract inline styles
            if "<style" in line_lower:
                import_info = ImportInfo(
                    module="<inline_style>", line=line_num, import_type="html_inline_style"
                )
                structure.imports.append(import_info)

    def analyze_dependencies(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Analyze dependencies in HTML file."""
        structure = self.get_code_structure(file_path)

        # Categorize imports/dependencies
        css_files = []
        js_files = []
        images = []
        other_resources = []

        for imp in structure.imports:
            if "stylesheet" in imp.import_type or imp.module.endswith(".css"):
                css_files.append(imp.__dict__)
            elif "script" in imp.import_type or imp.module.endswith(".js"):
                js_files.append(imp.__dict__)
            elif any(
                ext in imp.module for ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico"]
            ):
                images.append(imp.__dict__)
            else:
                other_resources.append(imp.__dict__)

        return {
            "file": str(file_path),
            "language": self.language_name,
            "total_resources": len(structure.imports),
            "css_files": css_files,
            "js_files": js_files,
            "images": images,
            "other_resources": other_resources,
            "inline_scripts": len([f for f in structure.functions if "js_function" in f.name]),
            "external_scripts": len(
                [f for f in structure.functions if "external_script" in f.name]
            ),
        }

    def organize_imports(self, file_path: Union[str, Path]) -> str:
        """Organize HTML dependencies (link and script tags)."""
        content = self.read_file_content(file_path)

        # This is a complex operation for HTML as tags can be in different sections
        # For now, provide basic organization within <head> section

        head_pattern = r"(<head[^>]*>)(.*?)(</head>)"
        head_match = re.search(head_pattern, content, re.DOTALL | re.IGNORECASE)

        if not head_match:
            return f"No <head> section found in {file_path} - cannot organize resources"

        head_start, head_content, head_end = head_match.groups()

        # Extract and categorize head elements
        meta_tags = re.findall(r"<meta[^>]*>", head_content, re.IGNORECASE)
        link_tags = re.findall(r"<link[^>]*>", head_content, re.IGNORECASE)
        script_tags = re.findall(r"<script[^>]*(?:/>|>[^<]*</script>)", head_content, re.IGNORECASE)
        title_tag = re.search(r"<title[^>]*>.*?</title>", head_content, re.IGNORECASE)

        # Organize: meta tags first, then title, then CSS links, then scripts
        organized_head = []

        # Add meta tags
        for meta in meta_tags:
            organized_head.append("  " + meta)

        # Add title
        if title_tag:
            organized_head.append("  " + title_tag.group())

        # Add CSS links
        css_links = [link for link in link_tags if "stylesheet" in link.lower()]
        for link in css_links:
            organized_head.append("  " + link)

        # Add other links
        other_links = [link for link in link_tags if "stylesheet" not in link.lower()]
        for link in other_links:
            organized_head.append("  " + link)

        # Add scripts
        for script in script_tags:
            organized_head.append("  " + script)

        # Rebuild head section
        new_head_content = "\n" + "\n".join(organized_head) + "\n"
        new_head_section = head_start + new_head_content + head_end

        # Replace in original content
        new_content = content.replace(head_match.group(), new_head_section)

        self.write_file_content(file_path, new_content)

        return f"Successfully organized HTML resources in {file_path}"

    def get_language_specific_config(self) -> Dict[str, Any]:
        """Get HTML-specific configuration."""
        return {
            "preserve_formatting": True,
            "indent_size": 2,
            "self_closing_tags": True,
            "attribute_quotes": "double",
            "organize_head_tags": True,
            "minify_inline_css": False,
            "minify_inline_js": False,
        }

    def rename_element_id(self, file_path: Union[str, Path], old_id: str, new_id: str) -> str:
        """Rename an ID attribute and suggest updates for linked CSS/JS files.

        Args:
            file_path: Path to the HTML file.
            old_id: The current ID to rename.
            new_id: The new ID name.

        Returns:
            A message indicating success or failure, with suggestions for linked files.
        """
        content = self.read_file_content(file_path)

        # Check if the ID exists in the HTML
        id_pattern = rf'id=["\']({re.escape(old_id)})["\']'
        if not re.search(id_pattern, content):
            return f"Error: ID '{old_id}' not found in {file_path}"

        # Track changes made
        changes = []

        # 1. Rename the id attribute itself
        new_content = re.sub(
            rf'id=(["\'])({re.escape(old_id)})\1',
            rf"id=\1{new_id}\1",
            content,
        )
        changes.append(f"Renamed id attribute from '{old_id}' to '{new_id}'")

        # 2. Update CSS selectors in <style> tags
        def replace_css_id_selector(match):
            style_content = match.group(1)
            # Replace #old_id but not when it's part of a longer word
            updated = re.sub(
                rf"#{re.escape(old_id)}(?=\s|{{|,|:|\.|\[|\)|>|\+|~|$)",
                f"#{new_id}",
                style_content,
            )
            return f"<style>{updated}</style>"

        style_pattern = r"<style[^>]*>(.*?)</style>"
        new_content_with_styles = re.sub(
            style_pattern, replace_css_id_selector, new_content, flags=re.DOTALL | re.IGNORECASE
        )
        if new_content_with_styles != new_content:
            changes.append("Updated CSS selectors in <style> tags")
            new_content = new_content_with_styles

        # 3. Update JavaScript references in <script> tags
        def replace_js_id_references(match):
            script_content = match.group(1)
            updated = script_content

            # getElementById('old_id') or getElementById("old_id")
            updated = re.sub(
                rf"getElementById\(['\"]({re.escape(old_id)})['\"]\)",
                f"getElementById('{new_id}')",
                updated,
            )

            # querySelector('#old_id') or querySelector("#old_id")
            updated = re.sub(
                rf"querySelector\(['\"]#{re.escape(old_id)}['\"]\)",
                f"querySelector('#{new_id}')",
                updated,
            )

            # querySelectorAll('#old_id')
            updated = re.sub(
                rf"querySelectorAll\(['\"]#{re.escape(old_id)}['\"]\)",
                f"querySelectorAll('#{new_id}')",
                updated,
            )

            return f"<script>{updated}</script>"

        script_pattern = r"<script[^>]*>(.*?)</script>"
        new_content_with_scripts = re.sub(
            script_pattern, replace_js_id_references, new_content, flags=re.DOTALL | re.IGNORECASE
        )
        if new_content_with_scripts != new_content:
            changes.append("Updated JavaScript references in <script> tags")
            new_content = new_content_with_scripts

        # Write the updated content
        self.write_file_content(file_path, new_content)

        # 4. Find linked CSS and JS files to suggest manual updates
        linked_files = self._get_linked_files(content)
        suggestions = []
        if linked_files["css"]:
            suggestions.append(
                f"Check these CSS files for #{old_id} selectors: {', '.join(linked_files['css'])}"
            )
        if linked_files["js"]:
            suggestions.append(
                f"Check these JS files for references to '{old_id}': {', '.join(linked_files['js'])}"
            )

        result = f"Successfully renamed ID '{old_id}' to '{new_id}' in {file_path}.\n"
        result += "Changes made:\n- " + "\n- ".join(changes)
        if suggestions:
            result += "\n\nLinked files to check:\n- " + "\n- ".join(suggestions)

        return result

    def rename_css_class(self, file_path: Union[str, Path], old_class: str, new_class: str) -> str:
        """Rename a CSS class across the HTML file.

        Args:
            file_path: Path to the HTML file.
            old_class: The current class name to rename.
            new_class: The new class name.

        Returns:
            A message indicating success or failure.
        """
        content = self.read_file_content(file_path)

        # Check if the class exists in the HTML
        class_pattern = rf'class=["\'][^"\']*\b{re.escape(old_class)}\b[^"\']*["\']'
        if not re.search(class_pattern, content):
            return f"Error: Class '{old_class}' not found in {file_path}"

        # Track changes
        changes = []
        rename_count = 0

        # 1. Rename class in class attributes
        def replace_class_in_attr(match):
            nonlocal rename_count
            quote = match.group(1)
            classes = match.group(2)
            # Split classes, replace the target, rejoin
            class_list = classes.split()
            new_class_list = []
            for cls in class_list:
                if cls == old_class:
                    new_class_list.append(new_class)
                    rename_count += 1
                else:
                    new_class_list.append(cls)
            return f'class={quote}{" ".join(new_class_list)}{quote}'

        class_attr_pattern = r'class=(["\'])([^"\']*)["\']'
        new_content = re.sub(class_attr_pattern, replace_class_in_attr, content)

        if rename_count > 0:
            changes.append(f"Renamed {rename_count} class attribute occurrence(s)")

        # 2. Update CSS selectors in <style> tags
        def replace_css_class_selector(match):
            style_content = match.group(1)
            # Replace .old_class but not when it's part of a longer word
            updated = re.sub(
                rf"\.{re.escape(old_class)}(?=\s|{{|,|:|\.|\[|\)|>|\+|~|:|$)",
                f".{new_class}",
                style_content,
            )
            return f"<style>{updated}</style>"

        style_pattern = r"<style[^>]*>(.*?)</style>"
        new_content_with_styles = re.sub(
            style_pattern, replace_css_class_selector, new_content, flags=re.DOTALL | re.IGNORECASE
        )
        if new_content_with_styles != new_content:
            changes.append("Updated CSS selectors in <style> tags")
            new_content = new_content_with_styles

        # 3. Update JavaScript references in <script> tags
        def replace_js_class_references(match):
            script_content = match.group(1)
            updated = script_content

            # querySelector('.old_class')
            updated = re.sub(
                rf"querySelector\(['\"]\.{re.escape(old_class)}['\"]\)",
                f"querySelector('.{new_class}')",
                updated,
            )

            # querySelectorAll('.old_class')
            updated = re.sub(
                rf"querySelectorAll\(['\"]\.{re.escape(old_class)}['\"]\)",
                f"querySelectorAll('.{new_class}')",
                updated,
            )

            # classList.add/remove/contains/toggle('old_class')
            for method in ["add", "remove", "contains", "toggle"]:
                updated = re.sub(
                    rf"classList\.{method}\(['\"]({re.escape(old_class)})['\"]\)",
                    f"classList.{method}('{new_class}')",
                    updated,
                )

            return f"<script>{updated}</script>"

        script_pattern = r"<script[^>]*>(.*?)</script>"
        new_content_with_scripts = re.sub(
            script_pattern,
            replace_js_class_references,
            new_content,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if new_content_with_scripts != new_content:
            changes.append("Updated JavaScript references in <script> tags")
            new_content = new_content_with_scripts

        # Write the updated content
        self.write_file_content(file_path, new_content)

        result = f"Successfully renamed class '{old_class}' to '{new_class}' in {file_path}.\n"
        result += "Changes made:\n- " + "\n- ".join(changes)

        return result

    def find_element_usages(
        self, file_path: Union[str, Path], element_identifier: str
    ) -> Dict[str, Any]:
        """Find all occurrences of an ID or class in the HTML file.

        Args:
            file_path: Path to the HTML file.
            element_identifier: ID (prefixed with #) or class (prefixed with .).

        Returns:
            Dictionary with usage information including line numbers.
        """
        content = self.read_file_content(file_path)
        lines = content.split("\n")

        # Determine if it's an ID or class
        is_id = element_identifier.startswith("#")
        is_class = element_identifier.startswith(".")

        if not is_id and not is_class:
            # Assume it's an ID if no prefix
            is_id = True
            identifier = element_identifier
        else:
            identifier = element_identifier[1:]  # Remove prefix

        result: Dict[str, Any] = {
            "file": str(file_path),
            "identifier": element_identifier,
            "type": "id" if is_id else "class",
            "html_attributes": [],
            "css_usages": [],
            "js_usages": [],
            "total_usages": 0,
        }

        # Search for usages in HTML attributes
        for line_num, line in enumerate(lines, 1):
            if is_id:
                # Look for id="identifier" or id='identifier'
                if re.search(rf'id=["\']({re.escape(identifier)})["\']', line):
                    result["html_attributes"].append(
                        {
                            "line": line_num,
                            "content": line.strip()[:80],
                            "type": "id_attribute",
                        }
                    )
            else:
                # Look for class containing the identifier
                if re.search(rf'class=["\'][^"\']*\b{re.escape(identifier)}\b[^"\']*["\']', line):
                    result["html_attributes"].append(
                        {
                            "line": line_num,
                            "content": line.strip()[:80],
                            "type": "class_attribute",
                        }
                    )

        # Search for usages in <style> tags
        style_pattern = r"<style[^>]*>(.*?)</style>"
        for match in re.finditer(style_pattern, content, re.DOTALL | re.IGNORECASE):
            style_content = match.group(1)
            style_start = content[: match.start()].count("\n") + 1

            style_lines = style_content.split("\n")
            for i, style_line in enumerate(style_lines):
                if is_id:
                    if re.search(
                        rf"#{re.escape(identifier)}(?=\s|{{|,|:|\.|\[|\)|>|\+|~|$)", style_line
                    ):
                        result["css_usages"].append(
                            {
                                "line": style_start + i,
                                "content": style_line.strip()[:80],
                                "type": "css_selector",
                            }
                        )
                else:
                    if re.search(
                        rf"\.{re.escape(identifier)}(?=\s|{{|,|:|\.|\[|\)|>|\+|~|:|$)", style_line
                    ):
                        result["css_usages"].append(
                            {
                                "line": style_start + i,
                                "content": style_line.strip()[:80],
                                "type": "css_selector",
                            }
                        )

        # Search for usages in <script> tags
        script_pattern = r"<script[^>]*>(.*?)</script>"
        for match in re.finditer(script_pattern, content, re.DOTALL | re.IGNORECASE):
            script_content = match.group(1)
            script_start = content[: match.start()].count("\n") + 1

            script_lines = script_content.split("\n")
            for i, script_line in enumerate(script_lines):
                found = False
                if is_id:
                    # getElementById, querySelector with #
                    if re.search(
                        rf"getElementById\(['\"]({re.escape(identifier)})['\"]\)", script_line
                    ):
                        found = True
                    if re.search(
                        rf"querySelector\(['\"]#{re.escape(identifier)}['\"]\)", script_line
                    ):
                        found = True
                    if re.search(
                        rf"querySelectorAll\(['\"]#{re.escape(identifier)}['\"]\)", script_line
                    ):
                        found = True
                else:
                    # querySelector with .
                    if re.search(
                        rf"querySelector\(['\"]\.{re.escape(identifier)}['\"]\)", script_line
                    ):
                        found = True
                    if re.search(
                        rf"querySelectorAll\(['\"]\.{re.escape(identifier)}['\"]\)", script_line
                    ):
                        found = True
                    # classList methods
                    if re.search(
                        rf"classList\.\w+\(['\"]({re.escape(identifier)})['\"]\)", script_line
                    ):
                        found = True

                if found:
                    result["js_usages"].append(
                        {
                            "line": script_start + i,
                            "content": script_line.strip()[:80],
                            "type": "js_reference",
                        }
                    )

        result["total_usages"] = (
            len(result["html_attributes"]) + len(result["css_usages"]) + len(result["js_usages"])
        )

        return result

    def analyze_accessibility(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Check for accessibility issues in the HTML file.

        Checks for:
        - Images without alt text
        - Missing ARIA labels on interactive elements
        - Form inputs without labels
        - Heading level skips
        - Missing lang attribute on html tag

        Args:
            file_path: Path to the HTML file.

        Returns:
            Dictionary with accessibility issues and summary.
        """
        content = self.read_file_content(file_path)
        issues = []

        # 1. Check for missing lang attribute on <html> tag
        html_tag_match = re.search(r"<html[^>]*>", content, re.IGNORECASE)
        if html_tag_match:
            if not re.search(r'\blang=["\'][^"\']+["\']', html_tag_match.group(), re.IGNORECASE):
                html_line = content[: html_tag_match.start()].count("\n") + 1
                issues.append(
                    {
                        "type": "missing_lang",
                        "severity": "error",
                        "line": html_line,
                        "message": "Missing lang attribute on <html> tag",
                        "suggestion": 'Add lang attribute, e.g., <html lang="en">',
                    }
                )

        # 2. Check for images without alt text
        img_pattern = r"<img\b[^>]*>"
        for match in re.finditer(img_pattern, content, re.IGNORECASE):
            img_tag = match.group()
            img_line = content[: match.start()].count("\n") + 1

            # Check if alt attribute exists
            has_alt = re.search(r'\balt=["\']', img_tag, re.IGNORECASE)
            if not has_alt:
                src_match = re.search(r'src=["\']([^"\']*)["\']', img_tag)
                src = src_match.group(1) if src_match else "unknown"
                issues.append(
                    {
                        "type": "missing_alt",
                        "severity": "error",
                        "line": img_line,
                        "message": f"Image without alt text: {src}",
                        "suggestion": "Add descriptive alt attribute to the image",
                    }
                )

        # 3. Check for interactive elements without labels
        # Buttons without text or aria-label
        button_pattern = r"<button\b[^>]*>([^<]*)</button>"
        for match in re.finditer(button_pattern, content, re.IGNORECASE | re.DOTALL):
            button_tag = match.group()
            button_content = match.group(1).strip()
            button_line = content[: match.start()].count("\n") + 1

            has_aria_label = re.search(r'aria-label=["\']', button_tag, re.IGNORECASE) is not None
            has_aria_labelledby = (
                re.search(r'aria-labelledby=["\']', button_tag, re.IGNORECASE) is not None
            )

            if not button_content and not has_aria_label and not has_aria_labelledby:
                issues.append(
                    {
                        "type": "empty_button",
                        "severity": "warning",
                        "line": button_line,
                        "message": "Button without visible text or aria-label",
                        "suggestion": "Add text content or aria-label to the button",
                    }
                )

        # 4. Check for form inputs without labels
        input_pattern = r"<input\b[^>]*>"
        for match in re.finditer(input_pattern, content, re.IGNORECASE):
            input_tag = match.group()
            input_line = content[: match.start()].count("\n") + 1

            # Skip hidden and submit/button types that don't need labels
            input_type = re.search(r'type=["\']([^"\']*)["\']', input_tag, re.IGNORECASE)
            if input_type:
                type_val = input_type.group(1).lower()
                if type_val in ["hidden", "submit", "button", "reset", "image"]:
                    continue

            # Check for id to find associated label
            input_id_match = re.search(r'id=["\']([^"\']*)["\']', input_tag, re.IGNORECASE)
            has_aria_label_input = (
                re.search(r'aria-label=["\']', input_tag, re.IGNORECASE) is not None
            )
            has_aria_labelledby_input = (
                re.search(r'aria-labelledby=["\']', input_tag, re.IGNORECASE) is not None
            )

            # Check if wrapped in a label
            input_pos = match.start()
            before_input = content[max(0, input_pos - 200) : input_pos]
            after_input = content[input_pos : min(len(content), input_pos + 200)]
            is_wrapped = "<label" in before_input.lower() and "</label>" in after_input.lower()

            if input_id_match:
                input_id = input_id_match.group(1)
                # Check for label with for attribute
                label_pattern = rf'<label[^>]*for=["\']({re.escape(input_id)})["\']'
                has_label = re.search(label_pattern, content, re.IGNORECASE) is not None
            else:
                has_label = False

            if (
                not has_label
                and not has_aria_label_input
                and not has_aria_labelledby_input
                and not is_wrapped
            ):
                issues.append(
                    {
                        "type": "input_without_label",
                        "severity": "warning",
                        "line": input_line,
                        "message": "Form input without associated label",
                        "suggestion": "Add a <label for='id'> or aria-label attribute",
                    }
                )

        # 5. Check for heading level skips
        heading_pattern = r"<(h[1-6])\b[^>]*>"
        headings = []
        for match in re.finditer(heading_pattern, content, re.IGNORECASE):
            heading_tag = match.group(1).lower()
            heading_level = int(heading_tag[1])
            heading_line = content[: match.start()].count("\n") + 1
            headings.append((heading_level, heading_line))

        for i in range(1, len(headings)):
            current_level = headings[i][0]
            prev_level = headings[i - 1][0]

            # Skip if going to a smaller heading (h1 -> h2 is fine, h1 -> h3 is not)
            if current_level > prev_level + 1:
                issues.append(
                    {
                        "type": "heading_skip",
                        "severity": "warning",
                        "line": headings[i][1],
                        "message": f"Heading level skip: h{prev_level} to h{current_level}",
                        "suggestion": f"Use h{prev_level + 1} instead of h{current_level}",
                    }
                )

        # Create summary
        error_count = sum(1 for issue in issues if issue["severity"] == "error")
        warning_count = sum(1 for issue in issues if issue["severity"] == "warning")

        return {
            "file": str(file_path),
            "total_issues": len(issues),
            "errors": error_count,
            "warnings": warning_count,
            "issues": issues,
            "summary": {
                "missing_lang": sum(1 for i in issues if i["type"] == "missing_lang"),
                "missing_alt": sum(1 for i in issues if i["type"] == "missing_alt"),
                "empty_buttons": sum(1 for i in issues if i["type"] == "empty_button"),
                "inputs_without_labels": sum(
                    1 for i in issues if i["type"] == "input_without_label"
                ),
                "heading_skips": sum(1 for i in issues if i["type"] == "heading_skip"),
            },
        }

    def _get_linked_files(self, content: str) -> Dict[str, List[str]]:
        """Extract linked CSS and JS files from HTML content.

        Args:
            content: HTML content string.

        Returns:
            Dictionary with 'css' and 'js' lists of file paths.
        """
        linked_files: Dict[str, List[str]] = {"css": [], "js": []}

        # Find CSS links
        css_pattern = r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']stylesheet["\']'
        css_pattern_alt = r'<link[^>]*rel=["\']stylesheet["\'][^>]*href=["\']([^"\']+)["\']'

        for pattern in [css_pattern, css_pattern_alt]:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                href = match.group(1)
                if not href.startswith("http") and href not in linked_files["css"]:
                    linked_files["css"].append(href)

        # Find JS scripts
        js_pattern = r'<script[^>]*src=["\']([^"\']+)["\']'
        for match in re.finditer(js_pattern, content, re.IGNORECASE):
            src = match.group(1)
            if not src.startswith("http") and src not in linked_files["js"]:
                linked_files["js"].append(src)

        return linked_files

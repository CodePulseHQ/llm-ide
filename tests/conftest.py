"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_python_code():
    """Sample Python code for testing."""
    return '''"""Sample Python module."""

import os
import sys
from pathlib import Path

def first_function():
    """First function."""
    return "first"

class SampleClass:
    """Sample class."""
    
    def method_one(self):
        """First method."""
        return "method_one"
    
    def method_two(self):
        """Second method."""
        return "method_two"

def second_function():
    """Second function."""
    return "second"

def third_function():
    """Third function."""  
    return "third"
'''


@pytest.fixture
def sample_javascript_code():
    """Sample JavaScript code for testing."""
    return """const fs = require('fs');
const path = require('path');

function firstFunction() {
    return 'first';
}

class SampleClass {
    methodOne() {
        return 'method_one';
    }
    
    methodTwo() {
        return 'method_two';
    }
}

const arrowFunction = () => {
    return 'arrow';
};

function secondFunction() {
    return 'second';
}

module.exports = {
    firstFunction,
    SampleClass,
    arrowFunction,
    secondFunction
};
"""


@pytest.fixture
def sample_typescript_code():
    """Sample TypeScript code for testing."""
    return """import { EventEmitter } from 'events';
import * as fs from 'fs';

interface User {
    id: number;
    name: string;
}

type UserRole = 'admin' | 'user' | 'guest';

function firstFunction(): string {
    return 'first';
}

class UserManager {
    private users: User[] = [];
    
    addUser(user: User): void {
        this.users.push(user);
    }
    
    getUser(id: number): User | undefined {
        return this.users.find(user => user.id === id);
    }
}

export { User, UserRole, firstFunction, UserManager };
"""


@pytest.fixture
def sample_go_code():
    """Sample Go code for testing."""
    return """package main

import (
    "fmt"
    "os"
    "strings"
)

type User struct {
    ID   int
    Name string
}

type UserInterface interface {
    GetName() string
    GetID() int
}

func (u *User) GetName() string {
    return u.Name
}

func (u *User) GetID() int {
    return u.ID
}

func main() {
    user := User{
        ID:   1,
        Name: "John Doe",
    }
    fmt.Printf("User: %s (ID: %d)\\n", user.GetName(), user.GetID())
}

func processData(data string) string {
    return strings.ToUpper(data)
}
"""


@pytest.fixture
def sample_html_code():
    """Sample HTML code for testing."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sample Page</title>
    <link rel="stylesheet" href="styles.css">
    <script src="https://cdn.jsdelivr.net/npm/jquery@3.6.0/dist/jquery.min.js"></script>
</head>
<body>
    <header>
        <h1>Sample Page</h1>
    </header>
    
    <main>
        <div id="content">
            <p>This is sample content.</p>
        </div>
    </main>
    
    <script src="scripts.js"></script>
    <script>
        function inlineFunction() {
            return 'inline';
        }
    </script>
</body>
</html>
"""


@pytest.fixture
def sample_css_code():
    """Sample CSS code for testing."""
    return """@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;700&display=swap');
@import 'components/buttons.css';

:root {
    --primary-color: #007bff;
    --secondary-color: #6c757d;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: 'Roboto', sans-serif;
    line-height: 1.6;
    color: #333;
}

.header {
    background-color: var(--primary-color);
    color: white;
    padding: 1rem;
}

#content {
    padding: 2rem;
}

@media (max-width: 768px) {
    .header {
        padding: 0.5rem;
    }
}
"""


@pytest.fixture
def test_files(
    temp_dir,
    sample_python_code,
    sample_javascript_code,
    sample_typescript_code,
    sample_go_code,
    sample_html_code,
    sample_css_code,
):
    """Create test files with sample content."""
    files = {
        "sample.py": sample_python_code,
        "sample.js": sample_javascript_code,
        "sample.ts": sample_typescript_code,
        "sample.go": sample_go_code,
        "sample.html": sample_html_code,
        "sample.css": sample_css_code,
    }

    file_paths = {}
    for filename, content in files.items():
        file_path = temp_dir / filename
        file_path.write_text(content)
        file_paths[filename] = file_path

    return file_paths


@pytest.fixture
def all_language_handlers():
    """Get instances of all language handlers."""
    from refactor_mcp.languages.css_handler import CSSHandler
    from refactor_mcp.languages.go_handler import GoHandler
    from refactor_mcp.languages.html_handler import HTMLHandler
    from refactor_mcp.languages.javascript_handler import JavaScriptHandler
    from refactor_mcp.languages.python_handler import PythonHandler
    from refactor_mcp.languages.typescript_handler import TypeScriptHandler

    return {
        "python": PythonHandler(),
        "javascript": JavaScriptHandler(),
        "typescript": TypeScriptHandler(),
        "html": HTMLHandler(),
        "css": CSSHandler(),
        "go": GoHandler(),
    }

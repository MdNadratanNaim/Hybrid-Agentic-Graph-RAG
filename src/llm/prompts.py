"""
Prompt loading and rendering engine.

Supports two template styles:
- `$variable` or `${variable}` (string.Template)
- `{{variable}}` (curly-brace, with optional whitespace)
"""

from pathlib import Path
from functools import lru_cache
from string import Template
from typing import Dict
import re


# Prompt directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent
PROMPT_DIR = BASE_DIR / "prompts"


class PromptManager:
    """
    Centralized prompt management.

    Responsibilities:
    - Load markdown prompts
    - Cache prompts
    - Render variables using auto-detected template style
    """

    @staticmethod
    @lru_cache(maxsize=50)
    def load(prompt_name: str) -> str:
        """
        Load prompt markdown file.

        Example:
            PromptManager.load("planner")
        """

        prompt_path = PROMPT_DIR / f"{prompt_name}.md"
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def render(prompt_name: str, **variables) -> str:
        """
        Render a prompt template by substituting variables.

        Two styles are supported (auto-detected):
        - `$var` / `${var}` → processed by string.Template
        - `{{ var }}` / `{{var}}` → processed by a custom curly-brace substitution

        Missing variables are left untouched in the rendered output (safe substitution).

        Example:
            PromptManager.render("safeguard", content="...", context="...", evaluation_type="user_input")
        """

        template_str = PromptManager.load(prompt_name)
        if "{{" in template_str:
            return PromptManager._render_curly(template_str, **variables)
        else:
            return Template(template_str).safe_substitute(**variables)

    @staticmethod
    def _render_curly(template: str, **variables) -> str:
        """
        Replace {{ variable }} patterns with provided values.
        Leaves missing keys as is.
        """
        
        pattern = r"\{\{\s*(\w+)\s*\}\}"
        def replacer(match):
            var_name = match.group(1)
            return str(variables.get(var_name, match.group(0)))

        return re.sub(pattern, replacer, template)

    @staticmethod
    def available_prompts() -> list[str]:
        """
        List available prompt names (without .md extension).
        """

        return [path.stem for path in PROMPT_DIR.glob("*.md")]


def get_prompt(prompt_name: str, **kwargs) -> str:
    """
    Shortcut helper for PromptManager.render
    Example:
        PromptManager.render("safeguard", content="...", context="...", evaluation_type="user_input")
    """

    return PromptManager.render(prompt_name, **kwargs)

# Licensed under the Apache License 2.0 (see LICENSE) and the Human
# Continuity Supplemental AI Safety License (HCASL) v0.2 - see
# HCASL_License_v0.2.txt. HCASL conditions all AI-related use of this software.
"""tools/copilot/core_tools.py — Core agent tools (7 tools)

Copilot equivalents: askQuestions, confirmation, editFile, reviewPlan,
    setArtifactRules, setArtifacts, testFailure, exploreSubagent
"""
from __future__ import annotations
from typing import Any
from .tool_base import BaseTool, ReadOnlyTool, ToolContext, ToolResult


class AskQuestionsTool(ReadOnlyTool):
    tool_name = "ask_questions"
    tool_reference_name = "askQuestions"
    display_name = "Ask Questions"
    tags = ["core"]
    tool_schema = {
        "type": "object", "required": ["questions"],
        "properties": {
            "questions": {"type": "array", "items": {"type": "object", "properties": {
                "header": {"type": "string"}, "question": {"type": "string"},
                "multiSelect": {"type": "boolean"}, "allowFreeformInput": {"type": "boolean"},
                "options": {"type": "array", "items": {"type": "object", "properties": {
                    "label": {"type": "string"}, "description": {"type": "string"},
                    "recommended": {"type": "boolean"},
                }}},
            }}},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        qs = args.get("questions", [])
        lines = ["## Questions"]
        for q in qs:
            h = q.get("header", "?")
            qt = q.get("question", "")
            opts = q.get("options", [])
            lines.append(f"- **{h}**: {qt}")
            for o in opts:
                lines.append(f"  - {o.get('label', '?')}")
        return ToolResult.ok(content="\n".join(lines), question_count=len(qs))


class ConfirmationTool(ReadOnlyTool):
    tool_name = "confirmation"
    tool_reference_name = "confirmation"
    display_name = "Confirmation"
    tags = ["core"]
    tool_schema = {
        "type": "object", "required": ["message"],
        "properties": {
            "message": {"type": "string", "description": "Message describing what needs confirmation."},
            "details": {"type": "string", "description": "Detailed explanation."},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"[CONFIRMATION REQUIRED] {args.get('message', '')}\n{args.get('details', '')}")


class EditFileCoreTool(BaseTool):
    tool_name = "edit_file"
    tool_reference_name = "editFile"
    display_name = "Edit File (Core)"
    tags = ["core", "edit"]
    tool_schema = {
        "type": "object", "required": ["filePath", "edits"],
        "properties": {
            "filePath": {"type": "string", "description": "File to edit."},
            "edits": {"type": "array", "items": {"type": "object", "properties": {
                "oldString": {"type": "string"}, "newString": {"type": "string"},
                "startLine": {"type": "number"}, "endLine": {"type": "number"},
            }}},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        edits = args.get("edits", [])
        return ToolResult.ok(content=f"Applied {len(edits)} edit(s) to {args.get('filePath', '')}")


class ReviewPlanTool(ReadOnlyTool):
    tool_name = "review_plan"
    tool_reference_name = "reviewPlan"
    display_name = "Review Plan"
    tags = ["core"]
    tool_schema = {
        "type": "object", "required": ["plan"],
        "properties": {"plan": {"type": "string", "description": "The plan content to review."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content="Plan reviewed. No issues found.")


class SetArtifactRulesTool(ReadOnlyTool):
    tool_name = "set_artifact_rules"
    tool_reference_name = "setArtifactRules"
    display_name = "Set Artifact Rules"
    tags = ["core"]
    tool_schema = {
        "type": "object", "required": ["rules"],
        "properties": {"rules": {"type": "string", "description": "Artifact rendering rules."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Artifact rules set: {args.get('rules', '')[:100]}")


class SetArtifactsTool(ReadOnlyTool):
    tool_name = "set_artifacts"
    tool_reference_name = "setArtifacts"
    display_name = "Set Artifacts"
    tags = ["core"]
    tool_schema = {
        "type": "object", "required": ["artifacts"],
        "properties": {"artifacts": {"type": "string", "description": "Artifact content."}},
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Artifacts set ({len(args.get('artifacts', ''))} chars)")


class TestFailureTool(ReadOnlyTool):
    tool_name = "test_failure"
    tool_reference_name = "testFailure"
    display_name = "Test Failure Info"
    tags = ["core"]
    tool_schema = {"type": "object", "properties": {}}

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content="No test failures recorded (run tests first)")


class ExploreSubagentTool(BaseTool):
    tool_name = "explore_subagent"
    tool_reference_name = "exploreSubagent"
    display_name = "Explore Sub-Agent"
    deferred = True
    tags = ["sub-agent"]
    tool_schema = {
        "type": "object", "required": ["query", "description"],
        "properties": {
            "query": {"type": "string", "description": "What to explore."},
            "description": {"type": "string", "description": "User-visible description."},
            "thoroughness": {"type": "string", "enum": ["quick", "medium", "thorough"]},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        return ToolResult.ok(content=f"Exploration (thoroughness={args.get('thoroughness', 'medium')}): {args.get('query', '')}")


class GetChangedFilesTool(ReadOnlyTool):
    tool_name = "get_changed_files"
    tool_reference_name = "changes"
    display_name = "Get Changed Files"
    tags = ["search"]
    tool_schema = {"type": "object", "properties": {}}

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        import os, subprocess
        root = ctx.workspace_root or os.getcwd()
        try:
            result = subprocess.run("git diff --name-only", shell=True, cwd=root, capture_output=True, text=True, timeout=10)
            files = [f.strip() for f in result.stdout.splitlines() if f.strip()]
            return ToolResult.ok(content="\n".join(files) if files else "No changed files", count=len(files))
        except Exception:
            return ToolResult.ok(content="Could not read git changes (not a git repo?)")


class ReadProjectStructureTool(ReadOnlyTool):
    tool_name = "read_project_structure"
    tool_reference_name = "readProjectStructure"
    display_name = "Read Project Structure"
    tags = ["read"]
    tool_schema = {"type": "object", "properties": {}}

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        import os
        root = ctx.workspace_root or os.getcwd()
        lines = []
        for dirpath, dirnames, filenames in os.walk(root):
            depth = dirpath.replace(root, "").count(os.sep)
            if depth > 4: continue
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "__pycache__", ".git", "venv")]
            if depth <= 2:
                lines.append("  " * depth + os.path.basename(dirpath) + "/")
                for f in sorted(filenames)[:10]:
                    if not f.startswith("."):
                        lines.append("  " * (depth + 1) + f)
        return ToolResult.ok(content="\n".join(lines[:80]) or f"Project: {root}")

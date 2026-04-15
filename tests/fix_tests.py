import re
import ast

with open("tests/test_tools.py") as f:
    content = f.read()

tools = [
    "session_start",
    "task_start",
    "save_note",
    "update_task",
    "update_task_status",
    "get_meeting",
    "save_meeting_summary",
    "session_end",
    "ingest_meeting",
    "create_task",
    "rewind_task",
    "what_am_i_missing",
    "resume_session",
]

# Step 1: Replace await tool_name(...) with await resolve_depends(...)
# But we need to capture and skip the first argument (ctx)
for tool in tools:
    # Match: await tool_name(ctx, ...)  -> replace with: await resolve_depends(tool, ctx, db_session, ...)
    # (skip: ctx, after the tool name is the first arg we skip)
    escaped_tool = re.escape(tool)
    # Pattern: await tool_name(ctx, args...)
    # We want to replace the whole call EXCEPT keep ctx as second arg
    pattern = r"(\s*await )" + escaped_tool + r"\(ctx, "
    # Replacement: resolve_depends(tool, ctx, db_session,  (note: ctx already there, just skip it)
    replacement = r"\1resolve_depends(" + escaped_tool + ", ctx, db_session, "
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

# Step 2: Keep patch.multiple() but keep body as-is
lines = content.split("\n")
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    if "with patch.multiple(" in line and "wizard.tools" in line:
        # Keep the with line and body as-is
        new_lines.append(line)
        with_indent = len(line) - len(line.lstrip())
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if not next_line.strip():
                new_lines.append(next_line)
                i += 1
                continue
            next_indent = len(next_line) - len(next_line.lstrip())
            if next_indent <= with_indent:
                break
            # Keep body as-is (it's already transformed)
            new_lines.append(next_line)
            i += 1
    else:
        new_lines.append(line)
        i += 1

content = "\n".join(new_lines)

# Add resolve_depends to imports
old_import = (
    "from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session"
)
new_import = "from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session, resolve_depends"
content = content.replace(old_import, new_import)

with open("tests/test_tools.py", "w") as f:
    f.write(content)

try:
    ast.parse(content)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax error at line {e.lineno}: {e.msg}")
    lines = content.split("\n")
    for j in range(max(0, e.lineno - 3), min(len(lines), e.lineno + 3)):
        print(f"  {j + 1}: {lines[j]}")

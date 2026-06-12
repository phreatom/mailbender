import os

# Give Rich a wide, stable width during tests so table cell text isn't wrapped
# or truncated (the render module's Consoles auto-detect width in production).
os.environ.setdefault("COLUMNS", "200")

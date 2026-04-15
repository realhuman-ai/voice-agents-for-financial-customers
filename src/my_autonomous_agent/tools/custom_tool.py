from crewai.tools import tool

@tool("FileWriteTool")
def file_write_tool(filename: str, content: str) -> str:
    """Useful to save research or code results to a local file on Windows."""
    try:
        with open(filename, 'w') as f:
            f.write(content)
        return f"Successfully saved to {filename}"
    except Exception as e:
        return f"Error saving file: {str(e)}"
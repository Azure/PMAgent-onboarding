import os
import yaml
import requests
import uvicorn
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("Spec Fetcher")

# Define paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "../docs")
INDEX_FILE = os.path.join(DOCS_DIR, "index.yml")
REPO_BASE_URL = "https://raw.githubusercontent.com/Azure/PMAgent-onboarding/main"

@mcp.tool()
def list_specs() -> str:
    """
    List all available specifications from the index.
    Returns a formatted string listing spec names and descriptions.
    """
    try:
        # Try local index first
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, 'r') as f:
                    data = yaml.safe_load(f)
            except Exception:
                data = None
        else:
            data = None
            
        # If local failed or empty, try remote
        if not data:
             url = f"{REPO_BASE_URL}/spec/docs/index.yml"
             try:
                 response = requests.get(url)
                 if response.status_code == 200:
                     data = yaml.safe_load(response.text)
             except Exception:
                 pass

        if not data:
            return "No specifications found (checked local and remote)."

        result = "Available Specifications:\n"
        for item in data:
            name = item.get('name', 'Unknown')
            desc = item.get('description', 'No description')
            result += f"- {name}: {desc}\n"
        
        return result
    except Exception as e:
        return f"Error reading index: {str(e)}"

@mcp.tool()
def fetch_spec(name: str) -> str:
    """
    Fetch the content of a specification by its name.
    First tries to fetch locally, then falls back to the public repository.
    Args:
        name: The name of the spec to fetch (as listed in index).
    """
    try:
        # 1. Get Index Data (Local or Remote)
        data = None
        if os.path.exists(INDEX_FILE):
            try:
                with open(INDEX_FILE, 'r') as f:
                    data = yaml.safe_load(f)
            except Exception:
                data = None
        
        if not data:
             url = f"{REPO_BASE_URL}/spec/docs/index.yml"
             try:
                 response = requests.get(url)
                 if response.status_code == 200:
                     data = yaml.safe_load(response.text)
             except Exception:
                 pass
        
        if not data:
             return "Error: Could not load index file (local or remote)."

        # Find the file associated with the name
        target_file = None
        for item in data:
            if item.get('name') == name:
                target_file = item.get('file')
                break
        
        if not target_file:
            return f"Error: Spec '{name}' not found in index."
        
        normalized_path = os.path.normpath(target_file)

        # 2. Try Fetching Local File
        local_file_path = os.path.join(DOCS_DIR, normalized_path)
        if os.path.exists(local_file_path):
            try:
                with open(local_file_path, 'r') as f:
                    return f.read()
            except Exception:
                pass # Fall through to remote
        
        # 3. Try Fetching Remote File
        url = f"{REPO_BASE_URL}/spec/docs/{normalized_path}"
        
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            return f"Error: Spec file '{normalized_path}' not found locally or in public repository (404).\nURL: {url}"
        else:
            return f"Error: Failed to fetch spec. Status code: {response.status_code}"

    except Exception as e:
        return f"Error fetching spec: {str(e)}"

if __name__ == "__main__":
    uvicorn.run(mcp.sse_app(), port=8100)


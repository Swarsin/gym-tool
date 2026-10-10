import os
import sys
import uvicorn

if __name__ == "__main__":
    # Ensure backend directory is in pythonpath if running from root
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
    if os.path.exists(backend_dir) and backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)

    port_env = os.environ.get("PORT", "8000")
    try:
        port = int(port_env)
    except (ValueError, TypeError):
        port = 8000

    print(f"Starting Uvicorn server on 0.0.0.0:{port}...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)

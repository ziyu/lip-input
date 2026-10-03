"""Local-only service. Put an operator-managed HTTPS/auth proxy in front."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("server.lip_server.app:app", host="127.0.0.1", port=8000,
                workers=1, access_log=False, proxy_headers=False)

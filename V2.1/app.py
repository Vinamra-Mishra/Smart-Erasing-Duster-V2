"""
Smart Erasing Duster Digital Twin - HidenCloud / Pterodactyl Root Runner
File: app.py
"""
import os
import sys
from pathlib import Path

# Add possible backend directories to Python path
CURRENT_DIR = Path(__file__).resolve().parent
search_dirs = [
    CURRENT_DIR,
    CURRENT_DIR / "backend",
    CURRENT_DIR / "V2.1",
    CURRENT_DIR / "V2.1" / "backend",
    Path("/home/container"),
    Path("/home/container/backend"),
    Path("/home/container/V2.1"),
    Path("/home/container/V2.1/backend"),
]
for p in search_dirs:
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Ensure required ports are configured
primary_port = int(os.environ.get("SERVER_PORT", os.environ.get("PORT", "24666")))
rtp_port = int(os.environ.get("RTP_PORT", "25343"))

os.environ["PORT"] = str(primary_port)
os.environ["SERVER_PORT"] = str(primary_port)
os.environ["RTP_PORT"] = str(rtp_port)

print("=" * 60)
print("  Smart Erasing Duster V2.1 - Digital Twin Engine")
print(f"  Primary Port (Web UI / API / WS): {primary_port}")
print(f"  Secondary Port (RTP Stream UDP):  {rtp_port}")
print("=" * 60)

if __name__ == "__main__":
    import uvicorn
    # Start ASGI application with Uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=primary_port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )

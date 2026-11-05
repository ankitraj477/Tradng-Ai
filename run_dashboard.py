"""
Launcher for Tradng-Ai Multi-Desk Web Dashboard.
Serves 4 dedicated visual desks: Main Overview, Intraday MIS, Stocks / Swing CNC, and F&O Spreads.
Usage: python run_dashboard.py
"""

from app.dashboard import _load_runtime

if __name__ == "__main__":
    app = _load_runtime()
    print("==================================================")
    print("   Tradng-Ai PRO v7.1: Multi-Desk Dashboard Server")
    print("   Listening at: http://127.0.0.1:5000            ")
    print("==================================================")
    app.run(host="127.0.0.1", port=5000, debug=False)

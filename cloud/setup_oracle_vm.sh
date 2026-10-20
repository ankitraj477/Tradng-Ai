#!/usr/bin/env bash
# ==============================================================================
# Oracle Cloud VM One-Click Setup Script for Tradng-Ai
# Works on both Ubuntu and Oracle Linux
# ==============================================================================
set -e

echo "=== [1/5] Updating packages and installing dependencies ==="
if [ -f /etc/debian_version ]; then
    # Ubuntu / Debian
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-pip python3-venv git curl ufw
    CURRENT_USER="ubuntu"
elif [ -f /etc/oracle-release ] || [ -f /etc/redhat-release ]; then
    # Oracle Linux / RHEL
    sudo dnf update -y
    sudo dnf install -y python3.12 python3.12-pip git curl firewalld || sudo yum install -y python3 git curl
    CURRENT_USER="opc"
else
    CURRENT_USER="$USER"
fi

APP_DIR="/home/$CURRENT_USER/Tradng-Ai"

echo "=== [2/5] Setting up virtual environment in $APP_DIR ==="
cd "$APP_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== [3/5] Configuring firewall on Oracle Cloud VM ==="
# Open port 5000 in local OS firewall
if command -v ufw >/dev/null 2>&1; then
    sudo ufw allow 5000/tcp || true
fi
if command -v iptables >/dev/null 2>&1; then
    sudo iptables -I INPUT 1 -p tcp --dport 5000 -j ACCEPT || true
    if command -v netfilter-persistent >/dev/null 2>&1; then
        sudo netfilter-persistent save || true
    fi
fi

if command -v firewall-cmd >/dev/null 2>&1; then
    sudo firewall-cmd --zone=public --add-port=5000/tcp --permanent || true
    sudo firewall-cmd --reload || true
fi

echo "=== [4/5] Creating and enabling 24/7 systemd background service ==="
SERVICE_FILE="/etc/systemd/system/tradng-ai.service"

sudo bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=Tradng-Ai Multi-Desk Trading Platform & Dashboard
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python run.py --live
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=APP_HOST=0.0.0.0
Environment=APP_PORT=5000

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable tradng-ai.service
sudo systemctl restart tradng-ai.service

echo "=== [5/5] Tradng-Ai service status ==="
sudo systemctl status tradng-ai.service --no-pager

echo ""
echo "=========================================================================="
echo "SUCCESS! Tradng-Ai is now running 24/7 in the background."
echo "Access the dashboard at: http://<YOUR_ORACLE_PUBLIC_IP>:5000"
echo "View live logs anytime with: journalctl -u tradng-ai.service -f"
echo "=========================================================================="

#!/bin/bash
set -e

cd ~/pippin_arb_bot

echo "Installing backend dependencies..."
python3 -m pip install -r requirements.txt || python3 -m pip install -r requirements.txt --user

echo "Building frontend..."
cd frontend
rm -f .env.local  # Ensure production build uses dynamic WS URL
npm install
npm run build
cd ..

echo "Restarting backend PM2 process..."
pm2 delete pippin_frontend || true
pm2 restart arb-backend || pm2 start main.py --name "arb-backend" --interpreter python3
pm2 save

echo "Copying frontend to Nginx web root..."
sudo rm -rf /usr/share/nginx/html/arbitrage/*
sudo cp -r frontend/dist/* /usr/share/nginx/html/arbitrage/

echo "Deployment complete."

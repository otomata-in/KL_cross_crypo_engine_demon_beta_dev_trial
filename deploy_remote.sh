#!/bin/bash
set -e

cd ~/pippin_arb_bot

echo "Installing backend dependencies..."
python3 -m pip install -r requirements.txt || python3 -m pip install -r requirements.txt --user

echo "Building frontend..."
cd frontend
npm install
npm run build
cd ..

echo "Restarting PM2 processes..."
pm2 delete arb-backend || true
pm2 delete pippin_frontend || true

pm2 start main.py --name "arb-backend" --interpreter python3
pm2 serve frontend/dist 8000 --name "pippin_frontend" --spa
pm2 save

echo "Deployment complete."

#!/bin/bash
set -e

echo "🚀 Starting Smart Kanban..."

# Run database migrations
cd /workspace/backend
echo "📊 Initializing database..."
python -c "
import asyncio
from app.database import init_db
asyncio.run(init_db())
"

# Seed demo data if this is first run
if [ ! -f /workspace/data/.seeded ]; then
    echo "🌱 Seeding demo data..."
    python -m scripts.seed_demo
    touch /workspace/data/.seeded
else
    echo "✅ Demo data already seeded"
fi

# Start all services with supervisor
echo "🎯 Starting services..."
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf

#!/bin/bash

# start_workload.sh
# Usage: ./start_workload.sh [LOW|MEDIUM|HIGH] [DURATION_SECONDS]

PROFILE=${1:-LOW}
DURATION=${2:-60}

# Users and Spawn Rate mappings
if [ "$PROFILE" = "HIGH" ]; then
    USERS=100
    SPAWN_RATE=10
elif [ "$PROFILE" = "MEDIUM" ]; then
    USERS=50
    SPAWN_RATE=5
else
    USERS=10
    SPAWN_RATE=2
fi

echo "Starting $PROFILE workload simulation for $DURATION seconds ($USERS users)..."

WORKLOAD_PROFILE=$PROFILE locust \
    -f client/locustfile.py \
    --headless \
    -u $USERS \
    -r $SPAWN_RATE \
    -t ${DURATION}s \
    --host http://localhost:8000 \
    --html client/report_${PROFILE}.html
    
echo "Simulation complete. Report saved to client/report_${PROFILE}.html"

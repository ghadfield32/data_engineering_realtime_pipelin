#!/bin/bash
set -x

echo "Environment variables:"
env | grep AIRFLOW

echo "Waiting for Postgres to be fully ready..."
sleep 5

echo "Running Airflow DB upgrade..."
airflow db upgrade 2>&1 | tee /logs/db_upgrade.log
DB_RESULT=$?
echo "DB upgrade exit code: $DB_RESULT"

if [ $DB_RESULT -eq 0 ]; then
  echo "Creating admin user..."
  airflow users create \
    --username admin \
    --firstname Admin \
    --lastname User \
    --role Admin \
    --email admin@example.com \
    --password admin 2>&1 | tee /logs/user_create.log
  USER_RESULT=$?
  echo "User creation exit code: $USER_RESULT"
  exit $USER_RESULT
else
  exit $DB_RESULT
fi 
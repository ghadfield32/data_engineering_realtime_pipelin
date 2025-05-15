# Airflow 3 Migration Guide

This guide outlines the step-by-step process for migrating DAGs from Airflow 2.x to Airflow 3.x, focusing on the changes implemented in this project.

## Migration Checklist

1. ✅ Update imports to match Airflow 3's provider structure
2. ✅ Replace string schedules with `MultipleCronTriggerTimetable`
3. ✅ Add `dag_display_name` for better UI experience
4. ✅ Use `Variable.get` for all credentials and configuration
5. ✅ Add automated upgrade checks
6. ✅ Fix any deprecated patterns

## Detailed Steps

### 1. Add Automated Upgrade Checks

First, add the tools needed to automatically detect deprecated patterns:

```bash
# Add to requirements.txt
apache-airflow-upgrade-check

# Add to packages.txt (for Astro projects)
ruff
```

### 2. Run Initial Compatibility Check

Before making changes, run the compatibility checks to find issues:

```bash
# Check for deprecated Airflow features
airflow upgrade_check

# Check for deprecated imports with Ruff
ruff check --select APF211 dags/
```

### 3. Fix Imports

Update all imports to use the correct paths for Airflow 3:

```python
# OLD (Airflow 2)
from airflow.providers.postgres.operator.postgres import PostgresOperator

# NEW (Airflow 3)
from airflow.providers.postgres.operators.postgres import PostgresOperator
```

### 4. Update Schedules

Replace string schedules with `MultipleCronTriggerTimetable` for more flexibility:

```python
# OLD (Airflow 2)
@dag(
    schedule_interval="@daily",
    # ...
)

# NEW (Airflow 3)
from airflow.timetables.trigger import MultipleCronTriggerTimetable

@dag(
    schedule=MultipleCronTriggerTimetable(
        "0 10 * * *",  # 10 AM daily
        timezone="UTC"
    ),
    # ...
)
```

For asset-based scheduling, the format is already compatible with Airflow 3:

```python
@dag(
    schedule=[my_asset],  # Asset-driven scheduling
    # ...
)
```

### 5. Add Friendly UI Names

Add `dag_display_name` to improve UI discoverability:

```python
@dag(
    dag_display_name="My Descriptive DAG Name 🚀",
    # ...
)
```

### 6. Use `Variable.get` for Credentials

Replace direct environment variable access with Airflow Variables:

```python
# OLD (Airflow 2)
api_key = os.getenv("API_KEY")

# NEW (Airflow 3)
from airflow.models import Variable
api_key = Variable.get("API_KEY", default_var=os.getenv("API_KEY"))
```

### 7. Validate Changes

After making changes, run the validation script to ensure everything is migrated properly:

```bash
./validate_airflow3.sh
```

## Benefits of Migration

1. **Better UI Experience**: Friendly DAG names and improved UI components
2. **More Flexible Scheduling**: Multiple schedules in one DAG
3. **Centralized Configuration**: Configuration in Airflow UI instead of environment variables
4. **Early Warning System**: Automated checks catch issues before they cause problems
5. **Improved Security**: Better credential management with Variable.get

## Resources

- [Apache Airflow 3.0 Documentation](https://airflow.apache.org/docs/apache-airflow/3.0.0/)
- [Astronomer Airflow 3 Features Guide](https://www.astronomer.io/docs/astro/airflow3/features-af3/)
- [Airflow Timetables Documentation](https://airflow.apache.org/docs/apache-airflow/stable/authoring-and-scheduling/timetable.html)
- [Airflow Upgrade Check Tool](https://github.com/apache/airflow/tree/main/dev/airflow-upgrade-check) 
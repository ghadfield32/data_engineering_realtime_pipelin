


-- Create kestra database
CREATE DATABASE kestra;

-- Create database for real-time pipeline
CREATE DATABASE real_time_pipeline;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE kestra TO airflow;
GRANT ALL PRIVILEGES ON DATABASE real_time_pipeline TO airflow; 



###############################################################################
# AWS Infrastructure for GTFS Data Pipeline
###############################################################################
# This Terraform configuration sets up all the AWS resources needed to run
# the GTFS data pipeline. It creates:
# - S3 bucket for raw and processed data
# - Lambda function for ingestion
# - CloudWatch Event Rule for scheduled execution
# - IAM roles and policies
# - Optional Athena workgroup and database

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Uncomment to use a specific profile from your AWS CLI configuration
  # profile = "your-profile"
  
  default_tags {
    tags = {
      Project     = "data-engineering-pipeline"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

###############################################################################
# S3 Bucket for Data Storage
###############################################################################

resource "aws_s3_bucket" "data_bucket" {
  bucket = "${var.project_prefix}-${var.environment}-data-bucket"

  # Comment out to keep objects when destroying infra
  force_destroy = var.force_destroy_bucket
}

# Enable versioning
resource "aws_s3_bucket_versioning" "data_bucket_versioning" {
  bucket = aws_s3_bucket.data_bucket.id
  
  versioning_configuration {
    status = "Enabled"
  }
}

# Create buckets for different data sources
resource "aws_s3_object" "gtfs_raw_prefix" {
  bucket = aws_s3_bucket.data_bucket.id
  key    = "gtfs/raw/"
  source = "/dev/null"  # Empty object
}

resource "aws_s3_object" "gtfs_processed_prefix" {
  bucket = aws_s3_bucket.data_bucket.id
  key    = "gtfs/processed/"
  source = "/dev/null"  # Empty object
}

resource "aws_s3_object" "nba_raw_prefix" {
  bucket = aws_s3_bucket.data_bucket.id
  key    = "nba/raw/"
  source = "/dev/null"  # Empty object
}

resource "aws_s3_object" "nba_processed_prefix" {
  bucket = aws_s3_bucket.data_bucket.id
  key    = "nba/processed/"
  source = "/dev/null"  # Empty object
}

resource "aws_s3_object" "weather_raw_prefix" {
  bucket = aws_s3_bucket.data_bucket.id
  key    = "weather/raw/"
  source = "/dev/null"  # Empty object
}

resource "aws_s3_object" "weather_processed_prefix" {
  bucket = aws_s3_bucket.data_bucket.id
  key    = "weather/processed/"
  source = "/dev/null"  # Empty object
}

###############################################################################
# IAM Role for Lambda
###############################################################################

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_prefix}-${var.environment}-lambda-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      },
    ]
  })
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.project_prefix}-${var.environment}-lambda-policy"
  description = "Policy for GTFS data pipeline Lambda function"
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.data_bucket.arn,
          "${aws_s3_bucket.data_bucket.arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

###############################################################################
# Lambda Function for GTFS Ingestion
###############################################################################

# Create a zip file from the Lambda function code
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_function.zip"
  
  source {
    content  = templatefile("${path.module}/lambda_function.py.tmpl", {
      s3_bucket = aws_s3_bucket.data_bucket.id,
      s3_prefix = "gtfs/raw/"
    })
    filename = "lambda_function.py"
  }
  
  # Include common modules needed by the function
  source {
    content  = file("${path.module}/../../ingestion/fetch_gtfs.py")
    filename = "fetch_gtfs.py"
  }
}

# Lambda function for GTFS ingestion
resource "aws_lambda_function" "gtfs_ingestion" {
  function_name    = "${var.project_prefix}-${var.environment}-gtfs-ingestion"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.10"
  timeout          = 30  # seconds
  memory_size      = 256  # MB
  
  environment {
    variables = {
      S3_BUCKET = aws_s3_bucket.data_bucket.id
      S3_PREFIX = "gtfs/raw/"
      GTFS_API_URL = var.gtfs_api_url
      GTFS_API_KEY = var.gtfs_api_key
      OUTPUT_FORMAT = "json"
    }
  }
}

###############################################################################
# CloudWatch Event for Scheduled Execution
###############################################################################

resource "aws_cloudwatch_event_rule" "gtfs_schedule" {
  name                = "${var.project_prefix}-${var.environment}-gtfs-schedule"
  description         = "Schedule for GTFS data ingestion"
  schedule_expression = "rate(15 minutes)"
}

resource "aws_cloudwatch_event_target" "gtfs_lambda_target" {
  rule      = aws_cloudwatch_event_rule.gtfs_schedule.name
  target_id = "TriggerGTFSLambda"
  arn       = aws_lambda_function.gtfs_ingestion.arn
}

resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.gtfs_ingestion.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.gtfs_schedule.arn
}

###############################################################################
# Athena Setup for Querying
###############################################################################

resource "aws_athena_workgroup" "gtfs_workgroup" {
  count = var.create_athena_resources ? 1 : 0
  
  name        = "${var.project_prefix}-${var.environment}-workgroup"
  description = "Workgroup for GTFS data analysis"
  
  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    
    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_bucket.bucket}/athena-results/"
    }
  }
}

resource "aws_glue_catalog_database" "gtfs_database" {
  count = var.create_athena_resources ? 1 : 0
  
  name        = replace("${var.project_prefix}_${var.environment}_db", "-", "_")
  description = "Database for GTFS data"
}

###############################################################################
# Outputs
###############################################################################

output "s3_bucket_name" {
  description = "The name of the S3 bucket created"
  value       = aws_s3_bucket.data_bucket.id
}

output "lambda_function_name" {
  description = "The name of the Lambda function created"
  value       = aws_lambda_function.gtfs_ingestion.function_name
}

output "lambda_function_arn" {
  description = "The ARN of the Lambda function created"
  value       = aws_lambda_function.gtfs_ingestion.arn
}

output "cloudwatch_schedule" {
  description = "The CloudWatch schedule expression"
  value       = aws_cloudwatch_event_rule.gtfs_schedule.schedule_expression
}

output "athena_workgroup" {
  description = "The Athena workgroup name (if created)"
  value       = var.create_athena_resources ? aws_athena_workgroup.gtfs_workgroup[0].name : "Not created"
} 
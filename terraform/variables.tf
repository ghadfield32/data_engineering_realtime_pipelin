variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Name of the project for resource naming"
  type        = string
  default     = "data-pipeline"
}

variable "key_name" {
  description = "Name of the AWS key pair to use for EC2 instance"
  type        = string
  default     = "data-pipeline-key"
}

variable "ec2_ami" {
  description = "AMI ID for the EC2 instance (Amazon Linux 2)"
  type        = string
  # Amazon Linux 2 AMI in us-east-1
  default     = "ami-0c94855ba95c71c99"
}

variable "db_username" {
  description = "Username for PostgreSQL database"
  type        = string
  default     = "airflow"
  sensitive   = true
}

variable "db_password" {
  description = "Password for PostgreSQL database"
  type        = string
  default     = "airflow123"
  sensitive   = true
} 
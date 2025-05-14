###############################################################################
# Variables for AWS Infrastructure
###############################################################################

variable "aws_region" {
  description = "AWS Region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod"
  }
}

variable "project_prefix" {
  description = "Prefix for all resource names"
  type        = string
  default     = "data-pipeline"
}

variable "force_destroy_bucket" {
  description = "Allow Terraform to destroy buckets even if they contain objects"
  type        = bool
  default     = true
}

variable "gtfs_api_url" {
  description = "URL for the GTFS Realtime API"
  type        = string
  default     = "https://gtfsrt.prod.obanyc.com/vehiclePositions"
}

variable "gtfs_api_key" {
  description = "API key for the GTFS Realtime API (if required)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "create_athena_resources" {
  description = "Whether to create Athena resources (workgroup, database)"
  type        = bool
  default     = true
} 
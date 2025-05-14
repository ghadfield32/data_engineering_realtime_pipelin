terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.0.0"
  
  # Uncomment to use remote state
  # backend "s3" {
  #   bucket  = "your-terraform-state-bucket"
  #   key     = "data-pipeline/terraform.tfstate"
  #   region  = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region
  
  # Use these for local development
  # profile = "your-profile"
  # shared_credentials_file = "~/.aws/credentials"
  
  default_tags {
    tags = {
      Project     = "data-engineering-realtime-pipeline"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# VPC and Network Configuration
resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.project_name}-vpc"
  }
}

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-public-subnet"
  }
}

resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.2.0/24"
  availability_zone       = "${var.aws_region}b"
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.project_name}-private-subnet"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.project_name}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.project_name}-public-route-table"
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# Security Group for EC2 instance
resource "aws_security_group" "ec2_sg" {
  name        = "${var.project_name}-ec2-sg"
  description = "Security group for data pipeline EC2 instance"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "SSH access"
  }
  
  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Airflow WebUI access"
  }
  
  ingress {
    from_port   = 8083
    to_port     = 8083
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Kestra WebUI access"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name = "${var.project_name}-ec2-sg"
  }
}

# Free tier EC2 instance (t2.micro)
resource "aws_instance" "pipeline_server" {
  ami                    = var.ec2_ami # Amazon Linux 2 AMI
  instance_type          = "t2.micro"  # Free tier eligible
  key_name               = var.key_name
  subnet_id              = aws_subnet.public.id
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]
  
  root_block_device {
    volume_type = "gp2"
    volume_size = 30
  }

  user_data = <<-EOF
              #!/bin/bash
              sudo yum update -y
              sudo yum install -y docker git jq
              sudo systemctl start docker
              sudo systemctl enable docker
              sudo usermod -a -G docker ec2-user
              sudo curl -L "https://github.com/docker/compose/releases/download/v2.15.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
              sudo chmod +x /usr/local/bin/docker-compose
              
              # Clone repository
              git clone https://github.com/yourusername/data_engineering_realtime_pipeline.git /home/ec2-user/data_engineering_realtime_pipeline
              chown -R ec2-user:ec2-user /home/ec2-user/data_engineering_realtime_pipeline
              
              # Start pipeline
              cd /home/ec2-user/data_engineering_realtime_pipeline
              sudo -u ec2-user docker-compose up -d
              EOF

  tags = {
    Name = "${var.project_name}-server"
  }
}

# Free tier RDS (db.t3.micro)
resource "aws_db_subnet_group" "main" {
  name        = "${var.project_name}-db-subnet-group"
  description = "Database subnet group for ${var.project_name}"
  subnet_ids  = [aws_subnet.public.id, aws_subnet.private.id]
}

resource "aws_security_group" "rds_sg" {
  name        = "${var.project_name}-rds-sg"
  description = "Security group for RDS instance"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2_sg.id]
    description     = "PostgreSQL access from EC2"
  }

  tags = {
    Name = "${var.project_name}-rds-sg"
  }
}

resource "aws_db_instance" "postgres" {
  identifier              = "${var.project_name}-db"
  allocated_storage       = 20
  storage_type            = "gp2"
  engine                  = "postgres"
  engine_version          = "15.3"
  instance_class          = "db.t3.micro"  # Free tier eligible
  db_name                 = "airflow"
  username                = var.db_username
  password                = var.db_password
  parameter_group_name    = "default.postgres15"
  db_subnet_group_name    = aws_db_subnet_group.main.name
  vpc_security_group_ids  = [aws_security_group.rds_sg.id]
  skip_final_snapshot     = true
  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "Mon:04:00-Mon:05:00"
  
  tags = {
    Name = "${var.project_name}-postgres"
  }
} 
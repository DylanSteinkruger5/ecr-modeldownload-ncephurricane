variable "region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
}

variable "public_subnets" {
  type = list(string)
}

variable "security_groups" {
  type = list(string)
}

variable "sqs_queue_name" {
  type = string
}

variable "container_image" {
  type = string
}

variable "ecr_repository_name" {
  type = string
}

variable "ecr_image_tag" {
  type    = string
  default = "latest"
}

variable "task_s3_resources" {
  type = list(string)
}

variable "target_visible_messages" {
  type    = number
  default = 0.5
}

variable "scale_out_cooldown" {
  type    = number
  default = 60
}

variable "scale_in_cooldown" {
  type    = number
  default = 60
}

variable "min_tasks" {
  type    = number
  default = 0
}

variable "max_tasks" {
  type    = number
  default = 5
}


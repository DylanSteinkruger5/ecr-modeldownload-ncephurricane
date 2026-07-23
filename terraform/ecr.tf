data "aws_ecr_repository" "worker" {
  name = var.ecr_repository_name
}

data "aws_ecr_image" "worker_tag" {
  repository_name = var.ecr_repository_name
  image_tag       = var.ecr_image_tag
}

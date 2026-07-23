resource "aws_ecs_service" "app" {
  name            = "${var.project}-svc"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.app.arn
  desired_count   = var.min_tasks
  launch_type     = null
  platform_version = "LATEST"

  network_configuration {
    subnets          = var.public_subnets
    security_groups  = var.security_groups
    assign_public_ip = true
  }

  # Strong bias to FARGATE_SPOT; tiny weight on FARGATE keeps automatic fallback
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 99
  }
  capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }

  lifecycle {
    # Let Application Auto Scaling control desired_count
    ignore_changes = [desired_count]
  }
}

# Target: keep ApproximateNumberOfMessagesVisible near 0

resource "aws_appautoscaling_target" "svc" {
  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.app.name}"
  min_capacity       = var.min_tasks
  max_capacity       = var.max_tasks
}

resource "aws_appautoscaling_policy" "visible_zero" {
  name               = "${var.project}-visible-zero"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.svc.service_namespace
  scalable_dimension = aws_appautoscaling_target.svc.scalable_dimension
  resource_id        = aws_appautoscaling_target.svc.resource_id

  target_tracking_scaling_policy_configuration {
    target_value       = var.target_visible_messages   # e.g., 0.5 or 1
    scale_in_cooldown  = var.scale_in_cooldown        # e.g., 120–180
    scale_out_cooldown = var.scale_out_cooldown       # e.g., 60

    customized_metric_specification {
      metric_name = "ApproximateNumberOfMessagesVisible"
      namespace   = "AWS/SQS"
      statistic   = "Average"
      dimensions {
        name  = "QueueName"
        value = var.sqs_queue_name   # queue NAME, not URL
      }
    }
  }
}

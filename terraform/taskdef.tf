resource "aws_ecs_task_definition" "app" {
  family                   = "${var.project}-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "1024"
  memory                   = "4096"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "worker",
      image     = "${data.aws_ecr_repository.worker.repository_url}@${data.aws_ecr_image.worker_tag.image_digest}",
      essential = true,

      workingDirectory = "/app",
      command          = ["-u", "/app/lambda_function.py"],

      environment = [
        # use the actual URL to avoid name mismatches
        { name = "AWS_REGION", value = var.region },
        { name = "PYTHONUNBUFFERED", value = "1" },
        { name = "SQS_QUEUE_NAME",    value = var.sqs_queue_name }
      ],

      logConfiguration = {
        logDriver = "awslogs",
        options = {
          awslogs-group         = aws_cloudwatch_log_group.app.name,
          awslogs-region        = var.region,
          awslogs-stream-prefix = "ecs"
        }
      }
    }
  ])

}

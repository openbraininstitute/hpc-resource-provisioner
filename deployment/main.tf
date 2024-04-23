# Install our simple lambdas
# No runtime required, only boto3

resource "aws_iam_role" "lambda_role_all" {
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "AWSLambda_Read" {
  role       = aws_iam_role.lambda_role_all.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

data "archive_file" "hpc_provisioner_package" {
    type = "zip"
    source_dir = "${path.module}/lambda_package"
    output_path = "hpc_provisioner.zip"
}

resource "aws_lambda_function" "hpc_provisioner_lambda" {
    function_name = "hpc_provisioner"
    filename      = "hpc_provisioner.zip"
    source_code_hash = data.archive_file.hpc_provisioner_package.output_base64sha256
    role          = aws_iam_role.lambda_role_all.arn
    runtime       = "python3.9"
    handler       = "provisioner_handlers.pcluster_create_handler"
    timeout       = 10
}

# resource "aws_lambda_function" "resource_discovery_lambda_detail" {
#     function_name = "vlab_resource_discovery_detail"
#     filename      = "resource_discovery.zip"
#     source_code_hash = data.archive_file.resource_discovery_package.output_base64sha256
#     role          = aws_iam_role.lambda_role_all.arn
#     runtime       = "python3.9"
#     handler       = "list_vlab_resources.detail_handler"
#     timeout       = 10
# }

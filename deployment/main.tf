resource "aws_cloudwatch_log_group" "hpc_resource_provisioner_log_group" {
  name              = "/aws/lambda/auto-hpc-resource-provisioner"
  retention_in_days = 7
}

resource "aws_lambda_permission" "hpc_resource_provisioner_permission_post" {
  statement_id  = "AllowAPIGatewayInvokePOST"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.hpc_resource_provisioner_lambda.function_name
  principal     = "apigateway.amazonaws.com"
}

resource "aws_lambda_function" "hpc_resource_provisioner_lambda" {
  function_name = "auto-hpc-resource-provisioner"
  role          = var.hpc_resource_provisioner_role
  image_uri     = var.hpc_resource_provisioner_image_uri
  package_type  = "Image"
  architectures = ["x86_64"]
  timeout       = 90
  memory_size   = 1024
  vpc_config {
    security_group_ids = var.hpc_resource_provisioner_sg_ids
    subnet_ids         = var.hpc_resource_provisioner_subnet_ids
  }
}

resource "aws_api_gateway_rest_api" "hpc_resource_provisioner_api" {
  name = "auto-hpc_resource_provisioner"
}

resource "aws_api_gateway_resource" "hpc_resource_provisioner_res_provisioner" {
  rest_api_id = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  parent_id   = aws_api_gateway_rest_api.hpc_resource_provisioner_api.root_resource_id
  path_part   = "hpc-provisioner"
}

resource "aws_api_gateway_resource" "hpc_resource_provisioner_res_pcluster" {
  rest_api_id = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  parent_id   = aws_api_gateway_resource.hpc_resource_provisioner_res_provisioner.id
  path_part   = "pcluster"
}

resource "aws_api_gateway_method" "hpc_resource_provisioner_pcluster_method_get" {
  rest_api_id   = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  resource_id   = aws_api_gateway_resource.hpc_resource_provisioner_res_pcluster.id
  http_method   = "GET"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_method" "hpc_resource_provisioner_pcluster_method_post" {
  rest_api_id   = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  resource_id   = aws_api_gateway_resource.hpc_resource_provisioner_res_pcluster.id
  http_method   = "POST"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_method" "hpc_resource_provisioner_pcluster_method_delete" {
  rest_api_id   = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  resource_id   = aws_api_gateway_resource.hpc_resource_provisioner_res_pcluster.id
  http_method   = "DELETE"
  authorization = "AWS_IAM"
}

resource "aws_api_gateway_integration" "hpc_resource_provisioner_integration_get" {
  rest_api_id             = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  resource_id             = aws_api_gateway_resource.hpc_resource_provisioner_res_pcluster.id
  http_method             = aws_api_gateway_method.hpc_resource_provisioner_pcluster_method_get.http_method
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.hpc_resource_provisioner_lambda.invoke_arn
  integration_http_method = "POST"
}

resource "aws_api_gateway_integration" "hpc_resource_provisioner_integration_post" {
  rest_api_id             = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  resource_id             = aws_api_gateway_resource.hpc_resource_provisioner_res_pcluster.id
  http_method             = aws_api_gateway_method.hpc_resource_provisioner_pcluster_method_post.http_method
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.hpc_resource_provisioner_lambda.invoke_arn
  integration_http_method = "POST"
}
resource "aws_api_gateway_integration" "hpc_resource_provisioner_integration_delete" {
  rest_api_id             = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  resource_id             = aws_api_gateway_resource.hpc_resource_provisioner_res_pcluster.id
  http_method             = aws_api_gateway_method.hpc_resource_provisioner_pcluster_method_delete.http_method
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.hpc_resource_provisioner_lambda.invoke_arn
  integration_http_method = "POST"
}


resource "aws_api_gateway_deployment" "hpc_resource_provisioner_api_deployment" {
  rest_api_id = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  triggers = {
    # redeploy when the api or its methods change, but also serves to declare a dependency
    # if omitted, terraform may deploy the deployment before the methods
    redeployment = sha1(jsonencode([
      aws_api_gateway_rest_api.hpc_resource_provisioner_api.body,
      aws_api_gateway_method.hpc_resource_provisioner_pcluster_method_get.id,
      aws_api_gateway_method.hpc_resource_provisioner_pcluster_method_post.id,
      aws_api_gateway_method.hpc_resource_provisioner_pcluster_method_delete.id,
      aws_lambda_function.hpc_resource_provisioner_lambda
    ]))
  }
}

resource "aws_api_gateway_stage" "hpc_resource_provisioner_api_stage" {
  rest_api_id   = aws_api_gateway_rest_api.hpc_resource_provisioner_api.id
  stage_name    = "production"
  deployment_id = aws_api_gateway_deployment.hpc_resource_provisioner_api_deployment.id
}

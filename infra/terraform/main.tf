# 1. Create project
resource "railway_project" "dunner_project" {
  name        = "dunner-production"
  description = "Motor de Dunning Serverless"
}

# 2. Create service
resource "railway_service" "dunner_api" {
  project_id      = railway_project.dunner_project.id
  name            = "dunner-api"
  source_repo     = var.github_repo
}

# 3. Inject environment variables
resource "railway_variable" "db_url" {
  project_id     = railway_project.dunner_project.id
  service_id     = railway_service.dunner_api.id
  environment_id = railway_project.dunner_project.default_environment.id
  name           = "DATABASE_URL"
  value          = var.database_url
}

resource "railway_variable" "qstash_token" {
  project_id     = railway_project.dunner_project.id
  service_id     = railway_service.dunner_api.id
  environment_id = railway_project.dunner_project.default_environment.id
  name           = "QSTASH_TOKEN"
  value          = var.qstash_token
}

resource "railway_variable" "qstash_curr_key" {
  project_id     = railway_project.dunner_project.id
  service_id     = railway_service.dunner_api.id
  environment_id = railway_project.dunner_project.default_environment.id
  name           = "QSTASH_CURRENT_SIGNING_KEY"
  value          = var.qstash_current_signing_key
}

resource "railway_variable" "qstash_next_key" {
  project_id     = railway_project.dunner_project.id
  service_id     = railway_service.dunner_api.id
  environment_id = railway_project.dunner_project.default_environment.id
  name           = "QSTASH_NEXT_SIGNING_KEY"
  value          = var.qstash_next_signing_key
}

resource "railway_variable" "qstash_url" {
  project_id     = railway_project.dunner_project.id
  service_id     = railway_service.dunner_api.id
  environment_id = railway_project.dunner_project.default_environment.id
  name           = "QSTASH_URL"
  value          = var.qstash_url
}

# Public URL for the service
resource "railway_variable" "public_api_url" {
  project_id     = railway_project.dunner_project.id
  service_id     = railway_service.dunner_api.id
  environment_id = railway_project.dunner_project.default_environment.id
  name           = "PUBLIC_API_URL"
  value          = "https://${railway_service.dunner_api.name}-production.up.railway.app" 
}
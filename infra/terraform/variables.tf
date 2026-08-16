variable "upstash_email" {
  description = "Email of your Upstash account"
  type        = string
}

variable "upstash_api_key" {
  description = "Global API key for Upstash"
  type        = string
  sensitive   = true
}

variable "supabase_access_token" {
  description = "Personal access token for Supabase"
  type        = string
  sensitive   = true
}

variable "railway_token" {
  description = "Personal token for Railway"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "Supabase connection URL"
  type        = string
  sensitive   = true
}

variable "qstash_token" {
  type        = string
  sensitive   = true
}

variable "qstash_current_signing_key" {
  type        = string
  sensitive   = true
}

variable "qstash_next_signing_key" {
  type        = string
  sensitive   = true
}

variable "qstash_url" {
  type        = string
}

variable "github_repo" {
  description = "Your GitHub user and repo"
  type        = string
}
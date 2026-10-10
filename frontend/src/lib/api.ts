/**
 * Central API configuration
 * Reads backend URL from VITE_API_BASE_URL (e.g. your Azure Container Apps URL in production)
 * Defaults to http://localhost:8000 for local development
 */
const rawApiUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"

export const API_BASE_URL = rawApiUrl.replace(/['"]/g, '').replace(/\/+$/, '').trim()

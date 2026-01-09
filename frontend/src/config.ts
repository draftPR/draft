/**
 * Application configuration
 */
export const config = {
  /**
   * Backend API base URL
   */
  backendBaseUrl: import.meta.env.VITE_BACKEND_URL || "http://localhost:8000",
  
  /**
   * Application name
   */
  appName: "Orion Kanban",
} as const;



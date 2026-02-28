"""Project template registry with pre-configured board setups."""

from typing import TypedDict


class TemplateGoal(TypedDict, total=False):
    """A starter goal for a template."""

    title: str
    description: str


class ProjectTemplate(TypedDict):
    """A project template with pre-configured settings and starter goals."""

    id: str
    name: str
    description: str
    icon: str
    category: str
    config: dict
    starter_goals: list[TemplateGoal]
    tags: list[str]


TEMPLATES: list[ProjectTemplate] = [
    {
        "id": "web-app",
        "name": "Web Application",
        "description": "Modern web app with React, Next.js, or Vue. Optimized for UI development.",
        "icon": "🌐",
        "category": "Frontend",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 300,
            }
        },
        "starter_goals": [
            {
                "title": "Set up project structure",
                "description": "Initialize the web app with proper folder structure, routing, and build configuration.",
            },
            {
                "title": "Implement responsive layout",
                "description": "Create a mobile-first responsive layout with navigation and theming support.",
            },
        ],
        "tags": ["react", "nextjs", "vue", "frontend", "ui"],
    },
    {
        "id": "api-service",
        "name": "API Service",
        "description": "REST or GraphQL API with FastAPI, Express, or Django. Optimized for backend development.",
        "icon": "🔌",
        "category": "Backend",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 400,
            }
        },
        "starter_goals": [
            {
                "title": "Set up API framework",
                "description": "Initialize the API with routing, middleware, and database connection.",
            },
            {
                "title": "Add authentication",
                "description": "Implement JWT or OAuth authentication with proper security.",
            },
            {
                "title": "Add API documentation",
                "description": "Generate OpenAPI/Swagger docs with examples and schemas.",
            },
        ],
        "tags": ["api", "fastapi", "express", "django", "backend", "rest", "graphql"],
    },
    {
        "id": "mobile-app",
        "name": "Mobile App",
        "description": "Cross-platform mobile app with React Native or Flutter. Optimized for mobile development.",
        "icon": "📱",
        "category": "Mobile",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 350,
            }
        },
        "starter_goals": [
            {
                "title": "Set up navigation",
                "description": "Configure screen navigation and routing for iOS and Android.",
            },
            {
                "title": "Implement offline support",
                "description": "Add local data persistence and offline-first architecture.",
            },
        ],
        "tags": ["mobile", "react-native", "flutter", "ios", "android"],
    },
    {
        "id": "data-pipeline",
        "name": "Data Pipeline",
        "description": "ETL/analytics pipeline with longer timeout for data processing tasks.",
        "icon": "📊",
        "category": "Data",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 600,  # 10 minutes for data processing
            }
        },
        "starter_goals": [
            {
                "title": "Set up data sources",
                "description": "Configure connections to databases, APIs, or file sources.",
            },
            {
                "title": "Build transformation pipeline",
                "description": "Implement data cleaning, validation, and transformation logic.",
            },
            {
                "title": "Add monitoring and alerts",
                "description": "Set up pipeline monitoring, error handling, and alerting.",
            },
        ],
        "tags": ["data", "etl", "analytics", "pipeline", "airflow", "spark"],
    },
    {
        "id": "docs-site",
        "name": "Documentation Site",
        "description": "Documentation with Docusaurus, MkDocs, or VitePress. Optimized for content writing.",
        "icon": "📚",
        "category": "Content",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 250,
            }
        },
        "starter_goals": [
            {
                "title": "Set up docs structure",
                "description": "Organize content into sections with proper navigation.",
            },
            {
                "title": "Add search functionality",
                "description": "Implement full-text search across documentation.",
            },
        ],
        "tags": ["docs", "documentation", "docusaurus", "mkdocs", "vitepress"],
    },
    {
        "id": "library",
        "name": "Library/Package",
        "description": "Reusable library or NPM/PyPI package. Optimized for library development.",
        "icon": "📦",
        "category": "Library",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 300,
            }
        },
        "starter_goals": [
            {
                "title": "Set up build and packaging",
                "description": "Configure build tools, TypeScript/types, and package.json/pyproject.toml.",
            },
            {
                "title": "Add comprehensive tests",
                "description": "Implement unit tests with high coverage and CI integration.",
            },
            {
                "title": "Create usage examples",
                "description": "Write clear examples and API documentation for library users.",
            },
        ],
        "tags": ["library", "package", "npm", "pypi", "sdk"],
    },
    {
        "id": "ml-model",
        "name": "Machine Learning",
        "description": "ML/AI model with training pipelines. Extended timeout for model training.",
        "icon": "🤖",
        "category": "AI/ML",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 900,  # 15 minutes for training
            }
        },
        "starter_goals": [
            {
                "title": "Set up training pipeline",
                "description": "Configure data loading, model architecture, and training loop.",
            },
            {
                "title": "Add experiment tracking",
                "description": "Integrate MLflow, Weights & Biases, or similar for experiment tracking.",
            },
            {
                "title": "Implement model evaluation",
                "description": "Create evaluation metrics, validation splits, and model comparison.",
            },
        ],
        "tags": ["ml", "ai", "machine-learning", "pytorch", "tensorflow", "scikit-learn"],
    },
    {
        "id": "blank",
        "name": "Blank Project",
        "description": "Start from scratch with default settings. No starter goals.",
        "icon": "✨",
        "category": "Other",
        "config": {
            "execute_config": {
                "executor_model": "sonnet-4.5",
                "timeout": 300,
            }
        },
        "starter_goals": [],
        "tags": ["blank", "custom"],
    },
]


def get_template(template_id: str) -> ProjectTemplate | None:
    """Get a template by ID."""
    return next((t for t in TEMPLATES if t["id"] == template_id), None)


def list_templates() -> list[ProjectTemplate]:
    """List all available templates."""
    return TEMPLATES

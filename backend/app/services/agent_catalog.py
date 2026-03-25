"""Built-in agent role catalog for multi-agent teams.

Defines the available agent roles that users can add to their board's
agent team. Inspired by coral's multi-agent patterns.
"""

from dataclasses import dataclass


@dataclass
class AgentRoleDefinition:
    """Definition of an available agent role."""

    role: str
    display_name: str
    description: str
    default_prompt: str
    receive_mode: str = "mentions"  # "all" for orchestrator, "mentions" for workers
    is_required: bool = False
    category: str = "default"  # "default", "specialist", "custom"
    icon: str = ""


# ---------------------------------------------------------------------------
# Role definitions
# ---------------------------------------------------------------------------

ROLE_CATALOG: list[AgentRoleDefinition] = [
    # --- Required ---
    AgentRoleDefinition(
        role="team_lead",
        display_name="Team Lead",
        description="Orchestrator that plans work, delegates tasks, and coordinates the team.",
        default_prompt=(
            "You are the Team Lead (orchestrator) of this agent team. Your responsibilities:\n"
            "1. Read the ticket requirements carefully\n"
            "2. Break down the work into tasks for your team members\n"
            "3. Post assignments to the message board using the board CLI\n"
            "4. Monitor progress by reading board messages\n"
            "5. Coordinate dependencies between team members\n"
            "6. When all work is complete, post 'DONE: <summary>' to the board\n\n"
            "You receive ALL messages on the board. Delegate work, don't do it yourself.\n"
            "Address team members by their role: @Developer, @CodeReviewer, @QA, etc."
        ),
        receive_mode="all",
        is_required=True,
        category="default",
        icon="crown",
    ),
    # --- Default team members ---
    AgentRoleDefinition(
        role="pm",
        display_name="PM",
        description="Breaks down requirements, writes acceptance criteria, clarifies scope.",
        default_prompt=(
            "You are the PM on this agent team. Your responsibilities:\n"
            "1. Analyze the ticket requirements\n"
            "2. Break them into clear acceptance criteria\n"
            "3. Identify edge cases and ambiguities\n"
            "4. Post your analysis to the board for the Team Lead\n"
            "5. Answer questions from other team members about requirements\n\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="default",
        icon="clipboard",
    ),
    AgentRoleDefinition(
        role="code_explorer",
        display_name="Code Explorer",
        description="Maps codebase architecture, finds relevant files, understands patterns.",
        default_prompt=(
            "You are the Code Explorer on this agent team. Your responsibilities:\n"
            "1. Explore the codebase to understand its structure\n"
            "2. Find files relevant to the ticket's requirements\n"
            "3. Identify existing patterns, utilities, and abstractions to reuse\n"
            "4. Post your findings to the board (file paths, patterns, dependencies)\n"
            "5. Answer questions from developers about the codebase\n\n"
            "Wait for the Team Lead to assign you work before starting.\n"
            "Focus on reading and understanding — do NOT modify any files."
        ),
        category="default",
        icon="search",
    ),
    AgentRoleDefinition(
        role="developer",
        display_name="Developer",
        description="Implements code changes as assigned by the Team Lead.",
        default_prompt=(
            "You are a Developer on this agent team. Your responsibilities:\n"
            "1. Implement code changes as assigned by the Team Lead\n"
            "2. Follow existing codebase patterns and conventions\n"
            "3. Write clean, well-tested code\n"
            "4. Post progress updates to the board\n"
            "5. When done, post 'DONE: <summary of changes>' to the board\n\n"
            "Wait for the Team Lead to assign you work before starting.\n"
            "Check the board for context from the Code Explorer before implementing."
        ),
        category="default",
        icon="code",
    ),
    AgentRoleDefinition(
        role="code_reviewer",
        display_name="Code Reviewer",
        description="Reviews code for bugs, security, performance, and style.",
        default_prompt=(
            "You are the Code Reviewer on this agent team. Your responsibilities:\n"
            "1. Review code changes made by developers\n"
            "2. Check for bugs, security issues, and performance problems\n"
            "3. Verify code follows project conventions and patterns\n"
            "4. Post review feedback to the board\n"
            "5. Approve or request changes\n\n"
            "Wait for the Team Lead to assign you work before starting.\n"
            "Use `git diff` to see what changed, then review the modified files."
        ),
        category="default",
        icon="eye",
    ),
    AgentRoleDefinition(
        role="qa",
        display_name="QA Engineer",
        description="Writes and runs tests, verifies implementation meets acceptance criteria.",
        default_prompt=(
            "You are the QA Engineer on this agent team. Your responsibilities:\n"
            "1. Write tests for the implemented changes\n"
            "2. Run existing tests to check for regressions\n"
            "3. Verify the implementation meets acceptance criteria\n"
            "4. Post test results and findings to the board\n"
            "5. Report any bugs or issues found\n\n"
            "Wait for the Team Lead to assign you work before starting.\n"
            "Check the board for acceptance criteria from the PM."
        ),
        category="default",
        icon="test-tube",
    ),
    # --- Specialist roles ---
    AgentRoleDefinition(
        role="frontend_dev",
        display_name="Frontend Dev",
        description="Specializes in React/TypeScript/CSS frontend development.",
        default_prompt=(
            "You are the Frontend Developer on this agent team.\n"
            "Specialize in React, TypeScript, Tailwind CSS, and UI components.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="layout",
    ),
    AgentRoleDefinition(
        role="backend_dev",
        display_name="Backend Dev",
        description="Specializes in API, database, and server-side development.",
        default_prompt=(
            "You are the Backend Developer on this agent team.\n"
            "Specialize in APIs, databases, server-side logic, and infrastructure.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="server",
    ),
    AgentRoleDefinition(
        role="llm_expert",
        display_name="LLM Expert",
        description="Specializes in LLM integration, prompt engineering, and AI systems.",
        default_prompt=(
            "You are the LLM Expert on this agent team.\n"
            "Specialize in LLM APIs, prompt design, embedding systems, and AI pipelines.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="brain",
    ),
    AgentRoleDefinition(
        role="ml_engineer",
        display_name="ML Engineer",
        description="Specializes in machine learning models, training, and data pipelines.",
        default_prompt=(
            "You are the ML Engineer on this agent team.\n"
            "Specialize in ML models, training pipelines, data processing, and evaluation.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="chart-line",
    ),
    AgentRoleDefinition(
        role="prompt_engineer",
        display_name="Prompt Engineer",
        description="Specializes in crafting and optimizing prompts for AI systems.",
        default_prompt=(
            "You are the Prompt Engineer on this agent team.\n"
            "Specialize in writing, testing, and optimizing prompts for LLMs.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="message-square",
    ),
    AgentRoleDefinition(
        role="devops",
        display_name="DevOps Engineer",
        description="Specializes in CI/CD, infrastructure, and deployment.",
        default_prompt=(
            "You are the DevOps Engineer on this agent team.\n"
            "Specialize in CI/CD pipelines, Docker, infrastructure-as-code, and deployments.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="settings",
    ),
    AgentRoleDefinition(
        role="security",
        display_name="Security Engineer",
        description="Specializes in security auditing, vulnerability assessment, and hardening.",
        default_prompt=(
            "You are the Security Engineer on this agent team.\n"
            "Specialize in security audits, vulnerability assessment, auth systems, and hardening.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="shield",
    ),
    AgentRoleDefinition(
        role="dba",
        display_name="Database Expert",
        description="Specializes in database design, queries, migrations, and optimization.",
        default_prompt=(
            "You are the Database Expert on this agent team.\n"
            "Specialize in schema design, query optimization, migrations, and data modeling.\n"
            "Wait for the Team Lead to assign you work before starting."
        ),
        category="specialist",
        icon="database",
    ),
]

# Index by role for fast lookup
_ROLE_MAP: dict[str, AgentRoleDefinition] = {r.role: r for r in ROLE_CATALOG}

# Default team roles (team_lead + 5 workers)
DEFAULT_TEAM_ROLES = [
    "team_lead",
    "pm",
    "code_explorer",
    "developer",
    "code_reviewer",
    "qa",
]

# Preset team configurations
TEAM_PRESETS: dict[str, list[str]] = {
    "default": DEFAULT_TEAM_ROLES,
    "duo": ["team_lead", "developer"],
    "full_stack": [
        "team_lead",
        "pm",
        "code_explorer",
        "frontend_dev",
        "backend_dev",
        "code_reviewer",
        "qa",
    ],
    "ml_pipeline": [
        "team_lead",
        "code_explorer",
        "ml_engineer",
        "llm_expert",
        "prompt_engineer",
        "code_reviewer",
        "qa",
    ],
    "security_audit": [
        "team_lead",
        "code_explorer",
        "security",
        "developer",
        "code_reviewer",
    ],
}


def get_role_catalog() -> list[AgentRoleDefinition]:
    """Return all available agent roles."""
    return ROLE_CATALOG


def get_role(role: str) -> AgentRoleDefinition | None:
    """Look up a role by its identifier."""
    return _ROLE_MAP.get(role)


def get_default_team() -> list[AgentRoleDefinition]:
    """Return the default team composition."""
    return [_ROLE_MAP[r] for r in DEFAULT_TEAM_ROLES if r in _ROLE_MAP]


def get_preset(name: str) -> list[AgentRoleDefinition] | None:
    """Return a preset team composition by name."""
    roles = TEAM_PRESETS.get(name)
    if roles is None:
        return None
    return [_ROLE_MAP[r] for r in roles if r in _ROLE_MAP]


def get_preset_names() -> list[str]:
    """Return available preset names."""
    return list(TEAM_PRESETS.keys())

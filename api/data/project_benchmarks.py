PROJECT_BENCHMARKS = [
    {
        "name": "Stable Project",
        "nature": "predictable, low stress",
        "description": (
            "The team works on a well-defined project, such as a booking system "
            "or a simple web app. Requirements are clear and remain stable throughout."
        ),
        "conditions": [
            "no requirement changes",
            "full initial documentation",
            "realistic timeline",
        ],
        "tests": [
            "planning and task distribution",
            "architecture design",
            "delivery discipline",
        ],
    },
    {
        "name": "Production Crisis - System Failure",
        "nature": "high pressure, urgent",
        "description": (
            "A working system suddenly breaks, for example because of a critical bug "
            "or outage."
        ),
        "conditions": [
            "limited time",
            "focus on fixing, not building",
        ],
        "tests": [
            "debugging skills",
            "prioritization under pressure",
            "crisis communication",
        ],
    },
    {
        "name": "Iterative Project - Controlled Change",
        "nature": "dynamic, evolving",
        "description": (
            "The project is developed in multiple phases, with new requirements "
            "introduced at each stage. The team must continuously adapt their solution."
        ),
        "conditions": [
            "requirements revealed gradually",
            "fixed deadlines per iteration",
            "new features added mid-development",
        ],
        "tests": [
            "adaptability to change",
            "refactoring skills",
            "backlog management",
        ],
    },
    {
        "name": "Demanding Client - Changing Requirements",
        "nature": "business-driven, unstable",
        "description": (
            "A client frequently changes requirements during the project, forcing "
            "the team to constantly reassess priorities and scope."
        ),
        "conditions": [
            "requirement changes every 15-30 minutes",
            "unclear or shifting priorities",
            "conflicting feature requests",
        ],
        "tests": [
            "requirement management",
            "prioritization and trade-offs",
            "communication with stakeholders",
        ],
    },
    {
        "name": "Distributed Team - Remote Only",
        "nature": "communication-focused, asynchronous",
        "description": (
            "The team collaborates entirely remotely, relying on written communication "
            "and limited real-time interaction."
        ),
        "conditions": [
            "no face-to-face communication",
            "delayed responses between team members",
            "decisions must be documented",
        ],
        "tests": [
            "clarity in communication",
            "documentation practices",
            "coordination in distributed teams",
        ],
    },
    {
        "name": "Legacy System - Maintenance and Fixes",
        "nature": "technical debt, constrained",
        "description": (
            "The team works on an older system with limited documentation and fragile "
            "dependencies. They must fix issues and make small improvements without "
            "breaking existing functionality."
        ),
        "conditions": [
            "limited or outdated documentation",
            "high risk of regression",
            "small changes must be carefully tested",
        ],
        "tests": [
            "patience with complex existing code",
            "risk-aware decision making",
            "maintenance discipline",
        ],
    },
    {
        "name": "Deadline Cut - Time Pressure Scenario",
        "nature": "high pressure, delivery-focused",
        "description": (
            "The project deadline is suddenly shortened. The team must reduce scope, "
            "protect core value, and deliver a usable result under increased time pressure."
        ),
        "conditions": [
            "deadline reduced unexpectedly",
            "scope must be reassessed",
            "non-essential work must be postponed",
        ],
        "tests": [
            "prioritization under pressure",
            "scope management",
            "delivery focus",
        ],
    },
    {
        "name": "Quality Audit - Continuous Review",
        "nature": "quality-focused, systematic",
        "description": (
            "The team is evaluated through regular quality reviews. They must keep "
            "standards high, document decisions, and address issues continuously "
            "instead of waiting until the end."
        ),
        "conditions": [
            "regular review checkpoints",
            "quality issues must be documented",
            "improvements must be applied continuously",
        ],
        "tests": [
            "attention to detail",
            "documentation practices",
            "continuous improvement",
        ],
    },
    {
        "name": "Knowledge Gap - Missing Expertise",
        "nature": "uncertain, learning-intensive",
        "description": (
            "The team faces a problem in an area where they have limited expertise. "
            "They must learn quickly, share knowledge, and make careful decisions "
            "despite incomplete understanding."
        ),
        "conditions": [
            "missing specialist knowledge",
            "limited time to learn",
            "decisions must be made with partial information",
        ],
        "tests": [
            "learning agility",
            "knowledge sharing",
            "decision making under uncertainty",
        ],
    },
    {
        "name": "Team Conflict - Diverging Opinions",
        "nature": "collaboration-focused, tense",
        "description": (
            "Team members strongly disagree about priorities, technical direction, "
            "or ways of working. The team must resolve tension and continue making progress."
        ),
        "conditions": [
            "conflicting opinions between team members",
            "risk of delayed decisions",
            "need for constructive communication",
        ],
        "tests": [
            "conflict resolution",
            "emotional regulation",
            "collaborative decision making",
        ],
    },
    {
        "name": "Innovation Challenge - Unique Solution Required",
        "nature": "creative, ambiguous",
        "description": (
            "The team must solve a problem that has no obvious standard solution. "
            "They need to explore ideas, test assumptions, and create an original approach."
        ),
        "conditions": [
            "no clear existing solution",
            "high uncertainty at the start",
            "experimentation is required",
        ],
        "tests": [
            "creative problem solving",
            "openness to experimentation",
            "adaptability during discovery",
        ],
    },
]

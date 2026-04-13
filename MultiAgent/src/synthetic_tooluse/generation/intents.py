from typing import List
from pydantic import BaseModel, Field


class ScenarioIntent(BaseModel):
    name: str
    description: str
    positive_keywords: List[str]
    negative_keywords: List[str]
    workflow_templates: List[str] = Field(default_factory=list)
    primary_domains: List[str] = Field(
        default_factory=list,
        description="Domains used to filter the tool graph before planning.",
    )


# Intents align with curated registry domains (Travel, Finance, Productivity, Account, Knowledge).
INTENT_CONFIGS = [
    ScenarioIntent(
        name="trip planning",
        description="Plan a trip: flights, hotels, attractions, itinerary, and booking.",
        positive_keywords=["travel", "flight", "hotel", "book", "itinerary", "destination", "attraction", "schedule"],
        negative_keywords=["lyric", "game", "crypto", "stock", "shopping", "quiz", "joke"],
        primary_domains=["Travel"],
        workflow_templates=[
            "search → select → act: find flights and hotels, then book",
            "retrieve → compare → decide: hotels and attractions, then finalize itinerary",
            "plan → refine → execute: gather options, narrow dates, confirm booking",
        ],
    ),
    ScenarioIntent(
        name="budgeting and finance",
        description="Build a budget, log expenses, and set savings contributions from disposable income.",
        positive_keywords=["budget", "expense", "finance", "savings", "income", "money", "track"],
        negative_keywords=["flight", "hotel", "travel", "music", "game", "lyric", "crypto"],
        primary_domains=["Finance"],
        workflow_templates=[
            "search → select → act: compute budget, log spending category, set savings plan",
            "retrieve → compare → decide: disposable income vs goal horizon",
            "plan → refine → execute: budget baseline, expense entry, savings allocation",
        ],
    ),
    ScenarioIntent(
        name="savings and cash flow",
        description="Model monthly cash flow, record expenses, and plan savings toward a goal.",
        positive_keywords=["savings", "cash flow", "budget", "expense", "goal", "monthly"],
        negative_keywords=["stock", "crypto", "travel", "hotel", "game", "music", "reminder", "calendar"],
        primary_domains=["Finance"],
        workflow_templates=[
            "calculate_budget → track_expenses → savings_planner",
            "plan → refine → execute: income minus fixed costs, then savings rate",
        ],
    ),
    ScenarioIntent(
        name="schedule and productivity",
        description="Create schedule blocks, reminders, and calendar events.",
        positive_keywords=["calendar", "reminder", "schedule", "task", "productivity", "event", "time"],
        negative_keywords=[
            "hotel",
            "flight",
            "travel",
            "itinerary",
            "attraction",
            "destination",
            "crypto",
            "trading",
            "stock",
            "game",
            "music",
            "shopping",
        ],
        primary_domains=["Productivity"],
        workflow_templates=[
            "create_schedule → set_reminder → add_calendar_event",
            "plan → refine → execute: block time, alert, publish calendar event",
        ],
    ),
    ScenarioIntent(
        name="account management",
        description="Look up account details, review billing methods, and update payment info.",
        positive_keywords=["account", "billing", "payment", "profile", "subscription"],
        negative_keywords=["flight", "hotel", "game", "music", "lyric"],
        primary_domains=["Account"],
        workflow_templates=[
            "get_account_info → list_payment_methods → update_payment_method",
            "retrieve → compare → decide: verify account, review methods, update card",
        ],
    ),
    ScenarioIntent(
        name="research and information",
        description="Find articles on a topic and produce a grounded summary.",
        positive_keywords=["article", "search", "research", "summary", "source", "read"],
        negative_keywords=["booking", "hotel", "payment", "game", "quiz"],
        primary_domains=["Knowledge"],
        workflow_templates=[
            "search_articles → summarize_content → refine search",
            "retrieve → compare → decide: pick source, summarize, follow-up query",
        ],
    ),
]
